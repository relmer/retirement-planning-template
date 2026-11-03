"""
Retirement model: year-by-year engine
=====================================
Single continuous annual model, start_year..end_year, for a married couple
(MFJ while both are alive, single after a first death). Household data comes
from Inputs.xlsx; tax law from data/federal_tax.json and data/state_tax/<XX>.json.

One vectorized simulation loop (_simulate) serves every analysis:
    run_deterministic(cfg, real_return)          -> pandas.DataFrame (yearly ledger)
    run_monte_carlo(cfg, n_paths, mean, sd)      -> dict of summary stats + arrays
    run_monte_carlo_historical(cfg, method)      -> same, on historical return sequences
Config.retire_year adds a working phase (keep-working scenario); Config.first_death_age
adds a survivor phase. ASSUMPTIONS are flagged with the tag  # ASSUMPTION.
"""

from __future__ import annotations
from dataclasses import dataclass
import json
import os as _os
import numpy as np
import pandas as pd

from inputs_io import Inputs, load_inputs, SPOUSES   # noqa: E402,F401

_HERE = _os.path.dirname(__file__)
INF = float("inf")

# ----------------------------------------------------------------------------
# 1. ACTIVE INPUTS + TAX LAW
# ----------------------------------------------------------------------------
INP = None   # active case inputs; install via set_inputs()
FED = None   # federal tax law (data/federal_tax.json)
STATE = None # state tax law (data/state_tax/<Params.state>.json)

def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def load_federal():
    return _load_json(_os.path.join(_HERE, "data", "federal_tax.json"))

def load_state(code: str):
    path = _os.path.join(_HERE, "data", "state_tax", f"{code}.json")
    if not _os.path.exists(path):
        raise FileNotFoundError(
            f"No state tax file for '{code}'. Create model/data/state_tax/{code}.json "
            f"(see model/data/state_tax/README.md) or set Params.state to NONE.")
    return _load_json(path)

def set_inputs(inp) -> None:
    """Install the active Inputs (and the matching federal/state tax law)."""
    global INP, FED, STATE
    INP = inp
    FED = load_federal()
    STATE = load_state(inp.state)

def _inp():
    if INP is None:
        raise RuntimeError("Inputs not loaded. Call set_inputs(load_inputs(path)) first.")
    return INP

def age_in(birth_year: int, year: int) -> int:
    return year - birth_year

def spending_real(year: int) -> float:
    return _inp().spending_real(year)

def infl_factor(year: int) -> float:
    """Price level relative to start_year (spending, SS COLA)."""
    return (1 + _inp().inflation) ** (year - _inp().start_year)

def law_factor(year: int, law_year: int) -> float:
    """Indexation of tax-law dollar figures from the law's tax_year to `year`."""
    return (1 + _inp().inflation) ** (year - law_year)

def _br(lst):
    return [(INF if u is None else float(u), float(r)) for u, r in lst]

# ----------------------------------------------------------------------------
# 2. TAX HELPERS (vectorized: work on floats or numpy arrays)
# ----------------------------------------------------------------------------
def bracket_tax(x, brackets, scale=1.0):
    x = np.asarray(x, dtype=float)
    tax = np.zeros_like(x)
    lo = 0.0
    for hi, rate in brackets:
        hi_s = hi * scale
        tax = tax + np.clip(np.minimum(x, hi_s) - lo, 0.0, None) * rate
        lo = hi_s
    return tax

def stacked_tax(base, gains, brackets, scale=1.0):
    """Tax on `gains` stacked on top of `base` taxable income (LTCG method)."""
    base = np.asarray(base, dtype=float)
    gains = np.clip(np.asarray(gains, dtype=float), 0.0, None)
    tax = np.zeros_like(gains + base)
    lo = base.copy() if base.ndim else np.array(base)
    remaining = gains.copy() if gains.ndim else np.array(gains)
    for hi, rate in brackets:
        room = np.clip(hi * scale - lo, 0.0, None)
        chunk = np.minimum(remaining, room)
        tax = tax + chunk * rate
        remaining = remaining - chunk
        lo = lo + chunk
    return tax

def ss_taxable(ss_benefit: float, other_agi, filing: str):
    """Portion of SS subject to federal income tax. Provisional income =
    other AGI (incl. capital gains and dividends) + half of benefits."""
    other_agi = np.asarray(other_agi, dtype=float)
    if ss_benefit <= 0:
        return np.zeros_like(other_agi)
    t1, t2 = FED["ss_taxation_thresholds"][filing]
    prov = other_agi + 0.5 * ss_benefit
    tier2 = np.minimum(0.5 * (prov - t1), 0.5 * ss_benefit)
    tier3 = np.minimum(0.5 * (t2 - t1) + 0.85 * (prov - t2), 0.85 * ss_benefit)
    return np.where(prov <= t1, 0.0, np.where(prov <= t2, tier2, tier3))

