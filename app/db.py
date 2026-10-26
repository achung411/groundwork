"""SQLite foundation and explicit fictional-data setup.

Run `python -m app.db init` once; use `reset --confirm` to erase demo work.
Ordinary application startup creates missing tables but never reseeds records.
"""

import argparse
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "property-operations.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    tenant_name TEXT NOT NULL,
    account_label TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS property_account_labels (
    normalized_label TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    active INTEGER NOT NULL CHECK(active IN (0,1))
);
CREATE TABLE IF NOT EXISTS lease_documents (
    id INTEGER PRIMARY KEY,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    filename TEXT NOT NULL UNIQUE,
    document_type TEXT NOT NULL CHECK(document_type IN ('lease', 'amendment')),
    document_date TEXT NOT NULL,
    text_content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS document_uploads (
    document_id INTEGER PRIMARY KEY REFERENCES lease_documents(id),
    original_filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    original_bytes BLOB NOT NULL,
    page_count INTEGER NOT NULL CHECK(page_count > 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS lease_facts (
    id INTEGER PRIMARY KEY,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    document_id INTEGER NOT NULL REFERENCES lease_documents(id),
    fact_type TEXT NOT NULL,
    value_json TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    status TEXT NOT NULL CHECK(status IN ('proposed', 'approved', 'rejected')),
    uncertainty TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS fact_evidence (
    id INTEGER PRIMARY KEY,
    lease_fact_id INTEGER NOT NULL REFERENCES lease_facts(id),
    page INTEGER NOT NULL CHECK(page > 0),
    section TEXT NOT NULL,
    quote TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_decisions (
    id INTEGER PRIMARY KEY,
    record_type TEXT NOT NULL,
    record_id INTEGER NOT NULL,
    decision TEXT NOT NULL,
    reviewer_label TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS extraction_submissions (
    content_digest TEXT PRIMARY KEY,
    lease_fact_id INTEGER NOT NULL UNIQUE REFERENCES lease_facts(id),
    proposal_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS rent_obligations (
    id INTEGER PRIMARY KEY,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    period TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    due_date TEXT NOT NULL,
    grace_days INTEGER CHECK(grace_days >= 0),
    source_fact_id INTEGER NOT NULL REFERENCES lease_facts(id),
    due_fact_id INTEGER NOT NULL REFERENCES lease_facts(id),
    grace_fact_id INTEGER REFERENCES lease_facts(id),
    terms_snapshot_json TEXT NOT NULL,
    assumptions_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(property_id, period)
);
CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    content_digest TEXT NOT NULL UNIQUE,
    row_count INTEGER NOT NULL,
    imported_count INTEGER NOT NULL,
    skipped_count INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status='imported'),
    imported_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    external_id TEXT NOT NULL,
    import_id INTEGER NOT NULL REFERENCES imports(id),
    source_row INTEGER NOT NULL,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    account_label TEXT NOT NULL,
    posted_date TEXT NOT NULL,
    description TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(account_label, external_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS transactions_property_external ON transactions(property_id, external_id);
CREATE TABLE IF NOT EXISTS match_proposals (
    id INTEGER PRIMARY KEY,
    transaction_id INTEGER NOT NULL REFERENCES transactions(id),
    obligation_id INTEGER NOT NULL REFERENCES rent_obligations(id),
    proposed_amount_cents INTEGER NOT NULL CHECK(proposed_amount_cents > 0),
    status TEXT NOT NULL CHECK(status IN ('proposed','approved','rejected','withdrawn')),
    rationale TEXT NOT NULL,
    review_date TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(transaction_id, obligation_id)
);
CREATE TABLE IF NOT EXISTS payment_allocations (
    id INTEGER PRIMARY KEY,
    transaction_id INTEGER NOT NULL UNIQUE REFERENCES transactions(id),
    obligation_id INTEGER NOT NULL REFERENCES rent_obligations(id),
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    review_decision_id INTEGER NOT NULL UNIQUE REFERENCES review_decisions(id),
    match_proposal_id INTEGER REFERENCES match_proposals(id),
    review_date TEXT NOT NULL,
    timing_label TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS exceptions (
    id INTEGER PRIMARY KEY,
    issue_key TEXT NOT NULL UNIQUE,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    transaction_id INTEGER REFERENCES transactions(id),
    obligation_id INTEGER REFERENCES rent_obligations(id),
    kind TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('open','resolved')),
    initial_reason TEXT NOT NULL,
    current_reason TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    opened_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS exception_events (
    id INTEGER PRIMARY KEY,
    exception_id INTEGER NOT NULL REFERENCES exceptions(id),
    event TEXT NOT NULL,
    review_decision_id INTEGER REFERENCES review_decisions(id),
    notes TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS lease_option_events (
    id INTEGER PRIMARY KEY,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    option_fact_id INTEGER NOT NULL REFERENCES lease_facts(id),
    lease_end_fact_id INTEGER NOT NULL REFERENCES lease_facts(id),
    document_id INTEGER NOT NULL REFERENCES lease_documents(id),
    option_number INTEGER NOT NULL CHECK(option_number > 0),
    exercised_on TEXT NOT NULL,
    prior_expiration TEXT NOT NULL,
    new_expiration TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    terms_snapshot_json TEXT NOT NULL,
    review_decision_id INTEGER NOT NULL UNIQUE REFERENCES review_decisions(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(option_fact_id, option_number)
);
"""


def database_path():
    return Path(os.environ.get("PROPERTY_DB_PATH", str(DEFAULT_DB))).expanduser().resolve()


@contextmanager
def connect(path=None):
    target = Path(path) if path is not None else database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize(path=None):
    with connect(path) as connection:
        connection.executescript(SCHEMA)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "reset"])
    parser.add_argument("--confirm", action="store_true", help="Confirm deletion of demo records")
    args = parser.parse_args()
    target = database_path()
    if args.command == "reset":
        if not args.confirm:
            parser.error("reset deletes local demo records; repeat with --confirm. Stop the app first.")
        # Reset our tables transactionally instead of unlinking a potentially open database.
        initialize(target)
        with connect(target) as connection:
            for table in ("lease_option_events", "exception_events", "exceptions", "payment_allocations", "match_proposals", "transactions", "imports", "rent_obligations", "extraction_submissions", "review_decisions", "fact_evidence", "lease_facts", "document_uploads", "lease_documents", "property_account_labels", "properties"):
                connection.execute("DELETE FROM " + table)
            from app.seed import seed
            seed(connection)
    else:
        initialize(target)
        with connect(target) as connection:
            from app.seed import seed
            seed(connection)
    print("Demo database ready: " + str(target))


if __name__ == "__main__":
    main()
