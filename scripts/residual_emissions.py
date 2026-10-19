"""Residual emissions in Westeros: scale-up rates and carbon removal as guardrails.

Extends the tutorial baseline (scripts/baseline.py) with
- a hard-to-abate demand: industrial heat from coal boilers (coal_heat),
- an abatement option whose growth is limited: electrified heat (elec_heat,
  heat pumps and e-boilers), with a maximum annual growth rate of activity,
- carbon dioxide removal: biomass power with CO2 capture and storage
  (bio_ppl_ccs, negative emission factor), limited by biomass supply,
- CO2 emissions of coal power (tutorial value) and coal heat,
- net zero CO2 in 720.

A grid of runs crosses the electrification growth limit with the biomass
limit. For each run: feasibility, residual gross CO2 by sector in 720,
removals, the CO2 price and the system cost. The numbers are illustrative
(Westeros is a teaching model); the point is the mechanism.

Usage: python scripts/residual_emissions.py
Output: results/runs.csv, results/table.md, results/fig1_feasibility.png,
        results/timeseries.csv (input to scripts/to_iamc.py)
"""
import sys
from itertools import product
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from message_ix import make_df

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline import HISTORY, HORIZON, add_years, build, io  # noqa: E402
from common import COUNTRY, MODEL, RESULTS, platform  # noqa: E402

LAST = HORIZON[-1]
HEAT_DEMAND = {700: 30.0, 710: 38.0, 720: 45.0}  # GWa of industrial heat
HEAT_HIST = 25.0                                # GWa served by coal boilers in 690
EF = {"coal_ppl": 7.4, "coal_heat": 3.0, "bio_ppl_ccs": -9.0}  # tCO2/kWa
SECTOR = {"coal_ppl": "Electricity", "coal_heat": "Industry"}
GWA_PER_YEAR = "GWa/yr"
# IAMC variables from activity (GWa per year) of each technology
ENERGY_VAR = {
    "coal_ppl": "Secondary Energy|Electricity|Coal|w/o CCS",
    "wind_ppl": "Secondary Energy|Electricity|Wind",
    "bio_ppl_ccs": "Secondary Energy|Electricity|Biomass|w/ CCS",
    "coal_heat": "Useful Energy|Industry|Heat|Coal",
    "elec_heat": "Useful Energy|Industry|Heat|Electricity",
}

GROWTH = [0.06, 0.08, 0.10, 0.12, 0.14, 0.16]   # max annual growth of electrified heat
BIOMASS = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]        # max BECCS electricity, GWa per year


