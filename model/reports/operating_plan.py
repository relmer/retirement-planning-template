"""operating_plan.py: the Annual Operating Plan (withdrawal-rate rule + per-year thresholds).

Writes output/Annual_Operating_Plan.md.  python model/reports/operating_plan.py
"""
from __future__ import annotations
from common import load, write, money, money_m, first_portfolio_funded_year, M
from retirement_model import Config, run_deterministic, spending_real, infl_factor


def build(quick=False):
    inp = M._inp()
    c = Config().resolved()
    df = run_deterministic(Config(), 0.065)
    g0 = first_portfolio_funded_year(inp)
    life0 = spending_real(g0)
    md = [f"# Annual Operating Plan: withdrawals and guardrails\n",
          f"_On-track path: 6.5% real every year, claim {c.husband_claim_age}/{c.wife_claim_age}. "
          "Dollars are nominal (actual account values that year) unless marked real._\n",
          "## The one rule: the withdrawal rate\n",
          "Every January, **divide this year's lifestyle budget by the total investable portfolio** on Dec 31 "
          "(taxable + traditional + Roth; exclude deferred comp while it pays out, and money set aside for a "
          "planned big purchase):\n",
          "| Withdrawal rate (budget ÷ portfolio) | Action |", "|---|---|",
          f"| **Above {c.gr_upper:.1%}** | **CUT** the budget {c.gr_cut:.0%}, never below the floor "
          f"(**{money(life0 * c.gr_floor)}/yr real**, {money(life0 * c.gr_floor / 12)}/mo) |",
          f"| {c.gr_lower:.1%} to {c.gr_upper:.1%} | **STAY**: last year's budget + inflation |",
          f"| **Below {c.gr_lower:.1%}** | **RAISE** the budget {c.gr_raise:.0%}, up to the ceiling "
          f"({money(life0 * c.gr_ceiling)}/yr real) |",
          "\nOne step per year; the new level becomes next year's base. Taxes, the mortgage and big purchases "
          "are outside the budget. Big purchases follow the affordability rule: "
          f"*affordable = {c.car_wr_ceiling:.1%} × portfolio − (budget − Social Security − pensions)*, "
          "capped at the planned price.\n",
          f"**In today's dollars** ({g0} budget {money(life0)}): CUT if the portfolio falls below "
          f"**{money(life0 / c.gr_upper)}**, RAISE if it climbs above **{money(life0 / c.gr_lower)}**.\n"]
    if g0 > inp.start_year:
        md += [f"## Bridge years {inp.start_year}-{g0 - 1}: withdrawals are a goal, not a rule\n",
               "Income (work, vests, deferred comp) covers part of spending, so the formula is dormant. "
               "Spend the budget unless the total portfolio falls ~20% below the on-track level; even then, "
               "the first move is one ~10% trim, reassessed each January.\n",
               "| Year | Lifestyle budget | Portfolio draw | Trim if Jan 1 total < | On-track Jan 1 total |",
               "|---|--:|--:|--:|--:|"]
        prev = inp.investable_start
        for _, r in df[df.year < g0].iterrows():
            y = int(r.year)
            draw = r.w_taxable + r.w_trad + r.w_roth
            md.append(f"| {y} | {money(spending_real(y) * infl_factor(y))} | {money(draw)} | "
                      f"{money_m(prev * 0.8)} | {money_m(prev)} |")
            prev = r.total
    md += [f"\n## Master table {g0}+: compare the Jan 1 total to the CUT / RAISE lines\n",
           "| Year | Ages (H/W) | Taxable | Traditional | Roth | **Jan 1 total** | Budget | **CUT if <** | → cut to | **RAISE if >** | → raise to |",
           "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    prev = None
    for _, r in df.iterrows():
        y = int(r.year)
        if y >= g0 and prev is not None:
            life = spending_real(y) * infl_factor(y)
            floor = spending_real(y) * c.gr_floor * infl_factor(y)
            ceil = spending_real(y) * c.gr_ceiling * infl_factor(y)
            md.append(f"| {y} | {r.husband_age}/{r.wife_age} | {money_m(prev.taxable)} | {money_m(prev.trad)} | "
                      f"{money_m(prev.roth)} | **{money_m(prev.total)}** | {money(life)} | "
                      f"**{money_m(life / c.gr_upper)}** | {money(max(life * (1 - c.gr_cut), floor))} | "
                      f"**{money_m(life / c.gr_lower)}** | {money(min(life * (1 + c.gr_raise), ceil))} |")
        prev = r
    md += ["\n## Worked examples\n",
           "- **Flat markets:** total between the lines → STAY (last year + inflation).",
           "- **Bad two-year run:** total below the CUT line → CUT one step; re-check next January.",
           "- **Boom:** total above the RAISE line → RAISE one step (or bank it).",
           "\nThis is a map, not a GPS: real returns are never a smooth 6.5%. Let the thresholds, not "
           "headlines, drive spending."]
    write("Annual_Operating_Plan.md", "\n".join(md))


if __name__ == "__main__":
    load()
    build()
    print("see output/Annual_Operating_Plan.md")
