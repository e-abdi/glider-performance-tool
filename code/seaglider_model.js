/*
 * Seaglider endurance model (firmware 66.12, single battery pack), fitted to our glider's logs.
 *
 * One function, used both by the page (content/seaglider-endurance.qmd, where the build
 * script inlines it) and by code/build_seaglider_page.js, which runs it against every logged
 * dive before the page is rebuilt. Coefficients come from content/data/seaglider-model.json;
 * see code/fit_seaglider_model.py for how each one was fitted.
 *
 * Everything is Ah drawn from the pack per dive cycle (surface + dive).
 */
(function (root) {
  "use strict";

  // Sensors that can be hosted by the SciCon or polled by the TT8. The SciCon fit covers
  // all three sampled together, so a subset on the SciCon is charged that fit's per-sample
  // energy in proportion to the sensors' TT8-equivalent energy per sample. The proportion is
  // an estimate; the total is measured.
  var SCICON_FITTED_SET = ["SBE_CT", "CONTOPT", "ECO"];

  function sampleEnergy(model, key, mA) {
    var s = model.sensors[key];
    return (mA == null ? s.mA : mA) * s.s_per_sample; // mAs per sample
  }

  // Samples in one dive from a science-file style table: rows of {to: depth (m), interval (s)},
  // each row covering from the previous row's depth down to its own. The glider passes through
  // every band twice (down and up) at the mean vertical speed w.
  function samplesPerDive(bins, depth, w) {
    var n = 0, top = 0;
    var rows = (bins || []).filter(function (b) { return b && b.to > 0 && b.interval > 0; })
      .sort(function (a, b) { return a.to - b.to; });
    for (var i = 0; i < rows.length && top < depth; i++) {
      var bottom = Math.min(rows[i].to, depth);
      if (bottom > top) n += 2 * (bottom - top) / w / rows[i].interval;
      top = Math.max(top, rows[i].to);
    }
    if (top < depth && rows.length) n += 2 * (depth - top) / w / rows[rows.length - 1].interval;
    return n;
  }

  function evaluate(model, cfg) {
    var g = model.glider;
    var diveS = 2 * cfg.depth / cfg.w;              // w is the mean vertical speed over the dive
    var diveH = diveS / 3600;
    var cycleH = diveH + cfg.surface_min / 60;
    var callN = Math.max(1, cfg.call_ndives || 1);
    var nSamples = samplesPerDive(cfg.bins, cfg.depth, cfg.w);

    var parts = [];                                  // {key, label, ah per dive}
    function add(key, label, ah) { parts.push({ key: key, label: label, ah: ah }); }

    var pumpJ = (cfg.pump_factor || 1) * (cfg.max_buoy + cfg.sm_cc) * (g.pump.a + g.pump.b * cfg.depth);
    add("pump", "Buoyancy pump", pumpJ / (cfg.battery.volts * 3600));
    add("motors", "Pitch and roll motors", g.motors.m0 + g.motors.m1 * diveH);
    add("hotel", "Processor, compass and sleep", g.hotel.h0 + g.hotel.h1 * cycleH);
    // Iridium: the fixed cost of a call is paid every CALL_NDIVES dives, but the data volume
    // still has to go up, so only the fixed part divides.
    add("comms", "Iridium and GPS", g.comms.c0 / callN + g.comms.c1 * cfg.kb);

    // Science sensors, on the SciCon or polled by the TT8.
    var sci = cfg.science || {};
    var polledS = 0, fitted = 0, chosen = 0;
    SCICON_FITTED_SET.forEach(function (k) { fitted += sampleEnergy(model, k); });
    Object.keys(sci).forEach(function (k) {
      var s = sci[k];
      if (!s || !s.on) return;
      if (cfg.scicon) {
        chosen += sampleEnergy(model, k);
      } else {
        polledS += model.sensors[k].s_per_sample * nSamples;
        add("sci_" + k, model.sensors[k].label, sampleEnergy(model, k, s.mA) * nSamples / 3.6e6);
      }
    });
    if (cfg.scicon && chosen > 0) {
      var sc = model.scicon;
      add("scicon", "SciCon and its sensors",
          (sc.base_mA * diveS + sc.per_set_mAs * (chosen / fitted) * nSamples) / 3.6e6);
    }
    var tt8S = g.tt8.per_hour * cycleH + g.tt8.per_eng * nSamples + g.tt8.per_polled * polledS;
    add("tt8", "TT8 sampling", g.tt8.mA * tt8S / 3.6e6);

    // Loggers: current x time recording. They record above a depth, on a share of dives.
    (cfg.loggers || []).forEach(function (L) {
      if (!L.on) return;
      var above = L.record_above == null ? 1 : Math.min(1, L.record_above / cfg.depth);
      var duty = L.duty == null ? 1 : L.duty;
      add("log_" + L.key, L.label, L.mA * diveS * above * duty / 3.6e6);
    });

    var total = 0;
    parts.forEach(function (p) { total += p.ah; });
    var usable = cfg.battery.capacity * (1 - (cfg.battery.reserve_pct || 0) / 100);
    var dives = usable / total;
    var kmPerDive = 2 * cfg.depth * cfg.glide_ratio / 1000;
    return {
      parts: parts, total: total, samples: nSamples,
      dive_h: diveH, cycle_h: cycleH, t_dive_min: diveS / 60,
      usable_ah: usable, dives: dives, days: dives * cycleH / 24, km: dives * kmPerDive,
      ah_per_day: total * 24 / cycleH, km_per_day: kmPerDive * 24 / cycleH
    };
  }

  var api = { evaluate: evaluate, samplesPerDive: samplesPerDive };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SeagliderModel = api;
})(this);
