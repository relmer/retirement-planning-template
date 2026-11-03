"""build_inputs.py: (re)creates Inputs.xlsx populated with a FICTIONAL sample household.

    python model/build_inputs.py               # writes ./Inputs.xlsx (refuses to overwrite)
    python model/build_inputs.py --force       # overwrite an existing Inputs.xlsx
    python model/build_inputs.py other.xlsx    # write somewhere else

Every number below is made up. Replace all of them with your own (AGENTS.md
describes the interview that does this).
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from inputs_io import assert_writable, load_inputs

ROOT = Path(__file__).resolve().parent.parent

# Marker preflight uses to detect an untouched sample workbook.
SAMPLE_MARKER = "SAMPLE DATA: replace every value"

# ===========================================================================
# Sample data (fictional Georgia household: "Alex" and "Jordan")
# ===========================================================================
PARAMS = [
    # key, value, notes (what it is, where to find it)
    ("household", SAMPLE_MARKER, "Free text label for this plan. Preflight flags the workbook while this cell contains the sample marker."),
    ("husband_name", "Alex", "First name. Use the same text in Accounts.owner, SocialSecurity.person and Pensions.person."),
    ("wife_name", "Jordan", "First name."),
    ("husband_birth", "1968-04-10", "YYYY-MM-DD. Sets ages, Social Security start month, Medicare and RMD dates."),
    ("wife_birth", "1970-11-22", "YYYY-MM-DD."),
    ("state", "GA", "Two-letter state of residence (model/data/state_tax/<XX>.json must exist), or NONE."),
    ("start_year", 2027, "First modeled year. Account balances are as of Jan 1 of this year (or the as_of date)."),
    ("plan_to_age", 95, "Plan horizon: the model runs until the YOUNGER spouse reaches this age. 95 is a sensible default; use 100 for longevity in the family."),
    ("end_year", None, "Optional: overrides plan_to_age with an explicit last year."),
    ("retire_date", "2026-12-31", "Last day of work (or blank if already retired). Drives COBRA and the action schedule."),
    ("cobra_months", 18, "Months of COBRA coverage after retire_date (0 if going straight to ACA/Medicare/other)."),
    ("inflation", 0.03, "Annual inflation. Spending, tax brackets and SS COLA index by this."),
    ("healthcare_inflation_extra", 0.02, "Extra annual growth of the Spending.healthcare column above inflation (medical costs historically outpace CPI)."),
    ("equity_real_mean", 0.065, "Pessimistic (parametric) lens: mean REAL annual return, arithmetic."),
    ("equity_vol", 0.18, "Pessimistic (parametric) lens: annual standard deviation of returns."),
    ("stock_allocation", 0.90, "Actual stock share of the portfolio today (informational; the engine models 100% stocks, see tools/levers.py for 60/40)."),
    ("largest_position_pct", 0.08, "Largest single stock as a share of the investable portfolio (concentration check)."),
    ("taxable_basis_fraction", 0.60, "Cost basis / market value of the taxable account(s). tools/basis_from_positions.py computes it from a positions CSV."),
    ("taxable_dividend_yield", 0.015, "Dividend + interest yield of the taxable account (from the positions export or fund pages)."),
    ("husband_claim_age", 67, "Default Social Security claim age (62-70)."),
    ("wife_claim_age", 67, "Default Social Security claim age (62-70)."),
    ("ss_statement_date", "2026-10-01", "Date of the ssa.gov statements used in SocialSecurity (refresh yearly)."),
    ("ss_cut_year", 2034, "Year a Social Security trust-fund shortfall would cut benefits (stress test)."),
    ("ss_cut_factor", 1.0, "1.0 = no cut. The stress test in the report uses 0.77 (the projected payable share)."),
    ("roth_conversion_ceiling", 0, "Convert traditional->Roth each year up to this ordinary TAXABLE income, in today's $ (0 = off)."),
    ("survivor_spend_pct", 0.80, "Spending after the first death, as a fraction of the couple's budget."),
    ("survivor_test_age", 80, "Survivor stress test: each spouse in turn dies in the year they reach this age."),
    ("target_success", 0.80, "Success target on the PESSIMISTIC lens with guardrails. The levers analysis aims for this."),
    ("mc_paths", 3000, "Monte Carlo paths for the headline runs."),
    ("mc_seed", 42, "Random seed (same seed => same paths => comparisons reflect strategy, not noise)."),
    ("dcp_payout_start", 2027, "Deferred-comp (NQDC) payout start year. Ignored if no 'Deferred comp' account."),
    ("dcp_payout_years", 5, "Deferred-comp installments: remaining balance / years left."),
    ("gr_upper", 0.055, "Guardrails: CUT spending one step if lifestyle / portfolio exceeds this."),
    ("gr_lower", 0.035, "Guardrails: RAISE spending one step if lifestyle / portfolio is below this."),
    ("gr_cut", 0.10, "Guardrails: size of one cut step."),
    ("gr_raise", 0.10, "Guardrails: size of one raise step."),
    ("gr_floor", 0.75, "Guardrails: lowest cumulative spending multiplier (floor = this x planned lifestyle). tools/floor_menu.py helps choose it."),
    ("gr_ceiling", 1.25, "Guardrails: highest cumulative spending multiplier."),
    ("car_wr_ceiling", 0.055, "Affordability rule for BigPurchases: buy only up to what keeps the net withdrawal rate at or below this."),
    ("kw_salary", 180_000, "Keep-working scenario: base salary if the husband works longer (nominal). 0 if not applicable."),
    ("kw_salary_growth", 0.03, "Keep-working: nominal annual raise."),
    ("kw_bonus", 20_000, "Keep-working: annual bonus (nominal, flat)."),
    ("kw_annual_grant", 0, "Keep-working: gross value of each new annual stock grant (0 if none)."),
    ("kw_grant_vest_years", 4, "Keep-working: years each new grant vests over."),
    ("kw_401k_pct", 0.10, "Keep-working: employee pre-tax 401(k) contribution, fraction of salary."),
    ("kw_match_pct", 0.50, "Keep-working: employer match as a fraction of the employee contribution."),
]

ACCOUNTS = [  # account, owner, tax_type, balance, as_of, source_file
    ("Joint brokerage", "Joint", "Taxable", 850_000, "2026-12-31", "private/accounts/brokerage/2026-12-31_joint_positions.csv"),
    ("Alex 401(k)", "Alex", "Traditional (pre-tax)", 1_400_000, "2026-12-31", "private/accounts/401k/2026-12-31_alex_401k.pdf"),
    ("Alex rollover IRA", "Alex", "Traditional (pre-tax)", 200_000, "2026-12-31", ""),
    ("Jordan 403(b)", "Jordan", "Traditional (pre-tax)", 450_000, "2026-12-31", ""),
    ("Roth IRAs (both)", "Joint", "Roth", 120_000, "2026-12-31", ""),
    ("HSA (modeled as tax-free)", "Alex", "Roth", 35_000, "2026-12-31", ""),
    ("Deferred comp (optional)", "Alex", "Deferred comp", 0, "", ""),
]

EARNED = [  # year, component, amount (ordinary income)
    (2027, "Part-time consulting (Alex)", 40_000),
    (2028, "Part-time consulting (Alex)", 40_000),
]

VESTS = [  # year, vest_date, award, shares, amount, note
    (2027, "2027-03-15", "Final grant", 150, 60_000, "Gross value at vest; ordinary income"),
    (2028, "2028-03-15", "Final grant", 75, 30_000, ""),
]

SOCIAL_SECURITY = [  # person, claim_age, monthly (today's $), claim_date
    ("Alex", 62, 2_400, "2030-05"), ("Alex", 67, 3_450, "2035-05"), ("Alex", 70, 4_300, "2038-05"),
    ("Jordan", 62, 1_500, "2032-12"), ("Jordan", 67, 2_150, "2037-12"), ("Jordan", 70, 2_650, "2040-12"),
]

PENSIONS = [  # person, kind, start_year, end_year, annual_amount, cola, survivor_pct, note
    ("Jordan", "pension", 2030, None, 18_000, "no", 0.5, "State teacher pension, 50% joint-and-survivor"),
]

SPENDING = [  # start_year, end_year, annual_real, base_ex_healthcare, healthcare, other, note
    (2027, 2028, None, 150_000, 22_000, 0, "COBRA through mid-2028, then ACA marketplace"),
    (2029, 2032, None, 150_000, 26_000, 0, "ACA marketplace until Alex reaches 65"),
    (2033, 2035, None, 150_000, 18_000, 0, "Alex on Medicare, Jordan on ACA"),
    (2036, 2065, None, 140_000, 14_000, 0, "Both on Medicare (Part B + D + Medigap)"),
]

FIXED_PAYMENTS = [  # item, start_year, end_year, annual_nominal, note
    ("Mortgage principal + interest", 2027, 2034, 21_600, "Fixed nominal payment; NOT in Spending. Escrowed tax/insurance go in Spending."),
]

BIG_PURCHASES = [  # year, item, amount (today's $; negative = one-time inflow)
    (2029, "Car", 45_000),
    (2031, "Roof", 25_000),
    (2037, "Car", 45_000),
    (2045, "Car", 40_000),
]

BILLS = [  # item, annual_amount, due_months, paid_via, included_in_spending
    ("Property tax", 6_500, "11", "escrow", "yes"),
    ("Homeowners insurance", 2_800, "6", "escrow", "yes"),
    ("Auto insurance", 2_400, "3,9", "manual", "yes"),
    ("Umbrella policy", 450, "5", "autopay", "yes"),
]

ACTIONS = [  # date, action, amount, notes
    ("2027-01-15", "Sell concentrated stock lot (first tranche)", 50_000, "Example custom action; replace or delete"),
]

README = [
    "RETIREMENT MODEL INPUT WORKBOOK (source of truth)",
    "",
    "model/run.py loads this file. Edit values here, save, close Excel, then re-run.",
    "Data sheets are parsed BY HEADER NAME (row 1): columns may be reordered, extra columns are ignored.",
    "This README sheet is ignored. Every number shipped in this workbook is FICTIONAL sample data.",
    "",
    "All money is in TODAY'S dollars (real) unless a column says nominal. The model inflates it.",
    "",
    "Sheets:",
    "  Params          scalar settings: people, state, horizon, returns, claim ages, guardrails. See the notes column.",
    "  Accounts        every account: account, owner, tax_type, balance, as_of (balance date), source_file (export it came from).",
    "  EarnedIncome    year, component, amount: wages/severance/bonus/consulting AFTER the plan starts (ordinary income).",
    "  EquityVests     future RSU vests: year, vest_date, amount (gross value; ordinary income at vest). Delete the rows if none.",
    "  SocialSecurity  person, claim_age, monthly: from ssa.gov/myaccount, at least ages 62, 67 and 70.",
    "  Pensions        person, kind, start_year, end_year, annual_amount, cola (yes/no), survivor_pct. Annuities too.",
    "  Spending        bands of years with a real annual lifestyle budget (taxes are added by the model).",
    "                  A blank annual_real cell = base_ex_healthcare + healthcare + other.",
    "                  Include escrowed property tax and insurance, healthcare premiums, travel, gifts. Exclude mortgage P&I.",
    "  FixedPayments   nominal payments that do NOT rise with inflation: mortgage P&I, car loans (item, start/end year, annual).",
    "  BigPurchases    year, item, amount: cars, roofs, weddings. Negative = one-time inflow (home downsizing, inheritance).",
    "  Bills           lumpy bills for the action schedule only (already counted in Spending): due months, paid_via escrow/autopay/manual.",
    "  Actions         any other dated to-do (trades, elections, deadlines): date, action, amount, notes.",
    "",
    "tax_type values: 'Taxable', 'Traditional (pre-tax)', 'Roth', 'Deferred comp'.",
    "  Put an HSA under 'Roth' (spent on medical, it is tax-free).",
    "  'Deferred comp' = an employer NQDC plan paid out in installments (see dcp_* in Params).",
    "owner values: husband_name, wife_name, or 'Joint'. Traditional accounts marked Joint count as the husband's.",
]

HDR_FILL = PatternFill("solid", fgColor="1F4E78")
HDR_FONT = Font(bold=True, color="FFFFFF")
MONEY = "#,##0"


def _sheet(wb, name, header, rows, widths=None, money_cols=()):
    ws = wb.create_sheet(name)
    ws.append(header)
    for c in range(1, len(header) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = HDR_FILL; cell.font = HDR_FONT
        cell.alignment = Alignment(horizontal="center")
    for row in rows:
        ws.append(list(row))
    for ci in money_cols:
        for r in range(2, 2 + max(len(rows), 30)):
            ws.cell(row=r, column=ci).number_format = MONEY
    if widths:
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    return ws


def _choices(ws, rng, values):
    dv = DataValidation(type="list", formula1='"' + ",".join(values) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(rng)


def build_input_workbook(path: str):
    assert_writable(path)
    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "README"
    for i, ln in enumerate(README, 1):
        ws.cell(row=i, column=1, value=ln)
    ws["A1"].font = Font(bold=True, size=13)
    ws.column_dimensions["A"].width = 130

    _sheet(wb, "Params", ["param", "value", "notes"], PARAMS, widths=[26, 18, 130])
    acc = _sheet(wb, "Accounts", ["account", "owner", "tax_type", "balance", "as_of", "source_file"],
                 ACCOUNTS, widths=[30, 12, 24, 16, 12, 60], money_cols=(4,))
    _choices(acc, "C2:C200", ["Taxable", "Traditional (pre-tax)", "Roth", "Deferred comp"])
    _sheet(wb, "EarnedIncome", ["year", "component", "amount"], EARNED, widths=[8, 40, 14], money_cols=(3,))
    _sheet(wb, "EquityVests", ["year", "vest_date", "award", "shares", "amount", "note"],
           VESTS, widths=[8, 12, 18, 8, 14, 50], money_cols=(5,))
    _sheet(wb, "SocialSecurity", ["person", "claim_age", "monthly", "claim_date"],
           SOCIAL_SECURITY, widths=[12, 10, 12, 12], money_cols=(3,))
    pen = _sheet(wb, "Pensions", ["person", "kind", "start_year", "end_year", "annual_amount", "cola",
                                  "survivor_pct", "note"],
                 PENSIONS, widths=[12, 12, 10, 10, 14, 8, 12, 50], money_cols=(5,))
    _choices(pen, "F2:F100", ["yes", "no"])
    _sheet(wb, "Spending",
           ["start_year", "end_year", "annual_real", "base_ex_healthcare", "healthcare", "other", "note"],
           SPENDING, widths=[12, 10, 14, 20, 14, 12, 70], money_cols=(3, 4, 5, 6))
    _sheet(wb, "FixedPayments", ["item", "start_year", "end_year", "annual_nominal", "note"],
           FIXED_PAYMENTS, widths=[34, 10, 10, 16, 80], money_cols=(4,))
    _sheet(wb, "BigPurchases", ["year", "item", "amount"], BIG_PURCHASES, widths=[8, 30, 14], money_cols=(3,))
    bills = _sheet(wb, "Bills", ["item", "annual_amount", "due_months", "paid_via", "included_in_spending"],
                   BILLS, widths=[28, 14, 12, 12, 20], money_cols=(2,))
    _choices(bills, "D2:D100", ["escrow", "autopay", "manual"])
    _sheet(wb, "Actions", ["date", "action", "amount", "notes"], ACTIONS, widths=[12, 50, 14, 60], money_cols=(3,))
    wb.save(path)
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=str(ROOT / "Inputs.xlsx"))
    ap.add_argument("--force", action="store_true", help="overwrite an existing workbook")
    args = ap.parse_args()
    if os.path.exists(args.path) and not args.force:
        raise SystemExit(f"{args.path} exists. Pass --force to overwrite it with the sample data.")
    build_input_workbook(args.path)
    inp = load_inputs(args.path)
    print("Built and re-loaded:", args.path)
    print(f"  investable {inp.investable_start:,.0f} | horizon {inp.start_year}-{inp.end_year} | state {inp.state}")
