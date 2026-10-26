# Synthetic demo data

Every name, property, lease, amount, account label, and transaction in this folder is fictional and was created for the interview prototype. These examples are not copied from family records or real bank statements.

## Files

- `leases/orchard-row-lease.txt` and `leases/orchard-row-amendment.txt`: base rent and a later rent change. The amendment should be treated as a proposed update to the current obligation, with the original term retained in history.
- `leases/beacon-industrial-lease.txt`: payment grace-period language and a future extension notice window.
- `leases/juniper-market-lease.txt`: rent with no stated grace period, useful for checking that the workflow does not invent one.
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

CSV files use UTF-8, exactly the five documented columns (in any order), nonempty transaction identifiers and descriptions, ISO posted dates, known account labels, and positive unsigned decimal USD amounts with at most two decimal places. File fingerprints and account-scoped identifiers prevent duplicates. A duplicate with changed details is rejected instead of silently updating a prior transaction.
