"""Explicit monthly obligation creation from approved, effective terms."""

import calendar
import json
import re
from datetime import date

from app.db import connect


class ObligationError(ValueError):
    pass


def month_bounds(period):
    if not isinstance(period, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}", period):
        raise ObligationError("Choose a rent month in YYYY-MM format.")
    try:
        year, month = map(int, period.split("-"))
        first = date(year, month, 1)
        return first, date(year, month, calendar.monthrange(year, month)[1])
    except ValueError as error:
        raise ObligationError("Choose a valid calendar month.") from error


def term_for_month(connection, property_id, fact_type, first, last, required=True):
    facts = connection.execute(
        "SELECT * FROM lease_facts WHERE property_id=? AND fact_type=? AND status='approved' "
        "AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?)",
        (property_id, fact_type, last.isoformat(), first.isoformat())).fetchall()
    label = fact_type.replace("_", " ")
    if not facts:
        if required:
            raise ObligationError("No approved {} covers this month. Review the lease terms first.".format(label))
        return None
    if len(facts) != 1 or facts[0]["effective_from"] > first.isoformat() or (facts[0]["effective_to"] and facts[0]["effective_to"] < last.isoformat()):
        raise ObligationError("The {} changes within this month or has conflicting coverage. Proration and mid-month changes require review and are outside this prototype.".format(label))
    return facts[0]


def snapshot_fact(connection, fact):
    document = connection.execute("SELECT filename FROM lease_documents WHERE id=?", (fact["document_id"],)).fetchone()
    return {"fact_id": fact["id"], "fact_type": fact["fact_type"], "value": json.loads(fact["value_json"]),
            "effective_from": fact["effective_from"], "effective_to": fact["effective_to"],
            "document_filename": document["filename"], "uncertainty": fact["uncertainty"],
            "evidence": [dict(row) for row in connection.execute(
                "SELECT page, section, quote FROM fact_evidence WHERE lease_fact_id=? ORDER BY id", (fact["id"],))]}


def preview_obligation(connection, property_id, period):
    first, last = month_bounds(period)
    if not connection.execute("SELECT 1 FROM properties WHERE id=?", (property_id,)).fetchone():
        raise ObligationError("Property not found.")
    # A source amendment must be reviewed before we rely on older terms after its document date.
    unreviewed = connection.execute(
        "SELECT d.filename FROM lease_documents d WHERE d.property_id=? AND d.document_type='amendment' "
        "AND d.document_date<=? AND NOT EXISTS (SELECT 1 FROM lease_facts f WHERE f.document_id=d.id AND f.status='approved') "
        "AND NOT EXISTS (SELECT 1 FROM lease_option_events e WHERE e.document_id=d.id)",
        (property_id, last.isoformat())).fetchone()
    if unreviewed:
        raise ObligationError("Review and approve the amendment {} before creating this month's rent. Rejecting a proposal alone does not resolve the source amendment.".format(unreviewed["filename"]))
    pending = connection.execute(
        "SELECT 1 FROM lease_facts f JOIN lease_documents d ON d.id=f.document_id WHERE f.property_id=? "
        "AND d.document_type='amendment' AND f.status='proposed' AND f.fact_type IN ('monthly_base_rent','rent_due_day','grace_period','lease_start','lease_end') "
        "AND (f.effective_from='' OR f.effective_from<=?) AND (f.effective_to IS NULL OR f.effective_to>=?)",
        (property_id, last.isoformat(), first.isoformat())).fetchone()
    if pending:
        raise ObligationError("An amendment has pending terms for this month. Review them before creating rent.")
    rent = term_for_month(connection, property_id, "monthly_base_rent", first, last)
    due = term_for_month(connection, property_id, "rent_due_day", first, last)
    grace = term_for_month(connection, property_id, "grace_period", first, last, required=False)
    start = term_for_month(connection, property_id, "lease_start", first, last, required=False)
    end = term_for_month(connection, property_id, "lease_end", first, last, required=False)
    if end is None:
        # An expired validity range must not make an already-known expiration disappear.
        known_end = connection.execute(
            "SELECT * FROM lease_facts WHERE property_id=? AND fact_type='lease_end' AND status='approved' "
            "AND effective_from<=? ORDER BY effective_from DESC, id DESC LIMIT 1", (property_id, first.isoformat())).fetchone()
        if known_end and date.fromisoformat(json.loads(known_end["value_json"])["date"]) < last:
            raise ObligationError("The approved lease expiration precedes this month. Review the lease term before creating rent.")
    assumptions = []
    if start and date.fromisoformat(json.loads(start["value_json"])["date"]) > first:
        raise ObligationError("The lease starts after this month begins. Partial-month rent is outside scope.")
    if end and date.fromisoformat(json.loads(end["value_json"])["date"]) < last:
        raise ObligationError("The lease ends before this month finishes. Review its term; partial-month rent is outside scope.")
    if not start or not end:
        assumptions.append("Lease start/end dates are not fully reviewed. This obligation uses approved rent terms only.")
    if grace is None:
        assumptions.append("Grace period not specified in approved terms; no grace period or fee is inferred.")
    rent_value = json.loads(rent["value_json"])
    due_day = json.loads(due["value_json"])["day"]
    if due_day > last.day:
        raise ObligationError("The approved due day does not exist in this month. No shorter-month rule has been approved.")
    return {"property_id": property_id, "period": period, "amount_cents": rent_value["amount_cents"],
            "due_date": date(first.year, first.month, due_day).isoformat(),
            "grace_days": json.loads(grace["value_json"])["days"] if grace else None,
            "source_fact_id": rent["id"], "due_fact_id": due["id"], "grace_fact_id": grace["id"] if grace else None,
            "terms": [snapshot_fact(connection, fact) for fact in (rent, due, grace, start, end) if fact],
            "assumptions": assumptions}


def create_obligation(property_id, period):
    month_bounds(period)
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute("SELECT id FROM rent_obligations WHERE property_id=? AND period=?", (property_id, period)).fetchone()
        if existing:
            return existing["id"], False
        proposed = preview_obligation(connection, property_id, period)
        obligation_id = connection.execute(
            "INSERT INTO rent_obligations(property_id, period, amount_cents, due_date, grace_days, source_fact_id, due_fact_id, grace_fact_id, terms_snapshot_json, assumptions_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (property_id, period, proposed["amount_cents"], proposed["due_date"], proposed["grace_days"],
             proposed["source_fact_id"], proposed["due_fact_id"], proposed["grace_fact_id"],
             json.dumps(proposed["terms"]), json.dumps(proposed["assumptions"]))).lastrowid
        connection.execute(
            "INSERT INTO review_decisions(record_type, record_id, decision, reviewer_label, notes) "
            "VALUES ('rent_obligation', ?, 'created', 'Demo owner', ?)",
            (obligation_id, "Explicitly created for {} from approved terms. Values and evidence retained at creation.".format(period)))
        return obligation_id, True
