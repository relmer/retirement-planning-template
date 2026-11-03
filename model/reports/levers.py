"""levers.py: what raises the PESSIMISTIC (parametric) chance of success?

Each lever runs on the same return paths (common random numbers) with guardrails
ON, so differences reflect the lever, not Monte Carlo noise. Ranked by gain.
Writes output/Levers.md and output/data/levers.csv.

    python model/reports/levers.py
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from common import load, write, money, money_m, quick_paths, DATA_OUT, M
from retirement_model import Config

BOND_REAL_MEAN, BOND_VOL = 0.018, 0.06   # ASSUMPTION: intermediate bonds, real


def _blend(eq, bnd, w):
    return eq * w[None, :] + bnd * (1 - w)[None, :]


def build(quick=False):
    inp = M._inp()
    NP = quick_paths(quick, 6000)
    n_years = inp.end_year - inp.start_year + 1
    years = np.arange(inp.start_year, inp.end_year + 1)
    EQ = M.parametric_returns(NP)
    bond_nom = (1 + BOND_REAL_MEAN) * (1 + inp.inflation) - 1
    BND = np.random.default_rng(inp.mc_seed + 1).normal(bond_nom, BOND_VOL, (NP, n_years))
    allocs = {
        "100/0": EQ,
        "60/40": _blend(EQ, BND, np.full(n_years, 0.60)),
        # bond tent: 40% stocks at the start, +3 pts/yr to 70%
        "tent": _blend(EQ, BND, np.clip(0.40 + 0.03 * (years - inp.start_year), 0.40, 0.70)),
    }
    real_den = (1 + inp.inflation) ** (inp.end_year - inp.start_year)
    hc, wc = inp.default_husband_claim_age, inp.default_wife_claim_age
    older = "husband" if inp.husband_birth[0] <= inp.wife_birth[0] else "wife"

    tests = [("Current plan (workbook defaults)", "100/0", {}, None)]
    for h, w in ((70, wc), (hc, 70), (70, 70), (70, 67), (67, 67), (62, 62)):
        if (h, w) != (hc, wc):
            tests.append((f"Social Security: {inp.husband_name} at {h}, {inp.wife_name} at {w}", "100/0",
                          dict(husband_claim_age=h, wife_claim_age=w), None))
    tests += [
        ("Spend 5% less", "100/0", dict(spend_multiplier=0.95), None),
        ("Spend 10% less", "100/0", dict(spend_multiplier=0.90), None),
        (f"Accept a deeper guardrail floor ({max(inp.gr_floor - 0.10, 0.4):.2f})", "100/0",
         dict(gr_floor=max(inp.gr_floor - 0.10, 0.4)), None),
        ("Big purchases cut in half", "100/0", {}, "bp_half"),
        ("Roth conversions: fill to $150k taxable income", "100/0", dict(roth_conversion_ceiling=150_000), None),
        ("Allocation 60/40 stocks/bonds", "60/40", {}, None),
        ("Allocation: bond tent (40% -> 70% stocks)", "tent", {}, None),
        (f"Part-time work: $30k/yr for 5 years", "100/0", dict(earned_income={
            y: inp.earned_income.get(y, 0.0) + 30_000 * M.infl_factor(y)
            for y in range(inp.start_year, inp.start_year + 5)}), None),
    ]
    if inp.kw_salary > 0:
        for k in (1, 2, 3):
            tests.append((f"Work {k} more year{'s' if k > 1 else ''} (kw_* params)", "100/0",
                          dict(retire_year=inp.start_year + k), None))
    stress = [
        ("STRESS: Social Security cut to 77% from " + str(inp.ss_cut_year), "100/0", dict(ss_cut_factor=0.77), None),
        (f"STRESS: {inp.name(older)} dies at {inp.survivor_test_age}", "100/0",
         dict(first_death_age=inp.survivor_test_age, first_to_die=older), None),
        ("STRESS: spending 10% over plan", "100/0", dict(spend_multiplier=1.10), None),
    ]

    rows = []
    for label, alloc, kw, special in tests + stress:
        saved = inp.big_purchases
        if special == "bp_half":
            inp.big_purchases = {y: v * 0.5 for y, v in saved.items()}
        try:
            r = M.run_monte_carlo_vectorized(Config(guardrails=True, **kw), _returns=allocs[alloc])
        finally:
            inp.big_purchases = saved
        rows.append(dict(lever=label, success=r["success_rate"], median_end_real=r["median_ending"] / real_den,
                         stress=label.startswith("STRESS")))
    df = pd.DataFrame(rows)
    base = df.iloc[0]["success"]
    df["gain_pts"] = (df["success"] - base) * 100
    df.to_csv(DATA_OUT / "levers.csv", index=False)

    target = inp.target_success
    md = [f"# Levers: how to raise the chance of success\n",
          f"_Pessimistic (parametric) lens, {NP:,} paths, guardrails on (floor {inp.gr_floor:.2f}x). "
          f"Success = money lasts through {inp.end_year}. Every row uses the same return paths. "
          f"Target: {target:.0%}._\n",
          f"**Current plan: {base:.1%}** {'✅ meets' if base >= target else '❌ below'} the {target:.0%} target.\n",
          "## Levers, best first\n",
          "| Lever | Success | Change | Median ending wealth (today's $) |", "|---|--:|--:|--:|"]
    lev = df[(~df.stress) & (df.index > 0)].sort_values("success", ascending=False)
    for _, r in lev.iterrows():
        flag = " ✅" if r.success >= target else ""
        md.append(f"| {r.lever}{flag} | {r.success:.1%} | {r.gain_pts:+.1f} pts | {money_m(r.median_end_real)} |")
    md += ["\n## Stress tests (the plan's fragility)\n",
           "| Stress | Success | Change |", "|---|--:|--:|"]
    for _, r in df[df.stress].iterrows():
        md.append(f"| {r.lever.replace('STRESS: ', '')} | {r.success:.1%} | {r.gain_pts:+.1f} pts |")
    md.append("\n_Bonds: real return 1.8%, volatility 6%, independent of stocks (an assumption). "
              "Levers combine roughly additively for small changes; test any combination by adding a row "
              "to `tests` in model/reports/levers.py._")
    write("Levers.md", "\n".join(md))
    top = [r for _, r in lev.iterrows() if r.gain_pts > 0.5][:5]
    return dict(base=base, top=top, stress=[r for _, r in df[df.stress].iterrows()], paths=NP)


if __name__ == "__main__":
    load()
    out = build()
    print(f"current {out['base']:.1%}; see output/Levers.md")
