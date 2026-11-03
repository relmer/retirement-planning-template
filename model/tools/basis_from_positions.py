"""basis_from_positions.py: compute taxable_basis_fraction from a brokerage positions CSV.

    python model/tools/basis_from_positions.py "path/to/Portfolio_Positions.csv"

Looks for a market-value column and a cost-basis column by common header text
(most brokerage exports work with minor variations). Prints
total value, total basis, and basis / value. Copy that ratio into the
taxable_basis_fraction row of the Params sheet. Run it on TAXABLE accounts only.
"""
import csv
import re
import sys

VALUE_KEYS = ("current value", "market value", "value")
BASIS_KEYS = ("cost basis total", "cost basis", "total cost basis", "cost")


def _num(s):
    s = re.sub(r"[^0-9.\-]", "", str(s or ""))
    try:
        return float(s)
    except ValueError:
        return None


def _find(header, keys):
    low = [h.strip().lower() for h in header]
    for k in keys:
        for i, h in enumerate(low):
            if h == k:
                return i
    for k in keys:
        for i, h in enumerate(low):
            if k in h:
                return i
    raise SystemExit(f"No column matching {keys} in header: {header}")


def main(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    hdr_i = next(i for i, r in enumerate(rows) if any("value" in c.lower() for c in r))
    header = rows[hdr_i]
    vi, bi = _find(header, VALUE_KEYS), _find(header, BASIS_KEYS)
    value = basis = 0.0
    for r in rows[hdr_i + 1:]:
        if len(r) <= max(vi, bi):
            continue
        v, b = _num(r[vi]), _num(r[bi])
        if v is None or b is None:
            continue   # cash / pending / footer rows lack a basis
        value += v
        basis += b
    if value <= 0:
        raise SystemExit("No positions with both a value and a cost basis were found.")
    print(f"Columns: value='{header[vi]}', basis='{header[bi]}'")
    print(f"Total value : {value:,.0f}")
    print(f"Total basis : {basis:,.0f}")
    print(f"taxable_basis_fraction = {basis/value:.3f}  (unrealized gain {1-basis/value:.0%})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