def senior_deduction(year, n65, magi, filing):
    sd = FED.get("senior_deduction")
    if not sd or n65 == 0 or not (sd["first_year"] <= year <= sd["last_year"]):
        return 0.0
    full = n65 * sd["amount_per_person_65_plus"]
    return np.clip(full - sd["phaseout_rate"] * np.clip(magi - sd["phaseout_magi"][filing], 0.0, None),
                   0.0, None)

def fica_tax(wages, year, filing):
    f = FED["fica"]
    s = law_factor(year, FED["tax_year"])
    return (f["ss_rate"] * min(wages, f["ss_wage_base"] * s)
            + f["medicare_rate"] * wages
            + f["addl_medicare_rate"] * max(0.0, wages - f["addl_medicare_threshold"][filing]))

def state_brackets(year, filing):
    table = STATE["brackets"][filing]
    keys = sorted(int(k) for k in table)
    use = keys[0]
    for k in keys:
        if k <= year:
            use = k
    return _br(table[str(use)])

def state_tax(year, filing, alive_ages, parts, ss_fed_taxable):
    """State income tax. parts: dict of income by type and spouse attribution,
    floats or per-path arrays (see _simulate)."""
    st = STATE
    s = law_factor(year, st["tax_year"]) if st.get("indexed") else 1.0
    cg = st.get("capital_gains") or {"mode": "income"}
    mode = cg.get("mode", "income")
    gains, divs = parts["gains"], parts["dividends"]
    agi = (parts["earned"] + parts["vest"] + parts["dcp"] + parts["ira"] + parts["pension"]
           + (gains + divs if mode == "income" else 0.0)
           + (ss_fed_taxable if st.get("ss_taxable") else 0.0))
    excl = 0.0
    rx = st.get("retirement_exclusion")
    if rx:
        elig_types = set(rx.get("eligible_income", []))
        rs = law_factor(year, st["tax_year"]) if rx.get("indexed") else 1.0
        for who, age in alive_ages.items():
            cap = 0.0
            for min_age, amt in rx["tiers_by_age"]:
                if age >= min_age:
                    cap = amt * rs
            if cap <= 0:
                continue
            share = parts["share"][who]
            elig = 0.0
            if "ira" in elig_types:
                elig = elig + parts["ira"] * share["ira"]
            if "pension" in elig_types:
                elig = elig + parts["pension_by"][who]
            if "dcp" in elig_types:
                elig = elig + parts["dcp"] * share["dcp"]
            if mode == "income":
                if "gains" in elig_types:
                    elig = elig + gains * 0.5
                if "dividends" in elig_types:
                    elig = elig + divs * 0.5
            elig = elig + min(parts["earned"] * 0.5, rx.get("earned_income_cap_per_person", 0) * rs)
            excl = excl + np.minimum(elig, cap)
    deduct = (st["standard_deduction"][filing] + st.get("personal_exemption_per_person", 0) * len(alive_ages)) * s
    taxable = np.clip(agi - excl - deduct, 0.0, None)
    tax = bracket_tax(taxable, state_brackets(year, filing), s) + st.get("local_rate", 0.0) * taxable
    if mode == "separate":
        base = gains + (divs if cg.get("include_dividends") else 0.0)
        tax = tax + bracket_tax(base, _br(cg["brackets"]), s)
    return tax

# Uniform Lifetime Table (RMD divisors).
UNIFORM_LIFETIME = {
    72:27.4,73:26.5,74:25.5,75:24.6,76:23.7,77:22.9,78:22.0,79:21.1,80:20.2,81:19.4,
    82:18.5,83:17.7,84:16.8,85:16.0,86:15.2,87:14.4,88:13.7,89:12.9,90:12.2,
    91:11.5,92:10.8,93:10.1,94:9.5,95:8.9,96:8.4,97:7.8,98:7.3,99:6.8,100:6.4,
    101:6.0,102:5.6,103:5.2,104:4.9,105:4.6,106:4.3,107:4.1,108:3.9,109:3.7,
    110:3.5,111:3.4,112:3.3,113:3.1,114:3.0,115:2.9,116:2.8,117:2.7,118:2.5,
    119:2.3,120:2.0,
}

def rmd_start_age(birth_year: int) -> int:
    """SECURE 2.0: born 1960+ => 75; 1951-1959 => 73; earlier => 72."""
    if birth_year >= 1960:
        return 75
    if birth_year >= 1951:
        return 73
    return 72

