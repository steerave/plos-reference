# Recurring Questions

Reference document. The questions PLOS needs to answer reliably, organized by domain. Each question maps to an answer surface — either a Dataview dashboard or one of the three compiled artifacts — per the routing rule in `examples/sample-vault/CONVENTIONS.md` and the architecture in `ARCHITECTURE.md`.

This list shaped the v0.3 artifact set (3 compiled + 10 Dataview) and stays in the repo as reference for when a new question shows up: does it fit an existing dashboard, an existing compiled artifact, a new dashboard, or — under the explicit decision rule — a new compiled artifact?

---

## Properties

- When are property taxes due, per property?
- Which property taxes are escrowed in the mortgage payment vs. paid manually?
- Which insurance policy covers which property, and what does each policy cover?
- What is the monthly carrying cost per property (mortgage, HOA, utilities, insurance)?
- What is the cash flow status per property — healthy, break-even, or bleeding?
- Who is the current mortgage servicer for each property, and what is the servicer history?

## Financial overall

- Where is the majority of monthly cash outflow going?
- What is the total subscription cost per month, broken down by service?
- What are utilities costing per property and in aggregate?

## Medical

- What vaccinations has each family member received, and when?
- What appointments are scheduled or overdue per person?
- What medications is each person currently taking?
- What does our health insurance cover, and what are the deductibles and out-of-pocket maximums?

## Vehicles

- What is the insurance, registration, and inspection status for each vehicle?
- What is the service history for each vehicle?

## Tax

- Which entities are missing tax documents for the current tax year?
- What is the running list of items the accountant will need at tax time?
- How do property tax payments roll up into the annual tax-year view?

## Investments and retirement

- What is the current snapshot of investment accounts and balances?
- What are the retirement targets, and where do we currently stand against them?

## Projects

Covers the active project portfolio (DocFlow, joet.build, the portfolio site, PLOS itself).

- What is the current state of each project?
- What are the next steps for each project?
- Across all projects, what should I prioritize working on right now?

## Key dates

- Birthdays and anniversaries (folded into the upcoming dashboard).

## Estate and legal

Currently sparse — this domain exists primarily as a flagged gap.

- Where are wills stored?
- Who are the named beneficiaries on each account?
- Where are POA documents and originals of important records?

---

## Cross-cutting questions

These cut across all domains and are the highest-leverage answers in the system. All three are compiled artifacts (named exceptions to the Dataview default), because each requires synthesis beyond aggregation.

- **What's expiring or due in the next 30 / 60 / 90 days?** (Dataview — `dashboards/upcoming.md`. Aggregation, not synthesis.)
- **What needs my attention this week?** (Compiled — `compiled/this-week.md`. Priority reasoning across domains.)
- **What's unusual about this month?** (Compiled — `compiled/anomalies.md`. Pattern detection from history.)

---

## Gap-surfacing as a feature

PLOS should not only summarize present information — it should flag *absent* information that ought to exist. The system pointing out "you have no will" is as valuable as the system pointing out "your insurance renews in 14 days."

Initial gaps surfaced by this inventory:

- **No estate planning documents.** No wills, POA, or beneficiary review on file.
- **Vehicle records are low-frequency lookups but high-stakes when needed.** If insurance/registration/service history isn't centrally captured, the gap surfaces in an emergency rather than during routine maintenance.
- **Account access map for family members.** Who has access to what, in case of incapacity or death.

Gap-surfacing is concentrated in the `tax-prep.md` compiled artifact (checklist-vs-received) and the `dashboards/estate.md` dashboard (currently mostly empty by design — its emptiness is the report).
