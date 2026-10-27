import csv
import io
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.db import ROOT, connect, initialize
from app.main import app
from app.services.extraction_import import review_fact, stage_proposal
from app.services.obligations import create_obligation
from app.services.payments import PaymentError, approve_payment, balance, payment_timing, reconciliation_state, reject_proposal, run_matching
from app.services.reconciliation import COLUMNS, import_csv

PERIOD = "2026-10"
AS_OF = "2026-10-25"


def fixture_bytes(name):
    return (ROOT / "sample-data" / name).read_bytes()


def one_row(identifier, amount, property_label="Beacon Industrial operating", posted="2026-10-20"):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS)
    writer.writerow([identifier, posted, "FICTIONAL TEST CREDIT | " + property_label, amount])
    return buffer.getvalue().encode()


@pytest.fixture
def payments(database):
    with connect() as connection:
        document_id = connection.execute("SELECT id FROM lease_documents WHERE filename='orchard-row-amendment.txt'").fetchone()[0]
    payload = {"schema_version": "1.0", "document_filename": "orchard-row-amendment.txt", "facts": [{
        "fact_type": "monthly_base_rent", "value": {"amount": "5050.00", "currency": "USD"}, "effective_from": "2025-07-01", "status": "proposed",
        "uncertainty": "Execution is unestablished.", "evidence": [{"page": 1, "section": "2. REVISED BASE RENT", "quote": "Effective July 1, 2025, monthly base rent is amended to $5,050.00."}]}]}
    stage_proposal(1, document_id, json.dumps(payload))
    with connect() as connection:
        fact_id = connection.execute("SELECT id FROM lease_facts WHERE status='proposed'").fetchone()[0]
    review_fact(1, fact_id, "approved", "Approve for fictional test", acknowledge=True, replace=True)
    obligations = {property_id: create_obligation(property_id, PERIOD)[0] for property_id in (1, 2, 3)}
    import_csv("october.csv", fixture_bytes("transactions-2026-10.csv"))
    with connect() as connection:
        transactions = {row["external_id"]: row["id"] for row in connection.execute("SELECT id, external_id FROM transactions")}
    return {"obligations": obligations, "transactions": transactions}


def tx(payments, suffix):
    with connect() as connection:
        return connection.execute("SELECT id FROM transactions WHERE external_id=?", ("SYN-2026-10-" + suffix,)).fetchone()[0]


def get_proposal(transaction_id):
    with connect() as connection:
        return dict(connection.execute("SELECT * FROM match_proposals WHERE transaction_id=?", (transaction_id,)).fetchone())


def recorded(obligation_id, as_of=None):
    with connect() as connection:
        obligation = connection.execute("SELECT * FROM rent_obligations WHERE id=?", (obligation_id,)).fetchone()
        return balance(connection, obligation, as_of)


def test_full_matches_are_proposals_only_and_runs_are_idempotent(payments):
    assert run_matching(PERIOD, AS_OF) == 2
    assert recorded(payments["obligations"][1]) == {"paid_cents": 0, "remaining_cents": 505000}
    assert run_matching(PERIOD, AS_OF) == 0
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM match_proposals").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM payment_allocations").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM exceptions WHERE status='open'").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM exception_events").fetchone()[0] == 2
    with TestClient(app) as client:
        for _ in range(2):
            assert "Pending approval" in client.get("/reconciliation?period=2026-10&as_of=2026-10-25").text
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM exception_events").fetchone()[0] == 2


