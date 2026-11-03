"""draw_schedule.py: which account funds each year, and the Roth-conversion comparison.

Writes output/Draw_Schedule.md.  python model/reports/draw_schedule.py
"""
from __future__ import annotations
from common import load, write, money, M
from retirement_model import Config, run_deterministic, ss_benefit_year


def draw_source(r):
    parts = [n for n, v in (("Taxable", r.w_taxable), ("Traditional", r.w_trad), ("Roth", r.w_roth)) if v > 0]
    if r.rmd > 0:
        return "RMD + " + "+".join(parts) if parts else "RMDs cover"
    if not parts:
        return "(income covers)" if r.total > 0 else "depleted"
    return "+".join(parts)


def build(quick=False):
    inp = M._inp()
    c = Config().resolved()
    df = run_deterministic(Config(), 0.065)
    md = ["# Draw schedule: which account funds each year\n",
          f"_On-track path: 6.5% real, claim {c.husband_claim_age}/{c.wife_claim_age}, Roth conversion ceiling "
          f"{money(c.roth_conversion_ceiling)}. Nominal dollars. Draw order: taxable → traditional → Roth._\n"]
    for w in ("husband", "wife"):
        claim = c.husband_claim_age if w == "husband" else c.wife_claim_age
        y = inp.birth(w)[0] + claim
        md.append(f"- {inp.name(w)} claims Social Security at {claim} in **{y}**: "
                  f"{money(ss_benefit_year(w, claim, inp.birth(w), y + 1))}/yr (first full year, nominal).")
    md += ["", "| Year | Ages | Draw | Source | Roth conv. | Big purchase | SS + pension | Fed tax | State tax | Year-end total |",
           "|---|--:|--:|---|--:|--:|--:|--:|--:|--:|"]
    for _, r in df.iterrows():
        y = int(r.year)
        draw = r.w_taxable + r.w_trad + r.w_roth
        bb = inp.big_purchases.get(y, 0.0) * M.infl_factor(y)
        md.append(f"| {y} | {r.husband_age}/{r.wife_age} | {money(draw)} | {draw_source(r)} | "
                  f"{money(r.conversion) if r.conversion else ''} | {money(bb) if bb else ''} | "
                  f"{money(r.ss + r.pension)} | {money(r.fed_tax)} | {money(r.state_tax)} | {money(r.total)} |")
    md += ["\n## Roth-conversion comparison (on-track path)\n",
           "| Fill ordinary taxable income to (today's $) | Lifetime federal tax | Lifetime state tax | Ending total |",
           "|--:|--:|--:|--:|"]
    for cc in (0, 100_000, 150_000, 200_000, 300_000):
        d = run_deterministic(Config(roth_conversion_ceiling=cc), 0.065)
        md.append(f"| {money(cc)} | {money(d.fed_tax.sum())} | {money(d.state_tax.sum())} | {money(d.iloc[-1].total)} |")
    md.append("\n_Conversions trade tax now for less tax (and smaller RMDs) later. They also raise MAGI, which "
              "can trigger IRMAA two years later and reduce ACA credits: see Preflight.md._")
    write("Draw_Schedule.md", "\n".join(md))
    return df


if __name__ == "__main__":
    load()
    build()
    print("see output/Draw_Schedule.md")
