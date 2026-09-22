#!/usr/bin/env python3
"""Reduce the Seaglider deployment archive to one row per dive, for the endurance model.

The archive (output/Seaglider endurance tool/SG644 deployments/, ~1.6 GB, gitignored) holds the
basestation's per-dive netCDF files, p<glider><dive>.nc. Each carries the glider's own energy
bookkeeping for that dive, which is what the endurance calculator is fitted to:

  $DEVICES / $DEVICE_SECS / $DEVICE_MAMPS   on-time and mean current of every internal device
  $SENSORS / $SENSOR_SECS / $SENSOR_MAMPS   the same for each sensor slot (SciCon, PAM, UVP, ...)
  $24V_AH, $10V_AH                          pack voltage and the glider's cumulative Ah counter
  gc_* (guidance and control table)         every pump, pitch and roll move, with depth and current

Energy of a device in a dive is secs * mA. The buoyancy pump is additionally broken down per
move, so its cost can be fitted against pressure instead of per dive.

Only files with engineering data are read (the 2017 psc*.nc files are science-only). A dive
that appears in several folders (reprocessed copies, the Lofoten "eddy mission" duplicate) is
kept once, keyed on (glider, mission, dive).

Usage:  python3 code/extract_seaglider_dives.py
Writes: content/data/seaglider-dives.csv
Needs:  netCDF4, numpy, pandas (requirements.txt), and the archive in output/.
"""
import glob
import math
import os
import warnings
from pathlib import Path

import netCDF4
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parent.parent
ARCHIVE = REPO / "output" / "Seaglider endurance tool" / "SG644 deployments"
OUT = REPO / "content" / "data" / "seaglider-dives.csv"

# Log parameters carried through as-is (pilot settings and battery configuration).
PARAMS = ["ID", "MISSION", "DIVE", "D_TGT", "T_DIVE", "MAX_BUOY", "SM_CC", "CALL_NDIVES",
          "N_NOSURFACE", "AH0_24V", "AH0_10V", "SC_RECORDABOVE", "PA_RECORDABOVE", "PA_PROFILE",
          "CAPUPLOAD", "D_BOOST", "T_BOOST"]

# Devices whose loads are summed into one column each in the output. Anything the glider logs
# that is not named here lands in e_other, so a new firmware device cannot vanish silently.
GROUPS = {
    "pump_apogee": ["VBD_pump_during_apogee"],
    "pump_surface": ["VBD_pump_during_surface", "VBD_valve"],
    "motors": ["Pitch_motor", "Roll_motor"],
    "comms": ["Iridium_during_init", "Iridium_during_connect", "Iridium_during_xfer", "GPS",
              "GPS_charging", "Transponder_ping"],
    "tt8_sampling": ["TT8_Sampling"],
    "hotel": ["TT8", "LPSleep", "TT8_Active", "TT8_CF8", "TT8_Kalman", "Analog_circuits",
              "Compass", "Compass2", "Transponder", "GUMSTIX_24V", "RAFOS"],
}


def val(v, k):
    """A log variable as a python scalar, list or string (None if absent)."""
    if k not in v:
        return None
    x = v[k][:]
    if x.dtype.kind == "S":
        return str(netCDF4.chartostring(x))
    x = np.ma.filled(np.asarray(x, dtype=float), np.nan)
    return x.tolist() if x.size > 1 else float(x)


def csv_floats(s):
    return [float(t) for t in s.split(",")]


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def pump_moves(v, maxdepth):
    """Split the dive's pump moves into the apogee pump and the shallow top-up.

    The netCDF has no pump start position, so each move's volume is the change in VBD position
    since the previous guidance-and-control event. Energy per move is secs * current * pack
    voltage (J), so gliders on different pack voltages can be compared.
    """
    need = ["gc_vbd_secs", "gc_vbd_i", "gc_depth", "gc_vbd_ad"]
    if any(k not in v for k in need) or "log_VBD_CNV" not in v:
        return {}
    g = {k: np.ma.filled(np.asarray(v[k][:], dtype=float), np.nan) for k in need}
    volts = (np.ma.filled(np.asarray(v["gc_vbd_volts"][:], dtype=float), np.nan)
             if "gc_vbd_volts" in v else np.full(len(g["gc_vbd_ad"]), np.nan))
    cc = np.diff(g["gc_vbd_ad"], prepend=np.nan) * float(v["log_VBD_CNV"][:])
    pumping = (g["gc_vbd_secs"] > 0) & (g["gc_vbd_i"] > 0) & (cc > 5)
    joules = g["gc_vbd_secs"] * g["gc_vbd_i"] * volts
    deep = pumping & (g["gc_depth"] > 0.5 * maxdepth)
    shallow = pumping & ~deep
    out = {"cc_apogee": np.nansum(cc[deep]), "j_apogee": np.nansum(joules[deep]),
           "cc_shallow": np.nansum(cc[shallow]), "j_shallow": np.nansum(joules[shallow])}
    out["d_apogee"] = (np.nansum(g["gc_depth"][deep] * cc[deep]) / out["cc_apogee"]
                       if out["cc_apogee"] > 0 else np.nan)
    return out


