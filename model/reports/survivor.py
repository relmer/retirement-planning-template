"""survivor.py: what happens to the surviving spouse?

After the first death the survivor files single (higher tax brackets on similar
income), keeps the larger of the two Social Security benefits, receives the
survivor share of each pension, and spends Params.survivor_spend_pct of the
couple's budget. Writes output/Survivor.md.

    python model/reports/survivor.py
"""
from __future__ import annotations
from common import load, write, money, quick_paths, M
from retirement_model import Config, run_deterministic
import analysis as A


def build(quick=False, mats=None):
    inp = M._inp()
    mats = mats or A.lens_matrices(quick_paths(quick, 3000))
    base = A.success_all(Config(guardrails=True), mats)
    ages = sorted({70, inp.survivor_test_age, 85})
    rows = []
    for who in ("husband", "wife"):
        for age in ages:
            if inp.birth(who)[0] + age > inp.end_year:
                continue
            cfg = Config(guardrails=True, first_death_age=age, first_to_die=who)
            res = A.success_all(cfg, mats)
            led = run_deterministic(Config(first_death_age=age, first_to_die=who), 0.065)
            led0 = run_deterministic(Config(), 0.065)
            y = inp.birth(who)[0] + age + 1
            after = led[led.year == y]
            before = led0[led0.year == y]
            if after.empty:
                continue
            a, b = after.iloc[0], before.iloc[0]
            rows.append(dict(who=who, age=age, year=y, res=res,
                             income_drop=(b.ss + b.pension) - (a.ss + a.pension),
                             tax_change=a.tax - b.tax * inp.survivor_spend_pct))
    md = ["# Survivor scenarios\n",
          f"_Each row: one spouse dies in the year they reach the age shown; the survivor lives to {inp.end_year}. "
          f"Survivor spending = {inp.survivor_spend_pct:.0%} of the couple's budget. Guardrails on._\n",
          "| Scenario | Pessimistic | Middle | Optimistic | Guaranteed income lost (first year, nominal) |",
          "|---|--:|--:|--:|--:|",
          f"| Both live to the horizon | **{base['parametric']['success_rate']:.0%}** | "
          f"{base['bootstrap']['success_rate']:.0%} | {base['cyclical']['success_rate']:.0%} | |"]
    for r in rows:
        md.append(f"| {inp.name(r['who'])} dies at {r['age']} ({r['year'] - 1}) | "
                  f"**{r['res']['parametric']['success_rate']:.0%}** | {r['res']['bootstrap']['success_rate']:.0%} | "
                  f"{r['res']['cyclical']['success_rate']:.0%} | {money(r['income_drop'])} |")
    md += ["\n## What to do with this\n",
           "- A survivor scenario that lowers success is the single-filer 'widow's tax' plus the lost Social "
           "Security check and pension share. Roth conversions while both spouses are alive (MFJ brackets) reduce it.",
           "- Delaying the higher earner's Social Security to 70 maximizes the survivor benefit.",
           "- Pension elections (joint-and-survivor percentage) and life insurance are the other levers.",
           "- Make sure beneficiaries on every account are current; see Action_Schedule.md."]
    write("Survivor.md", "\n".join(md))
    worst = min(rows, key=lambda r: r["res"]["parametric"]["success_rate"]) if rows else None
    return dict(rows=rows, worst=worst, base=base)


if __name__ == "__main__":
    load()
    build()
    print("see output/Survivor.md")
