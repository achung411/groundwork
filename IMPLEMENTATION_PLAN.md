# Property Operations Workflow — Implementation Plan

**Status:** All six build slices completed, October 25, 2026. Fresh setup and 118 automated checks passed; walkthrough, observed results, and manual-verification limits are documented.
**Inputs:** [Product brief](PRODUCT_BRIEF.md), [technical design](TECHNICAL_DESIGN.md)  
**Time target:** The exercise is expected to take about 3–4 hours, with a six-hour maximum. Target roughly three focused hours for implementation and focused verification, then reserve 30–60 minutes for the user's manual review, demo rehearsal, and small refinements. Track planning, implementation, and review time honestly; do not assume preparation is excluded from the exercise total unless the instructions explicitly say so. Do not stretch work merely to fill the target.

## 1. Agreed outcome and boundaries

Build a locally run FastAPI web app with server-rendered templates, SQLite persistence, and fictional records. Demonstrate the complete loop: review lease evidence, approve terms, import transactions, approve payment allocations, investigate exceptions, and produce a monthly brief and unsent reminder.

- The only runtime AI capability is a reusable lease-extraction skill invoked live in a separate ChatGPT session. The app has no model API integration.
- The skill specifies versioned JSON. The app has a paste textarea, validation feedback, and per-fact approval. The user can select just the JSON portion of a response with surrounding prose. No general-purpose response cleanup or saved model-response demo is required.
- Full payments may receive automatic match proposals. Every recorded match requires approval, including full payments; this preserves the existing human-review boundary.
- Partial payments require manual allocation and explicit approval. Multiple approved payments can satisfy one obligation. Unidentified money remains unresolved until a reviewer explicitly associates it with an obligation and records a reason.
- Approved amendments affect new obligations and payments only. Existing obligations and payment allocations remain unchanged. Retroactive recalculation, reopening reconciled periods, and adjustment accounting are out of scope.
- Matching, date calculations, explanations, reports, and reminder drafts use deterministic rules and templates.
- Extend fictional fixtures for a later payment, duplicate and ambiguous cases, and exhausted extension options.
- No real records, authentication, deployment, background jobs, bank connections, or message sending.

## 2. Implementation defaults

Use Python, FastAPI, Jinja2, Pydantic, Uvicorn, and Python's built-in SQLite driver. Use pytest for service-level acceptance tests. Keep one application process and a simple local setup with a virtual environment and documented commands. Pin the dependencies actually verified during the build.

Store source text in SQLite, preserving the fixture page markers and original document identity. Keep the runtime database under ignored `data/`. Use integer cents for money, ISO calendar dates for business dates, and UTC timestamps for decisions. USD is the only supported currency. Each fictional property has one active lease and tenant; multiple simultaneous tenants per property are outside this build.

Use one reviewer label, such as “Demo owner,” without accounts. Seed fictional source documents and explicitly labeled, pre-reviewed base terms so reconciliation works immediately. Leave the Orchard amendment pending for live extraction and approval. Provide an explicit reset-and-seed command; ordinary startup must preserve existing work.

Keep the interface small: overview, property/lease review, reconciliation, and monthly report. Use plain labels, visible evidence, and compact history panels. Avoid a frontend build pipeline, rich text editor, PDF export, and elaborate styling. The report can be a printable HTML page with copyable text.

## 3. Data and rule contracts

### Lease handoff and approval

Define the interchange schema before writing the skill or review interface. Include `schema_version`, document identity, proposed facts, effective dates, uncertainty, and page/section/quote evidence. Support the demo's finite fact types: base rent, due day, grace days, lease start/end, and extension notice/term rules. Track option exercise decisions as reviewed events linked to approved source terms.

Keep unknown values distinct from zero or false. In particular, an absent grace term is unknown, not an inferred zero-day contractual grace period. Validate each fact's value shape and source identity; verify quotes against the cited page using narrowly defined whitespace normalization. A missing or mismatched quote blocks approval until the proposal is corrected. Uncertainty remains visible and requires explicit reviewer acknowledgement. Do not claim that quote validation establishes legal meaning or execution status.

Use a paste-and-resubmit JSON workflow rather than an inline JSON editor. Permit approve/reject per fact, with notes. Manual entry follows the same staging and evidence review rules. Approval and history writes must be atomic. Keep old facts and sources; do not silently replace them. Reject overlapping contradictory effective terms until corrected. Once all required rent terms are approved, the user explicitly generates obligations for the selected month; prevent duplicate obligations.

Existing obligations snapshot their approved amount, due date, grace rule, and supporting fact references. New obligations use the approved terms effective for that period. Do not backfill or regenerate existing obligations when approving an amendment. Require the demo amendment to be approved before generating October obligations for Orchard.

