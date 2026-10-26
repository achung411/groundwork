import json
import subprocess
import sys
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.db import ROOT, connect, initialize
from app.main import app
from app.services.attention import add_months, attention_items, lease_state, record_exercise, rent_status
from app.services.attention_demo import stage_attention_demo
from app.services.extraction_import import ReviewError, review_fact
from app.services.obligations import ObligationError, create_obligation
from app.services.payments import PaymentError, approve_payment, run_matching
from app.services.reconciliation import import_csv
from app.services.reporting import build_report, report_markdown


def approved_attention():
    stage_attention_demo()
    with connect() as connection:
        facts = connection.execute("SELECT id FROM lease_facts WHERE property_id=2 AND status='proposed'").fetchall()
    for fact in facts:
        review_fact(2, fact["id"], "approved", acknowledge=True)
    with connect() as connection:
        state = lease_state(connection, 2, "2026-10-25")
        document = connection.execute("SELECT * FROM lease_documents WHERE filename='beacon-extension-confirmation.txt'").fetchone()
    quote = "For this fictional scenario, the parties confirm that written notice exercising the lease's sole three-year extension option was delivered and accepted on September 15, 2026. The prior expiration is August 31, 2027. The extension begins September 1, 2027 and ends August 31, 2030. No contractual extension options remain unexercised."
    return {"property_id": 2, "option_fact_id": state["option_fact"]["id"], "lease_end_fact_id": state["end_fact"]["id"],
            "document_id": document["id"], "exercised_on": "2026-09-15", "new_expiration": "2030-08-31",
            "page": 1, "section": "2. EXERCISE CONFIRMATION", "quote": quote,
            "notes": "Reviewed the fictional accepted notice and extended dates; extension rent is not established.",
            "as_of": "2026-10-25", "acknowledge": True}


def counts():
    with connect() as connection:
        return {table: connection.execute("SELECT count(*) FROM " + table).fetchone()[0]
                for table in ("lease_facts", "review_decisions", "rent_obligations", "transactions", "payment_allocations", "lease_option_events")}


@pytest.mark.parametrize("as_of,grace,remaining,expected", [
    ("2026-10-04", 5, 320000, "Upcoming"), ("2026-10-05", 5, 320000, "Due today"),
    ("2026-10-10", 5, 320000, "Within approved grace period"),
    ("2026-10-11", 5, 320000, "Overdue after approved grace period"),
    ("2026-10-06", None, 320000, "Past due date; grace period not specified"),
    ("2026-10-06", 0, 320000, "Overdue after approved grace period"),
    ("2026-10-20", 5, 0, "Paid in full"),
])
def test_rent_attention_status_boundaries(as_of, grace, remaining, expected):
    assert rent_status({"due_date": "2026-10-05", "grace_days": grace}, as_of, remaining) == expected


def test_calendar_notice_and_leap_boundaries():
    assert add_months(date(2027, 8, 31), -12) == date(2026, 8, 31)
    assert add_months(date(2027, 8, 31), -9) == date(2026, 11, 30)
    assert add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)


@pytest.mark.parametrize("as_of,title", [("2026-08-30", "Extension notice window approaching"),
                                        ("2026-08-31", "Extension notice window open"),
                                        ("2026-11-30", "Extension notice window open"),
                                        ("2026-12-01", "Notice window ended; exercise not recorded")])
def test_beacon_notice_window_inclusive_without_assumed_exercise(database, as_of, title):
    approved_attention()
    with connect() as connection:
        result = attention_items(connection, as_of)
        beacon = next(lease for lease in result["leases"] if lease["property"]["id"] == 2)
        assert beacon["window_start"].isoformat() == "2026-08-31"
        assert beacon["window_end"].isoformat() == "2026-11-30"
        assert beacon["remaining_options"] == 1
        assert any(item["property_id"] == 2 and item["title"] == title for item in result["items"])
        assert connection.execute("SELECT count(*) FROM lease_option_events").fetchone()[0] == 0


