"""charts.py: matplotlib figures (headless). Each function writes a PNG."""
from __future__ import annotations
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import retirement_model as M
from retirement_model import Config, run_deterministic


def _claim_text(inp):
    return f"SS claim {inp.default_husband_claim_age}/{inp.default_wife_claim_age}"


def portfolio_trajectory(path, returns=(0.03, 0.05, 0.065, 0.08)):
    inp = M._inp()
    fig, ax = plt.subplots(figsize=(9, 5))
    for r in returns:
        d = run_deterministic(Config(), r)
        ax.plot(d["year"], d["total_incl_dcp"] / 1e6, label=f"{r*100:.1f}% real")
    ax.set_xlabel("Year"); ax.set_ylabel("Portfolio ($M, nominal)")
    ax.set_title(f"Deterministic portfolio trajectory ({_claim_text(inp)})")
    ax.axhline(0, color="k", lw=0.8); ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)


def mc_fan(path, returns, label):
    """Percentile fan of real (today's $) portfolio value, guardrails on."""
    inp = M._inp()
    res = M.run_monte_carlo_vectorized(Config(guardrails=True), _returns=returns, track=True)
    years = np.arange(inp.start_year, inp.end_year + 1)
    defl = np.array([M.infl_factor(y) for y in years])
    mat = res["totals"] / defl[None, :]
    p10, p25, p50, p75, p90 = np.percentile(mat, [10, 25, 50, 75, 90], axis=0)
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.fill_between(years, p10 / 1e6, p90 / 1e6, alpha=0.20, label="10th-90th pct")
    ax.fill_between(years, p25 / 1e6, p75 / 1e6, alpha=0.30, label="25th-75th pct")
    ax.plot(years, p50 / 1e6, color="navy", label="median")
    ax.set_xlabel("Year"); ax.set_ylabel(f"Portfolio ($M, {inp.start_year} dollars)")
    ax.set_title(f"{label}: success {res['success_rate']*100:.0f}% with guardrails")
    ax.axhline(0, color="k", lw=0.8); ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)


def success_curve(path, df_success, target_spend, target_success):
    inp = M._inp()
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(df_success["lifestyle_spend"] / 1e3, df_success["pessimistic_success_gk"] * 100,
            marker="o", color="darkgreen")
    ax.axvline(target_spend / 1e3, color="crimson", ls="--", label=f"plan ${target_spend/1e3:.0f}k")
    ax.axhline(target_success * 100, color="gray", ls=":", alpha=0.7,
               label=f"target {target_success*100:.0f}%")
    ax.set_xlabel(f"Lifestyle spend ({inp.start_year} $000/yr)")
    ax.set_ylabel("Pessimistic success with guardrails (%)")
    ax.set_title("Success probability vs. spending level")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)