### Imports, matching, and allocations

Use the existing CSV columns: `transaction_id`, `account_label`, `posted_date`, `description`, and `amount`. Validate the whole file before committing; on any invalid row, report row-specific errors and import nothing. Accept positive incoming USD amounts with no more than two decimal places; other transaction types are unsupported. Use file digest and account-scoped transaction IDs for duplicate protection. Skip identical previously imported rows with visible counts; reject reused identifiers with conflicting content.

Create a small `payment_allocations` table in addition to the technical design's entities. Each approved allocation links a transaction, obligation, amount in cents, reviewer decision, and timestamp. Derive paid amount and remaining balance from allocations. Approval must recheck available transaction funds and outstanding obligation balance inside the database transaction; repeated clicks must not allocate twice. Do not support overpayments, reversals, or splitting one transaction among multiple obligations in this iteration; leave those cases for review.

Automatically propose only an unallocated transaction equal to the original amount of an entirely unpaid obligation, on the same account, with one eligible obligation in the selected review period. Exclude future-dated transactions relative to the review date. Memo text is visible supporting context, not an AI inference or sufficient reason to combine money. Multiple candidates remain ambiguous. Payments for old arrears or a remaining partial balance require manual selection and approval with a note.

Rejecting a proposal records that decision and does not recreate the same proposal on refresh. A partial payment opens an outstanding-balance exception. A later approved allocation can resolve that exception with an appended resolution event; preserve the original issue and decisions. A payment posted late remains historically late after approval, even when its current balance is zero.

### Dates, attention, and reporting

Use a visible review date, defaulting to today, and a selected rent month. Evaluate rent as upcoming, due today, within an explicitly approved grace period, or outstanding after the due date. When grace is unknown, label it “Past due date; grace period not specified” rather than claiming a contractual past-grace status. Beacon's fifth-day due date plus five calendar days includes the tenth; the eleventh is past grace. Use posted date as the demo proxy for payment receipt and document that limitation.

Use calendar-month arithmetic with end-of-month clamping for notice windows. For Beacon's August 31, 2027 expiration, the approved 12-to-9-month window is August 31 through November 30, 2026, inclusive. Display unexercised, exercised, and exhausted option states from reviewed events, never from elapsed time alone. Use a fixed, visible demo review date of October 25, 2026 in the walkthrough so the window remains reproducible.

Render report sections for approved expected rent, recorded payments, remaining balances, imported but unapproved candidates, evidence, assumptions, unresolved issues, and next actions. Reminder templates use approved facts and recorded balances; distinguish pending payment evidence and never assert that a candidate payment is recorded. Do not compute late fees. Reports reflect the current reviewed records evaluated at the chosen date; a full historical reconstruction of what the reviewer knew on an earlier date is outside scope.

## 4. Three-hour implementation sequence

The estimates include focused verification within each slice. Before each slice, explain its purpose and affected files; after it, report the behavior delivered and any manual run steps. Keep a simple elapsed-time log. This is a target, not a hard deadline; the six-hour maximum includes implementation and review work.

| Slice | Budget | Deliverable and acceptance |
|---|---:|---|
| 1. Running foundation | 20 min | App, templates, dependencies, SQLite initialization, reset/seed command, and property overview. Startup is reproducible; restart preserves records. |
| 2. Lease handoff | 35 min | Versioned schema, extraction skill, source/evidence display, paste validation, per-fact approval/rejection, and effective-term history. A pasted Orchard amendment stays pending until approved and retains the original rent term. |
| 3. Obligations and CSV intake | 25 min | Selected-month obligation generation, immutable term snapshots, validated imports, duplicate handling, transaction list. October Orchard rent is $5,050 after amendment approval; repeat imports add no payments. |
| 4. Reconciliation and memory | 40 min | Full-payment proposals, approval/rejection, manual partial allocations, exception history, later-payment resolution. Juniper remains $4,200 outstanding after a $3,000 allocation; its unidentified credit is not silently combined. |
| 5. Attention and outputs | 30 min | Due/grace and option attention, reviewed exercise events, report, neutral copyable reminder. Beacon's late payment and open notice window are explained from evidence; no fee or message sending. |
| 6. Final verification and demo materials | 30 min | Focused acceptance checks, README and observed evaluation results, known limitations, and demo run-through notes. |
| **Target implementation total** | **180 min** | **Build plus focused verification; reserve 30–60 minutes afterward for user-led review and refinement.** |

