"""summary.py: output/START_HERE.md, the one page to read first."""
from __future__ import annotations
from common import write, money, horizon_text, TODAY, M
import analysis as A

DOCS = [
    ("START_HERE.md", "This page: the answer, how to improve it, and the guide to everything else.", "Once, then after each annual re-run."),
    ("Preflight.md", "Stale data, inconsistent inputs, and known model limitations this household is exposed to.", "Before trusting any number. Clear every 🛑; decide on every ⚠️."),
    ("Action_Schedule.md", "Checklist of every dated task: quarterly share sales, estimated taxes, bills not paid by escrow, COBRA/ACA/Medicare windows, Social Security applications, Roth conversions, RMDs, vests, custom actions.", "Put the next 15 months on the calendar. Re-generate each January."),
    ("Action_Schedule.ics", "The same dates as calendar events.", "Import into Google, Outlook or Apple Calendar (re-import after each annual re-run)."),
    ("Annual_Operating_Plan.md", "The once-a-year spending rule: withdrawal-rate guardrails with the CUT / RAISE portfolio thresholds pre-computed for every year.", "Each January: compare the Dec 31 total to that year's lines and set the budget."),
    ("Draw_Schedule.md", "Which account to sell from each year, when Social Security starts, federal and state tax by year, and the Roth-conversion comparison.", "When deciding where each quarter's cash comes from, and each December for conversions."),
    ("Levers.md", "Every change that raises the pessimistic chance of success, ranked, plus stress tests.", "When the plan misses the target, or to buy more margin."),
    ("Survivor.md", "What happens to the surviving spouse (single tax brackets, one Social Security check, pension survivor share).", "When choosing claim ages, pension options, life insurance, and Roth conversions."),
    ("Retire_Year_Sweep.md", "Retire as planned vs. working 1-5 more years (only when kw_salary is set).", "The 'one more year?' decision."),
    ("Detailed_Report.md", "All the numbers: longevity ladder, claim-age table, spending curve, scenario grid, first five years line by line.", "Reference, and to sanity-check the model."),
    ("data/, figures/", "CSV data behind every table, and charts.", "For your own analysis."),
]


def build(pre_n, pre_F, det, lev, surv, sweep):
    inp = M._inp()
    target = inp.target_success
    p_gk = det["gk"]["parametric"]["success_rate"]
    md = [f"# Your retirement plan: {inp.husband_name} & {inp.wife_name}\n",
          f"_Generated {TODAY.isoformat()} from Inputs.xlsx. Plan horizon {horizon_text(inp)}._\n"]
    if pre_n["BLOCKER"] or pre_n["WARN"]:
        md.append(f"> **Preflight: {pre_n['BLOCKER']} blocker(s), {pre_n['WARN']} warning(s).** "
                  "Read [Preflight.md](Preflight.md) first. "
                  + ("Results below are NOT meaningful until the blockers are fixed." if pre_n["BLOCKER"] else ""))
        for f in [f for f in pre_F if f["level"] == "BLOCKER"][:5]:
            md.append(f"> - 🛑 {f['area']}: {f['msg']}")
        md.append("")
    md += ["## The answer\n",
           f"Chance the money lasts through {inp.end_year}:\n",
           "| Return outlook | Fixed spending | With guardrails |", "|---|--:|--:|"]
    for m in A.LENSES:
        b = "**" if m == "parametric" else ""
        md.append(f"| {b}{A.LENS_LABEL[m]}{b} | {b}{det['fixed'][m]['success_rate']:.0%}{b} | "
                  f"{b}{det['gk'][m]['success_rate']:.0%}{b} |")
    verdict = ("✅ **meets**" if p_gk >= target else "❌ **misses**")
    md += ["",
           f"**Plan on the pessimistic number: {p_gk:.0%}** with guardrails, which {verdict} the "
           f"{target:.0%} target.\n",
           "Why pessimistic: the historical lenses replay the best-performing large stock market of the last "
           "150 years and assume the future looks like it. Starting valuations today are high, and a plan "
           "that only works under the historical lenses depends on luck. A plan built on the pessimistic lens "
           "that turns out better than expected leads to raising spending later (the guardrails do that "
           "automatically). One built on the optimistic lens that turns out worse leads to cuts in your 80s, "
           "when there is no way to go back to work.\n",
           f"**Guardrails** mean adjusting spending each January by the rule in "
           f"[Annual_Operating_Plan.md](Annual_Operating_Plan.md): cut 10% after bad years, raise 10% after good "
           f"years, never below {inp.gr_floor:.0%} of plan (about {money(inp.spending_real(inp.start_year) * inp.gr_floor)}/yr "
           "in today's dollars). The 'fixed spending' column assumes no adjustment ever, which nobody actually does.\n",
           f"Sustainable lifestyle for {target:.0%} pessimistic success: **~{money(det['safe']['safe_first'])}/yr** "
           f"(plan: {money(det['safe']['target_first'])}).\n",
           "## How to raise the odds\n"]
    if lev["top"]:
        md += ["Ranked by gain on the pessimistic lens (full list: [Levers.md](Levers.md)):\n",
               "| Lever | Success | Gain |", "|---|--:|--:|"]
        for r in lev["top"]:
            md.append(f"| {r.lever} | {r.success:.0%} | {r.gain_pts:+.0f} pts |")
    else:
        md.append("No single lever adds more than half a point. The plan is at its practical maximum, or "
                  "comfortably above it.")
    md += ["\n## Stress tests\n", "| Stress | Pessimistic success | Change |", "|---|--:|--:|"]
    for r in lev["stress"]:
        md.append(f"| {r.lever.replace('STRESS: ', '')} | {r.success:.0%} | {r.gain_pts:+.0f} pts |")
    if surv and surv["worst"]:
        w = surv["worst"]
        md.append(f"\nWorst survivor case: {inp.name(w['who'])} dies at {w['age']} → "
                  f"{w['res']['parametric']['success_rate']:.0%} pessimistic ([Survivor.md](Survivor.md)).")
    if sweep:
        md.append("\nWorking longer: " + ", ".join(
            f"retire {R}: {res['parametric']['success_rate']:.0%}" for R, _, res in sweep)
            + " ([Retire_Year_Sweep.md](Retire_Year_Sweep.md)).")
    md += ["\n## Your documents\n", "| Document | What it is | How to use it |", "|---|---|---|"]
    for name, what, how in DOCS:
        if name == "Retire_Year_Sweep.md" and not sweep:
            continue
        link = f"[{name}]({name})" if name.endswith(".md") else name
        md.append(f"| {link} | {what} | {how} |")
    md += ["\n## Keeping it current\n",
           "- **Every January:** export Dec 31 balances into `private/`, update Inputs.xlsx, run "
           "`python model/run.py`, then follow the new Action_Schedule.md.",
           "- **After every change:** commit to the local history (`git add -A && git commit -m \"...\"`) "
           "so each version of the plan is kept. The folder lives in OneDrive, which backs it up.",
           "- **Every November:** update the federal and state tax-law files for the coming year (Preflight flags them).",
           "- **Any life change** (health, move to another state, inheritance, job offer, home sale, a big market drop) "
           "→ update the inputs and re-run.",
           "- This is a planning model, not financial, tax or legal advice. Review the plan with a fee-only "
           "fiduciary advisor or CPA before acting on large, irreversible decisions (claim ages, pension "
           "elections, Roth conversions, annuities)."]
    write("START_HERE.md", "\n".join(md))