def extend(base):
    """Clone the baseline and add industrial heat, BECCS, emissions and net zero."""
    scen = base.clone(MODEL, "residual_base", "industrial heat, BECCS and net zero", keep_solution=False)
    scen.check_out()
    mp = scen.platform
    scen.add_set("commodity", "industrial_heat")
    scen.add_set("technology", ["coal_heat", "elec_heat", "bio_ppl_ccs"])
    scen.add_par("demand", make_df("demand", node=COUNTRY, commodity="industrial_heat", level="useful",
                                   year=list(HEAT_DEMAND), time="year", unit="GWa",
                                   value=list(HEAT_DEMAND.values())))

    life = {"coal_heat": 20, "elec_heat": 20, "bio_ppl_ccs": 30}
    for tec, val in life.items():
        scen.add_par("technical_lifetime", make_df("technical_lifetime", node_loc=COUNTRY, technology=tec,
                                                   year_vtg=HISTORY + HORIZON, unit="y", value=val))
    io(scen, "coal_heat", out=("industrial_heat", "useful", 1.0))
    io(scen, "elec_heat", out=("industrial_heat", "useful", 1.0), inp=("electricity", "final", 0.6))
    io(scen, "bio_ppl_ccs", out=("electricity", "secondary", 1.0))

    for tec, cf in {"coal_heat": 1.0, "elec_heat": 1.0, "bio_ppl_ccs": 0.85}.items():
        add_years(scen, "capacity_factor", tec, time="year", unit="-", value=cf)
    for tec, val in {"coal_heat": 300, "elec_heat": 800, "bio_ppl_ccs": 3000}.items():
        scen.add_par("inv_cost", make_df("inv_cost", node_loc=COUNTRY, technology=tec,
                                         year_vtg=HORIZON, unit="USD/kW", value=val))
    for tec, val in {"coal_heat": 10, "elec_heat": 15, "bio_ppl_ccs": 60}.items():
        add_years(scen, "fix_cost", tec, unit="USD/kWa", value=val)
    for tec, val in {"coal_heat": 20, "bio_ppl_ccs": 50}.items():
        add_years(scen, "var_cost", tec, mode="standard", time="year", unit="USD/kWa", value=val)

    scen.add_par("historical_activity", make_df("historical_activity", node_loc=COUNTRY, technology="coal_heat",
                                                year_act=HISTORY, mode="standard", time="year", unit="GWa",
                                                value=HEAT_HIST))
    scen.add_par("historical_new_capacity", make_df("historical_new_capacity", node_loc=COUNTRY,
                                                    technology="coal_heat", year_vtg=HISTORY, unit="GW/y",
                                                    value=HEAT_HIST / 10))
    # electrified heat can start from a small level and then grow at most at the set rate
    scen.add_par("initial_activity_up", make_df("initial_activity_up", node_loc=COUNTRY, technology="elec_heat",
                                                year_act=HORIZON, time="year", unit="GWa", value=0.2))

    scen.add_set("emission", "CO2")
    scen.add_cat("emission", "GHG", "CO2")
    mp.add_unit("tCO2/kWa")
    mp.add_unit("MtCO2")
    for tec, val in EF.items():
        add_years(scen, "emission_factor", tec, mode="standard", unit="tCO2/kWa", emission="CO2", value=val)
    scen.add_par("bound_emission", make_df("bound_emission", node=COUNTRY, type_emission="GHG", type_tec="all",
                                           type_year=LAST, value=0.0, unit="MtCO2"))
    scen.commit(comment="industrial heat, electrified heat with growth limit, BECCS, net zero CO2 in 720")
    return scen


def run(base, growth, biomass):
    name = f"g{round(growth * 100):02d}_b{biomass:g}"
    scen = base.clone(MODEL, name, f"growth {growth}, biomass {biomass}", keep_solution=False)
    scen.check_out()
    scen.add_par("growth_activity_up", make_df("growth_activity_up", node_loc=COUNTRY, technology="elec_heat",
                                               year_act=HORIZON, time="year", unit="-", value=growth))
    scen.add_par("bound_activity_up", make_df("bound_activity_up", node_loc=COUNTRY, technology="bio_ppl_ccs",
                                              year_act=HORIZON, mode="standard", time="year", unit="GWa",
                                              value=biomass))
    scen.commit(comment=name)
    row = dict(scenario=name, growth=growth, biomass=biomass)
    try:
        scen.solve(quiet=True)
    except Exception:  # GAMS stops when the LP has no solution under the net-zero bound
        return scen, row | dict(status="infeasible")
    act_all = scen.var("ACT").groupby(["technology", "year_act"]).lvl.sum().unstack(fill_value=0.0)
    act_all = act_all.reindex(columns=HORIZON, fill_value=0.0)
    act = act_all[LAST]
    gross = {SECTOR[t]: act.get(t, 0.0) * EF[t] for t in SECTOR}
    removed = -act.get("bio_ppl_ccs", 0.0) * EF["bio_ppl_ccs"]
    price_all = scen.var("PRICE_EMISSION").groupby("year").lvl.max().reindex(HORIZON, fill_value=0.0)
    price = price_all[[LAST]]
    row |= dict(status="optimal", cost=float(scen.var("OBJ")["lvl"]),
                gross=sum(gross.values()), removed=removed, net=sum(gross.values()) - removed,
                co2_price=float(price.max()) if len(price) else 0.0,
                elec_heat=act.get("elec_heat", 0.0), coal_heat=act.get("coal_heat", 0.0),
                **{f"gross_{k.lower()}": v for k, v in gross.items()})
    row["timeseries"] = timeseries(name, act_all, price_all)
    return scen, row


