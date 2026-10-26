"""Read-only monthly brief, Markdown artifact, and unsent neutral reminders."""

import json
from datetime import datetime, timezone

from app.services.attention import attention_items, rent_status
from app.services.obligations import month_bounds
from app.services.payments import reconciliation_state, review_date, usd


def reminder(property_record, obligation, as_of, pending):
    if obligation["remaining_cents"] <= 0 or obligation["due_date"] > as_of:
        return None
    lines = ["Subject: Rent payment status — {} — {}".format(property_record["name"], obligation["period"]),
             "", "Hello {},".format(property_record["tenant_name"]), "",
             "We are reviewing {} base rent for {}. The approved amount is {}, due {}.".format(obligation["period"], property_record["name"], usd(obligation["amount_cents"]), obligation["due_date"]),
             "As of {}, our reviewed records show {} in approved payments and a remaining balance of {} awaiting reconciliation.".format(as_of, usd(obligation["paid_cents"]), usd(obligation["remaining_cents"]))]
    if pending:
        lines.append("We also have imported credits awaiting review, so this is a request to confirm payment details rather than a conclusion that payment has not arrived.")
    lines += ["If you have already paid, please share the payment date and reference so we can check our records.", "", "Thank you,", "[Owner name]", "", "UNSENT DRAFT — review the records and edit before use. No message has been sent."]
    return "\n".join(lines)


def build_report(connection, period, as_of):
    first, last = month_bounds(period)
    as_of = review_date(as_of)
    if not connection.in_transaction:
        connection.execute("BEGIN")  # Keep all sections consistent if another request approves a payment.
    state = reconciliation_state(connection, period, as_of)
    properties = {row["id"]: dict(row) for row in connection.execute("SELECT * FROM properties ORDER BY id")}
    obligations = [row for row in state["obligations"] if row["period"] == period]
    pending = [row for row in state["transactions"] if not row["allocation"] and not row["future"]]
    futures = [row for row in state["transactions"] if row["future"]]
    drafts = []
    for obligation in obligations:
        obligation["status"] = rent_status(obligation, as_of, obligation["remaining_cents"])
        obligation["terms"] = json.loads(obligation["terms_snapshot_json"])
        obligation["assumptions"] = json.loads(obligation["assumptions_json"])
        draft = reminder(properties[obligation["property_id"]], obligation, as_of,
                         any(tx["property_id"] == obligation["property_id"] for tx in pending))
        if draft:
            drafts.append({"property_name": obligation["property_name"], "text": draft, "obligation_id": obligation["id"]})
    missing = [p for p in properties.values() if not any(o["property_id"] == p["id"] for o in obligations)]
    assumptions = ["USD monthly base rent only; NNN and other charges are excluded.",
                   "Bank posted date stands in for payment receipt in this fictional prototype.",
                   "Approved records reflect current review decisions. The review date filters posted payments, not historical reviewer knowledge.",
                   "Unknown grace remains unspecified. No late fee or legal consequence is calculated."]
    for obligation in obligations:
        assumptions.extend("At obligation creation — {}: {}".format(obligation["property_name"], item) for item in obligation["assumptions"])
    uncertainties = [dict(row) for row in connection.execute(
        "SELECT f.*, d.filename, p.name property_name FROM lease_facts f JOIN lease_documents d ON d.id=f.document_id JOIN properties p ON p.id=f.property_id "
        "WHERE f.status='proposed' AND (f.effective_from='' OR f.effective_from<=?) AND (f.effective_to IS NULL OR f.effective_to>=?) ORDER BY f.id", (last.isoformat(), first.isoformat()))]
    attention = attention_items(connection, as_of)
    for lease in attention["leases"]:
        lease["event_records"] = [{**dict(event), "source": json.loads(event["evidence_json"])}
                                  for event in lease["events"] if event["exercised_on"] <= as_of]
    recommendations = []
    if missing:
        recommendations.append("Create this month's obligations after reviewing approved terms for: " + ", ".join(p["name"] for p in missing) + ".")
    if pending:
        recommendations.append("Review {} unallocated transaction(s), run matching, and approve only evidence-supported allocations. Amount alone does not identify a payer.".format(len(pending)))
    if any(e["status"] == "open" for e in state["exceptions"]):
        recommendations.append("Investigate open exceptions; retain unidentified credits separately from rent balances.")
    if uncertainties:
        recommendations.append("Review pending lease facts and their uncertainty before treating them as effective terms.")
    if drafts:
        recommendations.append("Review pending credits before using the neutral reminder drafts; the app sends nothing.")
    if any(item["kind"] in ("notice_window", "options_exhausted", "expiration") for item in attention["items"]):
        recommendations.append("Review lease attention items and record any option exercise from cited evidence. Do not assume exercise from elapsed time.")
    if not recommendations:
        recommendations.append("Retain the reviewed evidence and decisions and review the next period.")
    return {"period": period, "as_of": as_of, "generated_at": datetime.now(timezone.utc).isoformat(),
            "obligations": obligations, "missing": missing, "expected_cents": sum(o["amount_cents"] for o in obligations),
            "paid_cents": sum(o["paid_cents"] for o in obligations), "remaining_cents": sum(o["remaining_cents"] for o in obligations),
            "pending": pending, "futures": futures, "state": state, "assumptions": assumptions,
            "uncertainties": uncertainties, "attention": attention, "recommendations": recommendations, "drafts": drafts}


