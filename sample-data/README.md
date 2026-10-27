# Synthetic demo data

The documents and transactions in this folder are fictional demo artifacts. The Best Burger PDFs are a synthetic, partial re-creation based on the structure of a family lease; they provide a more realistic document test than the short hand-authored TXT examples. Use these synthesized samples, not original family records or bank statements.

## Files

- `leases/orchard-row-lease.txt` and `leases/orchard-row-amendment.txt`: base rent and a later rent change. The amendment should be treated as a proposed update to the current obligation, with the original term retained in history.
- `leases/beacon-industrial-lease.txt`: payment grace-period language and a future extension notice window.
- `leases/juniper-market-lease.txt`: rent with no stated grace period, useful for checking that the workflow does not invent one.
- `leases/best burger lease.pdf` and `leases/best burger - rent addendum.pdf`: a partial synthetic lease packet for the final new-property intake and documentation-gap demonstration. See the Best Burger instructions below.
- `transactions-history.csv`: eight August/September 2026 credits for preloading historical activity before trying the October scenarios. See the historical preload instructions below.
- `transactions-2026-10.csv`: fictional incoming activity for October 2026. It includes a clear payment, a late payment, a partial payment, and an unattributed credit that should remain ambiguous pending review.

The lease text uses page markers so the extraction skill can cite evidence by page and section. Amounts and dates are illustrative only.

## Property intake example

`leases/harbor-court-lease.txt` is an additional fictional, unnumbered lease for the property-upload interface. It is not automatically seeded. Try adding Harbor Court / Cove Studio LLC with document date December 15, 2025; the default account label is Harbor Court operating. Its text becomes page 1 and uses `Page text` citations. Rent and dates remain unapproved until reviewed.

## Option attention example

`leases/beacon-extension-confirmation.txt` is a later fictional amendment confirming delivery and acceptance of notice on September 15, 2026, exercise of Beacon's sole three-year option, and an extended expiration of August 31, 2030. It deliberately leaves extension rent unestablished.

This source is added to the database only when the user clicks **Stage fictional attention examples** on Needs Attention. That action also stages manually authored, citation-backed start/end/option proposals from Beacon's original lease where not already pending or approved. These are fixture proposals, not saved model responses or automatic approvals. Review the proposals individually, observe the original notice window, then explicitly approve the exercise from the new source. The original unexercised lease source and subsequent reviewed event are both retained.

## Import checks and later run

- `transactions-2026-10-follow-up.csv`: repeats Juniper's already identified $3,000 payment, then adds a separately identified October 28 payment of $4,200. After the original file, expect one new transaction and one duplicate skipped. It does not identify or resolve the original unattributed $4,200 credit. Payment allocation will be added in slice 4.
- `transactions-invalid.csv`: includes a valid-looking first row followed by an unknown account, impossible date, and excess decimal places. Expect row-specific errors and no rows imported, including the first row.
- `transactions-conflicting-id.csv`: reuses the original Orchard transaction ID with a different amount. After importing the original October file, expect a conflict and no new import. The app cannot know that an ID is conflicting until its original transaction exists.
- `transactions-ambiguous-full.csv`: adds a second, distinct $3,200 Beacon credit. Use in a separate ambiguity scenario before recording Beacon's original payment. Both credits fit the full amount, so matching must not choose between them. A previously proposed match becomes ineligible and is withdrawn on the next matching run; manual allocation requires a reviewer reason.

CSV files use UTF-8, exactly four columns: `transaction_id,posted_date,description,amount` (in any order), nonempty transaction identifiers and descriptions, ISO posted dates and positive unsigned decimal USD amounts with at most two decimal places. File fingerprints and feed-wide identifiers prevent duplicates. Configured property phrases are included inside descriptions; there is no account_label column. Unmatched descriptions and descriptions matching multiple properties remain imported for manual property assignment. A duplicate with changed details is rejected instead of silently updating a prior transaction.

`transactions-property-review.csv` demonstrates a description with no matching phrase and one matching two properties. Importing these rows creates no payment and leaves them in the manual property-assignment queue.

## Historical preload: August and September 2026

`transactions-history.csv` uses the four-column transaction import format and ISO `YYYY-MM-DD` posted dates. It contains eight distinct transaction IDs, none reused by the other sample CSVs:

| Property | Rows | August credits | September credits | Total credits |
|---|---:|---:|---:|---:|
| Orchard Row Retail | 2 | $5,050 | $5,050 | $10,100 |
| Beacon Industrial | 2 | $3,200 | $3,200 | $6,400 |
| Juniper Market | 4 | $7,200 | $7,200 | $14,400 |
| **Total** | **8** | **$15,450** | **$15,450** | **$30,900** |

All descriptions include the corresponding default property phrase (`Orchard Row operating`, `Beacon Industrial operating`, or `Juniper Market operating`). If you configure different phrases, retain these as aliases or manually assign unresolved rows. The file lists September before August; import order is harmless because the UI orders activity by posted date.

To prepare a populated dataset without using the October test files:

