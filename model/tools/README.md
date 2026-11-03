# `model/tools/`

| Script | Purpose |
|---|---|
| `floor_menu.py` | Price each guardrail floor: yearly and monthly spend, the monthly cut from the full lifestyle, and success under all three lenses. Pick `gr_floor` from it. |
| `basis_from_positions.py <csv>` | `taxable_basis_fraction` from a brokerage positions CSV. |
| `guard.py` | Privacy checks run by the git hooks in `.githooks` (see `setup_clone.py`). |

Every output document has a module in `model/reports/` that runs
standalone (`python model/reports/levers.py`). `python model/run.py` runs them
all.

## Custom questions

```python
import sys; sys.path.insert(0, "model/reports")
from common import load, M
from retirement_model import Config

inp = load()
r = M.run_monte_carlo(Config(guardrails=True, husband_claim_age=70, spend_multiplier=0.95), n_paths=4000)
print(r["success_rate"])
```

`Config` fields override the workbook for one run: claim ages, spending
multiplier, Roth ceiling, guardrail settings, `retire_year` (keep working),
`first_death_age` / `first_to_die` (survivor), `ss_cut_factor`, extra
one-time spending (`extra_real`, `extra_nominal`), and a conditional home
purchase. `M.lens_returns("bootstrap")` / `("cyclical")` return the historical
lens matrices for `M.run_monte_carlo_vectorized(cfg, _returns=...)`.
