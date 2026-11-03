"""Compare parametric (IID-normal) vs historical (bootstrap/cyclical) Monte Carlo
for the plan, including bootstrap block-length sensitivity. Useful when
reconciling against FICalc.app (which uses the cyclical method)."""
import numpy as np
import retirement_model as M
from retirement_model import (Config, run_monte_carlo, run_monte_carlo_historical,
                              bootstrap_returns)
from inputs_io import load_inputs
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
M.set_inputs(load_inputs(str(ROOT / "Inputs.xlsx")))
inp = M._inp()
ny = inp.end_year - inp.start_year + 1
cfg = Config()

# sanity: generated paths reproduce the historical stats
boot = bootstrap_returns(4000, ny, inp.inflation, seed=1, block_mean=8)
real = (1 + boot) / (1 + inp.inflation) - 1
print("Generated bootstrap real-return stats (source is ~6.8% geo / 18% sd):")
print(f"  arith mean {real.mean()*100:.2f}%  sd {real.std()*100:.2f}%  "
      f"geo {(np.exp(np.log1p(real).mean())-1)*100:.2f}%\n")

print(f"Plan (claim {inp.default_husband_claim_age}/{inp.default_wife_claim_age}): success at planned spending\n")
para = run_monte_carlo(cfg, n_paths=6000)["success_rate"]
print(f"  Parametric IID-normal ({inp.equity_real_mean*100:.1f}% arith, {inp.equity_vol*100:.0f}% vol): {para*100:5.1f}%")
for bm in (1, 4, 8, 15):
    s = run_monte_carlo_historical(cfg, method="bootstrap", n_paths=6000, block_mean=bm)["success_rate"]
    tag = " (=IID resample of history)" if bm == 1 else ""
    print(f"  Historical bootstrap, mean block {bm:2d}yr:       {s*100:5.1f}%{tag}")
cyc = run_monte_carlo_historical(cfg, method="cyclical")
print(f"  Historical cyclical (FICalc-exact, {len(cyc['ending'])} windows): {cyc['success_rate']*100:5.1f}%")
