import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.db import ROOT, connect, initialize
from app.main import app
from app.models import ExtractionProposal
from app.services.extraction_import import ReviewError, review_fact, stage_proposal


@pytest.fixture
def proposal():
    # Hand-authored expected proposal for validation tests, not a saved LLM response.
    return {"schema_version": "1.0", "document_filename": "orchard-row-amendment.txt", "facts": [{
        "fact_type": "monthly_base_rent", "value": {"amount": "5050.00", "currency": "USD"},
        "effective_from": "2025-07-01", "effective_to": None, "status": "proposed",
        "uncertainty": "The source does not establish execution status.",
        "evidence": [{"page": 1, "section": "2. REVISED BASE RENT",
                      "quote": "Effective July 1, 2025, monthly base rent is amended to $5,050.00."},
                     {"page": 2, "section": "4. SIGNATURE STATUS",
                      "quote": "For this sample workflow, treat the amendment as a document presented for review. Do not assume that a real-world document is fully executed unless the source itself establishes that fact."}]}]}


def amendment_id():
    with connect() as connection:
        return connection.execute("SELECT id FROM lease_documents WHERE filename='orchard-row-amendment.txt'").fetchone()[0]


def stage(payload):
    return stage_proposal(1, amendment_id(), json.dumps(payload))


def pending_id():
    with connect() as connection:
        return connection.execute("SELECT id FROM lease_facts WHERE status='proposed' ORDER BY id DESC LIMIT 1").fetchone()[0]


def test_amendment_requires_approval_and_preserves_prior_value_and_history(database, proposal):
    assert stage(proposal) == (1, 0)
    assert stage(proposal) == (0, 1)
    fact_id = pending_id()
    with connect() as connection:
        original = dict(connection.execute("SELECT * FROM lease_facts WHERE property_id=1 AND fact_type='monthly_base_rent' AND status='approved'").fetchone())
        assert original["effective_to"] is None
        assert json.loads(original["value_json"])["amount_cents"] == 480000
    with pytest.raises(ReviewError, match="Confirm"):
        review_fact(1, fact_id, "approved", notes="Use as fictional demo term", replace=True)
    with pytest.raises(ReviewError, match="review notes"):
        review_fact(1, fact_id, "approved", acknowledge=True, replace=True)
    with pytest.raises(ReviewError, match="overlaps"):
        review_fact(1, fact_id, "approved", notes="Use as fictional demo term", acknowledge=True)
    review_fact(1, fact_id, "approved", notes="Use as fictional demo term; execution not established", acknowledge=True, replace=True)
    initialize()  # Additive initialization must not reset the reviewed amendment.
    with connect() as connection:
        old = connection.execute("SELECT * FROM lease_facts WHERE id=?", (original["id"],)).fetchone()
        new = connection.execute("SELECT * FROM lease_facts WHERE id=?", (fact_id,)).fetchone()
        assert old["value_json"] == original["value_json"]
        assert old["effective_to"] == "2025-06-30"
        assert new["status"] == "approved"
        assert json.loads(new["value_json"])["amount_cents"] == 505000
        history = connection.execute("SELECT * FROM review_decisions WHERE decision='superseded'").fetchone()
        assert '"effective_to": null' in history["notes"]
        assert "480000" in history["notes"]
    with pytest.raises(ReviewError, match="already been reviewed"):
        review_fact(1, fact_id, "approved", acknowledge=True, replace=True)
    with TestClient(app) as client:
        page = client.get("/properties/1").text
        assert "$5,050.00" in page and "$4,800.00" in page
        assert "through 2025-06-30" in page
        assert "Demo owner" in page
        assert "superseded" in page


@pytest.mark.parametrize("change", [
    {"schema_version": "2.0"},
    {"facts": []},
    {"unexpected": "extra field"},
])
def test_invalid_envelopes_are_rejected(database, proposal, change):
    proposal.update(change)
    with pytest.raises(ReviewError):
        stage(proposal)
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM lease_facts").fetchone()[0] == 7


@pytest.mark.parametrize("path,value", [
    (("value", "amount"), "5050.001"),
    (("value", "amount"), True),
    (("value", "amount"), "0"),
    (("value", "currency"), "EUR"),
    (("effective_from",), "2025-02-30"),
    (("effective_from",), 1751328000),
    (("effective_to",), "2025-01-01"),
    (("status",), "approved"),
    (("fact_type",), "late_fee"),
    (("evidence",), []),
])
def test_bad_values_never_stage(database, proposal, path, value):
    target = proposal["facts"][0]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ReviewError):
        stage(proposal)


@pytest.mark.parametrize("field,value", [("page", 9), ("page", 2), ("section", "1. IDENTIFICATION"), ("quote", "Rent is $9,999.00.")])
def test_wrong_citations_never_stage(database, proposal, field, value):
    proposal["facts"][0]["evidence"][0][field] = value
    with pytest.raises(ReviewError):
        stage(proposal)


def test_all_or_nothing_and_source_identity(database, proposal):
    proposal["facts"].append(deepcopy(proposal["facts"][0]))
    proposal["facts"][1]["evidence"][0]["quote"] = "Unsupported claim"
    with pytest.raises(ReviewError):
        stage(proposal)
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM extraction_submissions").fetchone()[0] == 0
    proposal["document_filename"] = "beacon-industrial-lease.txt"
    with pytest.raises(ReviewError, match="filename"):
        stage(proposal)
    with pytest.raises(ReviewError, match="filename"):
        stage_proposal(2, amendment_id(), json.dumps(proposal))


