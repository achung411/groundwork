import csv
import io
import json

import pytest
from fastapi.testclient import TestClient

from app.db import connect, initialize, ROOT
from app.main import app
from app.services.account_labels import save_settings
from app.services.obligations import create_obligation
from app.services.payments import run_matching, approve_payment
from app.services.reconciliation import import_csv, manually_assign, unresolved_rows, CsvImportError, COLUMNS


def content(rows):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    return out.getvalue().encode()


def row(ref, description, amount='3200.00', posted='2026-10-05'):
    return [ref, posted, description, amount]


def test_case_insensitive_substrings_same_property_aliases_and_ambiguity(database):
    save_settings(2, 'TIDEPOOL', 'printworks\nTidepool Printworks')
    save_settings(3, 'Mosaic', '')
    result = import_csv('descriptions.csv', content([
        row('SYN-UNIQUE', 'ACH credit from TidePool Printworks Inc. Oct rent'),
        row('SYN-NONE', 'ACH CREDIT'),
        row('SYN-MULTIPLE', 'Tidepool payment for Mosaic account'),
    ]))
    assert result['added'] == 3
    with connect() as connection:
        tx = connection.execute('SELECT * FROM transactions').fetchall()
        assert len(tx) == 1 and tx[0]['property_id'] == 2
        evidence = json.loads(connection.execute('SELECT evidence_json FROM transaction_assignments').fetchone()[0])
        assert evidence == [{'property_id': 2, 'phrases': ['printworks', 'tidepool', 'tidepool printworks']}]
        unresolved = unresolved_rows(connection, '2026-10')
        assert len(unresolved) == 2
        assert unresolved[0]['candidates'] == []
        assert {item['property_id'] for item in unresolved[1]['candidates']} == {2, 3}
        assert connection.execute('SELECT count(*) FROM payment_allocations').fetchone()[0] == 0


def test_overlapping_phrases_do_not_prefer_longest_or_first_property(database):
    save_settings(2, 'studio', '')
    save_settings(3, 'Mosaic studio', '')
    import_csv('overlap.csv', content([row('SYN-OVERLAP', 'MOSAIC STUDIO PAYMENT')]))
    with connect() as connection:
        assert connection.execute('SELECT count(*) FROM transactions').fetchone()[0] == 0
        assert len(unresolved_rows(connection)[0]['candidates']) == 2


def test_manual_assignment_audited_and_payment_still_requires_approval(database):
    obligation_id, _ = create_obligation(2, '2026-10')
    source = content([row('SYN-MANUAL', 'ACH CREDIT')])
    import_csv('manual.csv', source)
    assert run_matching('2026-10', '2026-10-25') == 0
    with connect() as connection:
        intake_id = unresolved_rows(connection)[0]['id']
    manually_assign(intake_id, 2, 'Verified fictional payer reference', True, '2026-10', '2026-10-25')
    with connect() as connection:
        tx = connection.execute('SELECT * FROM transactions').fetchone()
        assert tx['property_id'] == 2 and tx['description'] == 'ACH CREDIT'
        assert not unresolved_rows(connection)
        assignment = connection.execute('SELECT * FROM transaction_assignments').fetchone()
        decision = connection.execute('SELECT * FROM review_decisions WHERE id=?', (assignment['review_decision_id'],)).fetchone()
        assert decision['decision'] == 'property_assigned'
        assert 'Verified fictional payer' in decision['notes']
        assert connection.execute('SELECT count(*) FROM payment_allocations').fetchone()[0] == 0
    save_settings(3, 'ACH CREDIT', '')
    assert import_csv('reimport.csv', source.replace(b'\r\n', b'\n'))['skipped'] == 1
    with pytest.raises(CsvImportError, match='already been assigned'):
        manually_assign(intake_id, 3, 'Trying again', True, '2026-10', '2026-10-25')
    assert run_matching('2026-10', '2026-10-25') == 1
    with connect() as connection:
        proposal_id = connection.execute('SELECT id FROM match_proposals').fetchone()[0]
    approve_payment(tx['id'], obligation_id, '2026-10', '2026-10-25', acknowledge=True, proposal_id=proposal_id)
    initialize()
    with connect() as connection:
        assert connection.execute('SELECT property_id FROM transactions').fetchone()[0] == 2
        assert connection.execute('SELECT count(*) FROM payment_allocations').fetchone()[0] == 1