# ----------------------------------------------------------------------------
# 3. CONFIG
# ----------------------------------------------------------------------------
@dataclass
class Config:
    # None => use the default from INP (the workbook)
    husband_claim_age: "int | None" = None
    wife_claim_age: "int | None" = None
    roth_conversion_ceiling: "float | None" = None
    taxable_basis_fraction: "float | None" = None
    spend_multiplier: float = 1.0         # scales the real spending schedule
    earned_income: "dict | None" = None   # override INP earned income if given
    ss_cut_factor: "float | None" = None  # e.g. 0.77 => benefits cut 23% from Params.ss_cut_year
    # --- keep-working scenario: work (kw_* params) through retire_year - 1 ---
    retire_year: "int | None" = None
    # --- survivor scenario: one spouse dies in the year they reach this age ---
    first_death_age: "int | None" = None
    first_to_die: str = "husband"
    survivor_spend_pct: "float | None" = None
    # --- Guyton-Klinger guardrails (absolute withdrawal-rate bands); None => Params sheet ---
    guardrails: bool = False
    gr_upper: "float | None" = None     # if WR exceeds this -> cut spending
    gr_lower: "float | None" = None     # if WR below this  -> raise spending
    gr_cut: "float | None" = None       # spending cut step
    gr_raise: "float | None" = None     # spending raise step
    gr_floor: "float | None" = None     # min cumulative multiplier (floor = gr_floor x lifestyle)
    gr_ceiling: "float | None" = None   # max cumulative multiplier
    guardrails_in_bridge: bool = False  # also flex spending in bridge years (earned/vest/DCP income)
    # --- extra spending injections (year -> $); added AFTER guardrails, so not flexed ---
    extra_real: "dict | None" = None      # real $ added in that year (inflated to nominal)
    extra_nominal: "dict | None" = None   # fixed nominal $ added
    # --- conditional new-home purchase (per path: buy only if portfolio clears a threshold) ---
    house_year: "int | None" = None
    house_year_end: "int | None" = None  # if set, buy on FIRST crossing in [house_year, end]
    house_cost_real: float = 0.0       # one-time real $ outlay in purchase year (bought paths)
    house_threshold_real: float = 0.0  # buy only if real investable portfolio exceeds this
    house_carry_real: float = 0.0      # ongoing real $ from purchase year (bought paths only)
    # --- big purchases sized by an affordability rule (headroom to a WR ceiling) ---
    flex_big_purchases: bool = True
    car_wr_ceiling: "float | None" = None  # buy only up to what keeps NET withdrawal rate <= this
    bp_flex_floor: float = 0.0     # optional minimum fraction of a planned buy (0 => WR fully decides)

    def resolved(self) -> "Config":
        """Copy with every None default filled from the Params sheet."""
        inp = _inp()
        c = Config(**self.__dict__)
        for k in ("gr_upper", "gr_lower", "gr_cut", "gr_raise", "gr_floor", "gr_ceiling",
                  "car_wr_ceiling", "survivor_spend_pct", "ss_cut_factor",
                  "roth_conversion_ceiling", "taxable_basis_fraction"):
            if getattr(c, k) is None:
                setattr(c, k, getattr(inp, k))
        if c.husband_claim_age is None:
            c.husband_claim_age = inp.default_husband_claim_age
        if c.wife_claim_age is None:
            c.wife_claim_age = inp.default_wife_claim_age
        return c

# ----------------------------------------------------------------------------
# 4. ENGINE
# ----------------------------------------------------------------------------
def ss_monthly_for(person: str, claim_age: int) -> float:
    table = _inp().ss_monthly[person]
    if not table:
        return 0.0
    if claim_age in table:
        return float(table[claim_age])
    ages = sorted(table)
    return float(np.interp(claim_age, ages, [table[a] for a in ages]))

def ss_benefit_year(person: str, claim_age: int, birth: tuple, year: int) -> float:
    """Annual nominal SS benefit, prorated in the first year, COLA = inflation."""
    by, bm, bd = birth
    claim_year = by + claim_age
    if year < claim_year:
        return 0.0
    annual_real = ss_monthly_for(person, claim_age) * 12
    if year == claim_year:
        annual_real *= (12 - (bm - 1)) / 12.0   # ASSUMPTION: benefit begins the birthday month
    return annual_real * infl_factor(year)

def vest_schedule(inp, retire_year=None) -> dict:
    """EquityVests rows, plus (keep-working scenario) a new grant each working year
    vesting evenly over kw_grant_vest_years starting the following year."""
    sched = dict(inp.vest_cash)
    if retire_year is not None and inp.kw_annual_grant > 0:
        per = inp.kw_annual_grant / inp.kw_grant_vest_years
        for g in range(inp.start_year, retire_year):
            for k in range(1, inp.kw_grant_vest_years + 1):
                sched[g + k] = sched.get(g + k, 0.0) + per
    return sched

