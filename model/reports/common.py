"""Shared helpers for the report generators in model/reports."""
from __future__ import annotations
import datetime as dt
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "model"
OUTPUT = ROOT / "output"
DATA_OUT = OUTPUT / "data"
FIG = OUTPUT / "figures"
INPUT = ROOT / "Inputs.xlsx"
if str(MODEL) not in sys.path:
    sys.path.insert(0, str(MODEL))

import retirement_model as M          # noqa: E402
from inputs_io import load_inputs     # noqa: E402

TODAY = dt.date.today()


def load(path=None):
    """Load Inputs.xlsx into the engine (standalone runs of a report module)."""
    inp = load_inputs(str(path or INPUT))
    M.set_inputs(inp)
    for d in (OUTPUT, DATA_OUT, FIG):
        d.mkdir(exist_ok=True)
    return inp


def write(name, md):
    path = OUTPUT / name
    path.write_text(md if md.endswith("\n") else md + "\n", encoding="utf-8")
    return path


def money(x):
    return f"${x:,.0f}"


def money_k(x):
    return f"${x/1e3:,.0f}k"


def money_m(x):
    return f"${x/1e6:.2f}M"


def pct(x):
    return f"{x*100:.0f}%"


def first_portfolio_funded_year(inp):
    """First year with no earned income, vests or deferred-comp payout (guardrails apply from here)."""
    for y in range(inp.start_year, inp.end_year + 1):
        if (inp.earned_income.get(y, 0) == 0 and inp.vest_cash.get(y, 0) == 0
                and y not in inp.payout_years):
            return y
    return inp.end_year


def horizon_text(inp):
    yb = max(inp.husband_birth[0], inp.wife_birth[0])
    younger = inp.husband_name if inp.husband_birth[0] == yb else inp.wife_name
    older = inp.wife_name if younger == inp.husband_name else inp.husband_name
    ob = min(inp.husband_birth[0], inp.wife_birth[0])
    return (f"through **{inp.end_year}**, when {younger} reaches **{inp.end_year - yb}** "
            f"and {older} would be **{inp.end_year - ob}**")


def quick_paths(quick, full):
    return max(200, full // 8) if quick else full
