import json
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app.db import ROOT, connect, initialize
from app.main import app
from app.services.extraction_import import review_fact, stage_proposal
from app.services.obligations import ObligationError, create_obligation, month_bounds


def approve_orchard():
    with connect() as connection:
        doc_id = connection.execute("SELECT id FROM lease_documents WHERE filename='orchard-row-amendment.txt'").fetchone()[0]
    payload = {"schema_version": "1.0", "document_filename": "orchard-row-amendment.txt", "facts": [{
        "fact_type": "monthly_base_rent", "value": {"amount": "5050.00", "currency": "USD"},
        "effective_from": "2025-07-01", "status": "proposed", "uncertainty": "Execution not established",
        "evidence": [{"page": 1, "section": "2. REVISED BASE RENT", "quote": "Effective July 1, 2025, monthly base rent is amended to $5,050.00."}]}]}
    stage_proposal(1, doc_id, json.dumps(payload))
    with connect() as connection:
        fact_id = connection.execute("SELECT id FROM lease_facts WHERE status='proposed'").fetchone()[0]
    review_fact(1, fact_id, "approved", notes="Approve for fictional demo", acknowledge=True, replace=True)


def test_approved_terms_history_and_idempotent_snapshot(database):
    with pytest.raises(ObligationError, match="amendment"):
        create_obligation(1, "2026-10")
    # A pre-amendment month uses the original value, without assuming the pending amendment is approved.
    old_id, _ = create_obligation(1, "2025-03")
    with connect() as connection:
        original = dict(connection.execute("SELECT * FROM rent_obligations WHERE id=?", (old_id,)).fetchone())
    approve_orchard()
    october_id, created = create_obligation(1, "2026-10")
    assert created
    assert create_obligation(1, "2026-10") == (october_id, False)
    june_id, _ = create_obligation(1, "2025-06")
    with connect() as connection:
        october = connection.execute("SELECT * FROM rent_obligations WHERE id=?", (october_id,)).fetchone()
        assert october["amount_cents"] == 505000
        assert october["due_date"] == "2026-10-01"
        assert october["grace_days"] is None
        assert connection.execute("SELECT amount_cents FROM rent_obligations WHERE id=?", (june_id,)).fetchone()[0] == 480000
        assert dict(connection.execute("SELECT * FROM rent_obligations WHERE id=?", (old_id,)).fetchone()) == original
        stored = json.loads(october["terms_snapshot_json"])
        assert stored[0]["document_filename"] == "orchard-row-amendment.txt"
        assert stored[0]["value"]["amount_cents"] == 505000
        assert "July 1, 2025" in stored[0]["evidence"][0]["quote"]
        assert connection.execute("SELECT count(*) FROM review_decisions WHERE record_type='rent_obligation' AND record_id=?", (october_id,)).fetchone()[0] == 1
    initialize()
    with TestClient(app) as client:
        page = client.get("/reconciliation?period=2026-10").text
        assert "$5,050.00" in page
        assert "Evidence and assumptions retained" in page


def test_missing_terms_unknown_grace_and_due_date(database):
    beacon_id, _ = create_obligation(2, "2026-10")
    juniper_id, _ = create_obligation(3, "2026-10")
    with connect() as connection:
        beacon = connection.execute("SELECT * FROM rent_obligations WHERE id=?", (beacon_id,)).fetchone()
        juniper = connection.execute("SELECT * FROM rent_obligations WHERE id=?", (juniper_id,)).fetchone()
        assert (beacon["amount_cents"], beacon["due_date"], beacon["grace_days"]) == (320000, "2026-10-05", 5)
        assert juniper["grace_days"] is None
        connection.execute("UPDATE lease_facts SET status='rejected' WHERE property_id=3 AND fact_type='rent_due_day'")
    with pytest.raises(ObligationError, match="No approved rent due day"):
        create_obligation(3, "2026-11")
    with pytest.raises(ObligationError):
        create_obligation(3, "2024-02")


@pytest.mark.parametrize("period", ["2026-13", "2026-00", "0000-01", "2026-2", "2026-10-01", "anything", ""])
def test_invalid_month_cannot_create_records(database, period):
    with pytest.raises(ObligationError):
        create_obligation(2, period)
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM rent_obligations").fetchone()[0] == 0


def test_calendar_boundaries_and_midmonth_changes_are_not_inferred(database):
    assert month_bounds("2028-02")[1].day == 29
    with connect() as connection:
        connection.execute("UPDATE lease_facts SET value_json=? WHERE property_id=2 AND fact_type='rent_due_day'", (json.dumps({"day": 31}),))
    with pytest.raises(ObligationError, match="due day does not exist"):
        create_obligation(2, "2026-02")
    with connect() as connection:
        connection.execute("UPDATE lease_facts SET effective_from='2026-10-15' WHERE property_id=2 AND fact_type='monthly_base_rent'")
    with pytest.raises(ObligationError, match="changes within this month"):
        create_obligation(2, "2026-10")


def test_snapshot_is_not_recomputed_after_later_term_change(database):
    obligation_id, _ = create_obligation(2, "2026-10")
    with connect() as connection:
        before = dict(connection.execute("SELECT * FROM rent_obligations WHERE id=?", (obligation_id,)).fetchone())
        # Simulate a subsequently reviewed term change; past obligations must remain untouched.
        connection.execute("UPDATE lease_facts SET value_json=? WHERE property_id=2 AND fact_type='monthly_base_rent'", (json.dumps({"amount_cents": 350000, "currency": "USD"}),))
    assert create_obligation(2, "2026-10") == (obligation_id, False)
    with connect() as connection:
        assert dict(connection.execute("SELECT * FROM rent_obligations WHERE id=?", (obligation_id,)).fetchone()) == before


def test_approved_expiration_blocks_rent_even_after_its_fact_validity_ends(database):
    with connect() as connection:
        doc_id = connection.execute("SELECT id FROM lease_documents WHERE property_id=2").fetchone()[0]
        connection.execute(
            "INSERT INTO lease_facts(property_id, document_id, fact_type, value_json, effective_from, effective_to, status) "
            "VALUES (2, ?, 'lease_end', ?, '2022-09-01', '2027-08-31', 'approved')",
            (doc_id, json.dumps({"date": "2027-08-31"})))
    create_obligation(2, "2027-08")
    with pytest.raises(ObligationError, match="expiration"):
        create_obligation(2, "2027-09")


def test_explicit_http_creation_and_additive_startup(database):
    with TestClient(app) as client:
        assert client.get("/reconciliation?period=2026-10").status_code == 200
        with connect() as connection:
            assert connection.execute("SELECT count(*) FROM rent_obligations").fetchone()[0] == 0
        response = client.post("/reconciliation/obligations", data={"property_id": 2, "period": "2026-10"})
        assert response.status_code == 200 and "Rent obligation created" in response.text
        repeat = client.post("/reconciliation/obligations", data={"property_id": 2, "period": "2026-10"})
        assert "already exists" in repeat.text
        assert client.post("/reconciliation/obligations", data={"property_id": 999, "period": "2026-10"}).status_code == 422
        assert client.post("/reconciliation/obligations", data={"property_id": 2, "period": "bad"}).status_code == 422
    result = subprocess.run([sys.executable, "-m", "app.db", "init"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM rent_obligations").fetchone()[0] == 1