def test_full_approval_and_late_annotation_survive_restart(payments):
    run_matching(PERIOD, AS_OF)
    orchard = get_proposal(tx(payments, "001"))
    with pytest.raises(PaymentError, match="Confirm"):
        approve_payment(orchard["transaction_id"], orchard["obligation_id"], PERIOD, AS_OF, proposal_id=orchard["id"])
    allocation_id = approve_payment(orchard["transaction_id"], orchard["obligation_id"], PERIOD, AS_OF, acknowledge=True, proposal_id=orchard["id"])
    assert recorded(orchard["obligation_id"])["remaining_cents"] == 0
    with pytest.raises(PaymentError, match="already been allocated"):
        approve_payment(orchard["transaction_id"], orchard["obligation_id"], PERIOD, AS_OF, acknowledge=True, proposal_id=orchard["id"])
    beacon = get_proposal(tx(payments, "002"))
    assert "after the approved grace" in beacon["rationale"]
    approve_payment(beacon["transaction_id"], beacon["obligation_id"], PERIOD, AS_OF, acknowledge=True, proposal_id=beacon["id"])
    initialize()
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM payment_allocations WHERE id=?", (allocation_id,)).fetchone()[0] == 1
        label = connection.execute("SELECT timing_label FROM payment_allocations WHERE transaction_id=?", (beacon["transaction_id"],)).fetchone()[0]
        assert label == "Posted after the approved grace period"
        assert recorded(beacon["obligation_id"])["remaining_cents"] == 0
    with TestClient(app) as client:
        page = client.get("/reconciliation?period=2026-10&as_of=2026-10-25").text
        assert "$8,250.00" in page
        assert "Paid in full" in page
        assert "Posted after the approved grace period" in page


def test_rejection_is_retained_and_manual_override_requires_new_reason(payments):
    run_matching(PERIOD, AS_OF)
    proposal = get_proposal(tx(payments, "001"))
    with pytest.raises(PaymentError, match="rejection reason"):
        reject_proposal(proposal["id"])
    reject_proposal(proposal["id"], "Need to verify payer identity against source")
    run_matching(PERIOD, AS_OF)
    run_matching(PERIOD, AS_OF)
    assert get_proposal(proposal["transaction_id"])["status"] == "rejected"
    assert recorded(proposal["obligation_id"])["paid_cents"] == 0
    with pytest.raises(PaymentError):
        approve_payment(proposal["transaction_id"], proposal["obligation_id"], PERIOD, AS_OF, acknowledge=True, proposal_id=proposal["id"])
    approve_payment(proposal["transaction_id"], proposal["obligation_id"], PERIOD, AS_OF, notes="Fictional owner verified the named payer", acknowledge=True)
    assert get_proposal(proposal["transaction_id"])["status"] == "rejected"
    with connect() as connection:
        exception = connection.execute("SELECT * FROM exceptions WHERE transaction_id=?", (proposal["transaction_id"],)).fetchone()
        assert exception["status"] == "resolved"
        assert "Need to verify payer" in exception["initial_reason"]
        assert connection.execute("SELECT count(*) FROM review_decisions WHERE record_type='match_proposal' AND record_id=? AND decision='rejected'", (proposal["id"],)).fetchone()[0] == 1


def test_partial_followup_resolves_balance_but_not_unidentified_credit(payments):
    obligation_id = payments["obligations"][3]
    run_matching(PERIOD, AS_OF)
    with pytest.raises(PaymentError, match="requires a reason"):
        approve_payment(tx(payments, "003"), obligation_id, PERIOD, AS_OF, acknowledge=True)
    approve_payment(tx(payments, "003"), obligation_id, PERIOD, AS_OF, "Named tenant's October partial payment", acknowledge=True)
    assert recorded(obligation_id) == {"paid_cents": 300000, "remaining_cents": 420000}
    run_matching(PERIOD, AS_OF)
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM match_proposals WHERE transaction_id=?", (tx(payments, "004"),)).fetchone()[0] == 0
        issue = connection.execute("SELECT * FROM exceptions WHERE issue_key=?", ("balance:{}".format(obligation_id),)).fetchone()
        assert issue["status"] == "open"
        assert "$4,200.00" in issue["initial_reason"]
        issue_id = issue["id"]
    result = import_csv("followup.csv", fixture_bytes("transactions-2026-10-follow-up.csv"))
    assert (result["added"], result["skipped"]) == (1, 1)
    with pytest.raises(PaymentError, match="after the review date"):
        approve_payment(tx(payments, "005"), obligation_id, PERIOD, AS_OF, "Named tenant's remaining rent", acknowledge=True)
    run_matching(PERIOD, "2026-10-28")
    approve_payment(tx(payments, "005"), obligation_id, PERIOD, "2026-10-28", "Named tenant's October remainder; separate credit remains unidentified", acknowledge=True)
    assert recorded(obligation_id)["remaining_cents"] == 0
    assert recorded(obligation_id, AS_OF)["remaining_cents"] == 420000
    with connect() as connection:
        resolved = connection.execute("SELECT * FROM exceptions WHERE id=?", (issue_id,)).fetchone()
        assert resolved["status"] == "resolved"
        assert "$4,200.00" in resolved["initial_reason"]
        assert [row[0] for row in connection.execute("SELECT event FROM exception_events WHERE exception_id=? ORDER BY id", (issue_id,))] == ["opened", "resolved"]
        assert connection.execute("SELECT status FROM exceptions WHERE transaction_id=?", (tx(payments, "004"),)).fetchone()[0] == "open"
        assert connection.execute("SELECT count(*) FROM payment_allocations WHERE transaction_id=?", (tx(payments, "004"),)).fetchone()[0] == 0
    with pytest.raises(PaymentError, match="exceeds the rent balance"):
        approve_payment(tx(payments, "004"), obligation_id, PERIOD, "2026-10-28", "Test overpayment guard", acknowledge=True)