def test_demo_staging_is_pending_idempotent_and_preserves_user_terms(database):
    before = counts()
    assert stage_attention_demo() == 3
    assert stage_attention_demo() == 0
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM lease_facts WHERE status='approved'").fetchone()[0] == before["lease_facts"]
        assert connection.execute("SELECT count(*) FROM lease_facts WHERE status='proposed'").fetchone()[0] == 3
        assert connection.execute("SELECT count(*) FROM lease_documents WHERE filename='beacon-extension-confirmation.txt'").fetchone()[0] == 1
        assert lease_state(connection, 2, "2026-10-25")["expiration"] is None


def test_reviewed_exercise_exhausts_options_retains_history_and_does_not_set_rent(database):
    args = approved_attention()
    original_facts = counts()["lease_facts"]
    event_id = record_exercise(**args)
    initialize()
    with connect() as connection:
        before = lease_state(connection, 2, "2026-09-14")
        after = lease_state(connection, 2, "2026-10-25")
        assert before["expiration"] == date(2027, 8, 31) and before["remaining_options"] == 1
        assert after["expiration"] == date(2030, 8, 31) and after["remaining_options"] == 0
        assert after["window_start"] is None
        event = connection.execute("SELECT * FROM lease_option_events WHERE id=?", (event_id,)).fetchone()
        assert json.loads(event["evidence_json"])["document_filename"] == "beacon-extension-confirmation.txt"
        assert len(json.loads(event["terms_snapshot_json"])) == 2
        assert connection.execute("SELECT decision FROM review_decisions WHERE id=?", (event["review_decision_id"],)).fetchone()[0] == "option_exercised"
        items = attention_items(connection, "2026-10-25")["items"]
        assert any(item["property_id"] == 2 and item["kind"] == "options_exhausted" for item in items)
        exported = report_markdown(build_report(connection, "2026-10", "2026-10-25"))
        assert "beacon-extension-confirmation.txt" in exported
        assert args["quote"] in exported
        assert "notice must be delivered no earlier than twelve months" in exported
    assert counts()["lease_facts"] == original_facts
    # A reviewed exercise resolves the source's review gate but never carries base rent into the extension.
    create_obligation(2, "2026-10")
    with pytest.raises(ObligationError):
        create_obligation(2, "2027-09")
    with pytest.raises(ReviewError, match="already been recorded"):
        record_exercise(**args)
    with connect() as connection:
        connection.execute("UPDATE lease_facts SET effective_to='2027-08-31' WHERE id=?", (args["option_fact_id"],))
        later = lease_state(connection, 2, "2028-10-25")
        assert later["expiration"] == date(2030, 8, 31)
        assert later["remaining_options"] == 0


@pytest.mark.parametrize("changes,match", [
    ({"acknowledge": False}, "Acknowledge"), ({"notes": ""}, "review notes"),
    ({"exercised_on": "2026-08-30"}, "outside the approved notice window"),
    ({"exercised_on": "2026-11-30", "as_of": "2026-10-25"}, "after the review date"),
    ({"new_expiration": "2030-08-30"}, "expected 2030-08-31"),
    ({"quote": "Unsupported source"}, "Quotation"), ({"quote": ""}, "nonempty quotation"),
    ({"page": 9}, "page 9"), ({"property_id": 1}, "Review and approve"),
])
def test_exercise_requires_approval_dates_and_property_evidence(database, changes, match):
    args = approved_attention()
    before = counts()
    with pytest.raises(ReviewError, match=match):
        record_exercise(**{**args, **changes})
    assert counts() == before


def test_attention_missing_terms_and_reads_do_not_mutate_records(database):
    create_obligation(3, "2026-10")
    before = counts()
    with connect() as connection:
        items = attention_items(connection, "2026-10-25")["items"]
        assert any(item["kind"] == "rent" and "grace period not specified" in item["title"] for item in items)
        assert not any(item["kind"] == "options_exhausted" for item in items)
        assert any(item["kind"] == "missing_terms" for item in items)
        assert attention_items(connection, "9999-12-31")
    with TestClient(app) as client:
        assert client.get("/attention?as_of=2026-10-25").status_code == 200
        assert client.get("/?as_of=2026-10-25").status_code == 200
        assert client.get("/attention?as_of=bad").status_code == 422
    assert counts() == before


