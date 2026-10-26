"""Property/document intake with retained originals and no automatic term approvals."""

import hashlib
import io
import re
from pathlib import PurePosixPath

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.services.account_labels import owners, normalize
from app.db import connect
from app.services.payments import review_date

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_DOCUMENT_PAGES = 100
MAX_SOURCE_CHARACTERS = 500000


class IntakeError(ValueError):
    pass


def text_field(value, label, limit=160):
    value = value.strip()
    if not value or len(value) > limit or any(ord(c) < 32 for c in value):
        raise IntakeError("{} must be 1–{} characters without control characters.".format(label, limit))
    return value


def parse_document(filename, content):
    filename = text_field(PurePosixPath((filename or "").replace("\\", "/")).name, "Filename")
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix not in (".pdf", ".txt"):
        raise IntakeError("Upload a PDF with selectable text or a UTF-8 TXT file. DOCX and scanned-image OCR are not supported.")
    if not content or len(content) > MAX_DOCUMENT_BYTES:
        raise IntakeError("Choose a nonempty file up to 10 MB.")
    if suffix == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise IntakeError("The selected file is not a readable PDF.")
        try:
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted:
                raise IntakeError("Password-protected PDFs are not supported. Use an unencrypted fictional copy.")
            if not 1 <= len(reader.pages) <= MAX_DOCUMENT_PAGES:
                raise IntakeError("PDFs must contain 1–100 pages.")
            pages = []
            for number, page in enumerate(reader.pages, 1):
                text = (page.extract_text() or "").strip()
                if not text:
                    raise IntakeError("PDF page {} has no extractable text. Scanned/image-only or blank pages are not supported; use a text PDF or a reviewed TXT transcription.".format(number))
                pages.append("--- Page {} ---\n\n{}".format(number, text))
                if sum(len(part) for part in pages) > MAX_SOURCE_CHARACTERS:
                    raise IntakeError("Extracted text exceeds the 500,000-character limit.")
            source = "\n\n".join(pages)
        except IntakeError:
            raise
        except (PdfReadError, ValueError, TypeError, KeyError, IndexError, NotImplementedError, RecursionError) as error:
            raise IntakeError("The PDF could not be read. Use a text PDF or a UTF-8 TXT transcription.") from error
        content_type = "application/pdf"
        page_count = len(pages)
    else:
        if content.startswith(b"%PDF-"):
            raise IntakeError("This appears to be a PDF named as TXT. Upload it with its .pdf extension so its text can be extracted correctly.")
        try:
            source = content.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n").strip()
        except UnicodeDecodeError as error:
            raise IntakeError("TXT files must use UTF-8 encoding.") from error
        if not source or any(ord(c) < 32 and c not in "\n\t" for c in source):
            raise IntakeError("The TXT file contains no readable text or contains binary/control characters.")
        if len(source) > MAX_SOURCE_CHARACTERS:
            raise IntakeError("Text exceeds the 500,000-character limit.")
        markers = list(re.finditer(r"(?m)^--- Page ([0-9]+) ---\s*$", source))
        if markers:
            if [int(marker.group(1)) for marker in markers] != list(range(1, len(markers) + 1)):
                raise IntakeError("TXT page markers must be unique and sequential, starting at --- Page 1 ---. Correct the file before uploading.")
            for index, marker in enumerate(markers):
                end = markers[index + 1].start() if index + 1 < len(markers) else len(source)
                if not source[marker.end():end].strip():
                    raise IntakeError("Each marked TXT page must contain source text.")
            page_count = len(markers)
        else:
            source = "--- Page 1 ---\n\n" + source
            page_count = 1
        if page_count > MAX_DOCUMENT_PAGES:
            raise IntakeError("TXT files must contain no more than 100 marked pages.")
        content_type = "text/plain"
    return {"original_filename": filename, "content_type": content_type, "content_digest": hashlib.sha256(content).hexdigest(),
            "original_bytes": content, "text_content": source, "page_count": page_count}


def validate_date(value):
    try:
        return review_date(value)
    except ValueError as error:
        raise IntakeError("Enter the source document's date in YYYY-MM-DD format; it is not an inferred rent effective date.") from error


def insert_document(connection, property_id, document, document_date, document_type):
    existing = connection.execute(
        "SELECT d.* FROM document_uploads u JOIN lease_documents d ON d.id=u.document_id WHERE d.property_id=? AND u.content_digest=?",
        (property_id, document["content_digest"])).fetchone()
    if existing:
        if existing["document_date"] != document_date or existing["document_type"] != document_type:
            raise IntakeError("This file already exists for the property with a different document date or type. Its existing record was not changed.")
        return existing["id"], False
    # References are unique even when different properties upload files named lease.pdf.
    original = PurePosixPath(document["original_filename"])
    base = "Property {} - {}".format(property_id, original.name)
    reference, counter = base, 2
    while connection.execute("SELECT 1 FROM lease_documents WHERE filename=?", (reference,)).fetchone():
        reference = "Property {} - {} ({}){}".format(property_id, original.stem, counter, original.suffix)
        counter += 1
    document_id = connection.execute(
        "INSERT INTO lease_documents(property_id, filename, document_type, document_date, text_content) VALUES (?, ?, ?, ?, ?)",
        (property_id, reference, document_type, document_date, document["text_content"])).lastrowid
    connection.execute(
        "INSERT INTO document_uploads(document_id, original_filename, content_type, content_digest, original_bytes, page_count) VALUES (?, ?, ?, ?, ?, ?)",
        (document_id, document["original_filename"], document["content_type"], document["content_digest"], document["original_bytes"], document["page_count"]))
    return document_id, True


def create_property(name, tenant_name, account_label, document_date, filename, content):
    name = text_field(name, "Property name")
    tenant_name = text_field(tenant_name, "Tenant name")
    account_label = text_field(account_label or name + " operating", "Account label")
    document_date = validate_date(document_date)
    document = parse_document(filename, content)
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        owner_id = owners(connection, historical=True).get(normalize(account_label))
        existing = connection.execute("SELECT * FROM properties WHERE id=?", (owner_id,)).fetchone()
        if existing:
            identical = connection.execute(
                "SELECT d.id FROM lease_documents d JOIN document_uploads u ON u.document_id=d.id "
                "WHERE d.property_id=? AND d.document_type='lease' AND d.document_date=? AND u.content_digest=?",
                (existing["id"], document_date, document["content_digest"])).fetchone()
            if identical and existing["name"] == name and existing["tenant_name"] == tenant_name:
                return existing["id"], identical["id"], False
            raise IntakeError("That account label is already used. Choose a distinct fictional label, or add the document to the existing property.")
        property_id = connection.execute("INSERT INTO properties(name, tenant_name, account_label) VALUES (?, ?, ?)", (name, tenant_name, account_label)).lastrowid
        document_id, _ = insert_document(connection, property_id, document, document_date, "lease")
        return property_id, document_id, True


def add_document(property_id, document_date, document_type, filename, content):
    document_date = validate_date(document_date)
    if document_type not in ("lease", "amendment"):
        raise IntakeError("Choose lease or amendment as the document type.")
    document = parse_document(filename, content)
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if not connection.execute("SELECT 1 FROM properties WHERE id=?", (property_id,)).fetchone():
            raise IntakeError("Property not found.")
        return insert_document(connection, property_id, document, document_date, document_type)