def test_new_ambiguous_credit_blocks_stale_approval_and_withdraws_proposal(payments):
    run_matching(PERIOD, AS_OF)
    proposal = get_proposal(tx(payments, "002"))
    import_csv("ambiguous.csv", fixture_bytes("transactions-ambiguous-full.csv"))
    with pytest.raises(PaymentError, match="no longer unique"):
        approve_payment(proposal["transaction_id"], proposal["obligation_id"], PERIOD, AS_OF, acknowledge=True, proposal_id=proposal["id"])
    run_matching(PERIOD, AS_OF)
    assert get_proposal(proposal["transaction_id"])["status"] == "withdrawn"
    assert recorded(proposal["obligation_id"])["paid_cents"] == 0
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM exceptions WHERE kind='ambiguous' AND status='open'").fetchone()[0] == 2
    approve_payment(proposal["transaction_id"], proposal["obligation_id"], PERIOD, AS_OF, "Verified named tenant; second credit remains unidentified", acknowledge=True)
    with connect() as connection:
        assert connection.execute("SELECT status FROM exceptions WHERE transaction_id=?", (tx(payments, "006"),)).fetchone()[0] == "open"


def test_partial_allocation_invalidates_an_old_full_proposal(payments):
    run_matching(PERIOD, AS_OF)
    proposal = get_proposal(tx(payments, "002"))
    import_csv("smaller.csv", one_row("SYN-HALF", "1600.00"))
    with connect() as connection:
        partial_id = connection.execute("SELECT id FROM transactions WHERE external_id='SYN-HALF'").fetchone()[0]
    approve_payment(partial_id, proposal["obligation_id"], PERIOD, AS_OF, "Fictional partial credit verified", acknowledge=True)
    assert get_proposal(proposal["transaction_id"])["status"] == "withdrawn"
    with pytest.raises(PaymentError, match="exceeds the rent balance"):
        approve_payment(proposal["transaction_id"], proposal["obligation_id"], PERIOD, AS_OF, acknowledge=True, proposal_id=proposal["id"])


def test_review_date_excludes_future_payments_and_preserves_their_proposals(payments):
    assert run_matching(PERIOD, "2026-10-01") == 1
    run_matching(PERIOD, AS_OF)
    beacon = get_proposal(tx(payments, "002"))
    run_matching(PERIOD, "2026-10-01")
    assert get_proposal(beacon["transaction_id"])["status"] == "proposed"
    with pytest.raises(PaymentError, match="after the review date"):
        approve_payment(beacon["transaction_id"], beacon["obligation_id"], PERIOD, "2026-10-01", acknowledge=True, proposal_id=beacon["id"])
    approve_payment(beacon["transaction_id"], beacon["obligation_id"], PERIOD, AS_OF, acknowledge=True, proposal_id=beacon["id"])
    assert recorded(beacon["obligation_id"], "2026-10-01")["paid_cents"] == 0
    with connect() as connection:
        state = reconciliation_state(connection, PERIOD, "2026-10-01")
        current = next(o for o in state["obligations"] if o["id"] == beacon["obligation_id"])
        assert current["available_cents"] == 0
        assert current["remaining_cents"] == 320000


