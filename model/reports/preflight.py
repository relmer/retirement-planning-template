"""preflight.py: staleness, consistency, and known-limitation exposure checks.

Run automatically at the start of model/run.py; also standalone:
    python model/reports/preflight.py

Every finding has a level:
    BLOCKER  results are not meaningful until fixed
    WARN     results may be wrong for this household; fix or acknowledge
    INFO     limitation or assumption worth knowing
Writes output/Preflight.md and returns the findings list.
"""
from __future__ import annotations
import datetime as dt
import re
import subprocess
import sys

from common import load, write, money, ROOT, TODAY, M
from retirement_model import Config, run_deterministic, law_factor
from inputs_io import to_date

STALE_BALANCE_DAYS = 92
STALE_FILE_DAYS = 365
DATE_PREFIX = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _git(*args):
    try:
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def year_ranges(ys):
    """[2027, 2028, 2030] -> '2027-2028, 2030'."""
    out, ys = [], sorted(ys)
    for y in ys:
        if out and y == out[-1][1] + 1:
            out[-1][1] = y
        else:
            out.append([y, y])
    return ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in out)


def run_checks(inp):
    F = []
    add = lambda level, area, msg, fix="": F.append(dict(level=level, area=area, msg=msg, fix=fix))
    ages_at = lambda y: {w: y - inp.birth(w)[0] for w in ("husband", "wife")}

    # ---------------- data identity ----------------
    if "SAMPLE DATA" in str(inp.params.get("household", "")):
        add("BLOCKER", "Inputs", "Inputs.xlsx contains the fictional sample household.",
            "Run the interview in AGENTS.md, then change Params.household to your own label.")

    # ---------------- tax law freshness ----------------
    fed_year = M.FED["tax_year"]
    if fed_year < TODAY.year:
        add("WARN", "Federal tax law",
            f"model/data/federal_tax.json has {fed_year} figures; the current tax year is {TODAY.year}.",
            f"Update every value to {TODAY.year} law (IRS Rev. Proc. for {TODAY.year}, SSA wage base, "
            "CMS IRMAA tiers, HHS poverty guidelines), check for new legislation, set tax_year.")
    st_year = M.STATE["tax_year"]
    if st_year < TODAY.year:
        add("WARN", "State tax law",
            f"model/data/state_tax/{inp.state}.json has {st_year} figures; the current tax year is {TODAY.year}.",
            f"Verify {M.STATE.get('name', inp.state)} rates, deductions and retirement exclusions for "
            f"{TODAY.year} with the state Department of Revenue; update and set tax_year.")
    sd = M.FED.get("senior_deduction")
    if sd and sd["last_year"] < inp.end_year:
        add("INFO", "Federal tax law",
            f"The senior deduction expires after {sd['last_year']} under current law; the model drops it then.")

    # ---------------- plan timing ----------------
    if inp.start_year < TODAY.year:
        add("WARN", "Timing", f"start_year {inp.start_year} is in the past.",
            f"Set start_year to {TODAY.year if TODAY.month < 10 else TODAY.year + 1} and refresh balances to that date.")

    # ---------------- balances / exports freshness ----------------
    for a in inp.accounts:
        if a["balance"] == 0:
            continue
        if a["as_of"] is None:
            add("WARN", "Accounts", f"'{a['account']}' has no as_of date.", "Record the statement date of the balance.")
        elif (TODAY - a["as_of"]).days > STALE_BALANCE_DAYS:
            add("WARN", "Accounts", f"'{a['account']}' balance is from {a['as_of']} "
                f"({(TODAY - a['as_of']).days} days old).", "Download a fresh export and update the balance.")
        if inp.owner_key(a["owner"]) == "joint" and str(a["owner"]).strip().lower() not in ("joint", "both"):
            add("WARN", "Accounts", f"Owner '{a['owner']}' of '{a['account']}' matches neither spouse; treated as Joint.",
                "Use husband_name, wife_name, or Joint.")
        sf = a.get("source_file")
        if sf and not (ROOT / sf).exists():
            add("INFO", "Accounts", f"source_file for '{a['account']}' is missing: {sf}")
    priv = ROOT / "private"
    if priv.exists():
        for f in priv.rglob("*"):
            if not f.is_file() or f.name.lower() == "readme.md":
                continue
            m = DATE_PREFIX.search(f.name)
            when = None
            if m:
                try:
                    when = dt.date(int(m[1]), int(m[2]), int(m[3]))
                except ValueError:
                    when = None
            when = when or dt.date.fromtimestamp(f.stat().st_mtime)
            if (TODAY - when).days > STALE_FILE_DAYS:
                add("WARN", "Source documents", f"{f.relative_to(ROOT)} is from {when} (over a year old).",
                    "Replace it with a current export or statement.")
    ssd = to_date(inp.params.get("ss_statement_date"))
    if ssd is None:
        add("WARN", "Social Security", "Params.ss_statement_date is blank.", "Record the date of the ssa.gov statements.")
    elif (TODAY - ssd).days > STALE_FILE_DAYS:
        add("WARN", "Social Security", f"SS estimates are from {ssd}.", "Download fresh statements from ssa.gov/myaccount.")
    for w in ("husband", "wife"):
        have = set(inp.ss_monthly[w])
        if not {62, 67, 70} <= have:
            add("WARN", "Social Security", f"{inp.name(w)}: SocialSecurity rows at ages {sorted(have)}; "
                "62, 67 and 70 are required for the claim-age analysis.", "Copy them from the ssa.gov statement.")

    # ---------------- schedule consistency ----------------
    covered = set()
    for s, e, *_ in inp.spending:
        for y in range(s, e + 1):
            if y in covered:
                add("BLOCKER", "Spending", f"Spending bands overlap in {y}.", "Make the bands contiguous.")
            covered.add(y)
    gaps = [y for y in range(inp.start_year, inp.end_year + 1) if y not in covered]
    if gaps:
        add("BLOCKER", "Spending", f"No Spending band covers {gaps[0]}-{gaps[-1]} ({len(gaps)} years).",
            "Extend the bands through end_year.")
    for s, e, amt, hc in inp.spending:
        young = any(a < 65 for a in ages_at(s).values())
        if young and hc == 0:
            add("WARN", "Healthcare", f"Spending {s}-{e} has no healthcare amount while a spouse is under 65.",
                "Enter COBRA / marketplace premiums plus out-of-pocket in the healthcare column.")
    for y in inp.big_purchases:
        if y > inp.end_year or y < inp.start_year:
            add("WARN", "BigPurchases", f"Big purchase in {y} is outside {inp.start_year}-{inp.end_year}.")
    for p in inp.pensions:
        if inp.owner_key(p["person"]) == "joint":
            add("BLOCKER", "Pensions", f"Pension person '{p['person']}' matches neither spouse.")
    escrow = [b for b in inp.bills if b["paid_via"] == "escrow"]
    if escrow and not any("mortgage" in f["item"].lower() for f in inp.fixed_payments):
        add("WARN", "Bills", "Bills are paid via escrow but FixedPayments has no mortgage.",
            "Add the mortgage principal + interest to FixedPayments, or change paid_via.")
    for b in inp.bills:
        if not b["in_spending"]:
            add("WARN", "Bills", f"'{b['item']}' is marked not included in Spending, so the model omits it.",
                "Add it to a Spending band (Bills is only for the action schedule).")
    for f in inp.fixed_payments:
        if "mortgage" in f["item"].lower() and f["end_year"] >= inp.start_year:
            add("INFO", "Mortgage", f"Mortgage payments run through {f['end_year']}. Escrowed property tax and "
                "insurance continue after payoff: confirm the Spending bands after that year still include them.")

    # ---------------- exposure to known limitations ----------------
    if inp.taxable_start > 0 and inp.taxable_dividend_yield == 0:
        add("WARN", "Dividends", "taxable_dividend_yield is 0 with a taxable balance, so dividend/interest tax is omitted.",
            "Set it from the positions export (typically 0.01-0.03).")
    if inp.stock_allocation < 0.85:
        add("WARN", "Allocation", f"Actual stock allocation is {inp.stock_allocation:.0%}; the engine models 100% stocks.",
            "Read the 60/40 and bond-tent rows of Levers.md, which model bonds explicitly.")
    if inp.largest_position_pct > 0.10:
        add("WARN", "Concentration", f"Largest single stock is {inp.largest_position_pct:.0%} of the portfolio; "
            "the model assumes a diversified index.", "Build a de-risking plan (templates/Derisk_Plan.md).")
    if inp.equity_real_mean > 0.07:
        add("WARN", "Returns", f"equity_real_mean {inp.equity_real_mean:.1%} is above the conservative 6.5% default.",
            "The pessimistic lens is only pessimistic at 6.5% or lower.")
    if inp.ss_cut_factor < 1.0:
        add("INFO", "Social Security", f"Benefits are cut to {inp.ss_cut_factor:.0%} from {inp.ss_cut_year} in every run.")

    led = run_deterministic(Config(), 0.065)
    # IRMAA: premiums in year Y are set by MAGI in Y-2; flag MAGI years that land on Medicare years
    irmaa = []
    for _, r in led.iterrows():
        y = int(r.year)
        ages2 = ages_at(y + 2)
        on_medicare = [w for w in ages2 if ages2[w] >= 65]
        if not on_medicare:
            continue
        thr = M.FED["irmaa_first_tier_magi"][r.filing] * law_factor(y, M.FED["tax_year"])
        if r.magi > thr:
            irmaa.append((y, r.magi, thr))
    if irmaa:
        ys = year_ranges([y for y, *_ in irmaa])
        add("WARN", "IRMAA", f"MAGI exceeds the first Medicare IRMAA tier in {len(irmaa)} year(s) ({ys}); the "
            "surcharge on Part B/D premiums applies two years later and is not modeled.",
            "Add the surcharge (roughly $1,000-$5,000 per person per year by tier) to the healthcare column for "
            "those years, or smooth income (Roth conversion size, withdrawal timing) to stay under a tier.")
    # ACA: the premium tax credit depends on MAGI vs 400% FPL while a spouse is under 65 and not on employer coverage
    aca_hi, aca_lo = [], []
    for _, r in led.iterrows():
        y = int(r.year)
        a = ages_at(y)
        n_under = sum(1 for v in a.values() if v < 65)
        if n_under == 0:
            continue
        key = "household_2" if r.filing == "mfj" else "household_1"
        line = M.FED["aca_400pct_fpl"][key] * law_factor(y, M.FED["tax_year"])
        (aca_hi if r.magi > line else aca_lo).append(y)
    if aca_hi:
        add("INFO", "ACA", f"MAGI is above 400% of the poverty line in {year_ranges(aca_hi)} (pre-Medicare): "
            "no premium tax credit under current law.",
            "Confirm the healthcare column uses UNSUBSIDIZED marketplace premiums for those years.")
    if aca_lo:
        add("INFO", "ACA", f"MAGI is under 400% of the poverty line in {year_ranges(aca_lo)} (pre-Medicare): "
            "premium tax credits may apply.",
            "Price the marketplace plan at healthcare.gov with this MAGI; the healthcare column may be overstated.")
    big = led[(led.earned + led.vest + led.conversion) > 400_000]
    if len(big):
        add("INFO", "AMT", f"Ordinary income above $400K in {int(big.year.iloc[0])}: AMT is not modeled.",
            "Ask about incentive stock options and large state-tax deductions; run the year through tax software.")
    for w in ("husband", "wife"):
        age0 = inp.start_year - inp.birth(w)[0]
        if age0 >= M.rmd_start_age(inp.birth(w)[0]):
            add("INFO", "RMD", f"{inp.name(w)} is already of RMD age in {inp.start_year}.",
                "Confirm the current-year RMD has been taken.")

    add("INFO", "Model scope", "Married couple filing jointly; single filing after the first death in the survivor test. "
        "No AMT, no IRMAA, no ACA credit math, no long-term-care event, constant cost-basis fraction, "
        "state tax not deducted federally. See docs/Methodology.md.")
    add("INFO", "Long-term care", "No long-term-care event is modeled.",
        "Consider a BigPurchases reserve (e.g. 2-3 years of care at ~$100K+/yr in the mid-80s) or LTC premiums in Spending.")

    # ---------------- privacy + safekeeping ----------------
    maintainer = _git("config", "--bool", "template.maintainer") == "true"
    hooks = _git("config", "--get", "core.hooksPath")
    if hooks != ".githooks":
        add("WARN", "Privacy", "The push guard hooks are not installed in this copy.",
            "Run: python setup_clone.py")
    if not maintainer:
        sys.path.insert(0, str(ROOT))
        import setup_clone
        if not setup_clone.in_onedrive():
            add("WARN", "Backup", f"{ROOT} is not inside OneDrive, so nothing backs up the plan.",
                "Move the folder into OneDrive Documents, then run python setup_clone.py again.")
        dirty = _git("status", "--porcelain", "--", "Inputs.xlsx", "private", "model/data")
        if dirty:
            add("WARN", "Backup", f"{len(dirty.splitlines())} changed or new data file(s) are not committed to "
                "the local history.", 'Commit them: git add -A && git commit -m "Update plan data"')
    tmpl = [t.strip().lower() for t in (ROOT / ".template-upstream").read_text().splitlines()
            if t.strip()] if (ROOT / ".template-upstream").exists() else []
    accepted = (_git("config", "--get", "plan.acceptedRemote") or "").lower()
    for line in (_git("remote", "-v") or "").splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[2] != "(push)" or parts[1].startswith("PUSH-DISABLED"):
            continue
        if any(t in parts[1].lower() for t in tmpl):
            if not maintainer:
                add("WARN", "Privacy", f"Remote '{parts[0]}' can push to the shared template repo.",
                    "Run: python setup_clone.py (makes the template fetch-only).")
        elif parts[1].lower() == accepted:
            add("INFO", "Privacy", f"Remote '{parts[0]}' ({parts[1]}) holds a copy of the plan (accepted with "
                "--accept-risks).", "Keep two-factor authentication on, review apps with repo access, and "
                "black out account numbers in private/.")
        elif not maintainer:
            add("WARN", "Privacy", f"Remote '{parts[0]}' ({parts[1]}) was not accepted; the hook blocks pushes to it.",
                f"Remove it (git remote remove {parts[0]}) or read the risks: python setup_clone.py --remote <url>")
    return F


