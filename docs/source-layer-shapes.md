# Source Layer — Entity Shapes

Reference document. The shape of entity folders in the source layer, plus the entity record (`index.md`) pattern they all follow. The architectural principles that govern the source layer are in `ARCHITECTURE.md` (vault layout, capture flow, merge contract); the operating rules are in `examples/sample-vault/CONVENTIONS.md`. This doc covers the per-entity-type shape only.

The source layer is what compile passes read from and Dataview dashboards query against. Every fact PLOS knows enters here and is held here.

---

## Entity-folder shapes

### Properties

```
source/properties/123-main-davenport/
├── index.md                    ← entity record
├── mortgage/
│   ├── current-statement.pdf
│   ├── current-statement.txt
│   ├── archive/
│   │   ├── 2025-12-statement.pdf
│   │   └── 2026-01-statement.pdf
│   └── servicer-history.md     ← manual log of servicer changes
├── insurance/
│   ├── current-policy.pdf
│   ├── current-policy.txt
│   └── archive/
├── tax/
│   ├── 2024-statement.pdf
│   ├── 2024-statement.txt
│   ├── 2025-statement.pdf
│   └── 2025-statement.txt
├── utilities/
│   ├── electric/
│   ├── gas/
│   ├── water/
│   └── internet/
├── hoa/                        ← omitted if no HOA
└── notes.md                    ← free-form
```

### Vehicles

```
source/vehicles/2019-civic-1234/    ← slug includes year/model + last 4 of VIN
├── index.md
├── registration/
│   ├── current.pdf, current.txt
│   └── archive/
├── insurance/
├── inspections/
├── service/
│   ├── service-log.md          ← manual log; primary source for compile
│   ├── 2024-10-oil-change.pdf
│   └── 2025-04-tires.pdf
└── purchase/                   ← title, original purchase docs
```

### People

```
source/people/joe/
├── index.md                    ← birthdate, ID expirations, employment
├── identity/
│   ├── passport.pdf, passport.txt
│   ├── drivers-license.pdf
│   └── ssn-location.md         ← where physical card is stored, not the number
├── medical/
│   ├── vaccinations.md         ← manual log; primary source for compile
│   ├── medications.md          ← current list
│   └── records/
│       └── 2025-physical.pdf
├── employment/
└── account-access.md           ← source for the account-access dashboard
```

### Accounts

Financial accounts (bank, brokerage, retirement) and health insurance live here. Health insurance is structured as an account because the questions asked of it (coverage, deductibles, OOP max, who's on the policy) match the account shape better than the person shape. People records reference the household health-insurance account by path.

```
source/accounts/chase-checking-4521/
├── index.md                    ← owner(s), purpose, login URL, recovery contact
├── statements/
│   ├── 2025-04.pdf, 2025-04.txt
│   └── ...
└── transactions/
    └── 2025-q1.csv             ← chunked CSVs (preprocessing artifact)
```

```
source/accounts/healthcare-bcbs-family/
├── index.md                    ← carrier, plan name, deductible, OOP max, covered persons
├── coverage/
│   ├── current-summary.pdf, current-summary.txt
│   └── archive/
└── claims/                     ← optional; per-year claims summaries if useful
```

### Organizations

Referenced entities — servicers, carriers, utilities, employers. Metadata-only; documents live under the entity they describe (the property whose insurance policy is from State Farm, not under State Farm).

```
source/organizations/state-farm/
└── index.md                    ← contact info, support URLs, policies referencing this org
```

### Tax

```
source/tax/2025/
├── index.md                    ← filing status, accountant info, key dates
├── expected-documents.md       ← canonical list; drives gap-surfacing in compiled/tax-prep.md
├── received/
│   ├── w2-anthropic.pdf, w2-anthropic.txt
│   ├── 1099int-chase.pdf
│   └── ...
└── working-notes.md            ← running notes for the year
```

### Projects

```
source/projects/docflow/
├── index.md                    ← link to repo, current focus, role of project in portfolio
└── STATUS.md                   ← (or symlink to canonical STATUS.md in the repo)
```

Projects mostly link out to where the canonical state lives (per-project `STATUS.md` files in their own repos). The vault doesn't try to own that — it points to it. Whether the link is a symlink or a copy depends on the deployment topology of the operating instance.

### Estate

```
source/estate/
├── index.md                    ← what exists, what's missing, what's planned
├── wills/                      ← currently empty for new vaults; existence flagged in dashboards/estate.md
├── poa/
└── beneficiaries.md            ← named beneficiaries per account
```

---

## Entity record shape (`index.md`)

Every entity folder's `index.md` follows this pattern:

```markdown
---
type: source
entity: property
slug: 123-main-davenport
status: active                  ← active | archived | sold | retired
address: 123 Main St, Davenport, IA 52801
purchased: 2018-06-15
purpose: primary-residence
mortgage_servicer_current: Mr. Cooper
insurance_carrier_current: State Farm
hoa: false
---

# 123 Main St, Davenport, IA

**Use:** Primary residence.

## Current key facts

- **Mortgage:** Mr. Cooper, balance ~$284k, monthly P&I $1,840
  → mortgage/current-statement.txt
- **Property tax:** $4,200/yr, escrowed in mortgage
  → tax/2025-statement.txt
- **Insurance:** State Farm SF-XYZ-001, renews Sept 12
  → insurance/current-policy.txt
- **HOA:** None.

## History

- 2018-06: Purchased.
- 2026-02: Mortgage transferred PennyMac → Mr. Cooper.
  → mortgage/servicer-history.md

## Documents

Subfolders: `mortgage/`, `insurance/`, `tax/`, `utilities/`.

## Notes

(Free-form.)
```

**Frontmatter rule:** anything that compile passes need to filter on, sort by, or surface in summaries — and anything Dataview queries against — goes into frontmatter as a typed field. Anything narrative goes into prose. When in doubt, frontmatter — it's cheaper to read structurally than to parse prose.

The full frontmatter contract (date formats, money fields, cross-reference style, naming conventions) lives in `examples/sample-vault/CONVENTIONS.md`.

---

## Joint-ownership note

For entities with multiple owners — a vehicle co-owned by two household members, a joint account — the entity record carries `owners: [joe, partner]` in frontmatter. Cross-references from each person's record duplicate, which is acceptable. The entity has one canonical record; the people records point to it.
