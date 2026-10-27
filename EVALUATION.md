# Build log and observed checks

## Final verification summary

**Latest extension:** property/document intake regression suite passes **137 tests**. The original six-slice clean-environment result below was 118 tests; the additional intake verification is recorded at the end of this log.

All six build slices are complete. A newly created virtual environment installed the documented requirements, initialized a separate database, and passed **118 tests** and `pip check` on Python 3.9.6/macOS. The skill metadata validator and repository whitespace checks also passed. Runtime databases, rehearsal exports, environment files, and virtual environments remain ignored by Git.

| Area | Observed result |
|---|---|
| Lease proposal validation, evidence, approval, and prior terms | Passed service/HTTP tests and earlier browser review |
| CSV validation, atomic rollback, duplicate/conflict handling | Passed multipart HTTP tests, including the complete rehearsal |
| Full/partial approvals and concurrency guards | Passed tests; supported payments and later resolution also exercised in the browser |
| Persistent exceptions and later payment | Complete rehearsal reached $15,450 approved / $0 remaining; unidentified $4,200 credit stayed open |
| Grace and lease notice/exercise dates | Passed boundary tests and browser exercise walkthrough; no inferred fee or extension rent |
| Monthly brief, source evidence, Markdown artifact, neutral drafts | Passed HTTP/content checks and browser report/copy review |
| Restart persistence | Passed repeated app lifecycles and a separate clean-environment server startup on the persisted rehearsal database |
| Live ChatGPT extraction quality | Not benchmarked; automated tests use hand-authored expected proposals, not observed model outputs |
| Automated browser CSV file selection | Earlier tool limitation remains; HTTP uploads passed and the main app contains the user's imported fixture |

The detailed per-slice records below are historical checkpoints. The implementation/verification durations exclude unmeasured prior planning and between-slice user review; they must not be presented as total project effort or a complete measure of demo preparation time.

## Slice 1 — Running foundation

**Date:** October 25, 2026 (America/Los_Angeles).

**Elapsed implementation and verification:** Approximately 3 minutes, starting at 4:20 p.m. Earlier product discovery and planning are separate activities; their duration was not measured in this log.

Delivered a local FastAPI application with a portfolio overview, property records, SQLite storage, source document text, seven pre-reviewed fictional facts with quotations and approval history, and explicit initialize/reset commands. Orchard's amendment is retained as source material without an approved rent change. Ordinary startup never reseeds records.

### Observed verification

- `python -m pytest -q`: **5 passed**, using temporary databases. Checks cover setup reruns and two app startup/shutdown cycles preserving changed records; quotation and review-history integrity; foreign-key enforcement; page rendering and missing-property handling; explicit reset confirmation and reseeding; empty startup without automatic seeding.
- `python -m pip check`: no broken requirements.
- `git diff --check`: passed.
- Started Uvicorn on `127.0.0.1:8000` and inspected the overview and Orchard property page in the in-app browser. Verified visible $4,800 base rent, source quotation, effective date, and amendment notice; expanded the amendment to inspect its full stored text. The layout was inspected at the browser panel's approximately 670-pixel width.
- Verified with Python 3.9.6 and the direct dependency versions pinned in the requirements files.

The environment required network permission for package installation and local-server permission to bind the loopback port. Both succeeded. No runtime API credentials are used.

### Current limits and review handoff

This slice does not yet include lease extraction/paste review, manual fact entry, monthly obligations, transaction imports, payment allocation, attention rules, or reports. No future-slice acceptance criteria have been marked passed. The seed's approval history is explicitly labeled “Demo seed”; it is setup data, not evidence of a live model extraction or user approval.

For user review: open the local app, inspect all three properties and the source documents, and confirm the initial terms are understandable. Slice 2 has not started.

## Slice 2 — Lease extraction and review

**Date:** October 25, 2026 (America/Los_Angeles).

**Elapsed implementation and verification:** Approximately 7 minutes, starting around 4:30 p.m. Cumulative recorded build time across slices 1–2 is approximately 10 minutes; prior planning and the user's between-slice review are not measured here.

