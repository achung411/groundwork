# Property Operations Workflow — Product Brief

**Status:** Interview prototype implemented; observed results and limitations are recorded in `EVALUATION.md`.
**Purpose:** Define the product problem and the interview prototype before implementation.

## Summary

Build a small property-operations workspace for owner-managed commercial properties. The interview prototype will demonstrate one end-to-end workflow: establish reviewed rent obligations from lease records, reconcile a monthly set of incoming payment transactions, and prepare follow-up for human review.

The prototype is a learning and interview exercise grounded in the family's experience managing three commercial properties. It is not intended to be a production-ready property-management platform.

## User and problem

### Primary user

An owner or family member who handles administrative work for a small commercial property portfolio.

### Current situation

Each property has its own bank account, and rent payments are deposited into the corresponding account. The official payment records can be reviewed through each bank's portal. Rent activity is then recorded manually in a physical ledger, with calculations maintained alongside it; there is not currently a digital spreadsheet serving as the rent ledger. This reflects the family's accounting background and established paper-based practices. Lease documents and amendments provide the underlying terms. When a payment is late or unclear, a person investigates and may contact the tenant. The process is manageable for three properties, but checking separate bank portals and reconciling them with paper records takes manual effort and makes it harder to review activity in one place.

### User need

When reviewing a rent period, the owner wants to know which expected payments arrived, which remain outstanding or need investigation, and what follow-up may be appropriate—without losing the evidence behind the decision or letting automation make an unreviewed change.

## Product direction

Create an owner-focused administrative workspace, rather than a tenant-facing portal or a full property-management suite. Lease documents establish the facts the workflow needs; recurring payment reconciliation provides the ongoing utility.

### Product principles

- **Evidence before assertion:** Show the transaction details or lease passage supporting an extracted or matched fact.
- **Human approval for consequential changes:** AI proposes lease extractions; application rules propose payment matches and prepare reminder drafts. A person approves changes to approved records. The prototype sends nothing externally.
- **Deterministic rules for arithmetic and dates:** Use code for amount comparisons, due dates, payment status calculations, match explanations, and reminder templates. Use AI for lease-document interpretation only.
- **Keep history:** Preserve source documents, approved values, prior values, decisions, and unresolved exceptions so a later run can use relevant context.
- **Be explicit about uncertainty:** Flag ambiguous lease language, missing evidence, duplicate candidates, or partial payments for review. Do not infer late fees or legal consequences that are not supported by an approved lease term.
- **Protect family information:** Use fictional sample documents and transaction data in the take-home prototype. Do not put leases, payment data, credentials, or other secrets in the code repository.

## Demonstration workflow

1. **Establish expected rent.** Start with manually entered lease facts or use a reusable lease-extraction skill in a separate ChatGPT session with a fictional lease packet. Transfer the skill's structured proposal into the app, then review each term against its cited source passage before approval.
2. **Import a monthly transaction file.** Load a fictional bank-transaction CSV that represents a bank feed. This is a simulation, not a connection to a real bank.
3. **Suggest payment matches.** Compare transactions against expected rent obligations using deterministic account, amount, and date rules. Explain candidates and leave ambiguous cases for human review.
4. **Review and approve.** Show evidence, confidence or uncertainty, and the proposed result. Require a human decision before recording a payment or resolving an exception.
5. **Prepare follow-up.** For an overdue or unresolved obligation, generate a neutral reminder draft for review. The prototype does not send email.
6. **Reuse memory on a later run.** Persist approved lease facts, imported transactions, human decisions, and open exceptions. Demonstrate that a later transaction can resolve a previously open item without erasing its history.
7. **Produce an actionable artifact.** Generate a monthly rent reconciliation brief that separates evidence, assumptions, exceptions, and recommended next steps.

## Date-driven attention check

The product may include a narrow, deterministic daily check that surfaces upcoming or overdue items in an in-app **Needs Attention** list. This is a small rules-based review of approved lease dates and payment status, not a general notification platform.

- **Lease options and expiration:** Surface the start of a notice window, an approaching lease end, and cases where all contractual extension options have been exercised so the owner can plan to negotiate a new lease or discuss the tenant's plans. Record exercise or other decisions as reviewed events; do not assume an option was exercised merely because time passed.
- **Rent due dates and grace periods:** Show a payment as due, within its approved grace period, or overdue only after the stored due date and grace-period terms support that status. Do not infer a grace period, late fee, or legal consequence absent an approved source term.
- **Prototype behavior:** Calculate the list when the user opens or runs the review, using an explicit review date. This demonstrates the daily check without requiring background scheduling or real-time push delivery.
- **Future delivery:** A deployed version could run the check on a daily schedule and add user-selected delivery channels. Background scheduling, email or push delivery, channel preferences, and a broad notification-management system are outside the interview prototype.

