"""Synthetic CSV intake. Importing a transaction never records a rent payment."""

import csv
import hashlib
import io
import json
import re
from datetime import date
from decimal import Decimal

from app.db import connect
from app.services.account_labels import owners, normalize

MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_ROWS = 10000
COLUMNS = ["transaction_id", "posted_date", "description", "amount"]


class CsvImportError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__(" ".join(errors))


def parse_rows(content, accounts):
    if len(content) > MAX_CSV_BYTES:
        raise CsvImportError(["CSV exceeds the 2 MB limit."])
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise CsvImportError(["Use a UTF-8 CSV file, not a spreadsheet or binary file."]) from error
    if "\x00" in text:
        raise CsvImportError(["The file contains binary/null characters. Use a UTF-8 CSV file."])
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    errors, parsed = [], []
    try:
        header = next(reader, [])
        if len(header) != len(COLUMNS) or set(header) != set(COLUMNS):
            raise CsvImportError(["CSV must contain exactly these four unique columns: " + ", ".join(COLUMNS) + "."])
        while True:
            line = reader.line_num + 1
            cells = next(reader, None)
            if cells is None:
                break
            if not cells:
                continue
            if len(parsed) + len(errors) >= MAX_ROWS:
                raise CsvImportError(["CSV exceeds the 10,000-row limit."])
            if len(cells) != len(header):
                errors.append("Row {}: expected four values, received {}.".format(line, len(cells)))
                continue
            row = {key: value.strip() for key, value in zip(header, cells)}
            problems = []
            if not row["transaction_id"] or len(row["transaction_id"]) > 200:
                problems.append("transaction_id must be 1–200 characters")
            if not row["description"] or len(row["description"]) > 2000:
                problems.append("description must be 1–2,000 characters")
            try:
                if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", row["posted_date"]):
                    raise ValueError()
                date.fromisoformat(row["posted_date"])
            except ValueError:
                problems.append("posted_date must be a valid YYYY-MM-DD date")
            amount_cents = None
            if not re.fullmatch(r"[0-9]{1,10}(?:\.[0-9]{1,2})?", row["amount"]):
                problems.append("amount must be positive USD dollars with at most two decimal places (no signs, commas, symbols, or exponents)")
            else:
                amount_cents = int(Decimal(row["amount"]) * 100)
                if amount_cents <= 0:
                    problems.append("amount must be greater than zero")
            if problems:
                errors.append("Row {}: {}.".format(line, "; ".join(problems)))
            else:
                candidates = description_candidates(row["description"], accounts)
                property_id = candidates[0]["property_id"] if len(candidates) == 1 else None
                parsed.append({"external_id": row["transaction_id"], "candidates": candidates,
                               "property_id": property_id, "posted_date": row["posted_date"],
                               "description": row["description"], "amount_cents": amount_cents, "source_row": line})
    except csv.Error as error:
        errors.append("Row {}: malformed CSV ({}).".format(reader.line_num, error))
    if errors:
        raise CsvImportError(errors)
    if not parsed:
        raise CsvImportError(["CSV contains no transaction rows."])
    return parsed


def import_csv(filename, content):
    digest = hashlib.sha256(content).hexdigest()
    filename = (filename or "transactions.csv").replace("\\", "/").rsplit("/", 1)[-1][:255]
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        previous = connection.execute("SELECT * FROM imports WHERE content_digest=?", (digest,)).fetchone()
        if previous:
            return {"import_id": previous["id"], "added": 0, "skipped": previous["row_count"], "repeated_file": True}
        accounts = owners(connection)
        rows = parse_rows(content, accounts)
        seen, new_rows, errors = {}, [], []
        skipped = 0
        for row in rows:
            key = row["external_id"]
            old = seen.get(key)
            if old is None:
                old = connection.execute("SELECT * FROM transaction_intake WHERE external_id=?", (key,)).fetchone()
            if old is None:
                legacy = connection.execute("SELECT * FROM transactions WHERE external_id=?", (key,)).fetchall()
                if len(legacy) > 1:
                    errors.append("Row {}: transaction_id {} has multiple historical records; use a unique bank reference.".format(row["source_row"], key))
                    continue
                old = legacy[0] if legacy else None
            if old is not None:
                if any(old[field] != row[field] for field in ("posted_date", "description", "amount_cents")):
                    errors.append("Row {}: transaction_id {} already exists with different details; nothing was imported.".format(row["source_row"], row["external_id"]))
                else:
                    skipped += 1
            else:
                new_rows.append(row)
                seen[key] = row
        if errors:
            raise CsvImportError(errors)
        import_id = connection.execute(
            "INSERT INTO imports(filename, content_digest, row_count, imported_count, skipped_count, status) VALUES (?, ?, ?, ?, ?, 'imported')",
            (filename, digest, len(rows), len(new_rows), skipped)).lastrowid
        for row in new_rows:
            intake_id = connection.execute(
                "INSERT INTO transaction_intake(external_id,import_id,source_row,posted_date,description,amount_cents,candidates_json) VALUES (?,?,?,?,?,?,?)",
                (row["external_id"], import_id, row["source_row"], row["posted_date"], row["description"], row["amount_cents"], json.dumps(row["candidates"]))).lastrowid
            if row["property_id"] is not None:
                assign_row(connection, intake_id, row["property_id"], "description", row["candidates"])
        return {"import_id": import_id, "added": len(new_rows), "skipped": skipped, "repeated_file": False}