Delivered the reusable `skills/lease-extraction/SKILL.md`, a versioned response contract and generated JSON Schema, copyable prompt with the selected source text, JSON paste validation, pending facts, per-fact approval/rejection, correction by resubmission, source quotations, uncertainty acknowledgement, and amendment history. Startup adds the submission table without resetting slice 1 data. JSON is also the manual-entry interface; there is no separate guided term editor.

### Observed verification

- `python -m pytest -q`: **30 passed**, including the five foundation checks. New checks exercise invalid envelopes and values, unsupported types, duplicate JSON keys, wrong page/section/quote, all-or-nothing staging, property/source identity, duplicate submissions, unknown dates, evidence revalidation, per-fact decisions, repeated decisions, conflicting starts, and explicit amendment replacement with prior-value history.
- Skill-creator `quick_validate.py`: **Skill is valid!** Installed its PyYAML dependency and pinned it in development requirements.
- `python -m pip check`: no broken requirements. `git diff --check`: passed.
- Browser test on a separate SQLite database and port 8001: pasted an incomplete response and saw validation errors with text retained; pasted an evidence-backed Orchard proposal and saw it remain pending; added a note about unestablished execution, acknowledged evidence and replacement, and approved it. The property page then showed $5,050 from July 1, 2025, the original $4,800 through June 30, 2025, both sources, and the supersession decision.
- Restarted the main app on port 8000 without clearing its records. Verified its Orchard amendment remains unsubmitted for user review. Opened the live handoff screen and confirmed the copy button displays its successful-copy status.
- Closed the isolated browser test and stopped its server. The main app remains running for the user's review.

### Limits and next review

The browser test used a proposal authored during development, not an extraction performed in the user's separate ChatGPT session. That live manual handoff remains the user's next review step. The prompt contains a format example from a different invented source; it does not embed a precomputed answer for the demo packet. Metadata/schema validation and the integration checks do not establish model extraction quality.

Quote verification proves only text location after whitespace normalization, not semantic correctness or legal validity. Unknown effective dates must be corrected before approval. Replacement supports one earlier term and the same end boundary; temporary overrides and retroactive changes to existing obligations remain outside scope. Existing obligation/payment behavior will be evaluated when those entities are introduced in later slices.

Slice 3 has not started. For review, copy the prompt from Orchard's lease-review screen into a separate ChatGPT session, paste only its JSON response back into the app, and review the amendment evidence and uncertainty before approval.

## Slice 3 — Monthly obligations and CSV intake

**Date:** October 25, 2026 (America/Los_Angeles).

**Elapsed implementation and verification:** Approximately 22 minutes, starting around 4:46 p.m. This includes approximately 14.6 minutes spent waiting on a browser file-chooser tool call. Cumulative recorded implementation/verification time across slices 1–3 is approximately 32 minutes; prior planning and user review between slices are not measured here.

Delivered a month-based reconciliation workspace, explicit per-property obligation creation, retained approved-term values/evidence/assumptions, import history, CSV upload validation, account-scoped duplicate/conflict handling, and transaction lists filtered by posted month. Added three fictional fixtures for a follow-up run, invalid rows, and conflicting identifiers. Matching and payment allocations have not been implemented.

### Observed verification

