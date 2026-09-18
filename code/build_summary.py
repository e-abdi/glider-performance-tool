"""
File: code/build_summary.py

What it does: Builds the Glider Performance Tool summary spreadsheet from the
    converted per-glider NetCDF files and the rodeo glider specification sheet.
    One sheet per topic, so new analyses can be added as extra sheets:
      - Gliders:   platform, owner, PAM system, hydrophone, battery, deployment length
      - Power use: how each glider measures energy, and per-dive/per-hour use
      - Notes:     column definitions and data caveats

How to run (from the repository root):
    python code/build_summary.py
    python code/build_summary.py --nc-dir ~/og1 --specs ~/shared-public/GliderRodeo/PAM_Glider_Specs.csv

Inputs:
    --nc-dir  folder of per-glider NetCDF files (default ../hackathon-shared-repo/data/og1)
    --specs   PAM_Glider_Specs.csv from the rodeo shared data
Outputs:
    --out     spreadsheet, default output/glider_performance_summary.xlsx
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from openpyxl.styles import Font

# Rodeo mission modes (UTC), from the Glider Rodeo fieldwork plan.
MODES = [
    ("shakedown", "2026-01-28 22:00", "2026-01-30 06:00"),
    ("fast", "2026-01-30 06:00", "2026-02-01 18:00"),
    ("slow", "2026-02-01 18:00", "2026-02-04 18:00"),
    ("intermediate", "2026-02-04 18:00", "2026-02-06 18:00"),
    ("drift", "2026-02-06 18:00", "2026-02-08 18:00"),
    ("mini-slow", "2026-02-08 18:00", "2026-02-09 06:00"),
    ("mini-intermediate", "2026-02-09 06:00", "2026-02-09 18:00"),
    ("mini-fast", "2026-02-09 18:00", "2026-02-10 06:00"),
]


def mode_of(times):
    """Label each timestamp with its rodeo mission mode (NaN outside the plan)."""
    t = pd.to_datetime(pd.Series(times)).to_numpy()
    out = pd.Series(pd.NA, index=range(len(t)), dtype="object")
    for name, start, end in MODES:
        inside = (t >= np.datetime64(start)) & (t < np.datetime64(end))
        out[inside] = name
    return out

DEFAULT_NC_DIR = Path.home() / "hackathon-shared-repo" / "data" / "og1"
DEFAULT_SPECS = Path.home() / "hackathon-shared-repo" / "data" / "PAM_Glider_Specs.csv"
DEFAULT_OUT = Path("output") / "glider_performance_summary.xlsx"

NOTES = [
    ("Source", "Per-glider NetCDF files converted from the Glider Rodeo CSV exports; "
               "glider specifications from PAM_Glider_Specs.csv."),
    ("W h/dive", "Amp-hours x pack voltage. Seagliders: nominal 24 V and 10 V packs. "
                 "Slocums: each glider's own median measured voltage."),
    ("Watts", "Mean power draw over a dive: watt-hours used divided by dive duration in hours."),
    ("Period measured", "Span of the energy record against the span of the whole deployment. "
                        "risso and capex987 engineering data stop on 10 Feb while their CTDs keep recording."),
    ("Dives", "Seagliders: dives in the GPS file. belladonna: dives in dives_with_status.csv. "
              "Slocums: intervals between surfacings, keeping those deeper than 100 m and longer than 30 min."),
    ("SEA117", "Reports battery voltage only, with no charge counter, so energy use cannot be derived."),
    ("belladonna", "No flight/engineering export (no pitch, roll or buoyancy), but since 16 Sep it has a "
                   "power log: current, voltage, power and cumulative energy every 25 s, plus per-dive "
                   "battery percentage and free disk space."),
    ("capex987", "Energy use is about 2.4x its sister Slocums; its JASCO OceanObserver records "
                 "5 channels from 4 hydrophones (one at 512 kHz) against a single channel on the others."),
    ("Preliminary", "All rodeo data are marked PRELIMINARY and need further QA/QC."),
    ("Mission modes", "Rodeo fieldwork plan (UTC). A dive belongs to the mode its start time falls in; "
                      "rows are labelled by their own timestamp."),
    ("belladonna vert speed", "Not trustworthy: its CTD timestamps arrive in bursts (samples under 1 ms apart), "
                              "so rates computed between samples are far too high."),
    ("km per hour", "Straight-line distance over ground between the start and end of a dive, divided by "
                    "dive duration. It is not speed through water and ignores what the glider did in between."),
    ("cc pumped per dive", "Same measure summed over one dive, then the median across the dives of that mode. "
                           "Counts travel in both directions: a dive that pumps 400 cc down and 400 cc back "
                           "up counts as 800 cc."),
    ("cc pumped per hour", "Total volume the buoyancy pump moved per hour, summing |change| between samples "
                           "(Seaglider VBD, Slocum oil volume, SeaExplorer ballast). Changes under 1 cc are "
                           "treated as sensor noise. A proxy for pump work; the gliders do not report pump energy."),
]


def load_specs(path):
    specs = pd.read_csv(path)
    specs["key"] = specs["Glider Name"].astype(str).str.lower().str.strip()
    by_id = specs.assign(key=specs["Glider ID"].astype(str).str.lower().str.strip())
    return pd.concat([specs, by_id]).drop_duplicates("key").set_index("key")


def hydrophones(ds):
    out = []
    for v in ds.variables:
        if str(v).startswith("SENSOR_HYDROPHONE"):
            a = ds[v].attrs
            serial = a.get("sensor_serial_number", "")
            out.append(f"{a.get('sensor_model', '')}{f' ({serial})' if serial and serial != 'unknown' else ''}")
    return "; ".join(sorted(set(out)))


def seaglider_energy(name, nc_dir):
    """Per-dive energy from the Seaglider GPS file (fuel gauge, one reading per dive)."""
    gps = next((nc_dir.parent / f"{name}_20260128").glob("*_GPS_timeseries.csv"), None)
    if gps is None or "FG_AHR_24V" not in pd.read_csv(gps, nrows=0).columns:
        return None
    d = pd.read_csv(gps)
    a24, a10 = d.FG_AHR_24V.diff(), d.FG_AHR_10V.diff()
    ok = (a24 >= 0) & (a10 >= 0)
    hours = (d.endTime - d.startTime)[ok] / 3600
    wh = (a24 * 24 + a10 * 10)[ok]
    return {
        "energy source": "fuel gauge, 24 V + 10 V packs", "sampling": "once per dive",
        "measured days": round((d.startTime.max() - d.startTime.min()) / 86400, 1),
        "dives": int(ok.sum()), "median dive h": round(hours.median(), 2),
        "A h/dive": round(float(a24[ok].median() + a10[ok].median()), 2),
        "A h/dive detail": f"{a24[ok].median():.2f} (24 V) + {a10[ok].median():.2f} (10 V)",
        "W h/dive": round(float(wh.median()), 1), "Watts": round(float((wh / hours).median()), 2),
        "W h per km": round(float((wh / d.distance_km[ok]).median()), 1),
    }


def slocum_energy(ds):
    """Per-dive energy from a continuous coulomb counter, one dive = one interval between surfacings."""
    if "BATTERY_CHARGE_USED_TOTAL" not in ds:
        return None
    df = ds[["BATTERY_CHARGE_USED_TOTAL", "SEGMENT_NUMBER", "DEPTH"]].to_dataframe().reset_index()
    df = df.dropna(subset=["BATTERY_CHARGE_USED_TOTAL"])
    volt = float(np.nanmedian(ds.BATTERY_VOLTAGE.values))
    g = df.groupby("SEGMENT_NUMBER")
    per = pd.DataFrame({"ah": g.BATTERY_CHARGE_USED_TOTAL.max().diff(),
                        "hours": (g.TIME.max() - g.TIME.min()).dt.total_seconds() / 3600,
                        "depth": g.DEPTH.max()}).dropna()
    per = per[(per.ah >= 0) & (per.ah < 5) & (per.hours > 0.5) & (per.depth > 100)]
    interval = df.TIME.diff().dt.total_seconds().median()
    return {
        "energy source": f"coulomb counter at {volt:.1f} V", "sampling": f"every {interval:.0f} s",
        "measured days": round((df.TIME.max() - df.TIME.min()).total_seconds() / 86400, 1),
        "dives": len(per), "median dive h": round(float(per.hours.median()), 2),
        "A h/dive": round(float(per.ah.median()), 2), "A h/dive detail": "",
        "W h/dive": round(float((per.ah * volt).median()), 1),
        "Watts": round(float(((per.ah * volt) / per.hours).median()), 2), "W h per km": "",
    }


def oceanscout_energy(name, ds, nc_dir):
    """Per-dive energy for a glider that logs power directly (current, voltage, energy)."""
    if "BATTERY_ENERGY_USED" not in ds:
        return None
    dives = dives_table(name, ds, nc_dir)
    d = dives[(dives.hours > 0) & dives["W h"].notna() & (dives["W h"] > 0)]
    e = ds[["BATTERY_ENERGY_USED"]].to_dataframe().reset_index().dropna(subset=["BATTERY_ENERGY_USED"])
    interval = e.TIME.diff().dt.total_seconds().median()
    ah = ""
    if "BATTERY_CHARGE_USED_TOTAL" in ds:
        c = ds[["BATTERY_CHARGE_USED_TOTAL"]].to_dataframe().reset_index().dropna(subset=["BATTERY_CHARGE_USED_TOTAL"])
        c = c.set_index("TIME").BATTERY_CHARGE_USED_TOTAL.sort_index()
        ends = d.start + pd.to_timedelta(d.hours, unit="h")
        per = [c.loc[s:t].diff().pipe(lambda r: r[r > 0].sum()) for s, t in zip(d.start, ends)]
        ah = round(float(np.nanmedian([v for v in per if v > 0])), 2)
    return {
        "energy source": "power log (current, voltage, energy)", "sampling": f"every {interval:.0f} s",
        "measured days": round((e.TIME.max() - e.TIME.min()).total_seconds() / 86400, 1),
        "dives": len(d), "median dive h": round(float(d.hours.median()), 2),
        "A h/dive": ah if ah is not None else "", "A h/dive detail": "",
        "W h/dive": round(float(d["W h"].median()), 1),
        "Watts": round(float((d["W h"] / d.hours).median()), 2),
        "W h per km": round(float((d["W h"] / d.km.replace(0, np.nan)).median()), 1),
    }


def _haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def _energy_per_window(ds, starts, ends):
    """Energy used in each time window, from a cumulative counter that restarts per log file."""
    e = ds[["BATTERY_ENERGY_USED"]].to_dataframe().reset_index().dropna(subset=["BATTERY_ENERGY_USED"])
    e = e.set_index("TIME").BATTERY_ENERGY_USED.sort_index()
    out = []
    for s, t in zip(starts, ends):
        v = e.loc[s:t]
        rise = v.diff()
        out.append(float(rise[rise > 0].sum()) if len(v) > 1 else np.nan)
    return out


def dives_table(name, ds, nc_dir):
    """One row per dive: start, duration, max depth, energy and distance over ground."""
    status = next((nc_dir.parent / f"{name}_20260128").glob("*_dives_with_status.csv"), None)
    if status is not None and "BATTERY_ENERGY_USED" in ds:
        d = pd.read_csv(status)
        starts, ends = pd.to_datetime(d.start_time).dt.tz_localize(None), pd.to_datetime(d.end_time).dt.tz_localize(None)
        return pd.DataFrame({
            "start": starts, "hours": (ends - starts).dt.total_seconds() / 3600,
            "max depth m": d.max_depth_m, "W h": _energy_per_window(ds, starts, ends),
            "km": d.distance_m / 1000.0,
        }).dropna(subset=["hours"])

    gps = next((nc_dir.parent / f"{name}_20260128").glob("*_GPS_timeseries.csv"), None)
    if gps is not None and "FG_AHR_24V" in pd.read_csv(gps, nrows=0).columns:
        d = pd.read_csv(gps)
        return pd.DataFrame({
            "start": pd.to_datetime(d.startTime, unit="s"),
            "hours": (d.endTime - d.startTime) / 3600,
            "max depth m": d.maxDepth_m,
            "W h": d.FG_AHR_24V.diff() * 24 + d.FG_AHR_10V.diff() * 10,
            "km": d.distance_km,
        }).dropna(subset=["hours"])

    if "BATTERY_CHARGE_USED_TOTAL" not in ds:
        return None
    df = ds[["BATTERY_CHARGE_USED_TOTAL", "SEGMENT_NUMBER", "DEPTH", "LATITUDE", "LONGITUDE"]].to_dataframe().reset_index()
    df = df.dropna(subset=["BATTERY_CHARGE_USED_TOTAL"])
    volt = float(np.nanmedian(ds.BATTERY_VOLTAGE.values))
    g = df.groupby("SEGMENT_NUMBER")
    per = pd.DataFrame({
        "start": g.TIME.min(),
        "hours": (g.TIME.max() - g.TIME.min()).dt.total_seconds() / 3600,
        "max depth m": g.DEPTH.max(),
        "W h": g.BATTERY_CHARGE_USED_TOTAL.max().diff() * volt,
        "lat0": g.LATITUDE.first(), "lon0": g.LONGITUDE.first(),
        "lat1": g.LATITUDE.last(), "lon1": g.LONGITUDE.last(),
    })
    per["km"] = _haversine_km(per.lat0, per.lon0, per.lat1, per.lon1)
    return per.drop(columns=["lat0", "lon0", "lat1", "lon1"])


def buoyancy_activity(ds, jitter_cc=1.0, max_gap_s=300):
    """How much the buoyancy pump moved: |change| in pumped volume between samples.

    Uses whichever buoyancy variable the platform reports (Seaglider VBD, Slocum oil
    volume, SeaExplorer ballast). Changes below `jitter_cc` are treated as sensor
    noise, and gaps longer than `max_gap_s` are not bridged.
    """
    var = next((v for v in ("GLIDER_RELATIVE_VBD", "OIL_VOL", "BALLAST_POSITION") if v in ds), None)
    if var is None:
        return None
    d = ds[[var]].to_dataframe().reset_index().dropna(subset=[var])
    d["moved"] = d[var].diff().abs()
    d.loc[d.moved < jitter_cc, "moved"] = 0.0
    d.loc[d.TIME.diff().dt.total_seconds() > max_gap_s, "moved"] = np.nan
    d["mode"] = mode_of(d.TIME).to_numpy()
    return d.dropna(subset=["mode"])


def dive_windows(name, ds, nc_dir):
    """Start and end time of each dive, matching the dives used for the energy columns."""
    gps = next((nc_dir.parent / f"{name}_20260128").glob("*_GPS_timeseries.csv"), None)
    if gps is not None and "FG_AHR_24V" in pd.read_csv(gps, nrows=0).columns:
        d = pd.read_csv(gps)
        return pd.DataFrame({"start": pd.to_datetime(d.startTime, unit="s"),
                             "end": pd.to_datetime(d.endTime, unit="s")})
    if "SEGMENT_NUMBER" not in ds:
        return None
    g = ds[["SEGMENT_NUMBER", "DEPTH"]].to_dataframe().reset_index().dropna(subset=["DEPTH"]).groupby("SEGMENT_NUMBER")
    w = pd.DataFrame({"start": g.TIME.min(), "end": g.TIME.max(), "depth": g.DEPTH.max()})
    return w[w.depth > 100].reset_index(drop=True)


def pump_per_dive(name, ds, nc_dir, pump):
    """Volume the buoyancy pump moved during each dive (cc), with the dive's mode."""
    windows = dive_windows(name, ds, nc_dir)
    if windows is None or pump is None or not len(windows):
        return None
    moved = pump.dropna(subset=["moved"]).set_index("TIME").moved.sort_index()
    totals = [moved.loc[s:e].sum() if e > s else np.nan for s, e in zip(windows.start, windows.end)]
    out = windows.assign(cc=totals, hours=(windows.end - windows.start).dt.total_seconds() / 3600)
    out["mode"] = mode_of(out.start).to_numpy()
    return out[(out.hours > 0.5) & out.cc.notna()]