Checkpoint after about 80 minutes: lease review, obligations, and imports should work. At about 150 minutes, freeze features and use the final 30 minutes for verification and delivery. If behind, reduce styling and navigation polish, use simple forms and HTML reports, and avoid optional convenience controls. Preserve approval, evidence, allocation integrity, and persistence. Document incomplete acceptance criteria honestly rather than claiming completion or quietly spending more time. Live ChatGPT extraction and manual demo verification count toward implementation time. Leave room for the user to test the app and offer feedback; stop well before the six-hour maximum if the acceptance criteria are met.

## 5. Planned files

- `app/main.py`, `app/db.py`, `app/models.py`: routes, schema initialization, validated request/interchange types.
- `app/services/extraction_import.py`: proposal validation, evidence checks, and fact approval.
- `app/services/obligations.py`: approved effective terms and monthly obligation generation.
- `app/services/reconciliation.py`: import validation, matching, allocations, exceptions, and decisions.
- `app/services/attention.py`, `app/services/reporting.py`: date rules, summaries, and reminder text.
- `app/templates/`, `app/static/`: small server-rendered interface.
- `skills/lease-extraction/SKILL.md` and a compact schema reference: input instructions, allowed fact types, exact JSON format, evidence requirements, amendment handling, uncertainty, and live invocation instructions.
- `sample-data/`: additional fictional sources and transactions, with a scenario guide.
- `tests/`: service-level checks for consequential rules and state transitions.
- `README.md`, `EVALUATION.md`, dependency configuration, and `.gitignore`: reproducible setup, demo, observed results, and limitations.

Create the extraction skill during the build using the skill-creator workflow. Document a manual invocation path that works in the intended ChatGPT session; do not assume a repository skill is automatically installed or recognized there. The full skill instructions and fictional source text can be supplied manually if necessary.

## 6. Fixture extensions

Preserve the existing October transactions, especially Juniper's unattributed $4,200 credit. Add a separately identified later $4,200 Juniper payment so a reviewer can resolve the remaining balance while leaving the unattributed credit open. Use an October date after the initial review date and a later explicit review date for the follow-up demonstration.

The implemented extension example uses Beacon before and after a reviewed exercise, retaining the original unexercised base-lease source and adding a later fictional confirmation. A staging action creates pending date/option proposals; the user approves them and the exercise event separately. This demonstrates both an open notice window and exhausted options without adding a fourth property. Unknown future extension rent remains unknown. Focused import fixtures cover invalid rows, duplicate identifiers, and an ambiguous full-payment candidate.

## 7. Verification and demo acceptance

Use focused automated service tests for the financial/date and approval boundaries, plus one complete browser walkthrough. Prioritize:

1. Invalid JSON, wrong value types, unsupported quotes, and contradictory effective terms cannot become approved records; an amendment preserves source and prior terms and does not modify existing obligations.
2. A clear payment produces a proposal but does not reduce balance until approved. Repeated approval cannot double-record funds. Rejected proposals stay rejected.
3. Partial allocations reduce balance only after approval; a later allocation resolves the issue with history retained. The unrelated credit remains unresolved. Over-allocation is rejected.
4. Reimporting a file or the same identified transaction in another file creates no duplicate transactions; conflicting identifiers and malformed files are reported without partial writes.
5. Beacon's grace boundary and calendar-month notice boundaries are correct; no grace term or fee is invented. Exhausted options come from reviewed history.
6. Restart preserves approved facts, allocations, decisions, and exceptions. Refresh does not duplicate obligations or decisions. A future payment does not appear as received before its posted date.
7. Report and reminder agree with recorded allocations and distinguish pending evidence. No workflow calls a model API, financial service, or message-delivery service.

The demo follows the user's actual workflow: start the local app; show seeded terms; invoke live extraction on Orchard's amendment; paste the JSON portion; review and approve; generate October obligations; import October activity; approve a clear payment; show Beacon's timing; manually allocate Juniper's partial payment; inspect the unidentified credit; generate a report and reminder; import the later payment at a later review date; approve it and show exception resolution and retained history. Show the extension attention cases and persistence across restart.

## 8. Delivery and limitations

Deliver working source, the reusable extraction skill and schema, fictional fixtures, automated checks, and concise setup/demo instructions. `EVALUATION.md` records what was actually tested, observed pass/fail outcomes, live extraction observations, actual build time, and any unfinished items. Do not present planned tests as passed or synthetic examples as measured business benefits.

Expected limitations: manual ChatGPT handoff, one lease per property, base rent only, posted dates standing in for receipt dates, no retroactive amendment reconciliation, no overpayment/reversal accounting, and no production controls. See `EVALUATION.md` for actual implementation progress, measured build time, and observed checks.
