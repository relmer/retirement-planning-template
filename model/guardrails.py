"""Guardrails (Guyton-Klinger) impact: success + the spending-cut experience, per return model."""
import numpy as np
import retirement_model as M
from retirement_model import Config, bootstrap_returns, cyclical_returns
from inputs_io import load_inputs
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
M.set_inputs(load_inputs(str(ROOT / "Inputs.xlsx")))
inp = M._inp()
ny = inp.end_year - inp.start_year + 1

base = Config()
guard = Config(guardrails=True)   # bands / floor from the Params sheet

print(f"GUARDRAILS (Guyton-Klinger {inp.gr_lower*100:.1f}%-{inp.gr_upper*100:.1f}% bands, "
      f"floor {inp.gr_floor:.2f}x), claim {inp.default_husband_claim_age}/{inp.default_wife_claim_age}\n")
for label, returns in [
    ("Parametric IID-normal", None),
    ("Historical bootstrap", bootstrap_returns(6000, ny, inp.inflation, seed=inp.mc_seed)),
    ("Historical cyclical (FICalc)", cyclical_returns(ny, inp.inflation)),
]:
    if returns is None:
        b = M.run_monte_carlo(base, n_paths=6000)
        g = M.run_monte_carlo_vectorized(guard, n_paths=6000)
    else:
        b = M.run_monte_carlo_vectorized(base, _returns=returns)
        g = M.run_monte_carlo_vectorized(guard, _returns=returns)
    gm = g["final_gr_mult"]
    print(f"{label}:")
    print(f"  success   : {b['success_rate']*100:5.1f}%  ->  {g['success_rate']*100:5.1f}%  "
          f"({(g['success_rate']-b['success_rate'])*100:+.1f} pts)")
    print(f"  final spend multiplier (guardrails): "
          f"median {np.median(gm)*100:.0f}%  p10 {np.percentile(gm,10)*100:.0f}%  "
          f"p90 {np.percentile(gm,90)*100:.0f}%  min {gm.min()*100:.0f}%")
    cut = (g["gr_min"] < 0.999).mean()
    print(f"  paths that ever cut spending: {cut*100:.0f}%   "
          f"median years at the floor: {np.median(g['gr_years_at_floor']):.0f}\n")
