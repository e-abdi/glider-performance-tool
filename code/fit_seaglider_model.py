#!/usr/bin/env python3
"""Fit the Seaglider endurance model to the per-dive energy logs.

There is no manufacturer endurance tool for this firmware (66.12), so the model is built
from what the gliders logged. Each term below is a regression of one group of logged loads
against the variable that physically drives it, fitted separately for each glider:

  buoyancy pump   J/dive  = pump_factor * (MAX_BUOY + SM_CC) * (a + b * depth)
                  The glider pumps about 2 x MAX_BUOY at apogee and tops up to SM_CC near the
                  surface; the cost of a cc rises with pressure. Joules, so that packs of
                  different voltage share one law; Ah = J / (pack V * 3600).
  pitch + roll    Ah/dive = m0 + m1 * dive hours
  hotel           Ah/dive = h0 + h1 * cycle hours       (TT8, sleep, CF card, compass, analog)
  comms           Ah/dive = c0 + c1 * kB sent           (Iridium, GPS, transponder ping)
  TT8 sampling    secs    = t0 * cycle h + t1 * eng samples + t2 * polled-sensor secs
  SciCon          mA      = base + per_set / sample interval  (fitted on missions 5 and 6)

Sensors on the TT8 are charged as logged current * on-time per sample, the on-time per sample
being measured (e.g. SBE CT 0.68 s, Contros optode 2.8 s). Loggers (PAM, UVP6, echosounder)
are charged current * the time they record.

Usage:  python3 code/fit_seaglider_model.py
Reads:  content/data/seaglider-dives.csv   (from code/extract_seaglider_dives.py)
Writes: content/data/seaglider-model.json
Then:   node code/build_seaglider_page.js  (validates the model and updates the page)
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DIVES = REPO / "content" / "data" / "seaglider-dives.csv"
OUT = REPO / "content" / "data" / "seaglider-model.json"

# Missions whose SciCon was sampling in its standard way. Mission 7's deep dives report
# ~38 mA at a slower sample rate than mission 5's 13 mA, which no sampling law explains;
# it is shown in the validation, not fitted.
SCICON_FIT_MISSIONS = [5, 6]

# The pump law's depth slope is only identifiable from SG644, the one glider that dove
# deeper than 300 m. Other gliders keep their own intercept and borrow this slope.
SLOPE_FROM = 644

# Sensors that can run on the TT8 (polled each sample). On-time per sample is measured where
# the sensor flew on the TT8; the SeaOWL never did, so its figure comes from its .cnf
# (105 mA, 1.2 s warm-up) and the ECO puck's measured on-time, and is marked estimated.
TT8_SENSORS = {
    "SBE_CT": {"label": "Sea-Bird CT (SBE 41 style)", "log": "SBE_CT"},
    "CONTOPT": {"label": "Contros HydroFlash O2 optode", "log": "CONTOPT"},
    "WL_ECO": {"label": "WET Labs ECO puck (BB2FL)", "log": "WL_blue_red_Chl_old_fw"},
}

LOGGERS = {"PAM": "PAM", "UVP": "UVP", "ESNDR": "ESNDR"}


def lstsq(y, *cols):
    """Least squares with every coefficient held >= 0.

    A load cannot be negative, but with few dives the terms are collinear (SG150's TT8 time
    tracks both cycle length and sample count) and a plain fit trades one against the other
    into negative values. Terms that go negative are dropped and the rest refitted.
    """
    A = np.column_stack(cols).astype(float)
    y = np.asarray(y, dtype=float)
    keep = list(range(A.shape[1]))
    while True:
        coef = np.linalg.lstsq(A[:, keep], y, rcond=None)[0]
        if (coef >= 0).all() or len(keep) == 1:
            break
        keep.pop(int(np.argmin(coef)))
    out = [0.0] * A.shape[1]
    for i, c in zip(keep, coef):
        out[i] = max(float(c), 0.0)
    return out


def prepare(d):
    d = d[(d.dive_min > 10) & (d.surface_min > 0) & (d.surface_min < 240)].copy()
    d["dive_h"] = d.dive_min / 60
    d["cycle_h"] = (d.dive_min + d.surface_min) / 60
    d["kb"] = d.kb_data.fillna(0) + d.kb_cap.fillna(0)
    d["eng_interval"] = d.dive_min * 60 / d.n_eng
    return d


def fit_glider(g, slope=None):
    pump_j = (g.e_pump_apogee + g.e_pump_surface) * g.v24 * 3600
    vol = g.MAX_BUOY + g.SM_CC
    if slope is None:
        a, b = lstsq(pump_j, vol, vol * g.maxdepth)
    else:
        b = slope
        a = float(np.median(pump_j / vol - b * g.maxdepth))
    m0, m1 = lstsq(g.e_motors, np.ones(len(g)), g.dive_h)
    h0, h1 = lstsq(g.e_hotel, np.ones(len(g)), g.cycle_h)
    c0, c1 = lstsq(g.e_comms, np.ones(len(g)), g.kb)
    polled = sum(g.get("S_" + s["log"], pd.Series(0, index=g.index)).fillna(0)
                 for s in TT8_SENSORS.values())
    t0, t1, t2 = lstsq(g.s_tt8_sampling, g.cycle_h, g.n_eng, polled)
    tt8_ma = float(np.median((g.e_tt8_sampling * 3.6e6 / g.s_tt8_sampling)[g.s_tt8_sampling > 0]))
    dual = bool(g.AH0_10V.median() > 0)
    return {
        "pump": {"a": a, "b": b},
        "motors": {"m0": m0, "m1": m1},
        "hotel": {"h0": h0, "h1": h1},
        "comms": {"c0": c0, "c1": c1},
        "tt8": {"per_hour": t0, "per_eng": t1, "per_polled": t2, "mA": tt8_ma},
        "battery": {
            "dual": dual,
            "cap24": float(g.AH0_24V.median()), "cap10": float(g.AH0_10V.median()),
            "v24": float(g.v24.median()), "v10": float(g.v10.median()),
        },
    }


def mission_summary(g, fit):
    """Median settings of one mission, as a preset, plus what it actually used."""
    first = g.iloc[0]
    sensors = str(first.sensors).split("|") if isinstance(first.sensors, str) else []
    depth = float(g.maxdepth.median())
    p = {
        "glider": int(first.ID), "mission": int(first.MISSION),
        "start": pd.to_datetime(g.t_start.min(), unit="s").strftime("%Y-%m-%d"),
        "end": pd.to_datetime(g.t_start.max(), unit="s").strftime("%Y-%m-%d"),
        "dives": int(len(g)), "firmware": str(first.firmware),
        "instrument": str(first.instrument),
        "depth": round(depth), "d_tgt": float(g.D_TGT.median()),
        "w": round(float(np.median(2 * g.maxdepth / (g.dive_min * 60))), 3),
        "surface_min": round(float(g.surface_min.median()), 1),
        "max_buoy": float(g.MAX_BUOY.median()), "sm_cc": float(g.SM_CC.median()),
        "kb": round(float(g.kb.median())),
        "glide_ratio": round(float((g.km_water * 1000 / (2 * g.maxdepth)).median()), 2),
        "eng_interval": round(float(g.eng_interval.median()), 1),
        "sensors": sensors,
    }
    s = {}
    if "SciCon" in sensors:
        on = g[g.S_SciCon > 0]
        s["scicon"] = {"interval": round(float((on.S_SciCon / on.n_sbect).median()), 1)}
    for key, log in LOGGERS.items():
        if log in sensors:
            col = g["S_" + log].fillna(0)
            on = g[col > 0]
            entry = {"mA": float(on["I_" + log].median()) if len(on) else 0.0,
                     "duty": round(float((col > 0).mean()), 2)}
            if key == "PAM":
                entry["record_above"] = float(g.PA_RECORDABOVE.median())
            else:
                entry["frac"] = round(float((on["S_" + log] / (on.dive_min * 60)).median()), 2)
            s[key] = entry
    for key, meta in TT8_SENSORS.items():
        if meta["log"] in sensors:
            s[key] = {"interval": p["eng_interval"]}
    p["settings"] = s

    # What it used, from the device logs (all loads, PAM included) and from the glider's
    # own Ah counter (which leaves the PAM out; see the page notes).
    logged = g[[c for c in g.columns if c.startswith("e_")]].sum(axis=1)
    for col in [c for c in g.columns if c.startswith("S_")]:
        name = col[2:]
        logged = logged + (g[col].fillna(0) * g["I_" + name].fillna(0) / 3.6e6)
    days = float(g.cycle_h.sum() / 24)
    p["used"] = {
        "ah_logged": round(float(logged.sum()), 2),
        "ah_per_dive": round(float(logged.mean()), 4),
        "ah_per_day": round(float(logged.sum() / days), 3),
        "days": round(days, 1),
        "counter_ah": round(float((g.ah24 + g.ah10).max() - (g.ah24 + g.ah10).min()), 2),
    }
    return p


def main():
    d = prepare(pd.read_csv(DIVES))
    fits = {}
    slope = None
    for gid in [SLOPE_FROM] + [i for i in sorted(d.ID.unique()) if i != SLOPE_FROM]:
        g = d[d.ID == gid]
        fits[str(gid)] = fit_glider(g, None if gid == SLOPE_FROM else slope)
        if gid == SLOPE_FROM:
            slope = fits[str(gid)]["pump"]["b"]

    # SciCon: mA = base + per_set / interval, where interval is seconds between sample sets.
    sc = d[(d.ID == 644) & d.MISSION.isin(SCICON_FIT_MISSIONS) & (d.S_SciCon > 0)]
    base, per_set = lstsq(sc.I_SciCon, np.ones(len(sc)), sc.n_sbect / sc.S_SciCon)

    tt8 = {}
    for key, meta in TT8_SENSORS.items():
        col = "S_" + meta["log"]
        if col in d:
            on = d[d[col].fillna(0) > 0]
            tt8[key] = {"label": meta["label"], "mA": float(on["I_" + meta["log"]].median()),
                        "s_per_sample": round(float((on[col] / on.n_eng).median()), 3),
                        "measured": True}
    tt8["SEAOWL"] = {"label": "WET Labs SeaOWL", "mA": 105.0,
                     "s_per_sample": tt8["WL_ECO"]["s_per_sample"], "measured": False}

    missions = [mission_summary(g, fits[str(k[0])]) for k, g in d.groupby(["ID", "MISSION"])]

    # Pump factor per mission: how much more (or less) the pump cost than the glider's law.
    for m in missions:
        g = d[(d.ID == m["glider"]) & (d.MISSION == m["mission"])]
        f = fits[str(m["glider"])]["pump"]
        j = (g.e_pump_apogee + g.e_pump_surface) * g.v24 * 3600
        law = (g.MAX_BUOY + g.SM_CC) * (f["a"] + f["b"] * g.maxdepth)
        m["pump_factor"] = round(float(np.median(j / law)), 2)

    model = {
        "source": "Fitted by code/fit_seaglider_model.py to content/data/seaglider-dives.csv",
        "dives": int(len(d)),
        "gliders": fits,
        "scicon": {"base_mA": round(base, 2), "per_set_mAs": round(per_set, 1),
                   "fit_missions": SCICON_FIT_MISSIONS,
                   "hosts": "SBE CT, Contros optode, WET Labs SeaOWL, auxiliary compass/pressure"},
        "tt8_sensors": tt8,
        "missions": missions,
    }
    OUT.write_text(json.dumps(model, indent=1) + "\n")
    print(f"wrote {OUT.relative_to(REPO)}")
    print(json.dumps({k: v for k, v in model.items() if k != "missions"}, indent=1))
    for m in missions:
        print(m["glider"], m["mission"], m["start"], m["dives"], m["depth"], m["w"],
              m["surface_min"], m["pump_factor"], m["settings"], m["used"])


if __name__ == "__main__":
    main()
