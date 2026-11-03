# private/: your source documents

Put every export, statement and letter the plan is built from here. Everything
in this folder is committed to **this copy's local git history**, alongside
`Inputs.xlsx` and `output/`, and OneDrive backs up the folder. The hooks that
`setup_clone.py` installs block every push, so git never copies any of it off
this computer.

## Layout

| Folder | What goes in it |
|---|---|
| `accounts/<institution>/` | Positions CSVs (with cost basis) and statements for every brokerage, 401(k)/403(b), IRA, Roth, HSA and deferred-comp account |
| `social_security/` | ssa.gov statements for both spouses |
| `income/` | Recent pay stubs, offer or separation letters, severance terms, pension benefit estimates |
| `benefits/` | Health plan and COBRA notices, deferred-comp payout elections, equity vest schedules |
| `spending/<institution>/` | 12+ months of card and checking transaction exports (CSV) |
| `taxes/<year>/` | Last two years of federal and state returns |
| `insurance/` | Home, auto, umbrella, life and long-term-care policy declarations |
| `property/` | Property tax bill, mortgage statement, escrow analysis |
| `estate/` | Wills, powers of attorney, beneficiary confirmations (optional) |

## Naming

Start every file name with the **as-of date**, `YYYY-MM-DD_`, for example
`accounts/<institution>/2026-12-31_joint_brokerage_positions.csv`. Preflight uses the
date to flag documents more than a year old. Record the path in the
`source_file` column of `Inputs.xlsx` → `Accounts` so every number traces back
to a document.
