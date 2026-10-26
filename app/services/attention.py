"""Date-driven review from approved terms; no scheduler or external delivery."""

import calendar
import json
from datetime import date

from pydantic import ValidationError

from app.db import connect
from app.models import Evidence
from app.services.extraction_import import ReviewError, verify_evidence
from app.services.obligations import snapshot_fact
from app.services.payments import PaymentError, balance, decision, review_date, usd

UPCOMING_RENT_DAYS = 30
EXPIRATION_MONTHS = 12


def add_months(day, months):
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    month += 1
    if not 1 <= year <= 9999:
        raise ReviewError("Approved date and month rule fall outside the supported calendar.")
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def planning_horizon(day, months):
    try:
        return add_months(day, months)
    except ReviewError:
        return date.max


def rent_status(obligation, as_of, remaining_cents):
    day = date.fromisoformat(review_date(as_of))
    due = date.fromisoformat(obligation["due_date"])
    if remaining_cents == 0:
        return "Paid in full"
    if day < due:
        return "Upcoming"
    if day == due:
        return "Due today"
    if obligation["grace_days"] is None:
        return "Past due date; grace period not specified"
    if (day - due).days <= obligation["grace_days"]:
        return "Within approved grace period"
    return "Overdue after approved grace period"


def approved_fact(connection, property_id, fact_type, as_of):
    facts = connection.execute(
        "SELECT * FROM lease_facts WHERE property_id=? AND fact_type=? AND status='approved' "
        "AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?) ORDER BY effective_from DESC, id DESC",
        (property_id, fact_type, as_of, as_of)).fetchall()
    if len(facts) > 1:
        raise ReviewError("Conflicting approved {} terms require review.".format(fact_type.replace("_", " ")))
    if facts:
        return facts[0]
    # Keep a known expiration visible after the validity range expires; do not make it unknown again.
    if fact_type == "lease_end":
        return connection.execute(
            "SELECT * FROM lease_facts WHERE property_id=? AND fact_type='lease_end' AND status='approved' "
            "AND effective_from<=? ORDER BY effective_from DESC, id DESC LIMIT 1", (property_id, as_of)).fetchone()
    return None


def lease_state(connection, property_id, as_of):
    as_of = review_date(as_of)
    end = approved_fact(connection, property_id, "lease_end", as_of)
    option = approved_fact(connection, property_id, "extension_option", as_of)
    if option is None:
        # An exercise that was reviewed while its rule applied remains historical evidence
        # after that rule's validity ends. It must not make the extended expiration disappear.
        option = connection.execute(
            "SELECT f.* FROM lease_facts f JOIN lease_option_events e ON e.option_fact_id=f.id "
            "WHERE f.property_id=? AND f.status='approved' AND e.exercised_on<=? "
            "ORDER BY e.exercised_on DESC, e.id DESC LIMIT 1", (property_id, as_of)).fetchone()
    result = {"end_fact": end, "option_fact": option, "expiration": None, "remaining_options": None,
              "window_start": None, "window_end": None, "events": [], "evidence": [], "gaps": []}
    if end is None:
        result["gaps"].append("Lease expiration is not approved; no expiration or notice deadline is inferred.")
    else:
        result["expiration"] = date.fromisoformat(json.loads(end["value_json"])["date"])
        result["evidence"].append(snapshot_fact(connection, end))
    if option is None:
        result["gaps"].append("No approved extension-option rule is available; no option rights or exhausted-option state is inferred.")
    else:
        value = json.loads(option["value_json"])
        result["evidence"].append(snapshot_fact(connection, option))
        all_events = connection.execute("SELECT e.*, r.notes FROM lease_option_events e JOIN review_decisions r ON r.id=e.review_decision_id WHERE e.option_fact_id=? ORDER BY e.option_number", (option["id"],)).fetchall()
        result["events"] = all_events
        events = [event for event in all_events if event["exercised_on"] <= as_of]
        result["remaining_options"] = value["options_count"] - len(events)
        if events:
            if end is None or any(event["lease_end_fact_id"] != end["id"] for event in events):
                result["gaps"].append("The reviewed exercise and current expiration use different source terms. Resolve their relationship before deriving dates.")
                result["expiration"] = None
            else:
                result["expiration"] = date.fromisoformat(events[-1]["new_expiration"])
        if option["effective_to"] and option["effective_to"] < as_of and result["remaining_options"] > 0:
            result["gaps"].append("The option rule's approved validity ended. Review it before deriving another notice window or exercise.")
        elif result["expiration"] and result["remaining_options"] > 0:
            result["window_start"] = add_months(result["expiration"], -value["notice_earliest_months"])
            result["window_end"] = add_months(result["expiration"], -value["notice_latest_months"])
    return result