- `python -m pytest -q`: **69 passed**, including prior-slice checks. New coverage includes approved effective terms and historical amounts, pending amendment gates, unique property/month obligations, snapshots surviving later term changes, unknown grace, invalid months, leap February, unsupported due days, mid-month changes, known expiration, HTTP creation/upload, restart/setup persistence, populated reset, raw-file duplicates, overlapping files, within-file duplicates, account-scoped identifiers, conflict rollback, malformed files, BOM/reordered headers, exact cents, and the file-size limit.
- `python -m pip check`: no broken requirements. `git diff --check`: passed.
- Browser testing used an isolated SQLite copy of the fictional main demo records. It successfully created October obligations of $5,050, $3,200, and $7,200, totaling $15,450. Missing approved lease boundaries appeared as assumptions; unknown grace was not converted to zero. A screenshot records the created-obligation summary.
- **Browser upload check remains incomplete.** The automated browser file-chooser API returned without attaching a file (the file input remained empty). An attempted native-picker fallback was unavailable because the computer-use tool disallows controlling the Codex app. HTTP multipart uploads passed through FastAPI's test client, including actual fixture bytes and repeated imports, but this does not substitute for a successful interactive browser file selection. No successful browser CSV upload is claimed.
- Restarted the main app with additive schema initialization and preserved the user's approved Orchard amendment. Main data has no slice 3 obligations or imports created by these checks. Left the October workspace open for user review; closed the isolated tab and stopped its server.

### Limits and next review

Please create October's obligations in the main workspace, select `sample-data/transactions-2026-10.csv` using the browser's file picker, and import it. Expect four added transactions; repeat the import and expect zero added and four skipped. Try the invalid-row fixture to check the all-or-nothing error display. This manual file-selection review is the remaining verification item for slice 3.

An unreviewed amendment blocks new obligations after its document date, even when its precise effective date has not yet been approved; this conservative gate is documented in the UI and README. Missing approved lease boundary dates remain visible assumptions. Mid-month changes, proration, and unsupported shorter-month rules require review rather than invented calculations. Importing transactions records evidence only and never records a rent payment. Slice 4 has not started.

## Slice 4 — Reconciliation and persistent memory

**Date:** October 25, 2026 (America/Los_Angeles).

**Elapsed implementation and verification:** Approximately 10 minutes, starting around 5:29 p.m. Cumulative recorded implementation/verification time across slices 1–4 is approximately 42 minutes; prior planning and between-slice user review are not measured here.

Delivered explicit full-payment matching runs, pending/approved/rejected/withdrawn proposals, reviewer decisions, manual allocation of entire deposits against one obligation, balances derived from approved allocations, review-date filtering, persistent exceptions and resolution events, and payment history with retained due/grace timing. Added a separate ambiguous-full-credit fixture. No slice 5 attention/report/reminder features were implemented.

### Observed verification

- `python -m pytest -q`: **89 passed**. New tests cover proposals leaving balances unchanged, repeat matching and page views, acknowledgement and reason requirements, full approval, retained late annotations, rejection persistence and later manual override, partial balance creation, later-payment resolution, unrelated-credit preservation, stale approval after competing evidence, withdrawal after partial allocation, earlier review dates, manual arrears and cross-property guards, concurrent duplicate approvals, due/grace boundaries, invalid dates, HTTP review forms, and reset with populated allocation/exception history.
- `python -m pip check`: no broken requirements. `git diff --check`: passed.
- Browser test on an isolated copy of fictional main records: ran matching and confirmed two pending full proposals with no recorded money; approved Orchard's $5,050 and Beacon's $3,200 payments; explicitly selected Juniper's October obligation, entered a reason, acknowledged, and approved its $3,000 partial payment. The interface showed $4,200 remaining and an open partial-payment issue.
- Loaded the follow-up CSV through the import service into the isolated database (one added, one skipped), avoiding the prior file-chooser automation limitation. The browser showed the October 28 transaction as after the October 25 review date. Advanced the review date, explicitly selected Juniper's remaining obligation, entered a reason, and approved its separate $4,200 remainder. The balance reached zero; the partial-payment issue retained opening and resolution events with linked decisions. The earlier unidentified credit remained open and unallocated. A screenshot records both issue states.
- Main records remained at three obligations, one import, four transactions, zero match proposals, and zero payment allocations after verification. Left the main October review open for user testing. Closed the isolated tab and stopped its server; main app remains running.

### Limits and next review

Each allocation consumes an entire deposit against one obligation. Deposit splitting, overpayment accounting, reversals, and allocation to later rent months are unsupported. Open earlier rent months can be selected manually. The review date filters posted transactions and totals but does not reconstruct historical reviewer knowledge; later-approved deposits remain reserved against reuse even when excluded from an earlier date's displayed totals. Posted date is the prototype's proxy for receipt, and no late fee is calculated.

