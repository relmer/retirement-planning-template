"""Shared bootstrap for the scripts in model/tools: puts model/ on sys.path and
loads Inputs.xlsx. Every tool runs from any working directory."""
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "model"
OUTPUT = ROOT / "output"
INPUT = ROOT / "Inputs.xlsx"
sys.path.insert(0, str(MODEL))

import retirement_model as M          # noqa: E402
from inputs_io import load_inputs     # noqa: E402


def load():
    inp = load_inputs(str(INPUT))
    M.set_inputs(inp)
    OUTPUT.mkdir(exist_ok=True)
    return inp


def money(x):
    return f"${x:,.0f}"


def money_m(x):
    return f"${x/1e6:.2f}M"


def first_portfolio_funded_year(inp):
    """First year with no earned income, vests or deferred-comp payout (guardrails apply from here)."""
    for y in range(inp.start_year, inp.end_year + 1):
        if (inp.earned_income.get(y, 0) == 0 and inp.vest_cash.get(y, 0) == 0
                and y not in inp.payout_years):
            return y
    return inp.end_year