def _simulate(cfg: Config, returns: np.ndarray, record=False, track=False):
    """Advance every path in `returns` (n_paths x n_years, NOMINAL) through the plan."""
    inp = _inp()
    cfg = cfg.resolved()
    n_paths = returns.shape[0]
    births = {"husband": inp.husband_birth, "wife": inp.wife_birth}
    claims = {"husband": cfg.husband_claim_age, "wife": cfg.wife_claim_age}
    rmd_age = {w: rmd_start_age(births[w][0]) for w in SPOUSES}
    basis_frac = cfg.taxable_basis_fraction
    roth_ceiling = cfg.roth_conversion_ceiling
    R = cfg.retire_year
    if R is not None:
        earned_src = {}          # ASSUMPTION: salary replaces EarnedIncome; nothing earned after R
        dcp_start = R            # ASSUMPTION: deferred comp pays out from the retire year
    else:
        earned_src = cfg.earned_income if cfg.earned_income is not None else inp.earned_income
        dcp_start = inp.dcp_payout_start
    payout = set(range(dcp_start, dcp_start + inp.dcp_payout_years)) if inp.dcp_balance > 0 else set()
    vests = vest_schedule(inp, R)
    death_year = None
    if cfg.first_death_age is not None:
        death_year = births[cfg.first_to_die][0] + cfg.first_death_age
    pensions_by = {w: [p for p in inp.pensions if inp.owner_key(p["person"]) == w] for w in SPOUSES}
    fixed = inp.fixed_nominal
    T = FED
    fed_year = T["tax_year"]

    z = np.zeros(n_paths)
    taxable = z + inp.taxable_start
    trad = {"husband": z + inp.husband_traditional, "wife": z + inp.wife_traditional}
    roth = z + inp.roth_start
    dcp_bal = z + inp.dcp_balance
    dead = np.zeros(n_paths, dtype=bool)
    depletion_year = np.full(n_paths, -1, dtype=int)
    house_bought = np.zeros(n_paths, dtype=bool)
    gr_mult = np.ones(n_paths)
    gr_min = np.ones(n_paths)
    gr_ncuts = np.zeros(n_paths, dtype=int)
    gr_max_streak = np.zeros(n_paths, dtype=int)
    gr_cur_streak = np.zeros(n_paths, dtype=int)
    gr_years_reduced = np.zeros(n_paths, dtype=int)
    gr_years_at_floor = np.zeros(n_paths, dtype=int)
    bal_real_by_year = {}
    rows = []
    totals = np.zeros((n_paths, returns.shape[1])) if track else None
    merged = False

    for i, year in enumerate(range(inp.start_year, inp.end_year + 1)):
        ages = {w: year - births[w][0] for w in SPOUSES}
        alive = {w: not (death_year is not None and cfg.first_to_die == w and year > death_year)
                 for w in SPOUSES}
        single = not all(alive.values())   # ASSUMPTION: MFJ in the year of death, single after
        filing = "single" if single else "mfj"
        if single and not merged:
            # spousal rollover: the survivor's traditional accounts absorb the deceased's
            gone = cfg.first_to_die
            keep = "wife" if gone == "husband" else "husband"
            trad[keep] = trad[keep] + trad[gone]
            trad[gone] = z.copy()
            merged = True
        alive_ages = {w: ages[w] for w in SPOUSES if alive[w]}
        gf = 1.0 + returns[:, i]
        infl = infl_factor(year)
        lf = law_factor(year, fed_year)
        working = R is not None and year < R

        # --- wages (keep-working scenario) ---
        salary = bonus = k401 = match = 0.0
        if working:
            # ASSUMPTION: salary/bonus are nominal; kw_salary_growth is the nominal raise
            salary = inp.kw_salary * (1 + inp.kw_salary_growth) ** (year - inp.start_year)
            bonus = inp.kw_bonus
            k401 = inp.kw_401k_pct * salary
            match = inp.kw_match_pct * k401
        earned = salary + bonus if working else float(earned_src.get(year, 0.0))
        vest = float(vests.get(year, 0.0))               # ASSUMPTION: ordinary income at vest
        fica = fica_tax(earned + vest, year, filing) if working else 0.0

        # --- Social Security (survivor keeps the larger of the two benefits) ---
        ss_each = {w: ss_benefit_year(w, claims[w], births[w], year) for w in SPOUSES}
        ss_total = max(ss_each.values()) if single else sum(ss_each.values())
        if cfg.ss_cut_factor < 1.0 and year >= inp.ss_cut_year:
            ss_total *= cfg.ss_cut_factor

        # --- pensions / annuities ---
        pension_by = {}
        for w in SPOUSES:
            amt = 0.0
            for p in pensions_by[w]:
                if year < p["start_year"] or (p["end_year"] is not None and year > p["end_year"]):
                    continue
                a = p["annual"] * (infl if p["cola"] else 1.0)
                amt += a if alive[w] else a * p["survivor_pct"]
            pension_by[w] = amt
        pension = sum(pension_by.values())

        # --- spending ---
        spend = spending_real(year) * cfg.spend_multiplier * infl
        if single:
            spend *= cfg.survivor_spend_pct
        base_spend = spend
        portfolio_funded = (not working) and earned == 0 and vest == 0 and year not in payout
        if cfg.guardrails and (cfg.guardrails_in_bridge or portfolio_funded):
            invest_port = taxable + trad["husband"] + trad["wife"] + roth
            safe_port = np.where(invest_port > 0, invest_port, 1.0)
            wr = np.where(invest_port > 0, spend / safe_port, 1.0)
            is_cut = (wr > cfg.gr_upper) & (~dead)
            gr_mult = np.where(wr > cfg.gr_upper,
                               np.maximum(gr_mult * (1 - cfg.gr_cut), cfg.gr_floor), gr_mult)
            gr_mult = np.where(wr < cfg.gr_lower,
                               np.minimum(gr_mult * (1 + cfg.gr_raise), cfg.gr_ceiling), gr_mult)
            gr_min = np.minimum(gr_min, gr_mult)
            gr_ncuts = gr_ncuts + is_cut
            gr_cur_streak = np.where(is_cut, gr_cur_streak + 1, 0)
            gr_max_streak = np.maximum(gr_max_streak, gr_cur_streak)
            gr_years_reduced = gr_years_reduced + ((gr_mult < 0.999) & (~dead))
            gr_years_at_floor = gr_years_at_floor + ((gr_mult <= cfg.gr_floor + 1e-9) & (~dead))
        if cfg.guardrails:
            spend = spend * gr_mult
        # fixed / one-time extras: not guardrail-flexed
        spend = spend + fixed.get(year, 0.0)
        if cfg.extra_real:
            spend = spend + float(cfg.extra_real.get(year, 0.0)) * infl
        if cfg.extra_nominal:
            spend = spend + float(cfg.extra_nominal.get(year, 0.0))
        # Big-ticket AFFORDABILITY FORMULA (negative amounts = one-time inflows):
        #     affordable = car_wr_ceiling * portfolio - (base lifestyle - guaranteed income)
        #     bought     = clip(affordable, floor, planned)
        bp_amt = inp.big_purchases.get(year, 0.0) * infl
        if bp_amt > 0 and cfg.guardrails and cfg.flex_big_purchases and portfolio_funded:
            port = taxable + trad["husband"] + trad["wife"] + roth
            affordable = cfg.car_wr_ceiling * port - (base_spend - ss_total - pension)
            bp = np.clip(affordable, cfg.bp_flex_floor * bp_amt, bp_amt)
        else:
            bp = bp_amt
        spend = spend + bp
        if cfg.house_year is not None and year >= cfg.house_year:
            end = cfg.house_year_end if cfg.house_year_end is not None else cfg.house_year
            if year <= end:
                invest_now = taxable + trad["husband"] + trad["wife"] + roth
                newly = (~house_bought) & (~dead) & (invest_now > cfg.house_threshold_real * infl)
                house_bought = house_bought | newly
                spend = spend + np.where(newly, cfg.house_cost_real * infl, 0.0)
            spend = spend + np.where(house_bought, cfg.house_carry_real * infl, 0.0)

        n65 = sum(1 for w in alive_ages if alive_ages[w] >= 65)
        std = (T["standard_deduction"][filing] + n65 * T["additional_65_per_person"][filing]) * lf

        # --- deferred comp installment (balance grows with returns) ---
        if year in payout:
            years_left = dcp_start + inp.dcp_payout_years - year
            dcp = np.where(dcp_bal > 0, dcp_bal / years_left, 0.0)
            dcp_bal = dcp_bal - dcp
        else:
            dcp = z.copy()

        # --- RMDs, removed proportionally from traditional ---
        rmd = z.copy()
        for w in SPOUSES:
            if alive[w] and ages[w] >= rmd_age[w]:
                rmd = rmd + trad[w] / UNIFORM_LIFETIME.get(ages[w], 2.0)
        tot_trad = trad["husband"] + trad["wife"]
        safe = np.where(tot_trad > 0, tot_trad, 1.0)
        has_rmd = rmd > 0
        h_share = np.where(tot_trad > 0, trad["husband"] / safe, 0.5)   # for state attribution
        for w in SPOUSES:
            trad[w] = trad[w] - np.where(has_rmd, rmd * trad[w] / safe, 0.0)

        dividends = taxable * inp.taxable_dividend_yield   # ASSUMPTION: qualified, reinvested

        # --- optional Roth conversion (fill ordinary taxable income up to the ceiling) ---
        conversion = z.copy()
        if roth_ceiling > 0 and not working:
            base_ord = dcp + earned + vest + rmd + pension
            base_ord = base_ord + ss_taxable(ss_total, base_ord + dividends, filing)
            room = roth_ceiling * infl - (base_ord - std)
            avail_c = trad["husband"] + trad["wife"]
            conversion = np.clip(np.minimum(room, avail_c), 0.0, None)
            tot = np.where(avail_c > 0, avail_c, 1.0)
            for w in SPOUSES:
                trad[w] = trad[w] - conversion * trad[w] / tot
            roth = roth + conversion

        wages_taxable = earned - k401
        ord_base = dcp + wages_taxable + vest + rmd + conversion + pension
        cash_in = vest + ss_total + dcp + wages_taxable + rmd + pension

        share = {"husband": {"ira": h_share, "dcp": 1.0 if inp.dcp_owner == "husband" else 0.0},
                 "wife": {"ira": 1.0 - h_share, "dcp": 1.0 if inp.dcp_owner == "wife" else 0.0}}

        # --- withdrawal / tax solver: cover spending + the tax the withdrawals create ---
        w_taxable = z.copy(); w_trad = z.copy(); w_roth = z.copy()
        realized_gain = z.copy()
        total_tax = fed = st_tax = z.copy()
        magi = z.copy()
        for _ in range(60):
            ord_income = ord_base + w_trad
            pref = realized_gain + dividends
            ss_tax_part = ss_taxable(ss_total, ord_income + pref, filing)
            magi = ord_income + ss_tax_part + pref
            ded = std + senior_deduction(year, n65, magi, filing)
            ord_taxable = np.clip(ord_income + ss_tax_part - ded, 0.0, None)
            niit_thr = T["niit"]["threshold"][filing]
            fed = (bracket_tax(ord_taxable, _br(T["ordinary_brackets"][filing]), lf)
                   + stacked_tax(ord_taxable, pref, _br(T["ltcg_brackets"][filing]), lf)
                   + T["niit"]["rate"] * np.clip(np.minimum(pref, magi - niit_thr), 0.0, None))
            parts = dict(earned=wages_taxable, vest=vest, dcp=dcp, ira=rmd + conversion + w_trad,
                         pension=pension, pension_by=pension_by, gains=realized_gain,
                         dividends=dividends, share=share)
            st_tax = state_tax(year, filing, alive_ages, parts, ss_tax_part)
            total_tax = fed + st_tax + fica
            gap = (spend + total_tax) - (cash_in + w_taxable + w_trad + w_roth)

            avail_tax = taxable - w_taxable
            avail_trad = (trad["husband"] + trad["wife"]) - w_trad
            avail_roth = roth - w_roth
            pos = gap >= 1.0
            neg = gap <= -1.0
            if not (pos.any() or neg.any()):
                break
            # draw: taxable -> traditional -> roth (one source per iteration)
            d_tax = pos & (avail_tax > 1)
            d_trad = pos & (avail_tax <= 1) & (avail_trad > 1)
            d_roth = pos & (avail_tax <= 1) & (avail_trad <= 1) & (avail_roth > 1)
            w_taxable = w_taxable + np.where(d_tax, np.minimum(gap, avail_tax), 0.0)
            w_trad = w_trad + np.where(d_trad, np.minimum(gap, avail_trad), 0.0)
            w_roth = w_roth + np.where(d_roth, np.minimum(gap, avail_roth), 0.0)
            # overshoot: reduce roth -> trad -> taxable (most recent first)
            r_roth = neg & (w_roth > 0)
            r_trad = neg & (w_roth <= 0) & (w_trad > 0)
            r_tax = neg & (w_roth <= 0) & (w_trad <= 0) & (w_taxable > 0)
            w_roth = np.where(r_roth, np.clip(w_roth + gap, 0.0, None), w_roth)
            w_trad = np.where(r_trad, np.clip(w_trad + gap, 0.0, None), w_trad)
            w_taxable = np.where(r_tax, np.clip(w_taxable + gap, 0.0, None), w_taxable)
            realized_gain = w_taxable * (1 - basis_frac)   # ASSUMPTION: constant basis fraction

        # apply withdrawals
        taxable = taxable - w_taxable
        tot_trad = trad["husband"] + trad["wife"]
        safe = np.where(tot_trad > 0, tot_trad, 1.0)
        wmask = (w_trad > 0) & (tot_trad > 0)
        for w in SPOUSES:
            trad[w] = trad[w] - np.where(wmask, w_trad * trad[w] / safe, 0.0)
        roth = roth - w_roth
        surplus = (cash_in + w_taxable + w_trad + w_roth) - (spend + total_tax)
        taxable = taxable + np.clip(surplus, 0.0, None)
        if working:
            trad["husband"] = trad["husband"] + (k401 + match)   # ASSUMPTION: the earner is the husband

        # growth
        taxable = taxable * gf
        for w in SPOUSES:
            trad[w] = trad[w] * gf
        roth = roth * gf
        dcp_bal = dcp_bal * gf

        total_port = taxable + trad["husband"] + trad["wife"] + roth
        bal_real_by_year[year] = float(np.median(total_port)) / infl
        newly_dead = (~dead) & (total_port <= 0)
        depletion_year = np.where(newly_dead, year, depletion_year)
        was_dead = dead
        dead = dead | (total_port <= 0)
        taxable = np.where(dead, 0.0, taxable)
        for w in SPOUSES:
            trad[w] = np.where(dead, 0.0, trad[w])
        roth = np.where(dead, 0.0, roth)
        dcp_bal = np.where(dead, 0.0, dcp_bal)
        if track:
            totals[:, i] = taxable + trad["husband"] + trad["wife"] + roth + dcp_bal

        if record:
            on = 0.0 if was_dead[0] else 1.0
            v = lambda a: round(float(np.asarray(a).reshape(-1)[0]) * on)
            rows.append(dict(
                year=year, husband_age=ages["husband"], wife_age=ages["wife"], filing=filing,
                spend=v(spend), ss=v(ss_total), pension=v(pension), dcp=v(dcp),
                earned=v(earned), vest=v(vest), rmd=v(rmd), conversion=v(conversion),
                dividends=v(dividends), fed_tax=v(fed), state_tax=v(st_tax), fica=v(fica),
                tax=v(total_tax), magi=v(magi),
                w_taxable=v(w_taxable), w_trad=v(w_trad), w_roth=v(w_roth),
                taxable=v(taxable), trad=v(trad["husband"] + trad["wife"]),
                roth=v(roth), dcp_remaining=v(dcp_bal),
                total=v(total_port) if not dead[0] else 0,
                total_incl_dcp=v(total_port + dcp_bal) if not dead[0] else 0,
                nominal_return=round(float(returns[0, i]), 4),
            ))

    ending = np.round(taxable + trad["husband"] + trad["wife"] + roth)
    survived = ending > 0
    dep_years = depletion_year[depletion_year > 0]
    out = dict(
        success_rate=float(survived.mean()),
        median_ending=float(np.median(ending)),
        p10_ending=float(np.percentile(ending, 10)),
        p90_ending=float(np.percentile(ending, 90)),
        worst_depletion=int(dep_years.min()) if dep_years.size else None,
        depletion_year=depletion_year,   # per-path: calendar year of depletion, -1 if survived
        bal_real_by_year=bal_real_by_year,  # median real (today's $) total portfolio at each year-end
        house_bought=house_bought,
        ending=ending,
        final_gr_mult=gr_mult,
        gr_min=gr_min, gr_ncuts=gr_ncuts, gr_max_streak=gr_max_streak,
        gr_years_reduced=gr_years_reduced, gr_years_at_floor=gr_years_at_floor,
    )
    if record:
        out["rows"] = rows
    if track:
        out["totals"] = totals
    return out


