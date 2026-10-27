import csv
import io

import pytest
from fastapi.testclient import TestClient

from app.db import connect, initialize
from app.main import app
from app.services.account_labels import AccountLabelError, save_settings, settings
from app.services.document_intake import IntakeError, create_property
from app.services.obligations import create_obligation
from app.services.payments import approve_payment, run_matching
from app.services.reconciliation import COLUMNS, CsvImportError, import_csv


def deposit(label, amount='3200.00', identifier='SYN-LABEL-1'):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(COLUMNS)
    writer.writerow([identifier, '2026-10-05', 'FICTIONAL RENT | ' + label, amount])
    return output.getvalue().encode()


def beacon_id():
    with connect() as connection:
        return connection.execute("SELECT id FROM properties WHERE account_label='Beacon Industrial operating'").fetchone()[0]


def test_alias_import_normalization_and_duplicate_protection(database):
    pid = beacon_id()
    save_settings(pid, 'Beacon checking', 'Beacon export\nBEACON EXPORT')
    assert import_csv('one.csv', deposit('  BEACON EXPORT  '))['added'] == 1
    assert import_csv('two.csv', deposit('  BEACON EXPORT  ').replace(b'\r\n', b'\n'))['skipped'] == 1
    with pytest.raises(CsvImportError, match='different details'):
        import_csv('conflict.csv', deposit('Beacon checking', '3201.00'))
    with connect() as connection:
        rows = connection.execute('SELECT * FROM transactions').fetchall()
        assert len(rows) == 1
        assert rows[0]['property_id'] == pid
        assert rows[0]['account_label'] == 'Beacon checking'


def test_old_label_remains_valid_for_existing_payment_only(database):
    pid = beacon_id()
    obligation_id, _ = create_obligation(pid, '2026-10')
    import_csv('old.csv', deposit('Beacon Industrial operating'))
    save_settings(pid, 'Beacon checking', '')
    import_csv('retired.csv', deposit('Beacon Industrial operating', identifier='SYN-NEW'))
    with connect() as connection:
        assert connection.execute('SELECT count(*) FROM transaction_intake WHERE transaction_id IS NULL').fetchone()[0] == 1
    assert run_matching('2026-10', '2026-10-25') == 1
    with connect() as connection:
        proposal = connection.execute('SELECT * FROM match_proposals').fetchone()
    approve_payment(proposal['transaction_id'], obligation_id, '2026-10', '2026-10-25', acknowledge=True, proposal_id=proposal['id'])
    initialize()
    with connect() as connection:
        assert connection.execute('SELECT count(*) FROM payment_allocations').fetchone()[0] == 1
        assert connection.execute('SELECT account_label FROM transactions').fetchone()[0] == 'Beacon Industrial operating'
        assert settings(connection, pid)['preferred_label'] == 'Beacon checking'


def test_label_ownership_reserved_and_settings_atomic(database):
    pid = beacon_id()
    save_settings(pid, 'Beacon checking', 'Reserved alias')
    save_settings(pid, 'Beacon checking', '')
    with connect() as connection:
        other = connection.execute('SELECT id FROM properties WHERE id<>? LIMIT 1', (pid,)).fetchone()[0]
        before = settings(connection, other)
    for label in ('reserved ALIAS', 'BEACON INDUSTRIAL OPERATING', 'Beacon checking'):
        with pytest.raises(AccountLabelError, match='reserved'):
            save_settings(other, 'Uncommitted label', label)
    with pytest.raises(IntakeError, match='already used'):
        create_property('Fictional new', 'Fictional tenant', 'RESERVED ALIAS', '2026-01-01', 'new.txt', b'Fictional lease text')
    with connect() as connection:
        assert settings(connection, other) == before
        assert connection.execute("SELECT count(*) FROM property_account_labels WHERE label='Uncommitted label'").fetchone()[0] == 0


@pytest.mark.parametrize('preferred,aliases', [('', ''), ('x' * 161, ''), ('Bad\x00label', ''), ('Valid', '\n'.join(str(i) for i in range(30)))])
def test_invalid_settings_leave_no_changes(database, preferred, aliases):
    pid = beacon_id()
    with pytest.raises(AccountLabelError):
        save_settings(pid, preferred, aliases)
    with connect() as connection:
        assert settings(connection, pid)['preferred_label'] == 'Beacon Industrial operating'
        assert connection.execute('SELECT count(*) FROM property_account_labels').fetchone()[0] == 0


def test_settings_ui_history_errors_noop_and_restart(database):
    pid = beacon_id()
    url = '/properties/{}/matching'.format(pid)
    with TestClient(app) as client:
        assert 'Configure transaction labels' in client.get('/properties/{}'.format(pid)).text
        assert 'Beacon Industrial operating' in client.get(url).text
        data = {'preferred_label': 'Beacon checking', 'aliases': 'CSV alias'}
        response = client.post(url, data=data)
        assert response.status_code == 200
        assert 'Account labels saved' in response.text
        assert 'Beacon Industrial operating → Beacon checking' in response.text
        assert client.post(url, data=data).status_code == 200
        invalid = client.post(url, data={'preferred_label': 'Orchard Row operating', 'aliases': 'Preserve typed alias'})
        assert invalid.status_code == 422
        assert 'Preserve typed alias' in invalid.text
        assert 'reserved' in invalid.text
        assert client.get('/properties/99999/matching').status_code == 404
    with TestClient(app) as client:
        assert 'CSV alias' in client.get(url).text
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM review_decisions WHERE decision='matching_labels_changed'").fetchone()[0] == 1
