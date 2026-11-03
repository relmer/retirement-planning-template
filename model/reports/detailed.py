"""detailed.py: headline success rates (three lenses, fixed vs. guardrails), the
longevity ladder, scenario grids, CSV data and charts. Writes output/Detailed_Report.md.
"""
from __future__ import annotations
from common import load, write, money, quick_paths, horizon_text, DATA_OUT, FIG, M
from retirement_model import Config
import analysis as A
import charts as C


def build(quick=False, mats=None):
    inp = M._inp()
    NP = quick_paths(quick, inp.mc_paths)
    mats = mats or A.lens_matrices(NP)
    fixed = A.success_all(Config(), mats)
    gk = A.success_all(Config(guardrails=True), mats)
    young_by = max(inp.husband_birth[0], inp.wife_birth[0])
    ladder = {(m, g): A.depletion_ladder(res[m], young_by, inp.end_year)
              for g, res in (("fixed", fixed), ("gk", gk)) for m in A.LENSES}

    led = A.ledger(Config(), 0.065)
    led.to_csv(DATA_OUT / "ledger_on_track.csv", index=False)
    grid = A.scenario_grid(); grid.to_csv(DATA_OUT / "scenarios.csv", index=False)
    mct = A.monte_carlo_table(n_paths=quick_paths(quick, 2000)); mct.to_csv(DATA_OUT / "claim_ages.csv", index=False)
    sweep = A.success_by_spend(n_paths=quick_paths(quick, 1500)); sweep.to_csv(DATA_OUT / "success_by_spend.csv", index=False)
    roth = A.roth_comparison(); roth.to_csv(DATA_OUT / "roth_comparison.csv", index=False)
    safe = A.safe_spending(target=inp.target_success, n_paths=quick_paths(quick, 1500), guardrails=True)
    first5 = A.first5_text(Config(), 0.065)
    (DATA_OUT / "first5_breakdown.txt").write_text(first5, encoding="utf-8")

    C.portfolio_trajectory(FIG / "portfolio_trajectory.png")
    C.mc_fan(FIG / "fan_pessimistic.png", mats["parametric"], "Pessimistic lens")
    C.mc_fan(FIG / "fan_middle.png", mats["bootstrap"], "Middle lens")
    C.success_curve(FIG / "success_by_spend.png", sweep, inp.spending_real(inp.start_year), inp.target_success)

    md = [f"# Detailed report: {inp.husband_name} & {inp.wife_name}\n",
          f"_Plan horizon {horizon_text(inp)}. {NP:,} paths per lens._\n",
          "## Success by lens\n",
          "| Lens | Fixed spending | With guardrails | 95%-confidence age (younger spouse, guardrails) |",
          "|---|--:|--:|--:|"]
    for m in A.LENSES:
        md.append(f"| {A.LENS_LABEL[m]} | {fixed[m]['success_rate']:.1%} | **{gk[m]['success_rate']:.1%}** | "
                  f"{ladder[(m, 'gk')][95]} |")
    md += [f"\n_Pessimistic = IID-normal returns, {inp.equity_real_mean:.1%} real arithmetic mean, "
           f"{inp.equity_vol:.0%} volatility (~{(inp.equity_real_mean - inp.equity_vol**2 / 2):.1%} geometric). "
           "Middle = 8-year block bootstrap of US real returns 1872-2022. Optimistic = every historical "
           "window (the FICalc method)._\n",
           f"## Sustainable spending\n",
           f"For {inp.target_success:.0%} pessimistic success with guardrails: **{safe['multiplier']:.0%} of plan** "
           f"(~{money(safe['safe_first'])}/yr in {inp.start_year} vs. {money(safe['target_first'])} planned).\n",
           "## Longevity ladder (age of the younger spouse the money lasts to, at least)\n",
           "| Lens | Spending | Success | 75% conf. | 90% conf. | 95% conf. | Typical failure age |",
           "|---|---|--:|:--:|:--:|:--:|:--:|"]
    for g in ("fixed", "gk"):
        for m in A.LENSES:
            d = ladder[(m, g)]
            tf = f"{d['typ_fail']}" if d["typ_fail"] is not None else "n/a"
            md.append(f"| {A.LENS_LABEL[m]} | {'guardrails' if g == 'gk' else 'fixed'} | {d['success']:.1%} | "
                      f"{d[75]} | {d[90]} | {d[95]} | {tf} |")
    md += ["\n## Deterministic ending balance by return and claim age\n", grid.to_markdown(index=False),
           "\n## Social Security claim ages (pessimistic, guardrails)\n", mct.to_markdown(index=False),
           "\n## Success vs. spending level (pessimistic, guardrails)\n", sweep.to_markdown(index=False),
           "\n## Roth conversions (on-track path)\n", roth.to_markdown(index=False),
           "\n## First five years, line by line\n", "```\n" + first5 + "\n```\n",
           "## Figures\n"] + [f"- `output/figures/{f}`" for f in
                              ("portfolio_trajectory.png", "fan_pessimistic.png", "fan_middle.png", "success_by_spend.png")]
    write("Detailed_Report.md", "\n".join(md))
    return dict(fixed=fixed, gk=gk, ladder=ladder, safe=safe, mats=mats, paths=NP)


if __name__ == "__main__":
    load()
    build()
    print("see output/Detailed_Report.md")