def _n_years():
    inp = _inp()
    return inp.end_year - inp.start_year + 1

def run_deterministic(cfg: Config, real_return: float, returns_seq=None) -> pd.DataFrame:
    """Yearly ledger at a constant real return, or along one NOMINAL return sequence."""
    inp = _inp()
    if returns_seq is None:
        nominal = (1 + real_return) * (1 + inp.inflation) - 1
        returns_seq = np.full(_n_years(), nominal)
    res = _simulate(cfg, np.asarray(returns_seq, dtype=float).reshape(1, -1), record=True)
    return pd.DataFrame(res["rows"])

def parametric_returns(n_paths=None, mean_real=None, sd=None, seed=None):
    inp = _inp()
    n_paths = inp.mc_paths if n_paths is None else n_paths
    mean_real = inp.equity_real_mean if mean_real is None else mean_real
    sd = inp.equity_vol if sd is None else sd
    seed = inp.mc_seed if seed is None else seed
    mean_nominal = (1 + mean_real) * (1 + inp.inflation) - 1
    # row p = p-th block of n_years draws => identical to a per-path loop
    return np.random.default_rng(seed).normal(mean_nominal, sd, (n_paths, _n_years()))

def run_monte_carlo_vectorized(cfg: Config, n_paths=None, mean_real=None, sd=None,
                               seed=None, _returns=None, track=False):
    """Monte Carlo over all paths at once. _returns: optional NOMINAL return matrix."""
    returns = parametric_returns(n_paths, mean_real, sd, seed) if _returns is None else _returns
    return _simulate(cfg, returns, track=track)