def report_markdown(report):
    lines = ["# Monthly rent reconciliation brief", "", "Month: {} | Review date: {}".format(report["period"], report["as_of"]),
             "Generated: {}".format(report["generated_at"]), "Fictional records only. No message has been sent.", "",
             "## Approved records", "", "Expected: {} | Approved payments: {} | Remaining: {}".format(usd(report["expected_cents"]), usd(report["paid_cents"]), usd(report["remaining_cents"]))]
    for obligation in report["obligations"]:
        lines += ["", "### {}".format(obligation["property_name"]),
                  "{} rent; due {}; {} paid; {} remaining. {}.".format(usd(obligation["amount_cents"]), obligation["due_date"], usd(obligation["paid_cents"]), usd(obligation["remaining_cents"]), obligation["status"]), "", "Evidence retained at obligation creation:"]
        for term in obligation["terms"]:
            lines.append("- {} — {} (effective {} through {}).".format(term["fact_type"], term["document_filename"], term["effective_from"], term["effective_to"] or "open end"))
            for evidence in term["evidence"]:
                lines += ["  Page {} · {}:".format(evidence["page"], evidence["section"]), "> " + evidence["quote"].replace("\n", "\n> ")]
            if term["uncertainty"]:
                lines.append("  Reviewed uncertainty: " + term["uncertainty"])
    for property_record in report["missing"]:
        lines.append("- {}: monthly obligation not created; expected amount not established in this report.".format(property_record["name"]))
    lines += ["", "## Approved payment evidence and history", ""]
    for allocation in report["state"]["allocations"]:
        lines.append("- {}: {} from {} posted {}, applied to {} rent. {}. Review decision: {}{}".format(
            allocation["property_name"], usd(allocation["amount_cents"]), allocation["external_id"], allocation["posted_date"], allocation["period"], allocation["timing_label"], allocation["notes"],
            " [Posted after review date; excluded from totals.]" if allocation["posted_date"] > report["as_of"] else ""))
    if not report["state"]["allocations"]:
        lines.append("No approved payment allocations.")
    lines += ["", "## Imported evidence still awaiting approval", ""]
    for transaction in report["pending"]:
        lines.append("- {} — {} — {} — {} — {}".format(transaction["property_name"], transaction["external_id"], transaction["posted_date"], usd(transaction["amount_cents"]), transaction["description"]))
    if not report["pending"]:
        lines.append("No unallocated credits posted through the review date in this month.")
    if report["futures"]:
        lines.append("Transactions posted after review date (excluded from payment totals): " + ", ".join(tx["external_id"] for tx in report["futures"]))
    lines += ["", "## Assumptions", ""] + ["- " + item for item in report["assumptions"]]
    lines += ["", "## Uncertainty and pending lease facts", ""]
    for fact in report["uncertainties"]:
        lines.append("- {} — {} — {}: {}".format(fact["property_name"], fact["fact_type"], fact["filename"], fact["uncertainty"] or "Proposed, not approved."))
    if not report["uncertainties"]:
        lines.append("No pending lease facts for this period. Missing source terms and obligation-creation assumptions are listed separately.")
    lines += ["", "## Exceptions and history", ""]
    for exception in report["state"]["exceptions"]:
        lines.append("- {} — {} — {}: {}".format(exception["property_name"], exception["kind"], exception["status"], exception["current_reason"]))
        for event in exception["events"]:
            lines.append("  - {} · {}: {}".format(event["created_at"], event["event"], event["notes"]))
    if not report["state"]["exceptions"]:
        lines.append("No saved exceptions. Unallocated credits above still require review even if matching has not been run.")
    lines += ["", "## Date-driven attention", "", "Upcoming rent: 30 days. Expiration planning: 12 months. Upcoming notice windows: one calendar month. These planning horizons do not modify contractual dates."]
    for item in report["attention"]["items"]:
        lines.append("- {} — {}: {}".format(item["property_name"], item["title"], item["detail"]))
    for lease in report["attention"]["leases"]:
        if lease["evidence"]:
            lines += ["", "Lease date evidence — " + lease["property"]["name"]]
        for term in lease["evidence"]:
            for evidence in term["evidence"]:
                lines += ["- {} — {} — page {} — {}".format(term["fact_type"], term["document_filename"], evidence["page"], evidence["section"]),
                          "> " + evidence["quote"].replace("\n", "\n> ")]
        for event in lease["event_records"]:
            source = event["source"]
            lines += ["- Reviewed exercise {} on {}: {} to {}. Decision #{}. Source: {} — page {} — {}.".format(
                event["option_number"], event["exercised_on"], event["prior_expiration"], event["new_expiration"], event["review_decision_id"], source["document_filename"], source["page"], source["section"]),
                      "> " + source["quote"].replace("\n", "\n> ")]
    lines += ["", "## Recommended next steps", ""] + ["- " + item for item in report["recommendations"]]
    lines += ["", "## Unsent reminder drafts", ""]
    for draft in report["drafts"]:
        lines += ["### " + draft["property_name"], "", draft["text"], ""]
    if not report["drafts"]:
        lines.append("No reminder prepared: no created obligation has an outstanding amount due on or before this review date.")
    return "\n".join(lines) + "\n"
