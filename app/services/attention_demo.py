"""Explicitly stage manually authored fictional terms; never auto-approve them."""

import json

from app.db import ROOT, connect
from app.services.extraction_import import ReviewError, stage_proposal


def stage_attention_demo():
    with connect() as connection:
        document = connection.execute("SELECT * FROM lease_documents WHERE filename='beacon-industrial-lease.txt' AND property_id=2").fetchone()
        if document is None:
            raise ReviewError("Initialize the fictional Beacon property before staging these examples.")
        existing = {row[0] for row in connection.execute("SELECT fact_type FROM lease_facts WHERE document_id=? AND status IN ('approved','proposed')", (document["id"],))}
    term_quote = "The term begins September 1, 2022 and ends August 31, 2027, unless ended earlier under this Lease."
    definitions = [("lease_start", {"date": "2022-09-01"}, 1, "1. PARTIES, PREMISES, AND TERM", term_quote),
                   ("lease_end", {"date": "2027-08-31"}, 1, "1. PARTIES, PREMISES, AND TERM", term_quote),
                   ("extension_option", {"options_count": 1, "term_months": 36, "notice_earliest_months": 12, "notice_latest_months": 9},
                    3, "4. EXTENSION OPTION AND NOTICE", "Tenant may exercise one option to extend the term for three years. Written notice must be delivered no earlier than twelve months and no later than nine months before the current expiration date.")]
    facts = [{"fact_type": kind, "value": value, "effective_from": "2022-09-01", "status": "proposed",
              "evidence": [{"page": page, "section": section, "quote": quote}]} for kind, value, page, section, quote in definitions if kind not in existing]
    added = 0
    if facts:
        added, _ = stage_proposal(2, document["id"], json.dumps({"schema_version": "1.0", "document_filename": document["filename"], "facts": facts}))
    filename = "beacon-extension-confirmation.txt"
    with connect() as connection:
        connection.execute("INSERT INTO lease_documents(property_id, filename, document_type, document_date, text_content) VALUES (2, ?, 'amendment', '2026-09-15', ?) ON CONFLICT(filename) DO NOTHING",
                           (filename, (ROOT / "sample-data/leases" / filename).read_text()))
    return added