The slice 3 browser file-chooser automation limitation was not independently retested or marked passed. Current main records contain the user's October import, and multipart intake continues to pass the HTTP integration checks.

For review: run matching in the main app, approve supported full payments, manually allocate Juniper's named partial payment, then use the separate follow-up file and later review date. Confirm the unidentified credit stays unresolved and inspect the retained decisions. Slice 5 has not started.

## Slice 5 — Attention, option review, monthly brief, and unsent drafts

**Date:** October 25, 2026 (America/Los_Angeles).

**Elapsed implementation and verification:** Approximately 16 minutes, starting around 6:08 p.m. Cumulative recorded implementation/verification time across slices 1–5 is approximately 58 minutes; prior planning and between-slice user review are not measured here.

Delivered read-only date-driven attention on the overview and a dedicated page, explicit review dates, approved due/grace labels, inclusive calendar notice windows, reviewed option-exercise events, optional fictional attention staging, and a monthly report with Markdown export and copyable unsent reminder drafts. The Beacon example demonstrates both an open notice window and exhausted options before/after a reviewed event, preserving the original base source instead of adding a fourth property. Report sections retain rent and lease-date source quotations, approved payment evidence, pending credits, uncertainty, assumptions, exception history, and next steps.

### Observed verification

- `python -m pytest -q`: **117 passed**. New coverage includes due/grace and unknown-grace boundaries, calendar/end-of-month clamping, inclusive Beacon notice boundaries, no time-implied exercise, pending/idempotent fixture staging, exercise acknowledgement/notes/source/property/date validation, duplicate exercise prevention, option exhaustion and later historical visibility, no inferred extension rent, read-only attention/report/export behavior, missing obligations, partial payment versus unallocated credit distinction, future credits, paid-late evidence, neutral reminder content, HTTP forms/export headers, and reset with reviewed exercise history.
- `python -m pip check`: no broken requirements. `git diff --check`: passed.
- Isolated browser workflow: staged three pending Beacon date/option facts, approved each against the original source, and verified the August 31–November 30, 2026 inclusive window. Read the separate fictional confirmation, explicitly chose its source, entered the September 15 exercise date and August 31, 2030 expiration, supplied its exact quotation and review note, acknowledged, and approved. The attention page displayed zero remaining options and retained the source and decision history. A screenshot records that result.
- Browser report review: inspected approved-record totals, pending credits, assumptions, uncertainty, exception history, date attention, and unsent drafts. Verified the final report includes the original option-rule citation and reviewed confirmation evidence. Clicked the Juniper draft copy control and observed its “no message has been sent” success status. Markdown generation and attachment headers passed HTTP integration checks; no external delivery was attempted.
- Restarted the finalized main app with additive schema initialization and opened its October brief. Closed the isolated test tab and stopped its server. Main app remains running. No attention fixture proposals or exercise events were added to the main records by these checks; lease reviews, obligations, imported transactions, and payment decisions were preserved.

### Limits and next review

Attention is evaluated on page load/run, with explicitly labeled planning horizons rather than background notifications. Quote checks establish text location, not semantic or legal correctness. Exercise outside an approved notice window, waivers, or inconsistent source relationships require additional reviewed terms. The exercise ledger updates planning dates but does not establish extension rent or recalculate obligations. The base lease's approved boundary still prevents rent generation into an extension with unestablished terms.

The Markdown artifact is generated on demand from a consistent read snapshot; reports and drafts are not a separate mutable email/document-management system. Drafts can be copied and edited outside the app. HTML print styling is included; no separate PDF or physical print verification is claimed. Earlier browser file-chooser automation limitations were not revisited in this slice.

For review: inspect Needs Attention and the October brief, download the Markdown artifact, and try a draft copy. Optionally stage Beacon's attention proposals, approve them, then record the fictional exercise from its source. Slice 6 (final demo preparation and user-led refinement) has not started.