def test_report_separates_approved_payments_pending_evidence_and_draft(database):
    obligation_id = create_obligation(3, "2026-10")[0]
    import_csv("october.csv", (ROOT / "sample-data/transactions-2026-10.csv").read_bytes())
    run_matching("2026-10", "2026-10-25")
    with connect() as connection:
        transaction_id = connection.execute("SELECT id FROM transactions WHERE external_id='SYN-2026-10-003'").fetchone()[0]
    approve_payment(transaction_id, obligation_id, "2026-10", "2026-10-25", "Named tenant's partial rent", acknowledge=True)
    before = counts()
    with connect() as connection:
        report = build_report(connection, "2026-10", "2026-10-25")
        assert (report["expected_cents"], report["paid_cents"], report["remaining_cents"]) == (720000, 300000, 420000)
        assert len(report["missing"]) == 2
        assert len(report["drafts"]) == 1
        draft = report["drafts"][0]["text"]
        assert "$3,000.00" in draft and "$4,200.00" in draft
        assert "imported credits awaiting review" in draft
        assert "UNSENT DRAFT" in draft
        assert any(item["external_id"] == "SYN-2026-10-004" for item in report["pending"])
        markdown = report_markdown(report)
        for heading in ("## Approved records", "## Assumptions", "## Uncertainty", "## Exceptions", "## Recommended next steps", "## Unsent reminder drafts"):
            assert heading in markdown
        assert "juniper-market-lease.txt" in markdown
        assert "No late fee or legal consequence is calculated" in markdown
    with TestClient(app) as client:
        page = client.get("/report?period=2026-10&as_of=2026-10-25")
        assert page.status_code == 200 and "Copy unsent draft for Juniper Market" in page.text
        exported = client.get("/report.md?period=2026-10&as_of=2026-10-25")
        assert exported.status_code == 200 and "text/markdown" in exported.headers["content-type"]
        assert "attachment" in exported.headers["content-disposition"]
        assert "$4,200.00" in exported.text
        assert client.get("/report?period=2026-13").status_code == 422
        assert client.get("/report.md?as_of=bad").status_code == 422
    assert counts() == before


def test_future_credit_and_upcoming_rent_do_not_produce_received_money_or_reminder(database):
    create_obligation(3, "2026-10")
    import_csv("followup.csv", (ROOT / "sample-data/transactions-2026-10-follow-up.csv").read_bytes())
    with connect() as connection:
        report = build_report(connection, "2026-10", "2026-09-30")
        assert report["paid_cents"] == 0
        assert len(report["futures"]) == 2
        assert not report["pending"] and not report["drafts"]
        assert report["obligations"][0]["status"] == "Upcoming"


def test_paid_rent_has_no_reminder_and_retains_late_annotation(database):
    obligation_id = create_obligation(2, "2026-10")[0]
    import_csv("october.csv", (ROOT / "sample-data/transactions-2026-10.csv").read_bytes())
    run_matching("2026-10", "2026-10-25")
    with connect() as connection:
        proposal = connection.execute("SELECT * FROM match_proposals WHERE obligation_id=?", (obligation_id,)).fetchone()
    approve_payment(proposal["transaction_id"], obligation_id, "2026-10", "2026-10-25", acknowledge=True, proposal_id=proposal["id"])
    with connect() as connection:
        report = build_report(connection, "2026-10", "2026-10-25")
        assert not report["drafts"]
        assert report["obligations"][0]["status"] == "Paid in full"
        assert "Posted after the approved grace period" in report_markdown(report)


def test_http_exercise_and_reset_with_reviewed_events(database):
    args = approved_attention()
    with TestClient(app) as client:
        page = client.get("/attention?as_of=2026-10-25")
        assert "Extension notice window open" in page.text
        endpoint = "/attention/properties/2/exercise"
        form = {key: value for key, value in args.items() if key != "property_id"}
        failed = client.post(endpoint, data={**form, "quote": "bad", "notes": "Retain these notes"})
        assert failed.status_code == 409 and "Retain these notes" in failed.text
        result = client.post(endpoint, data=form)
        assert result.status_code == 200
        assert "All approved extension options exercised" in result.text
        assert "2030-08-31" in result.text
        assert client.post(endpoint, data=form).status_code == 409
    reset = subprocess.run([sys.executable, "-m", "app.db", "reset", "--confirm"], cwd=ROOT, capture_output=True, text=True)
    assert reset.returncode == 0, reset.stderr
    assert counts()["lease_option_events"] == 0
