"""floor_menu.py: menu of guardrail floors, expressed as a yearly and monthly spend,
the monthly cut from the full lifestyle, and the success payoff under all three
return models. Use it to choose gr_floor in the Params sheet.
"""
import numpy as np
from _setup import load, first_portfolio_funded_year, M
from retirement_model import Config

inp = load()
NP = 8000
n_years = inp.end_year - inp.start_year + 1
eq_mean = (1 + inp.equity_real_mean) * (1 + inp.inflation) - 1
RET = {
    "cyclical": M.cyclical_returns(n_years, inp.inflation),
    "bootstrap": M.bootstrap_returns(NP, n_years, inp.inflation, seed=inp.mc_seed),
    "parametric": np.random.default_rng(inp.mc_seed).normal(eq_mean, inp.equity_vol, (NP, n_years)),
}
FULL = inp.spending_real(first_portfolio_funded_year(inp))

print(f"Full lifestyle = ${FULL:,.0f}/yr = ${FULL/12:,.0f}/mo (real, first portfolio-funded year)\n")
print(f"{'floor/yr':>10}{'floor/mo':>10}{'cut/mo':>9}{'gr_floor':>9}"
      f"{'param':>8}{'boot':>7}{'cyc':>7}{'yrs@floor (par med)':>21}")
for grf in (1.00, 0.95, 0.90, 0.85, 0.80, 0.75, 0.70, 0.65, 0.60):
    fl = FULL * grf
    cfg = Config(guardrails=True, gr_floor=grf)
    out = {m: M.run_monte_carlo_vectorized(cfg, _returns=RET[m]) for m in RET}
    yflr = int(np.median(np.asarray(out["parametric"]["gr_years_at_floor"])))
    print(f"${fl/1000:>8.0f}K${fl/12:>9,.0f}{-(FULL-fl)/12:>9,.0f}{grf:>9.2f}"
          f"{out['parametric']['success_rate']*100:>7.1f}%"
          f"{out['bootstrap']['success_rate']*100:>6.1f}%"
          f"{out['cyclical']['success_rate']*100:>6.1f}%{yflr:>16} yrs")
print("\n('yrs@floor' = median years a parametric path spends pinned at that minimum.)")
