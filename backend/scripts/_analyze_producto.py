"""Analyze Producto column values across all Unicaja CSV files."""
import zipfile, tempfile, os, sys
import pandas as pd

zip_path = "/Users/macbookpro/Desktop/ALMReady/data/balances/balance_retimed_2026-02-22_div4.zip"
tmp = tempfile.mkdtemp()

with zipfile.ZipFile(zip_path) as zf:
    zf.extractall(tmp)

# Walk entire tree for CSVs
csvs = []
for root, dirs, files in os.walk(tmp):
    for f in files:
        if f.endswith(".csv"):
            csvs.append(os.path.join(root, f))
csvs.sort(key=lambda p: os.path.basename(p))

print("Found %d CSVs\n" % len(csvs))

# Part 1: Column headers per file
for c in csvs:
    name = os.path.basename(c)
    header_row = 0
    with open(c, "r", encoding="cp1252") as fh:
        for i, line in enumerate(fh):
            if "Identifier" in line:
                header_row = i
                break
    df = pd.read_csv(c, sep=";", encoding="cp1252", decimal=",", skiprows=header_row, nrows=0)
    print("=== %s (%d cols) ===" % (name, len(df.columns)))
    for col in df.columns:
        print("  %s" % col)
    print()

print("\n" + "=" * 80)
print("PRODUCTO ANALYSIS")
print("=" * 80 + "\n")

# Part 2: Producto breakdown per file
all_products = []
for c in csvs:
    name = os.path.basename(c)
    header_row = 0
    with open(c, "r", encoding="cp1252") as fh:
        for i, line in enumerate(fh):
            if "Identifier" in line:
                header_row = i
                break

    df = pd.read_csv(
        c, sep=";", encoding="cp1252", decimal=",", skiprows=header_row,
        usecols=lambda col: col in ("Producto", "Apartado", "Outstanding principal"),
        dtype={"Producto": str, "Apartado": str},
    )

    total_rows = len(df)
    print("=== %s (%d rows) ===" % (name, total_rows))

    if "Producto" not in df.columns:
        print("  [No Producto column]\n")
        continue

    grp_cols = []
    if "Apartado" in df.columns:
        grp_cols.append("Apartado")
    grp_cols.append("Producto")

    agg_dict = {"count": ("Producto", "size")}
    if "Outstanding principal" in df.columns:
        agg_dict["total_notional"] = ("Outstanding principal", "sum")

    grouped = df.groupby(grp_cols, dropna=False).agg(**agg_dict).reset_index()
    grouped = grouped.sort_values("count", ascending=False)

    for _, row in grouped.iterrows():
        apartado = row.get("Apartado", "?")
        producto = str(row["Producto"])
        count = int(row["count"])
        notional = float(row.get("total_notional", 0))
        pct = count / total_rows * 100
        all_products.append({
            "file": name, "apartado": apartado, "producto": producto,
            "count": count, "notional": notional,
        })
        print("  [%s] %-55s %8d rows (%5.1f%%)  notional: %15.0f" % (
            apartado, producto[:55], count, pct, notional
        ))
    print()

# Part 3: Summary across all files
print("\n" + "=" * 80)
print("CROSS-FILE SUMMARY (all unique Producto values)")
print("=" * 80 + "\n")

pdf = pd.DataFrame(all_products)
summary = pdf.groupby(["apartado", "producto"]).agg(
    total_rows=("count", "sum"),
    total_notional=("notional", "sum"),
    files=("file", lambda x: ", ".join(sorted(set(x)))),
).reset_index().sort_values(["apartado", "total_rows"], ascending=[True, False])

for _, row in summary.iterrows():
    print("[%s] %-55s %8d rows  notional: %15.0f  files: %s" % (
        row["apartado"], str(row["producto"])[:55], row["total_rows"],
        row["total_notional"], row["files"]
    ))