def run_monte_carlo(cfg: Config, n_paths=None, mean_real=None, sd=None, seed=None):
    """Parametric (IID-normal) Monte Carlo: the PESSIMISTIC lens."""
    return run_monte_carlo_vectorized(cfg, n_paths, mean_real, sd, seed)

# ----------------------------------------------------------------------------
# 5. HISTORICAL return engine (block bootstrap + cyclical, the FICalc method)
# ----------------------------------------------------------------------------
_HIST_REAL = None

def _load_hist_real():
    """Annual real total returns (US large-cap, Shiller-derived). See build_returns.py."""
    global _HIST_REAL
    if _HIST_REAL is None:
        path = _os.path.join(_HERE, "data", "annual_real_returns.csv")
        vals = []
        with open(path) as f:
            next(f)
            for line in f:
                line = line.strip()
                if line:
                    vals.append(float(line.split(",")[1]))
        _HIST_REAL = np.array(vals)
    return _HIST_REAL

def bootstrap_returns(n_paths, n_years, inflation, seed=42, block_mean=8):
    """Stationary (Politis-Romano) block bootstrap of historical REAL returns,
    converted to nominal. Random block lengths ~ Geometric(1/block_mean) preserve
    short/medium-run autocorrelation (mean reversion). block_mean=1 => IID resample."""
    rng = np.random.default_rng(seed)
    hist = _load_hist_real(); N = len(hist)
    p = 1.0 / block_mean
    idx = np.empty((n_paths, n_years), dtype=int)
    cur = rng.integers(0, N, size=n_paths)
    idx[:, 0] = cur
    for t in range(1, n_years):
        restart = rng.random(n_paths) < p
        cur = np.where(restart, rng.integers(0, N, size=n_paths), (cur + 1) % N)
        idx[:, t] = cur
    real = hist[idx]
    return (1 + real) * (1 + inflation) - 1