@pytest.mark.parametrize('property_id,notes,ack,period,as_of', [
    (999, 'Evidence', True, '2026-10', '2026-10-25'),
    (2, '', True, '2026-10', '2026-10-25'),
    (2, 'Evidence', False, '2026-10', '2026-10-25'),
    (2, 'Evidence', True, '2026-09', '2026-10-25'),
    (2, 'Evidence', True, '2026-10', '2026-10-01'),
])
def test_invalid_manual_assignment_is_atomic(database, property_id, notes, ack, period, as_of):
    import_csv('unresolved.csv', content([row('SYN-UNRESOLVED', 'Unknown credit')]))
    with connect() as connection:
        intake_id = unresolved_rows(connection)[0]['id']
    with pytest.raises(CsvImportError):
        manually_assign(intake_id, property_id, notes, ack, period, as_of)
    with connect() as connection:
        assert len(unresolved_rows(connection)) == 1
        assert connection.execute('SELECT count(*) FROM transactions').fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM review_decisions WHERE decision='property_assigned'").fetchone()[0] == 0


def test_unresolved_duplicates_conflicts_and_label_changes(database):
    source = content([row('SYN-REPEAT', 'Unidentified credit')])
    import_csv('first.csv', source)
    save_settings(2, 'Unidentified', '')
    assert import_csv('repeat.csv', source.replace(b'\r\n', b'\n'))['skipped'] == 1
    with pytest.raises(CsvImportError, match='different details'):
        import_csv('conflict.csv', content([row('SYN-NEW', 'Unidentified'), row('SYN-REPEAT', 'Unidentified credit', '3201.00')]))
    with connect() as connection:
        assert len(unresolved_rows(connection)) == 1
        assert connection.execute('SELECT count(*) FROM transactions').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM imports').fetchone()[0] == 2


def test_four_columns_required_and_unassigned_rows_visible_in_report_and_http(database):
    with pytest.raises(CsvImportError, match='four unique columns'):
        import_csv('old.csv', b'transaction_id,account_label,posted_date,description,amount\nSYN-OLD,Beacon,2026-10-05,ACH,3200.00\n')
    with TestClient(app) as client:
        response = client.post('/reconciliation/import', data={'period': '2026-10', 'as_of': '2026-10-25'}, files={'transaction_file': ('unassigned.csv', content([row('SYN-UI', 'ACH CREDIT')]), 'text/csv')})
        assert response.status_code == 200
        assert 'Transactions needing a property' in response.text
        assert 'No configured phrase matched' in response.text
        assert 'SYN-UI' in client.get('/report?period=2026-10&as_of=2026-10-25').text
        assert 'SYN-UI' in client.get('/report.md?period=2026-10&as_of=2026-10-25').text
        with connect() as connection:
            intake_id = unresolved_rows(connection)[0]['id']
        url = '/reconciliation/assignments/{}'.format(intake_id)
        form = {'property_id': 2, 'notes': 'Fictional receipt confirmed', 'period': '2026-10', 'as_of': '2026-10-25'}
        rejected = client.post(url, data=form)
        assert rejected.status_code == 409
        assert 'Fictional receipt confirmed' in rejected.text
        form['acknowledge'] = 'true'
        accepted = client.post(url, data=form)
        assert accepted.status_code == 200
        assert 'Property assigned. No payment was recorded' in accepted.text
        assert 'Fictional receipt confirmed' in accepted.text
        assert client.post(url, data=form).status_code == 409


def test_existing_assignments_and_approvals_survive_schema_upgrade(database):
    obligation_id, _ = create_obligation(2, '2026-10')
    # Simulate the original schema's imported transaction, without new assignment metadata.
    with connect() as connection:
        import_id = connection.execute("INSERT INTO imports(filename,content_digest,row_count,imported_count,skipped_count,status) VALUES ('old.csv','old',1,1,0,'imported')").lastrowid
        tx_id = connection.execute("INSERT INTO transactions(external_id,import_id,source_row,property_id,account_label,posted_date,description,amount_cents) VALUES ('SYN-HISTORY',?,2,2,'Beacon Industrial operating','2026-10-05','Historical fictional rent',320000)", (import_id,)).lastrowid
    approve_payment(tx_id, obligation_id, '2026-10', '2026-10-25', notes='Approved fictional historical evidence', acknowledge=True)
    initialize()
    assert import_csv('repeat-history.csv', content([row('SYN-HISTORY', 'Historical fictional rent')]))['skipped'] == 1
    with connect() as connection:
        assert connection.execute('SELECT count(*) FROM payment_allocations').fetchone()[0] == 1
        assert connection.execute('SELECT count(*) FROM transactions').fetchone()[0] == 1
