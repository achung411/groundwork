import io
import json

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.db import ROOT, connect, initialize
from app.main import app
from app.services.document_intake import IntakeError, MAX_DOCUMENT_BYTES, add_document, create_property, parse_document
from app.services.extraction_import import ReviewError, stage_proposal


def lease_bytes():
    return (ROOT / 'sample-data/leases/harbor-court-lease.txt').read_bytes()


def create(name='Harbor Court', account=''):
    return create_property(name, 'Cove Studio LLC', account, '2025-12-15', 'lease.txt', lease_bytes())


def pdf_bytes(pages, encrypted=False):
    """Small in-memory fictional PDFs for parser integration, not deliverable documents."""
    writer = PdfWriter()
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        if text:
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
            stream = DecodedStreamObject()
            stream.set_data(('BT /F1 12 Tf 72 720 Td (' + text + ') Tj ET').encode('ascii'))
            page[NameObject('/Contents')] = writer._add_object(stream)
    if encrypted:
        writer.encrypt('fictional-test-password')
    result = io.BytesIO()
    writer.write(result)
    return result.getvalue()


def test_new_property_retains_source_and_requires_fact_review(database):
    property_id, document_id, created = create()
    assert created
    with connect() as connection:
        property_record = connection.execute('SELECT * FROM properties WHERE id=?', (property_id,)).fetchone()
        source = connection.execute('SELECT * FROM lease_documents WHERE id=?', (document_id,)).fetchone()
        upload = connection.execute('SELECT * FROM document_uploads WHERE document_id=?', (document_id,)).fetchone()
        assert property_record['account_label'] == 'Harbor Court operating'
        assert source['text_content'].startswith('--- Page 1 ---')
        assert upload['original_bytes'] == lease_bytes()
        assert upload['original_filename'] == 'lease.txt'
        assert connection.execute('SELECT count(*) FROM lease_facts WHERE property_id=?', (property_id,)).fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM rent_obligations WHERE property_id=?', (property_id,)).fetchone()[0] == 0
    payload = {'schema_version': '1.0', 'document_filename': source['filename'], 'facts': [{
        'fact_type': 'monthly_base_rent', 'value': {'amount': '2100.00', 'currency': 'USD'},
        'effective_from': '2026-01-01', 'status': 'proposed',
        'evidence': [{'page': 1, 'section': 'Page text', 'quote': 'Beginning January 1, 2026, monthly base rent is $2,100.00, due on the first calendar day of each month.'}]}]}
    assert stage_proposal(property_id, document_id, json.dumps(payload)) == (1, 0)
    initialize()
    with TestClient(app) as client:
        assert 'Harbor Court' in client.get('/').text
        assert 'No lease terms approved yet' in client.get('/properties/{}'.format(property_id)).text
        assert 'Pending review' in client.get('/properties/{}/lease-review'.format(property_id)).text
        original = client.get('/properties/{}/documents/{}/original'.format(property_id, document_id))
        assert original.content == lease_bytes()
        assert 'attachment' in original.headers['content-disposition']
        assert client.get('/properties/1/documents/{}/original'.format(document_id)).status_code == 404


def test_duplicate_creation_and_uploads_do_not_overwrite_or_add_records(database):
    property_id, document_id, _ = create()
    assert create() == (property_id, document_id, False)
    assert add_document(property_id, '2025-12-15', 'lease', 'renamed.txt', lease_bytes()) == (document_id, False)
    with pytest.raises(IntakeError, match='different document date'):
        add_document(property_id, '2026-01-01', 'amendment', 'renamed.txt', lease_bytes())
    with pytest.raises(IntakeError, match='already used'):
        create_property('Different property', 'Other fictional tenant', 'harbor court OPERATING', '2025-12-15', 'lease.txt', lease_bytes())
    other_property, other_document, _ = create('Other Fictional Court')
    with connect() as connection:
        names = [row[0] for row in connection.execute('SELECT filename FROM lease_documents WHERE id IN (?,?)', (document_id, other_document))]
        assert len(set(names)) == 2
        assert connection.execute('SELECT count(*) FROM properties').fetchone()[0] == 5
    amendment_id, added = add_document(property_id, '2026-01-01', 'amendment', 'lease.txt', b'Fictional amendment: no terms approved yet.')
    assert added and amendment_id != document_id
    assert other_property != property_id


