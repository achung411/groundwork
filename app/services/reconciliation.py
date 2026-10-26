"""Synthetic CSV intake. Importing a transaction never records a rent payment."""

import csv
import hashlib
import io
import re
from datetime import date
from decimal import Decimal

from app.db import connect
from app.services.account_labels import owners, normalize

MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_ROWS = 10000
COLUMNS = ["transaction_id", "account_label", "posted_date", "description", "amount"]


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
            raise CsvImportError(["CSV must contain exactly these five unique columns: " + ", ".join(COLUMNS) + "."])
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
                errors.append("Row {}: expected five values, received {}.".format(line, len(cells)))
                continue
            row = {key: value.strip() for key, value in zip(header, cells)}
            problems = []
            if not row["transaction_id"] or len(row["transaction_id"]) > 200:
                problems.append("transaction_id must be 1–200 characters")
            if normalize(row["account_label"]) not in accounts:
                problems.append("account_label does not match a fictional property account")
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
                parsed.append({"external_id": row["transaction_id"], "account_label": row["account_label"],
                               "property_id": accounts[normalize(row["account_label"])], "posted_date": row["posted_date"],
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
            key = (row["property_id"], row["external_id"])
            # The same transaction ID may legitimately exist on a different property account.
            old = seen.get(key)
            if old is None:
                old = connection.execute("SELECT * FROM transactions WHERE property_id=? AND external_id=?", key).fetchone()
            if old is not None:
                if any(old[field] != row[field] for field in ("posted_date", "description", "amount_cents", "property_id")):
                    errors.append("Row {}: transaction_id {} already exists on this account with different details; nothing was imported.".format(row["source_row"], row["external_id"]))
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
            connection.execute(
                "INSERT INTO transactions(external_id, import_id, source_row, property_id, account_label, posted_date, description, amount_cents) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (row["external_id"], import_id, row["source_row"], row["property_id"], row["account_label"], row["posted_date"], row["description"], row["amount_cents"]))
        return {"import_id": import_id, "added": len(new_rows), "skipped": skipped, "repeated_file": False}
