"""Explainable proposals and atomic, explicitly reviewed payment allocations."""

import json
import re
from collections import Counter
from datetime import date

from app.db import connect
from app.services.obligations import month_bounds


class PaymentError(ValueError):
    pass


def usd(cents):
    return "${:,}.{:02d}".format(cents // 100, cents % 100)


def review_date(value):
    try:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError()
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise PaymentError("Choose a valid review date in YYYY-MM-DD format.") from error


def payment_timing(obligation, posted_date):
    days = (date.fromisoformat(posted_date) - date.fromisoformat(obligation["due_date"])).days
    if days <= 0:
        return "Posted on or before the due date"
    if obligation["grace_days"] is None:
        return "Posted after the due date; grace period not specified"
    if days <= obligation["grace_days"]:
        return "Posted within the approved grace period"
    return "Posted after the approved grace period"


def balance(connection, obligation, as_of=None):
    sql = "SELECT coalesce(sum(a.amount_cents),0) FROM payment_allocations a JOIN transactions t ON t.id=a.transaction_id WHERE a.obligation_id=?"
    params = [obligation["id"]]
    if as_of is not None:
        sql += " AND t.posted_date<=?"
        params.append(as_of)
    paid = connection.execute(sql, params).fetchone()[0]
    return {"paid_cents": paid, "remaining_cents": obligation["amount_cents"] - paid}


def candidate_analysis(connection, period, as_of):
    first, last = month_bounds(period)
    review_date(as_of)
    transactions = connection.execute(
        "SELECT t.* FROM transactions t JOIN properties p ON p.id=t.property_id "
        "WHERE t.posted_date BETWEEN ? AND ? AND t.posted_date<=? "
        "AND NOT EXISTS (SELECT 1 FROM payment_allocations a WHERE a.transaction_id=t.id) ORDER BY t.id",
        (first.isoformat(), last.isoformat(), as_of)).fetchall()
    obligations = connection.execute(
        "SELECT * FROM rent_obligations o WHERE o.period=? AND NOT EXISTS "
        "(SELECT 1 FROM payment_allocations a WHERE a.obligation_id=o.id)", (period,)).fetchall()
    candidates = {tx["id"]: [o for o in obligations if o["property_id"] == tx["property_id"] and o["amount_cents"] == tx["amount_cents"]]
                  for tx in transactions}
    counts = Counter(o["id"] for choices in candidates.values() for o in choices)
    pairs = {(tx_id, choices[0]["id"]) for tx_id, choices in candidates.items() if len(choices) == 1 and counts[choices[0]["id"]] == 1}
    return transactions, candidates, pairs


def decision(connection, record_type, record_id, outcome, notes, reviewer="Demo owner"):
    return connection.execute(
        "INSERT INTO review_decisions(record_type, record_id, decision, reviewer_label, notes) VALUES (?, ?, ?, ?, ?)",
        (record_type, record_id, outcome, reviewer, notes)).lastrowid


def issue(connection, key, property_id, kind, reason, evidence, transaction_id=None, obligation_id=None, decision_id=None):
    existing = connection.execute("SELECT * FROM exceptions WHERE issue_key=?", (key,)).fetchone()
    if existing is None:
        issue_id = connection.execute(
            "INSERT INTO exceptions(issue_key, property_id, transaction_id, obligation_id, kind, status, initial_reason, current_reason, evidence_json) "
            "VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?)",
            (key, property_id, transaction_id, obligation_id, kind, reason, reason, json.dumps(evidence))).lastrowid
        event = "opened"
    elif existing["status"] == "open" and existing["current_reason"] != reason:
        issue_id = existing["id"]
        connection.execute("UPDATE exceptions SET current_reason=? WHERE id=?", (reason, issue_id))
        event = "updated"
    else:
        return
    connection.execute("INSERT INTO exception_events(exception_id, event, review_decision_id, notes) VALUES (?, ?, ?, ?)",
                       (issue_id, event, decision_id, reason))


def resolve_issue(connection, key, decision_id, notes):
    existing = connection.execute("SELECT id FROM exceptions WHERE issue_key=? AND status='open'", (key,)).fetchone()
    if existing:
        connection.execute("UPDATE exceptions SET status='resolved', current_reason=?, resolved_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (notes, existing["id"]))
        connection.execute("INSERT INTO exception_events(exception_id, event, review_decision_id, notes) VALUES (?, 'resolved', ?, ?)",
                           (existing["id"], decision_id, notes))


def withdraw_stale(connection, period, eligible_pairs, as_of):
    proposals = connection.execute(
        "SELECT m.* FROM match_proposals m JOIN rent_obligations o ON o.id=m.obligation_id "
        "JOIN transactions t ON t.id=m.transaction_id WHERE m.status='proposed' AND o.period=? AND t.posted_date<=?", (period, as_of)).fetchall()
    for proposal in proposals:
        if (proposal["transaction_id"], proposal["obligation_id"]) not in eligible_pairs:
            connection.execute("UPDATE match_proposals SET status='withdrawn' WHERE id=?", (proposal["id"],))
            decision(connection, "match_proposal", proposal["id"], "withdrawn", "Full-payment rules no longer support this proposal; manual review is required. No payment was recorded.", "Application rule")


def run_matching(period, as_of):
    month_bounds(period)
    as_of = review_date(as_of)
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        transactions, candidates, pairs = candidate_analysis(connection, period, as_of)
        # An earlier review date hides future candidates, without withdrawing their stored proposals.
        withdraw_stale(connection, period, pairs, as_of)
        created = 0
        for transaction in transactions:
            choices = candidates[transaction["id"]]
            pair = (transaction["id"], choices[0]["id"]) if len(choices) == 1 else None
            prior = connection.execute("SELECT * FROM match_proposals WHERE transaction_id=? AND obligation_id=?", pair).fetchone() if pair else None
            if pair in pairs and prior is None:
                obligation = choices[0]
                reason = "Exact full amount, same property account, and one candidate in {}. {}. Property assignment is separate from payer verification; review the source description and assignment evidence.".format(period, payment_timing(obligation, transaction["posted_date"]))
                connection.execute(
                    "INSERT INTO match_proposals(transaction_id, obligation_id, proposed_amount_cents, status, rationale, review_date) VALUES (?, ?, ?, 'proposed', ?, ?)",
                    (transaction["id"], obligation["id"], transaction["amount_cents"], reason, as_of))
                created += 1
            elif pair not in pairs or (prior and prior["status"] in ("rejected", "withdrawn")):
                if choices and pair not in pairs:
                    kind, reason = "ambiguous", "Multiple transactions or obligations fit a full payment. Choose manually using additional evidence."
                elif prior and prior["status"] in ("rejected", "withdrawn"):
                    kind, reason = "reviewed_match", "A prior proposal was {}. Manual allocation requires a new explicit decision and reason.".format(prior["status"])
                else:
                    kind, reason = "unmatched", "No unique, entirely unpaid full-rent match. Partial payments, remaining balances, unidentified credits, and arrears require manual review."
                issue(connection, "transaction:{}".format(transaction["id"]), transaction["property_id"], kind, reason,
                      dict(transaction), transaction_id=transaction["id"])
        return created


def validate_allocation(connection, transaction_id, obligation_id, period, as_of):
    first, last = month_bounds(period)
    as_of = review_date(as_of)
    transaction = connection.execute("SELECT * FROM transactions WHERE id=?", (transaction_id,)).fetchone()
    obligation = connection.execute("SELECT * FROM rent_obligations WHERE id=?", (obligation_id,)).fetchone()
    if transaction is None or obligation is None:
        raise PaymentError("Transaction or rent obligation not found.")
    if not first.isoformat() <= transaction["posted_date"] <= last.isoformat():
        raise PaymentError("The transaction is outside the selected review month.")
    if transaction["posted_date"] > as_of:
        raise PaymentError("The transaction is posted after the review date and cannot be recorded yet.")
    if transaction["property_id"] != obligation["property_id"]:
        raise PaymentError("A transaction can only be allocated to rent for the same property account.")
    if obligation["period"] > period:
        raise PaymentError("Advance allocation to a later rent month is outside this prototype.")
    if connection.execute("SELECT 1 FROM payment_allocations WHERE transaction_id=?", (transaction_id,)).fetchone():
        raise PaymentError("This transaction has already been allocated. Refresh to see the recorded decision.")
    remaining = balance(connection, obligation)["remaining_cents"]
    if transaction["amount_cents"] > remaining:
        raise PaymentError("This deposit exceeds the rent balance available to allocate. Overpayments and splitting a deposit are outside scope.")
    return transaction, obligation


def approve_payment(transaction_id, obligation_id, period, as_of, notes="", acknowledge=False, proposal_id=None):
    notes = notes.strip()
    if not acknowledge:
        raise PaymentError("Confirm the transaction, rent month, and amount before recording payment.")
    if len(notes) > 4000:
        raise PaymentError("Review notes must be 4,000 characters or fewer.")
    if proposal_id is None and not notes:
        raise PaymentError("Manual allocation requires a reason identifying the supporting evidence.")
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        transaction, obligation = validate_allocation(connection, transaction_id, obligation_id, period, as_of)
        proposal = None
        if proposal_id is not None:
            proposal = connection.execute("SELECT * FROM match_proposals WHERE id=?", (proposal_id,)).fetchone()
            if proposal is None or proposal["status"] != "proposed" or proposal["transaction_id"] != transaction_id or proposal["obligation_id"] != obligation_id:
                raise PaymentError("The proposal has already been reviewed or does not match this transaction and rent.")
            if (transaction_id, obligation_id) not in candidate_analysis(connection, period, as_of)[2]:
                raise PaymentError("The full-payment proposal is no longer unique or entirely unpaid. Run matching again and review manually.")
        else:
            proposal = connection.execute("SELECT * FROM match_proposals WHERE transaction_id=? AND obligation_id=? AND status='proposed'", (transaction_id, obligation_id)).fetchone()
        timing = payment_timing(obligation, transaction["posted_date"])
        summary = "{} {} from {} to {} rent. {}. Review date {}. {}".format(
            "Approved proposal:" if proposal_id else "Manual allocation:", usd(transaction["amount_cents"]), transaction["external_id"], obligation["period"], timing, as_of, notes)
        decision_id = decision(connection, "match_proposal" if proposal else "transaction", proposal["id"] if proposal else transaction_id, "approved" if proposal else "payment_approved", summary)
        allocation_id = connection.execute(
            "INSERT INTO payment_allocations(transaction_id, obligation_id, amount_cents, review_decision_id, match_proposal_id, review_date, timing_label) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (transaction_id, obligation_id, transaction["amount_cents"], decision_id, proposal["id"] if proposal else None, as_of, timing)).lastrowid
        if proposal:
            connection.execute("UPDATE match_proposals SET status='approved' WHERE id=?", (proposal["id"],))
        resolve_issue(connection, "transaction:{}".format(transaction_id), decision_id, "Resolved by approved allocation #{}. {}".format(allocation_id, notes))
        remaining = balance(connection, obligation)["remaining_cents"]
        key = "balance:{}".format(obligation_id)
        if remaining:
            issue(connection, key, obligation["property_id"], "partial_payment", "Approved partial payment; {} remains outstanding.".format(usd(remaining)),
                  {"obligation_id": obligation_id, "period": obligation["period"], "original_amount_cents": obligation["amount_cents"], "first_allocation_id": allocation_id},
                  obligation_id=obligation_id, decision_id=decision_id)
        else:
            resolve_issue(connection, key, decision_id, "Outstanding balance resolved by approved allocation #{}. {}".format(allocation_id, notes))
        withdraw_stale(connection, obligation["period"], candidate_analysis(connection, obligation["period"], as_of)[2], as_of)
        return allocation_id


def reject_proposal(proposal_id, notes=""):
    notes = notes.strip()
    if not notes or len(notes) > 4000:
        raise PaymentError("Record a rejection reason of 1–4,000 characters.")
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        proposal = connection.execute("SELECT * FROM match_proposals WHERE id=?", (proposal_id,)).fetchone()
        if proposal is None or proposal["status"] != "proposed":
            raise PaymentError("This proposal has already been reviewed or withdrawn.")
        transaction = connection.execute("SELECT * FROM transactions WHERE id=?", (proposal["transaction_id"],)).fetchone()
        connection.execute("UPDATE match_proposals SET status='rejected' WHERE id=?", (proposal_id,))
        decision_id = decision(connection, "match_proposal", proposal_id, "rejected", notes)
        issue(connection, "transaction:{}".format(transaction["id"]), transaction["property_id"], "rejected_match",
              "Full-payment match rejected: " + notes, dict(transaction), transaction_id=transaction["id"], decision_id=decision_id)


def reconciliation_state(connection, period, as_of):
    as_of = review_date(as_of)
    first, last = month_bounds(period)
    _, _, pairs = candidate_analysis(connection, period, as_of)
    obligations = [dict(row) for row in connection.execute("SELECT o.*, p.name property_name FROM rent_obligations o JOIN properties p ON p.id=o.property_id WHERE o.period<=? ORDER BY o.period, p.id", (period,))]
    for obligation in obligations:
        obligation.update(balance(connection, obligation, as_of))
        obligation["available_cents"] = balance(connection, obligation)["remaining_cents"]
    transactions = [dict(row) for row in connection.execute(
        "SELECT t.*, p.name property_name FROM transactions t JOIN properties p ON p.id=t.property_id WHERE t.posted_date BETWEEN ? AND ? ORDER BY t.posted_date, t.id",
        (first.isoformat(), last.isoformat()))]
    for transaction in transactions:
        transaction["allocation"] = connection.execute(
            "SELECT a.*, o.period, r.notes FROM payment_allocations a JOIN rent_obligations o ON o.id=a.obligation_id JOIN review_decisions r ON r.id=a.review_decision_id WHERE a.transaction_id=?", (transaction["id"],)).fetchone()
        transaction["future"] = transaction["posted_date"] > as_of
        transaction["targets"] = [o for o in obligations if o["property_id"] == transaction["property_id"] and o["available_cents"] >= transaction["amount_cents"]]
    proposals = [dict(row) for row in connection.execute(
        "SELECT m.*, t.external_id, t.description, t.posted_date, p.name property_name, o.period FROM match_proposals m "
        "JOIN transactions t ON t.id=m.transaction_id JOIN rent_obligations o ON o.id=m.obligation_id JOIN properties p ON p.id=o.property_id WHERE o.period=? AND t.posted_date<=? ORDER BY m.id",
        (period, as_of))]
    for proposal in proposals:
        proposal["eligible"] = (proposal["transaction_id"], proposal["obligation_id"]) in pairs
        proposal["decisions"] = connection.execute("SELECT * FROM review_decisions WHERE record_type='match_proposal' AND record_id=? ORDER BY id", (proposal["id"],)).fetchall()
    exceptions = [dict(row) for row in connection.execute(
        "SELECT e.*, p.name property_name, t.external_id, t.posted_date, o.period FROM exceptions e "
        "JOIN properties p ON p.id=e.property_id LEFT JOIN transactions t ON t.id=e.transaction_id LEFT JOIN rent_obligations o ON o.id=e.obligation_id "
        "WHERE (t.posted_date<=? AND t.posted_date<=?) OR o.period<=? ORDER BY e.id",
        (last.isoformat(), as_of, period))]
    for exception in exceptions:
        exception["events"] = connection.execute("SELECT * FROM exception_events WHERE exception_id=? ORDER BY id", (exception["id"],)).fetchall()
    allocations = connection.execute(
        "SELECT a.*, t.external_id, t.posted_date, p.name property_name, o.period, r.notes FROM payment_allocations a "
        "JOIN transactions t ON t.id=a.transaction_id JOIN rent_obligations o ON o.id=a.obligation_id JOIN properties p ON p.id=o.property_id JOIN review_decisions r ON r.id=a.review_decision_id "
        "WHERE o.period=? OR (t.posted_date BETWEEN ? AND ?) ORDER BY a.id", (period, first.isoformat(), last.isoformat())).fetchall()
    return {"obligations": obligations, "transactions": transactions, "proposals": proposals, "exceptions": exceptions, "allocations": allocations}
