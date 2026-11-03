"""retire_sweep.py: retire as planned vs. work 1, 2, 3, 5 more years (kw_* params).

Skipped when Params.kw_salary is 0. Writes output/Retire_Year_Sweep.md.
    python model/reports/retire_sweep.py
"""
from __future__ import annotations
from common import load, write, money, quick_paths, M
from retirement_model import Config
import analysis as A


def build(quick=False, mats=None):
    inp = M._inp()
    if inp.kw_salary <= 0:
        return None
    mats = mats or A.lens_matrices(quick_paths(quick, 3000))
    plan = inp.spending_real(inp.start_year)
    md = [f"# Retire-year sweep: {inp.husband_name} & {inp.wife_name}\n",
          f"_Keep-working salary {money(inp.kw_salary)} (+{inp.kw_salary_growth:.0%}/yr), bonus {money(inp.kw_bonus)}, "
          f"401(k) {inp.kw_401k_pct:.0%} + {inp.kw_match_pct:.0%} match. Guardrails on._\n",
          "| Retire in | Extra years | Pessimistic | Middle | Optimistic |", "|---|--:|--:|--:|--:|"]
    rows = []
    for extra in (0, 1, 2, 3, 5):
        R = inp.start_year + extra
        if R >= inp.end_year:
            break
        cfg = Config(guardrails=True, retire_year=None if extra == 0 else R)
        res = A.success_all(cfg, mats)
        rows.append((R, extra, res))
        md.append(f"| {R} | {extra} | **{res['parametric']['success_rate']:.0%}** | "
                  f"{res['bootstrap']['success_rate']:.0%} | {res['cyclical']['success_rate']:.0%} |")
    md.append("\n_Row 0 is the plan as entered (EarnedIncome, vests, deferred comp). Later rows replace "
              "EarnedIncome with the kw_* salary until the retire year; the planned lifestyle "
              f"({money(plan)}/yr) applies throughout._")
    write("Retire_Year_Sweep.md", "\n".join(md))
    return rows


if __name__ == "__main__":
    load()
    build()
    print("see output/Retire_Year_Sweep.md")
