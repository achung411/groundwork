"""One clean HTTP rehearsal across the complete interview workflow.

The proposal below is hand-authored test input, not an observed ChatGPT response.
All state and exported artifacts live in pytest's temporary directory.
"""

import json

from fastapi.testclient import TestClient

from app.db import ROOT, connect
from app.main import app


def test_interview_workflow_survives_restart(database, tmp_path):
    period = "2026-10"
    initial = {"period": period, "as_of": "2026-10-25"}
    later = {"period": period, "as_of": "2026-10-28"}

    def get_one(sql, args=()):
        with connect() as connection:
            return dict(connection.execute(sql, args).fetchone())

    def upload(client, name, review=initial):
        return client.post("/reconciliation/import", data=review,
                           files={"transaction_file": (name, (ROOT / "sample-data" / name).read_bytes(), "text/csv")})

    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        source = get_one("SELECT * FROM lease_documents WHERE filename='orchard-row-amendment.txt'")
        prompt = client.get("/properties/1/lease-review", params={"document_id": source["id"]})
        assert prompt.status_code == 200 and "Complete extraction prompt" in prompt.text
        proposal = {"schema_version": "1.0", "document_filename": source["filename"], "facts": [{
            "fact_type": "monthly_base_rent", "value": {"amount": "5050.00", "currency": "USD"},
            "effective_from": "2025-07-01", "status": "proposed",
            "uncertainty": "Execution is not established by this fictional review source.",
            "evidence": [{"page": 1, "section": "2. REVISED BASE RENT",
                          "quote": "Effective July 1, 2025, monthly base rent is amended to $5,050.00."}]}]}
        staged = client.post("/properties/1/lease-review", data={"document_id": source["id"], "proposal_json": json.dumps(proposal)})
        assert staged.status_code == 200 and "Pending review" in staged.text
        fact = get_one("SELECT * FROM lease_facts WHERE document_id=? AND status='proposed'", (source["id"],))
        assert get_one("SELECT * FROM lease_facts WHERE property_id=1 AND fact_type='monthly_base_rent' AND status='approved'")["effective_to"] is None
        approved = client.post("/properties/1/facts/{}/review".format(fact["id"]), data={
            "decision": "approved", "acknowledge": "true", "replace": "true", "notes": "Use this presented amendment for the fictional demo; retain execution uncertainty."})
        assert approved.status_code == 200
        assert get_one("SELECT * FROM lease_facts WHERE property_id=1 AND fact_type='monthly_base_rent' AND document_id<>?", (source["id"],))["effective_to"] == "2025-06-30"

        for property_id in (1, 2, 3):
            created = client.post("/reconciliation/obligations", data={**initial, "property_id": property_id})
            assert created.status_code == 200
        with connect() as connection:
            assert connection.execute("SELECT sum(amount_cents) FROM rent_obligations").fetchone()[0] == 1545000
        bad = upload(client, "transactions-invalid.csv")
        assert bad.status_code == 422 and "Row 3" in bad.text
        assert get_one("SELECT count(*) total FROM transactions")["total"] == 0
        assert "4 new transactions" in upload(client, "transactions-2026-10.csv").text
        assert "0 new transactions, 4 duplicate rows skipped" in upload(client, "transactions-2026-10.csv").text
        assert client.post("/reconciliation/matching", data=initial).status_code == 200
        assert get_one("SELECT count(*) total FROM match_proposals WHERE status='proposed'")["total"] == 2
        assert get_one("SELECT count(*) total FROM payment_allocations")["total"] == 0

        for suffix in ("001", "002"):
            proposal_record = get_one("SELECT m.* FROM match_proposals m JOIN transactions t ON t.id=m.transaction_id WHERE t.external_id=?", ("SYN-2026-10-" + suffix,))
            response = client.post("/reconciliation/proposals/{}".format(proposal_record["id"]), data={**initial, "action": "approve", "acknowledge": "true"})
            assert response.status_code == 200
        juniper = get_one("SELECT * FROM rent_obligations WHERE property_id=3 AND period=?", (period,))
        partial = get_one("SELECT * FROM transactions WHERE external_id='SYN-2026-10-003'")
        response = client.post("/reconciliation/allocations", data={**initial, "transaction_id": partial["id"], "obligation_id": juniper["id"], "acknowledge": "true", "notes": "Named Mosaic Foods partial rent for October."})
        assert response.status_code == 200 and "$4,200.00 remains outstanding" in response.text
        assert get_one("SELECT sum(amount_cents) total FROM payment_allocations")["total"] == 1125000
        partial_report = client.get("/report.md", params=initial)
        assert partial_report.status_code == 200
        assert "Expected: $15,450.00 | Approved payments: $11,250.00 | Remaining: $4,200.00" in partial_report.text
        assert "imported credits awaiting review" in partial_report.text
        (tmp_path / "partial-reconciliation.md").write_text(partial_report.text)

        assert "1 new transactions, 1 duplicate rows skipped" in upload(client, "transactions-2026-10-follow-up.csv").text
        followup = get_one("SELECT * FROM transactions WHERE external_id='SYN-2026-10-005'")
        form = {"transaction_id": followup["id"], "obligation_id": juniper["id"], "acknowledge": "true", "notes": "Named October remainder; the earlier unidentified credit remains separate."}
        assert client.post("/reconciliation/allocations", data={**initial, **form}).status_code == 409
        assert client.post("/reconciliation/allocations", data={**later, **form}).status_code == 200
        assert get_one("SELECT * FROM exceptions WHERE issue_key=?", ("balance:{}".format(juniper["id"]),))["status"] == "resolved"
        unidentified = get_one("SELECT e.* FROM exceptions e JOIN transactions t ON t.id=e.transaction_id WHERE t.external_id='SYN-2026-10-004'")
        assert unidentified["status"] == "open"

        assert client.post("/attention/demo-fixtures", data={"as_of": initial["as_of"]}).status_code == 200
        with connect() as connection:
            pending = connection.execute("SELECT id FROM lease_facts WHERE property_id=2 AND status='proposed'").fetchall()
        assert len(pending) == 3
        for pending_fact in pending:
            assert client.post("/properties/2/facts/{}/review".format(pending_fact["id"]), data={"decision": "approved", "acknowledge": "true"}).status_code == 200
        assert "Extension notice window open" in client.get("/attention", params={"as_of": initial["as_of"]}).text
        option = get_one("SELECT * FROM lease_facts WHERE property_id=2 AND fact_type='extension_option' AND status='approved'")
        expiration = get_one("SELECT * FROM lease_facts WHERE property_id=2 AND fact_type='lease_end' AND status='approved'")
        confirmation = get_one("SELECT * FROM lease_documents WHERE filename='beacon-extension-confirmation.txt'")
        quote = confirmation["text_content"].split("2. EXERCISE CONFIRMATION\n\n")[1].split("\n\n3.")[0]
        exercise = client.post("/attention/properties/2/exercise", data={
            "as_of": initial["as_of"], "option_fact_id": option["id"], "lease_end_fact_id": expiration["id"],
            "document_id": confirmation["id"], "exercised_on": "2026-09-15", "new_expiration": "2030-08-31",
            "page": 1, "section": "2. EXERCISE CONFIRMATION", "quote": quote, "acknowledge": "true",
            "notes": "Reviewed fictional delivery/acceptance and dates; extension rent remains unestablished."})
        assert exercise.status_code == 200 and "All approved extension options exercised" in exercise.text
        final_report = client.get("/report.md", params=later)
        assert "Expected: $15,450.00 | Approved payments: $15,450.00 | Remaining: $0.00" in final_report.text
        assert "SYN-2026-10-004" in final_report.text
        assert "Posted after the approved grace period" in final_report.text
        assert "beacon-extension-confirmation.txt" in final_report.text
        assert "No reminder prepared" in final_report.text
        (tmp_path / "final-reconciliation.md").write_text(final_report.text)

    with TestClient(app) as restarted:
        persisted = restarted.get("/report.md", params=later)
        assert "Approved payments: $15,450.00 | Remaining: $0.00" in persisted.text
        assert "All approved extension options exercised" in restarted.get("/attention", params={"as_of": later["as_of"]}).text
        assert get_one("SELECT count(*) total FROM payment_allocations")["total"] == 4
        assert get_one("SELECT count(*) total FROM lease_option_events")["total"] == 1
        assert get_one("SELECT status FROM exceptions WHERE id=?", (unidentified["id"],))["status"] == "open"