## Slice 6 — Final verification and demo materials

**Date:** October 25, 2026 (America/Los_Angeles).

**Elapsed implementation and verification:** Approximately 10 minutes, starting around 6:44 p.m. Cumulative recorded implementation/verification time across all six slices is approximately 68 minutes. Prior planning and between-slice user review are not measured by these logs.

Added `DEMO_WALKTHROUGH.md` with isolated setup, a suggested demo sequence, expected balances, optional edge cases, and candid architecture/limitation talking points. Shortened README into an entry point linking to that guide, aligned the brief/design/plan with implemented decisions, and added one complete HTTP workflow regression. No material application fixes were needed in this slice.

### Observed verification

- Created a new virtual environment in a unique temporary folder and installed `requirements-dev.txt` successfully from the documented command. Initialized a new database without touching the main runtime database.
- Ran the full suite with the **fresh interpreter**: **118 passed**. `pip check` reported no broken requirements. The skill-creator validator reported **Skill is valid!** `git diff --check` passed.
- The new complete HTTP rehearsal started from seeded records, staged/approved Orchard's amendment, retained the old term, created $15,450 of October obligations, rejected an invalid CSV atomically, imported/reimported October transactions, approved two full payments, and manually allocated Juniper's $3,000 partial payment. The partial brief showed $11,250 approved and $4,200 remaining with pending-credit-aware reminder text.
- The rehearsal imported the later file (one added, one skipped), blocked its future-posted payment at the earlier review date, advanced the date, approved the named remainder, and retained the resolved balance issue while the unidentified credit stayed open. It then staged/reviewed Beacon's date rules and exercised its sole option from the confirmation evidence, without establishing extension rent.
- Exported partial and final Markdown briefs and reopened the app on the same database. Final state: three obligations, five unique imported transactions, four approved payment allocations totaling $15,450, zero rent remaining, one unresolved unidentified $4,200 credit, and one reviewed option exercise. Repeated startup retained those records.
- Copied the synthetic rehearsal database and exports into ignored `data/final-rehearsal-2026-10-25/` for inspection. Started that database in a **separate process using the fresh environment** on port 8001 and inspected its final report in the browser. The totals, pending unidentified credit, source quotations, late-payment annotation, reviewed option evidence, and absence of an unnecessary rent reminder were visible.
- No fresh ChatGPT extraction or successful automated native-file selection is claimed by this rehearsal. Its JSON proposal is explicitly hand-authored test input, and uploads use the HTTP test client. Live handoff and normal browser file selection remain human rehearsal steps documented in the guide.
- Main records were not reset, seeded, or used for test approvals. The main server on port 8000 remained available; the temporary rehearsal server/tab were closed after review.

### Delivery and remaining limits

All planned prototype build slices are complete. The next step is the user's live demo rehearsal and feedback, with the manual ChatGPT handoff and browser file picker. There is no production deployment, repository publication, external message delivery, real account access, or measured business-impact claim.

## Extension — Property and lease-document intake

Added **Add property from a lease** on Overview and **Add lease document** on existing property pages. New-property metadata and a valid source save together and redirect to existing lease review, without approving facts or creating rent. Empty databases can start directly with an uploaded lease instead of sample seeding.

PDF/TXT originals are retained in the ignored SQLite database with their SHA-256 fingerprints, page counts, and original filenames. Reference filenames remain unique across properties; uploads do not overwrite approved source records. Uploaded originals can be downloaded through a property-scoped route. TXT page markers and PDF page numbers support citations. Unnumbered pages use the explicit `Page text` section; numbered-section checks remain enforced, including support for terms written on the heading line itself.

Observed checks:

- **137 tests passed**, plus `pip check`, skill metadata validation, and `git diff --check`.
- New tests cover creation without sample data, retained/downloaded original bytes, cross-property download isolation, no automatic facts/obligations, repeated submissions, account-label conflicts, later amendments, colliding original filenames, multi-page selectable PDFs, encrypted/blank/malformed/oversized inputs, and Page text versus numbered-section evidence validation.
- HTTP integration also takes a new Harbor Court source through proposed/approved rent and due-day terms, obligation creation, synthetic CSV intake using its account label, and a full-payment proposal. The payment remains unrecorded until separate approval.
- Browser inspection verified the new form's fields and format guidance and the resulting uploaded-source review page on an isolated database containing only the fictional Harbor Court upload. The file upload itself used the HTTP client; no successful automated native file-picker selection is claimed.
- Added `pypdf==5.9.0` and a fictional unnumbered Harbor Court TXT fixture. The existing main records were not used for test creation/approvals; main app was reloaded with additive schema initialization.

Limits: selectable text on every PDF page is required; image-only/blank pages, encryption, DOCX, and OCR are unsupported. Uploads are limited to 10 MB, 100 pages, and 500,000 extracted characters. PDF reading order can vary, so the review screen links to the original for comparison. Invalid forms retain metadata but require file reselection. This remains a fictional-data local prototype with the same manual ChatGPT/human approval boundary.

### Configurable account labels extension

Automated suite: **145 passed**. Added coverage for normalized alias resolution, duplicate/conflicting transaction IDs across aliases, retired-label payment approval without source edits, active and retired cross-property ownership collisions, new-property intake conflicts, invalid-setting rollback, no-op history behavior, HTTP validation and persistence across application restart.

### Property ledger extension

Automated suite: **151 passed**. Ledger tests cover chronological running balances, same-day charges before receipts, multiple partial payments, arrears applied to their original rent month, date cutoffs, scheduled charges, pending/proposed credits excluded from balances, property isolation, persistence, read-only GET behavior, empty ledgers, invalid dates, unknown properties, and early-payment credits including negative cent formatting.

Browser verification: an isolated fictional ledger showed $6,400 charged, $3,200 in approved receipts, $3,200 owed, and a separate $500 unapproved credit. Changing the through date to September 30 showed $3,200 charged, $1,000 received, and $2,200 owed. Verified the property-page link and ledger in the working app without adding or approving records there.

### Description-based property assignment extension

Automated suite: **162 passed**. The four-column CSV replaces the external account label with literal case-insensitive description matching against configured primary phrases and aliases. Tests cover unique matches, no matches, multiple property matches, overlapping phrases, multiple aliases for one property, manual confirmation/evidence and date/property validation, stale assignment rejection, no payment before separate approval, assignment evidence retention, re-import stability after label changes, unresolved-row duplicate conflicts, legacy data preservation, and unassigned rows in HTML/Markdown reports. Existing end-to-end payment and ledger checks use updated fictional CSV artifacts. All sample artifacts remain available; a new `transactions-property-review.csv` demonstrates unmatched and ambiguous property descriptions.

Browser verification in an isolated fictional database: imported one unmatched row and one row matching two properties. Selected Beacon Industrial for the unmatched row, supplied evidence, and confirmed; the queue dropped from two to one, the row appeared with a manual assignment, and no payment was recorded. The working database was not seeded or populated during verification.

### Historical transaction fixture validation

Validated `sample-data/transactions-history.csv` with the application's actual parser and import service in a temporary seeded database. Original `M/D/YY` dates failed all eight date validations; normalized them to `YYYY-MM-DD`, retaining IDs, descriptions, amounts, and row order. Result: eight valid rows, three uniquely matched properties, August/September totals of $15,450 each, no duplicate IDs or collisions with other sample CSVs. First import added eight; repeat import skipped eight. After reviewing the fictional Orchard amendment and creating six obligations, each month produced two full-payment proposals. Approving those and the named Juniper partials produced ledger balances of $0 Orchard, $0 Beacon, and $8,400 Juniper through September 30, with $30,900 charged and $22,500 approved. Unidentified credits remained unallocated. Subsequent October import added four; the follow-up added one/skipped one. The validation database was discarded; the working database was not changed. No application code changed for this validation.
