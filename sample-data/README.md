# Synthetic demo data

Every name, property, lease, amount, account label, and transaction in this folder is fictional and was created for the interview prototype. These examples are not copied from family records or real bank statements.

## Files

- `leases/orchard-row-lease.txt` and `leases/orchard-row-amendment.txt`: base rent and a later rent change. The amendment should be treated as a proposed update to the current obligation, with the original term retained in history.
- `leases/beacon-industrial-lease.txt`: payment grace-period language and a future extension notice window.
- `leases/juniper-market-lease.txt`: rent with no stated grace period, useful for checking that the workflow does not invent one.
- `transactions-2026-10.csv`: fictional incoming activity for October 2026. It includes a clear payment, a late payment, a partial payment, and an unattributed credit that should remain ambiguous pending review.

The lease text uses page markers so the extraction skill can cite evidence by page and section. Amounts and dates are illustrative only.