def attention_items(connection, as_of):
    as_of = review_date(as_of)
    day = date.fromisoformat(as_of)
    items, leases = [], []
    for obligation in connection.execute("SELECT o.*, p.name property_name FROM rent_obligations o JOIN properties p ON p.id=o.property_id ORDER BY o.due_date, o.id"):
        remaining = balance(connection, obligation, as_of)["remaining_cents"]
        if remaining and (date.fromisoformat(obligation["due_date"]) - day).days <= UPCOMING_RENT_DAYS:
            items.append({"property_id": obligation["property_id"], "property_name": obligation["property_name"],
                          "kind": "rent", "title": rent_status(obligation, as_of, remaining),
                          "detail": "{} rent: {} remains in approved payment records; due {}. Pending credits are not payments.".format(obligation["period"], usd(remaining), obligation["due_date"]),
                          "url": "/reconciliation?period={}&as_of={}".format(obligation["period"], as_of)})
    for property_record in connection.execute("SELECT * FROM properties ORDER BY id").fetchall():
        def add(kind, title, detail):
            items.append({"property_id": property_record["id"], "property_name": property_record["name"],
                          "kind": kind, "title": title, "detail": detail,
                          "url": ("/properties/{}/lease-review".format(property_record["id"]) if kind == "missing_terms"
                                  else "/attention?as_of={}#lease-{}".format(as_of, property_record["id"]))})
        try:
            state = lease_state(connection, property_record["id"], as_of)
        except (ReviewError, ValueError, OverflowError) as error:
            state = {"expiration": None, "remaining_options": None, "window_start": None, "window_end": None,
                     "events": [], "evidence": [], "end_fact": None, "option_fact": None, "gaps": [str(error)]}
        state["property"] = dict(property_record)
        leases.append(state)
        if state["gaps"]:
            add("missing_terms", "Lease term review needed", " ".join(state["gaps"]))
        expiration = state["expiration"]
        if expiration:
            if day > expiration:
                add("expiration", "Recorded lease expiration has passed", "Recorded expiration: {}. Discuss the lease status; no legal consequence is inferred.".format(expiration))
            elif expiration <= planning_horizon(day, EXPIRATION_MONTHS):
                add("expiration", "Lease expiration within 12 months", "Recorded expiration: {}. This 12-month planning horizon is an app setting, not a contractual deadline.".format(expiration))
        if state["remaining_options"] == 0:
            add("options_exhausted", "All approved extension options exercised", "Reviewed events account for every approved option. Plan to discuss a new lease before the recorded expiration {}; no further option is assumed.".format(expiration or "is confirmed"))
        elif state["window_start"]:
            start, end = state["window_start"], state["window_end"]
            if start <= day <= end:
                add("notice_window", "Extension notice window open", "Approved window: {} through {}, inclusive. Exercise is not recorded merely because the window is open.".format(start, end))
            elif day < start and start <= planning_horizon(day, 1):
                add("notice_window", "Extension notice window approaching", "Approved window begins {} and ends {}. Upcoming means within one calendar month in this view.".format(start, end))
            elif day > end:
                add("notice_window", "Notice window ended; exercise not recorded", "Approved window ended {}. Investigate the tenant's plans; no exercise, forfeiture, or penalty is assumed.".format(end))
    priorities = {"rent": 0, "notice_window": 1, "options_exhausted": 2, "expiration": 3, "missing_terms": 4}
    items.sort(key=lambda item: priorities[item["kind"]])
    return {"items": items, "leases": leases, "as_of": as_of}


def record_exercise(property_id, option_fact_id, lease_end_fact_id, document_id, exercised_on, new_expiration,
                    page, section, quote, notes, as_of, acknowledge=False):
    as_of, exercised_on, new_expiration = map(review_date, (as_of, exercised_on, new_expiration))
    notes = notes.strip()
    if not acknowledge or not notes or len(notes) > 4000:
        raise ReviewError("Acknowledge the source and dates and provide review notes of 1–4,000 characters.")
    if exercised_on > as_of:
        raise ReviewError("An exercise after the review date cannot be recorded in this review.")
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        state = lease_state(connection, property_id, exercised_on)
        option, end = state["option_fact"], state["end_fact"]
        if option is None or end is None or option["id"] != option_fact_id or end["id"] != lease_end_fact_id or state["gaps"]:
            raise ReviewError("Review and approve consistent option and expiration terms before recording an exercise.")
        value = json.loads(option["value_json"])
        events = state["events"]
        if len(events) >= value["options_count"]:
            raise ReviewError("All approved options have already been recorded as exercised.")
        if events and events[-1]["exercised_on"] > exercised_on:
            raise ReviewError("This would precede an already recorded exercise. Review the existing history.")
        if not state["window_start"] <= date.fromisoformat(exercised_on) <= state["window_end"]:
            raise ReviewError("Exercise date is outside the approved notice window. Waivers or exceptions require additional reviewed terms and are outside this workflow.")
        expected = add_months(state["expiration"], value["term_months"]).isoformat()
        if new_expiration != expected:
            raise ReviewError("The stated new expiration does not match the approved extension duration; expected {}.".format(expected))
        document = connection.execute("SELECT * FROM lease_documents WHERE id=? AND property_id=?", (document_id, property_id)).fetchone()
        if document is None:
            raise ReviewError("Select a source document for this property.")
        try:
            evidence = Evidence(page=page, section=section, quote=quote).model_dump()
        except ValidationError as error:
            raise ReviewError("Provide a positive source page, a numbered section heading, and a nonempty quotation (up to 6,000 characters).") from error
        verify_evidence(document, [evidence])
        number = len(events) + 1
        decision_id = decision(connection, "lease_fact", option_fact_id, "option_exercised",
                               "Reviewed exercise {} on {}, expiration {} to {}. {}".format(number, exercised_on, state["expiration"], new_expiration, notes))
        return connection.execute(
            "INSERT INTO lease_option_events(property_id, option_fact_id, lease_end_fact_id, document_id, option_number, exercised_on, prior_expiration, new_expiration, evidence_json, terms_snapshot_json, review_decision_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (property_id, option_fact_id, lease_end_fact_id, document_id, number, exercised_on, state["expiration"].isoformat(),
             new_expiration, json.dumps({"document_filename": document["filename"], **evidence}), json.dumps(state["evidence"]), decision_id)).lastrowid