## Prototype scope

### In scope

- A small set of fictional commercial properties and lease records.
- Add fictional properties through a PDF/TXT lease-upload interface; retain original documents and review extracted terms before approval. Add later lease/amendment documents to an existing property without overwriting history.
- Expected rent amount, due date, payment period, and source/provenance fields.
- Separate read-only property rent ledgers showing saved charges, approved payment receipts, rent months, due/received dates, source references, and chronological running balances; unapproved credits remain separate.
- Lease-document intake for sample files and AI-proposed term extraction with source evidence and human review. For this prototype, the user invokes the reusable skill in ChatGPT and transfers its structured output into the app; the app does not make a model API call.
- Import of a synthetic transaction CSV.
- Candidate transaction-to-rent matching, including clear, partial, late, duplicate, and ambiguous cases.
- Approval before recording a match or resolving an exception.
- Persistent lightweight memory across workflow runs.
- A small in-app attention list for lease notice/expiration dates and rent due/grace-period status, evaluated against approved terms and an explicit review date.
- A reconciliation brief and an unsent reminder draft.
- A reusable lease-obligation extraction skill with a defined input, structured output, evidence requirements, uncertainty handling, and invocation instructions. The user invokes it in ChatGPT and imports or pastes its result into the app for validation and review.
- Reproducible setup, run instructions, sample inputs, representative evaluation cases, a known limitation, and a concise README.

### Out of scope for the interview prototype

- Connecting to a real bank, bank credentials, or financial accounts.
- Sending email or taking any action on a tenant's behalf.
- A general notifications system, including push/SMS delivery, user notification preferences, high-volume event subscriptions, or background scheduling. The prototype only calculates a focused in-app attention list when a review is run or the app is opened.
- Tenant logins, rent payment processing, or a tenant communication portal.
- Full bookkeeping, tax preparation, trust accounting, CAM reconciliation, or lease legal advice.
- Production deployment or a claim that the prototype is ready for family use with real records.
- An in-app LLM API integration, provider credential management, or automatic model invocation. These can be considered in a later iteration after the workflow and cost model are validated.
- Full document-management replacement, tenant sales-report processing, property valuation, or general-purpose property-management features.
- Building a full email-management product. A later workflow could support reusable email templates with variables, multiple template types, scheduled delivery, and user review and editing before sending. That capability is intentionally outside this prototype: it is a substantial standalone product area, and an eventual version would more likely integrate with an established email service than build template management and delivery infrastructure from scratch. The prototype may prepare an unsent reminder draft, but it will not send email.

These may be future product directions if the prototype and user feedback support them.

## AI and deterministic responsibilities

| Capability | Approach |
|---|---|
| Extract rent terms and dates from lease documents | User invokes a reusable skill in ChatGPT; it proposes structured facts with source references, which the user transfers into the app for validation and approval |
| Resolve amendments and extensions | AI identifies candidate changes and relevant evidence; uncertain or conflicting changes require review |
| Compare payment amounts and dates | Deterministic application logic |
| Interpret a transaction memo or suggest a match | Deterministic rules explain full-payment candidates; partial payments require manual allocation and approval |
| Calculate overdue status | Deterministic logic based on approved due-date terms and the selected review date |
| Draft a reminder | A deterministic template uses approved facts; user reviews; no sending |
| Reconcile an ambiguous or unsupported case | Keep it open and explain what evidence or decision is needed |

## Memory model to demonstrate

The prototype should make its stored context inspectable. A lightweight store is sufficient.

- **Property:** fictional property identity and basic metadata.
- **Lease document:** file identity, document type, date, and relationship to other lease documents.
- **Lease fact / obligation:** proposed or approved value, effective period, source passage, review status, and approver decision.
- **Expected rent:** period, amount, due date, and link to the approved lease fact.
- **Imported transaction:** source file, transaction date, amount, description, and import/run identity.
- **Match proposal and decision:** candidate obligation, evidence, status, reviewer decision, and timestamp.
- **Exception:** issue type, supporting evidence, open/resolved status, and resolution history.