def test_unknown_date_cannot_be_approved_and_rejection_allows_correction(database, proposal):
    proposal["facts"][0]["effective_from"] = None
    stage(proposal)
    first = pending_id()
    with pytest.raises(ReviewError, match="Effective date is unknown"):
        review_fact(1, first, "approved", notes="Reviewed", acknowledge=True, replace=True)
    review_fact(1, first, "rejected", notes="Correct effective date")
    proposal["facts"][0]["effective_from"] = "2025-07-01"
    stage(proposal)
    assert pending_id() != first
    with connect() as connection:
        assert connection.execute("SELECT status FROM lease_facts WHERE id=?", (first,)).fetchone()[0] == "rejected"


def test_source_is_checked_again_at_approval(database, proposal):
    stage(proposal)
    with connect() as connection:
        connection.execute("UPDATE lease_documents SET text_content='Changed fictional source' WHERE id=?", (amendment_id(),))
    with pytest.raises(ReviewError, match="page"):
        review_fact(1, pending_id(), "approved", notes="Reviewed", acknowledge=True, replace=True)


def test_conflicting_start_dates_do_not_modify_original(database, proposal):
    proposal["facts"][0]["effective_from"] = "2024-01-01"
    stage(proposal)
    with pytest.raises(ReviewError, match="after the earlier"):
        review_fact(1, pending_id(), "approved", notes="Reviewed", acknowledge=True, replace=True)
    with connect() as connection:
        assert connection.execute("SELECT effective_to FROM lease_facts WHERE property_id=1 AND status='approved' AND fact_type='monthly_base_rent'").fetchone()[0] is None


def test_http_paste_errors_decisions_and_property_isolation(database, proposal):
    doc_id = amendment_id()
    with TestClient(app) as client:
        page = client.get("/properties/1/lease-review")
        assert page.status_code == 200
        assert "Complete extraction prompt" in page.text
        assert "schema_version" in page.text
        endpoint = "/properties/1/lease-review"
        invalid = client.post(endpoint, data={"document_id": doc_id, "proposal_json": "Here is JSON: {}"})
        assert invalid.status_code == 422
        assert "Invalid JSON" in invalid.text
        assert "Here is JSON: {}" in invalid.text
        submitted = client.post(endpoint, data={"document_id": doc_id, "proposal_json": json.dumps(proposal)})
        assert submitted.status_code == 200
        assert "Pending review" in submitted.text
        fact_id = pending_id()
        decision_url = "/properties/1/facts/{}/review".format(fact_id)
        assert client.post("/properties/2/facts/{}/review".format(fact_id), data={"decision": "approved"}).status_code == 404
        assert client.post(decision_url, data={"decision": "approved"}).status_code == 409
        approved = client.post(decision_url, data={"decision": "approved", "acknowledge": "true", "replace": "true", "notes": "Accept for fictional demo"})
        assert approved.status_code == 200
        assert "Term approved" in approved.text
        assert client.post(decision_url, data={"decision": "rejected"}).status_code == 409
        assert client.get("/properties/2/lease-review?document_id={}".format(doc_id)).status_code == 404


def test_duplicate_json_keys_and_schema_reference(database, proposal):
    with pytest.raises(ReviewError, match="Duplicate JSON field"):
        stage_proposal(1, amendment_id(), '{"schema_version":"1.0","schema_version":"2.0"}')
    assert json.loads((ROOT / "skills/lease-extraction/schema.json").read_text()) == ExtractionProposal.model_json_schema()


def test_new_base_facts_can_be_reviewed_individually(database):
    with connect() as connection:
        doc = connection.execute("SELECT * FROM lease_documents WHERE filename='beacon-industrial-lease.txt'").fetchone()
    term_quote = "The term begins September 1, 2022 and ends August 31, 2027, unless ended earlier under this Lease."
    facts = []
    for fact_type, value in [("lease_start", {"date": "2022-09-01"}), ("lease_end", {"date": "2027-08-31"}),
                             ("extension_option", {"options_count": 1, "term_months": 36, "notice_earliest_months": 12, "notice_latest_months": 9})]:
        evidence = {"page": 1, "section": "1. PARTIES, PREMISES, AND TERM", "quote": term_quote}
        if fact_type == "extension_option":
            evidence = {"page": 3, "section": "4. EXTENSION OPTION AND NOTICE", "quote": "Tenant may exercise one option to extend the term for three years. Written notice must be delivered no earlier than twelve months and no later than nine months before the current expiration date."}
        facts.append({"fact_type": fact_type, "value": value, "effective_from": "2022-09-01", "status": "proposed", "evidence": [evidence]})
    payload = {"schema_version": "1.0", "document_filename": doc["filename"], "facts": facts}
    assert stage_proposal(2, doc["id"], json.dumps(payload)) == (3, 0)
    with connect() as connection:
        ids = [row[0] for row in connection.execute("SELECT id FROM lease_facts WHERE status='proposed' ORDER BY id")]
    review_fact(2, ids[0], "approved", acknowledge=True)
    review_fact(2, ids[1], "rejected")
    with connect() as connection:
        assert [row[0] for row in connection.execute("SELECT status FROM lease_facts WHERE id IN (?, ?, ?) ORDER BY id", ids)] == ["approved", "rejected", "proposed"]
