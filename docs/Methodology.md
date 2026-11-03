# Methodology

How the engine in `model/retirement_model.py` works, and every assumption
worth checking. One vectorized loop (`_simulate`) produces the deterministic
ledger, every Monte Carlo lens, the keep-working scenario and the survivor
scenario, so they cannot disagree.

## One continuous annual model

Each calendar year from `start_year` to `end_year` (the year the younger
spouse reaches `plan_to_age`) runs the same steps:

1. **Scheduled income.** Earned income (or salary in a keep-working year),
   equity vests, deferred-comp installments, pensions (with or without COLA),
   and Social Security for each spouse (prorated in the claim year, COLA =
   inflation).
2. **RMDs** from each spouse's traditional balance from the SECURE 2.0 RMD age
   (75 if born 1960+, 73 if born 1951-1959), Uniform Lifetime Table.
3. **Dividends** on the taxable account (`taxable_dividend_yield`): taxed as
   qualified dividends, reinvested.
4. **Optional Roth conversion** up to `roth_conversion_ceiling` of ordinary
   taxable income (today's dollars).
5. **Spending:** the `Spending` band × inflation (the healthcare part grows
   faster by `healthcare_inflation_extra`), plus `FixedPayments` (nominal,
   such as a mortgage), plus `BigPurchases`. With guardrails on, the
   lifestyle portion flexes (below).
6. **Withdrawal / tax solve.** An iterative solver finds the withdrawals that
   cover spending **plus the federal and state tax those withdrawals
   create**, in a fixed order: **taxable → traditional → Roth**. Taxable
   withdrawals realize gains at `1 - taxable_basis_fraction`.
7. **Surplus** income is reinvested in the taxable account.
8. **Growth:** every balance grows by that year's return.

A path succeeds if the investable portfolio (taxable + traditional + Roth) is
above zero at the end of `end_year`.

## Federal tax (`model/data/federal_tax.json`)

Figures for `tax_year`, indexed by `inflation` for later years:

- Ordinary brackets and standard deduction, plus the per-person age-65
  addition (indexed) and the 2025-2028 senior deduction with its MAGI
  phase-out.
- Long-term gains and qualified dividends stacked on top of ordinary income.
- Social Security taxation via provisional income (all other AGI including
  gains and dividends, plus half of benefits; thresholds not indexed).
- 3.8% NIIT on gains and dividends above the MAGI threshold (not indexed).
- FICA in keep-working years.
- MFJ while both spouses are alive; single from the year after the first death.

## State tax (`model/data/state_tax/<XX>.json`)

Selected by `Params.state`. Brackets by year (so a legislated phase-down is
modeled), standard deduction and exemptions, optional indexing, Social
Security taxable or exempt, an age-tiered retirement-income exclusion per
spouse (with income attributed to each spouse), capital gains taxed as income,
excluded, or on a separate schedule (Washington), and a flat local rate. Full
field reference: `model/data/state_tax/README.md`.

## Three return lenses

| Lens | What it assumes | Role |
|---|---|---|
| **Pessimistic (parametric)** | IID-normal returns, `equity_real_mean` (arithmetic, default 6.5%) and `equity_vol` (18%). 6.5% / 18% is only ~4.9% *geometric* after volatility drag | **The plan** |
| **Middle (historical bootstrap)** | Real US returns 1872-2022 (Shiller) resampled in random blocks averaging 8 years, which preserves mean reversion | Cross-check |
| **Optimistic (historical cyclical)** | Every contiguous historical window, one path each; identical to FICalc.app | Cross-check; coarse (~110 paths) |

The historical lenses assume the future resembles the best-performing large
market of the last 150 years, starting from today's valuations. Plans built
on the pessimistic lens are robust to that assumption being wrong; plans
that only work on the historical lenses are not.

## Guardrails (Guyton-Klinger, absolute bands)

Once the portfolio is the funding source (no earned income, vests or
deferred-comp payout that year), each year:

- Withdrawal rate = planned lifestyle ÷ investable portfolio.
- Above `gr_upper` (5.5%) → multiplier × (1 − `gr_cut`); below `gr_lower`
  (3.5%) → multiplier × (1 + `gr_raise`).
- The multiplier ratchets one step per year within [`gr_floor`, `gr_ceiling`].
  `gr_floor` is the worst-case lifestyle the household accepts, and the most
  important choice in the plan.

## The affordability rule for big purchases

In guardrail runs, a planned purchase in a portfolio-funded year is capped at
`car_wr_ceiling × portfolio − (lifestyle − Social Security − pensions)`. A
healthy portfolio buys it in full; a stretched one buys a cheaper version or
defers. Negative `BigPurchases` amounts are one-time inflows and never flex.

## Survivor scenario (`Config.first_death_age`)

The first spouse dies in the year they reach the given age. From the next
year: single filing (federal and state), the survivor keeps the larger of the
two Social Security benefits, pensions pay their survivor percentage, the
traditional accounts roll over to the survivor, and spending becomes
`survivor_spend_pct` of the couple's budget.

## Keep-working scenario (`Config.retire_year`)

Years before `retire_year` have salary, bonus, 401(k) contributions and match
(to the husband's traditional balance), FICA, and optionally a new stock
grant each year. `EarnedIncome` is ignored; deferred comp pays out from the
retire year.

## Stress tests

- **Social Security cut:** `ss_cut_factor` (0.77 in the stress test) from
  `ss_cut_year`, the trust-fund depletion scenario.
- **Survivor:** each spouse at 70, `survivor_test_age`, and 85.
- **Overspending:** 10% above plan.

## Known approximations

- Constant cost-basis fraction for the taxable account.
- 100% stocks in the main engine; Levers.md models 60/40 and a bond tent
  (bonds 1.8% real, 6% volatility, independent of stocks).
- State tax is not deducted federally (standard deduction assumed).
- Not modeled, but flagged by preflight when the household is exposed:
  IRMAA surcharges, ACA premium credits, AMT, long-term-care events,
  concentration in one stock.
- Bridge income (vests, deferred comp) is fixed in dollars even though it
  falls in a bad market.

## Validation

- With state tax and dividends off, the engine reproduces an independent
  reference implementation to the dollar, across the deterministic ledger
  and every lens.
- The cyclical lens matches FICalc.app within about a point when the same
  plan is entered there.
- `output/data/first5_breakdown.txt` reconciles the first five years line by
  line.
