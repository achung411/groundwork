"""Validate evidence, stage proposals, and atomically record human decisions."""

import hashlib
import json
import re
from datetime import date, timedelta

from pydantic import ValidationError

from app.db import connect
from app.models import ExtractionProposal


class ReviewError(ValueError):
    pass


def normalize(text):
    return " ".join(text.split())


def verify_evidence(document, evidence):
    pages = re.split(r"--- Page (\d+) ---", document["text_content"])
    page_map = {int(pages[i]): pages[i + 1] for i in range(1, len(pages), 2)}
    for item in evidence:
        page = page_map.get(item["page"])
        if page is None:
            raise ReviewError("Cited page {} does not exist in {}.".format(item["page"], document["filename"]))
        sections = list(re.finditer(r"(?m)^\d+\. [^\n]+", page))
        section_text = page if not sections and item["section"] == "Page text" else None
        for index, heading in enumerate(sections):
            if normalize(heading.group()).casefold() == normalize(item["section"]).casefold():
                end = sections[index + 1].start() if index + 1 < len(sections) else len(page)
                section_text = page[heading.start():end]
                break
        if section_text is None:
            raise ReviewError("Section '{}' was not found on page {}.".format(item["section"], item["page"]))
        if normalize(item["quote"]) not in normalize(section_text):
            raise ReviewError("Quotation was not found in page {}, section '{}'. Correct and resubmit the JSON.".format(
                item["page"], item["section"]))


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReviewError("Duplicate JSON field: " + key)
        result[key] = value
    return result


def parse_proposal(raw):
    if len(raw) > 150000:
        raise ReviewError("Proposal is too large; paste at most 150,000 characters.")
    try:
        payload = json.loads(raw, object_pairs_hook=reject_duplicate_keys)
        return ExtractionProposal.model_validate(payload)
    except json.JSONDecodeError as error:
        raise ReviewError("Invalid JSON at line {}, column {}. Paste only the JSON object, without code fences or surrounding prose.".format(
            error.lineno, error.colno)) from error
    except ValidationError as error:
        messages = ["{}: {}".format(" → ".join(map(str, item["loc"])), item["msg"])
                    for item in error.errors(include_url=False)]
        raise ReviewError("Invalid proposal. " + "; ".join(messages)) from error


def stage_proposal(property_id, document_id, raw):
    proposal = parse_proposal(raw)
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        document = connection.execute("SELECT * FROM lease_documents WHERE id=? AND property_id=?",
                                      (document_id, property_id)).fetchone()
        if document is None or proposal.document_filename != document["filename"]:
            raise ReviewError("The proposal filename must match the selected source document for this property.")
        added = skipped = 0
        for fact in proposal.facts:
            item = fact.model_dump(mode="json")
            verify_evidence(document, item["evidence"])
            serialized = json.dumps(item, sort_keys=True)
            digest = hashlib.sha256((str(document_id) + ":" + serialized).encode()).hexdigest()
            if connection.execute("SELECT 1 FROM extraction_submissions WHERE content_digest=?", (digest,)).fetchone():
                skipped += 1
                continue
            value = item["value"]
            if fact.fact_type == "monthly_base_rent":
                value = {"amount_cents": int(fact.value.amount * 100), "currency": "USD"}
            # Unknown effective dates are held in the submission only; the DB's date field stays non-null.
            # Empty string is never an approved date, and approval explicitly rejects it.
            fact_id = connection.execute(
                "INSERT INTO lease_facts(property_id, document_id, fact_type, value_json, effective_from, effective_to, status, uncertainty) "
                "VALUES (?, ?, ?, ?, ?, ?, 'proposed', ?)",
                (property_id, document_id, fact.fact_type, json.dumps(value), item["effective_from"] or "",
                 item["effective_to"], fact.uncertainty)).lastrowid
            for evidence in item["evidence"]:
                connection.execute("INSERT INTO fact_evidence(lease_fact_id, page, section, quote) VALUES (?, ?, ?, ?)",
                                   (fact_id, evidence["page"], evidence["section"], evidence["quote"]))
            connection.execute(
                "INSERT INTO extraction_submissions(content_digest, lease_fact_id, proposal_json) VALUES (?, ?, ?)",
                (digest, fact_id, serialized))
            added += 1
        return added, skipped