def test_pdf_pages_original_bytes_and_text_are_preserved(database):
    content = pdf_bytes(['FICTIONAL LEASE', 'Monthly base rent is 2100 USD.'])
    parsed = parse_document('lease.PDF', content)
    assert parsed['page_count'] == 2
    assert '--- Page 1 ---\n\nFICTIONAL LEASE' in parsed['text_content']
    assert '--- Page 2 ---\n\nMonthly base rent is 2100 USD.' in parsed['text_content']
    assert parsed['original_bytes'] == content
    property_id, document_id, _ = create_property('PDF Court', 'Fictional tenant', '', '2025-12-15', 'lease.pdf', content)
    with TestClient(app) as client:
        response = client.get('/properties/{}/documents/{}/original'.format(property_id, document_id))
        assert response.content == content and response.headers['content-type'] == 'application/pdf'


@pytest.mark.parametrize('filename,content', [
    ('lease.docx', b'fictional'), ('lease.txt', b''), ('lease.txt', b'\xff\xfe'),
    ('lease.txt', b'abc\x00def'), ('lease.pdf', b'not a pdf'), ('lease.pdf', b'%PDF-1.7\nmalformed'),
    ('lease.txt', b'--- Page 1 ---\nRent\n--- Page 1 ---\nOther'),
    ('lease.txt', b'--- Page 2 ---\nRent'), ('lease.txt', b'--- Page 1 ---\n\n'),
    ('lease.txt', b'%PDF-1.7\nnot plain lease text'),
])
def test_invalid_documents_leave_no_orphan_property(database, filename, content):
    with pytest.raises(IntakeError):
        create_property('Invalid Court', 'Fictional tenant', '', '2025-12-15', filename, content)
    with connect() as connection:
        assert connection.execute('SELECT count(*) FROM properties').fetchone()[0] == 3
        assert connection.execute('SELECT count(*) FROM document_uploads').fetchone()[0] == 0


def test_scanned_blank_encrypted_and_oversized_documents_are_rejected():
    with pytest.raises(IntakeError, match='no extractable text'):
        parse_document('scan.pdf', pdf_bytes(['']))
    with pytest.raises(IntakeError, match='Password-protected'):
        parse_document('protected.pdf', pdf_bytes(['Fictional'], encrypted=True))
    with pytest.raises(IntakeError, match='10 MB'):
        parse_document('large.txt', b'x' * (MAX_DOCUMENT_BYTES + 1))
    with pytest.raises(IntakeError, match='500,000'):
        parse_document('large.txt', b'x' * 500001)


def test_page_text_fallback_cannot_bypass_numbered_section_validation(database):
    with connect() as connection:
        doc = connection.execute("SELECT * FROM lease_documents WHERE filename='beacon-industrial-lease.txt'").fetchone()
    payload = {'schema_version': '1.0', 'document_filename': doc['filename'], 'facts': [{
        'fact_type': 'monthly_base_rent', 'value': {'amount': '3200.00', 'currency': 'USD'}, 'status': 'proposed',
        'effective_from': '2022-09-01', 'evidence': [{'page': 2, 'section': 'Page text',
        'quote': 'Tenant will pay monthly base rent of $3,200.00, due on the fifth calendar day of each month.'}]}]}
    with pytest.raises(ReviewError, match='Section'):
        stage_proposal(2, doc['id'], json.dumps(payload))


def test_http_creation_errors_reset_and_existing_property_upload(database):
    with TestClient(app) as client:
        assert client.get('/properties/new').status_code == 200
        form = {'name': 'Harbor Court', 'tenant_name': 'Cove Studio LLC', 'account_label': '', 'document_date': '2025-12-15'}
        invalid = client.post('/properties/new', data={**form, 'document_date': 'bad'}, files={'lease_file': ('lease.txt', lease_bytes(), 'text/plain')})
        assert invalid.status_code == 422 and 'Harbor Court' in invalid.text
        result = client.post('/properties/new', data=form, files={'lease_file': ('lease.txt', lease_bytes(), 'text/plain')})
        assert result.status_code == 200 and 'Property and lease source added' in result.text
        property_id = int(str(result.url).split('/properties/')[1].split('/')[0])
        assert client.get('/properties/{}/documents/new'.format(property_id)).status_code == 200
        added = client.post('/properties/{}/documents/new'.format(property_id), data={'document_date': '2026-01-01', 'document_type': 'amendment'}, files={'lease_file': ('amendment.txt', b'Fictional change proposed for review.', 'text/plain')})
        assert added.status_code == 200 and 'Source document added' in added.text
    # Reset must remove retained originals before deleting their source documents.
    import subprocess
    import sys
    reset = subprocess.run([sys.executable, '-m', 'app.db', 'reset', '--confirm'], cwd=ROOT, capture_output=True, text=True)
    assert reset.returncode == 0, reset.stderr


