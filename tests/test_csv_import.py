import csv
import io
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app.db import ROOT, connect, initialize
from app.main import app
from app.services.reconciliation import COLUMNS, MAX_CSV_BYTES, CsvImportError, import_csv


def sample(name="transactions-2026-10.csv"):
    return (ROOT / "sample-data" / name).read_bytes()


def csv_bytes(rows, header=COLUMNS):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(header)
    writer.writerows(rows)
    return output.getvalue().encode()


BASE_ROW = ["SYN-TEST-001", "Beacon Industrial operating", "2026-10-05", "FICTIONAL RENT", "3200.00"]


def counts():
    with connect() as connection:
        return tuple(connection.execute("SELECT count(*) FROM " + table).fetchone()[0] for table in ("imports", "transactions"))


def test_file_and_account_scoped_id_duplicates_and_followup(database):
    first = import_csv("original.csv", sample())
    assert (first["added"], first["skipped"]) == (4, 0)
    repeat = import_csv("renamed.csv", sample())
    assert (repeat["added"], repeat["skipped"], repeat["repeated_file"]) == (0, 4, True)
    assert counts() == (1, 4)
    overlap = import_csv("follow-up.csv", sample("transactions-2026-10-follow-up.csv"))
    assert (overlap["added"], overlap["skipped"]) == (1, 1)
    assert counts() == (2, 5)
    # Different bytes, same normalized transactions: no duplicate records.
    normalized = import_csv("newlines.csv", sample().replace(b"\n", b"\r\n"))
    assert (normalized["added"], normalized["skipped"]) == (0, 4)
    initialize()
    with connect() as connection:
        assert connection.execute("SELECT amount_cents FROM transactions WHERE external_id='SYN-2026-10-003'").fetchone()[0] == 300000
        assert connection.execute("SELECT count(*) FROM payment_allocations").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM match_proposals").fetchone()[0] == 0


@pytest.mark.parametrize("column,value", [
    (0, ""), (1, "Unknown account"), (2, "2026-02-30"), (2, "20261005"),
    (3, ""), (4, "-1.00"), (4, "0"), (4, "3200.001"), (4, "NaN"), (4, "Infinity"),
    (4, "1e3"), (4, "$3,200.00"), (4, "+10.00"),
])
def test_invalid_row_blocks_entire_file_with_row_error(database, column, value):
    bad = BASE_ROW.copy()
    bad[0] = "SYN-TEST-002"
    bad[column] = value
    with pytest.raises(CsvImportError, match="Row 3"):
        import_csv("invalid.csv", csv_bytes([BASE_ROW, bad]))
    assert counts() == (0, 0)


def test_conflicting_identifier_rolls_back_new_rows_and_import_record(database):
    import_csv("original.csv", sample())
    with pytest.raises(CsvImportError, match="different details"):
        import_csv("conflict.csv", sample("transactions-conflicting-id.csv"))
    conflict = BASE_ROW.copy()
    conflict[-1] = "1.00"
    with pytest.raises(CsvImportError, match="different details"):
        import_csv("internal-conflict.csv", csv_bytes([BASE_ROW, conflict]))
    assert counts() == (1, 4)
    # A new row preceding a conflict with an earlier import is not committed either.
    existing = ["SYN-2026-10-001", "Orchard Row operating", "2026-10-01", "CHANGED", "5050.00"]
    with pytest.raises(CsvImportError):
        import_csv("mixed.csv", csv_bytes([BASE_ROW, existing]))
    assert counts() == (1, 4)


def test_same_file_duplicates_and_cross_account_identifiers(database):
    other = BASE_ROW.copy()
    other[1] = "Juniper Market operating"
    result = import_csv("same-ids.csv", csv_bytes([BASE_ROW, BASE_ROW, other]))
    assert (result["added"], result["skipped"]) == (2, 1)
    assert counts() == (1, 2)


@pytest.mark.parametrize("content", [
    b"", b"\xff\xfe", b"a,b\n1,2\n", b"transaction_id,account_label,posted_date,description,description\n",
    b"transaction_id,account_label,posted_date,description,amount\n", b"\x00",
    b"transaction_id,account_label,posted_date,description,amount\nx,y,z\n",
    b'transaction_id,account_label,posted_date,description,amount\n"unclosed',
])
def test_unreadable_or_malformed_files_leave_no_records(database, content):
    with pytest.raises(CsvImportError):
        import_csv("bad.csv", content)
    assert counts() == (0, 0)


def test_utf8_bom_reordered_headers_and_exact_cent_conversion(database):
    content = b"\xef\xbb\xbf" + csv_bytes([["0.01", "FICTIONAL CENT", "2026-10-05", "Beacon Industrial operating", "SYN-CENT"]], header=list(reversed(COLUMNS)))
    assert import_csv("cent.csv", content)["added"] == 1
    with connect() as connection:
        assert connection.execute("SELECT amount_cents FROM transactions").fetchone()[0] == 1
    with pytest.raises(CsvImportError, match="2 MB"):
        import_csv("large.csv", b"x" * (MAX_CSV_BYTES + 1))


def test_http_upload_results_errors_persistence_and_reset(database):
    with TestClient(app) as client:
        def upload(content):
            return client.post("/reconciliation/import", data={"period": "2026-10"}, files={"transaction_file": ("test.csv", content, "text/csv")})
        bad = upload(sample("transactions-invalid.csv"))
        assert bad.status_code == 422
        assert "Row 3" in bad.text
        assert counts() == (0, 0)
        accepted = upload(sample())
        assert accepted.status_code == 200
        assert "4 new transactions, 0 duplicate rows skipped" in accepted.text
        assert "SYN-2026-10-001" in accepted.text
        assert "Row 2" in accepted.text
        repeated = upload(sample())
        assert "0 new transactions, 4 duplicate rows skipped" in repeated.text
        assert counts() == (1, 4)
        november = client.get("/reconciliation?period=2026-11")
        assert "No transactions imported for this month" in november.text
    with TestClient(app) as restarted:
        assert "SYN-2026-10-001" in restarted.get("/reconciliation?period=2026-10").text
    result = subprocess.run([sys.executable, "-m", "app.db", "reset", "--confirm"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert counts() == (0, 0)
