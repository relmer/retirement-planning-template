"""ss_optimize.py: sweep husband x wife SS claim ages (62-70) for success & ending.
Vectorized MC + optional multiprocessing across the claim-age combinations.
Common RNG seed across combos so differences reflect strategy, not MC noise.

Usage:  python model/ss_optimize.py              # parallel (all cores)
        python model/ss_optimize.py --serial     # single process
        python model/ss_optimize.py --guardrails # evaluate with guardrails on
"""
import argparse, itertools, time, os
from pathlib import Path
import pandas as pd
import retirement_model as M
from retirement_model import Config, run_deterministic, run_monte_carlo
from inputs_io import load_inputs

ROOT = Path(__file__).resolve().parent.parent
XLSX = str(ROOT / "Inputs.xlsx")
AGES = range(62, 71)
NP = 2000
GUARDRAILS = False


def _init(path, guardrails):
    global GUARDRAILS
    GUARDRAILS = guardrails
    M.set_inputs(load_inputs(path))


def _eval(combo):
    h, w = combo
    cfg = Config(husband_claim_age=h, wife_claim_age=w, guardrails=GUARDRAILS)
    d = run_deterministic(cfg, 0.065); e = d.iloc[-1]["total"]
    dep = 9999 if e > 0 else int(d[d.total <= 0].year.min())
    r = run_monte_carlo(cfg, n_paths=NP)          # default seed -> common random numbers
    c = M.run_monte_carlo_historical(cfg, method="cyclical")
    return dict(husband=h, wife=w, success=round(r["success_rate"], 4),
                cyclical=round(c["success_rate"], 4),
                mean_end=int(r["ending"].mean()), p90=int(r["p90_ending"]),
                deplete=dep, end_at_6_5pct=int(e))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", action="store_true", help="single process")
    ap.add_argument("--guardrails", action="store_true", help="evaluate with guardrails on")
    args = ap.parse_args()
    combos = list(itertools.product(AGES, AGES))

    t0 = time.time()
    if args.serial:
        _init(XLSX, args.guardrails)
        rows = [_eval(c) for c in combos]
        mode = "serial"
    else:
        from concurrent.futures import ProcessPoolExecutor
        workers = min(os.cpu_count() or 4, len(combos))
        with ProcessPoolExecutor(max_workers=workers, initializer=_init,
                                 initargs=(XLSX, args.guardrails)) as ex:
            rows = list(ex.map(_eval, combos))
        mode = f"parallel x{workers}"

    inp = load_inputs(XLSX)
    df = pd.DataFrame(rows)
    (ROOT / "output").mkdir(exist_ok=True)
    df.to_csv(ROOT / "output" / "ss_optimization.csv", index=False)
    print(f"({time.time()-t0:.0f}s, {mode}, {len(df)} combos x {NP} paths, "
          f"guardrails {'ON' if args.guardrails else 'OFF'})")
    print(f"husband = {inp.husband_name}, wife = {inp.wife_name}\n")

    print("TOP 5 FOR SUCCESS (parametric):")
    print(df.sort_values(["success", "mean_end"], ascending=False)
            .head(5)[["husband", "wife", "success", "cyclical", "mean_end", "deplete"]].to_string(index=False))
    print("\nTOP 5 FOR ENDING VALUE (MC mean):")
    print(df.sort_values("mean_end", ascending=False)
            .head(5)[["husband", "wife", "mean_end", "p90", "success", "deplete"]].to_string(index=False))
    print(f"\nSuccess range across all combos: "
          f"{df.success.min()*100:.1f}% - {df.success.max()*100:.1f}%")
    print("\nSame-age diagonal (both claim X):")
    for a in AGES:
        r = df[(df.husband == a) & (df.wife == a)].iloc[0]
        print(f"  {a}/{a}: success {r['success']*100:4.1f}%  cyclical {r['cyclical']*100:4.1f}%  "
              f"mean_end {r['mean_end']:>12,.0f}")


if __name__ == "__main__":
    main()