def test_manual_arrears_allocation_and_cross_property_guards(payments):
    september_id = create_obligation(3, "2026-09")[0]
    with pytest.raises(PaymentError, match="same property"):
        approve_payment(tx(payments, "003"), payments["obligations"][2], PERIOD, AS_OF, "Invalid property test", acknowledge=True)
    approve_payment(tx(payments, "003"), september_id, PERIOD, AS_OF, "Fictional reviewer assigns this payment to September arrears", acknowledge=True)
    assert recorded(september_id)["paid_cents"] == 300000
    assert recorded(payments["obligations"][3])["paid_cents"] == 0
    november_id = create_obligation(3, "2026-11")[0]
    with pytest.raises(PaymentError, match="later rent month"):
        approve_payment(tx(payments, "004"), november_id, PERIOD, AS_OF, "Advance rent unsupported", acknowledge=True)
    with connect() as connection:
        state = reconciliation_state(connection, PERIOD, AS_OF)
        assert any(e["obligation_id"] == september_id for e in state["exceptions"])


def test_concurrent_approvals_cannot_spend_a_deposit_twice(payments):
    transaction_id, obligation_id = tx(payments, "003"), payments["obligations"][3]
    def attempt():
        try:
            approve_payment(transaction_id, obligation_id, PERIOD, AS_OF, "Concurrency check with synthetic credit", acknowledge=True)
            return "approved"
        except PaymentError:
            return "blocked"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(outcomes) == ["approved", "blocked"]
    assert recorded(obligation_id)["paid_cents"] == 300000
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM payment_allocations").fetchone()[0] == 1


@pytest.mark.parametrize("posted,grace,expected", [
    ("2026-10-05", 5, "on or before"), ("2026-10-04", None, "on or before"),
    ("2026-10-10", 5, "within the approved grace"), ("2026-10-11", 5, "after the approved grace"),
    ("2026-10-06", None, "grace period not specified"), ("2026-10-06", 0, "after the approved grace"),
])
def test_payment_timing_boundaries(posted, grace, expected):
    assert expected in payment_timing({"due_date": "2026-10-05", "grace_days": grace}, posted)


@pytest.mark.parametrize("bad_date", ["2026-02-30", "20261025", "not-a-date", ""])
def test_invalid_dates_cannot_record_any_payment(payments, bad_date):
    with pytest.raises(PaymentError, match="review date"):
        run_matching(PERIOD, bad_date)
    with pytest.raises(PaymentError):
        approve_payment(tx(payments, "003"), payments["obligations"][3], PERIOD, bad_date, "Date validation test", acknowledge=True)
    assert recorded(payments["obligations"][3])["paid_cents"] == 0


def test_http_approvals_errors_and_populated_reset(payments):
    with TestClient(app) as client:
        base = {"period": PERIOD, "as_of": AS_OF}
        result = client.post("/reconciliation/matching", data=base)
        assert result.status_code == 200 and "Pending approval" in result.text
        assert "Posted after the approved grace period" in result.text
        proposal = get_proposal(tx(payments, "001"))
        url = "/reconciliation/proposals/{}".format(proposal["id"])
        blocked = client.post(url, data={**base, "action": "approve", "notes": "Retain my notes after the error"})
        assert blocked.status_code == 409
        assert "Retain my notes after the error" in blocked.text
        accepted = client.post(url, data={**base, "action": "approve", "acknowledge": "true"})
        assert "Payment approved and recorded" in accepted.text
        manual = client.post("/reconciliation/allocations", data={**base, "transaction_id": tx(payments, "003"), "obligation_id": payments["obligations"][3], "notes": "Named tenant's partial rent", "acknowledge": "true"})
        assert manual.status_code == 200
        assert "$4,200.00 remains outstanding" in manual.text
        assert client.post(url, data={**base, "action": "approve", "acknowledge": "true"}).status_code == 409
        assert client.post(url, data={**base, "period": "2026-09", "action": "approve", "acknowledge": "true"}).status_code == 409
    result = subprocess.run([sys.executable, "-m", "app.db", "reset", "--confirm"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    with connect() as connection:
        for table in ("payment_allocations", "match_proposals", "exceptions", "exception_events"):
            assert connection.execute("SELECT count(*) FROM " + table).fetchone()[0] == 0
