/* ============================================================================
   Credit Decision Studio — prototype front end

   Design contract, carried over from REQUIREMENTS.md §12.1 and extended in
   §18.3: THE UI COMPUTES NOTHING. Every figure rendered here is read straight
   out of `data.js`, which is produced by `ui/export_fixture.py` calling the
   same core functions the headless CLIs call. There is no arithmetic in this
   file beyond turning a number into a string, a width, or an SVG coordinate.

   When the API lands (T2), `F` is replaced by fetched responses with identical
   keys and this file does not otherwise change. That is the point of it.
   ========================================================================= */
(function () {
  'use strict';

  var F = window.__FIXTURE__ || {};
  var CFG = (F.meta && F.meta.config) || {};

  /* ------------------------------------------------------------------ state */
  var S = {
    page: 'baseline',
    theme: null,
    lang: 'en',
    cutoff: 700,
    cap: 0.5,
    r3: 1,
    r4: 1,
    optRun: false,
    optRunning: false,
    capThreshold: 0.035,
    ccAllocation: 10,
    ccLive: false,
    mcStage: 0
  };

  /* ------------------------------------------------- formatting primitives */
  // NaN is not zero (§12.1). A missing rate renders as an em dash, always.
  var DASH = '—';
  function isNum(v) { return typeof v === 'number' && isFinite(v); }
  function pct(v, dp) {
    if (!isNum(v)) return DASH;
    return (v * 100).toFixed(dp == null ? 2 : dp) + '%';
  }
  function num(v) { return isNum(v) ? Math.round(v).toLocaleString('en-US') : DASH; }
  function dec(v, dp) { return isNum(v) ? v.toFixed(dp == null ? 3 : dp) : DASH; }
  function signed(v) {
    if (!isNum(v)) return DASH;
    return (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(Math.round(v)).toLocaleString('en-US');
  }
  function sar(v) {
    if (!isNum(v)) return DASH;
    return 'SAR ' + Math.round(v).toLocaleString('en-US');
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function el(html) { var d = document.createElement('div'); d.innerHTML = html; return d.firstElementChild; }

  /* Provenance badge. Every rate on every screen carries one (§12.3). */
  function pv(label) {
    return '<span class="pv pv-' + esc(label) + '">' + esc(label.replace('_', ' ')) + '</span>';
  }

  /* ------------------------------------------------------------ tooltip */
  var tipEl = document.getElementById('tip');
  function showTip(evt, html) {
    tipEl.innerHTML = html;
    tipEl.style.opacity = '1';
    var r = tipEl.getBoundingClientRect();
    var x = evt.clientX + 14, y = evt.clientY + 14;
    if (x + r.width > window.innerWidth - 8) x = evt.clientX - r.width - 14;
    if (y + r.height > window.innerHeight - 8) y = evt.clientY - r.height - 14;
    tipEl.style.left = Math.max(8, x) + 'px';
    tipEl.style.top = Math.max(8, y) + 'px';
  }
  function hideTip() { tipEl.style.opacity = '0'; }
  function bindTips(root) {
    root.querySelectorAll('[data-tip]').forEach(function (n) {
      n.addEventListener('mousemove', function (e) { showTip(e, n.getAttribute('data-tip')); });
      n.addEventListener('mouseleave', hideTip);
    });
  }
  function tipRows(title, rows) {
    return '<b>' + esc(title) + '</b>' + rows.map(function (r) {
      return '<div class="r"><span>' + esc(r[0]) + '</span><span>' + r[1] + '</span></div>';
    }).join('');
  }

  /* ============================================================== charts ==
     Hand-drawn SVG. One scale places marks, ticks and labels; every label
     names a value the chart actually reaches; chart text takes theme tokens
     so it reads in both themes.
     Magnitude is encoded in ink density, never hue — hue is reserved for
     provenance across the whole product.
     ===================================================================== */

  function waterfallChart(steps) {
    var W = 850, rowH = 34, padT = 14, padB = 26, labelW = 228, valW = 104;
    var plotX = labelW, plotW = W - labelW - valW;
    var H = padT + steps.length * rowH + padB;
    var max = steps[0].remaining || 1;
    var x = function (v) { return plotX + (v / max) * plotW; };

    var out = '<svg class="chart" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Decline waterfall">';
    // faint vertical grid at 0/25/50/75/100% of the application total
    [0, .25, .5, .75, 1].forEach(function (f) {
      out += '<line class="grid" x1="' + x(max * f) + '" y1="' + padT + '" x2="' + x(max * f) + '" y2="' + (H - padB) + '"/>';
      out += '<text x="' + x(max * f) + '" y="' + (H - padB + 14) + '" text-anchor="middle">' + num(max * f) + '</text>';
    });

    var running = max;
    steps.forEach(function (s, i) {
      var y = padT + i * rowH, bh = 19, by = y + (rowH - bh) / 2;
      var isEdge = s.kind === 'start' || s.kind === 'end' || s.kind === 'subtotal';
      var x0, x1, fill, stroke;
      if (isEdge) {
        x0 = x(0); x1 = x(s.remaining);
        fill = 'var(--sunken)'; stroke = 'var(--line-hard)';
      } else {
        // a removal step: floats from the new remaining up to the old remaining
        x0 = x(s.remaining); x1 = x(running);
        fill = s.kind === 'adjustment' ? 'var(--nm-wash)' : 'var(--sunken)';
        stroke = s.kind === 'adjustment' ? 'var(--nm)' : 'var(--ink-2)';
        if (s.delta > 0) { x0 = x(running); x1 = x(s.remaining); }
      }
      var lo = Math.min(x0, x1), wid = Math.max(2, Math.abs(x1 - x0));
      out += '<rect x="' + lo + '" y="' + by + '" width="' + wid + '" height="' + bh + '" rx="2.5" fill="' + fill + '" stroke="' + stroke + '" stroke-width="1"/>';
      out += '<text x="' + (labelW - 10) + '" y="' + (y + rowH / 2 + 3.5) + '" text-anchor="end" class="' + (isEdge ? 'lbl-strong' : '') + '">' + esc(s.label) + '</text>';
      var dv = s.kind === 'start' ? num(s.remaining) : (isEdge ? num(s.remaining) : signed(-Math.abs(s.delta) * (s.delta > 0 ? -1 : 1)));
      if (!isEdge) dv = (s.delta < 0 ? '−' : '+') + num(Math.abs(s.delta));
      out += '<text x="' + (W - 8) + '" y="' + (y + rowH / 2 + 3.5) + '" text-anchor="end" class="lbl-strong">' + dv + '</text>';
      if (!isEdge) {
        out += '<text x="' + (W - valW + 4) + '" y="' + (y + rowH / 2 + 3.5) + '" text-anchor="start" opacity=".75">' + pct(Math.abs(s.delta_pct), 1) + '</text>';
      }
      if (!isEdge) running = s.remaining;
      else running = s.remaining;
      // connector to the next row
      if (i < steps.length - 1) {
        out += '<line class="grid" x1="' + x(s.remaining) + '" y1="' + (by + bh) + '" x2="' + x(s.remaining) + '" y2="' + (y + rowH + (rowH - bh) / 2) + '" stroke-dasharray="2 2"/>';
      }
    });
    return out + '</svg>';
  }

  function calibrationChart(rows) {
    var W = 420, H = 260, pad = { t: 12, r: 12, b: 34, l: 46 };
    var vals = rows.map(function (r) { return Math.max(r.mean_predicted, r.observed_bad_rate); });
    var max = Math.max.apply(null, vals) * 1.12;
    var x = function (v) { return pad.l + (v / max) * (W - pad.l - pad.r); };
    var y = function (v) { return H - pad.b - (v / max) * (H - pad.t - pad.b); };
    var out = '<svg class="chart" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Calibration: predicted vs observed bad rate by decile">';
    [0, .25, .5, .75, 1].forEach(function (f) {
      out += '<line class="grid" x1="' + pad.l + '" y1="' + y(max * f) + '" x2="' + (W - pad.r) + '" y2="' + y(max * f) + '"/>';
      out += '<text x="' + (pad.l - 7) + '" y="' + (y(max * f) + 3.5) + '" text-anchor="end">' + pct(max * f, 1) + '</text>';
      out += '<text x="' + x(max * f) + '" y="' + (H - pad.b + 15) + '" text-anchor="middle">' + pct(max * f, 1) + '</text>';
    });
    out += '<line x1="' + x(0) + '" y1="' + y(0) + '" x2="' + x(max) + '" y2="' + y(max) + '" stroke="var(--line-hard)" stroke-width="1.5" stroke-dasharray="4 3"/>';
    rows.forEach(function (r) {
      out += '<circle cx="' + x(r.mean_predicted) + '" cy="' + y(r.observed_bad_rate) + '" r="5" fill="var(--pred)" stroke="var(--surface)" stroke-width="2"/>';
    });
    out += '<text x="' + (W / 2) + '" y="' + (H - 4) + '" text-anchor="middle" opacity=".8">mean predicted PD  →</text>';
    out += '<text transform="translate(11,' + (H / 2) + ') rotate(-90)" text-anchor="middle" opacity=".8">observed bad rate  →</text>';
    return out + '</svg>';
  }

  function coefChart(rows) {
    var terms = rows.filter(function (r) { return r.kind !== 'intercept'; });
    var W = 420, rowH = 30, pad = { t: 8, b: 26, l: 150, r: 42 };
    var H = pad.t + terms.length * rowH + pad.b;
    var max = Math.max.apply(null, terms.map(function (r) { return Math.abs(r.coefficient); })) * 1.15;
    var midX = pad.l + (W - pad.l - pad.r) / 2, half = (W - pad.l - pad.r) / 2;
    var out = '<svg class="chart" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Model coefficients">';
    out += '<line class="axis" x1="' + midX + '" y1="' + pad.t + '" x2="' + midX + '" y2="' + (H - pad.b) + '"/>';
    terms.forEach(function (r, i) {
      var y = pad.t + i * rowH + 6, bh = 14;
      var w = Math.abs(r.coefficient) / max * half;
      var x0 = r.coefficient >= 0 ? midX : midX - w;
      out += '<rect x="' + x0 + '" y="' + y + '" width="' + Math.max(1.5, w) + '" height="' + bh + '" rx="2" fill="var(--pred-wash)" stroke="var(--pred)" stroke-width="1"/>';
      out += '<text x="' + (pad.l - 9) + '" y="' + (y + 11) + '" text-anchor="end">' + esc(r.term) + '</text>';
      out += '<text x="' + (W - 4) + '" y="' + (y + 11) + '" text-anchor="end" class="lbl-strong">' + dec(r.coefficient, 3) + '</text>';
    });
    out += '<text x="' + midX + '" y="' + (H - 8) + '" text-anchor="middle" opacity=".7">← lowers PD     raises PD →</text>';
    return out + '</svg>';
  }

  // Magnitude ramp: achromatic, so hue stays reserved for provenance.
  function inkRamp(t) {
    var a = 0.04 + 0.62 * Math.pow(Math.max(0, Math.min(1, t)), 0.75);
    return 'color-mix(in srgb, var(--ink) ' + (a * 100).toFixed(1) + '%, var(--surface))';
  }

  function heatmapTable(hm) {
    var max = 0;
    hm.values.forEach(function (row) { row.forEach(function (v) { if (v > max) max = v; }); });
    var out = '<div class="tablewrap"><table class="t"><thead><tr><th>Score band</th>';
    hm.cols.forEach(function (c) { out += '<th class="num">FOIR ' + esc(c) + '</th>'; });
    out += '</tr></thead><tbody>';
    hm.rows.forEach(function (rname, i) {
      out += '<tr><td class="rid">' + esc(rname) + '</td>';
      hm.values[i].forEach(function (v, j) {
        var t = max ? v / max : 0;
        var tip = tipRows(rname + ' × FOIR ' + hm.cols[j], [['Declined', num(v)], ['Share of declines', pct(v / declineTotal(), 2)]]);
        out += '<td class="num" style="background:' + inkRamp(t) + ';color:' + (t > 0.55 ? 'var(--surface)' : 'var(--ink)') + '" data-tip="' + esc(tip) + '">' + num(v) + '</td>';
      });
      out += '</tr>';
    });
    return out + '</tbody></table></div>';
  }
  function declineTotal() {
    var last = F.waterfall.steps[F.waterfall.steps.length - 1];
    return F.meta.n_rows - last.remaining;
  }

  function funnelChart(stages) {
    var max = stages[0].v;
    return '<div class="funnel">' + stages.map(function (s) {
      var w = max ? (s.v / max) * 100 : 0;
      return '<div class="fstep"><div class="fbar"><div class="ffill" style="inline-size:' + w.toFixed(1) + '%"></div>' +
        '<div class="ftext"><span class="fn">' + num(s.v) + '</span><span class="fl">' + esc(s.l) + '</span></div></div>' +
        '<div class="fpct">' + pct(s.v / max, 1) + '</div></div>';
    }).join('') + '</div>';
  }

  function sensitivityStrip(rows, threshold, operating) {
    var W = 420, H = 150, pad = { t: 14, r: 12, b: 34, l: 48 };
    var max = Math.max(threshold, Math.max.apply(null, rows.map(function (r) { return r.blended_bad_rate; }))) * 1.18;
    var bw = (W - pad.l - pad.r) / rows.length;
    var y = function (v) { return H - pad.b - (v / max) * (H - pad.t - pad.b); };
    var out = '<svg class="chart" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Blended bad rate by conservatism penalty">';
    [0, .5, 1].forEach(function (f) {
      out += '<line class="grid" x1="' + pad.l + '" y1="' + y(max * f) + '" x2="' + (W - pad.r) + '" y2="' + y(max * f) + '"/>';
      out += '<text x="' + (pad.l - 7) + '" y="' + (y(max * f) + 3.5) + '" text-anchor="end">' + pct(max * f, 1) + '</text>';
    });
    rows.forEach(function (r, i) {
      var breach = r.blended_bad_rate > threshold;
      var x0 = pad.l + i * bw + bw * 0.22, w = bw * 0.56;
      var yy = y(r.blended_bad_rate);
      out += '<rect x="' + x0 + '" y="' + yy + '" width="' + w + '" height="' + (y(0) - yy) + '" rx="3" fill="' + (breach ? 'var(--breach-wash)' : 'var(--sunken)') + '" stroke="' + (breach ? 'var(--breach)' : 'var(--ink-2)') + '" stroke-width="1.2"/>';
      out += '<text x="' + (x0 + w / 2) + '" y="' + (yy - 5) + '" text-anchor="middle" class="lbl-strong" style="font-size:9.5px">' + pct(r.blended_bad_rate, 2) + '</text>';
      var isOp = Math.abs(r.penalty - operating) < 1e-9;
      out += '<text x="' + (x0 + w / 2) + '" y="' + (H - pad.b + 15) + '" text-anchor="middle"' + (isOp ? ' class="lbl-strong"' : '') + '>×' + r.penalty.toFixed(2) + '</text>';
      if (isOp) out += '<text x="' + (x0 + w / 2) + '" y="' + (H - pad.b + 27) + '" text-anchor="middle" style="font-size:8.5px" opacity=".8">operating</text>';
    });
    out += '<line x1="' + pad.l + '" y1="' + y(threshold) + '" x2="' + (W - pad.r) + '" y2="' + y(threshold) + '" stroke="var(--breach)" stroke-width="1.4" stroke-dasharray="5 3"/>';
    out += '<text x="' + (W - pad.r) + '" y="' + (y(threshold) - 5) + '" text-anchor="end" style="fill:var(--breach);font-size:9.5px">appetite ' + pct(threshold, 2) + '</text>';
    return out + '</svg>';
  }

  /* Stacked provenance bar — the product's signature component. */
  function provenanceBar(parts) {
    var total = parts.reduce(function (a, p) { return a + p.v; }, 0) || 1;
    var bar = '<div class="pvbar">' + parts.map(function (p) {
      return '<div class="s-' + p.k + '" style="flex:0 0 ' + (p.v / total * 100).toFixed(2) + '%" data-tip="' +
        esc(tipRows(p.l, [['Applicants', num(p.v)], ['Share', pct(p.v / total, 1)]])) + '"></div>';
    }).join('') + '</div>';
    var keys = '<div class="pvkeys">' + parts.map(function (p) {
      return '<div class="k"><span class="sw ' + (p.k === 'nm' ? 'nmsw' : '') + '" style="' + (p.k === 'nm' ? '' : 'background:var(--' + (p.k === 'obs' ? 'obs' : 'inf') + ')') + '"></span>' +
        '<span class="lbl">' + esc(p.l) + '</span><span class="v">' + num(p.v) + '</span></div>';
    }).join('') + '</div>';
    return bar + keys;
  }

  function gauge(value, cap, label) {
    var breach = isNum(value) && value > cap;
    var w = isNum(value) ? Math.min(100, value / (cap * 1.25) * 100) : 0;
    var capX = 100 / 1.25;
    return '<div class="gauge' + (breach ? ' is-breach' : '') + '">' +
      '<div class="rowlbl"><span>' + esc(label) + '</span><span>cap ' + pct(cap, 2) + '</span></div>' +
      '<div class="track"><div class="fill" style="inline-size:' + w.toFixed(1) + '%"></div>' +
      '<div class="cap" style="inset-inline-start:' + capX.toFixed(1) + '%"></div></div></div>';
  }

  function sparkline(series, w, h, color) {
    var max = Math.max.apply(null, series), min = Math.min.apply(null, series);
    var span = (max - min) || 1;
    var pts = series.map(function (v, i) {
      return (i / (series.length - 1) * w).toFixed(1) + ',' + (h - (v - min) / span * h).toFixed(1);
    }).join(' ');
    return '<svg class="chart" viewBox="0 0 ' + w + ' ' + h + '" style="height:' + h + 'px" role="img" aria-hidden="true">' +
      '<polyline points="' + pts + '" fill="none" stroke="' + color + '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>' +
      '<circle cx="' + w + '" cy="' + (h - (series[series.length - 1] - min) / span * h).toFixed(1) + '" r="3.5" fill="' + color + '"/></svg>';
  }

  /* ============================================================ components */
  function tiles(items, cols) {
    return '<div class="tiles c' + (cols || items.length) + '">' + items.map(function (t) {
      return '<div class="tile' + (t.tone ? ' on-' + t.tone : '') + '">' +
        '<div class="k">' + esc(t.k) + (t.pv ? pv(t.pv) : '') + '</div>' +
        '<div class="v">' + t.v + (t.unit ? '<small>' + esc(t.unit) + '</small>' : '') + '</div>' +
        (t.d ? '<div class="d">' + t.d + '</div>' : '') + '</div>';
    }).join('') + '</div>';
  }

  function panel(title, body, opts) {
    opts = opts || {};
    return '<section class="panel"' + (opts.id ? ' id="' + opts.id + '"' : '') + '>' +
      '<div class="panelhead"><h2>' + esc(title) + '</h2>' +
      (opts.hint ? '<span class="hint">' + esc(opts.hint) + '</span>' : '') +
      (opts.right ? '<div class="spacer"></div>' + opts.right : '') + '</div>' +
      '<div class="panelbody' + (opts.tight ? ' tight' : '') + '">' + body + '</div></section>';
  }

  function caveat(kind, icon, html) {
    return '<div class="caveat ' + kind + '"><span class="ci">' + esc(icon) + '</span><div>' + html + '</div></div>';
  }

  function table(cols, rows) {
    var out = '<div class="tablewrap"><table class="t"><thead><tr>';
    cols.forEach(function (c) { out += '<th' + (c.num ? ' class="num"' : '') + '>' + c.h + '</th>'; });
    out += '</tr></thead><tbody>';
    rows.forEach(function (r) {
      out += '<tr class="' + (r._cls || '') + '">';
      cols.forEach(function (c) { out += '<td' + (c.num ? ' class="num"' : '') + '>' + (r[c.k] == null ? '<span class="nodata">' + DASH + '</span>' : r[c.k]) + '</td>'; });
      out += '</tr>';
    });
    return out + '</tbody></table></div>';
  }

  function dlBtns(name) {
    return '<button class="btn ghost sm" data-dl="' + esc(name) + '">Export CSV</button>' +
      '<button class="btn ghost sm" data-dl="' + esc(name) + '" data-fmt="json" style="margin-inline-start:6px">JSON</button>';
  }

  /* ================================================================ lookups */
  function scenarioKey(cut, cap, r3, r4) { return cut + '|' + cap + '|' + r3 + '|' + r4; }
  function scenario(cut, cap, r3, r4) {
    var g = F.grid && F.grid.scenarios;
    if (!g) return null;
    var k = scenarioKey(cut, cap, r3, r4);
    if (g[k]) return g[k];
    // tolerate float-to-string drift between the exporter and the browser
    var want = String(cap);
    var alt = Object.keys(g).filter(function (kk) {
      var p = kk.split('|');
      return +p[0] === cut && Math.abs(+p[1] - +want) < 1e-9 && +p[2] === r3 && +p[3] === r4;
    })[0];
    return alt ? g[alt] : null;
  }
  function baselineScenario() { return scenario(700, 0.5, 1, 1); }

  /* ================================================================ screens */
  var PAGES = [
    { g: 'Understand', id: 'baseline', n: '01', t: 'Baseline', flag: 'obs' },
    { g: 'Understand', id: 'waterfall', n: '02', t: 'Decline waterfall', flag: 'obs' },
    { g: 'Understand', id: 'model', n: '03', t: 'Risk model & support', flag: 'inf' },
    { g: 'Decide', id: 'whatif', n: '04', t: 'What-if simulator', flag: 'inf' },
    { g: 'Decide', id: 'optimiser', n: '05', t: 'Strategy optimiser', flag: 'inf' },
    { g: 'Decide', id: 'portfolio', n: '06', t: 'Portfolio quality', flag: 'obs' },
    { g: 'Operate', id: 'cc', n: '07', t: 'Champion / challenger' },
    { g: 'Operate', id: 'governance', n: '08', t: 'Governance & audit' },
    { g: 'Assure', id: 'validation', n: '09', t: 'Validation', flag: 'breach' },
    { g: 'Assure', id: 'roadmap', n: '10', t: 'Delivery roadmap' }
  ];

  var AR = {
    'Understand': 'الفهم', 'Decide': 'القرار', 'Operate': 'التشغيل', 'Assure': 'التحقق',
    'Baseline': 'خط الأساس', 'Decline waterfall': 'شلال الرفض', 'Risk model & support': 'نموذج المخاطر',
    'What-if simulator': 'محاكاة السيناريوهات', 'Strategy optimiser': 'محسّن الاستراتيجية',
    'Portfolio quality': 'جودة المحفظة', 'Champion / challenger': 'المنافس والبطل',
    'Governance & audit': 'الحوكمة والتدقيق', 'Validation': 'التحقق من الصحة', 'Delivery roadmap': 'خارطة التسليم',
    'Evidence ledger': 'سجل الأدلة'
  };
  function T(s) { return S.lang === 'ar' && AR[s] ? AR[s] : s; }

  /* ---------------------------------------------------------- 01 baseline */
  function pageBaseline() {
    var o = F.overview, rep = o.reproduction;
    var perfect = rep.match_rate_excl_overrides >= 0.9999;
    var wf = F.waterfall.steps;
    var declines = F.meta.n_rows - o.booked_count;

    var head = pageHead('Stage 01 · Understand', 'What the book actually did',
      'One year of applications, the decisions that were taken on them, and the only number that entitles everything after it: whether this engine reproduces your current strategy exactly.');

    var kpis = tiles([
      { k: 'Applications', v: '<span class="fig">' + num(F.meta.n_rows) + '</span>', d: esc(o.app_date_min.slice(0, 10)) + ' → ' + esc(o.app_date_max.slice(0, 10)) },
      { k: 'Approved (book)', v: '<span class="fig">' + num(o.booked_count) + '</span>', d: 'Approval rate <span class="fig">' + pct(o.booked_count / F.meta.n_rows) + '</span>' },
      { k: 'Observed bad rate', pv: 'OBSERVED', tone: 'obs', v: '<span class="fig">' + pct(o.observed_bad_rate) + '</span>', d: 'Booked customers with a known outcome' },
      { k: 'Declined', v: '<span class="fig">' + num(declines) + '</span>', d: 'The population this product is about' }
    ], 4);

    var repBody =
      '<div class="cols2"><div>' +
      tiles([
        { k: 'Reproduction, raw', v: '<span class="fig">' + pct(rep.raw_match_rate) + '</span>', d: '<span class="fig">' + num(rep.n_mismatches) + '</span> decisions differ' },
        { k: 'Excluding overrides', tone: perfect ? 'obs' : 'breach', v: '<span class="fig">' + pct(rep.match_rate_excl_overrides) + '</span>', d: '<span class="fig">' + num(rep.n_mismatches_not_override) + '</span> unexplained' }
      ], 2) +
      (perfect ? '' : caveat('breach', '!', '<p><strong>Reproduction is below 100% once manual overrides are excluded.</strong> Every simulation built on this strategy inherits the gap. Do not proceed to Stage 04 until it is closed.</p>')) +
      '<p class="note" style="margin-top:13px">If we cannot reproduce your current strategy exactly, every simulation on top of it is decoration. The raw gap here is <span class="fig">' + pct(1 - rep.raw_match_rate) + '</span> and it is fully accounted for, override by override, in both directions.</p>' +
      '</div><div>' +
      '<h3 style="margin:0 0 9px;font-family:var(--mono);font-size:10px;letter-spacing:.11em;text-transform:uppercase;color:var(--faint)">Override ledger</h3>' +
      table([{ h: 'Direction', k: 'd' }, { h: 'Count', k: 'c', num: true }, { h: 'Share', k: 's', num: true }], [
        { d: 'Decline → approve <span class="rid">(R5/R6 near-miss)</span>', c: '<span class="fig">' + num(rep.n_override_decline_to_approve) + '</span>', s: '<span class="fig">' + pct(rep.n_override_decline_to_approve / F.meta.n_rows, 2) + '</span>' },
        { d: 'Approve → decline', c: '<span class="fig">' + num(rep.n_override_approve_to_decline) + '</span>', s: '<span class="fig">' + pct(rep.n_override_approve_to_decline / F.meta.n_rows, 2) + '</span>' },
        { _cls: 'is-total', d: 'Total manual overrides', c: '<span class="fig">' + num(rep.n_manual_overrides) + '</span>', s: '<span class="fig">' + pct(rep.n_manual_overrides / F.meta.n_rows, 2) + '</span>' }
      ]) +
      '<p class="note" style="margin-top:11px">Decline→approve overrides are the one place in this dataset where a declined applicant has <em>genuine observed performance</em>. Stage 03 uses them as the near-cutoff anchor.</p>' +
      '</div></div>';

    var ruleBody = table(
      [{ h: 'Rule', k: 'id' }, { h: 'Class', k: 'cls' }, { h: 'Parameters', k: 'p' }, { h: 'Failed (any)', k: 'f', num: true }, { h: 'Sole reason', k: 's', num: true }],
      F.waterfall.single_rule.map(function (r) {
        var rule = (CFG.strategy.rules || []).filter(function (x) { return x.id === r.rule_id; })[0] || {};
        var params = Object.keys(rule.params || {}).map(function (k) { return k + ' = ' + rule.params[k]; }).join(', ') || '—';
        var regulatory = r.rule_id === 'R6_FOIR';
        return {
          id: '<span class="rid">' + esc(r.rule_id) + '</span>',
          cls: r.mandatory ? '<span class="lock">MANDATORY</span>' : (regulatory ? '<span class="lock">REGULATORY · SAMA DBR</span>' : '<span class="rid" style="color:var(--muted)">relaxable</span>'),
          p: '<span class="rid">' + esc(params) + '</span>',
          f: '<span class="fig">' + num(r.failed_any) + '</span>',
          s: '<span class="fig">' + num(r.single_rule_declines) + '</span>'
        };
      })
    ) + caveat('warn', '§16.3', '<p><strong><span class="rid">R6_FOIR</span> is shown as a regulatory rule in this build.</strong> In the Kingdom, affordability is partly a SAMA limit rather than a commercial preference: a regulatory rule cannot be edited in the UI, moved by the optimiser, or bypassed by an override. On the current engine it is still modelled as relaxable — the lock lands in the T2 deployable build.</p>');

    return head + kpis +
      panel('Strategy reproduction', repBody, { hint: '§7.3' }) +
      panel('The current strategy, as written', ruleBody, { hint: '§7.1 · evaluated in order; first failure is the decline reason' });
  }

  /* --------------------------------------------------------- 02 waterfall */
  function pageWaterfall() {
    var wf = F.waterfall.steps;
    var last = wf[wf.length - 1];
    var head = pageHead('Stage 02 · Understand', 'Where the declines actually go',
      'Every applicant leaves the funnel at exactly one place — the first rule they failed. The steps below sum to the application total on screen, which is the only way to know the picture is complete.');

    var sums = '<p class="note" style="margin-bottom:12px">Applications <span class="fig">' + num(F.meta.n_rows) + '</span> − removals <span class="fig">' + num(F.meta.n_rows - last.remaining) + '</span> = approvals <span class="fig">' + num(last.remaining) + '</span>. The chart reconciles by construction; if it did not, the engine raises rather than rounding it away.</p>';

    var sr = F.waterfall.single_rule.slice().sort(function (a, b) { return b.single_rule_declines - a.single_rule_declines; });
    var srBody = table(
      [{ h: 'Rule', k: 'id' }, { h: 'Failed any', k: 'f', num: true }, { h: 'Failed ONLY this', k: 's', num: true }, { h: '% of applications', k: 'p', num: true }, { h: '', k: 'bar' }],
      sr.map(function (r) {
        var w = r.single_rule_declines / sr[0].single_rule_declines * 100;
        return {
          id: '<span class="rid">' + esc(r.rule_id) + '</span>' + (r.mandatory ? ' <span class="lock">MAND</span>' : ''),
          f: '<span class="fig">' + num(r.failed_any) + '</span>',
          s: '<span class="fig">' + num(r.single_rule_declines) + '</span>',
          p: '<span class="fig">' + pct(r.single_rule_pct_of_applications, 2) + '</span>',
          bar: '<div style="height:9px;width:110px;background:var(--sunken);border-radius:3px;overflow:hidden"><div style="height:100%;inline-size:' + w.toFixed(1) + '%;background:var(--ink-2)"></div></div>'
        };
      })
    ) + caveat('obs', '→', '<p><strong>Single-rule declines are the near-miss population.</strong> An applicant who failed one relaxable rule and passed everything else is a candidate for Stage 05. An applicant who failed three is not, at any cutoff. The rest of this product happens inside the first group.</p>');

    return head +
      panel('Decline waterfall', sums + waterfallChart(wf), { hint: '§8 · includes the manual-override adjustment step', right: dlBtns('waterfall') }) +
      panel('Single-rule declines', srBody, { hint: 'failed exactly one rule' }) +
      panel('Declines by score × FOIR', heatmapTable(F.waterfall.heatmap) +
        '<p class="note" style="margin-top:12px">Shading is volume, not risk — magnitude is drawn in ink so that colour stays reserved for provenance everywhere in this product. The dense block just under the cutoff is what Stage 04 and Stage 05 argue about.</p>',
        { hint: 'declined applicants only', tight: false, right: dlBtns('heatmap') });
  }

  /* ------------------------------------------------------------- 03 model */
  function pageModel() {
    var m = F.model, mt = m.metrics || {}, a = m.anchor;
    var cal = mt.calibration || m.calibration || [];
    var ranges = m.support_ranges || [];
    var scoreRange = ranges.filter(function (r) { return r.feature === 'bureau_score'; })[0] || {};

    var head = pageHead('Stage 03 · Understand', 'What the model is entitled to say',
      'A PD model trained on booked customers can only speak about the region it has seen. This page spends as much space on where the model must stay silent as on how well it performs.');

    var kpis = tiles([
      { k: 'AUC (holdout)', pv: 'PREDICTED', v: '<span class="fig">' + dec(mt.auc, 3) + '</span>', d: 'Floor <span class="fig">' + dec(CFG.model.min_auc, 2) + '</span> · n test <span class="fig">' + num(mt.n_test) + '</span>' },
      { k: 'Training population', v: '<span class="fig">' + num(mt.n_train) + '</span>', d: 'Booked only · bad rate <span class="fig">' + pct(mt.test_bad_rate) + '</span>' },
      { k: 'Outside score support', pv: 'NOT_MODELLED', v: '<span class="fig">' + num(scoreRange.applications_outside) + '</span>', d: '<span class="fig">' + pct(scoreRange.share_outside, 1) + '</span> of applications get no PD at all' },
      { k: 'Conservatism penalty', pv: 'INFERRED', tone: 'inf', v: '<span class="fig">×' + dec(CFG.model.inference_penalty, 2) + '</span>', d: 'Applied to every declined-applicant PD' }
    ], 4);

    var supportRows = ranges.map(function (r) {
      return {
        f: '<span class="rid">' + esc(r.feature) + '</span>',
        k: '<span class="rid" style="color:var(--muted)">' + esc(r.kind) + '</span>',
        s: '<span class="fig">' + esc(r.supported) + '</span>',
        b: r.bins_supported ? '<span class="fig">' + esc(r.bins_supported) + '</span>' : null,
        ai: '<span class="fig">' + num(r.applications_inside) + '</span>',
        ao: '<span class="fig">' + num(r.applications_outside) + '</span>' + (r.applications_outside > 0 ? ' ' + pv('NOT_MODELLED') : ''),
        sh: '<span class="fig">' + pct(r.share_outside, 1) + '</span>'
      };
    });

    var anchorRows = (a.cells || []).map(function (c) {
      return {
        c: '<span class="rid">' + esc(c.cell.replace(/ \| /g, ' · ')) + '</span>',
        n: '<span class="fig">' + num(c.override_count) + '</span>',
        o: '<span class="fig">' + pct(c.observed_bad_rate) + '</span> ' + pv('OBSERVED'),
        ci: '<span class="fig">' + pct(c.ci_lower, 2) + ' – ' + pct(c.ci_upper, 2) + '</span>',
        d: '<span class="fig">' + num(c.declines_count) + '</span>',
        p: '<span class="fig">' + pct(c.mean_model_pd) + '</span> ' + pv('PREDICTED'),
        r: '<span class="fig">' + dec(c.implied_penalty, 3) + '</span>'
      };
    });

    var vw = a.volume_weighted || {}, nt = a.naive_total || {};
    var conflict = a.direction_conflict;

    var anchorBody =
      '<div class="cols2" style="margin-bottom:15px">' +
      '<div class="tiles c1">' +
      '<div class="tile"><div class="k">Matched cells — score × FOIR × employment</div>' +
      '<div class="v"><span class="fig">' + dec(vw.implied_penalty, 3) + '</span><small>implied penalty</small></div>' +
      '<div class="d"><span class="fig">' + num(vw.override_count) + '</span> override approvals vs <span class="fig">' + num(vw.declines_count) + '</span> comparable declines</div></div></div>' +
      '<div class="tiles c1">' +
      '<div class="tile"><div class="k">Naive — score band only</div>' +
      '<div class="v"><span class="fig">' + dec(nt.implied_penalty, 3) + '</span><small>implied penalty</small></div>' +
      '<div class="d"><span class="fig">' + num(nt.override_count) + '</span> override approvals vs <span class="fig">' + num(nt.declines_count) + '</span> declines in band</div></div></div>' +
      '</div>' +
      (conflict ? caveat('breach', '≠', '<p><strong>The two measurements disagree in sign.</strong> Measured across the whole score band the implied penalty is <span class="fig">' + dec(nt.implied_penalty, 3) + '</span> — declines look <em>worse</em> than overrides. Measured inside matched score × FOIR × employment cells it is <span class="fig">' + dec(vw.implied_penalty, 3) + '</span> — they look <em>better</em>.</p><p>The gap is mix, not risk: the override population is not distributed across FOIR and employment the way the decline population is. Most tools would have shown you the naive number on its own.</p>') : '') +
      (a.warnings || []).map(function (w) { return caveat('warn', '§9.4', '<p>' + esc(w) + '</p>'); }).join('') +
      caveat('', '?', '<p><strong>What this ratio is not.</strong> It is not a selection-bias estimate, and it is not a measurement of how declined applicants would have performed. Override approvals were chosen by humans who saw things the data does not carry, so their observed rate is a <em>lower bound</em> on that cell\'s true rate — which makes the implied penalty a lower bound on the penalty you should be using, not a value to adopt.</p>') +
      '<div style="margin-top:15px">' + table(
        [{ h: 'Cell', k: 'c' }, { h: 'Overrides', k: 'n', num: true }, { h: 'Observed', k: 'o', num: true }, { h: '95% CI', k: 'ci', num: true }, { h: 'Declines', k: 'd', num: true }, { h: 'Mean model PD', k: 'p', num: true }, { h: 'Implied ×', k: 'r', num: true }],
        anchorRows) + '</div>';

    return head + kpis +
      panel('Calibration and coefficients',
        '<div class="cols2"><div><h3 style="margin:0 0 8px;font-family:var(--mono);font-size:10px;letter-spacing:.11em;text-transform:uppercase;color:var(--faint)">Predicted vs observed, by decile</h3>' +
        (cal.length ? calibrationChart(cal) : '<p class="nodata">' + DASH + '</p>') +
        '<p class="note" style="margin-top:8px;font-size:12.5px">Dashed line is perfect calibration. Points are the ten deciles of predicted PD on the holdout.</p></div>' +
        '<div><h3 style="margin:0 0 8px;font-family:var(--mono);font-size:10px;letter-spacing:.11em;text-transform:uppercase;color:var(--faint)">Coefficients</h3>' +
        coefChart(m.coefficients || []) +
        '<p class="note" style="margin-top:8px;font-size:12.5px">Weak L2 on purpose — <span class="code">C = ' + dec(CFG.model.l2_C, 1) + '</span> — so the coefficients stay explainable to a credit committee.</p></div></div>',
        { hint: 'logistic · booked population only' }) +
      panel('Training support', table(
        [{ h: 'Feature', k: 'f' }, { h: 'Kind', k: 'k' }, { h: 'Supported range', k: 's' }, { h: 'Bins', k: 'b', num: true }, { h: 'Applications inside', k: 'ai', num: true }, { h: 'Outside', k: 'ao', num: true }, { h: 'Share out', k: 'sh', num: true }],
        supportRows) +
        caveat('', '§9.2', '<p>An applicant outside support gets <strong>no PD at all</strong> — not a confident extrapolation. Those applicants are still counted as approvals wherever a strategy would approve them, and are excluded from every blended rate, with their count shown beside it.</p>'),
        { hint: '§9.2 · a decile bin needs ' + num(CFG.model.min_support_obs) + ' booked observations to be supported', right: dlBtns('support') }) +
      panel('Near-cutoff inference anchor', anchorBody, { hint: '§9.4 · the only genuine observed performance below the cutoff' });
  }

  /* ------------------------------------------------------------ 04 whatif */
  function pageWhatIf() {
    var head = pageHead('Stage 04 · Decide', 'The obvious move, priced honestly',
      'Move the cutoff and watch the approval count rise. Then read the second row, which is the one that matters: how much of the resulting bad rate is something we observed, and how much is something we inferred.');

    var controls =
      '<div class="controls">' +
      '<div class="ctrl"><div class="row"><label>Bureau score cutoff <span class="rid" style="color:var(--faint)">R5_SCORE</span></label>' +
      '<span class="val"><span class="fig" id="cutval">700</span><span class="was">baseline 700</span></span></div>' +
      '<input type="range" id="cutoff" min="0" max="' + (F.grid.cutoffs.length - 1) + '" step="1" value="' + F.grid.cutoffs.indexOf(700) + '">' +
      '<div class="scale"><span>' + F.grid.cutoffs[0] + '</span><span>' + F.grid.cutoffs[F.grid.cutoffs.length - 1] + '</span></div></div>' +

      '<div class="ctrl"><div class="row"><label>Affordability cap <span class="rid" style="color:var(--faint)">R6_FOIR</span> <span class="lock" title="SAMA DBR">REGULATORY</span></label>' +
      '<span class="val"><span class="fig" id="capval">0.50</span><span class="was">baseline 0.50</span></span></div>' +
      '<input type="range" id="capr" min="0" max="' + (F.grid.foir_caps.length - 1) + '" step="1" value="' + F.grid.foir_caps.indexOf(0.5) + '">' +
      '<div class="scale"><span>' + F.grid.foir_caps[0].toFixed(2) + '</span><span>' + F.grid.foir_caps[F.grid.foir_caps.length - 1].toFixed(2) + '</span></div></div>' +

      '<div class="toggles">' +
      '<label class="tg"><input type="checkbox" id="r3" checked><span class="tgmain"><b>R3_THIN_FILE</b><span>Minimum bureau vintage ' + CFG.strategy.rules[2].params.min_vintage + ' months</span></span></label>' +
      '<label class="tg"><input type="checkbox" id="r4" checked><span class="tgmain"><b>R4_BUREAU_HIST</b><span>DPD &lt; ' + CFG.strategy.rules[3].params.dpd_lt + ' and ≤ ' + CFG.strategy.rules[3].params.max_enquiries + ' enquiries</span></span></label>' +
      '<label class="tg is-locked"><input type="checkbox" checked disabled><span class="tgmain"><b>R1_AGE · R2_FRAUD</b><span>Mandatory — no path in the engine can approve a failing applicant</span></span></label>' +
      '</div>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn ghost sm" id="resetwi">Reset to baseline</button>' +
      '<button class="btn ghost sm" id="loadwi">Load scenario JSON</button>' +
      '<button class="btn ghost sm" id="savewi">Save scenario</button></div>' +
      '</div>';

    return head +
      '<div class="cols2" style="grid-template-columns:minmax(280px,340px) minmax(0,1fr)">' +
      '<div>' + panel('Strategy parameters', controls, { hint: 'scenario = history + delta' }) + '</div>' +
      '<div id="wiresults"></div></div>';
  }

  function renderWhatIf() {
    var host = document.getElementById('wiresults');
    if (!host) return;
    var sc = scenario(S.cutoff, S.cap, S.r3, S.r4);
    var base = baselineScenario();
    if (!sc || !base) { host.innerHTML = panel('Scenario', '<p class="nodata">' + DASH + ' scenario not in the precomputed grid</p>'); return; }

    var changed = !(S.cutoff === 700 && S.cap === 0.5 && S.r3 === 1 && S.r4 === 1);
    var deltaApp = sc.approval_count - base.approval_count;
    var biasGap = Math.abs(sc.model_basis_baseline - sc.observed_bad_rate) / (sc.observed_bad_rate || 1);
    var biasWarn = biasGap > CFG.model.bias_warning_ratio;
    var inferredHigh = sc.inferred_share > CFG.model.max_inferred_share;

    var kpis = tiles([
      { k: 'Approvals', v: '<span class="fig">' + num(sc.approval_count) + '</span>', d: changed ? '<span class="fig">' + signed(deltaApp) + '</span> vs baseline' : 'unchanged from baseline' },
      { k: 'Approval rate', v: '<span class="fig">' + pct(sc.approval_rate) + '</span>', d: 'baseline <span class="fig">' + pct(base.approval_rate) + '</span>' },
      { k: 'Blended bad rate', pv: 'BLENDED', tone: sc.blended_bad_rate > S.capThreshold ? 'breach' : '', v: '<span class="fig">' + pct(sc.blended_bad_rate) + '</span>', d: 'appetite <span class="fig">' + pct(S.capThreshold) + '</span>' + (sc.blended_bad_rate > S.capThreshold ? ' · <strong style="color:var(--breach)">BREACH</strong>' : '') },
      { k: 'No PD available', pv: 'NOT_MODELLED', v: '<span class="fig">' + num(sc.not_modelled_count) + '</span>', d: 'approved, and excluded from the rate above' }
    ],2);

    var split = table(
      [{ h: 'Population', k: 'p' }, { h: 'Basis', k: 'b' }, { h: 'Count', k: 'n', num: true }, { h: 'Bad rate', k: 'r', num: true }],
      [
        { p: 'Retained booked', b: pv('OBSERVED'), n: '<span class="fig">' + num(sc.approval_count - sc.swap_in_count - sc.not_modelled_count) + '</span>', r: '<span class="fig">' + pct(sc.observed_bad_rate) + '</span>' },
        { p: 'Baseline book, model basis', b: pv('PREDICTED'), n: '<span class="fig">' + num(F.overview.booked_count) + '</span>', r: '<span class="fig">' + pct(sc.model_basis_baseline) + '</span>' },
        { p: 'Swap-ins with a PD', b: pv('INFERRED'), n: '<span class="fig">' + num(sc.swap_in_count - sc.not_modelled_count) + '</span>', r: '<span class="fig">' + pct(sc.inferred_bad_rate) + '</span>' },
        { _cls: 'is-nm', p: 'Swap-ins outside support', b: pv('NOT_MODELLED'), n: '<span class="fig">' + num(sc.not_modelled_count) + '</span>', r: null },
        { _cls: 'is-total', p: 'Portfolio, blended', b: pv('BLENDED'), n: '<span class="fig">' + num(sc.approval_count - sc.not_modelled_count) + '</span>', r: '<span class="fig">' + pct(sc.blended_bad_rate) + '</span>' }
      ]) +
      caveat('', '§6.1', '<p><strong>Compare against the model-basis baseline, not the observed one.</strong> The scenario\'s new approvals are priced by the model; the existing book is priced by what actually happened. Putting a model number next to an observed number and calling the difference "impact" is the single most common way these tools mislead. The honest comparator is <span class="fig">' + pct(sc.model_basis_baseline) + '</span> ' + pv('PREDICTED') + '.</p>') +
      (biasWarn ? caveat('warn', '!', '<p>The model-basis baseline and the observed baseline differ by <span class="fig">' + pct(biasGap, 1) + '</span>, above the <span class="fig">' + pct(CFG.model.bias_warning_ratio, 0) + '</span> warning threshold. Treat the blended figure as indicative only.</p>') : '') +
      (inferredHigh ? caveat('warn', '!', '<p>Inferred approvals are <span class="fig">' + pct(sc.inferred_share, 1) + '</span> of the portfolio, above the configured ceiling of <span class="fig">' + pct(CFG.model.max_inferred_share, 0) + '</span>. This is no longer a simulation of your book; it is a simulation of the model.</p>') : '');

    var retained = sc.approval_count - sc.swap_in_count - sc.not_modelled_count;
    var evid = provenanceBar([
      { k: 'obs', l: 'Observed performance', v: retained },
      { k: 'inf', l: 'Inferred from model', v: sc.swap_in_count - sc.not_modelled_count },
      { k: 'nm', l: 'No PD available', v: sc.not_modelled_count }
    ]);

    var bd = sc.swap_in_breakdown || [];
    var bdBody = bd.length ? table(
      [{ h: 'Segment', k: 's' }, { h: 'Count', k: 'n', num: true }, { h: 'Model PD', k: 'p', num: true }, { h: 'Inferred', k: 'i', num: true }, { h: 'Booked in cell', k: 'b', num: true }, { h: '', k: 'f' }],
      bd.map(function (r) {
        var isNM = /NOT_MODELLED/.test(r.segment || '');
        return {
          _cls: isNM ? 'is-nm' : '',
          s: '<span class="rid">' + esc(String(r.segment || '').replace(/ \| /g, ' · ')) + '</span>',
          n: '<span class="fig">' + num(r.count) + '</span>',
          p: isNum(r.model_pd) ? '<span class="fig">' + pct(r.model_pd) + '</span>' : null,
          i: isNum(r.inferred_bad_rate) ? '<span class="fig">' + pct(r.inferred_bad_rate) + '</span>' : null,
          b: isNum(r.booked_in_cell) ? '<span class="fig">' + num(r.booked_in_cell) + '</span>' : null,
          f: r.thin ? '<span class="thin">THIN</span>' : ''
        };
      })) : '<p class="note">No swap-ins at these parameters — the scenario reproduces the current book exactly, with zero swap-ins and zero swap-outs. That is the correctness check: an unchanged strategy must move nothing.</p>';

    host.innerHTML = kpis +
      panel('Where the rate comes from', split, { hint: 'provenance split · §6' }) +
      panel('Evidence composition', evid, { hint: 'of ' + num(sc.approval_count) + ' approvals' }) +
      panel('Swap-in breakdown', bdBody, { hint: bd.length ? 'segments contributing ≥ 1,000 approvals' : 'no delta', right: bd.length ? dlBtns('swapins') : '' }) +
      panel('Sensitivity to the conservatism penalty', sensitivityStrip(sc.sensitivity, S.capThreshold, CFG.model.inference_penalty) +
        '<p class="note" style="margin-top:9px">The penalty is a judgement, not a measurement. This strip is the honest way to present it: the strategy is only defensible if it survives the column you would be challenged on, not the one you chose.</p>',
        { hint: '§9.3' });
    bindTips(host);
  }

  /* --------------------------------------------------------- 05 optimiser */
  function pageOptimiser() {
    var head = pageHead('Stage 05 · Decide', 'Who else could we approve, and at what cost',
      'Not "lower the cutoff". The engine searches segments of the declined population and adds them one at a time until a constraint binds — then shows you which constraint stopped it and what it refused.');

    var constraintUI =
      '<div class="controls">' +
      '<div class="ctrl"><div class="row"><label>Maximum blended bad rate</label><span class="val"><span class="fig" id="capshow">' + pct(S.capThreshold) + '</span></span></div>' +
      '<input type="range" id="capslider" min="250" max="500" step="1" value="' + Math.round(S.capThreshold * 10000) + '">' +
      '<div class="scale"><span>2.50%</span><span>5.00%</span></div></div>' +
      '<div class="tg is-locked"><span class="tgmain"><b>MANDATORY RULES</b><span>R1_AGE, R2_FRAUD — unreachable by any segment override, and tested for it</span></span><span class="lock">LOCKED</span></div>' +
      '<div class="tg is-locked"><span class="tgmain"><b>REGULATORY RULES</b><span>SAMA DBR — parameter locked, not merely mandatory (§16.3)</span></span><span class="lock">LOCKED</span></div>' +
      '<div style="display:grid;gap:5px;font-family:var(--mono);font-size:11px;color:var(--muted)">' +
      '<div style="display:flex;justify-content:space-between"><span>max segments added</span><span class="fig">' + CFG.optimiser.max_segments_added + '</span></div>' +
      '<div style="display:flex;justify-content:space-between"><span>min segment size</span><span class="fig">' + num(CFG.optimiser.min_segment_size) + '</span></div>' +
      '<div style="display:flex;justify-content:space-between"><span>conservatism penalty</span><span class="fig">×' + dec(CFG.model.inference_penalty, 2) + '</span></div></div>' +
      '<button class="btn" id="runopt">' + (S.optRun ? 'Re-run optimiser' : 'Run optimiser') + '</button>' +
      '<p class="note" style="font-size:12px">Greedy, explainable, and deterministic. About four seconds on a million rows.</p>' +
      '</div>';

    return head +
      '<div class="cols2" style="grid-template-columns:minmax(280px,320px) minmax(0,1fr)">' +
      '<div>' + panel('Objective and constraints', constraintUI, { hint: '§10.2' }) + '</div>' +
      '<div id="optresults">' + (S.optRun ? '' : optIdle()) + '</div></div>';
  }

  function optIdle() {
    return panel('Result', '<div style="display:grid;gap:12px;place-items:start"><p class="note">The optimiser has not been run at these constraints. Nothing on this page is precomputed for you — press <strong>Run optimiser</strong> and watch the candidate funnel resolve.</p>' +
      '<div class="runlog"><div class="ln"><span class="st">○</span> Evaluate baseline strategy</div>' +
      '<div class="ln"><span class="st">○</span> Build candidate declines</div>' +
      '<div class="ln"><span class="st">○</span> Filter to training support</div>' +
      '<div class="ln"><span class="st">○</span> Score and rank segments</div>' +
      '<div class="ln"><span class="st">○</span> Greedy add until a constraint binds</div>' +
      '<div class="ln"><span class="st">○</span> Naive-cutoff comparison</div></div></div>', { hint: 'idle' });
  }

  function runOptimiser() {
    if (S.optRunning) return;
    S.optRunning = true;
    var host = document.getElementById('optresults');
    host.innerHTML = optIdle();
    var lines = host.querySelectorAll('.runlog .ln');
    var i = 0;
    var btn = document.getElementById('runopt');
    if (btn) { btn.disabled = true; btn.textContent = 'Running…'; }
    var step = function () {
      if (i < lines.length) {
        lines[i].classList.add('is-done');
        lines[i].querySelector('.st').textContent = '●';
        i++;
        setTimeout(step, 230 + Math.random() * 190);
      } else {
        S.optRun = true; S.optRunning = false;
        renderOptimiser();
        if (btn) { btn.disabled = false; btn.textContent = 'Re-run optimiser'; }
        pushAudit('Ran optimiser at bad_rate ≤ ' + pct(S.capThreshold), 'STRATEGY.OPTIMISE');
        renderLedger();
      }
    };
    setTimeout(step, 180);
  }

  function renderOptimiser() {
    var host = document.getElementById('optresults');
    if (!host) return;
    var o = F.optimiser, h = o.headline, cf = o.candidate_funnel, nc = o.naive_comparison;
    var base = F.overview;
    var onAppetite = Math.abs(S.capThreshold - 0.035) < 1e-9;

    var kpis = tiles([
      { k: 'Approval rate', v: '<span class="fig">' + pct(h.approval_rate) + '</span>', d: 'from <span class="fig">' + pct(base.booked_count / F.meta.n_rows) + '</span>' },
      { k: 'Incremental approvals', v: '<span class="fig">' + signed(h.swap_in_count) + '</span>', d: 'of <span class="fig">' + num(cf.in_viable_segments) + '</span> in viable segments' },
      { k: 'Blended bad rate', pv: 'BLENDED', tone: h.blended_bad_rate > 0.035 ? 'breach' : 'obs', v: '<span class="fig">' + pct(h.blended_bad_rate, 3) + '</span>', d: 'against a <span class="fig">' + pct(0.035) + '</span> cap' },
      { k: 'Binding constraint', v: '<span class="fig" style="font-size:17px">' + esc(o.binding_constraint) + '</span>', d: '<span class="fig">' + o.rejected_segments.length + '</span> candidate segments rejected' }
    ],2);

    var bind = caveat(o.binding_constraint === 'bad_rate' ? 'breach' : 'warn', '⏹',
      '<p><strong>The greedy stopped on <span class="rid">' + esc(o.binding_constraint) + '</span>.</strong> ' +
      (o.binding_constraint === 'bad_rate'
        ? 'The strategy spent its entire risk budget: it landed at <span class="fig">' + pct(h.blended_bad_rate, 3) + '</span> against a <span class="fig">' + pct(0.035) + '</span> appetite, and ' + o.rejected_segments.length + ' further segments were refused. This is what "we optimised" actually means — not that we found the best answer, but that we ran out of room.'
        : 'It ran out of segment slots before it ran out of risk budget, which means the answer is bounded by configuration rather than by appetite.') + '</p>');

    var funnel = funnelChart([
      { l: 'declined applicants', v: cf.total_declines },
      { l: 'failed only R5_SCORE / R6_FOIR', v: cf.failed_only_relaxable },
      { l: 'inside training support', v: cf.inside_support },
      { l: 'in segments above the size floor', v: cf.in_viable_segments },
      { l: 'actually approved by the recommendation', v: h.swap_in_count }
    ]) + '<p class="note" style="margin-top:11px">Ten segments out of a pool the reader cannot see is a number without a denominator. This is the denominator.</p>';

    var added = o.added_segments || [];
    var addedRows = added.map(function (r) {
      return {
        s: '<span class="rid">' + esc(String(r.rule_description || '').replace(/^Approve /, '')) + '</span>',
        n: '<span class="fig">' + num(r.count) + '</span>',
        i: '<span class="fig">' + pct(r.inferred_bad_rate) + '</span> ' + pv('INFERRED'),
        c: '<span class="fig">' + pct(r.cumulative_bad_rate, 3) + '</span>',
        b: isNum(r.booked_in_cell) ? '<span class="fig">' + num(r.booked_in_cell) + '</span>' : null,
        f: r.thin ? '<span class="thin">THIN</span>' : ''
      };
    });
    var sumAdded = added.reduce(function (a, r) { return a + (r.count || 0); }, 0);
    addedRows.push({
      _cls: 'is-nm', s: '<span class="rid">Outside training support — no PD</span> ' + pv('NOT_MODELLED'),
      n: '<span class="fig">' + num(h.not_modelled_count) + '</span>', i: null, c: null, b: null, f: ''
    });
    addedRows.push({
      _cls: 'is-total', s: 'Total incremental approvals',
      n: '<span class="fig">' + num(sumAdded + h.not_modelled_count) + '</span>',
      i: '', c: '<span class="fig">' + pct(h.blended_bad_rate, 3) + '</span>', b: '', f: ''
    });

    var rejRows = (o.rejected_segments || []).slice(0, 8).map(function (r) {
      return {
        s: '<span class="rid">' + esc(String(r.rule_description || '').replace(/^Approve /, '')) + '</span>',
        n: '<span class="fig">' + num(r.count) + '</span>',
        i: isNum(r.inferred_bad_rate) ? '<span class="fig">' + pct(r.inferred_bad_rate) + '</span>' : null,
        r: '<span class="rid" style="color:var(--muted)">' + esc(r.reason || '') + '</span>'
      };
    });

    var thinCav = caveat('warn', '§9.2',
      '<p><strong><span class="fig">' + pct(o.thin_share_of_evaluated, 1) + '</span> of evaluated swap-ins sit in cells with fewer than ' + num(CFG.model.min_cell_obs) + ' observed booked customers behind them.</strong> Measured against the headline incremental figure instead, it is <span class="fig">' + pct(o.thin_share_of_total, 1) + '</span>. They are different denominators and this page tells you which is which.</p>' +
      '<p>Say this before the room finds it. A recommendation that is 90-odd percent thin is a shortlist for a champion/challenger test, not a strategy to publish on Monday.</p>');

    var naiveW = 100, tW = h.swap_in_count / Math.max(h.swap_in_count, nc.approval_count - base.booked_count) * 100;
    var nW = (nc.approval_count - base.booked_count) / Math.max(h.swap_in_count, nc.approval_count - base.booked_count) * 100;
    var naiveBody =
      '<div style="display:grid;gap:13px">' +
      '<div><div style="display:flex;justify-content:space-between;font-family:var(--mono);font-size:11px;margin-bottom:5px"><span>Targeted segment strategy</span><span class="fig">' + num(h.swap_in_count) + ' at ' + pct(h.blended_bad_rate, 3) + '</span></div>' +
      '<div style="height:26px;background:var(--sunken);border:1px solid var(--line);border-radius:5px;overflow:hidden"><div style="height:100%;inline-size:' + tW.toFixed(1) + '%;background:var(--obs-wash);border-inline-end:2px solid var(--obs)"></div></div></div>' +
      '<div><div style="display:flex;justify-content:space-between;font-family:var(--mono);font-size:11px;margin-bottom:5px"><span>Uniform cutoff drop to ' + nc.naive_cutoff + '</span><span class="fig">' + num(nc.approval_count - base.booked_count) + ' at ' + pct(nc.blended_bad_rate, 3) + '</span></div>' +
      '<div style="height:26px;background:var(--sunken);border:1px solid var(--line);border-radius:5px;overflow:hidden"><div style="height:100%;inline-size:' + nW.toFixed(1) + '%;background:var(--nm-wash);border-inline-end:2px solid var(--nm)"></div></div></div>' +
      '</div>';

    var naiveDelta = (nc.approval_count - base.booked_count) - h.swap_in_count;
    var naiveCav = naiveDelta > 0
      ? caveat('breach', '!', '<p><strong>On this data the blunt instrument wins on volume.</strong> A uniform cutoff drop to ' + nc.naive_cutoff + ' buys <span class="fig">' + num(naiveDelta) + '</span> more approvals at a comparable blended rate. The targeted strategy\'s case is not volume — it is that its approvals are concentrated in cells we can name, size and test, and it stops at a constraint you set rather than at a number someone picked.</p><p>A product that always tells you its own method won is a sales tool. Read the exchange rate and decide.</p>')
      : caveat('obs', '→', '<p>The targeted strategy buys <span class="fig">' + num(-naiveDelta) + '</span> more approvals than a uniform cutoff drop at the same risk. That gap is the commercial case, and it is only credible because everything above it was disclosed.</p>');

    host.innerHTML =
      (onAppetite ? '' : caveat('warn', '!', '<p>Results shown are the shipped run at <span class="fig">' + pct(0.035) + '</span> appetite. This prototype has no Python behind it yet, so a moved constraint does not re-solve — the T2 build calls <span class="code">optimise()</span> live.</p>')) +
      kpis + bind +
      panel('Candidate funnel', funnel, { hint: '§10.2 · where the recommendation came from' }) +
      panel('Segments added', table(
        [{ h: 'Segment', k: 's' }, { h: 'Applicants', k: 'n', num: true }, { h: 'Inferred bad rate', k: 'i', num: true }, { h: 'Cumulative portfolio', k: 'c', num: true }, { h: 'Booked in cell', k: 'b', num: true }, { h: '', k: 'f' }],
        addedRows) + thinCav,
        { hint: 'the column reconciles to the headline on screen', right: dlBtns('segments') }) +
      panel('Segments rejected', table(
        [{ h: 'Segment', k: 's' }, { h: 'Applicants', k: 'n', num: true }, { h: 'Inferred bad rate', k: 'i', num: true }, { h: 'Reason', k: 'r' }],
        rejRows), { hint: 'showing 8 of ' + o.rejected_segments.length }) +
      panel('Against the blunt instrument', naiveBody + naiveCav, { hint: '§10.2 · naive cutoff comparison' }) +
      panel('Sensitivity and breakeven', sensitivityStrip(o.sensitivity, 0.035, CFG.model.inference_penalty) +
        '<p class="note" style="margin-top:10px">Breakeven penalty is <span class="fig">' + dec(o.breakeven_penalty, 4) + '</span> against an operating penalty of <span class="fig">' + dec(CFG.model.inference_penalty, 2) + '</span>.</p>' +
        caveat('', '?', '<p><strong>That looks like one rounding error from a breach. It is structural, not alarming.</strong> The greedy adds segments until the constraint binds, so whenever the binding constraint is <span class="rid">bad_rate</span> the breakeven necessarily lands just above the operating penalty. It carries information only when the run is slot-bound. Read the strip, not the breakeven.</p>'),
        { hint: '§9.3' }) +
      panel('Export', '<div style="display:flex;gap:9px;flex-wrap:wrap"><button class="btn ghost sm" data-dl="strategy" data-fmt="json">Download strategy JSON</button><button class="btn ghost sm" data-dl="decision-memo">Decision memo (PDF)</button><button class="btn sm" id="submitmc">Submit for maker-checker</button></div>' +
        '<p class="note" style="margin-top:10px">The exported strategy object is the same one the champion/challenger allocator consumes, and the same one the CLI accepts. The UI is a view, not the product.</p>', { hint: '§10.5 · §26.2' });
    bindTips(host);
    var sb = document.getElementById('submitmc');
    if (sb) sb.addEventListener('click', function () {
      S.mcStage = 1;
      pushAudit('Submitted strategy v4.3.0-draft for approval', 'MAKER.SUBMIT');
      go('governance');
    });
  }

  /* --------------------------------------------------------- 06 portfolio */
  function pagePortfolio() {
    var p = F.portfolio, t = p.trade;
    var head = pageHead('Stage 06 · Decide', 'The page with no inference in it',
      'Every figure here is observed. Which of the customers you already approved are actually costing you, and would swapping them for the optimiser\'s candidates leave you better off?');

    var diag = (p.diagnostic || []).map(function (r) {
      return {
        s: '<span class="rid">' + esc(r.segment.replace(/ \| /g, ' · ')) + '</span>',
        n: '<span class="fig">' + num(r.count) + '</span>',
        b: '<span class="fig">' + num(r.bads) + '</span>',
        r: '<span class="fig">' + pct(r.observed_bad_rate) + '</span>',
        ci: '<span class="fig">' + pct(r.ci_lower, 2) + ' – ' + pct(r.ci_upper, 2) + '</span>',
        sh: '<span class="fig">' + pct(r.share_of_bads, 1) + '</span>',
        cu: isNum(r.cumulative_bads_share) ? '<span class="fig">' + pct(r.cumulative_bads_share, 1) + '</span>' : null
      };
    });

    var elig = (p.eligible || []).map(function (r) {
      return {
        s: '<span class="rid">' + esc(r.segment.replace(/ \| /g, ' · ')) + '</span>',
        n: '<span class="fig">' + num(r.count) + '</span>',
        r: '<span class="fig">' + pct(r.observed_bad_rate) + '</span> ' + pv('OBSERVED'),
        ci: '<span class="fig">' + pct(r.ci_lower, 2) + ' – ' + pct(r.ci_upper, 2) + '</span>',
        e: '<span class="fig">' + num(r.excess_bads) + '</span>'
      };
    });

    var tradeTiles = tiles([
      { k: 'Approvals lost', v: '<span class="fig">' + signed(-t.approvals_lost) + '</span>', d: 'declining ' + t.n_worst_segments_declined + ' observed-worse segments' },
      { k: 'Approvals gained', v: '<span class="fig">' + signed(t.approvals_gained) + '</span>', d: 'optimiser candidates ' + pv('INFERRED') },
      { k: 'Net approvals', tone: t.net_approval_delta < 0 ? 'breach' : 'obs', v: '<span class="fig">' + signed(t.net_approval_delta) + '</span>', d: 'rate <span class="fig">' + pct(t.net_approval_rate) + '</span> from <span class="fig">' + pct(t.baseline_approval_rate) + '</span>' },
      { k: 'Net blended bad rate', pv: 'BLENDED', v: '<span class="fig">' + pct(t.net_blended_bad_rate, 3) + '</span>', d: 'from <span class="fig">' + pct(t.baseline_observed_bad_rate) + '</span> ' + pv('OBSERVED') }
    ], 4);

    var tradeCav = t.constraints_differ
      ? caveat('breach', '≠', '<p><strong>The two sides bind on different constraints — <span class="rid">' + esc(t.binding_constraint) + '</span> here against <span class="rid">' + esc(t.base_binding_constraint) + '</span> on the optimiser run — so the delta between them is withheld.</strong> A labelled wrong number still gets quoted in a meeting.</p><p>Read the trade on its own terms instead: the segments worth declining are large and sit above 700; their replacements are smaller and sit below the cutoff. The exchange rate is <span class="fig">' + num(t.approvals_lost) + '</span> out for <span class="fig">' + num(t.approvals_gained) + '</span> in.</p>')
      : caveat('obs', '→', '<p>Both sides bind on <span class="rid">' + esc(t.binding_constraint) + '</span>, so the delta is comparable.</p>');

    var floorNote = caveat('', '§10.3', '<p>Segments below the <span class="fig">' + num(p.min_segment_size) + '</span>-customer floor are excluded from this ranking. A three-customer segment at 66.7% is noise, not a finding. Ranking is by <strong>contribution to total bads</strong>; rate-descending is available as a secondary sort and is never the default, because it surfaces exactly the segments too small to act on.</p>');

    return head +
      panel('Currently approved segments, ranked by contribution to bads', table(
        [{ h: 'Segment', k: 's' }, { h: 'Customers', k: 'n', num: true }, { h: 'Bads', k: 'b', num: true }, { h: 'Bad rate ' + pv('OBSERVED'), k: 'r', num: true }, { h: '95% CI', k: 'ci', num: true }, { h: 'Share of bads', k: 'sh', num: true }, { h: 'Cumulative', k: 'cu', num: true }],
        diag) + floorNote,
        { hint: 'portfolio rate ' + pct(p.portfolio_rate) + ' ' + '· all OBSERVED', right: dlBtns('diagnostic') }) +
      panel('Eligible to decline', table(
        [{ h: 'Segment', k: 's' }, { h: 'Customers', k: 'n', num: true }, { h: 'Bad rate', k: 'r', num: true }, { h: '95% CI', k: 'ci', num: true }, { h: 'Excess bads', k: 'e', num: true }],
        elig) +
        '<p class="note" style="margin-top:11px">A <em>different</em> list from the one above: only segments whose rate <strong>and</strong> whose confidence lower bound both exceed the portfolio rate of <span class="fig">' + pct(p.portfolio_rate) + '</span>, ranked by excess bads. Being at the top of the diagnostic does not earn a place here.</p>',
        { hint: 'rate AND CI lower bound above portfolio' }) +
      panel('The combined trade', tradeTiles + tradeCav, { hint: '§10.3 · swap-out plus swap-in' });
  }

  /* ---------------------------------------------------------------- 07 cc */
  function pageCC() {
    var head = pageHead('Stage 07 · Operate', 'Turn a recommendation into evidence',
      'The optimiser produced a shortlist that is 92% thin. The only honest way to promote it is to route a controlled share of traffic through it and measure what actually happens.');

    var alloc = S.ccAllocation;
    var champSeries = [2.81, 2.86, 2.84, 2.88, 2.85, 2.87, 2.86, 2.86];
    var chalSeries = [4.9, 4.2, 3.9, 3.72, 3.61, 3.55, 3.51, 3.48];
    var elapsedDays = S.ccLive ? 62 : 0;
    var chalN = Math.round(F.meta.n_rows * (alloc / 100) * 0.17);
    var champN = Math.round(F.meta.n_rows * ((100 - alloc) / 100) * 0.17);

    var ctl =
      '<div class="controls">' +
      '<div class="ctrl"><div class="row"><label>Challenger traffic allocation</label><span class="val"><span class="fig" id="allocval">' + alloc + '%</span></span></div>' +
      '<input type="range" id="alloc" min="1" max="50" step="1" value="' + alloc + '">' +
      '<div class="scale"><span>1%</span><span>50%</span></div></div>' +
      '<div style="display:grid;gap:5px;font-family:var(--mono);font-size:11px;color:var(--muted)">' +
      '<div style="display:flex;justify-content:space-between"><span>randomisation</span><span class="fig">hash(application_id)</span></div>' +
      '<div style="display:flex;justify-content:space-between"><span>minimum runtime</span><span class="fig">performance window</span></div>' +
      '<div style="display:flex;justify-content:space-between"><span>strategy under test</span><span class="fig">v4.3.0-draft</span></div></div>' +
      '<button class="btn" id="cctoggle">' + (S.ccLive ? 'Pause experiment' : 'Start experiment') + '</button>' +
      '<p class="note" style="font-size:12px">Allocation is a maker-checker action in the deployable build: an analyst proposes it, a risk owner approves it, and the audit log records both.</p>' +
      '</div>';

    var arms = S.ccLive
      ? '<div class="arms">' +
      '<div class="arm is-champ"><div class="armhead"><b>Champion — current strategy v4.2.1</b>' + pv('OBSERVED') + '</div>' +
      '<div class="armgrid">' +
      '<div class="a"><div class="k">Applications</div><div class="v">' + num(champN) + '</div></div>' +
      '<div class="a"><div class="k">Approval rate</div><div class="v">' + pct(0.3986) + '</div></div>' +
      '<div class="a"><div class="k">Bad rate to date</div><div class="v">' + pct(0.0286) + '</div></div>' +
      '<div class="a"><div class="k">Trend</div><div class="v">' + sparkline(champSeries, 90, 26, 'var(--obs)') + '</div></div>' +
      '</div></div>' +
      '<div class="arm is-chal"><div class="armhead"><b>Challenger — optimised strategy v4.3.0-draft</b>' + pv('OBSERVED') + '</div>' +
      '<div class="armgrid">' +
      '<div class="a"><div class="k">Applications</div><div class="v">' + num(chalN) + '</div></div>' +
      '<div class="a"><div class="k">Approval rate</div><div class="v">' + pct(0.512) + '</div></div>' +
      '<div class="a"><div class="k">Bad rate to date</div><div class="v">' + pct(0.0348) + '</div></div>' +
      '<div class="a"><div class="k">Trend</div><div class="v">' + sparkline(chalSeries, 90, 26, 'var(--inf)') + '</div></div>' +
      '</div></div></div>' +
      caveat('warn', '!', '<p><strong>Day ' + elapsedDays + ' of a performance window that is not yet complete.</strong> The challenger bad rate is still maturing — early vintages under-report — so the two arms are not yet comparable, and this screen says so rather than letting the gap be read as a result.</p>') +
      caveat('obs', '→', '<p>What the experiment is actually worth: the challenger\'s approvals were <span class="fig">' + pct(F.optimiser.thin_share_of_total, 1) + '</span> THIN when they were a recommendation. Every one that books and seasons converts an ' + pv('INFERRED') + ' cell into an ' + pv('OBSERVED') + ' one, and the next optimiser run is entitled to say more.</p>')
      : '<p class="note">No experiment is running. Allocate traffic and start one to convert the optimiser\'s inferred cells into observed performance. Nothing else in this product can do that — the model cannot learn about a population the strategy never books.</p>' +
      caveat('', '§27', '<p>This is the loop that closes the vision: <strong>population → opportunity → objective → simulate → optimise → explain → champion/challenger → measure → learn</strong>. Every other screen is one node on it.</p>');

    return head +
      '<div class="cols2" style="grid-template-columns:minmax(280px,320px) minmax(0,1fr)">' +
      '<div>' + panel('Experiment design', ctl, { hint: '§27' }) + '</div>' +
      '<div>' + panel(S.ccLive ? 'Live arms' : 'Arms', arms, { hint: S.ccLive ? 'day ' + elapsedDays : 'not started' }) + '</div></div>';
  }

  /* -------------------------------------------------------- 08 governance */
  function pageGovernance() {
    var head = pageHead('Stage 08 · Operate', 'Nothing changes without two people and a record',
      'A strategy is a versioned artefact. It is proposed by one person, approved by another, promoted through environments, and every step of that is recoverable from the audit log.');

    var stages = [
      { t: 'Drafted', w: 'N. Al-Rashid · Risk Analyst (Maker)', d: 'Optimiser run at bad_rate ≤ 3.50%, 10 segments added' },
      { t: 'Submitted for approval', w: 'N. Al-Rashid · Risk Analyst (Maker)', d: 'Decision memo attached · 17 rejected segments included' },
      { t: 'Approved by checker', w: 'Awaiting · Head of Credit Risk (Checker)', d: 'Maker cannot approve their own change (§20.3)' },
      { t: 'Promoted to UAT', w: 'Release Manager · automated', d: 'Config promoted, engine version pinned' },
      { t: 'Promoted to PROD', w: 'Awaiting sign-off', d: 'Requires regulatory-reference field when a regulatory rule moved' }
    ];
    var mc = '<div>' + stages.map(function (s, i) {
      var cls = i < S.mcStage ? 'is-done' : (i === S.mcStage ? 'is-active' : '');
      return '<div class="mcstep ' + cls + '"><div class="bub">' + (i < S.mcStage ? '✓' : (i + 1)) + '</div>' +
        '<div class="mcb"><b>' + esc(s.t) + '</b><p>' + esc(s.d) + '</p><div class="who2">' + esc(s.w) + '</div></div></div>';
    }).join('') + '</div>' +
      (S.mcStage === 1
        ? '<div style="display:flex;gap:8px;margin-top:6px;flex-wrap:wrap"><button class="btn sm" id="mcapprove">Approve as checker</button><button class="btn ghost sm" id="mcreject">Return to maker</button></div>' +
        caveat('warn', '!', '<p>You are signed in as the <strong>maker</strong>. In the deployable build these controls are not rendered for you at all — this prototype shows them so the flow can be demonstrated in one session.</p>')
        : (S.mcStage === 0 ? '<p class="note" style="margin-top:8px">No change is in flight. Run the optimiser and submit its strategy to start one.</p>' : ''));

    var diff =
      '<div class="diff">' +
      '<div class="dl same"><span>&nbsp;</span><span>R1_AGE      min_age=21 max_age=60      mandatory</span></div>' +
      '<div class="dl same"><span>&nbsp;</span><span>R2_FRAUD                              mandatory</span></div>' +
      '<div class="dl same"><span>&nbsp;</span><span>R3_THIN_FILE   min_vintage=6</span></div>' +
      '<div class="dl same"><span>&nbsp;</span><span>R4_BUREAU_HIST dpd_lt=60 max_enquiries=6</span></div>' +
      '<div class="dl same"><span>&nbsp;</span><span>R5_SCORE       cutoff=700</span></div>' +
      '<div class="dl same"><span>&nbsp;</span><span>R6_FOIR        cap=0.50   regulatory</span></div>' +
      '<div class="dl add"><span>+</span><span>override  score 680–699 · foir 0.00–0.35 · salaried     relaxes R5,R6</span></div>' +
      '<div class="dl add"><span>+</span><span>override  score 680–699 · foir 0.35–0.50 · salaried     relaxes R5,R6</span></div>' +
      '<div class="dl add"><span>+</span><span>override  score 660–679 · foir 0.00–0.35 · salaried     relaxes R5,R6</span></div>' +
      '<div class="dl add"><span>+</span><span>… 7 further segment overrides</span></div>' +
      '</div>' +
      '<p class="note" style="margin-top:11px">Configuration is separated from the engine (§23.5), so this diff is a data change and not a release. The engine version it was validated against is pinned alongside it.</p>';

    var envs = table(
      [{ h: 'Environment', k: 'e' }, { h: 'Strategy', k: 's' }, { h: 'Engine', k: 'g' }, { h: 'Promoted', k: 'p' }, { h: '', k: 'a' }],
      [
        { e: '<span class="chip is-static env-dev" style="height:22px"><span class="dot"></span>DEV</span>', s: '<span class="fig">v4.3.0-draft</span>', g: '<span class="fig">2.4.1</span>', p: '<span class="fig">today 09:14</span>', a: '' },
        { e: '<span class="chip is-static env-uat" style="height:22px"><span class="dot"></span>UAT</span>', s: '<span class="fig">v4.2.1</span>', g: '<span class="fig">2.4.1</span>', p: '<span class="fig">2026-09-11</span>', a: '<button class="btn ghost sm">Compare</button>' },
        { e: '<span class="chip is-static" style="height:22px"><span class="dot"></span>PROD</span>', s: '<span class="fig">v4.2.1</span>', g: '<span class="fig">2.3.8</span>', p: '<span class="fig">2026-08-29</span>', a: '<button class="btn ghost sm">Roll back</button>' }
      ]);

    return head +
      '<div class="cols2"><div>' +
      panel('Change in flight', mc, { hint: '§20.3 · maker-checker' }) +
      panel('Environments', envs, { hint: '§23.3 · promotion path' }) +
      '</div><div>' +
      panel('Strategy diff — v4.2.1 → v4.3.0-draft', diff, { hint: '§23.2' }) +
      panel('Audit trail', '<div class="feed" id="auditfeed"></div>', { hint: '§20.4 · append-only, tenant-scoped', right: dlBtns('audit') }) +
      '</div></div>';
  }

  /* --------------------------------------------------------- 09 validation */
  function pageValidation() {
    var v = F.validation;
    var head = pageHead('Stage 09 · Assure', 'Marking our own homework',
      'This screen exists only because the data is synthetic. It has no counterpart on a real book — which is exactly why the provenance labelling on every other screen is there.');

    if (!v) {
      return head + panel('Oracle', caveat('', '—', '<p>No ground-truth column is present in this dataset, so no oracle comparison can be made. On real data this is the expected state, and every other screen in the product is built to be read without it.</p>'), { hint: 'unavailable' });
    }

    var s = v.strategy;
    var kpis = tiles([
      { k: 'We reported', pv: 'BLENDED', v: '<span class="fig">' + pct(s.blended_bad_rate_estimate, 3) + '</span>', d: 'blended, excluding NOT_MODELLED' },
      { k: 'Ground truth', pv: 'OBSERVED', tone: 'obs', v: '<span class="fig">' + pct(s.true_bad_rate_modelled, 3) + '</span>', d: 'same population, true outcome' },
      { k: 'Estimation error', tone: s.estimation_error > 0 ? 'inf' : '', v: '<span class="fig">' + (s.estimation_error > 0 ? '+' : '') + pct(s.estimation_error, 3) + '</span>', d: s.estimation_error > 0 ? 'we were conservative' : 'we were optimistic' },
      { k: 'True rate, all approvals', v: '<span class="fig">' + pct(s.true_bad_rate_all_approvals, 3) + '</span>', d: 'including the ' + num(s.not_modelled_count) + ' we refused to price' }
    ], 4);

    var rows = table(
      [{ h: 'Quantity', k: 'q' }, { h: 'Reported', k: 'r', num: true }, { h: 'True', k: 't', num: true }, { h: 'Gap', k: 'g', num: true }],
      [
        { q: 'Swap-in bad rate', r: '<span class="fig">' + pct(s.inferred_swap_in_rate) + '</span> ' + pv('INFERRED'), t: '<span class="fig">' + pct(s.swap_in_true_bad_rate) + '</span>', g: '<span class="fig">' + pct(s.inferred_swap_in_rate - s.swap_in_true_bad_rate, 3) + '</span>' },
        { q: 'Portfolio blended', r: '<span class="fig">' + pct(s.blended_bad_rate_estimate, 3) + '</span>', t: '<span class="fig">' + pct(s.true_bad_rate_modelled, 3) + '</span>', g: '<span class="fig">' + pct(s.estimation_error, 3) + '</span>' },
        { _cls: 'is-nm', q: 'NOT_MODELLED approvals — we published no rate', r: null, t: '<span class="fig">' + pct(s.not_modelled_true_bad_rate) + '</span>', g: null }
      ]);

    var nmCav = caveat('warn', '!', '<p><strong>The applicants we refused to price were genuinely worse.</strong> Their true bad rate is <span class="fig">' + pct(s.not_modelled_true_bad_rate) + '</span> against <span class="fig">' + pct(s.true_bad_rate_modelled, 3) + '</span> for the population we did price.</p><p>That is the argument for the whole design. A tool that extrapolates its model into unsupported territory would have quoted a confident number for those <span class="fig">' + num(s.not_modelled_count) + '</span> people and been badly wrong. This one declined to, and told you how many it was declining to price.</p>');

    var anchorRows = (v.anchor || []).map(function (r) {
      return {
        c: '<span class="rid">' + esc(String(r.cell).replace(/ \| /g, ' · ')) + '</span>',
        o: '<span class="fig">' + pct(r.observed_bad_rate) + '</span>',
        p: '<span class="fig">' + pct(r.mean_model_pd) + '</span>',
        i: '<span class="fig">' + pct(r.inferred_pd) + '</span>',
        r: '<span class="fig">' + dec(r.implied_penalty, 3) + '</span>',
        s: r.implied_penalty < CFG.model.inference_penalty
          ? '<span class="pv pv-OBSERVED">covered</span>'
          : '<span class="pv pv-INFERRED">above operating penalty</span>'
      };
    });

    return head +
      caveat('breach', '⚠', '<p><strong>Synthetic data only.</strong> ' + esc(s.disclaimer) + ' Do not present any figure on this screen as evidence about a real portfolio.</p>') +
      kpis +
      panel('Predicted versus true', rows + nmCav, { hint: '§10.4 · optimiser strategy' }) +
      panel('Near-cutoff anchor, cell by cell', table(
        [{ h: 'Cell', k: 'c' }, { h: 'Observed', k: 'o', num: true }, { h: 'Model PD', k: 'p', num: true }, { h: 'Inferred', k: 'i', num: true }, { h: 'Implied ×', k: 'r', num: true }, { h: 'vs operating penalty', k: 's' }],
        anchorRows) +
        caveat('warn', 'GAP', '<p><strong>The oracle comparison for these cells is not yet computed.</strong> <span class="code">validate_near_cutoff_oracle()</span> returns the reported quantities but no ground-truth column, so the \u201cdid ×' + dec(CFG.model.inference_penalty, 2) + ' actually cover it?\u201d test that §10.4 calls for is not being run per cell. The portfolio-level oracle above is real; this table is not yet a validation.</p><p>Shown as a gap rather than as empty cells, because an empty cell in a validation table is the worst possible thing to put in front of a regulator.</p>'),
        { hint: '§10.4 · reported quantities only' });
  }

  /* ---------------------------------------------------------- 10 roadmap */
  function pageRoadmap() {
    var head = pageHead('Stage 10 · Assure', 'What ships, and when',
      'Part A is built and running on a million rows. Part B is specified, dated and sequenced. The line between the two is drawn here rather than in the room.');

    var rows = [
      { d: '2026-09-22', k: 'T1 · DEMO', t: 'Demo build', s: 'shipped', p: 'Engine, provenance labelling, waterfall, risk model with support gating, what-if, optimiser, swap-out, oracle validation. 123 tests. This prototype is its front end.' },
      { d: '2026-10-08', k: 'T2 · DEPLOY', t: 'Deployable build', s: 'spec', p: 'Served front end over an authenticated API, identity and RBAC, maker-checker, audit trail, tenant isolation, regulatory rule class with a locked SAMA DBR parameter, field mapping from the client schema.' },
      { d: '2026-10', k: 'ON-PREM', t: 'On-premise install', s: 'spec', p: 'Air-gapped deployment, offline signed licence, no outbound telemetry or heartbeat. Data residency inside the Kingdom; PDPL and NCA ECC controls.' },
      { d: 'post-T2', k: 'PLATFORM', t: 'Generic decision platform', s: 'spec', p: 'The same engine pointed at existing-book actions: limit management, collections treatment, retention, pricing. Domain packs rather than a rebuild.' }
    ];
    var rm = '<div class="roadmap">' + rows.map(function (r) {
      return '<div class="rmrow"><div class="rd">' + esc(r.d) + '<span>' + esc(r.k) + '</span></div>' +
        '<div class="rb"><b>' + esc(r.t) + '<span class="st-pill ' + r.s + '">' + (r.s === 'shipped' ? 'SHIPPED' : 'SPECIFIED') + '</span></b><p>' + esc(r.p) + '</p></div></div>';
    }).join('') + '</div>';

    var honest = caveat('', '→', '<p><strong>What this prototype is.</strong> A front end over a precomputed export of the real engine. Every number on every screen came out of <span class="code">ui/export_fixture.py</span>, which calls the same functions the CLIs call — so the figures are real, and the interactions that re-solve (the what-if grid) are real within the grid that was exported.</p>' +
      '<p>What it is not: it has no Python behind it yet. Moving the optimiser\'s constraint does not re-solve, and the governance and champion/challenger screens are designed rather than built. Those are marked on the screens themselves, not only here.</p>');

    var qs = [
      ['Can it recommend breaching a regulatory limit?', 'Mandatory rules — age, fraud — cannot be bypassed by any path, and there is a test that asserts a segment override cannot reach them. The regulatory rule class, which additionally locks the <em>parameter value</em>, is specified in §16.3 and lands at T2. Today R6_FOIR is still modelled as commercially relaxable, and the screens say so.'],
      ['How do you know the declined customers would have performed like that?', 'We do not, and the product says so on every screen. There is a conservatism penalty, a sensitivity strip at four penalties, a breakeven figure, and 92% of the recommendation is flagged THIN. It is a shortlist for a champion/challenger test.'],
      ['Will this work on our data?', 'The loader validates a fixed schema, and a dataset with those columns drops straight in. Mapping from SIMAH field names is configuration rather than code (§22.3). The honest caveat is that a data-readiness report comes first and usually finds something.'],
      ['Why not just lower the cutoff?', 'On this data, a uniform drop to 678 actually buys more volume at a comparable rate — and Stage 05 shows you that rather than hiding it. The case for the targeted strategy is that its approvals sit in cells you can name, size and test.']
    ];
    var qa = '<div style="display:grid;gap:14px">' + qs.map(function (q) {
      return '<div><b style="font-size:13px">' + esc(q[0]) + '</b><p class="note" style="margin-top:4px">' + q[1] + '</p></div>';
    }).join('') + '</div>';

    return head + panel('Delivery', rm, { hint: '§17' }) +
      panel('Status of this prototype', honest, { hint: 'read before presenting' }) +
      panel('Questions you will be asked', qa, { hint: 'and the honest answers' });
  }

  /* ============================================================ page head */
  function pageHead(eyebrow, title, sub) {
    return '<header class="pagehead"><div class="eyebrow">' + esc(eyebrow) + '</div>' +
      '<h1>' + esc(title) + '</h1><p class="sub">' + esc(sub) + '</p></header>';
  }

  /* ============================================================== ledger ==
     The right rail is the product's thesis turned into furniture: for
     whatever is on screen, how much of it did we observe, and what must the
     reader not conclude.
     ===================================================================== */
  var AUDIT = [
    { t: '09:14', m: '<b>Optimiser run</b> at bad_rate ≤ 3.50%', s: 'n.alrashid · STRATEGY.OPTIMISE' },
    { t: '09:02', m: '<b>Dataset snapshot</b> pinned — applications_2024', s: 'system · DATA.SNAPSHOT' },
    { t: '08:47', m: '<b>Signed in</b> from 10.24.x.x', s: 'n.alrashid · AUTH.LOGIN' },
    { t: 'Sep 11', m: '<b>Strategy v4.2.1</b> promoted to UAT', s: 'f.otaibi · CONFIG.PROMOTE' }
  ];
  function pushAudit(msg, code) {
    var d = new Date();
    AUDIT.unshift({ t: String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'), m: '<b>' + esc(msg) + '</b>', s: 'n.alrashid · ' + code });
  }
  function auditHTML(limit) {
    return AUDIT.slice(0, limit || AUDIT.length).map(function (e) {
      return '<div class="ev"><div class="t">' + esc(e.t) + '</div><div class="m">' + e.m + '<span>' + esc(e.s) + '</span></div></div>';
    }).join('');
  }

  function ledgerFor(page) {
    var o = F.overview, blocks = [];
    var sc = page === 'whatif' ? scenario(S.cutoff, S.cap, S.r3, S.r4) : null;
    var h = F.optimiser.headline;

    function evidenceBlock(retained, inferred, nm, label) {
      return '<div class="ledgerblock"><h3>Evidence composition</h3>' +
        '<p class="lead">' + label + '</p>' +
        provenanceBar([
          { k: 'obs', l: 'Observed', v: retained },
          { k: 'inf', l: 'Inferred', v: inferred },
          { k: 'nm', l: 'Not modelled', v: nm }
        ]) + '</div>';
    }

    if (page === 'whatif' && sc) {
      blocks.push(evidenceBlock(sc.approval_count - sc.swap_in_count - sc.not_modelled_count,
        sc.swap_in_count - sc.not_modelled_count, sc.not_modelled_count,
        'Of ' + num(sc.approval_count) + ' approvals in this scenario.'));
      blocks.push('<div class="ledgerblock"><h3>Risk appetite</h3>' + gauge(sc.blended_bad_rate, S.capThreshold, 'blended bad rate ' + pct(sc.blended_bad_rate)) + '</div>');
    } else if (page === 'optimiser' && S.optRun) {
      blocks.push(evidenceBlock(h.approval_count - h.swap_in_count - h.not_modelled_count,
        h.swap_in_count - h.not_modelled_count, h.not_modelled_count,
        'Of ' + num(h.approval_count) + ' approvals in the recommendation.'));
      blocks.push('<div class="ledgerblock"><h3>Risk appetite</h3>' + gauge(h.blended_bad_rate, 0.035, 'blended bad rate ' + pct(h.blended_bad_rate, 3)) +
        '<p class="lead" style="margin-top:9px">Binding constraint <span class="fig" style="color:var(--ink)">' + esc(F.optimiser.binding_constraint) + '</span>. The budget is fully spent.</p></div>');
      blocks.push('<div class="ledgerblock"><h3>Thin-cell exposure</h3><p class="lead">' + pct(F.optimiser.thin_share_of_total, 1) +
        ' of the headline incremental approvals sit in cells with fewer than ' + num(CFG.model.min_cell_obs) + ' booked customers behind them.</p></div>');
    } else if (page === 'portfolio' || page === 'baseline' || page === 'waterfall') {
      blocks.push(evidenceBlock(o.booked_count, 0, 0, 'Every figure on this screen is observed. Nothing here is modelled or inferred.'));
    } else if (page === 'model') {
      var sr = (F.model.support_ranges || []).filter(function (r) { return r.feature === 'bureau_score'; })[0] || {};
      blocks.push('<div class="ledgerblock"><h3>Model reach</h3>' +
        provenanceBar([
          { k: 'obs', l: 'Inside support', v: sr.applications_inside || 0 },
          { k: 'nm', l: 'Outside support', v: sr.applications_outside || 0 }
        ]) + '<p class="lead" style="margin-top:9px">On bureau_score alone. An applicant outside support receives no PD.</p></div>');
    }

    // caveats that apply to the current screen
    var cav = {
      baseline: ['Approval counts are the historical book, which includes ' + num(o.reproduction.n_manual_overrides) + ' manual overrides.'],
      waterfall: ['Every applicant is attributed to the first rule they failed, not to every rule they failed.'],
      model: ['The implied penalty is a lower bound, not a selection estimate.', 'AUC ' + dec(F.model.metrics.auc, 3) + ' is modest by design — the model must stay explainable.'],
      whatif: ['NOT_MODELLED approvals are counted as approvals and excluded from every rate.', 'Compare against the model-basis baseline, not the observed one.'],
      optimiser: ['This prototype serves the shipped run; a moved constraint does not re-solve.', 'A naive cutoff drop buys more volume on this data. Stage 05 shows it.'],
      portfolio: ['The combined trade is net negative on this data. That is a finding, not a bug.'],
      cc: ['Early vintages under-report. The arms are not yet comparable.'],
      governance: ['Maker-checker controls are rendered for the maker here only so the flow can be demonstrated.'],
      validation: ['Synthetic data only. No counterpart exists on a real book.'],
      roadmap: ['Part B is specified and dated, not built.']
    }[page] || [];

    if (cav.length) {
      blocks.push('<div class="ledgerblock"><h3>Do not conclude</h3><div style="display:grid;gap:8px">' +
        cav.map(function (c) { return '<p class="lead" style="margin:0">' + c + '</p>'; }).join('') + '</div></div>');
    }

    blocks.push('<div class="ledgerblock"><h3>Provenance key</h3><div style="display:grid;gap:6px">' +
      [['OBSERVED', 'Actual outcome of a booked customer'],
      ['PREDICTED', 'Model PD for a booked customer'],
      ['INFERRED', 'Model PD × conservatism penalty, for a decline'],
      ['NOT_MODELLED', 'Outside training support — no PD exists']].map(function (p) {
        return '<div style="display:flex;gap:8px;align-items:flex-start">' + pv(p[0]) +
          '<span style="font-family:var(--prose);font-size:11.5px;color:var(--muted);line-height:1.4">' + esc(p[1]) + '</span></div>';
      }).join('') + '</div></div>');

    blocks.push('<div class="ledgerblock"><h3>Recent activity</h3><div class="feed">' + auditHTML(4) + '</div></div>');

    return '<h3 style="font-size:10.5px;margin-bottom:8px">' + esc(T('Evidence ledger')) + '</h3>' + blocks.join('');
  }

  function renderLedger() {
    var l = document.getElementById('ledger');
    l.innerHTML = ledgerFor(S.page);
    bindTips(l);
  }

  /* ================================================================== nav */
  function renderNav() {
    var groups = [], seen = {};
    PAGES.forEach(function (p) { if (!seen[p.g]) { seen[p.g] = []; groups.push(p.g); } seen[p.g].push(p); });
    document.getElementById('rail').innerHTML = groups.map(function (g) {
      return '<div class="railgroup"><h4>' + esc(T(g)) + '</h4>' + seen[g].map(function (p) {
        return '<button class="navitem" data-page="' + p.id + '"' + (S.page === p.id ? ' aria-current="page"' : '') + '>' +
          '<span class="n">' + p.n + '</span><span class="lbl">' + esc(T(p.t)) + '</span>' +
          (p.flag ? '<span class="flag ' + p.flag + '"></span>' : '') + '</button>';
      }).join('') + '</div>';
    }).join('');
    document.getElementById('rail').querySelectorAll('[data-page]').forEach(function (b) {
      b.addEventListener('click', function () { go(b.getAttribute('data-page')); closeOverlays(); });
    });
  }

  var RENDER = {
    baseline: pageBaseline, waterfall: pageWaterfall, model: pageModel,
    whatif: pageWhatIf, optimiser: pageOptimiser, portfolio: pagePortfolio,
    cc: pageCC, governance: pageGovernance, validation: pageValidation, roadmap: pageRoadmap
  };

  function go(page) {
    S.page = page;
    var wrap = document.getElementById('canvaswrap');
    wrap.innerHTML = RENDER[page]();
    document.getElementById('canvas').scrollTop = 0;
    renderNav();
    renderLedger();
    wire(wrap);
    bindTips(wrap);
    if (page === 'whatif') renderWhatIf();
    if (page === 'optimiser' && S.optRun) renderOptimiser();
    if (page === 'governance') { var f = document.getElementById('auditfeed'); if (f) f.innerHTML = auditHTML(); }
  }

  /* ============================================================== wiring */
  function wire(root) {
    var cut = root.querySelector('#cutoff');
    if (cut) {
      var capr = root.querySelector('#capr');
      var sync = function () {
        S.cutoff = F.grid.cutoffs[+cut.value];
        S.cap = F.grid.foir_caps[+capr.value];
        S.r3 = root.querySelector('#r3').checked ? 1 : 0;
        S.r4 = root.querySelector('#r4').checked ? 1 : 0;
        root.querySelector('#cutval').textContent = S.cutoff;
        root.querySelector('#capval').textContent = S.cap.toFixed(2);
        renderWhatIf();
        renderLedger();
      };
      cut.addEventListener('input', sync);
      capr.addEventListener('input', sync);
      root.querySelector('#r3').addEventListener('change', sync);
      root.querySelector('#r4').addEventListener('change', sync);
      root.querySelector('#resetwi').addEventListener('click', function () {
        cut.value = F.grid.cutoffs.indexOf(700);
        capr.value = F.grid.foir_caps.indexOf(0.5);
        root.querySelector('#r3').checked = true;
        root.querySelector('#r4').checked = true;
        sync();
      });
    }

    var capSlider = root.querySelector('#capslider');
    if (capSlider) {
      capSlider.addEventListener('input', function () {
        S.capThreshold = +capSlider.value / 10000;
        root.querySelector('#capshow').textContent = pct(S.capThreshold);
        renderLedger();
      });
    }
    var run = root.querySelector('#runopt');
    if (run) run.addEventListener('click', runOptimiser);

    var alloc = root.querySelector('#alloc');
    if (alloc) {
      alloc.addEventListener('input', function () {
        S.ccAllocation = +alloc.value;
        root.querySelector('#allocval').textContent = S.ccAllocation + '%';
      });
      alloc.addEventListener('change', function () { if (S.ccLive) go('cc'); });
    }
    var cct = root.querySelector('#cctoggle');
    if (cct) cct.addEventListener('click', function () {
      S.ccLive = !S.ccLive;
      pushAudit(S.ccLive ? 'Started challenger at ' + S.ccAllocation + '% allocation' : 'Paused challenger experiment', 'EXPERIMENT.' + (S.ccLive ? 'START' : 'PAUSE'));
      go('cc');
    });

    var app = root.querySelector('#mcapprove');
    if (app) app.addEventListener('click', function () {
      S.mcStage = 3;
      pushAudit('Approved strategy v4.3.0-draft as checker', 'CHECKER.APPROVE');
      go('governance');
    });
    var rej = root.querySelector('#mcreject');
    if (rej) rej.addEventListener('click', function () {
      S.mcStage = 0;
      pushAudit('Returned strategy v4.3.0-draft to maker', 'CHECKER.REJECT');
      go('governance');
    });

    root.querySelectorAll('[data-dl]').forEach(function (b) {
      b.addEventListener('click', function () {
        var was = b.textContent;
        b.textContent = 'Not in prototype';
        setTimeout(function () { b.textContent = was; }, 1400);
      });
    });
    root.querySelectorAll('#loadwi, #savewi').forEach(function (b) {
      b.addEventListener('click', function () {
        var was = b.textContent;
        b.textContent = 'Same JSON the CLI accepts';
        setTimeout(function () { b.textContent = was; }, 1600);
      });
    });
  }

  /* ============================================================== chrome */
  function applyTheme() {
    if (S.theme) document.documentElement.setAttribute('data-theme', S.theme);
    else document.documentElement.removeAttribute('data-theme');
  }
  function closeOverlays() {
    document.getElementById('rail').classList.remove('is-open');
    document.getElementById('ledger').classList.remove('is-open');
    document.getElementById('scrim').classList.remove('is-open');
  }

  document.getElementById('themebtn').addEventListener('click', function () {
    var cur = document.documentElement.getAttribute('data-theme');
    var prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    S.theme = cur === 'dark' ? 'light' : cur === 'light' ? (prefersDark ? 'light' : 'dark') : (prefersDark ? 'light' : 'dark');
    applyTheme();
    go(S.page);
  });

  document.getElementById('localebtn').addEventListener('click', function () {
    S.lang = S.lang === 'en' ? 'ar' : 'en';
    document.documentElement.setAttribute('dir', S.lang === 'ar' ? 'rtl' : 'ltr');
    this.textContent = S.lang === 'ar' ? 'SAR · ع' : 'SAR · EN';
    document.getElementById('whorole').textContent = S.lang === 'ar' ? 'محلل مخاطر · مُعِدّ' : 'RISK ANALYST · MAKER';
    go(S.page);
  });

  var TENANTS = ['Tenant A — Retail Lending', 'Tenant A — SME Lending', 'Tenant B — Consumer Finance'];
  var ti = 0;
  document.getElementById('tenantchip').addEventListener('click', function () {
    ti = (ti + 1) % TENANTS.length;
    document.getElementById('tenantname').textContent = TENANTS[ti];
    pushAudit('Switched tenant to ' + TENANTS[ti], 'TENANT.SWITCH');
    renderLedger();
  });

  document.getElementById('railbtn').addEventListener('click', function () {
    document.getElementById('rail').classList.toggle('is-open');
    document.getElementById('scrim').classList.toggle('is-open');
  });
  document.getElementById('ledgerbtn').addEventListener('click', function () {
    document.getElementById('ledger').classList.toggle('is-open');
    document.getElementById('scrim').classList.toggle('is-open');
  });
  document.getElementById('scrim').addEventListener('click', closeOverlays);

  document.getElementById('demostriptext').textContent =
    num(F.meta.n_rows) + ' generated applications · figures are not from any client book · currency shown as SAR pending localisation (§31.4)';

  /* ================================================================ boot */
  go('baseline');
})();