def dive_row(path):
    ds = netCDF4.Dataset(path)
    v = ds.variables
    if "log_DEVICES" not in v:
        return None
    r = {"file": os.path.relpath(path, ARCHIVE)}
    for k in PARAMS:
        r[k] = val(v, "log_" + k)

    devices = val(v, "log_DEVICES").split(",")
    secs = csv_floats(val(v, "log_DEVICE_SECS"))
    mamps = csv_floats(val(v, "log_DEVICE_MAMPS"))
    ah = {d: s * i / 3.6e6 for d, s, i in zip(devices, secs, mamps)}
    known = set()
    for group, names in GROUPS.items():
        r["e_" + group] = sum(ah.get(n, 0.0) for n in names)
        known.update(names)
    r["e_other"] = sum(a for d, a in ah.items() if d not in known)
    r["s_tt8_sampling"] = dict(zip(devices, secs)).get("TT8_Sampling", 0.0)
    r["s_iridium"] = sum(dict(zip(devices, secs)).get(n, 0.0) for n in GROUPS["comms"][:3])

    # Sensor slots: keep each named sensor's on-time and logged current.
    names = val(v, "log_SENSORS").split(",")
    ssecs = csv_floats(val(v, "log_SENSOR_SECS"))
    smamps = csv_floats(val(v, "log_SENSOR_MAMPS"))
    fitted = [n for n in names if n != "nil"]
    r["sensors"] = "|".join(fitted)
    for n, s, i in zip(names, ssecs, smamps):
        if n != "nil":
            r["S_" + n] = s
            r["I_" + n] = i
    r["instrument"] = ds.getncattr("instrument").strip() if "instrument" in ds.ncattrs() else ""
    r["firmware"] = (ds.getncattr("seaglider_software_version")
                     if "seaglider_software_version" in ds.ncattrs() else "")

    r["v24"], r["ah24"] = csv_floats(val(v, "log_24V_AH"))
    r["v10"], r["ah10"] = csv_floats(val(v, "log_10V_AH"))

    # GPS1 = first fix after surfacing (end of the previous dive), GPS2 = last fix before this
    # dive, GPS = first fix after this dive. So GPS1 -> GPS is one full surface + dive cycle.
    t1, t2, t3 = val(v, "log_gps_time")
    lat, lon = val(v, "log_gps_lat"), val(v, "log_gps_lon")
    r["t_start"], r["surface_min"], r["dive_min"] = t2, (t2 - t1) / 60, (t3 - t2) / 60
    r["km_ground"] = haversine_km(lat[1], lon[1], lat[2], lon[2])

    t = np.ma.filled(np.asarray(v["time"][:], dtype=float), np.nan)
    z = np.ma.filled(np.asarray(v["depth"][:], dtype=float), np.nan)
    r["maxdepth"] = float(np.nanmax(z))
    dt = np.diff(t, append=t[-1])
    for lim in (100, 200, 300, 500, 900):
        r[f"t_above_{lim}"] = float(np.nansum(dt[z < lim]))
    r["n_eng"] = len(t)
    for dim in ("sbect", "contopt", "wlseaowl", "auxCompass", "wlbb2fl"):
        key = dim + "_data_point"
        r["n_" + dim] = len(ds.dimensions[key]) if key in ds.dimensions else 0

    # Through-water distance from the flight model (horz_speed is cm/s in basestation 2.9).
    if "horz_speed" in v:
        hs = np.ma.filled(np.asarray(v["horz_speed"][:], dtype=float), np.nan)
        tt = t if len(t) == len(hs) else (
            np.ma.filled(np.asarray(v["ctd_time"][:], dtype=float), np.nan)
            if "ctd_time" in v and len(v["ctd_time"]) == len(hs) else None)
        if tt is not None:
            r["km_water"] = float(np.nansum(hs * np.diff(tt, append=tt[-1]))) / 1e5

    dfs = val(v, "log_DATA_FILE_SIZE")
    cfs = val(v, "log_CAP_FILE_SIZE")
    r["kb_data"] = csv_floats(dfs)[0] / 1000 if dfs else np.nan
    r["kb_cap"] = csv_floats(cfs)[0] / 1000 if cfs else np.nan
    r.update(pump_moves(v, r["maxdepth"]))
    return r


def main():
    rows = {}
    for path in sorted(glob.glob(str(ARCHIVE / "**" / "p[0-9]*.nc"), recursive=True)):
        try:
            r = dive_row(path)
        except Exception as e:  # a truncated file should not stop the run, but say so
            print(f"skipped {os.path.relpath(path, ARCHIVE)}: {e}")
            continue
        if r is None:
            continue
        key = (int(r["ID"]), int(r["MISSION"]), int(r["DIVE"]))
        rows.setdefault(key, r)
    df = pd.DataFrame(rows.values()).sort_values(["ID", "MISSION", "DIVE"])
    for c in ("ID", "MISSION", "DIVE"):
        df[c] = df[c].astype(int)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False, float_format="%.6g")
    print(f"wrote {OUT.relative_to(REPO)}: {len(df)} dives")
    print(df.groupby(["ID", "MISSION"]).agg(dives=("DIVE", "size"), sensors=("sensors", "first")))


if __name__ == "__main__":
    main()
