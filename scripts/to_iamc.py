"""Export the Westeros runs to the IAMC format and check them against a small protocol.

Reads results/timeseries.csv (written by residual_emissions.py), adds totals,
converts energy from GWa/yr to EJ/yr and writes one pyam IamDataFrame.

Protocol checks (each against an independent source, not against the totals
built here):
  1. completeness: every required variable for every feasible scenario
  2. heat demand: useful industrial heat equals the demand given to the model
  3. electricity balance: generation after grid losses covers lighting and
     electrified heat
  4. gross CO2: the sectoral sum equals the run summary in runs.csv
  5. net zero: net CO2 at most zero in the last model year
  6. removal limit: BECCS storage within the biomass limit of each run

Usage: python scripts/to_iamc.py
Output: results/iamc/westeros_residual_iamc.xlsx, .csv, checks.md and
        results/fig2_sectors_and_removal.png (plotted with pyam)
"""
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import pyam

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline import DEMAND_PER_YEAR, GDP, GRID_EFF  # noqa: E402
from common import COUNTRY, MODEL, RESULTS  # noqa: E402
from residual_emissions import HEAT_DEMAND  # noqa: E402

OUT = RESULTS / "iamc"
LAST = 720
TOL = 1e-6
EF_BECCS = 9.0  # tCO2 removed per kWa of BECCS electricity (residual_emissions.py)
ELEC_PER_HEAT = 0.6  # electricity input per unit of electrified heat (residual_emissions.py)
GWA_TO_EJ = 1e9 * 365.25 * 24 * 3600 / 1e18  # 1 GWa in EJ, Julian year as in pyam
TOTALS = {
    "Secondary Energy|Electricity": None,
    "Useful Energy|Industry|Heat": None,
    "Emissions|CO2|Energy and Industrial Processes":
        ["Emissions|CO2|Energy|Supply|Electricity", "Emissions|CO2|Energy|Demand|Industry"],
}
REQUIRED = ["Emissions|CO2", "Emissions|CO2|Energy and Industrial Processes",
            "Carbon Sequestration|CCS|Biomass", "Secondary Energy|Electricity", "Price|Carbon"]


def build():
    data = pd.read_csv(RESULTS / "timeseries.csv").assign(model=MODEL, region=COUNTRY)
    df = pyam.IamDataFrame(data)
    for total, parts in TOTALS.items():
        parts = parts or [v for v in df.variable if v.startswith(total + "|")]
        df.aggregate(total, components=parts, append=True)
    net = df.subtract("Emissions|CO2|Energy and Industrial Processes", "Carbon Sequestration|CCS|Biomass",
                      "Emissions|CO2", ignore_units="Mt CO2/yr")
    df = df.append(net)
    return df.convert_unit("GWa/yr", to="EJ/yr")


def check(df, runs):
    results = []
    feasible = runs.loc[runs.status == "optimal", "scenario"].tolist()
    missing = [(s, v) for s in feasible for v in REQUIRED if v not in df.filter(scenario=s).variable]
    results.append(("completeness", not missing and set(df.scenario) == set(feasible),
                    f"{len(REQUIRED)} required variables for {len(feasible)} feasible scenarios" if not missing
                    else str(missing)))
    def ts(var):
        t = df.filter(variable=var).timeseries()
        t.index = t.index.get_level_values("scenario")
        return t

    heat = ts("Useful Energy|Industry|Heat") / GWA_TO_EJ
    dev = (heat - pd.Series(HEAT_DEMAND)).abs().max().max()
    results.append(("heat demand", dev <= 1e-6, f"largest deviation from the demand input: {dev:.2g} GWa"))

    light = (DEMAND_PER_YEAR * GDP).round()
    need = light + ELEC_PER_HEAT * ts("Useful Energy|Industry|Heat|Electricity") / GWA_TO_EJ
    gap = (need - GRID_EFF * ts("Secondary Energy|Electricity") / GWA_TO_EJ).max().max()
    results.append(("electricity balance", gap <= 1e-6,
                    f"largest shortfall of final electricity: {gap:.2g} GWa (negative = surplus)"))

    gross = ts("Emissions|CO2|Energy and Industrial Processes")[LAST]
    ref = runs.set_index("scenario").gross.reindex(gross.index)
    diff = (gross - ref).abs().max()
    results.append(("gross CO2", diff <= 1e-6, f"largest difference to runs.csv in {LAST}: {diff:.2g} Mt CO2/yr"))

    net = df.filter(variable="Emissions|CO2", year=LAST).timeseries()
    worst = net.max().max()
    results.append(("net zero", len(net) == len(feasible) and worst <= TOL,
                    f"largest net CO2 in {LAST}: {worst:.3g} Mt CO2/yr ({len(net)} scenarios)"))
    stored = df.filter(variable="Carbon Sequestration|CCS|Biomass").timeseries().max(axis=1)
    stored.index = stored.index.get_level_values("scenario")
    limit = runs.set_index("scenario").biomass * EF_BECCS
    over = (stored - limit.reindex(stored.index)).max()
    results.append(("removal limit", over <= TOL, f"largest storage above the biomass limit: {over:.3g} Mt CO2/yr"))
    return results


def plot(df):
    """Gross CO2 by sector and BECCS storage over time for three feasible runs, from the IAMC table."""
    runs = ["g12_b0", "g12_b6", "g08_b8"]
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharey=True)
    sectors = ["Emissions|CO2|Energy|Supply|Electricity", "Emissions|CO2|Energy|Demand|Industry"]
    for ax, scn in zip(axes, runs):
        sub = df.filter(scenario=scn, variable=sectors).rename(variable={v: v.rsplit("|", 1)[-1] for v in sectors})
        sub.plot.stack(ax=ax, stack="variable", total=False, legend=ax is axes[0], title=None)
        stored = df.filter(scenario=scn, variable="Carbon Sequestration|CCS|Biomass").timeseries().iloc[0]
        ax.plot(stored.index, stored.values, color="black", ls="--", lw=1.5, label="BECCS stored")
        g, b = scn[1:3], scn.split("_b")[1]
        ax.set_title(f"growth limit {int(g)}%/yr, BECCS limit {b} GWa", loc="left", fontsize=9)
        ax.set_xlabel("")
        ax.set_ylabel("Mt CO2/yr")
    axes[0].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(RESULTS / "fig2_sectors_and_removal.png", dpi=150)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    runs = pd.read_csv(RESULTS / "runs.csv")
    df = build()
    df.to_excel(OUT / "westeros_residual_iamc.xlsx")
    df.to_csv(OUT / "westeros_residual_iamc.csv")
    plot(df)
    lines = ["# Protocol checks on the IAMC export", "",
             f"{len(df.scenario)} feasible scenarios, {len(df.variable)} variables, years "
             f"{min(df.year)} to {max(df.year)}.", "", "| Check | Result | Detail |", "|---|---|---|"]
    ok = True
    for name, passed, detail in check(df, runs):
        ok &= passed
        lines.append(f"| {name} | {'pass' if passed else 'FAIL'} | {detail} |")
    (OUT / "checks.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