def mission_modes(name, ds, nc_dir):
    """Per mission mode: dive pattern, energy use and speeds for one glider."""
    dives = dives_table(name, ds, nc_dir)
    if dives is not None and len(dives):
        dives = dives.reset_index(drop=True).assign(mode=lambda d: mode_of(d.start).to_numpy())
    rows = ds[["DEPTH", "PROFILE_DIRECTION", "GLIDER_VERT_VELO_DZDT"]].to_dataframe().reset_index()
    rows["mode"] = mode_of(rows.TIME)
    profiling = rows[(rows.PROFILE_DIRECTION != 0) & rows["mode"].notna()]
    pump = buoyancy_activity(ds)
    per_dive = pump_per_dive(name, ds, nc_dir, pump)

    out = []
    for mode, _, _ in MODES:
        prof = profiling[profiling["mode"] == mode]
        r = {"glider": name, "mode": mode, "rows": len(prof)}
        if len(prof):
            r["median |vert speed| m/s"] = round(float(np.nanmedian(np.abs(prof.GLIDER_VERT_VELO_DZDT))), 3)
            r["deepest in mode m"] = round(float(prof.DEPTH.max()))
        if pump is not None:
            p = pump[pump["mode"] == mode]
            hours = (p.TIME.max() - p.TIME.min()).total_seconds() / 3600 if len(p) else 0
            if hours >= 1:
                r["cc pumped per hour"] = round(float(p.moved.sum() / hours))
                r["pump moves per hour"] = round(float((p.moved > 0).sum() / hours))
            if per_dive is not None:
                pd_mode = per_dive[per_dive["mode"] == mode]
                if len(pd_mode):
                    r["cc pumped per dive"] = round(float(pd_mode.cc.median()))
                    r["pump dives counted"] = len(pd_mode)
        if dives is not None and len(dives):
            d = dives[dives["mode"] == mode].dropna(subset=["hours"])
            d = d[(d.hours > 0.5) & (d["max depth m"] > 100)] if "max depth m" in d else d
            wh = d["W h"].dropna()
            wh = wh[(wh >= 0) & (wh < 100)]
            if len(d):
                r.update({"dives": len(d), "median dive h": round(float(d.hours.median()), 2),
                          "median max depth m": round(float(d["max depth m"].median()))})
            if len(wh):
                hours = d.loc[wh.index, "hours"]
                km = d.loc[wh.index, "km"]
                r.update({"W h/dive": round(float(wh.median()), 1),
                          "Watts": round(float((wh / hours).median()), 2),
                          "km/dive": round(float(km.median()), 2),
                          "km per hour": round(float((km / hours).median()), 3),
                          "W h per km": round(float((wh / km.replace(0, np.nan)).median()), 1)})
        out.append(r)
    return out


