# State tax rules

One JSON file per state, selected by `Params.state` in `Inputs.xlsx` (the
two-letter code, or `NONE`). The engine computes state tax every year on every
Monte Carlo path, and it is part of the withdrawal/tax solve.

Shipped files: `GA.json` (flat rate + retirement exclusion), `WA.json`
(capital gains excise only), `NONE.json` (no income tax). For any other state,
copy the closest one to `<XX>.json` and fill it in from the state Department
of Revenue. Cite every figure in `sources` and set `tax_year`.

## Fields

| Field | Meaning |
|---|---|
| `tax_year` | Year the figures apply to. Preflight flags the file when this is older than the current year. |
| `brackets.mfj` / `brackets.single` | `{ "<first year>": [[upper, rate], ...] }`. The engine uses the latest entry whose year is ≤ the model year, so a legislated phase-down is a row per year. `null` = no upper bound. A flat tax is one bracket. |
| `standard_deduction` | By filing status. Use 0 if there is no standard deduction. |
| `personal_exemption_per_person` | Subtracted per living spouse. |
| `indexed` | `true` if brackets, deductions and exemptions rise with inflation each year. |
| `ss_taxable` | `true` if the state taxes Social Security (the federally taxable portion is used). |
| `retirement_exclusion` | `null`, or `tiers_by_age` (`[[min_age, amount_per_person], ...]`), the income types it covers (`ira` = traditional withdrawals, RMDs and Roth conversions; `pension`; `dcp`; `gains`; `dividends`), and `earned_income_cap_per_person`. A state that exempts all retirement income: `[[0, 1e12]]`. |
| `capital_gains.mode` | `income` (taxed as ordinary state income), `excluded` (not taxed), or `separate` (a separate bracket schedule in `capital_gains.brackets`, applied to realized gains; `include_dividends` adds dividends). |
| `local_rate` | Flat local/county income tax applied to state taxable income (for example, Maryland counties). |

## Approximations

- Income is attributed to each spouse for the retirement exclusion:
  traditional-account flows by each spouse's share of traditional balances,
  taxable-account gains and dividends 50/50, pensions to their owner, deferred
  comp to its account owner.
- State tax is not deducted on the federal return (the federal engine uses the
  standard deduction).
- Part-year residency and a planned move: create the file for the destination
  state and switch `Params.state`, or run the plan twice and compare.
