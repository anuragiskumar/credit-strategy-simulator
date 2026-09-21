/* The one data model behind "Where applicants drop out". Both views (Funnel and Bars) draw
 * from this; only the drawing layer differs.
 *
 * It joins three exported blocks and computes nothing: every count and rate is read from
 * `funnel` (counts), `funnel_layout` (labels, groups, loss types, from config) and
 * `funnel_rules` (per-rule first-caught counts). `check()` re-adds the counts only to verify them.
 *
 * Loaded as a plain script in the page (window.FunnelModel) and with require() in the unit tests.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.FunnelModel = api;
})(this, function () {
  'use strict';

  function byStage(list) {
    var out = {};
    (list || []).forEach(function (r) { out[r.stage] = r; });
    return out;
  }

  function endpoint(row, spec) {
    return {
      id: row.stage, label: spec.label, sublabel: spec.sublabel || '', kind: spec.endpoint,
      stillIn: row.left, pctStillInOfTotal: row.left_pct
    };
  }

  function build(F) {
    var layout = F.funnel_layout, rows = byStage(F.funnel), drill = byStage(F.funnel_rules);
    var order = layout.order, first = order[0], last = order[order.length - 1];

    var stages = order.slice(1, -1).map(function (id) {
      var r = rows[id], spec = layout.stages[id], group = layout.groups[spec.group], d = drill[id];
      return {
        id: id, label: spec.label, sublabel: spec.sublabel || '',
        group: spec.group, groupLabel: group.label, lossType: group.loss_type,
        entered: r.entered, stillIn: r.left, lost: r.dropped,
        pctLostOfReaching: r.dropped_pct_of_entered,
        pctLostOfTotal: r.dropped_pct_of_total,
        pctStillInOfTotal: r.left_pct,
        drillable: spec.drill !== false && !!d && d.rules.length > 0,
        rulesTotal: d ? d.total : null, rulesCounted: d ? d.counted : null,
        nRules: d ? d.n_rules : 0, topN: d ? d.top_n : 0, topNPct: d ? d.top_n_pct : null,
        rules: d ? d.rules.map(function (x) {
          return { id: x.rule_id, code: x.policy_code, label: x.label, count: x.count,
                   pctOfStage: x.pct_of_stage, relaxable: x.relaxable,
                   tests: x.tests || '', disagrees: !!x.description_disagrees };
        }) : []
      };
    });

    // Groups in the order their first stage appears; membership comes from config only.
    var groups = [];
    stages.forEach(function (s) {
      var g = groups.filter(function (x) { return x.id === s.group; })[0];
      if (!g) groups.push(g = { id: s.group, label: s.groupLabel, lossType: s.lossType, stages: [] });
      g.stages.push(s);
    });

    var start = endpoint(rows[first], layout.stages[first]);
    var end = endpoint(rows[last], layout.stages[last]);
    var worst = stages.reduce(function (a, s) { return s.lost > a.lost ? s : a; }, stages[0]);

    var model = {
      total: start.stillIn, start: start, end: end, stages: stages, groups: groups,
      drillTopN: layout.drill_top_n,
      headline: {
        booked: end.stillIn, total: start.stillIn, bookedPct: end.pctStillInOfTotal,
        worst: worst, topN: worst.topN, nRules: worst.nRules, topNPct: worst.topNPct
      }
    };
    model.issues = check(model);
    stages.forEach(function (s) {
      s.issues = model.issues.filter(function (i) { return i.stage === s.id; });
    });
    return model;
  }

  /** Every way the counts can fail to add up, as {stage, msg}. Empty means the picture is complete. */
  function check(m) {
    var issues = [], at = null;
    function flag(msg) { issues.push({ stage: at, msg: msg }); }
    var prevIn = m.start.stillIn, prevLost = 0, prevId = m.start.id;
    m.stages.forEach(function (s) {
      at = s.id;
      if (s.entered !== prevIn - prevLost) {
        flag(s.id + ': in ' + s.entered + ' ≠ ' + prevId + ' in ' + prevIn + ' − lost ' + prevLost);
      }
      if (s.stillIn !== s.entered - s.lost) {
        flag(s.id + ': still in ' + s.stillIn + ' ≠ in ' + s.entered + ' − lost ' + s.lost);
      }
      if (s.rulesTotal !== null && s.rulesTotal !== s.lost) {
        flag(s.id + ': drill-down covers ' + s.rulesTotal + ' applicants but the stage lost ' + s.lost);
      }
      var sum = s.rules.reduce(function (a, r) { return a + r.count; }, 0);
      if (s.rules.length && sum !== s.lost) {
        flag(s.id + ': rule counts sum to ' + sum + ' but the stage lost ' + s.lost);
      }
      prevIn = s.entered; prevLost = s.lost; prevId = s.id;
    });
    var lastStage = m.stages[m.stages.length - 1];
    at = m.end.id;
    if (m.end.stillIn !== lastStage.stillIn) {
      flag(m.end.id + ': ' + m.end.stillIn + ' ≠ ' + lastStage.id + ' still in ' + lastStage.stillIn);
    }
    return issues;
  }

  /* Pixel geometry for the Funnel view, pure so it can be unit-tested.
   *
   * Bands are the still-in counts between stages: Applied, the survivors of each stage, and
   * Booked. Each band's width is exactly stillIn / applied × the band column's width, and a
   * trapezoid joins each band to the next, so the narrowing is the stage's loss. The last
   * stage's survivors ARE the booked loans, so that band is the Booked band and Booked is drawn
   * once. Stage names and leak arrows sit on the trapezoid rows, where the loss happens.
   */
  var MONO_CHAR = 6.6;   // IBM Plex Mono advance at 11px, for deciding whether a label fits

  function geometry(m, opts) {
    var W = opts.width, narrow = !!opts.narrow;
    // leakRun keeps clear space between the widest trapezoid and the labels, so every arrow
    // has room for the same curve, including the first stage, whose edge is nearest the labels.
    var leftW = narrow ? 78 : 172, rightW = narrow ? 104 : 232, gap = narrow ? 6 : 16, leakRun = narrow ? 30 : 64;
    var midX = leftW + gap, midW = Math.max(40, W - leftW - rightW - gap - leakRun);
    var cx = midX + midW / 2, labelX = W - rightW;
    var bandH = narrow ? 26 : 30, connH = narrow ? 56 : 54, groupH = 18, pad = 4;
    var maxLost = Math.max.apply(null, m.stages.map(function (s) { return s.lost; }));
    var swMin = narrow ? 1.5 : 2, swMax = narrow ? 6 : 12;

    function bandWidth(v) { return (v / m.total) * midW; }
    function bandLabel(kind, value, pct) {
      var n = value.toLocaleString('en-US');
      if (kind === 'start') return n + ' applied';
      if (kind === 'end') return narrow ? n + ' · ' + pct.toFixed(1) + '%' : n + ' booked · ' + pct.toFixed(1) + '%';
      return narrow ? n + ' · ' + pct.toFixed(1) + '%' : n + ' still in · ' + pct.toFixed(1) + '%';
    }
    function band(kind, id, value, pct, y) {
      var w = bandWidth(value), x = cx - w / 2, text = bandLabel(kind, value, pct);
      var tw = text.length * MONO_CHAR, h = kind === 'end' ? bandH + 4 : bandH;
      var place = tw + 16 <= w ? 'inside' : (W - (x + w) - 8 >= tw ? 'right' : 'left');
      return {
        kind: kind, id: id, value: value, pct: pct, x: x, y: y, w: w, h: h, text: text, place: place,
        tx: place === 'inside' ? cx : place === 'right' ? x + w + 8 : x - 8, ty: y + h / 2
      };
    }

    var y = pad, bands = [], connectors = [], leaks = [], names = [], groupLabels = [];
    var seenGroup = {};
    bands.push(band('start', m.start.id, m.start.stillIn, m.start.pctStillInOfTotal, y));
    names.push({ id: m.start.id, label: m.start.label, sub: '', y: y + bandH / 2, kind: 'start' });
    y += bandH;

    m.stages.forEach(function (s, i) {
      var top = bands[bands.length - 1];
      var first = !seenGroup[s.group];
      seenGroup[s.group] = true;
      var y0 = y + (first ? groupH : 0);
      if (first) groupLabels.push({ id: s.group, label: s.groupLabel, y: y + groupH / 2 + 3 });
      var last = i === m.stages.length - 1;
      var botW = bandWidth(last ? m.end.stillIn : s.stillIn);
      // The trapezoid always starts at the band above, including through a group label's row, so
      // the funnel never breaks; the label and its divider stay in the left column.
      var yb = y0 + connH;
      connectors.push({
        id: s.id, lossType: s.lossType, y: y, h: yb - y,
        points: [[cx - top.w / 2, y], [cx + top.w / 2, y], [cx + botW / 2, yb], [cx - botW / 2, yb]]
      });
      names.push({ id: s.id, label: s.label, sub: s.sublabel, y: y0 + connH / 2, kind: 'stage', group: s.group });

      // Every arrow leaves the trapezoid's right edge at the middle of the stage's row and
      // runs the same S-curve down to its label: one origin rule, one curve style.
      var ey = y0 + connH * 0.42, t = (ey - y) / (yb - y), ly = ey + (narrow ? 8 : 10);
      var ex = cx + (top.w / 2) * (1 - t) + (botW / 2) * t - 3;
      var sw = swMin + (swMax - swMin) * (maxLost ? s.lost / maxLost : 0);
      var head = narrow ? Math.max(3, sw * 0.6) + 2 : Math.max(4, sw * 0.8) + 3;
      var tip = labelX - (narrow ? 3 : 6), bx = tip - head * 1.3, k = (bx - ex) * 0.5;
      leaks.push({
        id: s.id, lossType: s.lossType, drillable: s.drillable, sw: sw,
        d: 'M' + ex.toFixed(1) + ',' + ey.toFixed(1) + ' C' + (ex + k).toFixed(1) + ',' + ey.toFixed(1) + ' ' +
           (bx - k).toFixed(1) + ',' + ly.toFixed(1) + ' ' + bx.toFixed(1) + ',' + ly.toFixed(1),
        head: [[bx, ly - head], [tip, ly], [bx, ly + head]],
        lx: labelX, ly: ly + 4, x0: ex, y0: y0, run: bx - ex,
        line1: '−' + s.lost.toLocaleString('en-US') + ' lost',
        line2: narrow ? s.pctLostOfReaching.toFixed(0) + '% of ' + s.entered.toLocaleString('en-US')
                      : s.pctLostOfReaching.toFixed(0) + '% of those reaching it'
      });
      y = y0 + connH;
      if (last) bands.push(band('end', m.end.id, m.end.stillIn, m.end.pctStillInOfTotal, y));
      else bands.push(band('mid', s.id, s.stillIn, s.pctStillInOfTotal, y));
      y += bands[bands.length - 1].h;
    });
    names.push({ id: m.end.id, label: m.end.label, sub: '', y: y - bands[bands.length - 1].h / 2, kind: 'end' });

    return {
      width: W, height: y + pad + 6, narrow: narrow, leftW: leftW, midX: midX, midW: midW, cx: cx,
      labelX: labelX, bands: bands, connectors: connectors, leaks: leaks, names: names, groupLabels: groupLabels
    };
  }

  return { build: build, check: check, geometry: geometry };
});
