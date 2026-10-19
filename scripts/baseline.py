"""Westeros baseline: the MESSAGEix tutorial model (light demand, coal and wind power, grid).

Data and structure follow the official tutorial `westeros_baseline.ipynb`
(message_ix 3.11, Apache License 2.0), written as a script.

Usage: python scripts/baseline.py
"""
import sys
from pathlib import Path

import message_ix
import pandas as pd
from message_ix import make_df

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import COUNTRY, MODEL, platform  # noqa: E402

HISTORY = [690]
HORIZON = [700, 710, 720]
GDP = pd.Series([1.0, 1.5, 1.9], index=HORIZON)
DEMAND_PER_YEAR = 40 * 12 * 1000 / 8760
GRID_EFF = 0.9


def add_years(scen, par, tec, **kw):
    """Add a parameter over all vintage and activity years of a technology."""
    yrs = scen.vintage_and_active_years((COUNTRY, tec), in_horizon=False)
    scen.add_par(par, make_df(par, node_loc=COUNTRY, technology=tec,
                              year_vtg=yrs["year_vtg"], year_act=yrs["year_act"], **kw))


def io(scen, tec, out=None, inp=None):
    """Output and input of one commodity each, as (commodity, level, value)."""
    yrs = scen.vintage_and_active_years((COUNTRY, tec), in_horizon=False)
    base = dict(node_loc=COUNTRY, technology=tec, year_vtg=yrs["year_vtg"], year_act=yrs["year_act"],
                mode="standard", time="year", unit="-")
    if out:
        c, lvl, v = out
        scen.add_par("output", make_df("output", **base, node_dest=COUNTRY, time_dest="year",
                                       commodity=c, level=lvl, value=v))
    if inp:
        c, lvl, v = inp
        scen.add_par("input", make_df("input", **base, node_origin=COUNTRY, time_origin="year",
                                      commodity=c, level=lvl, value=v))


def build(mp):
    scen = message_ix.Scenario(mp, model=MODEL, scenario="baseline", version="new")
    scen.add_horizon(year=HISTORY + HORIZON, firstmodelyear=HORIZON[0])
    scen.add_spatial_sets({"country": COUNTRY})
    scen.add_set("commodity", ["electricity", "light"])
    scen.add_set("level", ["secondary", "final", "useful"])
    scen.add_set("technology", ["coal_ppl", "wind_ppl", "grid", "bulb"])
    scen.add_set("mode", "standard")

    scen.add_par("demand", make_df("demand", node=COUNTRY, commodity="light", level="useful",
                                   year=HORIZON, time="year", unit="GWa",
                                   value=(DEMAND_PER_YEAR * GDP).round().values))
    for tec, val in {"coal_ppl": 20, "wind_ppl": 20, "bulb": 1, "grid": 30}.items():
        scen.add_par("technical_lifetime", make_df("technical_lifetime", node_loc=COUNTRY, technology=tec,
                                                   year_vtg=HISTORY + HORIZON, unit="y", value=val))

    io(scen, "bulb", out=("light", "useful", 1.0), inp=("electricity", "final", 1.0))
    io(scen, "grid", out=("electricity", "final", 1.0), inp=("electricity", "secondary", 1 / GRID_EFF))
    io(scen, "coal_ppl", out=("electricity", "secondary", 1.0))
    io(scen, "wind_ppl", out=("electricity", "secondary", 1.0))

    cf = {"coal_ppl": 1, "wind_ppl": 0.36, "bulb": 1, "grid": 1}
    for tec, val in cf.items():
        add_years(scen, "capacity_factor", tec, time="year", unit="-", value=val)
    for tec in ["coal_ppl", "wind_ppl"]:
        scen.add_par("growth_activity_up", make_df("growth_activity_up", node_loc=COUNTRY, technology=tec,
                                                   year_act=HORIZON, time="year", unit="-", value=0.1))

    hist_gen = 0.5 * DEMAND_PER_YEAR / GRID_EFF
    old = {"coal_ppl": 0.6 * hist_gen, "wind_ppl": 0.4 * hist_gen, "grid": hist_gen}
    mp.add_unit("GW/y")
    for tec, val in old.items():
        scen.add_par("historical_activity", make_df("historical_activity", node_loc=COUNTRY, technology=tec,
                                                    year_act=HISTORY, mode="standard", time="year",
                                                    unit="GWa", value=val))
        scen.add_par("historical_new_capacity", make_df("historical_new_capacity", node_loc=COUNTRY,
                                                        technology=tec, year_vtg=HISTORY, unit="GW/y",
                                                        value=val / (10 * cf[tec])))

    scen.add_par("interestrate", HORIZON, value=0.05, unit="-")
    mp.add_unit("USD/kW")
    for tec, val in {"coal_ppl": 500, "wind_ppl": 1500, "bulb": 5, "grid": 800}.items():
        scen.add_par("inv_cost", make_df("inv_cost", node_loc=COUNTRY, technology=tec,
                                         year_vtg=HORIZON, unit="USD/kW", value=val))
    for tec, val in {"coal_ppl": 30, "wind_ppl": 10, "grid": 16}.items():
        add_years(scen, "fix_cost", tec, unit="USD/kWa", value=val)
    add_years(scen, "var_cost", "coal_ppl", mode="standard", time="year", unit="USD/kWa", value=30)

    scen.commit(comment="Westeros baseline (MESSAGEix tutorial)")
    scen.set_as_default()
    return scen


def main():
    mp = platform()
    scen = build(mp)
    scen.solve(quiet=True)
    print(f"baseline solved, objective {scen.var('OBJ')['lvl']:.1f}")
    print(scen.var("ACT").groupby(["technology", "year_act"]).lvl.sum().unstack().round(1))
    mp.close_db()


if __name__ == "__main__":
    main()
