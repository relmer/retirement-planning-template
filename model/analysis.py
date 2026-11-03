"""analysis.py: analytical views built on the engine. Returns DataFrames/dicts/text;
no file I/O (run.py writes the output files)."""
from __future__ import annotations
import numpy as np
import pandas as pd
import retirement_model as M
from retirement_model import Config, run_deterministic, run_monte_carlo, age_in

LENSES = ("parametric", "bootstrap", "cyclical")
LENS_LABEL = {"parametric": "Pessimistic (parametric)",
              "bootstrap": "Middle (historical bootstrap)",
              "cyclical": "Optimistic (historical cyclical)"}


def lens_matrices(n_paths):
    """Return matrices for all three lenses, generated once and reused (common random numbers)."""
    return {m: M.lens_returns(m, n_paths) for m in LENSES}


def success_all(cfg, mats):
    return {m: M.run_monte_carlo_vectorized(cfg, _returns=mats[m]) for m in LENSES}


def ledger(cfg: Config, real_return: float) -> pd.DataFrame:
    return run_deterministic(cfg, real_return)


def _claim_rows(claim_ages):
    """Same-age diagonal plus the workbook default pair (if not already on the diagonal)."""
    inp = M._inp()
    pairs = [(a, a) for a in claim_ages]
    default = (inp.default_husband_claim_age, inp.default_wife_claim_age)
    if default not in pairs:
        pairs.append(default)
    return pairs


def scenario_grid(real_returns=(0.03, 0.05, 0.065, 0.08), claim_ages=(62, 67, 70)) -> pd.DataFrame:
    rows = []
    for a1, a2 in _claim_rows(claim_ages):
        row = {"claim_age (H/W)": f"{a1}/{a2}"}
        for r in real_returns:
            d = run_deterministic(Config(husband_claim_age=a1, wife_claim_age=a2), r)
            e = d.iloc[-1]["total"]
            row[f"{r*100:.1f}%_real"] = (f"{e:,.0f}" if e > 0
                                         else f"DEPLETED {int(d[d.total<=0].year.min())}")
        rows.append(row)
    return pd.DataFrame(rows)


def monte_carlo_table(claim_ages=(62, 67, 70), n_paths=None) -> pd.DataFrame:
    rows = []
    for a1, a2 in _claim_rows(claim_ages):
        r = run_monte_carlo(Config(husband_claim_age=a1, wife_claim_age=a2, guardrails=True), n_paths=n_paths)
        rows.append({"claim_age (H/W)": f"{a1}/{a2}", "pessimistic_success_gk": round(r["success_rate"], 4),
                     "median_ending": int(r["median_ending"]), "p10": int(r["p10_ending"]),
                     "p90": int(r["p90_ending"]), "worst_depletion": r["worst_depletion"]})
    return pd.DataFrame(rows)


def safe_spending(target=0.85, n_paths=1500, guardrails=False) -> dict:
    """Bisection on spend_multiplier for ~target PESSIMISTIC (parametric) success."""
    inp = M._inp()
    base_first = inp.spending_real(inp.start_year)
    lo, hi = 0.2, 1.8
    for _ in range(9):
        mid = (lo + hi) / 2
        s = run_monte_carlo(Config(spend_multiplier=mid, guardrails=guardrails),
                            n_paths=n_paths)["success_rate"]
        if s < target:
            hi = mid
        else:
            lo = mid
    return dict(multiplier=round(lo, 3), safe_first=base_first * lo, target_first=base_first,
                target_success=target, guardrails=guardrails)


def success_by_spend(multipliers=None, n_paths=1000) -> pd.DataFrame:
    inp = M._inp()
    base = inp.spending_real(inp.start_year)
    if multipliers is None:
        multipliers = [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3]
    rows = []
    for m in multipliers:
        s = run_monte_carlo(Config(spend_multiplier=m, guardrails=True), n_paths=n_paths)["success_rate"]
        rows.append(dict(spend_multiplier=m, lifestyle_spend=int(base * m), pessimistic_success_gk=round(s, 4)))
    return pd.DataFrame(rows)


def roth_comparison(ceilings=(0, 100_000, 200_000, 400_000), real_return=0.065) -> pd.DataFrame:
    rows = []
    for c in ceilings:
        d = run_deterministic(Config(roth_conversion_ceiling=c), real_return)
        e = d.iloc[-1]["total"]
        rows.append(dict(conversion_ceiling=c, ending=int(e),
                         depletion=("" if e > 0 else int(d[d.total <= 0].year.min())),
                         lifetime_fed_tax=int(d["fed_tax"].sum()),
                         lifetime_state_tax=int(d["state_tax"].sum())))
    return pd.DataFrame(rows)