An AI extraction must not silently overwrite an approved current term. A later amendment should create a proposed change linked to its source; after approval, the current effective record can be updated while the prior value remains in history. In the prototype, extraction runs outside the app through the user's ChatGPT session; the app validates the submitted structure and citations, then leaves approval to the user.

For this iteration, amendments affect new obligations and payments only. Recalculating or reopening previously reconciled periods is out of scope. Automatic matching produces full-payment proposals only; recording any match still requires human approval. Partial payments require explicit manual allocation and approval.

Lease extraction is the only runtime AI capability. The live ChatGPT skill defines a versioned JSON response, and the app provides a paste interface for that JSON. The user may copy just the JSON portion of a response containing additional prose; a saved model response is not required for the demo. Matching, explanations, reports, and reminder drafts use deterministic code and templates.

## Evaluation and success measures

The prototype should be judged on a scripted evaluation set, not on unobserved production impact.

### Observed prototype checks

- A clear payment is proposed for the correct obligation and requires approval before recording.
- A partial, late, duplicate, or ambiguous transaction is surfaced accurately as an exception or review item.
- An unsupported late-fee rule is not invented.
- A lease extraction includes its source evidence and remains proposed until approved.
- A subsequent run reuses prior approved facts and can resolve an open exception while retaining decision history.
- A lease option notice window, an exhausted-extension scenario, and a rent grace period are surfaced from approved terms without inventing deadlines or penalties.
- The reconciliation brief distinguishes evidence, assumptions, uncertainty, and recommended actions.
- No email is sent and no real financial account is accessed.

### Expected benefits to validate later

- Less time spent searching across lease files, spreadsheets, and transaction records.
- Fewer missed or unresolved payment follow-ups.
- Greater confidence that each current rent term is supported by the right lease document.

Do not present these expected benefits as measured results unless they are actually observed in user testing.

## Interview demo outline

1. Show the fictional property and its approved expected-rent record.
2. Invoke the lease-extraction skill in ChatGPT with a fictional lease or amendment, then transfer its structured result into the app and review the cited evidence.
3. Import a monthly transaction file and run the reconciliation workflow.
4. Review and approve one supported match.
5. Show an ambiguous or partial payment and explain why the system leaves it for review.
6. Generate a reminder draft without sending it.
7. Run a later period or import a follow-up transaction to demonstrate persistent memory and exception resolution.
8. Explain the reusable skill, what is stored, the safety boundary, and one limitation—including that model invocation is a manual handoff in this prototype.

## Assumptions and resolved prototype choices

- The initial user is a family member managing a small commercial portfolio, not a third-party property manager.
- The prototype uses fictional data and a transaction-file simulation.
- The first recurring workflow centers on rent; periodic sales reports and other tenant obligations are future scope.
- Product and technical choices will be made in reviewable slices. This brief describes the intended outcome, not a mandated implementation stack.
- Before any real family use, the team must choose hosting, authentication, data storage, backups, document access, and recovery practices suitable for sensitive records.

Choices resolved during planning and implementation:

- Three fictional base leases, Orchard's rent amendment, and a later Beacon option-confirmation source support the demo.
- Synthetic CSV fields are transaction identifier, account label, posted date, description, and amount. Deterministic full-payment rules make suggestions; partial and ambiguous cases require manual allocation.
- Lease facts, payment allocations, and option exercise events require explicit human review. Reports and attention checks calculate views without changing approval state.
- A local SQLite database preserves sources, effective terms, allocations, and inspectable decision/exception history.
- A virtual environment, pinned direct dependencies, documented local commands, isolated rehearsal data, and automated checks support the take-home. Repository publication and a hosted GitHub workflow have not been performed.

## Competitive context

Commercial property-management and lease-administration products already offer many adjacent capabilities, including lease dates, rent tracking, NNN/CAM workflows, documents, and AI-assisted lease abstraction. The prototype should not claim that lease extraction or rent tracking is novel. Its purpose is to demonstrate a focused, evidence-grounded, human-reviewed workflow for a small owner-managed context and to make the product choices and limitations explicit.

## Decisions still intentionally open

- Final product name and branding; “Property Operations” is the prototype's working title.
- Any future model API/provider integration or hosted deployment. This iteration uses local FastAPI, server-rendered HTML, and SQLite; its only runtime AI step is the manual ChatGPT lease handoff.
- Any future integration with Google Drive, email, or a bank sandbox.
- Whether the prototype later expands to periodic sales reports, property notes, or document storage beyond the demo packet.

