/*
 * Seaglider endurance model (firmware 66.12), fitted to our own dive logs.
 *
 * One function, used both by the page (content/seaglider-endurance.qmd, where the build
 * script inlines it) and by code/build_seaglider_page.js, which runs it against every logged
 * dive before the page is rebuilt. Coefficients come from content/data/seaglider-model.json;
 * see code/fit_seaglider_model.py for how each one was fitted.
 *
 * Everything is Ah drawn from the pack per dive cycle (surface + dive). On a dual-pack
 * glider the pump and motors draw from the 24 V pack and everything else from the 10 V pack,
 * as the Seaglider's own counters book it.
 */
(function (root) {
  "use strict";

  // Science sensors that can be hosted either by the SciCon or polled by the TT8.
  // The SciCon fit covers CT + optode + SeaOWL (+ its aux compass) sampled together, so a
  // subset on the SciCon is charged that fit's per-set energy in proportion to the sensors'
  // TT8-equivalent energy per sample. The proportion is an estimate; the total is measured.
  var SCICON_FITTED_SET = ["SBE_CT", "CONTOPT", "SEAOWL"];

  function sampleEnergy(model, key, mA) {
    var s = model.tt8_sensors[key];
    return (mA == null ? s.mA : mA) * s.s_per_sample; // mAs per sample
  }

  function evaluate(model, cfg) {
    var g = model.gliders[cfg.glider];
    var diveS = 2 * cfg.depth / cfg.w;              // w is the mean vertical speed over the dive
    var diveH = diveS / 3600;
    var cycleH = diveH + cfg.surface_min / 60;
    var callN = Math.max(1, cfg.call_ndives || 1);
    var interval = Math.max(1, cfg.sample_interval);
    var nSamples = diveS / interval;
    var v24 = cfg.battery.v24;

    var parts = [];                                  // [key, label, Ah per dive, bus]
    function add(key, label, ah, bus) { parts.push({ key: key, label: label, ah: ah, bus: bus }); }

    var pumpJ = (cfg.pump_factor || 1) * (cfg.max_buoy + cfg.sm_cc) * (g.pump.a + g.pump.b * cfg.depth);
    add("pump", "Buoyancy pump", pumpJ / (v24 * 3600), 24);
    add("motors", "Pitch and roll motors", g.motors.m0 + g.motors.m1 * diveH, 24);
    add("hotel", "Processor, compass and sleep", g.hotel.h0 + g.hotel.h1 * cycleH, 10);
    // Iridium: the fixed cost of a call is paid every CALL_NDIVES dives, but the data volume
    // still has to go up, so only the fixed part divides.
    add("comms", "Iridium and GPS", g.comms.c0 / callN + g.comms.c1 * cfg.kb, 10);

    // Science sensors, on the SciCon or on the TT8.
    var sci = cfg.science || {};
    var polledS = 0;
    var onSciCon = !!cfg.scicon;
    var fitted = 0, chosen = 0;
    SCICON_FITTED_SET.forEach(function (k) { fitted += sampleEnergy(model, k); });
    Object.keys(sci).forEach(function (k) {
      var s = sci[k];
      if (!s || !s.on) return;
      var label = model.tt8_sensors[k].label;
      if (onSciCon) {
        chosen += sampleEnergy(model, k);
      } else {
        polledS += model.tt8_sensors[k].s_per_sample * nSamples;
        add("sci_" + k, label + " (on TT8)", sampleEnergy(model, k, s.mA) * nSamples / 3.6e6, 10);
      }
    });
    if (onSciCon && chosen > 0) {
      var sc = model.scicon;
      var mA = sc.base_mA + sc.per_set_mAs * (chosen / fitted) / interval;
      add("scicon", "SciCon and its sensors", mA * diveS / 3.6e6, 10);
    }
    var tt8S = g.tt8.per_hour * cycleH + g.tt8.per_eng * nSamples + g.tt8.per_polled * polledS;
    add("tt8", "TT8 sampling", g.tt8.mA * tt8S / 3.6e6, 10);

    // Loggers: current x time recording. They record above a depth, on a share of dives.
    (cfg.loggers || []).forEach(function (L) {
      if (!L.on) return;
      var above = L.record_above == null ? 1 : Math.min(1, L.record_above / cfg.depth);
      var duty = L.duty == null ? 1 : L.duty;
      add("log_" + L.key, L.label, L.mA * diveS * above * duty / 3.6e6, 10);
    });

    var bus24 = 0, bus10 = 0, total = 0;
    parts.forEach(function (p) {
      total += p.ah;
      if (p.bus === 24) bus24 += p.ah; else bus10 += p.ah;
    });

    var b = cfg.battery, keep = 1 - (b.reserve_pct || 0) / 100, dives, limit;
    if (b.dual) {
      var d24 = b.cap24 * keep / bus24, d10 = b.cap10 * keep / bus10;
      dives = Math.min(d24, d10);
      limit = d24 < d10 ? "24 V pack" : "10 V pack";
    } else {
      dives = b.cap24 * keep / total;
      limit = "pack";
    }
    var kmPerDive = 2 * cfg.depth * cfg.glide_ratio / 1000;
    return {
      parts: parts, total: total, bus24: bus24, bus10: bus10,
      dive_h: diveH, cycle_h: cycleH, t_dive_min: diveS / 60,
      dives: dives, days: dives * cycleH / 24, km: dives * kmPerDive,
      ah_per_day: total * 24 / cycleH, km_per_day: kmPerDive * 24 / cycleH,
      limit: limit
    };
  }

  var api = { evaluate: evaluate };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SeagliderModel = api;
})(this);
