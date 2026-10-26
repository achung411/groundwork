import sqlite3
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app.db import ROOT, connect, initialize
from app.main import app
from app.seed import seed


def test_setup_and_app_restart_preserve_existing_records(database):
    with connect() as connection:
        connection.execute("UPDATE properties SET tenant_name='Updated fictional tenant' WHERE id=1")
        before = {table: connection.execute("SELECT count(*) FROM " + table).fetchone()[0]
                  for table in ("properties", "lease_documents", "lease_facts", "review_decisions")}
    result = subprocess.run([sys.executable, "-m", "app.db", "init"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    for _ in range(2):
        with TestClient(app) as client:
            assert "Updated fictional tenant" in client.get("/").text
    with connect() as connection:
        for table, count in before.items():
            assert connection.execute("SELECT count(*) FROM " + table).fetchone()[0] == count


def test_seed_evidence_and_amendment_boundary(database):
    with connect() as connection:
        facts = connection.execute(
            "SELECT f.*, e.page, e.quote, d.text_content FROM lease_facts f "
            "JOIN fact_evidence e ON e.lease_fact_id=f.id JOIN lease_documents d ON d.id=f.document_id").fetchall()
        assert len(facts) == 7
        for fact in facts:
            page_text = fact["text_content"].split("--- Page {} ---".format(fact["page"]))[1].split("--- Page")[0]
            assert fact["quote"] in page_text
            assert connection.execute(
                "SELECT count(*) FROM review_decisions WHERE record_type='lease_fact' AND record_id=? AND decision='approved'",
                (fact["id"],)).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM lease_facts f JOIN lease_documents d ON d.id=f.document_id "
            "WHERE d.document_type='amendment'").fetchone()[0] == 0
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO lease_documents(property_id, filename, document_type, document_date, text_content) "
                               "VALUES (999, 'invalid.txt', 'lease', '2026-01-01', 'fictional')")


def test_pages_and_missing_property(database):
    with TestClient(app) as client:
        overview = client.get("/")
        assert overview.status_code == 200
        assert "Orchard Row Retail" in overview.text
        assert "Payment review ready" in overview.text
        for property_id in (1, 2, 3):
            assert client.get("/properties/{}".format(property_id)).status_code == 200
        orchard = client.get("/properties/1").text
        assert "$4,800.00" in orchard
        assert "Extract and review lease terms" in orchard
        assert "Grace period not specified" in orchard
        beacon = client.get("/properties/2").text
        assert "5 calendar days" in beacon
        assert client.get("/properties/999").status_code == 404
        assert client.get("/static/style.css").status_code == 200


def test_reset_requires_confirmation_and_explicit_reset_reseeds(database):
    with connect() as connection:
        connection.execute("UPDATE properties SET tenant_name='Changed demo name' WHERE id=1")
    command = [sys.executable, "-m", "app.db", "reset"]
    denied = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert denied.returncode != 0
    with connect() as connection:
        assert connection.execute("SELECT tenant_name FROM properties WHERE id=1").fetchone()[0] == "Changed demo name"
    reset = subprocess.run(command + ["--confirm"], cwd=ROOT, capture_output=True, text=True)
    assert reset.returncode == 0, reset.stderr
    with connect() as connection:
        assert connection.execute("SELECT tenant_name FROM properties WHERE id=1").fetchone()[0] == "Willow & Pine Outfitters LLC"


def test_empty_startup_does_not_seed(tmp_path, monkeypatch):
    monkeypatch.setenv("PROPERTY_DB_PATH", str(tmp_path / "empty.sqlite3"))
    with TestClient(app) as client:
        assert "No demo properties yet" in client.get("/").text


def test_clear_requires_confirmation_empties_all_records_and_stays_empty(database):
    command = [sys.executable, "-m", "app.db", "clear"]
    denied = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert denied.returncode != 0
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM properties").fetchone()[0] == 3
    cleared = subprocess.run(command + ["--confirm"], cwd=ROOT, capture_output=True, text=True)
    assert cleared.returncode == 0, cleared.stderr
    for _ in range(2):
        with TestClient(app) as client:
            assert "No demo properties yet" in client.get("/").text
            assert client.get("/properties/new").status_code == 200
            assert client.get("/reconciliation?period=2026-10").status_code == 200
    with connect() as connection:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        assert tables
        assert all(connection.execute('SELECT count(*) FROM "' + table + '"').fetchone()[0] == 0 for table in tables)
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
    assert (ROOT / "sample-data/leases/beacon-industrial-lease.txt").is_file()
    assert (ROOT / "sample-data/transactions-2026-10.csv").is_file()
