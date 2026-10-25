# Instructions for coding agents

## Project context

Build the interview prototype described in `PRODUCT_BRIEF.md` and `TECHNICAL_DESIGN.md`. Read both before changing application code. Use `sample-data/` as the source for fictional lease and transaction examples.

The intended prototype is a local browser app using Python, FastAPI, SQLite, and simple server-rendered pages. It demonstrates lease fact review, rent reconciliation, persistent memory, a reusable AI capability, and actionable output. The exercise is expected to take about 3–4 hours, with a six-hour maximum. Prioritize one understandable end-to-end workflow over feature breadth or production infrastructure, and leave time for the user's manual review and feedback.

## Fixed boundaries

- Use only fictional data from `sample-data/`. Never use or add real family leases, bank records, tenant details, credentials, or other private records.
- Lease extraction uses a manual handoff: the user invokes the reusable skill in ChatGPT and transfers structured JSON into the app. Do not add an LLM API call or provider-key setup in this iteration.
- Do not connect to a live bank, email account, Google Drive, or other third-party data source.
- Do not send email, initiate payments, deploy the app, or make other external changes.
- Require human approval before extracted lease facts or payment matches change approved records.
- Keep date, amount, due-status, grace-period, and matching calculations deterministic. Leave ambiguous cases unresolved and show the evidence.
- Keep `.env` files, local databases, and private uploads out of Git. Never put secrets in source files or commit history.

## Working approach

- Build in small, reviewable slices. Before a substantial slice, explain the outcome and likely files to change; afterward, summarize what changed and how to run or inspect it.
- Prefer the simplest implementation that satisfies the product brief and technical design. Avoid speculative abstractions and production infrastructure.
- Preserve evidence, effective dates, prior approved values, and review decisions. Do not silently overwrite history.
- If implementation reveals a conflict with the product brief or technical design, explain the tradeoff and update the relevant document when the decision is made.
- Keep `README.md` setup and run instructions aligned with the actual app as it develops.
