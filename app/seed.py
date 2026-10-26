"""Pre-reviewed fictional base terms; the Orchard amendment is a source only."""

import json

from app.db import ROOT

PROPERTIES = [
    (1, "Orchard Row Retail", "Willow & Pine Outfitters LLC", "Orchard Row operating",
     "orchard-row-lease.txt", "2023-12-15", "2024-01-01", 480000, 1, None,
     "3. BASE RENT AND PAYMENT", "Tenant will pay monthly base rent of $4,800.00.",
     "Base rent is due in advance on the first calendar day of each month."),
    (2, "Beacon Industrial", "Tidepool Printworks Inc.", "Beacon Industrial operating",
     "beacon-industrial-lease.txt", "2022-08-01", "2022-09-01", 320000, 5, 5,
     "2. MONTHLY RENT", "Tenant will pay monthly base rent of $3,200.00, due on the fifth calendar day of each month.",
     "Tenant will pay monthly base rent of $3,200.00, due on the fifth calendar day of each month."),
    (3, "Juniper Market", "Mosaic Foods LLC", "Juniper Market operating",
     "juniper-market-lease.txt", "2024-02-01", "2024-03-01", 720000, 1, None,
     "2. BASE RENT", "Tenant will pay monthly base rent of $7,200.00 on the first calendar day of each month.",
     "Tenant will pay monthly base rent of $7,200.00 on the first calendar day of each month."),
]


def seed(connection):
    # Re-running init must not overwrite or supplement a working database.
    if connection.execute("SELECT count(*) FROM properties").fetchone()[0]:
        return
    for (property_id, name, tenant, account, filename, document_date, effective,
         cents, due_day, grace, section, rent_quote, due_quote) in PROPERTIES:
        connection.execute("INSERT INTO properties(id, name, tenant_name, account_label) VALUES (?, ?, ?, ?)",
                           (property_id, name, tenant, account))
        text = (ROOT / "sample-data" / "leases" / filename).read_text()
        document_id = connection.execute(
            "INSERT INTO lease_documents(property_id, filename, document_type, document_date, text_content) "
            "VALUES (?, ?, 'lease', ?, ?)", (property_id, filename, document_date, text)).lastrowid
        facts = [("monthly_base_rent", {"amount_cents": cents, "currency": "USD"}, section, rent_quote),
                 ("rent_due_day", {"day": due_day}, section, due_quote)]
        if grace is not None:
            facts.append(("grace_period", {"days": grace}, "3. GRACE PERIOD",
                          "Payment received within five calendar days after the due date is within the grace period."))
        for fact_type, value, fact_section, quote in facts:
            # Seed evidence must match the same source page shown in the interface.
            if quote not in text.split("--- Page 2 ---")[1].split("--- Page 3 ---")[0]:
                raise ValueError("Seed quotation does not match page 2: " + filename)
            fact_id = connection.execute(
                "INSERT INTO lease_facts(property_id, document_id, fact_type, value_json, effective_from, status) "
                "VALUES (?, ?, ?, ?, ?, 'approved')",
                (property_id, document_id, fact_type, json.dumps(value), effective)).lastrowid
            connection.execute("INSERT INTO fact_evidence(lease_fact_id, page, section, quote) VALUES (?, 2, ?, ?)",
                               (fact_id, fact_section, quote))
            connection.execute(
                "INSERT INTO review_decisions(record_type, record_id, decision, reviewer_label, notes) "
                "VALUES ('lease_fact', ?, 'approved', 'Demo seed', 'Pre-reviewed fictional base term for setup.')",
                (fact_id,))
    filename = "orchard-row-amendment.txt"
    connection.execute(
        "INSERT INTO lease_documents(property_id, filename, document_type, document_date, text_content) "
        "VALUES (1, ?, 'amendment', '2025-04-15', ?)",
        (filename, (ROOT / "sample-data" / "leases" / filename).read_text()))