def build(nc_dir, specs_path):
    specs = load_specs(specs_path)
    gliders, power, modes = [], [], []
    for f in sorted(nc_dir.glob("*.nc")):
        ds = xr.open_dataset(f)
        name = str(ds.PLATFORM_NAME.values)
        s = specs.loc[name.lower()]
        time = pd.to_datetime(ds.TIME.values)
        gliders.append({
            "glider": name, "platform": str(ds.PLATFORM_MODEL.values).replace(" glider", ""),
            "serial": str(ds.PLATFORM_SERIAL_NUMBER.values), "owner": s.Owner, "PAM system": s["PAM system"],
            "hydrophone": hydrophones(ds) or s["Hydrophone Type"], "battery type": s["Battery Type"],
            "battery capacity": s["Battery Capacity"], "deployment start": time[0].strftime("%Y-%m-%d %H:%M"),
            "deployment days": round((time[-1] - time[0]).total_seconds() / 86400, 1),
            "profiles": int(ds.PROFILE_NUMBER.max()), "max depth m": round(float(ds.DEPTH.where(ds.DEPTH_QC != 4).max())),
        })
        energy = seaglider_energy(name, nc_dir) or oceanscout_energy(name, ds, nc_dir) or slocum_energy(ds) or {
            "energy source": "voltage only, no charge counter" if "BATTERY_VOLTAGE" in ds else "none (no engineering export)"}
        power.append({"glider": name, "platform": gliders[-1]["platform"], "PAM system": s["PAM system"], **energy})
        modes.extend(mission_modes(name, ds, nc_dir))

    order = ["sg607", "sg274", "risso", "stenella", "capex987", "SEA117", "belladonna"]
    key = lambda df: df.glider.map({n: i for i, n in enumerate(order)}).fillna(99)  # noqa: E731
    gliders = pd.DataFrame(gliders).sort_values(by="glider", key=lambda c: key(pd.DataFrame({"glider": c})))
    power = pd.DataFrame(power).sort_values(by="glider", key=lambda c: key(pd.DataFrame({"glider": c})))
    modes = pd.DataFrame(modes)
    modes["_order"] = modes.glider.map({n: i for i, n in enumerate(order)}).fillna(99)
    modes["_mode"] = modes["mode"].map({m[0]: i for i, m in enumerate(MODES)})
    modes = modes.sort_values(["_order", "_mode"]).drop(columns=["_order", "_mode"])
    return gliders, power, modes


def write(sheets, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for sheet, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet, index=False)
            ws = writer.sheets[sheet]
            ws.freeze_panes = "A2"
            for column in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in column)
                ws.column_dimensions[column[0].column_letter].width = min(max(width + 2, 10), 46)
            for cell in ws[1]:
                cell.font = Font(bold=True)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--nc-dir", type=Path, default=DEFAULT_NC_DIR)
    p.add_argument("--specs", type=Path, default=DEFAULT_SPECS)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = p.parse_args()

    gliders, power, modes = build(args.nc_dir, args.specs)
    notes = pd.DataFrame(NOTES, columns=["item", "note"])
    out = write({"Gliders": gliders, "Power use": power, "Mission modes": modes, "Notes": notes}, args.out)
    print(f"wrote {out} ({len(gliders)} gliders, {len(modes)} mission-mode rows)")
    print(modes.to_string(index=False))


if __name__ == "__main__":
    main()
