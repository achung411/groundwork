import csv
import io

import pytest
from fastapi.testclient import TestClient

from app.db import connect, initialize
from app.main import app
from app.services.ledger import build_ledger
from app.services.obligations import create_obligation
from app.services.payments import approve_payment, run_matching
from app.services.reconciliation import COLUMNS, import_csv


def upload(rows):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    return import_csv('fictional-ledger.csv', output.getvalue().encode())


@pytest.fixture
def ledger_records(database):
    with connect() as connection:
        pid = connection.execute("SELECT id FROM properties WHERE name='Beacon Industrial'").fetchone()[0]
    sep, _ = create_obligation(pid, '2026-09')
    oct_id, _ = create_obligation(pid, '2026-10')
    create_obligation(pid, '2026-11')
    upload([
        ['SYN-L-1', 'Beacon Industrial operating', '2026-09-05', 'FICTIONAL PARTIAL', '1000.00'],
        ['SYN-L-2', 'Beacon Industrial operating', '2026-10-10', 'FICTIONAL ARREARS', '2200.00'],
        ['SYN-L-3', 'Beacon Industrial operating', '2026-10-20', 'FICTIONAL FULL RENT', '3200.00'],
        ['SYN-L-PENDING', 'Beacon Industrial operating', '2026-10-12', 'FICTIONAL UNREVIEWED', '400.00'],
        ['SYN-L-FUTURE', 'Beacon Industrial operating', '2026-12-01', 'FICTIONAL FUTURE', '100.00'],
        ['SYN-L-OTHER', 'Juniper Market operating', '2026-10-12', 'FICTIONAL OTHER PROPERTY', '77.00'],
    ])
    with connect() as connection:
        tx = {row['external_id']: row['id'] for row in connection.execute('SELECT * FROM transactions')}
    for ref, obligation, period in [('SYN-L-1', sep, '2026-09'), ('SYN-L-2', sep, '2026-10'), ('SYN-L-3', oct_id, '2026-10')]:
        approve_payment(tx[ref], obligation, period, '2026-10-25', notes='Reviewed fictional receipt evidence', acknowledge=True)
    return pid


def view(pid, as_of='2026-10-25'):
    with connect() as connection:
        return build_ledger(connection, pid, as_of)


def test_chronological_running_balance_partial_arrears_and_totals(ledger_records):
    ledger = view(ledger_records)
    assert [row['kind'] for row in ledger['rows']] == ['Rent charge', 'Approved payment', 'Rent charge', 'Approved payment', 'Approved payment']
    assert [row['balance_cents'] for row in ledger['rows']] == [320000, 220000, 540000, 320000, 0]
    assert ledger['charged_cents'] == ledger['received_cents'] == 640000
    assert ledger['balance_cents'] == 0
    arrears = ledger['rows'][3]
    assert (arrears['event_date'], arrears['period'], arrears['due_date']) == ('2026-10-10', '2026-09', '2026-09-05')
    assert ledger['pending_cents'] == 40000
    assert [row['external_id'] for row in ledger['pending']] == ['SYN-L-PENDING']
    assert [row['period'] for row in ledger['upcoming']] == ['2026-11']


def test_review_date_excludes_future_payments_and_charges(ledger_records):
    early = view(ledger_records, '2026-09-30')
    assert early['balance_cents'] == 220000
    assert len(early['rows']) == 2
    middle = view(ledger_records, '2026-10-15')
    assert middle['balance_cents'] == 320000
    assert middle['received_cents'] == 320000
    before = view(ledger_records, '2026-08-31')
    assert before['rows'] == []
    assert before['balance_cents'] == 0
    assert len(before['upcoming']) == 3


def test_property_isolation_and_persistence(ledger_records):
    initialize()
    with connect() as connection:
        other = connection.execute("SELECT id FROM properties WHERE name='Juniper Market'").fetchone()[0]
    ledger = view(other)
    assert ledger['rows'] == []
    assert ledger['balance_cents'] == 0
    assert ledger['pending_cents'] == 7700
    assert view(ledger_records)['received_cents'] == 640000


def test_proposals_do_not_reduce_balance_and_gets_do_not_write(database):
    with connect() as connection:
        pid = connection.execute("SELECT id FROM properties WHERE name='Beacon Industrial'").fetchone()[0]
    create_obligation(pid, '2026-10')
    upload([['SYN-PROPOSED', 'Beacon Industrial operating', '2026-10-01', 'FICTIONAL RENT', '3200.00']])
    assert run_matching('2026-10', '2026-10-25') == 1
    with connect() as connection:
        before = list(connection.iterdump())
    with TestClient(app) as client:
        response = client.get('/properties/{}/ledger?as_of=2026-10-25'.format(pid))
        assert response.status_code == 200
        assert 'Rent balance owed' in response.text
        assert 'Credits awaiting approval' in response.text
        assert 'SYN-PROPOSED' in response.text
        assert 'Received date' in response.text
        assert 'View rent ledger' in client.get('/').text
        assert 'View rent ledger' in client.get('/properties/{}'.format(pid)).text
    with connect() as connection:
        assert before == list(connection.iterdump())
    assert view(pid)['received_cents'] == 0
    assert view(pid)['balance_cents'] == 320000


def test_empty_ledger_invalid_date_and_unknown_property(database):
    with TestClient(app) as client:
        response = client.get('/properties/1/ledger?as_of=2026-10-25')
        assert response.status_code == 200
        assert 'No rent ledger entries through this date' in response.text
        invalid = client.get('/properties/1/ledger?as_of=2026-02-30')
        assert invalid.status_code == 422
        assert 'Choose a valid review date' in invalid.text
        assert client.get('/properties/99999/ledger').status_code == 404


def test_early_payment_shows_credit_until_due_date(database):
    obligation_id, _ = create_obligation(2, '2026-10')
    upload([['SYN-EARLY', 'Beacon Industrial operating', '2026-10-01', 'FICTIONAL EARLY RENT', '0.01']])
    with connect() as connection:
        transaction_id = connection.execute('SELECT id FROM transactions').fetchone()[0]
    approve_payment(transaction_id, obligation_id, '2026-10', '2026-10-03', notes='Reviewed fictional early partial payment', acknowledge=True)
    ledger = view(2, '2026-10-03')
    assert ledger['balance_cents'] == -1
    assert ledger['charged_cents'] == 0
    assert ledger['received_cents'] == 1
    assert view(2, '2026-10-05')['balance_cents'] == 319999
    with TestClient(app) as client:
        response = client.get('/properties/2/ledger?as_of=2026-10-03')
        assert '-$0.01' in response.text
        assert 'negative balance is a credit' in response.text