1. Add the three sample leases through **Add property from a lease**, extract/review their terms, and add/review Orchard's amendment establishing $5,050 effective July 1, 2025. Alternatively, explicitly run `python -m app.db init` against an empty selected database before starting its server; this creates the sample properties and base terms, but Orchard's amendment still needs review and approval. Importing transactions alone does not create properties, lease terms, or rent obligations.
2. Open **Reconciliation**, select rent month `2026-08` and review date `2026-09-30`, then import `transactions-history.csv`. Expect **8 added, 0 skipped**. The August view shows four rows; switch to `2026-09` to see the other four. Re-importing the file skips all eight rows.
3. In each of `2026-08` and `2026-09`, explicitly create all three rent obligations from approved terms. Each month's total is **$15,450**. Run matching for each month; expect two full-payment proposals (Orchard and Beacon), still requiring approval.
4. Approve those supported full payments. Manually allocate each named Mosaic Foods $3,000 partial payment to Juniper's corresponding month, with evidence and confirmation. The two `ACH CREDIT 84XX-1102` credits of $4,200 each identify the property by phrase but do not identify the payer. Leave them unallocated unless you have separately verified fictional evidence; do not combine credits merely because their totals equal rent.
5. Open each property's **View rent ledger**, through `2026-09-30`. With only the supported approvals above, expect **$30,900 charged, $22,500 approved, $8,400 remaining** across the three properties. Orchard and Beacon each have zero rent balance; Juniper has $4,200 remaining for each month and two unallocated $4,200 credits. Importing the file without any approvals instead leaves all $30,900 as outstanding rent after the obligations are created.
6. Keep `transactions-2026-10.csv` for a later import of four new credits. Then `transactions-2026-10-follow-up.csv` adds one credit and skips one duplicate. The invalid/conflicting/ambiguous/property-review CSVs remain separate scenarios. A conflict file requires its original October transaction to exist before it can demonstrate a conflicting ID.

Nothing auto-loads this history on startup. Import/approval state persists in the selected local database, so prepare it ahead of a demonstration and restart with that same database. Use a separate `PROPERTY_DB_PATH` as shown in `DEMO_WALKTHROUGH.md` to keep rehearsals isolated. October report totals cover October; historical arrears still remain visible in each property's all-period ledger until explicitly resolved.

## Best Burger: realistic PDF intake and documentation gaps

Keep both PDFs as supplied. They are intentionally used after the transaction-processing scenarios, as a new property whose documentation does not establish every fact needed to create expected rent. They are not automatically seeded, and the other sample transaction files do not contain Best Burger payments.

| File | Represents | Current PDF pages |
|---|---|---:|
| `leases/best burger lease.pdf` | A partial synthetic base lease dated March 1, 1998, including the original term, renewal rights, and references to supporting documents | 10 |
| `leases/best burger - rent addendum.pdf` | The same-date supporting rent addendum, including formula-based initial rent, subsequent adjustments, payment timing, and conditional late charges | 4 |

The page counts describe these PDF exports, not the original lease's pagination or a complete historical lease packet. The PDFs have selectable text; they do not test OCR on scanned images. Spaces in their filenames are supported and should be retained.

### Demo use

After demonstrating historical activity, new transaction imports, payment approval, reports, and ledgers, follow **8. Add Best Burger and demonstrate documentation gaps** in `DEMO_WALKTHROUGH.md`. Upload the base lease as a new property, then attach the rent addendum to that same property. Extract and review each source separately. These files demonstrate retaining source evidence, recognizing supported facts, and holding incomplete or unsupported terms for review.

### Expected gaps and limits

- **Monthly base rent:** even the initial amount depends on a Treasury-linked rate and Total Cost. No fixed monthly rent is established by the supplied packet. The funding limitation is not rent. Leave monthly base rent unestablished; do not look up rates, calculate CPI adjustments, or invent a demo amount.
- **Effective/current term:** rent commencement depends on events not fully established by the packet. The original dated lease and renewal rights alone do not establish exercise of options or a current term for a 2026 scenario. Preserve uncertainty; do not manufacture commencement, expiration, or exercise records.
- **Grace and fees:** the addendum describes business days after receipt of a default notice, with other conditions. This is not the app's simple calendar-day grace rule. Omit an unsupported grace-period fact; fee/interest calculations are outside this demo.
- **Renewal rights:** the lease states a minimum notice period without an earliest notice boundary. The current extension-option schema expects both boundaries. Explain this mismatch rather than inventing a notice window.
- **PDF extraction:** visual text and locally extracted text can differ, including ligature substitutions and flattened headings. These are extraction limitations, not necessarily typos in the original PDF. Compare the displayed extracted source with the original. For these exports the current citation validator recognizes no numbered heading lines, so use `Page text` and quotations matching the extracted page. Copy the exact app reference filename, including its property prefix and spaces.
- **Gap presentation:** ChatGPT can describe missing information and model limitations outside the JSON. The app validates the submitted supported facts, retains proposed uncertainty, and blocks obligation creation without approved rent/due terms. It does not automatically persist ChatGPT's surrounding commentary as a comprehensive document-gap checklist.

Success means both originals are retained, supported facts can be reviewed with citations, and expected rent remains unestablished when the source does not support it. A blocked rent preview is an expected outcome here. No PDF repair, OCR expansion, formula calculation, new rent confirmation, or forced approval is required for this scenario.