def review_fact(property_id, fact_id, decision, notes="", acknowledge=False, replace=False):
    if decision not in ("approved", "rejected"):
        raise ReviewError("Choose approve or reject.")
    notes = notes.strip()
    if len(notes) > 4000:
        raise ReviewError("Review notes must be 4,000 characters or fewer.")
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        fact = connection.execute("SELECT * FROM lease_facts WHERE id=? AND property_id=?", (fact_id, property_id)).fetchone()
        if fact is None:
            raise ReviewError("Proposal not found for this property.")
        if fact["status"] != "proposed":
            raise ReviewError("This proposal has already been reviewed. Refresh to see its decision.")
        history = []
        if decision == "approved":
            document = connection.execute("SELECT * FROM lease_documents WHERE id=? AND property_id=?",
                                          (fact["document_id"], property_id)).fetchone()
            evidence = [dict(row) for row in connection.execute("SELECT page, section, quote FROM fact_evidence WHERE lease_fact_id=?", (fact_id,))]
            if not evidence:
                raise ReviewError("Source evidence is required before approval.")
            verify_evidence(document, evidence)
            if not fact["effective_from"]:
                raise ReviewError("Effective date is unknown. Reject this proposal and resubmit corrected JSON before approval.")
            if not acknowledge:
                raise ReviewError("Confirm that you reviewed the source evidence and any uncertainty before approving.")
            if fact["uncertainty"] and not notes:
                raise ReviewError("Explain your decision in review notes when a proposal has uncertainty.")
            overlaps = connection.execute(
                "SELECT * FROM lease_facts WHERE property_id=? AND fact_type=? AND status='approved' "
                "AND effective_from <= ? AND (effective_to IS NULL OR effective_to >= ?)",
                (property_id, fact["fact_type"], fact["effective_to"] or "9999-12-31", fact["effective_from"])).fetchall()
            if overlaps:
                if len(overlaps) != 1 or document["document_type"] != "amendment" or not replace:
                    raise ReviewError("This overlaps an approved term. Only an explicit amendment replacement of one earlier term is supported.")
                old = overlaps[0]
                if old["effective_from"] >= fact["effective_from"]:
                    raise ReviewError("Replacement must begin after the earlier term's effective start. Correct conflicting dates and resubmit.")
                if old["effective_to"] != fact["effective_to"]:
                    raise ReviewError("Replacement must retain the earlier term's end date (including an open end). Temporary overrides are outside scope.")
                previous = json.dumps({"value": json.loads(old["value_json"]), "effective_from": old["effective_from"],
                                       "effective_to": old["effective_to"]}, sort_keys=True)
                end = (date.fromisoformat(fact["effective_from"]) - timedelta(days=1)).isoformat()
                connection.execute("UPDATE lease_facts SET effective_to=? WHERE id=?", (end, old["id"]))
                connection.execute(
                    "INSERT INTO review_decisions(record_type, record_id, decision, reviewer_label, notes) "
                    "VALUES ('lease_fact', ?, 'superseded', 'Demo owner', ?)",
                    (old["id"], "Replaced by fact #{} starting {}. Prior record: {}. {}".format(fact_id, fact["effective_from"], previous, notes)))
                history.append("Replaces fact #{} from {}. Existing obligations and payments are unchanged.".format(old["id"], fact["effective_from"]))
            history.append("Source evidence and uncertainty reviewed.")
        connection.execute("UPDATE lease_facts SET status=? WHERE id=?", (decision, fact_id))
        connection.execute(
            "INSERT INTO review_decisions(record_type, record_id, decision, reviewer_label, notes) "
            "VALUES ('lease_fact', ?, ?, 'Demo owner', ?)",
            (fact_id, decision, " ".join(history + [notes]).strip()))
