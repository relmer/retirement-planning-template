"""run.py: one command to regenerate EVERY output document from Inputs.xlsx.

Usage (from anywhere):
    python model/run.py            # full run (a few minutes)
    python model/run.py --quick    # fewer Monte Carlo paths (fast check of inputs)

Reads:   <root>/Inputs.xlsx, model/data/federal_tax.json, model/data/state_tax/<state>.json
Writes:  <root>/output/START_HERE.md and the documents it lists
"""
from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "reports"))

from common import load, quick_paths, OUTPUT, INPUT   # noqa: E402
import analysis as A                                   # noqa: E402
import preflight, detailed, levers, survivor, operating_plan, draw_schedule, action_schedule, retire_sweep, summary  # noqa: E402,E401


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="fewer Monte Carlo paths (fast)")
    ap.add_argument("--input", default=str(INPUT))
    args = ap.parse_args()
    t0 = time.time()
    inp = load(args.input)
    print(f"Inputs : {args.input}")
    print(f"Plan   : {inp.husband_name} & {inp.wife_name}, {inp.start_year}-{inp.end_year}, state {inp.state}")

    F, n = preflight.build(args.quick)
    print(f"[1] Preflight.md            {n['BLOCKER']} blocker(s), {n['WARN']} warning(s)")
    for f in F:
        if f["level"] == "BLOCKER":
            print(f"      BLOCKER {f['area']}: {f['msg']}")

    mats = A.lens_matrices(quick_paths(args.quick, inp.mc_paths))
    det = detailed.build(args.quick, mats)
    g = det["gk"]
    print(f"[2] Detailed_Report.md      pessimistic {g['parametric']['success_rate']:.1%} | "
          f"middle {g['bootstrap']['success_rate']:.1%} | optimistic {g['cyclical']['success_rate']:.1%} (guardrails)")
    lev = levers.build(args.quick)
    print(f"[3] Levers.md               {len(lev['top'])} lever(s) with a gain")
    surv = survivor.build(args.quick, mats)
    print("[4] Survivor.md")
    operating_plan.build(args.quick)
    print("[5] Annual_Operating_Plan.md")
    draw_schedule.build(args.quick)
    print("[6] Draw_Schedule.md")
    action_schedule.build(args.quick)
    print("[7] Action_Schedule.md")
    sweep = retire_sweep.build(args.quick, mats)
    if sweep:
        print("[8] Retire_Year_Sweep.md")
    summary.build(n, F, det, lev, surv, sweep)
    print(f"[9] START_HERE.md           ({time.time() - t0:.0f}s)")
    print(f"\nOpen {OUTPUT / 'START_HERE.md'}")


if __name__ == "__main__":
    main()