def depletion_ladder(res, birth_year, end_year):
    """Age (of the spouse with birth_year) the money lasts to AT LEAST at 75/90/95% confidence."""
    horizon_age = end_year - birth_year
    dy = np.asarray(res["depletion_year"])
    age = np.where(dy > 0, dy - birth_year, horizon_age + 1)
    row = {"success": float(res["success_rate"])}
    for c in (75, 90, 95):
        a = int(np.percentile(age, 100 - c, method="lower"))
        row[c] = f"{horizon_age}+" if a > horizon_age else str(a)
    fails = age[age <= horizon_age]
    row["typ_fail"] = int(np.median(fails)) if fails.size else None
    return row


def first5_text(cfg: Config, real_return=0.065, n_years=5) -> str:
    inp = M._inp()
    df = run_deterministic(cfg, real_return).set_index("year")
    s0 = inp.start_year
    c = cfg.resolved()
    out = []
    M_ = lambda x: f"{x:>14,.0f}"
    out.append("=" * 72)
    out.append(f" FIRST {n_years} YEARS: {s0}-{s0+n_years-1}")
    out.append(f" Deterministic {real_return*100:.1f}% real, claim {c.husband_claim_age}/{c.wife_claim_age}, "
               f"state {inp.state}, 100% stocks")
    out.append("=" * 72)
    out.append(f" STARTING BALANCES ({s0})")
    out.append(f"    Taxable (brokerage)               {M_(inp.taxable_start)}")
    out.append(f"    Traditional (IRAs + 401ks)        {M_(inp.husband_traditional + inp.wife_traditional)}")
    out.append(f"    Roth (incl. HSA, tax-free)        {M_(inp.roth_start)}")
    out.append(f"    Deferred comp                     {M_(inp.dcp_balance)}")
    out.append(f"    {'TOTAL incl. deferred comp':<33} {M_(inp.investable_start + inp.dcp_balance)}")
    for year in range(s0, min(s0 + n_years, inp.end_year + 1)):
        r = df.loc[year]
        inflow = r.earned + r.dcp + r.vest + r.ss + r.pension + r.rmd
        wd = r.w_taxable + r.w_trad + r.w_roth
        surplus = inflow - (r.spend + r.tax)
        out.append("\n" + "-" * 72)
        out.append(f" {year}   ({inp.husband_name} {r.husband_age} / {inp.wife_name} {r.wife_age})")
        out.append("-" * 72)
        out.append("  INFLOWS / INCOME")
        out.append(f"    Earned income                     {M_(r.earned)}")
        out.append(f"    Deferred-comp installment         {M_(r.dcp)}")
        out.append(f"    Equity vests (gross, taxed)       {M_(r.vest)}")
        out.append(f"    Social Security                   {M_(r.ss)}")
        out.append(f"    Pensions / annuities              {M_(r.pension)}")
        if r.rmd:
            out.append(f"    RMD (forced from Traditional)     {M_(r.rmd)}")
        out.append(f"    {'gross inflows':<33} {M_(inflow)}")
        out.append(f"    (dividends reinvested, taxed)     {M_(r.dividends)}")
        out.append("  OUTFLOWS")
        out.append(f"    Lifestyle + fixed + big purchases {M_(-r.spend)}")
        out.append(f"    Federal income tax                {M_(-r.fed_tax)}")
        out.append(f"    State income tax ({inp.state:<4})          {M_(-r.state_tax)}")
        if r.fica:
            out.append(f"    FICA                              {M_(-r.fica)}")
        out.append(f"    {'total outflows':<33} {M_(-(r.spend + r.tax))}")
        out.append("  PORTFOLIO ACTIVITY")
        if r.conversion:
            out.append(f"    Roth conversion (Trad->Roth)      {M_(r.conversion)}")
        if wd > 0.5:
            out.append(f"    Withdraw from Taxable             {M_(-r.w_taxable)}")
            out.append(f"    Withdraw from Traditional         {M_(-r.w_trad)}")
            out.append(f"    Withdraw from Roth                {M_(-r.w_roth)}")
            out.append(f"    {'net DRAWN from portfolio':<33} {M_(-wd)}")
        else:
            out.append(f"    Surplus REINVESTED to taxable     {M_(surplus)}")
        out.append("  ASSET BALANCES (end of year, after growth)")
        out.append(f"    Taxable                           {M_(r.taxable)}")
        out.append(f"    Traditional                       {M_(r.trad)}")
        out.append(f"    Roth (incl. HSA)                  {M_(r.roth)}")
        out.append(f"    Deferred comp remaining           {M_(r.dcp_remaining)}")
        out.append(f"    {'TOTAL incl. deferred comp':<33} {M_(r.total_incl_dcp)}")
    return "\n".join(out)