def timeseries(name, act, price):
    """Long table (variable, unit, year, value) for the IAMC export."""
    out = []

    def add(var, unit, series):
        out.extend(dict(scenario=name, variable=var, unit=unit, year=y, value=float(series.get(y, 0.0)))
                   for y in HORIZON)

    get = lambda t: act.loc[t] if t in act.index else pd.Series(0.0, index=HORIZON)  # noqa: E731
    for tec, var in ENERGY_VAR.items():
        add(var, GWA_PER_YEAR, get(tec))
    for tec, sector in {"coal_ppl": "Energy|Supply|Electricity", "coal_heat": "Energy|Demand|Industry"}.items():
        add(f"Emissions|CO2|{sector}", "Mt CO2/yr", get(tec) * EF[tec])
    add("Carbon Sequestration|CCS|Biomass", "Mt CO2/yr", -get("bio_ppl_ccs") * EF["bio_ppl_ccs"])
    add("Price|Carbon", "USD/t CO2", price)
    return out


def write(df):
    RESULTS.mkdir(exist_ok=True)
    df.to_csv(RESULTS / "runs.csv", index=False)
    lines = [f"# Residual CO2 in {LAST}: electrification growth limit x biomass limit (illustrative)", "",
             "| Growth limit of electrified heat (per year) | BECCS limit (GWa) | Status | Gross CO2 (Mt) | "
             "of which industry | of which electricity | Removed by BECCS (Mt) | CO2 price | System cost |",
             "|---|---|---|---|---|---|---|---|---|"]
    for _, r in df.iterrows():
        def f(x, nd=1):
            return "" if pd.isna(x) else f"{x:,.{nd}f}"
        lines.append(f"| {r.growth:.0%} | {r.biomass:g} | {r.status} | {f(r.get('gross'))} | "
                     f"{f(r.get('gross_industry'))} | {f(r.get('gross_electricity'))} | {f(r.get('removed'))} | "
                     f"{f(r.get('co2_price'), 0)} | {f(r.get('cost'), 0)} |")
    (RESULTS / "table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def plot(df):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10.5, 4.2))
    piv = df.assign(feasible=(df.status == "optimal").astype(int)).pivot(
        index="growth", columns="biomass", values="feasible")
    a1.imshow(piv.values, cmap="Greens", vmin=-0.3, vmax=1.3, origin="lower", aspect="auto")
    a1.set_xticks(range(len(piv.columns)), [f"{b:g}" for b in piv.columns])
    a1.set_yticks(range(len(piv.index)), [f"{g:.0%}" for g in piv.index])
    for i, g in enumerate(piv.index):
        for j, b in enumerate(piv.columns):
            r = df[(df.growth == g) & (df.biomass == b)].iloc[0]
            txt = "no solution" if r.status != "optimal" else f"{r.gross:.0f} Mt\n{r.co2_price:,.0f} $/t"
            a1.text(j, i, txt, ha="center", va="center", fontsize=8)
    a1.set_xlabel("BECCS limit (GWa per year)")
    a1.set_ylabel("max growth of electrified heat (per year)")
    a1.set_title(f"Net zero in {LAST}: residual gross CO2 and CO2 price", loc="left", fontsize=10)
    a1.grid(False)

    need = (df[df.status == "optimal"].groupby("growth").biomass.min() * -EF["bio_ppl_ccs"]).reindex(piv.index)
    a2.bar([f"{g:.0%}" for g in need.index], need.fillna(0).values, color="#2a78d6", width=0.6)
    for k, (g, v) in enumerate(need.items()):
        a2.text(k, (0 if pd.isna(v) else v) + 1.5, "none feasible" if pd.isna(v) else f"{v:.0f}",
                ha="center", fontsize=8)
    a2.set_xlabel("max growth of electrified heat (per year)")
    a2.set_ylabel(f"smallest BECCS removal in the grid (Mt CO2 in {LAST})")
    a2.set_title("CO2 removal needed for net zero", loc="left", fontsize=10)
    fig.tight_layout()
    fig.savefig(RESULTS / "fig1_feasibility.png", dpi=150)


def main():
    RESULTS.mkdir(exist_ok=True)
    mp = platform()
    base = build(mp)
    ext = extend(base)
    rows = []
    for growth, biomass in product(GROWTH, BIOMASS):
        print(f"growth {growth:.0%}, biomass {biomass:g} ...", flush=True)
        _, row = run(ext, growth, biomass)
        rows.append(row)
    pd.DataFrame([r for row in rows for r in row.pop("timeseries", [])]).to_csv(
        RESULTS / "timeseries.csv", index=False)
    df = pd.DataFrame(rows)
    write(df)
    plot(df)
    mp.close_db()


if __name__ == "__main__":
    main()
