"""inputs_io.py: loads Inputs.xlsx (the single source of truth for household data).

Tax law lives in model/data/federal_tax.json and model/data/state_tax/<XX>.json.
Methodology lives in retirement_model.py. Everything specific to a household
(people, balances, income, spending, dates) comes from the workbook.

Data sheets use a header row in row 1 and are parsed BY HEADER NAME, so columns
may be reordered. The README sheet is ignored. build_inputs.py writes a fresh
sample workbook.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import datetime as dt
import os
import openpyxl

SPOUSES = ("husband", "wife")


def to_date(v):
    """date from a cell: date/datetime, 'YYYY-MM-DD', 'YYYY-MM', or None."""
    if v in (None, ""):
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = str(v).strip()[:10]
    parts = s.split("-")
    try:
        if len(parts) == 3:
            return dt.date(int(parts[0]), int(parts[1]), int(parts[2]))
        if len(parts) == 2:
            return dt.date(int(parts[0]), int(parts[1]), 1)
    except ValueError:
        return None
    return None


def _yes(v):
    return str(v).strip().lower() in ("y", "yes", "true", "1", "x")


# ===========================================================================
# Inputs container
# ===========================================================================
@dataclass
class Inputs:
    params: dict
    accounts: list           # list of dict: account, owner, tax_type, balance, as_of, source_file
    earned: list             # (year, component, amount)
    equity_vests: list       # (year, vest_date, amount)
    social_security: list    # (person, claim_age, monthly, claim_date)
    spending: list           # (start_year, end_year, annual_real, healthcare_real)
    big_purchases: dict = field(default_factory=dict)   # {year: discrete real-$ one-time spend}
    pensions: list = field(default_factory=list)        # dict: person, kind, start_year, end_year, annual, cola, survivor_pct
    fixed_payments: list = field(default_factory=list)  # dict: item, start_year, end_year, annual_nominal
    bills: list = field(default_factory=list)           # dict: item, annual, due_months, paid_via, in_spending
    actions: list = field(default_factory=list)         # dict: date, action, amount, notes

    # ---- scalar params ----
    def _p(self, key, default=None):
        v = self.params.get(key)
        return default if v is None or v == "" else v

    @property
    def husband_name(self): return str(self._p("husband_name", "Husband"))
    @property
    def wife_name(self): return str(self._p("wife_name", "Wife"))
    def name(self, who): return self.husband_name if who == "husband" else self.wife_name

    def _birth(self, key):
        d = to_date(self.params.get(key))
        if d is None:
            raise ValueError(f"Params.{key} must be a date (YYYY-MM-DD)")
        return (d.year, d.month, d.day)
    @property
    def husband_birth(self): return self._birth("husband_birth")
    @property
    def wife_birth(self): return self._birth("wife_birth")
    def birth(self, who): return self.husband_birth if who == "husband" else self.wife_birth

    @property
    def start_year(self): return int(self._p("start_year"))
    @property
    def plan_to_age(self): return int(self._p("plan_to_age", 95))
    @property
    def end_year(self):
        """Params.end_year if set, else the year the YOUNGER spouse reaches plan_to_age."""
        v = self._p("end_year")
        if v is not None:
            return int(v)
        return max(self.husband_birth[0], self.wife_birth[0]) + self.plan_to_age
    @property
    def inflation(self): return float(self._p("inflation"))
    @property
    def equity_real_mean(self): return float(self._p("equity_real_mean", 0.065))
    @property
    def equity_vol(self): return float(self._p("equity_vol", 0.18))
    @property
    def taxable_basis_fraction(self): return float(self._p("taxable_basis_fraction", 1.0))
    @property
    def taxable_dividend_yield(self): return float(self._p("taxable_dividend_yield", 0.0))
    @property
    def healthcare_inflation_extra(self): return float(self._p("healthcare_inflation_extra", 0.0))
    @property
    def state(self): return str(self._p("state", "NONE")).strip().upper()
    @property
    def default_husband_claim_age(self): return int(self._p("husband_claim_age", 67))
    @property
    def default_wife_claim_age(self): return int(self._p("wife_claim_age", 67))
    def default_claim_age(self, who):
        return self.default_husband_claim_age if who == "husband" else self.default_wife_claim_age
    @property
    def ss_cut_year(self): return int(self._p("ss_cut_year", 2034))
    @property
    def ss_cut_factor(self): return float(self._p("ss_cut_factor", 1.0))
    @property
    def roth_conversion_ceiling(self): return float(self._p("roth_conversion_ceiling", 0))
    @property
    def mc_paths(self): return int(self._p("mc_paths", 3000))
    @property
    def mc_seed(self): return int(self._p("mc_seed", 42))
    @property
    def target_success(self): return float(self._p("target_success", 0.80))
    @property
    def dcp_payout_start(self): return int(self._p("dcp_payout_start", self.start_year))
    @property
    def dcp_payout_years(self): return int(self._p("dcp_payout_years", 1))
    @property
    def survivor_spend_pct(self): return float(self._p("survivor_spend_pct", 0.80))
    @property
    def survivor_test_age(self): return int(self._p("survivor_test_age", 80))
    @property
    def retire_date(self): return to_date(self._p("retire_date"))
    @property
    def cobra_months(self): return int(self._p("cobra_months", 0))
    @property
    def stock_allocation(self): return float(self._p("stock_allocation", 1.0))
    @property
    def largest_position_pct(self): return float(self._p("largest_position_pct", 0.0))

    # --- guardrail / affordability defaults (Config falls back to these) ---
    @property
    def gr_upper(self): return float(self._p("gr_upper", 0.055))
    @property
    def gr_lower(self): return float(self._p("gr_lower", 0.035))
    @property
    def gr_cut(self): return float(self._p("gr_cut", 0.10))
    @property
    def gr_raise(self): return float(self._p("gr_raise", 0.10))
    @property
    def gr_floor(self): return float(self._p("gr_floor", 0.75))
    @property
    def gr_ceiling(self): return float(self._p("gr_ceiling", 1.25))
    @property
    def car_wr_ceiling(self): return float(self._p("car_wr_ceiling", 0.055))

    # --- keep-working scenario params (Config.retire_year) ---
    @property
    def kw_salary(self): return float(self._p("kw_salary", 0))
    @property
    def kw_salary_growth(self): return float(self._p("kw_salary_growth", 0.0))
    @property
    def kw_bonus(self): return float(self._p("kw_bonus", 0))
    @property
    def kw_annual_grant(self): return float(self._p("kw_annual_grant", 0))
    @property
    def kw_grant_vest_years(self): return int(self._p("kw_grant_vest_years", 4))
    @property
    def kw_401k_pct(self): return float(self._p("kw_401k_pct", 0.0))
    @property
    def kw_match_pct(self): return float(self._p("kw_match_pct", 0.0))

    # ---- owner matching ----
    def owner_key(self, owner: str) -> str:
        """'husband', 'wife' or 'joint' for an owner / person cell."""
        o = str(owner).strip().lower()
        if o in ("husband", "h", self.husband_name.strip().lower()):
            return "husband"
        if o in ("wife", "w", self.wife_name.strip().lower()):
            return "wife"
        return "joint"

    # ---- derived account aggregates ----
    def _sum(self, pred):
        return sum(a["balance"] for a in self.accounts
                   if pred(self.owner_key(a["owner"]), a["tax_type"].strip().lower()))
    @property
    def taxable_start(self): return self._sum(lambda o, t: t == "taxable")
    @property
    def roth_start(self): return self._sum(lambda o, t: t == "roth")
    @property
    def dcp_balance(self): return self._sum(lambda o, t: "deferred" in t)
    @property
    def dcp_owner(self):
        h = self._sum(lambda o, t: o != "wife" and "deferred" in t)
        w = self._sum(lambda o, t: o == "wife" and "deferred" in t)
        return "wife" if w > h else "husband"
    @property
    def husband_traditional(self):
        # Traditional accounts are individually owned; a 'Joint' row counts as the husband's.
        return self._sum(lambda o, t: o != "wife" and "traditional" in t)
    @property
    def wife_traditional(self): return self._sum(lambda o, t: o == "wife" and "traditional" in t)
    @property
    def investable_start(self):
        return self.taxable_start + self.husband_traditional + self.wife_traditional + self.roth_start

    # ---- schedules ----
    @property
    def earned_income(self) -> dict:
        d = {}
        for year, _, amt in self.earned:
            d[int(year)] = d.get(int(year), 0.0) + float(amt)
        return d
    @property
    def vest_cash(self) -> dict:
        d = {}
        for year, _, amt in self.equity_vests:
            d[int(year)] = d.get(int(year), 0.0) + float(amt)
        return d
    @property
    def ss_monthly(self) -> dict:
        d = {"husband": {}, "wife": {}}
        for person, age, monthly, *_ in self.social_security:
            k = self.owner_key(person)
            if k in d:
                d[k][int(age)] = float(monthly)
        return d
    @property
    def fixed_nominal(self) -> dict:
        d = {}
        for f in self.fixed_payments:
            for y in range(f["start_year"], f["end_year"] + 1):
                d[y] = d.get(y, 0.0) + f["annual_nominal"]
        return d

    def _band(self, year):
        for s, e, amt, hc in self.spending:
            if int(s) <= year <= int(e):
                return float(amt), float(hc)
        return float(self.spending[-1][2]), float(self.spending[-1][3])

    def spending_real(self, year: int) -> float:
        """Lifestyle budget in today's $. The healthcare part grows faster than
        inflation by healthcare_inflation_extra per year."""
        amt, hc = self._band(year)
        g = (1 + self.healthcare_inflation_extra) ** (year - self.start_year)
        return amt + hc * (g - 1)

    @property
    def payout_years(self):
        if self.dcp_balance <= 0:
            return []
        return list(range(self.dcp_payout_start,
                          self.dcp_payout_start + self.dcp_payout_years))


# ===========================================================================
# Loader
# ===========================================================================
def _rows(ws):
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], []
    header = [str(c).strip().lower() if c is not None else "" for c in rows[0]]
    data = [r for r in rows[1:] if any(c is not None for c in r)]
    return header, data


def _num(v):
    return float(v) if v not in (None, "") else 0.0


def _dicts(wb, sheet):
    """Sheet rows as dicts keyed by lower-case header (empty list if the sheet is absent)."""
    if sheet not in wb.sheetnames:
        return []
    h, d = _rows(wb[sheet])
    return [{h[i]: r[i] for i in range(min(len(h), len(r))) if h[i]} for r in d]


def _get(row, *names, default=None):
    for n in names:
        if n in row and row[n] not in (None, ""):
            return row[n]
    return default


def load_inputs(path: str) -> Inputs:
    wb = openpyxl.load_workbook(path, data_only=True)

    params = {}
    for r in _dicts(wb, "Params"):
        k = _get(r, "param", "key")
        if k is not None:
            params[str(k).strip()] = r.get("value")

    accounts = []
    for r in _dicts(wb, "Accounts"):
        if _get(r, "account") is None:
            continue
        accounts.append(dict(account=str(r["account"]), owner=str(_get(r, "owner", default="joint")),
                             tax_type=str(_get(r, "tax_type", "tax type", default="Taxable")),
                             balance=_num(_get(r, "balance")),
                             as_of=to_date(_get(r, "as_of", "as of")),
                             source_file=_get(r, "source_file", "source file")))
    earned = [(int(r["year"]), str(_get(r, "component", default="")), _num(_get(r, "amount")))
              for r in _dicts(wb, "EarnedIncome") if _get(r, "year") is not None]
    vests = [(int(r["year"]), str(_get(r, "vest_date", default="")), _num(_get(r, "amount", "gross_amount")))
             for r in _dicts(wb, "EquityVests") if _get(r, "year") is not None]
    ss = [(str(r["person"]), int(_get(r, "claim_age", "age")), _num(_get(r, "monthly")),
           str(_get(r, "claim_date", default="")))
          for r in _dicts(wb, "SocialSecurity") if _get(r, "person") is not None]

    spend = []
    for r in _dicts(wb, "Spending"):
        if _get(r, "start_year") is None:
            continue
        hc = _num(_get(r, "healthcare"))
        amt = _get(r, "annual_real")
        if amt is None:
            amt = _num(_get(r, "base_ex_healthcare")) + hc + _num(_get(r, "other"))
        spend.append((int(r["start_year"]), int(r["end_year"]), float(amt), hc))

    big_purchases: dict = {}
    for r in _dicts(wb, "BigPurchases"):
        y, amt = _get(r, "year"), _get(r, "amount")
        if y is None or amt is None:
            continue
        big_purchases[int(y)] = big_purchases.get(int(y), 0.0) + float(amt)

    pensions = []
    for r in _dicts(wb, "Pensions"):
        if _get(r, "person") is None or _get(r, "annual_amount", "annual") is None:
            continue
        end = _get(r, "end_year")
        pensions.append(dict(person=str(r["person"]), kind=str(_get(r, "kind", default="pension")),
                             start_year=int(_get(r, "start_year")),
                             end_year=int(end) if end is not None else None,
                             annual=_num(_get(r, "annual_amount", "annual")),
                             cola=_yes(_get(r, "cola", default="no")),
                             survivor_pct=_num(_get(r, "survivor_pct", default=0))))

    fixed = []
    for r in _dicts(wb, "FixedPayments"):
        if _get(r, "start_year") is None:
            continue
        fixed.append(dict(item=str(_get(r, "item", default="")), start_year=int(r["start_year"]),
                          end_year=int(_get(r, "end_year", default=r["start_year"])),
                          annual_nominal=_num(_get(r, "annual_nominal", "amount"))))

    bills = []
    for r in _dicts(wb, "Bills"):
        if _get(r, "item") is None:
            continue
        months = [int(m) for m in str(_get(r, "due_months", default="")).replace(";", ",").split(",")
                  if m.strip().isdigit()]
        bills.append(dict(item=str(r["item"]), annual=_num(_get(r, "annual_amount", "amount")),
                          due_months=months, paid_via=str(_get(r, "paid_via", default="manual")).lower(),
                          in_spending=_yes(_get(r, "included_in_spending", default="yes"))))

    actions = []
    for r in _dicts(wb, "Actions"):
        d = to_date(_get(r, "date"))
        if d is None or _get(r, "action") is None:
            continue
        actions.append(dict(date=d, action=str(r["action"]), amount=_get(r, "amount"),
                            notes=str(_get(r, "notes", default=""))))

    return Inputs(params=params, accounts=accounts, earned=earned, equity_vests=vests,
                  social_security=ss, spending=spend, big_purchases=big_purchases,
                  pensions=pensions, fixed_payments=fixed, bills=bills, actions=actions)


# ===========================================================================
# Lock detection (so a script never clobbers the file while Excel has it open)
# ===========================================================================
def is_locked(path: str) -> bool:
    """True if the workbook cannot be opened for writing (typically because it
    is open in Excel, which takes an exclusive write lock)."""
    if not os.path.exists(path):
        return False
    lock_sidecar = os.path.join(os.path.dirname(path), "~$" + os.path.basename(path))
    if os.path.exists(lock_sidecar):
        return True
    try:
        with open(path, "r+b"):
            return False
    except (PermissionError, OSError):
        return True


def assert_writable(path: str) -> None:
    """Raise a clear, actionable error if the workbook is locked."""
    if is_locked(path):
        raise PermissionError(
            f"'{os.path.basename(path)}' appears to be open in Excel (locked). "
            f"Save and close it, then retry.")