def render(inp, F):
    order = {"BLOCKER": 0, "WARN": 1, "INFO": 2}
    icon = {"BLOCKER": "🛑", "WARN": "⚠️", "INFO": "ℹ️"}
    n = {k: sum(1 for f in F if f["level"] == k) for k in order}
    md = ["# Preflight checks\n",
          f"_Run {TODAY.isoformat()}. {n['BLOCKER']} blocker(s), {n['WARN']} warning(s), {n['INFO']} note(s)._\n",
          "Fix every 🛑 before trusting any number. Fix or consciously accept every ⚠️.\n",
          "| | Area | Finding | Fix |", "|---|---|---|---|"]
    for f in sorted(F, key=lambda f: order[f["level"]]):
        md.append(f"| {icon[f['level']]} | {f['area']} | {f['msg']} | {f['fix']} |")
    return "\n".join(md), n


def build(quick=False):
    inp = M._inp()
    F = run_checks(inp)
    md, n = render(inp, F)
    write("Preflight.md", md)
    return F, n


if __name__ == "__main__":
    load()
    F, n = build()
    for f in F:
        if f["level"] != "INFO":
            print(f"[{f['level']}] {f['area']}: {f['msg']}")
    print(f"\n{n['BLOCKER']} blocker(s), {n['WARN']} warning(s). See output/Preflight.md")
