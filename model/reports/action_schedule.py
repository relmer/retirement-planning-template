"""action_schedule.py: every dated thing the household has to do.

Month by month for the next ~15 months (share sales to fund spending, estimated
tax payments, bills not paid by escrow, healthcare enrollment windows, Roth
conversions, RMDs, vests, custom actions), then milestones by year to the horizon.
Writes output/Action_Schedule.md.  python model/reports/action_schedule.py
"""
from __future__ import annotations
import calendar
import datetime as dt
from collections import defaultdict

from common import load, write, money, money_m, first_portfolio_funded_year, TODAY, OUTPUT, M
from retirement_model import Config, run_deterministic, spending_real, infl_factor
from inputs_io import to_date


def add_months(d: dt.date, n: int) -> dt.date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def build(quick=False):
    inp = M._inp()
    c = Config().resolved()
    led = run_deterministic(Config(), 0.065).set_index("year")
    g0 = first_portfolio_funded_year(inp)
    win_start = dt.date(TODAY.year, TODAY.month, 1)
    win_end = dt.date(max(TODAY.year + 1, inp.start_year), 12, 31)
    ev = []   # (date, category, text)
    E = lambda d, cat, txt: ev.append((d, cat, txt))
    mortgage_end = max([f["end_year"] for f in inp.fixed_payments if "mortgage" in f["item"].lower()],
                       default=None)
    retire = inp.retire_date
    has_hsa = any("hsa" in a["account"].lower() for a in inp.accounts)

    for y in range(inp.start_year, inp.end_year + 1):
        if y not in led.index:
            continue
        r = led.loc[y]
        ages = {w: y - inp.birth(w)[0] for w in ("husband", "wife")}
        jan = dt.date(y, 1, 2)
        budget = spending_real(y) * infl_factor(y)
        if y >= g0:
            prev_total = led.loc[y - 1].total if (y - 1) in led.index else inp.investable_start
            E(jan, "Budget", f"Value every account as of Dec 31. Withdrawal-rate check: budget {money(budget)} ÷ "
              f"portfolio. CUT one step if the total is under {money_m(budget / c.gr_upper)}, RAISE if over "
              f"{money_m(budget / c.gr_lower)} (on-track: {money_m(prev_total)}). Set this year's budget.")
        else:
            E(jan, "Budget", f"Set this year's budget ({money(budget)} planned). Bridge year: income covers part; "
              "trim ~10% only if the portfolio is ~20% below the on-track level (Annual_Operating_Plan.md).")
        E(jan, "Upkeep", "Refresh Inputs.xlsx (Dec 31 balances, new exports into private/), re-run "
          "`python model/run.py`, review Preflight.md. Rebalance to the target allocation.")
        E(jan, "Upkeep", "Review beneficiaries on every account and insurance policy.")
        lumpy = sum(b["annual"] for b in inp.bills
                    if b["paid_via"] != "escrow" or (mortgage_end is not None and y > mortgage_end))
        if lumpy:
            E(jan, "Cash", f"Move the year's lumpy-bill total ({money(lumpy * infl_factor(y))}) into the bills "
              "savings account so a guardrail cut never touches it.")
        draw = r.w_taxable + r.w_trad + r.w_roth
        if draw > 0:
            src = ", ".join(n for n, v in (("taxable", r.w_taxable), ("traditional", r.w_trad), ("Roth", r.w_roth)) if v > 0)
            for q, mo in enumerate((1, 4, 7, 10), 1):
                E(dt.date(y, mo, 5), "Sell", f"Q{q} sale: ~{money(draw / 4)} from {src} (highest-basis lots first) "
                  "to refill checking for the next 3 months.")
        working = retire is not None and y <= retire.year and r.earned > 0
        tax = r.fed_tax + r.state_tax
        if tax > 0 and not working:
            for d, lbl in ((dt.date(y, 4, 15), "Q1"), (dt.date(y, 6, 15), "Q2"),
                           (dt.date(y, 9, 15), "Q3"), (dt.date(y + 1, 1, 15), "Q4")):
                E(d, "Tax", f"{y} estimated tax {lbl}: federal ~{money(r.fed_tax / 4)} (IRS Direct Pay), "
                  f"state ~{money(r.state_tax / 4)} ({inp.state}). Alternative: withhold the year's tax from a "
                  "December IRA distribution, which the IRS treats as paid evenly.")
        E(dt.date(y, 4, 15), "Tax", f"File {y - 1} federal and {inp.state} returns (extension = more time to file, not to pay).")
        for b in inp.bills:
            via = b["paid_via"]
            if via == "escrow" and mortgage_end is not None and y > mortgage_end:
                via = "manual (escrow ended with the mortgage)"
            for mo in b["due_months"]:
                amt = b["annual"] * infl_factor(y) / max(1, len(b["due_months"]))
                verb = {"escrow": "Escrow pays", "autopay": "Autopay"}.get(via, "PAY")
                E(dt.date(y, mo, 1), "Bills", f"{verb}: {b['item']} ~{money(amt)} ({via}).")
        if r.conversion > 0:
            E(dt.date(y, 12, 1), "Roth", f"Roth conversion ~{money(r.conversion)} (traditional → Roth); fund the tax "
              "from the taxable account. Check the IRMAA tier first (Preflight.md).")
        if r.rmd > 0:
            E(dt.date(y, 12, 15), "RMD", f"Take RMDs (~{money(r.rmd)} total) by Dec 31.")
        if any(a >= 71 for a in ages.values()):
            E(dt.date(y, 11, 15), "Tax", "Charitable giving: use a qualified charitable distribution (QCD) from an IRA "
              "instead of cash (counts toward the RMD, excluded from income).")
        E(dt.date(y, 11, 1), "Upkeep", f"Update model/data/federal_tax.json and state_tax/{inp.state}.json to "
          f"{y + 1} law when published.")
        if any(a < 65 for a in ages.values()) and not working:
            E(dt.date(y, 11, 1), "Health", "ACA open enrollment Nov 1 - Jan 15: re-shop the marketplace plan; "
              "report expected income (MAGI) accurately.")
        if y in inp.payout_years:
            E(dt.date(y, 1, 20), "Income", f"Deferred-comp installment ~{money(r.dcp)} (taxed as wages; check withholding).")
        if y in inp.big_purchases:
            E(dt.date(y, 1, 3), "Big purchase", f"Planned this year: ~{money(inp.big_purchases[y] * infl_factor(y))}. "
              f"Apply the affordability rule ({c.car_wr_ceiling:.1%} × portfolio − (budget − SS − pensions)).")
        if mortgage_end == y:
            E(dt.date(y, 12, 1), "Mortgage", "Final mortgage payment. Escrow ends: pay property tax and homeowners "
              "insurance directly from next year (Bills).")

    for _, vd, amt in inp.equity_vests:
        d = to_date(vd)
        if d:
            E(d, "Income", f"Equity vest ~{money(amt)}: sell at vest to diversify. Default withholding (22% federal) "
              "is usually too low; add the difference to the next estimated payment.")
    for p in inp.pensions:
        E(dt.date(p["start_year"] - 1, 10, 1), "Income", f"Apply for {inp.name(inp.owner_key(p['person']))}'s "
          f"{p['kind']} (starts {p['start_year']}, ~{money(p['annual'])}/yr). Choose the survivor option deliberately "
          f"(model assumes {p['survivor_pct']:.0%}).")
    for w in ("husband", "wife"):
        by, bm, _ = inp.birth(w)
        nm = inp.name(w)
        m65 = dt.date(by + 65, bm, 1)
        E(add_months(m65, -3), "Health", f"{nm}: Medicare initial enrollment window opens (3 months before the "
          f"65th-birthday month, {m65:%b %Y}). Enroll in Parts A and B; choose Medigap (6-month guaranteed-issue "
          "window starts with Part B) or Medicare Advantage, plus Part D.")
        if has_hsa:
            E(add_months(m65, -6), "Health", f"{nm}: stop HSA contributions 6 months before Medicare starts "
              "(Part A is retroactive up to 6 months).")
        E(m65, "Health", f"{nm}: if income fell after retirement, file SSA-44 (life-changing event) to lower IRMAA.")
        claim = c.husband_claim_age if w == "husband" else c.wife_claim_age
        cm = dt.date(by + claim, bm, 1)
        E(add_months(cm, -3), "Social Security", f"{nm}: apply for Social Security at ssa.gov (benefit starts "
          f"{cm:%b %Y}, age {claim}).")
        E(add_months(dt.date(by + 59, bm, 1), 6), "Milestone", f"{nm} reaches 59½: IRA/401(k) withdrawals "
          "become penalty-free.")
        ra = M.rmd_start_age(by)
        E(dt.date(by + ra, 12, 1), "RMD", f"{nm} reaches RMD age {ra}: first RMD is due by April 1 next year, "
          "but take it by Dec 31 to avoid two RMDs in one tax year.")
    if retire:
        E(retire, "Health", "Last day of work: employer health coverage ends (usually at month end).")
        if inp.cobra_months > 0:
            E(retire + dt.timedelta(days=60), "Health", "COBRA election deadline (about 60 days after coverage ends "
              "or the notice arrives, whichever is later). Coverage is retroactive.")
            cend = add_months(retire, inp.cobra_months)
            E(add_months(cend, -2), "Health", f"COBRA ends {cend:%b %Y}: enroll in a marketplace plan "
              "(special enrollment period starts 60 days before coverage ends).")
        else:
            E(retire, "Health", "Enroll in replacement coverage (marketplace special enrollment: 60 days).")
    E(win_start, "Upkeep", "Wills, powers of attorney, healthcare directives: review now and every 3-5 years.")
    for a in inp.actions:
        amt = f" ({money(float(a['amount']))})" if a["amount"] not in (None, "") else ""
        E(a["date"], "Action", f"{a['action']}{amt}. {a['notes']}".strip())

    # ---------------- render ----------------
    by_month = defaultdict(list)
    later = defaultdict(list)
    for d, cat, txt in sorted(ev, key=lambda e: (e[0], e[1])):
        if win_start <= d <= win_end:
            by_month[(d.year, d.month)].append((d, cat, txt))
        elif (d > win_end and cat not in ("Bills", "Sell", "Tax", "Upkeep", "Budget", "Cash")
              and not txt.startswith(("Take RMDs", "ACA open enrollment"))):
            later[d.year].append((d, cat, txt))
    md = [f"# Action schedule: {inp.husband_name} & {inp.wife_name}\n",
          f"_Generated {TODAY.isoformat()} from the on-track plan (6.5% real). Amounts are estimates: re-run each "
          "January with actual balances and the amounts update._\n",
          f"## Next {len(by_month)} months, month by month\n"]
    for (yy, mm) in sorted(by_month):
        md.append(f"### {calendar.month_name[mm]} {yy}\n")
        for d, cat, txt in by_month[(yy, mm)]:
            md.append(f"- [ ] **{d:%b %d}** · {cat}: {txt}")
        md.append("")
    md += ["## Every year (the rhythm)\n",
           "| When | What |", "|---|---|",
           "| Early January | Dec 31 balances → withdrawal-rate check → set the budget. Refresh Inputs.xlsx and re-run. Rebalance. Fund the bills account. Review beneficiaries. |",
           "| Jan / Apr / Jul / Oct | Sell one quarter of the year's draw (highest-basis lots first). |",
           "| Apr 15 / Jun 15 / Sep 15 / Jan 15 | Federal and state estimated tax payments (or one withholding from a December IRA distribution). |",
           "| Apr 15 | File last year's returns. |",
           "| November | Update tax-law files; ACA open enrollment while under 65; Medicare open enrollment Oct 15 - Dec 7 once on Medicare. |",
           "| December | Roth conversion (if planned), RMDs, charitable QCDs. |",
           "", "## Milestones by year\n", "| Year | Ages (H/W) | Milestones |", "|---|---|---|"]
    for yy in sorted(later):
        a = f"{yy - inp.husband_birth[0]}/{yy - inp.wife_birth[0]}"
        items = "<br>".join(f"{d:%b}: {txt}" for d, cat, txt in later[yy])
        md.append(f"| {yy} | {a} | {items} |")
    write("Action_Schedule.md", "\n".join(md))
    write_ics(inp, [e for m in by_month.values() for e in m] + [e for y in later.values() for e in y])
    return dict(months=len(by_month))


def write_ics(inp, events):
    """All-day calendar events (output/Action_Schedule.ics) for import into any calendar app."""
    esc = lambda s: s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//retirement-planning-template//action-schedule//EN",
             f"X-WR-CALNAME:Retirement plan ({inp.husband_name} & {inp.wife_name})"]
    for i, (d, cat, txt) in enumerate(sorted(events, key=lambda e: e[0])):
        summary = txt if len(txt) <= 70 else txt[:67].rsplit(" ", 1)[0] + "..."
        lines += ["BEGIN:VEVENT", f"UID:{d:%Y%m%d}-{i}@retirement-plan", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + dt.timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{esc(cat + ': ' + summary)}", f"DESCRIPTION:{esc(txt)}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    (OUTPUT / "Action_Schedule.ics").write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")


if __name__ == "__main__":
    load()
    build()
    print("see output/Action_Schedule.md")