def description_candidates(description, accounts):
    matched = {}
    text = normalize(description)
    for phrase, property_id in accounts.items():
        if phrase and phrase in text:
            matched.setdefault(property_id, []).append(phrase)
    return [{"property_id": property_id, "phrases": sorted(phrases)} for property_id, phrases in sorted(matched.items())]


def assign_row(connection, intake_id, property_id, method, evidence, decision_id=None):
    row = connection.execute("SELECT * FROM transaction_intake WHERE id=?", (intake_id,)).fetchone()
    # account_label is retained only for historical schema compatibility; source CSVs have no such field.
    label = connection.execute("SELECT account_label FROM properties WHERE id=?", (property_id,)).fetchone()[0]
    transaction_id = connection.execute(
        "INSERT INTO transactions(external_id,import_id,source_row,property_id,account_label,posted_date,description,amount_cents) VALUES (?,?,?,?,?,?,?,?)",
        (row["external_id"], row["import_id"], row["source_row"], property_id, label, row["posted_date"], row["description"], row["amount_cents"])).lastrowid
    connection.execute("INSERT INTO transaction_assignments(transaction_id,method,evidence_json,review_decision_id) VALUES (?,?,?,?)",
                       (transaction_id, method, json.dumps(evidence), decision_id))
    connection.execute("UPDATE transaction_intake SET transaction_id=? WHERE id=?", (transaction_id, intake_id))


def unresolved_rows(connection, period=None):
    query = "SELECT q.*,i.filename FROM transaction_intake q JOIN imports i ON i.id=q.import_id WHERE q.transaction_id IS NULL"
    params = []
    if period:
        query += " AND substr(q.posted_date,1,7)=?"
        params.append(period)
    rows = [dict(row) for row in connection.execute(query + " ORDER BY q.posted_date,q.id", params)]
    properties = {row['id']: row['name'] for row in connection.execute('SELECT id,name FROM properties')}
    for row in rows:
        row['candidates'] = [{**item, 'name': properties.get(item['property_id'], 'Unknown property')} for item in json.loads(row['candidates_json'])]
    return rows


def manually_assign(intake_id, property_id, notes, acknowledge, period, as_of):
    from app.services.obligations import month_bounds
    from app.services.payments import review_date
    month_bounds(period)
    review_date(as_of)
    notes = notes.strip()
    if not acknowledge or not notes or len(notes) > 4000:
        raise CsvImportError(["Confirm the property assignment and provide supporting evidence of 1–4,000 characters."])
    with connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute('SELECT * FROM transaction_intake WHERE id=?', (intake_id,)).fetchone()
        if row is None or row['transaction_id'] is not None:
            raise CsvImportError(["This transaction is missing or has already been assigned. Refresh the review."])
        if row['posted_date'][:7] != period or row['posted_date'] > as_of:
            raise CsvImportError(["The transaction must be in the selected month and posted by the review date."])
        if not connection.execute('SELECT 1 FROM properties WHERE id=?', (property_id,)).fetchone():
            raise CsvImportError(["Choose an existing property."])
        decision_id = connection.execute("INSERT INTO review_decisions(record_type,record_id,decision,reviewer_label,notes) VALUES ('transaction_intake',?,'property_assigned','Demo owner',?)",
                                         (intake_id, notes)).lastrowid
        assign_row(connection, intake_id, property_id, 'manual', {'property_id': property_id, 'notes': notes}, decision_id)
