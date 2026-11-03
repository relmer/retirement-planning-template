"""Build annual real total-return series for US large-cap from Shiller monthly data.
Real total return reinvests dividends and is CPI-adjusted. Saves annual_real_returns.csv."""
import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
rows = []
with open(HERE / "data" / "shiller_sp500.csv", newline="") as f:
    for r in csv.DictReader(f):
        try:
            rp = float(r["Real Price"]); rd = float(r["Real Dividend"])
            date = r["Date"]
        except (ValueError, KeyError):
            continue
        if rp <= 0:
            continue
        year = int(date[:4]); month = int(date[5:7])
        rows.append((year, month, rp, rd))

rows.sort()
# monthly real total return = (RP_t + RD_t/12) / RP_{t-1} - 1
monthly = []
for i in range(1, len(rows)):
    y, m, rp, rd = rows[i]
    rp0 = rows[i - 1][2]
    r = (rp + rd / 12.0) / rp0 - 1.0
    monthly.append((y, m, r))

# aggregate to calendar-year real total return
from collections import defaultdict
by_year = defaultdict(lambda: [0, 1.0])   # count, growth
for y, m, r in monthly:
    by_year[y][0] += 1
    by_year[y][1] *= (1 + r)

annual = []
for y in sorted(by_year):
    cnt, growth = by_year[y]
    if cnt == 12:                      # full years only
        annual.append((y, growth - 1.0))

import statistics as st
vals = [r for _, r in annual]
out = HERE / "data" / "annual_real_returns.csv"
with open(out, "w", newline="") as f:
    w = csv.writer(f); w.writerow(["year", "real_total_return"])
    for y, r in annual:
        w.writerow([y, round(r, 6)])

print(f"Years: {annual[0][0]}-{annual[-1][0]}  ({len(annual)} obs)")
print(f"Mean real:   {st.mean(vals)*100:6.2f}%")
print(f"Median real: {st.median(vals)*100:6.2f}%")
print(f"Stdev:       {st.pstdev(vals)*100:6.2f}%")
print(f"Min/Max:     {min(vals)*100:.1f}% / {max(vals)*100:.1f}%")
print(f"Geo mean:    {(st.geometric_mean([1+v for v in vals])-1)*100:6.2f}%")
print("Saved", out.name)
