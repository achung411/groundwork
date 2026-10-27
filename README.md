# Groundwork

A local prototype for reviewing fictional commercial lease terms, reconciling rent transactions, and preparing follow-up with evidence and human approval.

Python/FastAPI serves HTML pages; SQLite preserves sources, effective terms, review decisions, payment allocations, and exception history. Lease extraction runs manually in a separate ChatGPT session. Matching, arithmetic, date checks, reports, and reminders use deterministic code. No model API credentials are needed.

## Run locally

Tested with Python 3.9.6 on macOS. From the repository folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The app starts with an empty database. To explicitly preload fictional examples instead, run `python -m app.db init` before starting the server. Sample documents and CSVs remain in `sample-data/` for manual upload.

Open [the local app](http://127.0.0.1:8000). Ctrl+C stops the server. In later sessions, activate `.venv` and run the Uvicorn command. `requirements.txt` contains runtime dependencies; `requirements-dev.txt` includes test tools.

Explicitly loading the samples adds three fictional properties, four source documents, and seven explicitly labeled pre-reviewed base terms. Orchard's rent amendment starts unapproved. Page visits never create obligations or record payments.

## Add a property from a lease

On Overview, click **Add property from a lease**. Enter the property/tenant names, source document date, and an optional phrase to match within transaction descriptions. Upload a selectable-text PDF or UTF-8 TXT file. The property and retained source are saved together, then the app opens lease review. No terms or obligations are automatically approved or created.

The same flow works on an empty database without running the sample seeding command. Existing property pages also offer **Add lease document** for a later lease or amendment. Uploads preserve the original bytes and a file fingerprint in the ignored local database; the source can be downloaded from the review screen. Repeated uploads do not overwrite records or create duplicates. Reference filenames distinguish files with the same original name on different properties; use the reference shown in the extraction prompt.

PDF/TXT intake allows up to 10 MB, 100 pages, and 500,000 extracted characters. Password-protected PDFs, scans/image-only or blank PDF pages, and DOCX are unsupported. Compare PDF-extracted text with the original before reviewing terms. TXT files without page markers become one source page; existing sequential page markers are preserved. On unnumbered pages the citation section is `Page text`; numbered pages still require an actual numbered heading. Use fictional leases only. [Harbor Court](sample-data/leases/harbor-court-lease.txt) is an unnumbered example for trying this flow.

## Preload historical transactions

Use [transactions-history.csv](sample-data/transactions-history.csv) for eight sample transactions across August and September 2026 ($30,900 total), leaving October and the edge-case CSVs for later imports. First add/review the sample properties and lease terms, including Orchard's rent amendment. Import history once through Reconciliation; switch the rent month between August and September to see each month's four rows. Create monthly rent obligations and approve payments separately to populate the property ledgers; importing credits never records rent automatically.

Follow the [historical preload instructions](sample-data/README.md#historical-preload-august-and-september-2026) for the exact sequence, expected balances, unresolved credits, and duplicate behavior. This is an optional preparation step; ordinary startup still leaves an empty database empty.

## Demonstrate the workflow

Follow [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md) for an isolated walkthrough, expected balances, and edge cases.

1. **Lease review:** copy the complete extraction prompt into ChatGPT. Paste just its JSON object into the app; review citations, effective dates, and uncertainty before approving. The reusable [skill](skills/lease-extraction/SKILL.md), [response contract](skills/lease-extraction/contract.md), and [JSON Schema](skills/lease-extraction/schema.json) are included. The copyable prompt works without installing the repository skill into ChatGPT.
2. **Reconciliation:** select October 2026 and an explicit review date, create obligations from approved terms, and import the [fictional CSV](sample-data/transactions-2026-10.csv). Full-payment proposals require approval. Partial payments and ambiguous credits require an explicit target and evidence note.
3. **Needs Attention:** calculate due/grace and lease-date items from approved records. Optional fictional examples stage Beacon's date/option proposals; approving them and a cited exercise event demonstrates an open notice window and exhausted options.
4. **Report:** review approved balances, pending credits, citations, assumptions, exceptions, and next steps. Download the Markdown brief or copy an unsent reminder to edit outside the app.

Read [sample-data/README.md](sample-data/README.md) for fixture purposes. Use only fictional records.

Finish with the **Best Burger PDF intake scenario**: add the partial synthetic base lease and its same-date rent addendum as a new property after testing transaction processing. This demonstrates retained evidence and missing/unsupported terms while leaving expected rent unestablished. Keep both PDFs as supplied; no OCR repair or formula-based rent calculation is needed. Follow [walkthrough step 8](DEMO_WALKTHROUGH.md#8-add-best-burger-and-demonstrate-documentation-gaps) and the [fixture notes](sample-data/README.md#best-burger-realistic-pdf-intake-and-documentation-gaps).

## Persistence and reset

The ignored runtime database is `data/property-operations.sqlite3`. Startup creates missing tables without seeding or replacing records. `python -m app.db init` seeds only an empty property table. `PROPERTY_DB_PATH` selects a separate database for tests or rehearsal; the walkthrough shows how to preserve your working demo.

To deliberately empty the selected database without reloading samples, stop its server, confirm the intended `PROPERTY_DB_PATH`, then run:

```sh
python -m app.db clear --confirm
```

To discard current records and reload the fictional sample properties and lease facts instead:

```sh
python -m app.db reset --confirm
```

There is no browser reset button. Source documents, approved prior terms, decisions, and resolved issues remain available during ordinary use.

## Verification

```sh
python -m pytest -q
python -m pip check
```

The suite uses temporary databases. It covers consequential state transitions and boundaries, including a complete HTTP rehearsal through amendment approval, CSV upload, full/partial payments, later resolution, reviewed option exercise, Markdown export, and restart. See [EVALUATION.md](EVALUATION.md) for observed results, time records, and verification limits.

## Scope and limits

One active lease per property, USD base rent only. Posted date stands in for receipt. Unknown grace is never zero by assumption. Unallocated credits are not recorded payments; the selected review date filters posted evidence, not historical reviewer knowledge.

Amendments affect new obligations; existing obligation values/evidence are retained. Mid-month changes, proration, deposit splitting, overpayments, reversals, and notice-window waivers require additional work. An option exercise does not establish extension rent. Missing terms stay visible for review.

This is a fictional-data prototype: no authentication, production safeguards, real bank access, message sending, cloud deployment, or background scheduler. No measured business benefit or production-readiness claim is made.

The [product brief](PRODUCT_BRIEF.md), [technical design](TECHNICAL_DESIGN.md), and [implementation plan](IMPLEMENTATION_PLAN.md) explain the decisions and completed slices.

### Configure transaction labels

Open a property and choose **Configure transaction labels** to edit its primary description phrase and aliases (one per line). Use distinctive tenant names or payment references. Phrases match case-insensitive substrings of `description`, with no AI, regex, fuzzy scoring, or amount-based property identification. Multiple phrases for one property count as one candidate. A unique property is assigned automatically; no match or multiple matching properties leave the row in **Transactions needing a property**, where you select a property, explain the evidence, and confirm. Assignment does not approve rent payments. Changing phrases never reassigns imported rows. Retired phrases remain reserved to the original property but no longer match new rows.

CSV columns are now exactly `transaction_id,posted_date,description,amount` (any order). There is no `account_label` column. Each transaction ID must be unique across the imported feed, including across properties. Identical source details are skipped on re-import, while changed details reject the file. Keep bank reference IDs stable; independent bank feeds that reuse IDs need distinct identifiers. Existing historical assignments and payment approvals are preserved. The monthly brief also lists rows awaiting property assignment.

### Property rent ledgers

Choose **View rent ledger** on an overview property card or property page. Each property has its own chronological ledger of saved rent charges and approved payments, with the rent month, due date, received date (bank posted date), charged/received amounts, source reference, and running balance owed. Charges enter on their due dates; payments enter on posted dates. Partial payments and payments toward older rent remain separate entries. The through-date control excludes later charges/payments; early payments can create a temporary credit. Imported credits awaiting approval are shown separately and never reduce the balance. Scheduled obligations are listed outside the balance. The view is read-only and starts at zero before the first saved entry: it does not generate missing monthly obligations or infer an opening balance, fees, or other charges.
