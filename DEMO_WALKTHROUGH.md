# Interview walkthrough

This guide targets an 8–10 minute demonstration, plus time for the live ChatGPT handoff. All records and transactions are fictional. The exercise demonstrates a small owner-managed workflow, not measured operational impact or production readiness.

## Prepare an isolated demo

Keep the current app/database on port 8000. In a **new terminal**, from the repository folder, start a separate database on port 8001:

```sh
source .venv/bin/activate
export PROPERTY_DB_PATH="$PWD/data/interview-$(date +%Y%m%d-%H%M%S).sqlite3"
python -m app.db init
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Open [the isolated app](http://127.0.0.1:8001). Keep that terminal open; its database selection persists for later commands in that terminal. Each new filename starts a fresh demonstration without resetting your main records. To demonstrate persistence, stop with Ctrl+C and repeat only the Uvicorn command in the same terminal. If port 8001 is occupied, stop the earlier rehearsal server or choose another loopback port consistently.

Before the interview, run `python -m pytest -q` and `python -m pip check` in the activated environment. Have a separate ChatGPT session ready and locate the CSV files in `sample-data/` for the browser's file picker. The generated copyable prompt contains the skill instructions, response contract, and source text; it does not require a model key or a skill installation in ChatGPT.

## 1. Explain the problem and approval boundary

Show the three fictional properties. Suggested explanation:

> A small owner-managed commercial portfolio currently checks separate bank portals against paper records and leases. This prototype brings the evidence and review decisions into one local workspace. It proposes interpretations and matches, but approved terms and payments change only after a person reviews them.

Open Orchard's records. Its pre-reviewed base lease says $4,800. The later amendment is present as source material, not an approved change.

## 2. Extract and approve the amendment live

Open Orchard → **Extract and review lease terms**. Select `orchard-row-amendment.txt`, expand **Copy the extraction prompt for ChatGPT**, and copy it into the separate ChatGPT session. Request the extraction.

Copy only the returned JSON object, excluding code fences or commentary, into **Lease extraction JSON**. Validate and stage it. Check:

- Monthly base rent is $5,050 from July 1, 2025, supported by page 1, section 2.
- The proposal is pending; importing did not change approved rent.
- Execution status is not established by the sample source. Review that uncertainty explicitly rather than treating the file as proof of a real executed agreement.

Add a note explaining use of the presented amendment in this fictional demo. Acknowledge the evidence and replacement, then approve. Show the original $4,800 value through June 30, 2025 and $5,050 from July 1, with both sources and the decision retained.

If ChatGPT returns a malformed shape or a mismatched quote, correct the selected JSON and resubmit. Pending facts can be rejected and replaced with corrected proposals. Do not claim quote matching proves semantic or legal correctness. There is no saved model response required for this walkthrough; the automated tests use hand-authored expected proposals and do not evaluate live model quality.

## 3. Create rent and import October activity

Open **Reconciliation**. Choose rent month `2026-10`, review date `2026-10-25`, and **Open review**. Create each property's obligation after inspecting its preview.

| Property | Expected rent | Due | Approved grace |
|---|---:|---|---|
| Orchard Row Retail | $5,050 | October 1 | Not specified |
| Beacon Industrial | $3,200 | October 5 | Five calendar days after due date |
| Juniper Market | $7,200 | October 1 | Not specified |
| **Total** | **$15,450** | | |

Inspect an obligation's retained evidence/assumptions. The record keeps its values even after a later term changes. Missing approved lease boundaries are disclosed rather than silently filled in.

Use the file picker to import `transactions-2026-10.csv`. Expect four new transactions. Reimport it and expect zero added, four skipped. Importing the CSV has not recorded any rent payments.

The four credits total $15,450, exactly equal to expected rent. That total does **not** establish that all rent is paid: one credit is unidentified.

## 4. Approve supported matches and a partial payment

Click **Run matching for 2026-10**. Expect two pending full-payment proposals: Orchard $5,050 and Beacon $3,200. Neither changes the recorded balance until approved.

Review and approve Orchard and Beacon. Beacon's October 18 posted date is after its approved grace period. Its due/grace timing annotation stays in history after the balance is paid. No fee is calculated. Posted date is only this demo's proxy for receipt date.

Under **Manual allocation**, expand `SYN-2026-10-003`, Juniper's named $3,000 partial payment. Explicitly select October rent, explain the supporting memo, acknowledge, and approve. The entire deposit goes to that one obligation.

Leave `SYN-2026-10-004`, the unidentified $4,200 credit, unallocated. Matching the remaining balance is insufficient evidence to combine it with the partial payment.

| Checkpoint | Approved payments | Remaining rent | Important unresolved evidence |
|---|---:|---:|---|
| Obligations and CSV imported | $0 | $15,450 | All four credits await review |
| Orchard and Beacon approved | $8,250 | $7,200 | Juniper credits remain unallocated |
| Juniper partial approved | $11,250 | $4,200 | Unidentified $4,200 credit remains open |

## 5. Produce the actionable artifact

Follow **Open monthly brief and unsent reminders for this review**. Point out approved amounts, exact source passages, unallocated credits, assumptions, uncertainty, exceptions, and recommended next steps.

Inspect Juniper's unsent reminder: it reports the reviewed balance and acknowledges credits still awaiting review rather than concluding that payment has not arrived. Copy it for review/editing outside the app. Nothing is sent.

Use **Download brief as Markdown** to retain this partial reconciliation as a standalone artifact.

## 6. Demonstrate memory on a later run

Import `transactions-2026-10-follow-up.csv`: expect one added, one skipped. The new named $4,200 remainder posts October 28, so it cannot be approved in an October 25 review.

Advance **Review date** to `2026-10-28`, open `SYN-2026-10-005`, explicitly select Juniper's October obligation, add a reason, acknowledge, and approve. A remaining-balance payment still requires manual allocation.

Expected final result: **$15,450 approved, $0 remaining**, four approved allocations, five unique imported transactions. The earlier unidentified $4,200 credit remains open and unallocated. Expand the resolved partial-payment issue to show its original opening and later resolution events. Download the later brief and restart the app in the same terminal to show that the records and history persist.

The review date filters posted evidence against current review decisions; moving backward does not reconstruct what the reviewer knew at that earlier time. Already allocated deposits stay reserved against duplicate use.

## 7. Show date-driven option attention

Open **Needs Attention**, review date `2026-10-25`. Click **Stage fictional attention examples** and follow the link to review Beacon's three pending date/option terms. This is manually authored fixture staging, not a live extraction result or an automatic approval. The live skill can also propose these terms.

Approve the cited commencement, expiration, and one-option rule. Return to Needs Attention and show the **August 31–November 30, 2026 inclusive notice window**. Its passage does not imply exercise.

Under Beacon, open **Record an option exercise after reviewing its source** and read `beacon-extension-confirmation.txt`. Select it explicitly and enter:

- Exercise date: `2026-09-15`.
- New expiration: `2030-08-31`.
- Page: `1`; section: `2. EXERCISE CONFIRMATION`.
- Quotation: copy the supporting confirmation paragraph from that section.
- Notes: explain the reviewed notice, dates, and that extension rent remains unestablished.

Acknowledge and approve. Show zero remaining options, the recorded extended expiration, and the retained event source. This changes attention planning, not existing obligations or approved rent. The app cannot carry the current rent into an extension whose rent is unestablished.

If time is short, show the open window live and describe the reviewed exercise path; keep the longer option walkthrough for questions.

## Optional edge cases

Use these in a separate fresh scenario so they do not obscure the successful path:

| Input/action | Expected behavior |
|---|---|
| `transactions-invalid.csv` | Row-specific errors; no rows imported, including its valid-looking first row |
| `transactions-conflicting-id.csv` after the original file | Reused identifier with changed details blocks the file |
| `transactions-ambiguous-full.csv` before approving Beacon | Two distinct full credits fit the same rent; neither is chosen automatically; a prior proposal becomes stale |
| Reject a full proposal with a reason and rerun | Rejection stays in history; automatic matching does not recreate it |
| Approve the same deposit twice | Second attempt is blocked; no duplicate allocation |
| Review October 10/11 before Beacon's posted credit | Within approved grace on the tenth; after grace on the eleventh |
| Missing grace or unsupported late fee | Unknown grace remains unspecified; no fee invented |
| Exercise outside an approved notice window | Held for additional reviewed terms; no waiver inferred |

## Explain choices and limits candidly

AI is useful here for interpreting unstructured lease language. Deterministic rules are better for money, dates, matching constraints, and auditable state transitions. The separate skill makes the AI boundary reviewable without model credentials in the app.

SQLite and server-rendered pages keep the local prototype understandable and persistent without a deployment or frontend build pipeline. Evidence and append-only decisions matter more than broad feature coverage for this demonstration.

Known limits: fictional data only; one lease per property; base rent only; manual ChatGPT handoff; no model-quality benchmark; quote checks do not prove interpretation; no retroactive amendment adjustments, overpayment/reversal accounting, deposit splitting, notice waivers, authentication, production recovery, or delivery integrations. Expected business benefits are hypotheses, not measured results.

Use the recorded implementation/verification durations in `EVALUATION.md` accurately. Planning and between-slice user review were not timed by those logs, so do not present their sum as total project effort or automatically claim compliance with an interview time limit.