def test_uploaded_property_can_establish_rent_and_match_its_own_account(database):
    property_id, document_id, _ = create()
    with connect() as connection:
        source = connection.execute('SELECT * FROM lease_documents WHERE id=?', (document_id,)).fetchone()
    passage = 'Beginning January 1, 2026, monthly base rent is $2,100.00, due on the first calendar day of each month.'
    facts = [{'fact_type': kind, 'value': value, 'effective_from': '2026-01-01', 'status': 'proposed',
              'evidence': [{'page': 1, 'section': 'Page text', 'quote': passage}]}
             for kind, value in [('monthly_base_rent', {'amount': '2100.00', 'currency': 'USD'}), ('rent_due_day', {'day': 1})]]
    with TestClient(app) as client:
        staged = client.post('/properties/{}/lease-review'.format(property_id), data={
            'document_id': document_id, 'proposal_json': json.dumps({'schema_version': '1.0', 'document_filename': source['filename'], 'facts': facts})})
        assert staged.status_code == 200
        with connect() as connection:
            pending = connection.execute("SELECT id FROM lease_facts WHERE property_id=? AND status='proposed'", (property_id,)).fetchall()
        for fact in pending:
            assert client.post('/properties/{}/facts/{}/review'.format(property_id, fact['id']), data={'decision': 'approved', 'acknowledge': 'true'}).status_code == 200
        review = {'period': '2026-10', 'as_of': '2026-10-25'}
        assert client.post('/reconciliation/obligations', data={**review, 'property_id': property_id}).status_code == 200
        csv = b'transaction_id,posted_date,description,amount\nSYN-HARBOR-001,2026-10-01,COVE STUDIO OCT RENT | Harbor Court operating,2100.00\n'
        assert client.post('/reconciliation/import', data=review, files={'transaction_file': ('harbor.csv', csv, 'text/csv')}).status_code == 200
        assert client.post('/reconciliation/matching', data=review).status_code == 200
    with connect() as connection:
        obligation = connection.execute('SELECT * FROM rent_obligations WHERE property_id=?', (property_id,)).fetchone()
        assert obligation['amount_cents'] == 210000 and obligation['grace_days'] is None
        assert connection.execute('SELECT count(*) FROM match_proposals WHERE obligation_id=?', (obligation['id'],)).fetchone()[0] == 1
        assert connection.execute('SELECT count(*) FROM payment_allocations').fetchone()[0] == 0


def test_intake_works_without_loading_seed_documents(tmp_path, monkeypatch):
    monkeypatch.setenv('PROPERTY_DB_PATH', str(tmp_path / 'empty.sqlite3'))
    with TestClient(app) as client:
        assert 'No demo properties yet' in client.get('/').text
        result = client.post('/properties/new', data={'name': 'Harbor Court', 'tenant_name': 'Cove Studio LLC', 'document_date': '2025-12-15'},
                             files={'lease_file': ('lease.txt', lease_bytes(), 'text/plain')})
        assert result.status_code == 200
    with connect() as connection:
        assert connection.execute('SELECT count(*) FROM properties').fetchone()[0] == 1
        assert connection.execute('SELECT count(*) FROM lease_facts').fetchone()[0] == 0


def test_inline_numbered_rent_clause_is_citable(database):
    heading = '1. RENT: Monthly base rent is $2,100.00.'
    property_id, document_id, _ = create_property('Inline Court', 'Fictional tenant', '', '2025-12-15', 'inline.txt', heading.encode())
    with connect() as connection:
        filename = connection.execute('SELECT filename FROM lease_documents WHERE id=?', (document_id,)).fetchone()[0]
    payload = {'schema_version': '1.0', 'document_filename': filename, 'facts': [{
        'fact_type': 'monthly_base_rent', 'value': {'amount': '2100.00', 'currency': 'USD'},
        'effective_from': None, 'uncertainty': 'Effective date is not established.', 'status': 'proposed',
        'evidence': [{'page': 1, 'section': heading, 'quote': 'Monthly base rent is $2,100.00.'}]}]}
    assert stage_proposal(property_id, document_id, json.dumps(payload)) == (1, 0)
