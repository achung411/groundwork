# Demo walkthrough

Show an existing portfolio in progress, add a straightforward new property, process October transactions, show the updated results, and finish with a realistic PDF packet containing unresolved lease details. All records are fictional. This demonstrates a reviewed workflow, not measured business impact or production readiness. Rehearse the live ChatGPT handoffs separately; their response time is variable.

## Prepare before the audience arrives

### Use an isolated, persistent demo database

Keep the working app/database on port 8000. In a new terminal, from the repository folder:

```sh
source .venv/bin/activate
export PROPERTY_DB_PATH="$PWD/data/demo-$(date +%Y%m%d-%H%M%S).sqlite3"
python -m app.db init
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Open [the isolated app](http://127.0.0.1:8001). Keep that terminal open: its database selection persists for later commands. The unique filename creates a fresh demonstration without resetting the working records. To resume the prepared state, stop with Ctrl+C and repeat only the Uvicorn command in that same terminal. Do not rerun the timestamped export when resuming; that selects a different database. If port 8001 is occupied, stop the earlier demo server or choose another loopback port consistently.

Run `python -m pytest -q` and `python -m pip check` before presenting. Have a separate ChatGPT session ready and locate the files in `sample-data/` for normal browser uploads. The copyable extraction prompt includes the skill, contract, and selected source text; no model API key or skill installation is required.

### Prepare the three existing properties and their history

The explicit `init` command loads Orchard Row Retail, Beacon Industrial, and Juniper Market with base terms. **Reserve Harbor Court and Best Burger for live creation.** Do not upload them during preparation. Do not import the October transaction files yet or stage Beacon's optional extension examples for the main demo.

1. Open Orchard → **Extract and review lease terms**, select `orchard-row-amendment.txt`, and use the ChatGPT handoff. Review and approve $5,050 monthly rent effective July 1, 2025, including evidence, execution uncertainty, and replacement acknowledgment. The earlier $4,800 term remains in history. Complete this before creating historical obligations; the amendment is preparation, not a live demo step.
2. Open **Reconciliation**, rent month `2026-08`, review date `2026-09-30`. Import `transactions-history.csv` once. Expect **8 added, 0 skipped** across August and September. Only August's four rows appear in the August view; September's four appear when that month is selected. The configured default property phrases match these descriptions.
3. For both `2026-08` and `2026-09`, explicitly create each of the three properties' rent obligations. Each month totals **$15,450**. Run matching separately for each month and approve the supported Orchard $5,050 and Beacon $3,200 proposals.
4. For each month, manually allocate the named Mosaic Foods $3,000 partial payment to Juniper's corresponding month, with evidence and confirmation. Leave the two unidentified `ACH CREDIT 84XX-1102` credits of $4,200 each unallocated. Their property phrases identify Juniper, but their amounts do not verify payer identity.
5. Verify the prepared state below. Leave all October obligations uncreated so they can be introduced live. Use the same database when presenting.

Importing historical transactions alone does not create obligations, approve payments, or establish paid ledgers. See the [historical preload instructions](sample-data/README.md#historical-preload-august-and-september-2026) for fixture details.

| Prepared state through September 30 | Rent charged | Approved payments | Rent balance owed |
|---|---:|---:|---:|
| Orchard Row Retail | $10,100 | $10,100 | $0 |
| Beacon Industrial | $6,400 | $6,400 | $0 |
| Juniper Market | $14,400 | $6,000 | $8,400 |
| **Portfolio** | **$30,900** | **$22,500** | **$8,400** |

There should be eight imported historical transactions, six monthly obligations, six approved payment allocations, and two unallocated $4,200 credits. Harbor Court and Best Burger should be absent. No October transactions or obligations should exist. Historical arrears are intentional and remain separate from October's monthly totals.

## 1. Tour the portfolio in progress

Start on **Overview** with review date September 30: [prepared portfolio](http://127.0.0.1:8001/?as_of=2026-09-30).

Suggested introduction:

> This is a portfolio already in use. We can see what rent has been recorded, what remains outstanding, and what evidence still needs review. A person approves changes to lease terms and recorded payments.

Keep the tour focused:

- **Overview / Needs Attention:** show the three existing properties and outstanding rent based on approved records. For this state, focus on rent attention rather than optional lease-extension examples.
- **Property records:** briefly show an approved term, its source quotation, and prior values/history where relevant. No amendment processing is needed live.
- **Property ledger:** open Juniper's **View rent ledger**, through `2026-09-30`. Show chronological charges, partial receipts, the $8,400 running balance owed, and the two unallocated credits outside that balance. Orchard or Beacon provides a paid comparison.
- **Reconciliation:** select `2026-09`, review date `2026-09-30`. Show the month's transactions, approved allocations, and unresolved credit. September alone has $15,450 expected, $11,250 approved, and $4,200 remaining.
- **Report:** show the monthly brief and an unsent reminder acknowledging pending credits. It is a review aid; the app sends nothing.

Keep the distinction explicit: the monthly report covers September, while each property ledger accumulates all saved activity through its selected date. Current approval decisions are evaluated against due/posted dates; moving the date backward is not a reconstruction of past reviewer knowledge.

## 2. Create Harbor Court live

Harbor Court is the uncomplicated intake example: one short lease, fixed rent, stated dates, no amendments, and no extension options.

1. On **Overview**, choose **Add property from a lease**.
2. Enter property `Harbor Court`, tenant `Cove Studio LLC`, description matching phrase `Harbor Court operating` (or leave it blank for that default), and source document date `2025-12-15`.
3. Upload `sample-data/leases/harbor-court-lease.txt`. Show that the property and source are saved before any terms are approved.
4. Open **Copy the extraction prompt for ChatGPT**, copy the complete prompt into the separate session, and ask it to extract the proposed facts. Paste only the JSON object into **Lease extraction JSON** and validate/stage it.
5. Verify the source, effective dates, and citations before approving supported terms:

| Term | Expected source-supported value |
|---|---|
| Monthly base rent | $2,100 from January 1, 2026 |
| Rent due day | First day of each month |
| Lease commencement | January 1, 2026 |
| Lease expiration | December 31, 2030 |
| Grace period / extension option | Unspecified; do not invent values |

The unnumbered TXT is page 1 with citation section `Page text`. The JSON filename must match the app's displayed property-prefixed reference, not just the original filename. Correct malformed JSON or mismatched citations against the source before resubmission; quote matching establishes text location, not semantic correctness.

Return to the property records to show the approved terms. Harbor Court is now the fourth property. No earlier-month Harbor Court obligations or payments are created automatically; its ledger covers only obligations and payments actually saved in the app.

## 3. Create October rent and process new transactions

Open **Reconciliation**, rent month `2026-10`, review date `2026-10-25`, and choose **Open review**. Use this explicit date throughout the October steps.

Inspect each preview and create October obligations for **all four properties**:

| Property | October rent | Due | Approved grace |
|---|---:|---|---|
| Orchard Row Retail | $5,050 | October 1 | Not specified |
| Beacon Industrial | $3,200 | October 5 | Five calendar days after due date |
| Juniper Market | $7,200 | October 1 | Not specified |
| Harbor Court | $2,100 | October 1 | Not specified |
| **Total** | **$17,550** | | |

Explain the order:

> Importing transactions does not require rent obligations. We create them first here so the expected charges are visible before we compare receipts. Obligations must exist before matching or payment allocation.

Upload `sample-data/transactions-2026-10.csv`. Expect **4 added, 0 skipped**. The existing eight historical transactions remain saved. Only October rows are shown in this monthly view.

Descriptions identify Orchard, Beacon, and Juniper through configured phrases; no `account_label` CSV column is required. The file contains no Harbor Court payment. **Harbor Court's $2,100 will remain outstanding**, which is expected. Importing any of these credits records no rent payment by itself.

Click **Run matching for 2026-10**. Expect two pending full-payment proposals: Orchard $5,050 and Beacon $3,200. Review their source evidence and approve them. Beacon's October 18 payment is after its approved grace period; retain the timing annotation without calculating a fee.

Under **Manual allocation**, expand `SYN-2026-10-003`, select **Juniper's October obligation**, explain the named Mosaic Foods $3,000 partial payment, acknowledge, and approve. Explicitly choose October: Juniper also has historical obligations available, and this demo is not allocating the deposit to arrears.

Leave `SYN-2026-10-004`, the unidentified $4,200 credit, unallocated. It matches a property's phrase but still needs payer/payment verification. Do not combine it with the partial payment merely because their amounts total rent.

| October checkpoint | Approved payments | Remaining October rent |
|---|---:|---:|
| Four obligations and CSV imported | $0 | $17,550 |
| Orchard and Beacon approved | $8,250 | $9,300 |
| Juniper partial approved | **$11,250** | **$6,300** |

## 4. Show how the portfolio changed

Return to the October **monthly brief** and one or two **property ledgers** through `2026-10-25`.

- October report: **$17,550 expected, $11,250 approved, $6,300 remaining**. The remaining amount is $4,200 Juniper plus $2,100 Harbor Court. The new unidentified $4,200 credit remains separate.
- Juniper ledger: August and September arrears remain $8,400; October adds $4,200 outstanding. Its running rent balance is **$12,600**, with three unallocated $4,200 credits shown separately.
- Harbor Court ledger: one $2,100 October charge and no payment; earlier months are not inferred from the lease's start date.
- Orchard and Beacon: supported October payments leave their running rent balances at zero.

Across all saved obligations through October 25, the four property ledgers total **$48,450 charged, $33,750 approved, $14,700 owed**. This all-period balance includes historical arrears, so it differs from October's $6,300 remaining.

Show an updated unsent reminder or download the Markdown brief if useful. The key checkpoint is the visible change after approval, with uncertain credits still unresolved. Keep follow-up imports and duplicate/error scenarios out of the main path.

## 5. Finish with Best Burger: documentation gaps

<a id="8-add-best-burger-and-demonstrate-documentation-gaps"></a>

Add Best Burger as a fifth property after the successful processing examples. Keep both synthesized PDFs as supplied. The base lease is intentionally partial; these PDFs test selectable-text intake rather than OCR on sloppy scans.

1. Choose **Add property from a lease**. Enter property `Best Burger`, tenant `BURGER TIME ACQUISITION COMPANY, L.L.C.`, description matching phrase `BEST BURGER`, and source date `1998-03-01`. Upload `sample-data/leases/best burger lease.pdf` (currently 10 pages).
2. On the same property, use **Add lease document** or **Add another lease or amendment**. Upload `sample-data/leases/best burger - rent addendum.pdf` (currently 4 pages), dated `1998-03-01`, with document type **Lease**. It supports the original lease rather than representing a later rent change.
3. Use the extraction prompt for each selected source separately. The app includes only the selected document in its prompt and expects a separate source-specific JSON proposal. Ask ChatGPT to describe missing information and unsupported terms outside the JSON. Retain the exact app reference filename, including its prefix and spaces.
4. Compare the PDF with **Read the selected source**. Text extraction may alter ligatures or flatten headings even when the visual PDF is correct. For these exports, use citation section `Page text` and quotations matching the app's extracted page. A citation mismatch is an opportunity to review/correct the proposal, not proof that the underlying document is wrong.
5. Stage only supported facts. For example, the addendum states a first-of-month payment day, but the applicable commencement date is not fully established. An unknown effective date uses `effective_from: null` plus uncertainty and remains pending. Omit unsupported values rather than forcing approval. If there are no supported facts, discuss the missing information without manufacturing an importable response.
6. Return to October **Reconciliation**. Show Best Burger's missing-approved-term message and absence of a rent obligation. Existing obligations, payments, and the $6,300 October balance remain unchanged; Best Burger's expected rent is unestablished, not zero, and is excluded from that total.

Points to explain:

- Even initial rent depends on a Treasury-linked rate and cost inputs; neither PDF establishes a fixed monthly amount. The funding limitation is not rent. No macroeconomic lookup, formula calculation, or replacement rent confirmation is required for this demo.
- Conditional late charges use business days after a default notice and cannot be represented as a simple five-calendar-day grace period.
- Renewal language lacks the earliest notice boundary required by the current option schema; the partial packet also does not establish exercised options or a current 2026 term. Leave these unresolved.
- Some gaps come from missing source information, some from extraction, and some from the deliberately limited data model. The app validates submitted facts, shows proposed uncertainty, and blocks obligations without approved rent/due terms. ChatGPT's broader gap explanation remains outside the imported JSON and is not automatically persisted as a comprehensive checklist.

Suggested closing:

> The earlier properties show what we can process with reviewed terms. This property shows where we stop: we retain the evidence and supported facts, but we need more information before recording expected rent. Missing information is a review task, not permission to guess.

Expected endpoint: five properties, both Best Burger originals retained, no Best Burger obligation or payment, and the previously reviewed portfolio balances preserved. See the [Best Burger fixture notes](sample-data/README.md#best-burger-realistic-pdf-intake-and-documentation-gaps) for details.

## Optional material for questions or a separate rehearsal

These actions change the scenario; they are not required for the main demo:

| Input/action | Expected behavior |
|---|---|
| Reimport the October CSV | Zero added, four skipped; approvals are retained |
| `transactions-2026-10-follow-up.csv` | One new named $4,200 credit and one duplicate; October 28 receipt is ineligible in an October 25 review |
| Approve that follow-up on October 28 | Explicitly allocate to Juniper's October obligation with evidence; October remaining becomes $2,100 Harbor Court, while historical Juniper arrears remain |
| `transactions-invalid.csv` | Row-specific errors; no rows imported, including its valid-looking first row |
| `transactions-conflicting-id.csv` after October import | Reused identifier with changed details blocks the file |
| `transactions-ambiguous-full.csv` before approving Beacon | Two full credits fit; matching cannot choose; a prior proposal becomes stale |
| `transactions-property-review.csv` | Unmatched/multiple-property descriptions require manual property assignment, separate from payment approval |
| Reject a proposal and rerun / approve a deposit twice | Rejection persists / duplicate allocation is blocked |
| Beacon option attention and exercise | Additional source review and explicit exercise approval; do this in a separate scenario so pending amendments do not disrupt the main path |
| Restart using the same selected database | Sources, approvals, transactions, obligations, and unresolved history persist |

## Presentation boundaries

Lease interpretation uses the manual ChatGPT handoff. Money, dates, matching constraints, reports, and state changes use deterministic code. Quote checks prove text location, not semantic correctness or legal validity. Live model output has not been benchmarked; automated tests use hand-authored proposals.

The prototype uses fictional data only, one lease per property, USD base rent, and a limited term schema. It does not provide OCR, production authentication/recovery, live bank access, payment execution, message delivery, automatic formula-based rent, retroactive adjustments, deposit splitting, or general bookkeeping. Benefit claims remain hypotheses.

Recorded build durations in `EVALUATION.md` exclude prior planning and between-slice review; they are not total project effort or complete demo preparation time.