def cyclical_returns(n_years, inflation):
    """FICalc-style: every contiguous n_years window of real history as one path."""
    hist = _load_hist_real(); N = len(hist)
    starts = N - n_years + 1
    real = np.stack([hist[s:s + n_years] for s in range(starts)])
    return (1 + real) * (1 + inflation) - 1

def lens_returns(method, n_paths=None):
    """NOMINAL return matrix for 'parametric', 'bootstrap' or 'cyclical'."""
    inp = _inp()
    if method == "cyclical":
        return cyclical_returns(_n_years(), inp.inflation)
    if method == "bootstrap":
        return bootstrap_returns(inp.mc_paths if n_paths is None else n_paths, _n_years(),
                                 inp.inflation, inp.mc_seed)
    return parametric_returns(n_paths)

def run_monte_carlo_historical(cfg: Config, method="bootstrap", n_paths=None,
                               seed=None, block_mean=8):
    """Monte Carlo on historical real-return sequences instead of IID-normal.
    method='bootstrap' (block bootstrap, n_paths) or 'cyclical' (FICalc windows)."""
    inp = _inp()
    if method == "cyclical":
        returns = cyclical_returns(_n_years(), inp.inflation)
    else:
        n_paths = inp.mc_paths if n_paths is None else n_paths
        seed = inp.mc_seed if seed is None else seed
        returns = bootstrap_returns(n_paths, _n_years(), inp.inflation, seed, block_mean)
    return _simulate(cfg, returns)


if __name__ == "__main__":
    import sys
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 40)
    path = sys.argv[1] if len(sys.argv) > 1 else _os.path.join(_HERE, "..", "Inputs.xlsx")
    set_inputs(load_inputs(path))
    df = run_deterministic(Config(), real_return=0.065)
    print(f"=== Deterministic 6.5% real, default claim ages (inputs: {path}) ===")
    print(df[["year", "husband_age", "spend", "ss", "pension", "vest", "fed_tax", "state_tax",
              "w_taxable", "w_trad", "total"]].to_string(index=False))
