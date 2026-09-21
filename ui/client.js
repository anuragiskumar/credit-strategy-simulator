/* Three CxO screens over a real rule set (plan step 5).
 *
 * This file contains no arithmetic beyond turning a number into a string, a percentage, or a
 * bar width. Every figure is read from window.__CLIENT__, produced by ui/client_export.py, which calls
 * the same engine functions the CLIs and the tests call.
 *
 * Colour encodes provenance and nothing else:
 *   OBSERVED      counted from the replay
 *   PREDICTED     the PD model inside the population it was trained on
 *   INFERRED      reject inference — applicants the bank has never seen repay
 *   NOT_MODELLED  refused, and drawn hatched so an absence never reads as a number
 */
(function () {
  'use strict';

  /* The fixture carries one payload per precomputed context (product × period). F is the one on
   * screen; changing the product or the period swaps it (see setContext). */
  var ROOT = window.__CLIENT__;
  var F = ROOT;
  var MENU = ROOT.context_menu || null;
  var CTX = { product: F.meta.product, preset: F.meta.preset || null, window: F.meta.window || null,
              loading: false, error: null, seq: 0, open: false };
  var S = { page: 'portfolio', slice: 'employer_segment', trend: 'month', vintageBy: null, goal: 0, spec: false,
            fview: 'funnel', fdrill: null, fdrillAll: false };

  /* ------------------------------------------------------------- formatting */
  function esc(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function n0(v) { return v === null || v === undefined ? '—' : Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 }); }
  function pct(v, dp) { return v === null || v === undefined ? '—' : (Number(v) * 100).toFixed(dp === undefined ? 1 : dp) + '%'; }
  function pp(v) {
    if (v === null || v === undefined) return '—';
    var x = Number(v);
    return (x > 0 ? '+' : '') + x.toFixed(2) + 'pp';
  }
  function sar(v) {
    if (v === null || v === undefined) return '—';
    var x = Number(v);
    if (x >= 1e9) return (x / 1e9).toFixed(2) + 'bn';
    if (x >= 1e6) return (x / 1e6).toFixed(1) + 'm';
    if (x >= 1e3) return Math.round(x / 1e3) + 'k';
    return Math.round(x).toString();
  }
  function dash(v, fn) { return v === null || v === undefined ? '<span class="nodata">—</span>' : fn(v); }

  /** The only place provenance is decided. */
  function pv(kind, text) {
    return '<span class="pv pv-' + kind + '">' + esc(text || kind.replace('_', ' ')) + '</span>';
  }
  function riskPill(known) { return known ? pv('INFERRED', 'INFERRED') : pv('NOT_MODELLED', 'NO ESTIMATE'); }

  /** Marks an element as having a spec note; numbering and footnotes are applied by applySpec(). */
  function N(key) { return ' data-note="' + key + '"'; }

  function tile(key, value, detail, cls, note) {
    return '<div class="tile ' + (cls || '') + '"><div class="k"' + (note || '') + '>' + key + '</div>' +
      '<div class="v fig">' + value + '</div>' +
      (detail ? '<div class="d">' + detail + '</div>' : '') + '</div>';
  }
  function panel(title, right, body, note) {
    return '<div class="panel"><div class="panelhead"><h3' + (note || '') + '>' + esc(title) + '</h3>' +
      '<div class="spacer"></div>' + (right || '') + '</div>' +
      '<div class="panelbody">' + body + '</div></div>';
  }
  function caveat(kind, tag, html, note) {
    return '<div class="caveat ' + kind + '"><div class="ci"' + (note || '') + '>' + esc(tag) + '</div><div><p>' + html + '</p></div></div>';
  }
  function table(head, rows) {
    return '<div class="tablewrap"><table class="t"><thead><tr>' + head + '</tr></thead><tbody>' +
      rows.join('') + '</tbody></table></div>';
  }
  function bar(value, max, cls) {
    var w = max > 0 ? Math.max(1, Math.round((value / max) * 100)) : 0;
    return '<span class="minibar ' + (cls || '') + '" style="width:' + w + '%"></span>';
  }

  /* =============================================================== screen 1 */
  function pagePortfolio() {
    var h = F.headline, m = F.meta;
    var tiles = '<div class="tiles c4">' +
      tile('Approval rate ' + pv('OBSERVED'), pct(h.approval_rate),
           n0(h.booked) + ' booked of ' + n0(m.applicants), 'on-obs', N('k_approval')) +
      tile('Booked bad rate ' + pv('OBSERVED'), pct(h.booked_bad_rate, 2),
           m.window ? n0(m.window.mature_loans) + ' booked loans old enough to judge' : 'observed on the book only',
           'on-obs', N('k_bad')) +
      tile('Exposure ' + pv('OBSERVED'), 'SAR ' + sar(h.exposure), 'after every finance cap', '', N('k_exposure')) +
      tile('Median offer gap ' + pv('OBSERVED'), 'SAR ' + sar(h.median_offer_gap),
           'requested minus offered', '', N('k_gap')) +
      '</div>';

    var funnelPanel = funnelPanelHtml();

    var sliceBtns = ['employer_segment', 'sector', 'channel', 'score_band', 'nationality']
      .map(function (k) {
        return '<button class="chip" data-slice="' + k + '"' +
          (S.slice === k ? ' aria-current="true"' : '') + '>' + esc(k.replace(/_/g, ' ')) + '</button>';
      }).join(' ');

    var book = F.portfolio[S.slice];
    var key = Object.keys(book.rows[0])[0];
    var maxExp = Math.max.apply(null, book.rows.map(function (r) { return r.exposure || 0; }));
    var rows = book.rows.map(function (r) {
      var flag = (book.flags || []).filter(function (f) { return String(f.slice) === String(r[key]); })[0];
      return '<tr><td>' + esc(r[key]) + '</td>' +
        '<td class="num">' + n0(r.booked) + '</td>' +
        '<td style="width:120px">' + bar(r.exposure, maxExp) + '</td>' +
        '<td class="num">' + pct(r.share_of_exposure / 100) + '</td>' +
        '<td class="num">' + dash(r.bad_rate, function (v) { return v.toFixed(2) + '%'; }) + '</td>' +
        '<td>' + (flag ? '<span class="st-pill">' + esc(flag.flag) + '</span>' : '') + '</td></tr>';
    });

    var portfolioPanel = panel('The booked book, sliced', sliceBtns + csvBtn('portfolio'),
      table('<th>' + esc(key.replace(/_/g, ' ')) + '</th><th class="num"' + N('th_booked') + '>Booked</th>' +
            '<th' + N('th_exposure') + '>Exposure</th><th class="num"' + N('th_share') + '>Share</th>' +
            '<th class="num"' + N('th_bad') + '>Bad rate ' + pv('OBSERVED') + '</th>' +
            '<th' + N('th_flag') + '>Flag</th>', rows) +
      ((book.flags || []).length
        ? caveat('warn', 'CONC',
            'Concentration measured against an even split across slices. ' +
            esc((book.flags || []).map(function (f) { return f.slice + ' (' + f.flag + ')'; }).join(', ')) + '.',
            N('conc'))
        : ''), N('slice'));

    return '<div class="pagehead"><h2' + N('pf_head') + '>Portfolio</h2>' +
      '<p>What the current strategy books, and what that book is made of.</p>' + periodLine() + '</div>' +
      tiles + funnelPanel + overTimePanel() + portfolioPanel + sourcePanel();
  }

  /* ------------------------------------------------------------ over time (TODO B2)
   * Two views of the product's whole file, not the analysis window: approval and bad rate by
   * application month, and vintage curves by booking month or quarter. Every figure is the
   * engine's (payload `over_time`); a month or a point it gives no rate is drawn as a gap and
   * says why, so the recent months can never look safer than the loans behind them. */
  function shortMonth(label) { return String(label).replace(/ 20(\d\d)$/, ' ’$1'); }

  function trendChart(T) {
    var rows = T.months, n = rows.length, ceil = F.meta.bad_rate_ceiling;
    var W = 720, L = 56, R = 16, T0 = 22, H1 = 104, GAP = 34, H2 = 124, B = 30;
    var H = T0 + H1 + GAP + H2 + B, bw = (W - L - R) / n;
    function xMonth(i) { return L + (i + 0.5) * bw; }
    var ar = rows.map(function (r) { return r.approval_rate; });
    var a0 = Math.min.apply(null, ar), a1 = Math.max.apply(null, ar), ap = Math.max(0.01, (a1 - a0) * 0.25);
    a0 = Math.max(0, a0 - ap); a1 = Math.min(1, a1 + ap);
    var br = rows.map(function (r) { return r.bad_rate; }).filter(function (v) { return v !== null; });
    var b1 = Math.max.apply(null, br.concat([ceil || 0])) * 1.15 || 0.1;
    var y2 = T0 + H1 + GAP;
    function YA(v) { return T0 + (a1 - v) * H1 / (a1 - a0); }
    function YB(v) { return y2 + (b1 - v) * H2 / b1; }
    var g = '';
    // The analysis window, behind everything.
    var win = rows.map(function (r, i) { return r.in_window ? i : -1; }).filter(function (i) { return i >= 0; });
    if (win.length) {
      var wx = L + win[0] * bw, ww = (win[win.length - 1] - win[0] + 1) * bw;
      g += '<rect class="win" x="' + wx + '" y="' + (T0 - 16) + '" width="' + ww + '" height="' + (H - B - T0 + 16) + '"/>' +
           '<text class="wint" x="' + (wx + 6) + '" y="' + (T0 - 5) + '">chosen period</text>';
    }
    // Months with no bad rate yet: one band per run, in the bad-rate pane.
    var i = 0;
    while (i < n) {
      if (rows[i].bad_rate !== null) { i++; continue; }
      var j = i; while (j + 1 < n && rows[j + 1].bad_rate === null) j++;
      g += '<rect class="unjudged" x="' + (L + i * bw) + '" y="' + y2 + '" width="' + ((j - i + 1) * bw) + '" height="' + H2 + '"/>';
      if (j - i >= 2) g += '<text class="unj-t" x="' + (L + (i + j + 1) * bw / 2) + '" y="' + (y2 + H2 / 2 + 4) + '" text-anchor="middle">not judged yet: loans still inside the ' + T.performance_months + '-month window</text>';
      i = j + 1;
    }
    [[a0, a1, YA, T0, H1], [0, b1, YB, y2, H2]].forEach(function (p) {
      for (var k = 0; k <= 2; k++) {
        var v = p[0] + (p[1] - p[0]) * k / 2;
        g += '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + p[2](v) + '" y2="' + p[2](v) + '"/>' +
             '<text class="tick" x="' + (L - 8) + '" y="' + (p[2](v) + 4) + '" text-anchor="end">' + pct(v, 0) + '</text>';
      }
    });
    g += '<text class="axis" x="' + L + '" y="' + (T0 - 5 - (win.length && win[0] === 0 ? 12 : 0)) + '">Approval rate, today’s rules</text>';
    g += '<text class="axis" x="' + L + '" y="' + (y2 - 8) + '">Bad rate, ' + T.performance_months + ' months on book</text>';
    if (ceil) g += '<line class="ceil" x1="' + L + '" x2="' + (W - R) + '" y1="' + YB(ceil) + '" y2="' + YB(ceil) + '"/>' +
                   '<text class="lbl ceil-t" x="' + (W - R - 4) + '" y="' + (YB(ceil) - 5) + '" text-anchor="end">bad-rate limit ' + pct(ceil, 1) + '</text>';
    var step = n > 12 ? 3 : 1;
    rows.forEach(function (r, k) {
      if (k % step === 0) g += '<text class="tick" x="' + xMonth(k) + '" y="' + (H - B + 17) + '" text-anchor="middle">' + esc(shortMonth(r.label)) + '</text>';
    });
    // Lines break where there is no rate; they never bridge a gap.
    function line(get, Y) {
      var out = '', seg = [];
      rows.concat([null]).forEach(function (r, k) {
        var v = r ? get(r) : null;
        if (v !== null && v !== undefined) { seg.push([xMonth(k), Y(v)]); return; }
        if (seg.length > 1) out += '<polyline class="tl" points="' + pts(seg) + '"/>';
        seg = [];
      });
      return out;
    }
    g += line(function (r) { return r.approval_rate; }, YA) + line(function (r) { return r.bad_rate; }, YB);
    rows.forEach(function (r, k) {
      g += '<circle class="td" cx="' + xMonth(k) + '" cy="' + YA(r.approval_rate) + '" r="3.2"><title>' + esc(r.label + ': approval ' +
           pct(r.approval_rate) + ', ' + n0(r.booked) + ' of ' + n0(r.applications)) + '</title></circle>';
      g += r.bad_rate !== null
        ? '<circle class="td" cx="' + xMonth(k) + '" cy="' + YB(r.bad_rate) + '" r="3.2"><title>' + esc(r.label + ': bad rate ' +
          pct(r.bad_rate, 2) + ' on ' + n0(r.mature) + ' loans') + '</title></circle>'
        : '<rect class="hit" x="' + (L + k * bw) + '" y="' + y2 + '" width="' + bw + '" height="' + H2 + '"><title>' +
          esc(r.label + ': no bad rate, ' + r.bad_rate_reason) + '</title></rect>';
    });
    return '<div class="simchart trchart"' + N('trend_chart') + '><svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' +
      esc('Approval rate and bad rate by application month, ' + rows[0].label + ' to ' + rows[n - 1].label) + '">' + g + '</svg></div>';
  }

  function trendTable(T) {
    return table('<th>Application month</th><th class="num">Applications</th><th class="num">Approved</th>' +
      '<th class="num">Approval rate ' + pv('OBSERVED') + '</th><th class="num"' + N('tr_judged') + '>Loans judged</th>' +
      '<th class="num">Bad rate ' + pv('OBSERVED') + '</th>',
      T.months.slice().reverse().map(function (r) {
        return '<tr' + (r.in_window ? ' class="is-win"' : '') + '><td>' + esc(r.label) + (r.partial ? ' <span class="nodata">(part month)</span>' : '') + '</td>' +
          '<td class="num">' + n0(r.applications) + '</td><td class="num">' + n0(r.booked) + '</td>' +
          '<td class="num">' + pct(r.approval_rate) + '</td>' +
          '<td class="num">' + n0(r.mature) + (r.mature_share !== null && r.mature_share < 1 ? ' <span class="nodata">(' + pct(r.mature_share, 0) + ')</span>' : '') + '</td>' +
          '<td class="num">' + (r.bad_rate !== null ? pct(r.bad_rate, 2) : '<span class="nodata" title="' + esc(r.bad_rate_reason) + '">not yet</span>') + '</td></tr>';
      }));
  }

  function vintageChart(V) {
    var list = V.cohorts.filter(function (c) { return c.points.length; });
    if (!list.length) return '<p class="simnote">No booking cohort has been on book long enough to draw.</p>';
    var W = 720, H = 300, L = 56, R = 70, T0 = 16, B = 40;
    var m1 = Math.max.apply(null, list.map(function (c) { return c.points[c.points.length - 1][0]; }));
    var y1 = Math.max.apply(null, list.map(function (c) { return c.points[c.points.length - 1][1]; })) * 1.12 || 0.1;
    function xMob(k) { return L + (k - 1) * (W - L - R) / Math.max(1, m1 - 1); }
    function yShare(v) { return T0 + (y1 - v) * (H - T0 - B) / y1; }
    var g = '';
    for (var k = 0; k <= 4; k++) {
      var yv = y1 * k / 4;
      g += '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + yShare(yv) + '" y2="' + yShare(yv) + '"/>' +
           '<text class="tick" x="' + (L - 8) + '" y="' + (yShare(yv) + 4) + '" text-anchor="end">' + pct(yv, yv < 0.1 ? 1 : 0) + '</text>';
    }
    for (var m = 1; m <= m1; m++) {
      if (m === 1 || m % 3 === 0) g += '<text class="tick" x="' + xMob(m) + '" y="' + (H - B + 17) + '" text-anchor="middle">' + m + '</text>';
    }
    g += '<text class="axis" x="' + ((L + W - R) / 2) + '" y="' + (H - 4) + '" text-anchor="middle">Months on book →</text>' +
         '<text class="axis" x="14" y="' + ((T0 + H - B) / 2) + '" text-anchor="middle" transform="rotate(-90 14 ' + ((T0 + H - B) / 2) + ')">Share gone bad →</text>';
    var dm = V.definition_months;
    if (dm <= m1) g += '<line class="tgt" x1="' + xMob(dm) + '" x2="' + xMob(dm) + '" y1="' + T0 + '" y2="' + (H - B) + '"/>' +
                       '<text class="lbl tgt-t" x="' + (xMob(dm) + 6) + '" y="' + (T0 + 12) + '">bad definition: ' + dm + ' months</text>';
    // Newest cohort darkest. One colour, because every point is counted: colour is provenance.
    var labelled = V.granularity === 'quarter';
    list.forEach(function (c, idx) {
      var shade = list.length > 1 ? 0.3 + 0.7 * idx / (list.length - 1) : 1;
      var p = c.points.map(function (q) { return [xMob(q[0]), yShare(q[1])]; }), last = c.points[c.points.length - 1];
      var t = c.label + ': ' + n0(c.loans) + ' loans; ' + pct(last[1], 1) + ' gone bad after ' + last[0] + ' months on book';
      var op = ' style="opacity:' + shade.toFixed(2) + '"';
      g += '<g class="vl"><title>' + esc(t) + '</title>' +
           (p.length > 1 ? '<polyline' + op + ' points="' + pts(p) + '"/>' : '') +
           '<circle' + op + ' cx="' + p[p.length - 1][0] + '" cy="' + p[p.length - 1][1] + '" r="3"/>' +
           (labelled ? '<text class="vlt" x="' + (p[p.length - 1][0] + 6) + '" y="' + (p[p.length - 1][1] + 4) + '">' + esc(c.label) + '</text>' : '') +
           '</g>';
    });
    return '<div class="simchart trchart"' + N('vintage_chart') + '><svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' +
      esc('Cumulative bad rate by months on book, one line per booking ' + V.granularity) + '">' + g + '</svg></div>';
  }

  function vintageTable(V) {
    var at = [3, 6, V.definition_months].filter(function (v, i, a) { return a.indexOf(v) === i; });
    function point(c, k) { var p = c.points.filter(function (q) { return q[0] === k; })[0]; return p ? pct(p[1], 1) : '<span class="nodata">—</span>'; }
    return table('<th>Booked in</th><th class="num">Loans</th>' +
      at.map(function (k) { return '<th class="num">After ' + k + ' months ' + (k === V.definition_months ? pv('OBSERVED') : '') + '</th>'; }).join('') +
      '<th class="num">Latest</th>',
      V.cohorts.slice().reverse().map(function (c) {
        var last = c.points[c.points.length - 1];
        return '<tr><td>' + esc(c.label) + '</td><td class="num">' + n0(c.loans) + '</td>' +
          at.map(function (k) { return '<td class="num">' + point(c, k) + '</td>'; }).join('') +
          '<td class="num">' + (last ? pct(last[1], 1) + ' <span class="nodata">at ' + last[0] + ' mo</span>' : '<span class="nodata" title="' + esc(c.reason || '') + '">none yet</span>') + '</td></tr>';
      }));
  }

  function overTimePanel() {
    var T = F.over_time;
    if (!T) return '';
    var view = S.trend || 'month';
    var by = S.vintageBy && T.vintage[S.vintageBy] ? S.vintageBy : Object.keys(T.vintage)[0];
    var tabs = [['month', 'By application month'], ['vintage', 'Vintage']].map(function (v) {
      return '<button class="chip" data-trend="' + v[0] + '"' + (view === v[0] ? ' aria-current="true"' : '') + '>' + v[1] + '</button>';
    }).join(' ');
    var body, lastJudged = T.months.filter(function (r) { return r.bad_rate !== null; }).pop();
    if (view === 'month') {
      var waiting = T.months.filter(function (r) { return r.bad_rate === null; }).length;
      body = '<p class="trlead"' + N('trend_lead') + '>Each month’s applications replayed against today’s rules, and the bad rate of the loans they became. ' +
        'A month gets a bad rate once ' + pct(T.min_mature_share, 0) + ' of its loans have run ' + T.performance_months + ' months by the extract date (' +
        esc(dayMonthYear(T.as_of)) + ')' + (lastJudged ? '; the latest judged is ' + esc(lastJudged.label) : '') + '.' +
        (waiting ? ' The ' + waiting + ' months after it are too recent to judge, which is why the bad rate on this page comes from older loans.' : '') + '</p>' +
        trendChart(T) +
        '<details class="trmore"><summary>The months, as a table</summary>' + trendTable(T) + '</details>';
    } else {
      var V = T.vintage[by];
      var gran = Object.keys(T.vintage).map(function (k) {
        return '<button class="chip" data-vby="' + k + '"' + (by === k ? ' aria-current="true"' : '') + '>By ' + k + '</button>';
      }).join(' ');
      body = '<div class="trsub">' + gran + '</div>' +
        '<p class="trlead"' + N('vintage_lead') + '>Every loan the bank booked, grouped by when it was booked: the share that had reached ' +
        (MENU ? MENU.outcome.dpd + '+ DPD' : 'the bad definition') + ' after each month on book. A line stops at the last month every loan in it has run; ' +
        'at ' + V.definition_months + ' months it is that cohort’s bad rate. A later line above an earlier one is a book getting worse.</p>' +
        vintageChart(V) +
        '<details class="trmore"><summary>The cohorts, as a table</summary>' + vintageTable(V) + '</details>';
    }
    return panel('Over time', tabs + (view === 'month' ? csvBtn('trend') : csvBtn('vintage')), body +
      caveat('', 'ROLL', 'Roll rates are not shown: ' + esc(T.roll_rate.reason) + '.', N('roll_rate')), N('over_time'));
  }

  /* ------------------------------------------------ where applicants drop out
   * One panel, one model (client_funnel_model.js), two views. The header, headline, legend,
   * note and drill-down are shared; only funnelBarsHtml() and drawFunnel() differ, and they
   * only draw: every label, group, count and rate comes from the model, which reads the export.
   *
   * Loss is shown in achromatic greys by who ended the application (lender or customer), so
   * colour still means provenance only and hatching stays reserved for NOT MODELLED. */
  var DEV = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname) || /[?&]dev=1\b/.test(location.search);
  var FM = null;
  var SVGNS = 'http://www.w3.org/2000/svg';

  function funnelModel() {
    if (FM) return FM;
    FM = window.FunnelModel.build(F);
    // Dev-only: each stage's "in" must equal the previous "in" minus the previous "lost".
    if (DEV) FM.issues.forEach(function (i) { console.error('[funnel] ' + i.msg); });
    return FM;
  }
  function stageById(M, id) { return M.stages.filter(function (s) { return s.id === id; })[0] || null; }

  function drillTrigger(s, extraCls) {
    var open = S.fdrill === s.id;
    return '<button type="button" class="fchev ' + (extraCls || '') + '" data-drill="' + esc(s.id) + '"' +
      ' aria-expanded="' + open + '" aria-controls="fdrill"' +
      ' aria-label="' + (open ? 'Hide' : 'Show') + ' the rules behind ' + esc(s.label) + '">' +
      '<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M4 2.5 7.5 6 4 9.5" fill="none" ' +
      'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></button>';
  }

  /* Bars view. A waterfall: each stage row draws everyone who reached it, split into the solid
   * part that goes on and the grey part lost here, so the drop is seen, not subtracted. */
  function funnelBarsHtml(M) {
    function w(v) { return ((v / M.total) * 100).toFixed(3) + '%'; }
    var worst = M.headline.worst;

    function endRow(e, cls, figure) {
      return '<div class="frow ' + cls + '">' +
        '<div class="lbl"><b' + N('stage_' + e.id) + '>' + esc(e.label) + '</b></div>' +
        '<div class="track"><i class="go" style="width:' + w(e.stillIn) + '"></i></div>' +
        '<div class="fig-r">' + figure + '</div><div class="chev"></div></div>';
    }

    var body = M.groups.map(function (g, gi) {
      var head = '<div class="fgroup"><span class="gl">' + esc(g.label) + '</span>' +
        (gi === 0 ? '<span class="colhead">Lost here<small>% of those reaching it</small></span>' : '') + '</div>';
      return head + g.stages.map(function (s) {
        var tip = n0(s.entered) + ' reached this stage · ' + n0(s.lost) + ' lost · ' + n0(s.stillIn) + ' went on';
        return '<div class="frow is-' + s.lossType + (s === worst ? ' is-worst' : '') + '" data-stage="' + esc(s.id) + '">' +
          '<div class="lbl"><b' + N('stage_' + s.id) + '>' + esc(s.label) + '</b>' +
            '<span class="why hide-sm">' + esc(s.sublabel) + '</span></div>' +
          '<div class="track" role="img" aria-label="' + esc(s.label + ': ' + tip) + '" title="' + esc(tip) + '">' +
            '<i class="go" style="width:' + w(s.stillIn) + '"></i>' +
            '<i class="lost" style="left:' + w(s.stillIn) + ';width:calc(max(4px, ' + w(s.lost) + ') + 2px)"></i></div>' +
          '<div class="fig-r"><b>−' + n0(s.lost) + '</b>' +
            '<span>' + s.pctLostOfReaching.toFixed(0) + '% of ' + n0(s.entered) +
            // "% of all" only adds something when fewer than all applicants reached the stage.
            (s.entered === M.total ? '' :
              '<span class="hide-sm"> · ' + s.pctLostOfTotal.toFixed(0) + '% of all</span>') + '</span></div>' +
          '<div class="chev">' + (s.drillable ? drillTrigger(s) : '') + '</div></div>';
      }).join('');
    }).join('');

    return '<div class="fbars">' +
      endRow(M.start, 'is-start', '<b>' + n0(M.start.stillIn) + ' <em class="fbadge">Start</em></b>') +
      '<div class="fsep" role="presentation"></div>' + body + '<div class="fsep" role="presentation"></div>' +
      endRow(M.end, 'is-end', '<b>' + n0(M.end.stillIn) + ' <em class="fbadge is-booked">Booked</em></b>' +
        '<span>' + M.end.pctStillInOfTotal.toFixed(1) + '% of applicants</span>') +
      '</div>';
  }

  /* Funnel view: a glass vessel. Drawn after insertion because its geometry depends on the width
   * it gets. Every width is the model's: each disc is a band, the liquid joins them, and the glass
   * is the liquid padded by a constant.
   *
   * FANIM.p is how far the pour has got, in stages (0 = empty, one per band); null draws the
   * finished funnel. It only moves the figures toward the exported ones, and ends on them. */
  var FANIM = { p: null, target: null, raf: 0 };
  var FUNNEL_STAGE_S = 0.95;
  function clamp01(v) { return Math.max(0, Math.min(1, v)); }
  function easeOut(t) { t = clamp01(t); return 1 - (1 - t) * (1 - t) * (1 - t); }
  function span(t, a, b) { return clamp01((t - a) / (b - a)); }

  function svgEl(tag, attrs, text) {
    var el = document.createElementNS(SVGNS, tag);
    Object.keys(attrs || {}).forEach(function (k) { el.setAttribute(k, attrs[k]); });
    if (text !== undefined) el.textContent = text;
    return el;
  }
  function pts(list) { return list.map(function (p) { return p[0].toFixed(1) + ',' + p[1].toFixed(1); }).join(' '); }
  function xy(x, y) { return x.toFixed(1) + ',' + y.toFixed(1); }

  // Gradient stops take their colour from client.css, so both themes resolve from tokens.
  var GLASS_DEFS =
    '<linearGradient id="fg-body" x1="0" x2="1"><stop offset="0" class="s-glass-b"/><stop offset=".22" class="s-glass-a"/>' +
      '<stop offset=".7" class="s-glass-a"/><stop offset="1" class="s-glass-b"/></linearGradient>' +
    '<linearGradient id="fg-liquid" x1="0" x2="1"><stop offset="0" class="s-liq-edge"/><stop offset=".35" class="s-liq-mid"/>' +
      '<stop offset="1" class="s-liq-edge"/></linearGradient>' +
    '<radialGradient id="fg-disc" cx=".42" cy=".35" r=".75"><stop offset="0" class="s-obs-lite"/><stop offset="1" class="s-obs"/></radialGradient>' +
    '<radialGradient id="fg-disc-end" cx=".42" cy=".35" r=".75"><stop offset="0" class="s-obs"/><stop offset="1" class="s-obs-deep"/></radialGradient>' +
    '<filter id="fg-blur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6"/></filter>';

  function drawFunnel(host) {
    var M = funnelModel(), width = host.clientWidth;
    if (!width) return;
    var G = window.FunnelModel.geometry(M, { width: width, narrow: width < 560 });
    var GL = G.glass, cx = G.cx, last = G.bands.length - 1;
    var animating = FANIM.p !== null, p = animating ? FANIM.p : last + 1;
    function pour(k) { return clamp01(p - k); }   // stage k: 0 = applied, k = the band it leaves behind
    var svg = svgEl('svg', { width: G.width, height: G.height, viewBox: '0 0 ' + G.width + ' ' + G.height,
      'class': 'fsvg', role: 'group', 'aria-label': 'Funnel from ' + n0(M.total) + ' applicants to ' + n0(M.end.stillIn) + ' booked' });
    var defs = svgEl('defs');
    defs.innerHTML = GLASS_DEFS;
    svg.appendChild(defs);

    // Left column: a stage's name brightens as its stage fills.
    G.groupLabels.forEach(function (g) {
      svg.appendChild(svgEl('text', { x: 0, y: g.y, 'class': 'f-gl' }, g.label));
      svg.appendChild(svgEl('line', { x1: 0, x2: G.leftW, y1: g.y + 6, y2: g.y + 6, 'class': 'f-gdiv' }));
    });
    G.names.forEach(function (n, i) {
      var g = svgEl('g', animating ? { opacity: (0.32 + 0.68 * easeOut(pour(Math.min(i, last)) * 2)).toFixed(2) } : {});
      g.appendChild(svgEl('text', { x: 0, y: n.y + (n.sub && !G.narrow ? -3 : 4), 'class': 'f-name is-' + n.kind }, n.label));
      if (n.sub && !G.narrow) g.appendChild(svgEl('text', { x: 0, y: n.y + 12, 'class': 'f-sub' }, n.sub));
      svg.appendChild(g);
    });

    // The vessel: foot, then the glass behind the liquid.
    var rim = GL.rim, nk = GL.neck, st = GL.stem, ft = GL.foot, bend = nk.y0 + (nk.y1 - nk.y0) * 0.8;
    var neckL = ' C' + xy(cx - nk.x, bend) + ' ' + xy(cx - st.x, bend) + ' ' + xy(cx - st.x, nk.y1);
    var neckR = ' C' + xy(cx + nk.x, bend) + ' ' + xy(cx + st.x, bend) + ' ' + xy(cx + st.x, nk.y1);
    var wallL = 'M' + GL.wallL.map(function (q) { return xy(q[0], q[1]); }).join(' L') + neckL + ' L' + xy(cx - st.x, st.y1);
    var wallR = 'M' + GL.wallR.map(function (q) { return xy(q[0], q[1]); }).join(' L') + neckR + ' L' + xy(cx + st.x, st.y1);
    var body = wallL + ' L' + xy(cx + st.x, st.y1) + ' L' + xy(cx + st.x, nk.y1) +
      ' C' + xy(cx + st.x, bend) + ' ' + xy(cx + nk.x, bend) + ' ' + xy(cx + nk.x, nk.y0) +
      ' L' + GL.wallR.slice(0, -1).reverse().map(function (q) { return xy(q[0], q[1]); }).join(' L') +
      ' A' + rim.rx.toFixed(1) + ' ' + rim.ry.toFixed(1) + ' 0 0 1 ' + xy(cx - rim.rx, rim.cy) + ' Z';
    svg.appendChild(svgEl('ellipse', { cx: cx, cy: ft.cy + 5, rx: ft.rx * 1.15, ry: ft.ry * 0.9, 'class': 'f-gshadow', filter: 'url(#fg-blur)' }));
    svg.appendChild(svgEl('ellipse', { cx: cx, cy: ft.cy, rx: ft.rx, ry: ft.ry, 'class': 'f-glass' }));
    svg.appendChild(svgEl('ellipse', { cx: cx, cy: ft.cy - ft.ry * 0.3, rx: ft.rx * 0.8, ry: ft.ry * 0.6, 'class': 'f-ghi is-thin' }));
    svg.appendChild(svgEl('path', { d: body, 'class': 'f-gbody' }));
    svg.appendChild(svgEl('path', { d: 'M' + xy(cx - rim.rx, rim.cy) + ' A' + rim.rx + ' ' + rim.ry + ' 0 0 1 ' + xy(cx + rim.rx, rim.cy), 'class': 'f-gedge' }));

    // The liquid pours down to the level the animation has reached.
    var D = GL.discs, yFill = D[last].cy;
    if (animating) {
      yFill = D[0].cy;
      for (var k = 1; k <= last; k++) {
        var a = easeOut(span(pour(k), 0, 0.7));
        if (a > 0) yFill = D[k - 1].cy + (D[k].cy - D[k - 1].cy) * a;
      }
    }
    if (pour(0) > 0) {
      var ys = D.map(function (d) { return d.cy; }).filter(function (y) { return y < yFill; }).concat([yFill]);
      var liquid = ys.map(function (y) { return [cx - window.FunnelModel.liquidHalf(GL, y), y]; })
        .concat(ys.slice().reverse().map(function (y) { return [cx + window.FunnelModel.liquidHalf(GL, y), y]; }));
      svg.appendChild(svgEl('polygon', { points: pts(liquid), 'class': 'f-liquid', opacity: easeOut(pour(0)).toFixed(2) }));
    }

    // Discs: who is still in after each stage. The count runs down from the stage above.
    D.forEach(function (d, k) {
      var b = G.bands[k];
      var a = k === 0 ? easeOut(pour(0) * 1.3) : easeOut(span(pour(k), 0.3, 1));
      if (a <= 0) return;
      var g = svgEl('g', animating ? { opacity: a.toFixed(2), transform: 'translate(0 ' + ((1 - a) * -14).toFixed(1) + ')' } : {});
      g.appendChild(svgEl('ellipse', { cx: cx, cy: d.cy + 3, rx: d.rx, ry: d.ry, 'class': 'f-disc-under' }));
      g.appendChild(svgEl('ellipse', { cx: cx, cy: d.cy, rx: d.rx, ry: d.ry, 'class': 'f-disc' + (b.kind === 'end' ? ' is-end' : '') }));
      if (d.rx > 8 && d.ry > 4) {
        g.appendChild(svgEl('ellipse', { cx: cx, cy: d.cy - 1, rx: d.rx - 3, ry: d.ry - 2, 'class': 'f-disc-ring' }));
      }
      var text = b.text;
      if (animating && pour(k) < 1) {
        var v = k === 0 ? M.total * easeOut(pour(0))
          : G.bands[k - 1].value - (G.bands[k - 1].value - b.value) * easeOut(span(pour(k), 0.15, 0.9));
        text = G.bandLabel(b.kind === 'end' ? 'mid' : b.kind, Math.round(v), (v / M.total) * 100);
      }
      var anchor = b.place === 'inside' ? 'middle' : b.place === 'right' ? 'start' : 'end';
      g.appendChild(svgEl('text', { x: b.tx, y: b.ty + 4, 'text-anchor': anchor,
        'class': 'f-blabel' + (b.place === 'inside' ? ' is-in' : '') + (b.kind === 'end' ? ' is-end' : '') }, text));
      svg.appendChild(g);
    });

    // The glass in front: walls, highlights, the near half of the rim.
    svg.appendChild(svgEl('path', { d: wallL, 'class': 'f-gedge' }));
    svg.appendChild(svgEl('path', { d: wallR, 'class': 'f-gedge' }));
    var P = GL.pad;
    var hiL = GL.wallL.slice(0, -1).map(function (q, i) { return [q[0] + P * 0.9 + (i === 0 ? 6 : 0), q[1] + (i === 0 ? rim.ry + 4 : 0)]; });
    var hiR = GL.wallR.slice(0, -1).map(function (q, i) { return [q[0] - P * 0.7, q[1] + (i === 0 ? rim.ry + 8 : 0)]; });
    svg.appendChild(svgEl('polyline', { points: pts(hiL), 'class': 'f-ghi' }));
    svg.appendChild(svgEl('polyline', { points: pts(hiR), 'class': 'f-ghi is-thin' }));
    svg.appendChild(svgEl('line', { x1: cx - st.x * 0.4, x2: cx - st.x * 0.4, y1: st.y0 + 4, y2: st.y1 - 3, 'class': 'f-ghi is-thin' }));
    svg.appendChild(svgEl('path', { d: 'M' + xy(cx - rim.rx, rim.cy) + ' A' + rim.rx + ' ' + rim.ry + ' 0 0 0 ' + xy(cx + rim.rx, rim.cy), 'class': 'f-gedge' }));
    svg.appendChild(svgEl('path', { d: 'M' + xy(cx - rim.rx * 0.8, rim.cy + rim.ry * 0.6) + ' A' + rim.rx + ' ' + rim.ry + ' 0 0 0 ' +
      xy(cx - rim.rx * 0.2, rim.cy + rim.ry * 0.98), 'class': 'f-ghi' }));

    // Loss arrows leave through the wall. While pouring they grow out and their count runs up.
    G.leaks.forEach(function (l, i) {
      var s = stageById(M, l.id), open = S.fdrill === l.id;
      var grow = animating ? span(pour(i + 1), 0.1, 0.85) : 1;
      if (grow <= 0) return;
      var g = svgEl('g', { 'class': 'f-leak is-' + l.lossType + (l.drillable ? ' is-drill' : '') + (open ? ' is-open' : '') });
      if (l.drillable) {
        g.setAttribute('role', 'button');
        g.setAttribute('tabindex', '0');
        g.setAttribute('data-drill', l.id);
        g.setAttribute('aria-expanded', String(open));
        g.setAttribute('aria-controls', 'fdrill');
        g.setAttribute('aria-label', s.label + ': ' + l.line1 + ', ' + s.pctLostOfReaching.toFixed(0) +
          '% of those reaching it. ' + (open ? 'Hide' : 'Show') + ' the rules behind it');
      }
      var hitX = l.x0 - 4, hitY = l.y0 + 2;
      g.appendChild(svgEl('rect', { x: hitX, y: hitY, width: G.width - hitX, height: l.ly - hitY + 18, rx: 5, 'class': 'f-hit' }));
      var arrow = svgEl('g');
      if (grow < 1) {
        var clip = svgEl('clipPath', { id: 'fg-grow' + i });
        clip.appendChild(svgEl('rect', { x: hitX, y: hitY - 20, width: ((G.labelX - hitX) * easeOut(grow)).toFixed(1), height: l.ly - hitY + 40 }));
        defs.appendChild(clip);
        arrow.setAttribute('clip-path', 'url(#fg-grow' + i + ')');
      }
      arrow.appendChild(svgEl('path', { d: l.d, 'stroke-width': l.sw.toFixed(2), 'class': 'f-arrow' }));
      arrow.appendChild(svgEl('polygon', { points: pts(l.head), 'class': 'f-head' }));
      g.appendChild(arrow);
      var t = animating ? easeOut(span(grow, 0.25, 1)) : 1;
      if (t > 0) {
        var line1 = grow < 1 ? '−' + n0(Math.round(s.lost * t)) + ' lost' : l.line1;
        var labels = svgEl('g', t < 1 ? { opacity: t.toFixed(2) } : {});
        labels.appendChild(svgEl('text', { x: l.lx, y: l.ly - 1, 'class': 'f-l1' }, line1 + (l.drillable ? (open ? ' ▾' : ' ›') : '')));
        labels.appendChild(svgEl('text', { x: l.lx, y: l.ly + 12, 'class': 'f-l2' }, l.line2));
        g.appendChild(labels);
      }
      svg.appendChild(g);
    });
    host.replaceChildren(svg);
  }

  /* Presenter mode. The screen opens on an empty funnel with focus on it, and the arrow keys
   * pour it one stage at a time, so the presenter reveals each loss as they talk about it;
   * Home empties it, End pours the rest, Reset starts again. Reduced motion jumps instead of
   * pouring, and printing always gets the finished funnel. */
  function redrawFunnel() {
    var host = document.querySelector('.ffunnelhost');
    if (host) drawFunnel(host);
  }
  function funnelFull() { return funnelModel().stages.length + 1; }

  /* Where the funnel is heading: a whole number of stages, the full count when finished. */
  function funnelAt() { return FANIM.p === null ? funnelFull() : FANIM.target; }

  function settleFunnel(announce) {
    FANIM.p = FANIM.target >= funnelFull() ? null : FANIM.target;
    redrawFunnel();
    if (announce) announceStage(FANIM.target);
  }

  function animateFunnel(target, announce) {
    var full = funnelFull();
    cancelAnimationFrame(FANIM.raf);
    if (FANIM.p === null) FANIM.p = full;
    FANIM.target = Math.max(0, Math.min(full, target));
    if (calmMotion() || FANIM.p === FANIM.target) { settleFunnel(announce); return; }
    var prev = null;
    function tick(ts) {
      if (!document.querySelector('.ffunnelhost')) { FANIM.p = null; return; }
      if (prev === null) prev = ts;
      // Capped so a slow frame skips ahead a little, not to the end; a hidden tab gets no frames.
      var d = Math.min(0.25, (ts - prev) / 1000) / FUNNEL_STAGE_S;
      prev = ts;
      // Stepping back drains a little faster than it fills.
      FANIM.p = FANIM.p < FANIM.target ? Math.min(FANIM.target, FANIM.p + d) : Math.max(FANIM.target, FANIM.p - d * 1.6);
      if (FANIM.p === FANIM.target) { settleFunnel(announce); return; }
      redrawFunnel();
      FANIM.raf = requestAnimationFrame(tick);
    }
    FANIM.raf = requestAnimationFrame(tick);
  }
  function emptyFunnel(host) {
    cancelAnimationFrame(FANIM.raf);
    FANIM.p = 0;
    FANIM.target = 0;
    drawFunnel(host);
    announceStage(0);
    // Focus is for the presenter's keys; the ring only appears once the keyboard moves it.
    host.classList.add('is-quiet');
    host.focus({ preventScroll: true });
  }
  function finishFunnel() {
    cancelAnimationFrame(FANIM.raf);
    if (FANIM.p !== null) { FANIM.p = null; redrawFunnel(); }
  }

  /* What a step reveals, in words: shown beside Reset and read out by screen readers. */
  function stageCaption(k) {
    var M = funnelModel(), full = funnelFull();
    if (k === null) return '';
    if (k <= 0) return 'Empty · → to begin';
    var head = 'Stage ' + k + '/' + full + ' · ';
    if (k === 1) return head + n0(M.total) + ' applied';
    var s = M.stages[k - 2];
    var left = k === full ? n0(M.end.stillIn) + ' booked' : n0(s.stillIn) + ' still in';
    return head + s.label + ' −' + n0(s.lost) + ' · ' + left;
  }
  function announceStage(k) {
    var el = document.getElementById('fstep');
    if (el) el.textContent = stageCaption(k);
  }

  function stepFunnel(e, host) {
    var keys = { ArrowRight: 1, ArrowLeft: -1, Home: 'home', End: 'end' };
    if (!(e.key in keys) || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return false;
    e.preventDefault();
    // The arrows are redrawn on every frame, so focus stays on the funnel itself while it moves.
    if (document.activeElement !== host) host.focus({ preventScroll: true });
    var k = keys[e.key], at = funnelAt();
    animateFunnel(k === 'home' ? 0 : k === 'end' ? funnelFull() : at + k, true);
    return true;
  }
  window.addEventListener('beforeprint', finishFunnel);

  /* The drill-down, shared by both views: one region below them, opened from either. */
  var DISAGREE_TIP = 'The bank\'s description quotes different numbers from the conditions this rule ' +
    'actually tests. The conditions are what is replayed, so they are what the counts reflect.';

  var SOLE_TIP = 'Caught first counts each applicant once, under the first rule that stopped them, so ' +
    'these add up to the stage. Sole cause counts applicants only this rule stops: remove just this ' +
    'rule and they pass every other rule. These do not add up, because many applicants are stopped ' +
    'by several rules.';
  var LOCK_SVG = '<svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true">' +
    '<path d="M3.8 5.5V4a2.2 2.2 0 0 1 4.4 0v1.5" fill="none" stroke="currentColor" stroke-width="1.4"/>' +
    '<rect x="2" y="5.5" width="8" height="5.5" rx="1.2" stroke="currentColor" stroke-width="1.2"/></svg>';

  /* Locked is declared by the bank, so it is drawn solid; a fixed field is inferred from the
   * rule's fields, so it is drawn hollow and lighter — the same known/guessed distinction the
   * provenance tags make, in neutral ink because colour is reserved for provenance. */
  function lockMark(r) {
    if (r.locked) {
      return '<span class="rlock is-locked" role="img" aria-label="Locked: regulatory knock-out" ' +
        'title="Locked: regulatory knock-out">' + LOCK_SVG + '</span>';
    }
    if (r.fixedField) {
      return '<span class="rlock is-fixed" role="img" aria-label="Fixed field (inferred from rule fields)" ' +
        'title="Fixed field (inferred from rule fields)">' + LOCK_SVG + '</span>';
    }
    return '';
  }

  function drillHtml(M) {
    var s = S.fdrill ? stageById(M, S.fdrill) : null;
    if (!s) return '';
    var hasSole = s.soleTotal !== null;
    var all = S.fdrillAll && s.nRules > M.drillTopN;
    var shown = all ? s.rules : s.rules.slice(0, M.drillTopN), more = s.nRules - M.drillTopN;
    var rows = shown.map(function (r) {
      // The rule ID is always shown: descriptions repeat (two rules both read "Age is not
      // between 20 and 70"), and what separates them is the conditions on the second line.
      var sub = (r.id !== r.label ? '<span class="rid">' + esc(r.id) + '</span>' : '') +
        (r.tests ? '<span class="rtests">tests ' + esc(r.tests) + '</span>' : '') +
        (r.disagrees ? '<span class="rdiff" title="' + esc(DISAGREE_TIP) + '">≠ description</span>' : '');
      return '<li><span class="rn"><span class="rl" title="' + esc(r.label) + '">' + lockMark(r) +
          (r.code ? '<code>' + esc(r.code) + '</code>' : '') + esc(r.label) + '</span>' +
          (sub ? '<span class="rsub">' + sub + '</span>' : '') + '</span>' +
        '<span class="rc">' + n0(r.count) + '</span>' +
        '<span class="rp">' + r.pctOfStage.toFixed(1) + '%</span>' +
        (hasSole ? '<span class="rs">' + (r.sole === null ? '<span class="nodata">—</span>' : n0(r.sole)) + '</span>' : '') +
        '<span class="rb" aria-hidden="true"><i style="width:' + r.pctOfStage + '%"></i></span></li>';
    }).join('');
    var issues = s.issues.length
      ? caveat('warn', 'CHECK', 'These counts do not reconcile: ' +
          esc(s.issues.map(function (i) { return i.msg; }).join('; ')) + '.')
      : '';
    var moreBtn = more > 0
      ? '<button type="button" class="fmore" data-drill-more aria-expanded="' + all + '" aria-controls="fdrill-list">' +
          (all ? 'Show the top ' + M.drillTopN + ' only' : '+' + n0(more) + ' more ' + (more === 1 ? 'rule' : 'rules')) +
        '</button>'
      : '';
    return '<div class="fdrill-in is-' + s.lossType + '">' +
      '<div class="fdrill-head"><h4 id="fdrill-h" tabindex="-1">' + esc(s.label) +
        ' <span>rules that caught applicants first</span></h4>' +
        '<button type="button" class="fclose" data-drill-close aria-label="Close the rules behind ' + esc(s.label) + '">×</button></div>' +
      '<p class="fdrill-sub">' + n0(s.lost) + ' lost here across ' + n0(s.nRules) + (s.nRules === 1 ? ' reason' : ' rules') +
        '. Each applicant is counted once, under the first rule that caught them.</p>' +
      '<div class="fdrill-cols' + (hasSole ? ' has-sole' : '') + '"><span aria-hidden="true">Rule</span>' +
        '<span aria-hidden="true">Caught first</span><span aria-hidden="true">Share</span>' +
        (hasSole ? '<span class="soleh">Sole cause<button type="button" class="finfo" ' +
          'aria-label="What caught first and sole cause mean" aria-describedby="fdrill-sole-tip">i</button>' +
          '<span class="ftip" role="tooltip" id="fdrill-sole-tip">' + esc(SOLE_TIP) + '</span></span>' : '') +
        '<span></span></div>' +
      '<ol class="fdrill-list' + (hasSole ? ' has-sole' : '') + '" id="fdrill-list">' + rows + '</ol>' + moreBtn +
      (hasSole && s.multiCaught > 0
        ? '<p class="fdrill-multi"><b>' + n0(s.multiCaught) + '</b> of ' + n0(s.lost) + ' are stopped by more than ' +
          'one rule, so removing any single rule would not let them through.</p>'
        : '') +
      issues + '</div>';
  }

  function funnelPanelHtml() {
    var M = funnelModel(), h = M.headline, view = S.fview;
    var lede = '<p class="flede">' +
      '<b>' + n0(h.booked) + '</b> of ' + n0(h.total) + ' applicants are booked (' + h.bookedPct.toFixed(1) + '%). ' +
      '<b>' + esc(h.worst.label) + '</b> removes the most: ' + n0(h.worst.lost) + ' people, ' +
      h.worst.pctLostOfReaching.toFixed(0) + '% of those who reach it.' +
      (h.nRules > h.topN ? ' Top ' + h.topN + ' of ' + n0(h.nRules) + ' rules account for ' +
        h.topNPct.toFixed(1) + '% of these.' : '') + '</p>';
    var key = '<div class="fkey" aria-hidden="true">' +
      '<span><i class="k-go"></i>still in</span>' +
      '<span><i class="k-lender"></i>declined by lender</span>' +
      '<span><i class="k-customer"></i>customer walked away</span></div>';
    var seg = '<div class="fseg" role="group" aria-label="View"' + N('fview') + '>' +
      ['funnel', 'bars'].map(function (v) {
        return '<button type="button" data-fview="' + v + '" aria-pressed="' + (view === v) + '">' +
          (v === 'funnel' ? 'Funnel' : 'Bars') + '</button>';
      }).join('') + '</div>';
    var views = '<div class="fviews">' +
      '<div class="fview' + (view === 'funnel' ? ' is-on' : '') + '" data-view="funnel"' + (view === 'funnel' ? '' : ' inert aria-hidden="true"') + '>' +
        '<div class="fctl"><span class="fstep" id="fstep" aria-live="polite"></span>' +
          '<button type="button" class="freset" data-freset>Reset</button></div>' +
        '<div class="ffunnelhost" tabindex="0" role="group" aria-label="Funnel. Left and right arrow keys step ' +
          'through the stages, Home empties it, End fills it." aria-describedby="fstep"></div></div>' +
      '<div class="fview' + (view === 'bars' ? ' is-on' : '') + '" data-view="bars"' + (view === 'bars' ? '' : ' inert aria-hidden="true"') + '>' +
        funnelBarsHtml(M) + '</div></div>';

    return '<div class="fpanel">' + panel('Where applicants drop out', seg + pv('OBSERVED') + csvBtn('funnel', 'Stages CSV') + csvBtn('funnel-rules', 'Rules CSV'),
      lede + key + views +
      '<div id="fdrill" class="fdrill" role="region" aria-live="polite" aria-labelledby="fdrill-h"' + N('fdrill') + '>' +
        drillHtml(M) + '</div>' +
      caveat('sans', 'NOTE',
        'Every stage here is derived by replaying the rules, never assigned. The reason ' +
        'attached to each declined applicant is the rule that actually caught them.'), N('funnel')) + '</div>';
  }

  /* Wiring. The view switch and the drill-down update the panel in place, never re-rendering
   * the page, so the cross-fade can run and focus is never lost. */
  function syncDrillTriggers(root) {
    var M = funnelModel();
    root.querySelectorAll('[data-drill]').forEach(function (t) {
      var id = t.getAttribute('data-drill'), open = S.fdrill === id, s = stageById(M, id);
      t.setAttribute('aria-expanded', String(open));
      t.classList.toggle('is-open', open);
      if (t.tagName.toLowerCase() === 'button') {
        t.setAttribute('aria-label', (open ? 'Hide' : 'Show') + ' the rules behind ' + s.label);
      }
    });
    root.querySelectorAll('.frow[data-stage]').forEach(function (r) {
      r.classList.toggle('is-open', r.getAttribute('data-stage') === S.fdrill);
    });
  }

  function activeView(root) { return root.querySelector('.fview.is-on'); }

  function calmMotion() {
    return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  function setDrill(root, id, trigger, viaKeyboard) {
    var closing = !id || S.fdrill === id;
    var was = S.fdrill;
    S.fdrill = closing ? null : id;
    S.fdrillAll = false;
    root.querySelector('#fdrill').innerHTML = drillHtml(funnelModel());
    var host = root.querySelector('.ffunnelhost');
    if (host) drawFunnel(host);
    syncDrillTriggers(root);
    if (S.spec) applySpec();
    if (S.fdrill) {
      // Focus moves to the heading either way; the ring shows only when a keyboard opened it.
      var h = root.querySelector('#fdrill-h');
      if (h) {
        h.classList.toggle('is-quiet', !viaKeyboard);
        h.addEventListener('blur', function () { h.classList.remove('is-quiet'); }, { once: true });
        h.focus({ preventScroll: true });
      }
      var region = root.querySelector('#fdrill');
      requestAnimationFrame(function () {
        region.scrollIntoView({ block: 'nearest', behavior: calmMotion() ? 'auto' : 'smooth' });
      });
    } else {
      // Closing returns focus to whatever opened it, in the view that is showing now.
      var back = activeView(root).querySelector('[data-drill="' + (trigger || was) + '"]');
      if (back) back.focus();
    }
  }

  function setView(root, view) {
    if (S.fview === view) return;
    S.fview = view;
    root.querySelectorAll('.fview').forEach(function (v) {
      var on = v.getAttribute('data-view') === view;
      v.classList.toggle('is-on', on);
      if (on) { v.removeAttribute('inert'); v.removeAttribute('aria-hidden'); }
      else { v.setAttribute('inert', ''); v.setAttribute('aria-hidden', 'true'); }
    });
    root.querySelectorAll('[data-fview]').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.getAttribute('data-fview') === view));
    });
    if (S.spec) applySpec();
  }

  function toggleAllRules(root) {
    S.fdrillAll = !S.fdrillAll;
    root.querySelector('#fdrill').innerHTML = drillHtml(funnelModel());
    var b = root.querySelector('[data-drill-more]');
    if (b) b.focus();
    if (S.spec) applySpec();
  }

  /* `entering` is true when the screen is opened, not re-rendered in place: only then does the
   * funnel pour. */
  function mountFunnel(root, entering) {
    var panelEl = root.querySelector('.fpanel');
    if (!panelEl) return;
    var host = panelEl.querySelector('.ffunnelhost');
    drawFunnel(host);
    if (entering && S.fview === 'funnel') emptyFunnel(host);
    panelEl.addEventListener('click', function (e) {
      if (e.target.closest('[data-freset]')) { emptyFunnel(host); return; }
      var v = e.target.closest('[data-fview]');
      if (v) { setView(panelEl, v.getAttribute('data-fview')); return; }
      if (e.target.closest('[data-drill-close]')) { setDrill(panelEl, null); return; }
      if (e.target.closest('[data-drill-more]')) { toggleAllRules(panelEl); return; }
      var t = e.target.closest('[data-drill]');
      // A click with detail 0 came from the keyboard (Enter or Space on a button).
      if (t) setDrill(panelEl, t.getAttribute('data-drill'), t.getAttribute('data-drill'), e.detail === 0);
    });
    host.addEventListener('focus', function () {
      var el = document.getElementById('fstep');
      if (el && !el.textContent && FANIM.p === null) { el.textContent = '← → step through the stages'; el.classList.add('is-hint'); }
    });
    host.addEventListener('blur', function () {
      host.classList.remove('is-quiet');
      var el = document.getElementById('fstep');
      if (el && el.classList.contains('is-hint')) { el.textContent = ''; el.classList.remove('is-hint'); }
    });
    panelEl.addEventListener('keydown', function (e) {
      // Scoped to the funnel: the keys step it only when focus is on it or on one of its arrows.
      if (e.target.closest && e.target.closest('.ffunnelhost') && stepFunnel(e, host)) {
        var hint = document.getElementById('fstep');
        if (hint) hint.classList.remove('is-hint');
        return;
      }
      // One keyboard path for both views' triggers (chevron button or SVG arrow). preventDefault
      // stops the button's own click, so it opens once.
      var t = e.target.closest && e.target.closest('[data-drill]');
      if (t && (e.key === 'Enter' || e.key === ' ')) {
        e.preventDefault();
        setDrill(panelEl, t.getAttribute('data-drill'), t.getAttribute('data-drill'), true);
        return;
      }
      if (e.key === 'Escape' && S.fdrill && e.target.closest('#fdrill')) setDrill(panelEl, null);
    });
  }

  window.addEventListener('resize', function () {
    clearTimeout(drawFunnel.t);
    drawFunnel.t = setTimeout(function () {
      var host = document.querySelector('.ffunnelhost');
      if (host) drawFunnel(host);
    }, 120);
  });

  function sourcePanel() {
    var maxD = Math.max.apply(null, F.by_channel.map(function (r) { return r.declines; }));
    var rows = F.by_channel.map(function (r) {
      return '<tr><td>' + esc(r.channel) + '</td>' +
        '<td class="num">' + n0(r.applicants) + '</td>' +
        '<td class="num">' + r.approval_rate.toFixed(1) + '%</td>' +
        '<td style="width:130px">' + bar(r.declines, maxD) + '</td>' +
        '<td class="num">' + n0(r.declines) + '</td>' +
        '<td class="num">' + r.share_of_all_declines.toFixed(1) + '%</td></tr>';
    });
    return panel('Declines by channel', pv('OBSERVED') + csvBtn('channels'),
      table('<th>Channel</th><th class="num">Applicants</th><th class="num"' + N('th_ch_approval') + '>Approval</th>' +
            '<th' + N('th_ch_declines') + '>Declines</th><th class="num"' + N('th_ch_n') + '>n</th>' +
            '<th class="num"' + N('th_ch_share') + '>Share of declines</th>', rows), N('ch_panel'));
  }

  /* =============================================================== screen 2
   * Decline drivers is the diagnosis, read-only: which rules cost approvals, and which are safe to
   * loosen. Every rule's group (verdict) and every count comes from the engine; the page sorts
   * nothing and judges nothing. Each rule ends with a way into the Simulator, where changes are made. */
  var DR = { open: {}, all: {} };
  var DR_TOP = 5;
  var DR_COLLAPSED = { overlap: true, not_relaxable: true, never: true, unevaluated: true };

  function drGroup(id) { return (F.drivers_summary.groups || []).filter(function (g) { return g.id === id; })[0] || { rules: 0, approvals_gained: 0 }; }
  function info(text) { return '<span class="drinfo" tabindex="0" role="img" aria-label="' + esc(text) + '" title="' + esc(text) + '">ⓘ</span>'; }

  function drTiles() {
    var rv = drGroup('review'), ea = drGroup('earning'), ne = drGroup('no_estimate'), X = F.drivers_summary;
    return '<div class="tiles c3 drtiles">' +
      tile('Could gain at little extra risk ' + pv('INFERRED'), '+' + n0(rv.approvals_gained),
           n0(rv.rules) + ' ' + (rv.rules === 1 ? 'rule' : 'rules') + ' · approvals if each is loosened on its own',
           '', N('dr_t_review')) +
      tile('Earning their place ' + pv('INFERRED'), n0(ea.rules) + ' <small>rules</small>',
           'they decline applicants riskier than ' + pct(X.threshold, 1), '', N('dr_t_earning')) +
      tile('Can\'t be judged ' + pv('NOT_MODELLED', 'NO ESTIMATE'), n0(ne.rules) + ' <small>rules</small>',
           'too few applicants, or unlike anything the bank has booked', '', N('dr_t_noest')) +
      '</div>';
  }

  function drLead() {
    // The tiles carry the totals; the one line names the rule to look at first.
    var top = F.drivers.filter(function (r) { return r.verdict === 'review'; })[0];
    if (!top) return '';
    return caveat('warn', 'FINDING', '<strong>Look first at “' + esc(top.label) + '”.</strong> Loosened on its own it would add ' +
      n0(top.approvals_gained) + ' approvals at an estimated ' + pct(top.est_bad_rate_if_relaxed, 1) + ' bad rate, against ' +
      pct(F.drivers_summary.booked_bad_rate, 1) + ' on today\'s book.', N('dr_q10'));
  }

  function drLosses() {
    var L = F.drivers_summary.losses || [];
    var max = Math.max.apply(null, L.map(function (l) { return l.dropped; }).concat([1]));
    var rows = L.map(function (l) {
      var where = l.decline_rules ? '<a href="#dr-groups" class="drlink" data-dr-jump>Rules below</a>'
        : l.loss_type === 'customer' ? '<span class="verdict">the applicant\'s choice, not a rule</span>'
        : '<span class="verdict">the offer, not a rule: loosened by caps, not in the Simulator</span>';
      return '<tr class="' + (l.loss_type === 'customer' ? 'is-customer' : 'is-lender') + '"><td><b>' + esc(l.label) + '</b>' +
        (l.sublabel ? '<br><span class="verdict">' + esc(l.sublabel) + '</span>' : '') + '</td>' +
        '<td class="num">' + n0(l.dropped) + '<br><span class="verdict">' + pct(l.share_of_applicants, 1) + ' of applicants</span></td>' +
        '<td style="width:120px">' + bar(l.dropped, max) + '</td>' +
        '<td class="drreasons">' + l.reasons.map(function (r) { return esc(r.label) + ' <span class="fig">' + n0(r.count) + '</span>'; }).join('<br>') + '</td>' +
        '<td>' + where + '</td></tr>';
    });
    return panel('Where applicants are lost', pv('OBSERVED') + csvBtn('losses'),
      '<div class="drlosstab">' + table('<th>Stage</th><th class="num">Lost</th><th></th><th' + N('dr_reasons') + '>Biggest reasons</th><th></th>', rows) +
      '</div>', N('dr_losses'));
  }

  function drChart() {
    var X = F.drivers_summary;
    var pts = F.drivers.filter(function (r) { return (r.verdict === 'review' || r.verdict === 'earning') && r.est_bad_rate_if_relaxed !== null; });
    var none = F.drivers.filter(function (r) { return r.verdict === 'no_estimate'; });
    if (!pts.length && !none.length) return '';
    var W = 620, H = 300, L = 56, R = 16, T = 14, B = 64, STRIP = 14;
    var xmax = Math.max.apply(null, pts.concat(none).map(function (r) { return r.approvals_gained || 0; }).concat([10])) * 1.08;
    var ys = pts.map(function (r) { return r.est_bad_rate_if_relaxed; }).concat([X.threshold, X.booked_bad_rate]);
    var y0 = 0, y1 = Math.max.apply(null, ys) * 1.1;
    function Xs(v) { return L + v * (W - L - R) / xmax; }
    function Ys(v) { return T + (y1 - v) * (H - T - B) / (y1 - y0); }
    var g = '<defs><pattern id="drhatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">' +
      '<rect width="6" height="6" class="hatch-nm"/><line x1="0" y1="0" x2="0" y2="6" class="drhatch-l"/></pattern></defs>';
    for (var i = 0; i <= 4; i++) {
      var xv = xmax * i / 4, yv = y1 * i / 4;
      g += '<line class="grid" x1="' + Xs(xv) + '" x2="' + Xs(xv) + '" y1="' + T + '" y2="' + (H - B) + '"/>' +
           '<text class="tick" x="' + Xs(xv) + '" y="' + (H - B + 16) + '" text-anchor="middle">' + n0(xv) + '</text>' +
           '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + Ys(yv) + '" y2="' + Ys(yv) + '"/>' +
           '<text class="tick" x="' + (L - 8) + '" y="' + (Ys(yv) + 4) + '" text-anchor="end">' + pct(yv, 0) + '</text>';
    }
    g += '<text class="axis" x="' + ((L + W - R) / 2) + '" y="' + (H - 4) + '" text-anchor="middle">Approvals gained if loosened on its own →</text>' +
         '<text class="axis" x="14" y="' + ((T + H - B) / 2) + '" text-anchor="middle" transform="rotate(-90 14 ' + ((T + H - B) / 2) + ')">Bad rate of those gained →</text>';
    g += '<line class="drbook" x1="' + L + '" x2="' + (W - R) + '" y1="' + Ys(X.booked_bad_rate) + '" y2="' + Ys(X.booked_bad_rate) + '"/>' +
         '<text class="drbook-t" x="' + (W - R - 4) + '" y="' + (Ys(X.booked_bad_rate) + 14) + '" text-anchor="end">today\'s book ' + pct(X.booked_bad_rate, 1) + '</text>' +
         '<line class="drline" x1="' + L + '" x2="' + (W - R) + '" y1="' + Ys(X.threshold) + '" y2="' + Ys(X.threshold) + '"/>' +
         '<text class="drline-t" x="' + (W - R - 4) + '" y="' + (Ys(X.threshold) - 6) + '" text-anchor="end">earns its place above ' + pct(X.threshold, 1) + '</text>';
    pts.forEach(function (r) {
      g += '<g class="pt is-inf' + (r.verdict === 'review' ? ' is-review' : '') + '"><title>' + esc(r.label + ' · ' + n0(r.approvals_gained) +
           ' approvals · bad rate ' + pct(r.est_bad_rate_if_relaxed, 1)) + '</title>' +
           '<circle cx="' + Xs(r.approvals_gained || 0) + '" cy="' + Ys(r.est_bad_rate_if_relaxed) + '" r="6"/></g>';
    });
    // No estimate: no height to give them, so they sit on a hatched strip under the axis.
    var sy = H - B + 26;
    g += '<rect x="' + L + '" y="' + sy + '" width="' + (W - L - R) + '" height="' + STRIP + '" fill="url(#drhatch)" class="drstrip"/>' +
         '<text class="tick" x="' + (L - 8) + '" y="' + (sy + 11) + '" text-anchor="end">none</text>';
    none.forEach(function (r) {
      g += '<g class="drnone"><title>' + esc(r.label + ' · ' + n0(r.approvals_gained) + ' approvals · no estimate: ' + (r.risk_note || '')) + '</title>' +
           '<line x1="' + Xs(r.approvals_gained || 0) + '" x2="' + Xs(r.approvals_gained || 0) + '" y1="' + sy + '" y2="' + (sy + STRIP) + '"/></g>';
    });
    return panel('What each rule would give, and at what risk', pv('OBSERVED', 'APPROVALS') + ' ' + pv('INFERRED', 'RISK'),
      '<div class="simchart drchart"><svg viewBox="0 0 ' + W + ' ' + (H + STRIP + 12) + '" role="img" aria-label="Approvals each rule would add ' +
        'against the estimated bad rate of those applicants">' + g + '</svg></div>' +
      '<p class="simnote">Dots below the line are approvals the rule costs without buying safety. Rules with no estimate sit on the hatched strip.</p>',
      N('dr_chart'));
  }

  function drRisk(r) {
    if (r.verdict === 'not_relaxable') return pv('NOT_MODELLED', 'NOT RELAXABLE');
    if (r.verdict === 'overlap') return '<span class="verdict">frees nobody on its own</span>';
    if (r.verdict === 'no_estimate') return '<span title="' + esc(r.risk_note || '') + '">' + pv('NOT_MODELLED', 'NO ESTIMATE') + '</span>';
    return pv('INFERRED', pct(r.est_bad_rate_if_relaxed, 1));
  }

  function drRow(r) {
    var gain = r.approvals_gained === null || r.approvals_gained === undefined ? '<span class="nodata">—</span>' : '+' + n0(r.approvals_gained);
    var tryIt = r.verdict !== 'not_relaxable'
      ? '<button class="drtry" data-dr-try="' + esc(r.rule_id) + '">Try in Simulator →</button>' : '';
    return '<tr><td><span class="drname">' + esc(r.label) + '</span><br><span class="rid">' + esc(r.rule_id) + '</span>' +
      (r.policy_code ? ' <span class="rid">· ' + esc(r.policy_code) + '</span>' : '') +
      (r.verdict === 'not_relaxable' ? '<br><span class="verdict">rests on ' + esc(r.fields) + '</span>' : '') + '</td>' +
      '<td class="num"><span class="drgain">' + gain + '</span><br><span class="verdict">' + n0(r.declines) + ' declines</span></td>' +
      '<td>' + drRisk(r) + '</td><td class="drcta">' + tryIt + '</td></tr>';
  }

  function drGroupBlock(id, label, list, rowFn, head) {
    if (!list.length && DR_COLLAPSED[id]) return '';     // an empty closed group says nothing
    var open = DR.open[id] !== undefined ? DR.open[id] : !DR_COLLAPSED[id];
    var shown = DR.all[id] ? list : list.slice(0, DR_TOP);
    return '<details class="drgroup" data-dr-group="' + id + '"' + (open ? ' open' : '') + '>' +
      '<summary><b>' + esc(label) + '</b><span class="fig">' + n0(list.length) + '</span></summary>' +
      (list.length ? '<div class="drtab">' + table(head, shown.map(rowFn)) + '</div>' +
        (list.length > shown.length ? '<button class="fmore" data-dr-all="' + id + '">Show all ' + n0(list.length) + '</button>' : '')
        : '<p class="note">None.</p>') + '</details>';
  }

  function drGroups() {
    var head = '<th' + N('th_rule') + '>Rule</th><th class="num"' + N('th_gain') + '>Approvals gained if loosened ' +
      info('Switching off a rule whose declines are all shared with another rule frees nobody: the other rule still catches them. ' +
           'So this counts only the applicants no other rule declines, and only those who would then be booked.') + '</th>' +
      '<th' + N('th_relaxed') + '>Bad rate if loosened ' +
      info('Declined applicants have no repayment history, so this is inferred by a model trained on booked loans. ' +
           'Where a group is too small or unlike anything booked, the engine gives no estimate instead of a number.') + '</th><th></th>';
    var body = Object.keys(F.drivers_summary.groups.reduce(function (o, g) { o[g.id] = 1; return o; }, {})).map(function (id) {
      var g = drGroup(id);
      return drGroupBlock(id, g.label, F.drivers.filter(function (r) { return r.verdict === id; }), drRow, head);
    }).join('') +
      drGroupBlock('never', 'Catch nobody', F.drivers_summary.never_fire, function (r) {
        return '<tr><td><span class="drname">' + esc(r.label) + '</span><br><span class="rid">' + esc(r.rule_id) + '</span></td>' +
          '<td colspan="3" class="verdict">declines no applicant in this period</td></tr>';
      }, '<th>Rule</th><th colspan="3"></th>') +
      drGroupBlock('unevaluated', 'Not evaluated', F.drivers_summary.not_evaluated || [], function (r) {
        return '<tr><td><span class="drname">' + esc(r.label) + '</span><br><span class="rid">' + esc(r.rule_id) + '</span></td>' +
          '<td colspan="3" class="verdict">reads a value the applicant data does not supply</td></tr>';
      }, '<th>Rule</th><th colspan="3"></th>');
    return '<div id="dr-groups">' + panel('Rules by verdict', pv('OBSERVED', 'COUNTS') + ' ' + pv('INFERRED', 'RISK') + csvBtn('drivers'), body, N('dr_rank')) + '</div>';
  }

  function pageDrivers() {
    return '<div class="pagehead"><h2' + N('dr_head') + '>Decline drivers</h2>' +
      '<p>Which rules cost approvals, and which are safe to loosen.</p>' + periodLine() + '</div>' +
      drLead() + drTiles() + drChart() + drGroups() + drLosses();
  }

  function wireDrivers(root) {
    root.querySelectorAll('[data-dr-group]').forEach(function (d) {
      d.addEventListener('toggle', function () { DR.open[d.getAttribute('data-dr-group')] = d.open; });
    });
    root.querySelectorAll('[data-dr-all]').forEach(function (b) {
      b.addEventListener('click', function () { DR.all[b.getAttribute('data-dr-all')] = true; go('drivers', true); });
    });
    root.querySelectorAll('[data-dr-try]').forEach(function (b) {
      b.addEventListener('click', function () {
        SIM.view = 'rules'; SIM.q = b.getAttribute('data-dr-try'); SIM.filter = 'all'; SIM.picked = SIM.q;
        go('simulator');
      });
    });
    root.querySelectorAll('[data-dr-jump]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        e.preventDefault();
        var t = document.getElementById('dr-groups'); if (t) t.scrollIntoView({ behavior: calmMotion() ? 'auto' : 'smooth' });
      });
    });
  }

  /* =============================================================== screen 3
   * The simulator starts from today's rules, all on, and answers two questions in three views:
   *
   *   Set a target   "how do we reach X% approval?" — goal-seek, one recommendation in a sentence
   *   Try a change   "what if?" — story presets, two score-cutoff sliders, the busiest rules
   *   All rules      the analyst's workbench: every rule, every threshold, the sweeps
   *
   * Try a change and All rules share one scenario: an ordered list of changes, each replayed by
   * the engine behind ui/serve.py on top of the ones before it. One outcome bar at the top shows
   * the book after every change; a waterfall shows what each step added.
   *
   * With no engine running (the page opened from disk, or `serve --static`) it falls back to
   * the precomputed fixture: only the switch-offs exported in `rule_toggles` and the loosening
   * sweep cutoffs can be tried, one at a time, and goal-seek shows its two precomputed runs.
   * Every figure still comes from the engine; the page only formats. */
  var SIM = {
    live: null,          // null while checking, then true (engine) or false (fixture only)
    health: null, rules: null,
    view: 'target',      // 'target' | 'try' | 'rules' | 'saved'
    steps: [], out: null, pending: false, error: null, notice: null,
    q: '', filter: 'alone', picked: null,   // All rules: search, filter, the rule open in the detail
    shut: {}, more: {},  // stage groups closed, and stage groups showing every rule
    // Saved scenarios (the engine keeps them): the list, the compare picks and result, the save form.
    saved: null, savedLoading: false, savedErr: null, cmpPick: {}, cmp: null, cmpMax: 4, cmpPending: false, cmpErr: null,
    saving: false, savePending: false, saveErr: null, draftName: '', savedAs: null, pendingOpen: null,
    open: {},            // which disclosures are open, so a re-render keeps them open
    refocus: null,       // selector to focus again after a re-render (a slider, a switch)
    goal: { target: 25, ceiling: null, frozen: [], out: null, pending: false, error: null }
  };
  var RULE_PAGE = 25;
  var TOP_RULES = 8;
  var OPS = { lt: '<', lte: '≤', gt: '>', gte: '≥' };
  var FIELD_NAMES = { simahcreditscore: 'SIMAH score', crifscore: 'CRIF score', income: 'minimum income' };

  function api(path, body) {
    return fetch(path, body === undefined ? {} : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j.error || ('the engine answered ' + r.status));
        return j;
      });
    });
  }

  /** Decide once which mode the simulator is in. Polls while the engine is still loading. */
  function connectEngine(tries, custom) {
    if (location.protocol === 'file:') { engineUnavailable(); return; }
    api('/api/health' + ctxQuery()).then(function (h) {
      if (h.ready) {
        SIM.health = h;
        if (SIM.goal.ceiling === null) SIM.goal.ceiling = +(h.bad_rate_ceiling * 100).toFixed(1);
        return api('/api/rules' + ctxQuery()).then(function (j) {
          SIM.rules = j.rules; SIM.live = true; SIM.steps = []; SIM.out = null;
          refreshSim();
          renderCtx();
          if (custom) setContext(custom);
        });
      }
      if (h.loading && (tries || 0) < 60) { setTimeout(function () { connectEngine((tries || 0) + 1, custom); }, 1500); return; }
      engineUnavailable();
    }).catch(engineUnavailable);
  }
  function engineUnavailable() {
    SIM.live = false;
    SIM.rules = F.rule_catalogue || [];
    if (SIM.goal.ceiling === null) SIM.goal.ceiling = +(F.meta.bad_rate_ceiling * 100).toFixed(1);
    refreshSim();
  }
  function refreshSim() { if (S.page === 'simulator') go('simulator', true); }

  /* ---- the score cutoffs offered as sliders: the engine's own list, or the fixture's sweeps */
  function cutoffs() {
    if (SIM.live && SIM.health && SIM.health.cutoffs) return SIM.health.cutoffs;
    return (F.sweeps || []).map(function (sw) {
      return { field: sw.field, label: sw.label, from: sw.from,
               values: sw.rows.map(function (r) { return r.cutoff; }) };
    });
  }
  /** An engine started before score cutoffs existed does not list them, and refuses the change. */
  function cutoffsAvailable() { return !SIM.live || !!(SIM.health && SIM.health.cutoffs); }
  function ceilingRate() { return SIM.health ? SIM.health.bad_rate_ceiling : F.meta.bad_rate_ceiling; }

  /* ---- the scenario: an ordered list of changes, at most one per threshold or cutoff */
  function stepIndex(fn) { for (var i = 0; i < SIM.steps.length; i++) if (fn(SIM.steps[i])) return i; return -1; }
  function stepsFor(rid) { return SIM.steps.filter(function (s) { return s.rule_id === rid; }); }
  function cutoffStep(field) { return SIM.steps.filter(function (s) { return s.type === 'cutoff' && s.field === field; })[0]; }
  function precomputed(rid) { return (F.rule_toggles || []).filter(function (t) { return t.rule_id === rid; })[0]; }
  function precomputedCutoff(ch) {
    var sw = (F.sweeps || []).filter(function (s) { return s.field === ch.field && s.from === ch.from; })[0];
    return sw && sw.rows.filter(function (r) { return r.cutoff === ch.to; })[0];
  }
  function canTryStep(ch) {
    if (ch.type === 'cutoff' && !cutoffsAvailable()) return false;
    return SIM.live || canPrecompute(ch);
  }
  function canPrecompute(ch) {
    return ch.type === 'off' ? !!precomputed(ch.rule_id) : ch.type === 'cutoff' ? !!precomputedCutoff(ch) : false;
  }

  /** Fixture mode: one precomputed change, shaped like an engine result. */
  function fixtureStep(ch) {
    if (ch.type === 'off') {
      var t = precomputed(ch.rule_id);
      return t && Object.assign({}, t, { change_direction: 'loosen', added_pp: t.approval_change_pp,
        added_swap_in: t.swap_in, added_swap_out: t.swap_out });
    }
    var r = ch.type === 'cutoff' && precomputedCutoff(ch);
    return r && { approval_rate: r.approval_rate, approval_change_pp: r.approval_change_pp,
      swap_in: r.swap_in, swap_out: r.swap_out, expected_bad_rate: r.expected_bad_rate,
      risk_known: r.risk_known, verdict: r.note, swap_in_by_channel: {}, change_direction: 'loosen',
      added_pp: r.approval_change_pp, added_swap_in: r.swap_in, added_swap_out: r.swap_out };
  }

  /** Replace the scenario, replay it, and keep the old one if the engine refuses. */
  function propose(steps, after) {
    SIM.error = null; SIM.notice = null;
    if (!steps.length) { SIM.steps = []; SIM.out = null; refreshSim(); return; }
    if (!SIM.live) {
      var last = steps[steps.length - 1];
      var step = fixtureStep(last);
      if (!step) { SIM.error = 'This change needs the engine running. Start it with python -m ui.serve.'; refreshSim(); return; }
      SIM.steps = [last];
      SIM.out = { steps: [step], result: step };
      refreshSim();
      return;
    }
    SIM.pending = true; refreshSim();
    var seq = CTX.seq, ok = false;
    api('/api/simulate', ctxBody({ changes: steps })).then(function (out) {
      if (seq !== CTX.seq) return;           // the period changed while this was running
      SIM.steps = steps; SIM.out = out; ok = true;
    }).catch(function (e) {
      if (seq === CTX.seq) SIM.error = e.message;
    }).then(function () {
      if (seq !== CTX.seq) return;
      SIM.pending = false;
      if (after) after(ok);
      refreshSim();
    });
  }

  function switchRule(rid, on) {
    var rest = SIM.steps.filter(function (s) { return s.rule_id !== rid; });
    if (on) { propose(rest); return; }
    // Switching off replaces any threshold edits to the same rule, in the first one's place.
    var at = stepIndex(function (s) { return s.rule_id === rid; });
    var off = { type: 'off', rule_id: rid };
    if (at < 0) { propose(rest.concat([off])); return; }
    var next = SIM.steps.slice(0, at).filter(function (s) { return s.rule_id !== rid; })
      .concat([off], SIM.steps.slice(at).filter(function (s) { return s.rule_id !== rid; }));
    propose(next);
  }

  function setThreshold(rid, field, lo, hi, today) {
    var same = (lo === today.value_low) && (hi === null || hi === today.value_high);
    var at = stepIndex(function (s) { return s.rule_id === rid && s.field === field; });
    var next = SIM.steps.slice();
    if (same) {
      if (at >= 0) next.splice(at, 1);       // back to today's value: the step goes away
    } else {
      var ch = { type: 'threshold', rule_id: rid, field: field, value_low: lo };
      if (hi !== null) ch.value_high = hi;
      if (at >= 0) next[at] = ch; else next.push(ch);
    }
    propose(next);
  }

  /** Move one score cutoff. Back to today's value removes the step. */
  function setCutoff(field, from, to) {
    var at = stepIndex(function (s) { return s.type === 'cutoff' && s.field === field; });
    var next = SIM.steps.slice();
    if (to === from) { if (at >= 0) next.splice(at, 1); }
    else {
      var ch = { type: 'cutoff', field: field, from: from, to: to };
      if (at >= 0) next[at] = ch; else next.push(ch);
    }
    propose(next);
  }

  /* ---- words */
  function num(v) { return v === null || v === undefined ? '—' : Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 }); }
  function fieldName(f) { return String(f).split('.').pop(); }
  function fieldLabel(f) { return FIELD_NAMES[f] || fieldName(f); }
  /** A change in percentage points, as a CEO reads it: "+3.4 pts". */
  function ptsChange(v, dp) {
    if (v === null || v === undefined) return '—';
    var x = Number(v);
    return (x > 0 ? '+' : x < 0 ? '−' : '') + Math.abs(x).toFixed(dp === undefined ? 1 : dp) + ' pts';
  }
  function condText(t) {
    if (t.operator === 'between') return fieldName(t.field) + ' between ' + num(t.value_low) + ' and ' + num(t.value_high);
    if (t.operator === 'outside') return fieldName(t.field) + ' outside ' + num(t.value_low) + '–' + num(t.value_high);
    return fieldName(t.field) + ' ' + (OPS[t.operator] || t.operator) + ' ' + num(t.value_low);
  }
  function ruleById(rid) { return (SIM.rules || []).filter(function (r) { return r.rule_id === rid; })[0]; }
  function ruleName(rid) { var r = ruleById(rid); return r ? r.label : rid; }
  function stepText(s) {
    if (s.type === 'off') return 'Switch off “' + ruleName(s.rule_id) + '”';
    if (s.type === 'cutoff') return (s.to < s.from ? 'Lower' : 'Raise') + ' the ' + fieldLabel(s.field) +
      ' cutoff from ' + num(s.from) + ' to ' + num(s.to);
    return ruleName(s.rule_id) + ': ' + fieldLabel(s.field) + ' → ' + num(s.value_low) +
      (s.value_high !== undefined ? '–' + num(s.value_high) : '');
  }
  function signed(v) { return v === null || v === undefined ? '—' : (v > 0 ? '+' : v < 0 ? '−' : '') + n0(Math.abs(v)); }
  function joinWords(list) {
    if (list.length < 2) return list.join('');
    return list.slice(0, -1).join(', ') + ' and ' + list[list.length - 1];
  }

  /** A native disclosure whose open state survives a re-render. */
  function disclose(key, summary, body, note) {
    return '<details class="simmore" data-sim-open="' + key + '"' + (SIM.open[key] ? ' open' : '') + '>' +
      '<summary' + (note || '') + '>' + summary + '</summary><div class="simmorebody">' + body + '</div></details>';
  }

  function lockIcon(r) {
    if (!r.locked && !r.fixed_field) return '';
    return '<span class="rlock ' + (r.locked ? 'is-locked' : 'is-fixed') + '" aria-hidden="true">' +
      '<svg width="10" height="11" viewBox="0 0 10 11"><path d="M2.5 5V3.5a2.5 2.5 0 0 1 5 0V5" fill="none" stroke="currentColor" stroke-width="1.2"/>' +
      '<rect x="1" y="5" width="8" height="5.5" rx="1.2" stroke="currentColor" stroke-width="1.2"/></svg></span>';
  }

  /* ---- the outcome bar: the book after every change, always in view */
  function outcomeBar() {
    var h = F.headline, t = SIM.out && SIM.out.result, ceil = ceilingRate();
    var busy = SIM.pending ? '<span class="simbusy">Replaying…</span>' : '';
    if (!t) {
      return '<div class="simout is-today">' +
        '<div class="so"><span class="k">Approval today</span><span class="v fig c-obs">' + pct(h.approval_rate) + '</span></div>' +
        '<div class="so"><span class="k">Bad rate today</span><span class="v fig c-obs">' + pct(h.booked_bad_rate, 2) + '</span>' +
          '<span class="d">limit ' + pct(ceil, 1) + '</span></div>' +
        '<div class="so so-hint">' + (busy || 'Pick a change below to see what moves.') + '</div></div>';
    }
    var breach = t.risk_known && t.expected_bad_rate > ceil;
    var bad = t.risk_known
      ? '<span class="' + (t.swap_in ? 'c-inf' : 'c-obs') + '">' + pct(t.expected_bad_rate, 2) + '</span>'
      : '<span class="c-nm">no estimate</span>';
    return '<div class="simout">' +
      '<div class="so"><span class="k"' + N('t_approval') + '>Approval</span>' +
        '<span class="v fig"><s>' + pct(h.approval_rate) + '</s> → <span class="c-obs">' + pct(t.approval_rate) + '</span></span>' +
        '<span class="d">' + ptsChange(t.approval_change_pp) + '</span></div>' +
      '<div class="so' + (breach ? ' is-breach' : '') + '"><span class="k"' + N('t_bad') + '>Bad rate</span>' +
        '<span class="v fig"><s>' + pct(h.booked_bad_rate, 2) + '</s> → ' + bad + '</span>' +
        '<span class="d">' + (breach ? 'above the ' : 'limit ') + pct(ceil, 1) + (breach ? ' limit' : '') + '</span></div>' +
      '<div class="so"><span class="k"' + N('t_in') + '>Newly approved</span><span class="v fig">' + n0(t.swap_in) + '</span>' +
        '<span class="d">applicants</span></div>' +
      (t.swap_out ? '<div class="so"><span class="k"' + N('t_out') + '>Newly declined</span><span class="v fig">' + n0(t.swap_out) + '</span>' +
        '<span class="d">bad rate ' + pct(t.swap_out_observed_bad_rate, 1) + '</span></div>' : '') +
      (busy ? '<div class="so so-hint">' + busy + '</div>' : '') +
      '</div>';
  }

  /** Why, and by channel: behind a disclosure under the outcome bar. */
  function outcomeDetails() {
    var t = SIM.out && SIM.out.result;
    if (!t) return '';
    var chans = Object.keys(t.swap_in_by_channel || {});
    var tightens = t.swap_out > 0;
    var rows = chans.map(function (k) {
      var v = t.swap_in_by_channel[k];
      return '<tr><td>' + esc(k) + '</td><td class="num">' + n0(v.swap_in) + '</td>' +
        (tightens ? '<td class="num">' + n0(v.swap_out) + '</td>' : '') + '</tr>';
    });
    return disclose('why', 'Why, and by channel',
      '<p class="simverdict"' + N('verdict_tag') + '>' + esc(t.verdict) + '</p>' +
      (rows.length ? '<div class="simcsv">' + csvBtn('scenario-channels') + '</div>' + table('<th' + N('th_sw_channel') + '>Channel</th><th class="num">Newly approved</th>' +
        (tightens ? '<th class="num">Newly declined</th>' : ''), rows) : ''));
  }

  function legend() {
    return '<div class="simlegend"' + N('sim_legend') + '><span><i class="c-obs"></i>counted</span>' +
      '<span><i class="c-inf"></i>estimated (never booked)</span>' +
      '<span><i class="c-nm"></i>no estimate</span></div>';
  }

  /* ---- one chart: approval against bad rate, with the ceiling as a line */
  function frontier(points, opts) {
    var ceil = ceilingRate(), target = opts.target;
    var plotted = points.filter(function (p) { return p.y !== null && p.y !== undefined; });
    var xs = plotted.map(function (p) { return p.x; }).concat(target ? [target] : []);
    var ys = plotted.map(function (p) { return p.y; }).concat([ceil]);
    var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs);
    var y0 = Math.min.apply(null, ys), y1 = Math.max.apply(null, ys);
    var xpad = Math.max(0.005, (x1 - x0) * 0.12), ypad = Math.max(0.002, (y1 - y0) * 0.12);
    x0 -= xpad; x1 += xpad; y0 -= ypad; y1 += ypad;
    var W = 560, H = opts.compact ? 210 : 300, L = 56, R = 16, T = 14, B = 42;
    function X(v) { return L + (v - x0) * (W - L - R) / (x1 - x0); }
    function Y(v) { return T + (y1 - v) * (H - T - B) / (y1 - y0); }
    var g = '';
    // Axes and gridlines: four ticks each way.
    for (var i = 0; i <= 4; i++) {
      var xv = x0 + (x1 - x0) * i / 4, yv = y0 + (y1 - y0) * i / 4;
      g += '<line class="grid" x1="' + X(xv) + '" x2="' + X(xv) + '" y1="' + T + '" y2="' + (H - B) + '"/>' +
           '<text class="tick" x="' + X(xv) + '" y="' + (H - B + 16) + '" text-anchor="middle">' + pct(xv, 1) + '</text>' +
           '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(yv) + '" y2="' + Y(yv) + '"/>' +
           '<text class="tick" x="' + (L - 8) + '" y="' + (Y(yv) + 4) + '" text-anchor="end">' + pct(yv, 1) + '</text>';
    }
    g += '<text class="axis" x="' + ((L + W - R) / 2) + '" y="' + (H - 4) + '" text-anchor="middle">Approval rate →</text>' +
         '<text class="axis" x="14" y="' + ((T + H - B) / 2) + '" text-anchor="middle" transform="rotate(-90 14 ' + ((T + H - B) / 2) + ')">Bad rate →</text>';
    // Above the ceiling is out of bounds.
    g += '<rect class="over" x="' + L + '" y="' + T + '" width="' + (W - L - R) + '" height="' + Math.max(0, Y(ceil) - T) + '"/>' +
         '<line class="ceil" x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(ceil) + '" y2="' + Y(ceil) + '"/>' +
         '<text class="lbl ceil-t" x="' + (W - R - 4) + '" y="' + (Y(ceil) - 6) + '" text-anchor="end">bad-rate limit ' + pct(ceil, 1) + '</text>';
    if (target) {
      g += '<line class="tgt" x1="' + X(target) + '" x2="' + X(target) + '" y1="' + T + '" y2="' + (H - B) + '"/>' +
           '<text class="lbl tgt-t" x="' + (X(target) - 6) + '" y="' + ((T + H - B) / 2) + '" text-anchor="end">target ' + pct(target, 1) + '</text>';
    }
    var today = plotted.filter(function (p) { return p.kind === 'today'; })[0];
    plotted.forEach(function (p) {
      if (p.kind !== 'today' && today) {
        g += '<line class="move" x1="' + X(today.x) + '" y1="' + Y(today.y) + '" x2="' + X(p.x) + '" y2="' + Y(p.y) + '"/>';
      }
    });
    // Points close together (goal-seek options often are) take turns labelling above and below.
    var byX = plotted.slice().sort(function (a, b) { return a.x - b.x; });
    byX.forEach(function (p, i) {
      var near = i > 0 && Math.abs(X(p.x) - X(byX[i - 1].x)) < 40 && Math.abs(Y(p.y) - Y(byX[i - 1].y)) < 24;
      p.below = near && !byX[i - 1].below;
    });
    plotted.forEach(function (p) {
      g += '<g class="pt ' + p.cls + '"><title>' + esc(p.title) + '</title>' +
           '<circle cx="' + X(p.x) + '" cy="' + Y(p.y) + '" r="' + (p.kind === 'today' ? 6 : 7) + '"/>' +
           '<text class="lbl" x="' + X(p.x) + '" y="' + (p.below ? Y(p.y) + 22 : Y(p.y) - 12) + '" text-anchor="middle">' +
           esc(p.short || p.label) + '</text></g>';
    });
    var missing = points.filter(function (p) { return p.y === null || p.y === undefined; });
    return '<div class="simchart"' + N('sim_chart') + '><svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' +
      esc(opts.aria) + '">' + g + '</svg>' +
      (missing.length ? '<p class="simnote">Not plotted, no bad-rate estimate: ' +
        esc(missing.map(function (p) { return p.label; }).join(', ')) + ' (approval ' +
        missing.map(function (p) { return pct(p.x); }).join(', ') + ').</p>' : '') + '</div>';
  }

  function todayPoint() {
    return { kind: 'today', cls: 'is-today', x: F.headline.approval_rate, y: F.headline.booked_bad_rate,
             label: 'Today', title: 'Today: approval ' + pct(F.headline.approval_rate) + ', bad rate ' + pct(F.headline.booked_bad_rate, 2) };
  }
  function resultPoint(r, label, kind) {
    var y = r.risk_known ? r.expected_bad_rate : null;
    return { kind: kind, x: r.approval_rate, y: y, label: label,
             cls: r.risk_known && y > ceilingRate() ? 'is-breach' : (r.swap_in ? 'is-inf' : 'is-obs'),
             title: label + ': approval ' + pct(r.approval_rate) + ', bad rate ' + (r.risk_known ? pct(y, 2) : 'no estimate') };
  }

  /* ---- the waterfall: what each step added */
  function waterfall() {
    return panel('Your scenario', SIM.pending ? '<span class="simbusy">Replaying…</span>' : '', waterfallBody(), N('sim_stack'));
  }

  function waterfallBody() {
    var out = SIM.out, h = F.headline;
    if (!SIM.steps.length) {
      return '<p class="note">Nothing changed yet. Each change you make is a step. ' +
        'Add more to build on it, and remove any step to see the scenario without it.</p>';
    }
    var levels = [h.approval_rate].concat(SIM.steps.map(function (_, i) {
      return out && out.steps[i] ? out.steps[i].approval_rate : null;
    }));
    var known = levels.filter(function (v) { return v !== null; });
    var lo = Math.min.apply(null, known), hi = Math.max.apply(null, known);
    lo = Math.floor(lo * 100) / 100; hi = Math.max(hi, lo + 0.005);
    function at(v) { return Math.round((v - lo) * 1000 / (hi - lo)) / 10; }
    function row(label, from, to, fig, cls, extra) {
      var a = at(Math.min(from, to)), b = at(Math.max(from, to));
      return '<div class="wrow ' + cls + '"><div class="wl">' + label + '</div>' +
        '<div class="wt"><i style="inset-inline-start:' + a + '%;width:' + Math.max(0.6, b - a) + '%"></i></div>' +
        '<div class="wv fig">' + fig + '</div><div class="wx">' + (extra || '') + '</div></div>';
    }
    var rows = row('Today', lo, h.approval_rate, pct(h.approval_rate), 'is-base');
    SIM.steps.forEach(function (s, i) {
      var st = out && out.steps[i];
      var before = levels[i], after = levels[i + 1];
      var fig = st ? '<span' + (i === 0 ? N('sim_added') : '') + '>' + ptsChange(st.added_pp) + '</span>' : '…';
      var sub = st ? '<small>' + signed(st.added_swap_in) + ' approved' +
        (st.added_swap_out ? ' · ' + signed(st.added_swap_out) + ' declined' : '') + '</small>' : '';
      rows += row('<span class="simn">' + (i + 1) + '</span><span>' + esc(stepText(s)) + sub + '</span>',
        before === null ? lo : before, after === null ? lo : after, fig,
        st && st.added_pp < 0 ? 'is-down' : 'is-up',
        '<button class="iconbtn sm" data-sim-revert="' + i + '"' + (SIM.pending ? ' disabled' : '') +
        ' aria-label="Remove step ' + (i + 1) + '" title="Remove this step">×</button>');
    });
    var last = levels[levels.length - 1];
    if (last !== null) rows += row('After ' + (SIM.steps.length === 1 ? 'this change' : 'all ' + SIM.steps.length + ' changes'),
      lo, last, pct(last), 'is-base is-total');
    return '<div class="wfall">' + rows + '</div>' +
      '<p class="simnote">Bars show approval rate; the axis starts at ' + pct(lo, 0) + '.</p>' +
      '<button class="fmore" data-sim-reset' + (SIM.pending ? ' disabled' : '') + '>Reset to today\'s rules</button>';
  }

  /* ---- Try a change: story presets, two sliders, the busiest rules */
  function presets() {
    var list = [], rules = (SIM.rules || []).filter(function (r) { return r.editable && r.declines_alone; });
    if (rules[0]) {
      list.push({ id: 'bottleneck', t: 'Remove the biggest bottleneck',
        d: 'Switch off “' + rules[0].label + '”, which on its own stops ' + n0(rules[0].declines_alone) + ' applicants.',
        steps: [{ type: 'off', rule_id: rules[0].rule_id }] });
    }
    // The rules Decline drivers flagged, as the engine grouped them: never a second opinion here.
    // Offline, only one precomputed switch-off can be shown at a time.
    var flagged = (F.drivers || []).filter(function (r) { return r.verdict === 'review'; }).slice(0, SIM.live ? 2 : 1);
    if (flagged.length) {
      list.push({ id: 'flagged', t: 'Loosen what Decline drivers flagged',
        d: 'Switch off ' + joinWords(flagged.map(function (r) { return '“' + r.label + '”'; })) +
           ', flagged for costing approvals without buying safety.',
        steps: flagged.map(function (r) { return { type: 'off', rule_id: r.rule_id }; }) });
    }
    var sc = cutoffs()[0];
    var up = sc && sc.values.filter(function (v) { return v > sc.from; });
    if (up && up.length) {
      var to = up[Math.min(1, up.length - 1)];
      list.push({ id: 'tighten', t: 'Tighten for a downturn',
        d: 'Raise the ' + fieldLabel(sc.field) + ' cutoff from ' + num(sc.from) + ' to ' + num(to) +
           ', and see who approved today would be turned away.',
        steps: [{ type: 'cutoff', field: sc.field, from: sc.from, to: to }] });
    } else if (!SIM.live) {
      list.push({ id: 'tighten', t: 'Tighten for a downturn', d: 'Raise a score cutoff and see who approved today would be turned away.',
        steps: [] });
    }
    return list;
  }

  function presetCards() {
    var list = presets();
    if (!list.length) return '';
    return '<p class="simkicker"' + N('sim_presets') + '>Start from a story</p><div class="simpresets">' + list.map(function (p) {
      var ok = p.steps.length > 0 && (SIM.live || p.steps.length === 1) && p.steps.every(canTryStep);
      var on = ok && SIM.steps.length === p.steps.length && JSON.stringify(SIM.steps) === JSON.stringify(p.steps);
      return '<button class="simpreset' + (on ? ' is-on' : '') + '" data-sim-preset="' + p.id + '"' +
        (ok && !SIM.pending ? '' : ' disabled') + ' aria-pressed="' + on + '">' +
        '<b>' + esc(p.t) + '</b><span>' + esc(p.d) + '</span>' +
        (ok ? '' : '<em>' + (SIM.live ? 'restart the engine to use this' : 'needs the engine running') + '</em>') + '</button>';
    }).join('') + '</div>' +
      (list.some(function (p) { return p.id === 'flagged'; })
        ? '<p class="simnote"><a href="#drivers">Why these rules: Decline drivers →</a></p>' : '');
  }

  function sliders() {
    return cutoffs().map(function (c, ci) {
      var cur = cutoffStep(c.field);
      var val = cur ? cur.to : c.from;
      var vals = c.values.slice().sort(function (a, b) { return a - b; });
      var idx = vals.indexOf(val), today = vals.indexOf(c.from);
      return '<div class="simslider"' + (ci === 0 ? N('sim_cutoff') : '') + '>' +
        '<div class="sshead"><b>' + esc(c.label) + '</b><span class="fig" data-sim-val="' + esc(c.field) + '">' + num(val) +
          (val === c.from ? ' <small>today</small>' : ' <small>today ' + num(c.from) + '</small>') + '</span></div>' +
        '<input type="range" min="0" max="' + (vals.length - 1) + '" step="1" value="' + idx + '" ' +
          'data-sim-cutoff="' + esc(c.field) + '" data-from="' + c.from + '" data-values="' + vals.join(',') + '"' +
          (SIM.pending || !cutoffsAvailable() ? ' disabled' : '') + ' aria-label="' + esc(c.label) + '" style="--today:' + (today * 100 / Math.max(1, vals.length - 1)) + '%">' +
        '<div class="ssends"><span>← looser · ' + num(vals[0]) + '</span><span>' + num(vals[vals.length - 1]) +
          (vals[vals.length - 1] > c.from ? ' · stricter →' : '') + '</span></div>' +
        (cutoffsAvailable() ? '' : '<p class="simnote">The engine running now started before cutoff sliders existed. ' +
          'Restart it (<code>python -m ui.serve</code>) to use them.</p>') + '</div>';
    }).join('');
  }

  function ruleSwitches() {
    var top = (SIM.rules || []).filter(function (r) { return r.editable && r.declines_alone; }).slice(0, TOP_RULES);
    return '<ul class="simswitches"' + N('sim_levers') + '>' + top.map(function (r) {
      var off = stepsFor(r.rule_id).some(function (s) { return s.type === 'off'; });
      var ok = SIM.live || precomputed(r.rule_id);
      return '<li class="' + (off ? 'is-off' : '') + '"><label class="simtoggle' + (ok ? '' : ' is-disabled') + '">' +
        '<input type="checkbox" role="switch" data-sim-rule="' + esc(r.rule_id) + '"' + (off ? '' : ' checked') +
        (ok && !SIM.pending ? '' : ' disabled') + '><i aria-hidden="true"></i>' +
        '<span class="rn"><span class="rl">' + esc(r.label) + '</span>' +
        '<span class="rsub">only this rule stops ' + n0(r.declines_alone) + ' applicants' +
        (ok ? '' : ' · needs the engine') + '</span></span></label></li>';
    }).join('') + '</ul>';
  }

  function viewTry() {
    var pointsList = [todayPoint()];
    if (SIM.out && SIM.out.result) pointsList.push(resultPoint(SIM.out.result, 'Your scenario', 'scenario'));
    return presetCards() +
      '<div class="simgrid"><div class="simmain">' +
        panel('Score cutoffs', '', sliders()) +
        panel('The ' + TOP_RULES + ' rules that stop the most applicants', '', ruleSwitches() +
          '<button class="fmore" data-sim-view="rules">See all ' + (SIM.rules ? SIM.rules.length : '') + ' rules</button>') +
      '</div><div class="simside">' +
        panel('Your scenario', SIM.pending ? '<span class="simbusy">Replaying…</span>' : '',
          frontier(pointsList, { compact: true, aria: 'Approval rate against bad rate, today and your scenario' }) + legend() +
          '<div class="simsep"' + N('sim_stack') + '>What each change added</div>' + waterfallBody()) +
      '</div></div>';
  }

  /* ---- All rules: a picker. The list names each rule and its state; the detail changes it.
   * Every figure and every word about a rule (its sentence, stage, lock reason) comes from the
   * engine's rule catalogue; the page only arranges them. */
  function visibleRules() {
    var q = SIM.q.trim().toLowerCase();
    return (SIM.rules || []).filter(function (r) {
      if (SIM.filter === 'alone' && !r.declines_alone) return false;
      if (SIM.filter === 'editable' && !r.editable) return false;
      if (SIM.filter === 'changed' && !stepsFor(r.rule_id).length) return false;
      if (!q) return true;
      return (r.rule_id + ' ' + r.label + ' ' + (r.tests || '') + ' ' + (r.policy_code || '')).toLowerCase().indexOf(q) >= 0;
    });
  }

  /** On / Off / Changed / Locked, from the rule's lock and this scenario's steps. */
  function ruleStatus(r) {
    if (!r.editable) return { id: 'locked', t: 'Locked' };
    var mine = stepsFor(r.rule_id);
    if (mine.some(function (s) { return s.type === 'off'; })) return { id: 'off', t: 'Off' };
    return mine.length ? { id: 'changed', t: 'Changed' } : { id: 'on', t: 'On' };
  }

  function narrowRules() { return !!(window.matchMedia && window.matchMedia('(max-width: 1180px)').matches); }

  function ruleRow(r, first) {
    var st = ruleStatus(r), picked = SIM.picked === r.rule_id;
    return '<li class="simrule is-' + st.id + (picked ? ' is-picked' : '') + '">' +
      '<button type="button" class="simpick" data-sim-pick="' + esc(r.rule_id) + '" aria-expanded="' + picked + '"' +
        (first ? N('sim_pick') : '') + '>' +
        '<span class="rn"><span class="rl">' + esc(r.label) + '</span><span class="rid">' + esc(r.rule_id) + '</span></span>' +
        '<span class="rc">' + n0(r.declines_alone) + '</span>' +
        '<span class="simstatus is-' + st.id + '">' + (st.id === 'locked' ? lockIcon(r) : '') + st.t + '</span>' +
      '</button>' +
      (picked && narrowRules() ? '<div class="simdetail is-inline">' + ruleDetailBody(r) + '</div>' : '') + '</li>';
  }

  /** Rules by the stage that evaluates them, in the funnel's order. */
  function stageGroups(list) {
    var order = (F.funnel || []).map(function (s) { return s.stage; });
    var by = {};
    list.forEach(function (r) { (by[r.stage] = by[r.stage] || []).push(r); });
    return Object.keys(by).sort(function (a, b) { return order.indexOf(a) - order.indexOf(b); }).map(function (id) {
      return { id: id, label: by[id][0].stage_label || id, rules: by[id] };
    });
  }

  function rulesPanel() {
    if (!SIM.rules) return panel('Rules', '', '<p class="note">Loading the rule list…</p>');
    var all = visibleRules(), first = true, picked = SIM.picked && ruleById(SIM.picked);
    var filters = [['alone', 'Stops someone on its own'], ['editable', 'Can be changed'], ['changed', 'Changed'], ['all', 'All']]
      .map(function (f) {
        return '<button data-sim-filter="' + f[0] + '" aria-pressed="' + (SIM.filter === f[0]) + '">' + f[1] + '</button>';
      }).join('');
    var groups = stageGroups(all).map(function (g) {
      var more = !SIM.q && !SIM.more[g.id] && g.rules.length > RULE_PAGE;
      var shown = more ? g.rules.slice(0, RULE_PAGE) : g.rules;
      // A picked rule stays in view even when it sits below the fold of its group.
      if (more && picked && g.rules.indexOf(picked) >= RULE_PAGE) shown = shown.concat([picked]);
      return '<details class="simstage" data-sim-stage="' + esc(g.id) + '"' + (SIM.shut[g.id] ? '' : ' open') + '>' +
        '<summary><b>' + esc(g.label) + '</b> <span class="fig">' + n0(g.rules.length) + ' ' +
          (g.rules.length === 1 ? 'rule' : 'rules') + '</span></summary>' +
        '<ul class="simlist">' + shown.map(function (r) { var h = ruleRow(r, first); first = false; return h; }).join('') + '</ul>' +
        (more ? '<button class="fmore" data-sim-more="' + esc(g.id) + '">Show all ' + n0(g.rules.length) + '</button>' : '') +
        '</details>';
    }).join('');
    var body =
      '<div class="simtools"><input type="search" class="siminput simsearch" id="simsearch" placeholder="Search rules, fields, policy codes" ' +
        'value="' + esc(SIM.q) + '" aria-label="Search rules"><div class="fseg">' + filters + '</div></div>' +
      (groups
        ? '<div class="simcols" aria-hidden="true"><span>Rule</span><span' + N('sim_alone') + '>Only this rule stops</span><span>Status</span></div>' + groups
        : '<p class="simempty">No rule matches' + (SIM.filter !== 'all'
            ? ' this filter. <button class="drlink" data-sim-filter="all">Show all rules</button></p>' : '.</p>'));
    var changed = SIM.rules.filter(function (r) { return stepsFor(r.rule_id).length; }).length;
    return panel(n0(SIM.rules.length) + ' decline rules', (changed ? '<span class="fig">' + changed + ' changed</span>' : '') + csvBtn('rules'),
      body, N('sim_rules'));
  }

  function driverFor(rid) { return (F.drivers || []).filter(function (d) { return d.rule_id === rid; })[0]; }

  /** Today's value → the new one, per threshold, and the button that puts it in the scenario. */
  function thresholdEditor(r) {
    return r.thresholds.map(function (t, i) {
      var cur = SIM.steps.filter(function (s) { return s.rule_id === r.rule_id && s.field === t.field; })[0];
      var lo = cur ? cur.value_low : t.value_low;
      var hi = cur && cur.value_high !== undefined ? cur.value_high : t.value_high;
      var range = t.value_high !== null && t.value_high !== undefined;
      return '<div class="simedrow" data-sim-field="' + esc(t.field) + '" data-i="' + i + '">' +
        '<span class="simedk">' + esc(fieldLabel(t.field)) + '</span>' +
        '<span class="simedv"><span class="simednow">today ' + esc(condText(t).slice(fieldName(t.field).length + 1)) + '</span><span aria-hidden="true">→</span>' +
          (range ? esc(t.operator) + ' ' : esc(OPS[t.operator] || t.operator) + ' ') +
          '<input type="number" step="any" class="siminput" data-bound="lo" value="' + esc(lo) + '" aria-label="New ' + esc(fieldLabel(t.field)) + ' threshold">' +
          (range ? ' and <input type="number" step="any" class="siminput" data-bound="hi" value="' + esc(hi) + '" aria-label="New ' + esc(fieldLabel(t.field)) + ' upper bound">' : '') +
        '</span><button class="btn sm" data-sim-apply="' + esc(r.rule_id) + '"' + (SIM.pending ? ' disabled' : '') + '>' +
          (cur ? 'Update scenario' : 'Add to scenario') + '</button></div>';
    }).join('');
  }

  function ruleDetailBody(r) {
    var st = ruleStatus(r), s = r.sentence || {};
    var head = '<div class="rdhead"><div><h4 class="rdname">' + esc(r.label) + '</h4>' +
      '<p class="rdsub"><span class="rid">' + esc(r.rule_id) + '</span>' +
        (r.policy_code ? ' · ' + esc(r.policy_code) : '') + ' · ' + esc(r.stage_label || r.stage) + '</p></div>' +
      '<button type="button" class="rdclose" data-sim-close aria-label="Close rule detail">×</button></div>';
    var what = '<p class="rdwhen"' + N('sim_sentence') + '><b>Declines when</b> ' +
        esc(s.when || r.tests || 'the rule file gives no testable condition') + '.</p>' +
      (s.applies_to ? '<p class="rdwhen"><b>Applies to</b> ' + esc(s.applies_to) + '.</p>' : '');
    if (st.id === 'locked') {
      var why = r.reason || 'the bank declared it untouchable';
      return head + what + '<p class="rdlock">' + lockIcon(r) + '<b>Locked.</b> ' +
        esc(why.charAt(0).toUpperCase() + why.slice(1)) + '.</p>';
    }
    var d = driverFor(r.rule_id);
    var facts = '<dl class="rdfacts">' +
      '<div><dt>Declines</dt><dd class="fig">' + n0(r.declines) + '</dd></div>' +
      '<div><dt>Only this rule stops</dt><dd class="fig">' + n0(r.declines_alone) + '</dd></div>' +
      (d && d.approvals_gained !== null && d.approvals_gained !== undefined
        ? '<div><dt>Booked if switched off</dt><dd class="fig">+' + n0(d.approvals_gained) + '</dd></div>' : '') +
      '</dl>' +
      (d && d.verdict ? '<p class="rdverdict">Decline drivers: <b>' + esc(drGroup(d.verdict).label || d.verdict) + '</b> ' +
        '<a href="#drivers" class="drlink" data-sim-drivers>Why →</a></p>' : '');
    var off = st.id === 'off', canTry = SIM.live || precomputed(r.rule_id);
    var sw = '<label class="simtoggle' + (canTry ? '' : ' is-disabled') + '">' +
      '<input type="checkbox" role="switch" data-sim-rule="' + esc(r.rule_id) + '"' + (off ? '' : ' checked') +
      (canTry && !SIM.pending ? '' : ' disabled') + '><i aria-hidden="true"></i>' +
      '<span class="rn"><span class="rl">' + (off ? 'Switched off in this scenario' : 'On, as today') + '</span>' +
      '<span class="rsub">' + (canTry ? (off ? 'Switch it back on to take it out of the scenario' : 'Switch off to add that to the scenario')
                                     : 'Switching it off needs the engine running') + '</span></span></label>';
    var edit = '';
    if (r.thresholds.length && !off) {
      edit = SIM.live
        ? '<div class="rdsep"' + N('sim_edit') + '>Or move a threshold</div>' + thresholdEditor(r) +
          '<p class="simnote">Moving a threshold can loosen <em>or</em> tighten the rule. The result says which, ' +
          'and a tightening is the only way anyone approved today is newly declined.</p>'
        : '<p class="simnote">Moving a threshold needs the engine running.</p>';
    }
    var mine = SIM.steps.map(function (x, i) { return [x, i]; }).filter(function (p) { return p[0].rule_id === r.rule_id; });
    var inScen = mine.length ? '<div class="rdsep">In your scenario</div><ul class="rdsteps">' + mine.map(function (p) {
      return '<li><span>Step ' + (p[1] + 1) + ': ' + esc(stepText(p[0])) + '</span>' +
        '<button class="drlink" data-sim-revert="' + p[1] + '"' + (SIM.pending ? ' disabled' : '') + '>Remove</button></li>';
    }).join('') + '</ul>' : '';
    return head + what + facts + sw + edit + inScen;
  }

  function ruleDetail(r) {
    return '<section class="panel simdetail" aria-label="Rule detail">' + ruleDetailBody(r) + '</section>';
  }

  function sweepPanels() {
    return (F.sweeps || []).map(function (sw, si) {
      var cells = sw.rows.map(function (r, i) {
        return '<div class="s' + (r.note === 'current' ? ' is-current' : '') + '">' +
          '<div class="c"' + (i === 0 ? N('sweep_cell') : '') + '>' + esc(sw.field === 'simahcreditscore' ? 'SIMAH ' : 'CRIF ') + r.cutoff + '</div>' +
          '<div class="a">' + pct(r.approval_rate) + '</div>' +
          '<div class="b">' + (r.note === 'current' ? 'current' : pp(r.approval_change_pp)) + '<br>' +
          (r.risk_known ? 'bad ' + pct(r.expected_bad_rate, 2) : '<span class="nodata">no estimate</span>') +
          '</div></div>';
      }).join('');
      return panel(sw.label, pv('OBSERVED', 'APPROVAL') + ' ' + pv('INFERRED', 'RISK') + csvBtn('sweep:' + si),
        '<div class="sweep">' + cells + '</div>', N('sweep'));
    }).join('');
  }

  function viewRules() {
    // The detail takes the scenario panel's place; on a narrow screen it opens under its row instead.
    var r = SIM.picked && ruleById(SIM.picked);
    var side = r && !narrowRules() ? ruleDetail(r) : waterfall();
    return '<div class="simgrid"><div class="simmain">' + rulesPanel() + '</div>' +
      '<div class="simside">' + side + '</div></div>' +
      disclose('sweeps', 'Score cutoff sweeps', sweepPanels());
  }

  /* ---- Set a target: goal-seek, answered in one sentence */
  function goalCandidates() {
    var gs = SIM.health && SIM.health.goal_search;
    if (!gs || !SIM.rules) return [];
    return SIM.rules.filter(function (r) { return r.editable && r.declines_alone >= gs.min_declines_alone; })
      .slice(0, gs.max_rule_candidates);
  }

  function runGoal() {
    var g = SIM.goal;
    g.pending = true; g.error = null; refreshSim();
    var seq = CTX.seq;
    api('/api/goal-seek', ctxBody({ target: g.target === null ? null : g.target / 100,
                                     ceiling: g.ceiling === null ? null : g.ceiling / 100,
                                     frozen: g.frozen })).then(function (out) {
      if (seq === CTX.seq) g.out = out;
    }).catch(function (e) { if (seq === CTX.seq) g.error = e.message; })
      .then(function () { g.pending = false; refreshSim(); });
  }

  /** An option's changes in words. Structured changes when the engine sent them, else its label. */
  function optionWords(o) {
    if (o.changes && o.changes.length) {
      return o.changes.map(function (ch) {
        if (ch.type === 'off') return 'switch off “' + ruleName(ch.rule_id) + '”';
        return (ch.to < ch.from ? 'lower' : 'raise') + ' the ' + fieldLabel(ch.field) + ' cutoff from ' +
          num(ch.from) + ' to ' + num(ch.to);
      });
    }
    return String(o.option).replace(/^[A-Z]:\s*/, '').split(' + ').map(function (s) {
      var m = /^switch off \S+ \((.*)\)$/.exec(s);
      return m ? 'switch off “' + m[1] + '”' : s;
    });
  }

  function recommendation(res) {
    var o = res.options[0];
    if (!o) return caveat('warn', 'OUT OF REACH', 'The search found nothing it could change.', N('goal_tag'));
    var words = optionWords(o);
    var ok = res.reached && o.reaches_target && !o.breaches_ceiling;
    var head = ok ? 'To reach ' + pct(res.target, 1) + ':' : 'The closest we can get to ' + pct(res.target, 1) + ':';
    var bad = o.risk_known
      ? 'bad rate ' + pct(o.expected_bad_rate, 2) + ' (' + ptsChange(o.risk_cost_pp, 2) + '), ' +
        (o.breaches_ceiling ? 'above' : 'inside') + ' the ' + pct(res.ceiling, 1) + ' limit'
      : 'no bad-rate estimate is possible for these applicants';
    var sentence = words.map(function (w, i) { return i ? w : w.charAt(0).toUpperCase() + w.slice(1); });
    var canApply = SIM.live && o.changes && o.changes.length;
    return '<div class="simreco ' + (ok ? 'is-reached' : 'is-short') + '">' +
      '<div class="rtag"' + N('goal_tag') + '>' + (ok ? 'Reached' : 'Out of reach') + '</div>' +
      '<p class="rhead"' + N('goal_reco') + '><b>' + esc(head) + '</b> ' + esc(joinWords(sentence)) + '.</p>' +
      '<p class="rfig">Approval <span class="fig c-obs">' + pct(o.approval_rate) + '</span> (' + ptsChange(o.approval_change_pp) + '), ' +
        '<span class="fig">' + n0(o.swap_in) + '</span> newly approved; ' + esc(bad) + '.</p>' +
      '<div class="simacts">' + (canApply ? '<button class="btn" data-goal-apply="0"' + N('goal_apply') + '>Try this as a scenario</button>' : '') +
        '<button class="btn ghost sm" data-goal-print="0"' + N('goal_print') + '>Print pack</button>' + csvBtn('goal', 'All options CSV') + '</div>' +
      '</div>';
  }

  function otherOptions(res) {
    var rest = res.options.slice(1);
    if (!rest.length) return '';
    return disclose('options', rest.length + ' more option' + (rest.length > 1 ? 's' : ''), rest.map(function (o, j) {
      var i = j + 1;
      var tag = o.breaches_ceiling ? 'above the bad-rate limit' : o.reaches_target ? 'reaches the target' : 'falls short';
      return '<div class="opt ' + (o.breaches_ceiling ? 'is-breach' : '') + '">' +
        '<h4' + (j === 0 ? N('opt_head') : '') + '>Option ' + esc(String(o.option).charAt(0)) + ' <small>' + tag + '</small></h4>' +
        '<ul class="steps">' + optionWords(o).map(function (w, k) {
          return '<li' + (j === 0 && k === 0 ? N('opt_steps') : '') + '>' + esc(w) + '</li>'; }).join('') + '</ul>' +
        '<p class="rfig">Approval ' + pct(o.approval_rate) + ' (' + ptsChange(o.approval_change_pp) + ') · ' +
          '<span' + (j === 0 ? N('opt_risk') : '') + '>bad rate ' + (o.risk_known ? pct(o.expected_bad_rate, 2) + ' (' + ptsChange(o.risk_cost_pp, 2) + ')' : 'no estimate') + '</span>' +
          ' · ' + n0(o.swap_in) + ' newly approved</p>' +
        '<div class="simacts">' + (SIM.live && o.changes && o.changes.length ? '<button class="btn ghost sm" data-goal-apply="' + i + '">Try this as a scenario</button>' : '') +
        '<button class="btn ghost sm" data-goal-print="' + i + '">Print pack</button></div>' +
        '</div>';
    }).join(''), N('goal_more'));
  }

  function goalChart(res) {
    var pointsList = [todayPoint()].concat(res.options.map(function (o) {
      var p = resultPoint(o, 'Option ' + String(o.option).charAt(0), 'option');
      p.short = String(o.option).charAt(0);
      return p;
    }));
    return frontier(pointsList, { target: res.target, aria: 'Approval rate against bad rate: today and each option' });
  }

  function goalForm() {
    var g = SIM.goal, gs = SIM.health.goal_search, cands = goalCandidates();
    var chips = cands.map(function (r) {
      var frozen = g.frozen.indexOf(r.rule_id) >= 0;
      return '<button class="chip" data-goal-freeze="' + esc(r.rule_id) + '" aria-pressed="' + frozen + '" title="' + esc(r.rule_id) + '">' +
        (frozen ? lockIcon({ locked: true }) : '') + esc(r.label) + '</button>';
    }).join(' ');
    return '<div class="goalform">' +
      '<span class="gl"' + N('goal_target') + '>Reach an approval rate of</span>' +
      '<span class="gin"><input type="number" class="siminput" id="goaltarget" min="0" max="100" step="0.5" value="' + esc(g.target) +
        '" aria-label="Target approval rate, percent">%<small>today ' + pct(F.headline.approval_rate) + '</small></span>' +
      '<span class="gl"' + N('goal_ceiling') + '>without the bad rate going above</span>' +
      '<span class="gin"><input type="number" class="siminput" id="goalceiling" min="0" max="100" step="0.5" value="' + esc(g.ceiling) +
        '" aria-label="Bad-rate limit, percent">%<small>today ' + pct(F.headline.booked_bad_rate, 2) + '</small></span>' +
      '<button class="btn" data-goal-run' + (g.pending ? ' disabled' : '') + '>' + (g.pending ? '<span class="spin" aria-hidden="true"></span>Searching…' : 'Find the way') + '</button>' +
      '</div>' +
      disclose('constraints', 'Constraints',
        '<div class="simfrozen"><span class="simedk"' + N('goal_frozen') + '>Rules the search may switch off. Click one to keep it on:</span> ' + chips +
        '<p class="simnote">It may also try ' + gs.field_moves.length + ' cutoff moves set in config' +
        (gs.field_moves.length ? ' (' + esc(gs.field_moves.join('; ')) + ')' : '') + ', combined up to ' +
        gs.max_depth + ' at a time.</p></div>');
  }

  function goalResult(res) {
    return '<div class="simgrid is-goal"><div>' + recommendation(res) + otherOptions(res) + '</div>' +
      '<div>' + goalChart(res) + legend() + '</div></div>';
  }

  /** While goal-seek runs: the shape of the answer, drawn in grey, and what the engine is doing.
   * Pure CSS animation, no timers, so it costs nothing and stops the moment the result renders. */
  function goalLoading() {
    var gs = SIM.health.goal_search;
    var tries = goalCandidates().length + gs.field_moves.length;
    var stages = [
      'Replaying ' + n0(F.meta.applicants) + ' applicants under each change',
      'Combining ' + tries + ' possible changes, up to ' + gs.max_depth + ' at a time',
      'Ranking what reaches ' + pct(SIM.goal.target / 100, 1) + ' by the extra bad rate it costs'
    ];
    // Scattered where a search would look: rightwards of today, spread in bad rate.
    var dots = [[.22, .70], [.34, .58], [.30, .80], [.46, .64], [.52, .76], [.41, .46], [.63, .55],
                [.58, .70], [.70, .40], [.74, .62], [.81, .52], [.66, .78], [.86, .34], [.90, .60]];
    var svg = '<svg viewBox="0 0 100 60" preserveAspectRatio="none" aria-hidden="true">' +
      [15, 30, 45].map(function (y) { return '<line class="gl" x1="0" x2="100" y1="' + y + '" y2="' + y + '"/>'; }).join('') +
      [25, 50, 75].map(function (x) { return '<line class="gl" y1="0" y2="60" x1="' + x + '" x2="' + x + '"/>'; }).join('') +
      '<line class="ceil" x1="0" x2="100" y1="12" y2="12"/>' +
      dots.map(function (d, i) {
        return '<circle cx="' + d[0] * 100 + '" cy="' + d[1] * 60 + '" r="1.6" style="animation-delay:' + (i * 0.22).toFixed(2) + 's"/>';
      }).join('') +
      '<circle class="today" cx="12" cy="' + (0.78 * 60) + '" r="2"/>' +
      '<rect class="scan" x="0" y="0" width="14" height="60"/></svg>';
    return '<div class="goalwait" role="status" aria-live="polite">' +
      '<div class="gwbar"><i></i></div>' +
      '<div class="gwstages">' + stages.map(function (t, i) {
        return '<span style="animation-delay:' + (i * 3) + 's">' + esc(t) + '…</span>';
      }).join('') + '<span class="sr">Searching for options, this takes several seconds.</span></div>' +
      '<div class="simgrid is-goal">' +
        '<div class="gwcard"><i class="sk w30"></i><i class="sk w90 tall"></i><i class="sk w70 tall"></i>' +
          '<i class="sk w80"></i><i class="sk w40 skbtn"></i></div>' +
        '<div class="gwchart">' + svg + '</div>' +
      '</div></div>';
  }

  function viewTarget() {
    if (SIM.live) {
      var g = SIM.goal;
      return panel('How do we reach a target approval rate?', '',
        goalForm() +
        (g.error ? caveat('warn', 'REFUSED', esc(g.error)) : '') +
        (g.pending ? goalLoading() : '') +
        (g.out && !g.pending ? goalResult(g.out) : ''), N('goal'));
    }
    if (SIM.live === null || !F.goal_seek.length) return '';
    var chips = F.goal_seek.map(function (gg, i) {
      return '<button class="chip" data-goal="' + i + '"' + (i === S.goal ? ' aria-current="true"' : '') +
        '>' + pct(gg.target, 0) + ' approval</button>';
    }).join(' ');
    return panel('How do we reach a target approval rate?', chips, goalResult(F.goal_seek[S.goal]), N('goal'));
  }

  /* ======================================== export: CSV and the committee pack (TODO B3)
   * Both are built from the engine's payload, never scraped from the screen: a CSV carries the
   * raw figures (rates as fractions, counts as whole numbers) and the pack prints figures the
   * engine produced, with the provenance of each. A column of estimates says so in its header. */
  var INF = 'INFERRED';

  function ctxSlug(product, w) {
    product = product || CTX.product; w = w || CTX.window;
    return product + (w ? '_' + w.app_from + '_to_' + w.app_to : '');
  }
  function saveFile(name, text, type) {
    var url = URL.createObjectURL(new Blob([text], { type: type }));
    var a = document.createElement('a');
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }
  function csvCell(v) {
    if (v === null || v === undefined) return '';
    if (Array.isArray(v)) v = v.map(function (x) { return x !== null && typeof x === 'object' ? JSON.stringify(x) : x; }).join('; ');
    else if (typeof v === 'object') v = JSON.stringify(v);
    var s = String(v);
    // A cell a spreadsheet would run as a formula is written as text.
    if (/^[=+@\t\r]/.test(s) || (/^-/.test(s) && isNaN(Number(s)))) s = "'" + s;
    return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  /** Rows of objects as CSV: every key any row has, in first-seen order. BOM so Excel reads Arabic. */
  function toCsv(rows, prov) {
    var cols = [];
    rows.forEach(function (r) { Object.keys(r).forEach(function (k) { if (cols.indexOf(k) < 0) cols.push(k); }); });
    var lines = [cols.map(function (k) { return csvCell(prov && prov[k] ? k + ' [' + prov[k] + ']' : k); }).join(',')];
    rows.forEach(function (r) { lines.push(cols.map(function (k) { return csvCell(r[k]); }).join(',')); });
    return '\ufeff' + lines.join('\r\n') + '\r\n';
  }
  function copy(o, extra) {
    var out = {};
    Object.keys(o).forEach(function (k) { out[k] = o[k]; });
    Object.keys(extra || {}).forEach(function (k) { out[k] = extra[k]; });
    return out;
  }
  function currentGoal() { return SIM.live ? SIM.goal.out : (F.goal_seek || [])[S.goal]; }

  /** Each table's CSV: a name and rows straight from the payload. */
  function csvSpec(id) {
    var parts = id.split(':'), kind = parts[0], arg = parts[1];
    var ds = F.drivers_summary || {};
    switch (kind) {
      case 'portfolio': return { name: 'portfolio-by-' + S.slice, rows: F.portfolio[S.slice].rows };
      case 'funnel': return { name: 'funnel-stages', rows: F.funnel };
      case 'funnel-rules': return { name: 'funnel-rules', rows: [].concat.apply([], (F.funnel_rules || []).map(function (s) {
        return s.rules.map(function (r) { return copy({ stage: s.stage, stage_total: s.total }, r); });
      })) };
      case 'trend': return { name: 'by-application-month', rows: F.over_time.months };
      case 'vintage': var V = F.over_time.vintage[S.vintageBy && F.over_time.vintage[S.vintageBy] ? S.vintageBy : Object.keys(F.over_time.vintage)[0]];
        return { name: 'vintage-by-' + V.granularity, rows: [].concat.apply([], V.cohorts.map(function (c) {
          var base = { cohort: c.label, loans: c.loans, booked_from: c.booked_from, booked_to: c.booked_to };
          return c.points.length ? c.points.map(function (q) { return copy(base, { months_on_book: q[0], share_gone_bad: q[1] }); })
                                 : [copy(base, { months_on_book: null, share_gone_bad: null, reason: c.reason })];
        })) };
      case 'channels': return { name: 'declines-by-channel', rows: F.by_channel };
      case 'losses': return { name: 'where-applicants-are-lost', rows: (ds.losses || []).map(function (l) {
        return copy(l, { reasons: l.reasons.map(function (r) { return r.label + ' (' + r.count + ')'; }) });
      }) };
      case 'drivers': return { name: 'decline-drivers', prov: { est_bad_rate_if_relaxed: INF },
        rows: F.drivers.concat((ds.never_fire || []).map(function (r) { return copy(r, { verdict: 'never_fire' }); }),
                               (ds.not_evaluated || []).map(function (r) { return copy(r, { verdict: 'not_evaluated' }); })) };
      case 'rules': return { name: 'decline-rules', rows: (SIM.rules || []).map(function (r) {
        var s = r.sentence || {};
        return { rule_id: r.rule_id, label: r.label, stage: r.stage_label || r.stage, policy_code: r.policy_code,
                 declines_when: s.when || r.tests, applies_to: s.applies_to, declines: r.declines,
                 declines_alone: r.declines_alone, editable: r.editable, locked_because: r.reason,
                 in_your_scenario: ruleStatus(r).t };
      }) };
      case 'scenario': return { name: 'scenario', prov: { expected_bad_rate: INF },
        rows: SIM.out.steps.map(function (s, i) {
          return { step: i + 1, change: stepText(SIM.steps[i]), approval_rate: s.approval_rate,
                   approval_change_pp: s.approval_change_pp, added_pp: s.added_pp, newly_approved: s.swap_in,
                   newly_declined: s.swap_out, expected_bad_rate: s.risk_known ? s.expected_bad_rate : null,
                   risk_known: s.risk_known, verdict: s.verdict };
        }) };
      case 'scenario-channels': return { name: 'scenario-by-channel', rows: Object.keys(SIM.out.result.swap_in_by_channel || {}).map(function (k) {
        return copy({ channel: k }, SIM.out.result.swap_in_by_channel[k]);
      }) };
      case 'sweep': var sw = F.sweeps[+arg];
        return { name: sw.field + '-cutoff-sweep', prov: { expected_bad_rate: INF }, rows: sw.rows };
      case 'goal': var g = currentGoal();
        return { name: 'goal-seek-' + Math.round(g.target * 100) + 'pct', prov: { expected_bad_rate: INF, risk_cost_pp: INF },
          rows: g.options.map(function (o) { return copy(o, { changes: optionWords(o) }); }) };
      case 'saved': return { name: 'saved-scenarios', prov: { expected_bad_rate: INF }, rows: (SIM.saved || []).map(savedRow) };
      case 'compare': return { name: 'scenario-comparison', prov: { expected_bad_rate: INF },
        rows: SIM.cmp.scenarios.map(function (c) {
          return copy(savedRow(c.scenario), c.now ? { approval_rate: c.now.approval_rate, approval_change_pp: c.now.approval_change_pp,
            expected_bad_rate: c.now.risk_known ? c.now.expected_bad_rate : null, newly_approved: c.now.swap_in,
            newly_declined: c.now.swap_out, moved_since_saved: c.drift.length ? c.drift : 'unchanged', error: c.error } : { error: c.error });
        }) };
    }
    return null;
  }
  function savedRow(sc) {
    var o = sc.outcome;
    return { name: sc.name, product: sc.product, applications_from: sc.window.app_from, applications_to: sc.window.app_to,
             performance_months: sc.window.performance_months, changes: sc.steps.map(function (s) { return s.text; }),
             approval_rate: o.approval_rate, approval_change_pp: o.approval_change_pp,
             expected_bad_rate: o.risk_known ? o.expected_bad_rate : null, newly_approved: o.swap_in,
             newly_declined: o.swap_out, saved_by: sc.saved_by, saved_at: sc.saved_at };
  }
  function csvBtn(id, text) {
    return '<button type="button" class="btn ghost sm csvbtn" data-csv="' + esc(id) + '"' + N('csv') + '>' + (text || 'CSV') + '</button>';
  }
  function downloadCsv(id) {
    var spec = csvSpec(id);
    if (!spec || !spec.rows) return;
    saveFile(ctxSlug() + '_' + spec.name + '.csv', toCsv(spec.rows, spec.prov), 'text/csv;charset=utf-8');
  }

  /* ---- the committee pack: one printable page, saved as PDF from the print dialog */
  function stamp(iso) {
    var d = iso ? new Date(iso) : new Date();
    if (isNaN(d)) return String(iso);
    function two(n) { return (n < 10 ? '0' : '') + n; }
    return d.getDate() + ' ' + MONTHS[d.getMonth()] + ' ' + d.getFullYear() + ', ' + two(d.getHours()) + ':' + two(d.getMinutes());
  }
  function tag(kind, text) { return '<span class="pp-tag">' + esc(text || kind) + '</span>'; }

  /** Product, period, bad-rate basis and who prepared it: the context every figure belongs to. */
  function packContext(product, w) {
    var m = F.meta;
    w = w || m.window;
    var rows = [['Product', esc(product || m.product)]];
    if (w) {
      rows.push(['Applications replayed', esc(w.label || (w.app_from + ' – ' + w.app_to)) +
        (w.applicants ? ' · ' + n0(w.applicants) + ' applications' : '')]);
      if (w.mature_loans) rows.push(['Bad rate observed on', n0(w.mature_loans) + ' loans booked ' +
        esc(monthYear(w.mature_booked_from)) + ' – ' + esc(monthYear(w.mature_booked_to)) +
        ', each followed for ' + w.performance_months + ' months']);
    }
    rows.push(['Bad-rate limit', pct(ceilingRate(), 1)]);
    rows.push(['Rules replayed', n0(m.rules_replayed) + ' rules, as the bank runs them today']);
    rows.push(['Data', esc(asOfText())]);
    rows.push(['Prepared', (window.Session.who() ? esc(window.Session.who()) + ', ' : '') + stamp()]);
    return '<dl class="pp-meta">' + rows.map(function (r) { return '<div><dt>' + r[0] + '</dt><dd>' + r[1] + '</dd></div>'; }).join('') + '</dl>' +
      (m.synthetic ? '<p class="pp-warn">Synthetic applicants, real rules: the figures are illustrative; the rules and the method are real.</p>' : '');
  }

  /** Today against the change, with the provenance of each figure. */
  function packOutcome(t) {
    var h = F.headline, ceil = ceilingRate();
    var bad = t.risk_known
      ? pct(t.expected_bad_rate, 2) + (t.expected_bad_rate > ceil ? ' (above the limit)' : '')
      : 'no estimate';
    var badTag = !t.risk_known ? tag('NOT_MODELLED', 'NOT MODELLED') : t.swap_in ? tag(INF) : tag('OBSERVED');
    var rows = [
      ['Approval rate', pct(h.approval_rate), pct(t.approval_rate) + ' (' + ptsChange(t.approval_change_pp) + ')', tag('OBSERVED')],
      ['Bad rate', pct(h.booked_bad_rate, 2), bad, tag('OBSERVED') + ' → ' + badTag],
      ['Newly approved', '', n0(t.swap_in) + ' applicants', tag('OBSERVED')]
    ];
    if (t.swap_out) rows.push(['Newly declined', '', n0(t.swap_out) + ' applicants' +
      (t.swap_out_observed_bad_rate !== null && t.swap_out_observed_bad_rate !== undefined
        ? ', bad rate ' + pct(t.swap_out_observed_bad_rate, 1) : ''), tag('OBSERVED')]);
    return '<table class="pp-t"><thead><tr><th>Measure</th><th>Today</th><th>With the changes</th><th>Basis</th></tr></thead><tbody>' +
      rows.map(function (r) { return '<tr><td>' + r[0] + '</td><td>' + r[1] + '</td><td><b>' + r[2] + '</b></td><td>' + r[3] + '</td></tr>'; }).join('') +
      '</tbody></table>' + (t.verdict ? '<p class="pp-note">Engine verdict: ' + esc(t.verdict) + '.</p>' : '');
  }

  function packKey() {
    return '<section class="pp-key"><h2>How to read the figures</h2><dl>' +
      '<div><dt>' + tag('OBSERVED') + '</dt><dd>Counted from the data: applications, declines, today\'s rules replayed on them, and the bad rate of loans the bank booked.</dd></div>' +
      '<div><dt>' + tag(INF) + '</dt><dd>Estimated by reject inference: the bad rate of applicants the bank has never booked, from similar applicants it did book. Treat it as a forecast.</dd></div>' +
      '<div><dt>' + tag('NOT_MODELLED', 'NOT MODELLED') + '</dt><dd>Left blank on purpose: the group sits outside anything the bank has booked, so any figure would be a guess.</dd></div>' +
      '</dl><p class="pp-note">Every figure in this pack was produced by the Azentio engine; the page only lays them out.</p></section>';
  }

  function printPack(title, name, body) {
    var host = document.getElementById('printpack');
    if (!host) { host = document.createElement('div'); host.id = 'printpack'; document.body.appendChild(host); }
    host.innerHTML = '<header class="pp-head"><div class="pp-brand">Azentio · Credit Strategy Optimiser</div>' +
      '<h1>' + esc(title) + '</h1>' + (name ? '<p class="pp-name">' + esc(name) + '</p>' : '') + '</header>' + body + packKey();
    var was = document.title;
    document.title = ctxSlug() + ' ' + (name || title);
    document.documentElement.classList.add('is-printing');
    function done() {
      document.documentElement.classList.remove('is-printing');
      document.title = was;
      window.removeEventListener('afterprint', done);
    }
    window.addEventListener('afterprint', done);
    window.print();
  }

  function printScenario() {
    var t = SIM.out && SIM.out.result;
    if (!t) return;
    var changes = SIM.out.steps.map(function (s, i) {
      var st = SIM.steps[i], r = st.rule_id && ruleById(st.rule_id);
      var sn = (r && r.sentence) || {};
      return '<li><b>' + esc(stepText(st)) + '</b>' +
        (sn.when ? '<br><span class="pp-note">The rule declines when ' + esc(sn.when) +
          (sn.applies_to ? ', for applicants whose ' + esc(sn.applies_to) : '') + '.</span>' : '') +
        '<br><span class="pp-note">Adds ' + ptsChange(s.added_pp) + ' approval · ' + n0(s.added_swap_in) + ' newly approved' +
        (s.added_swap_out ? ' · ' + n0(s.added_swap_out) + ' newly declined' : '') + '</span></li>';
    }).join('');
    var ch = Object.keys(t.swap_in_by_channel || {});
    var chans = ch.length ? '<h2>Newly approved, by channel ' + tag('OBSERVED') + '</h2><table class="pp-t"><thead><tr><th>Channel</th><th>Newly approved</th>' +
      (t.swap_out ? '<th>Newly declined</th>' : '') + '</tr></thead><tbody>' + ch.map(function (k) {
        var v = t.swap_in_by_channel[k];
        return '<tr><td>' + esc(k) + '</td><td>' + n0(v.swap_in) + '</td>' + (t.swap_out ? '<td>' + n0(v.swap_out) + '</td>' : '') + '</tr>';
      }).join('') + '</tbody></table>' : '';
    printPack('Scenario for committee', savedName(), packContext() +
      '<h2>The changes, in order</h2><ol class="pp-steps">' + changes + '</ol>' +
      '<h2>What they do to the book</h2>' + packOutcome(t) + chans);
  }

  function printGoalOption(i) {
    var res = currentGoal(), o = res && res.options[i];
    if (!o) return;
    var others = res.options.map(function (x) {
      return '<tr' + (x === o ? ' class="is-this"' : '') + '><td>' + esc(String(x.option).charAt(0)) + '</td><td>' +
        esc(joinWords(optionWords(x))) + '</td><td>' + pct(x.approval_rate) + '</td><td>' +
        (x.risk_known ? pct(x.expected_bad_rate, 2) : 'no estimate') + '</td><td>' + n0(x.swap_in) + '</td></tr>';
    }).join('');
    printPack('Goal-seek option for committee', 'Option ' + String(o.option).charAt(0) + ': reach ' + pct(res.target, 1) + ' approval',
      packContext() +
      '<p class="pp-note">Asked for: approval of ' + pct(res.target, 1) + ' with the bad rate at most ' + pct(res.ceiling, 1) + '. ' +
        (res.reached ? 'The search reached it.' : 'The search could not reach it; this is the closest.') + '</p>' +
      '<h2>The changes</h2><ol class="pp-steps">' + optionWords(o).map(function (w) {
        return '<li><b>' + esc(w.charAt(0).toUpperCase() + w.slice(1)) + '</b></li>'; }).join('') + '</ol>' +
      '<h2>What they do to the book</h2>' + packOutcome(o) +
      '<h2>Every option the search returned</h2><table class="pp-t"><thead><tr><th></th><th>Changes</th><th>Approval</th>' +
        '<th>Bad rate ' + tag(INF) + '</th><th>Newly approved</th></tr></thead><tbody>' + others + '</tbody></table>');
  }

  function printComparison() {
    var c = SIM.cmp;
    if (!c) return;
    printPack('Scenarios compared', c.scenarios.map(function (x) { return x.scenario.name; }).join(' · '),
      packContext() + (c.same_context ? '' : '<p class="pp-warn">These scenarios were built on different products or periods, ' +
        'so their figures are not measured on the same applications.</p>') + compareTable(true));
  }

  /* ======================================== saved scenarios (TODO B4)
   * Kept by the engine, which re-runs the steps when a scenario is saved and again when it is
   * compared, and records who saved it and when. The page lists, opens and compares; it never
   * stores a figure of its own. */
  function savedName() {
    var s = SIM.savedAs;
    return s && s.key === JSON.stringify(SIM.steps) ? s.name : '';
  }

  function loadSaved() {
    if (!SIM.live || SIM.savedLoading) return;
    SIM.savedLoading = true;
    api('/api/scenarios').then(function (j) {
      SIM.saved = j.scenarios; SIM.cmpMax = j.compare_max || 4; SIM.savedErr = null;
      Object.keys(SIM.cmpPick).forEach(function (id) {
        if (!SIM.saved.some(function (s) { return s.id === id; })) delete SIM.cmpPick[id];
      });
    }).catch(function (e) { SIM.savedErr = e.message; })
      .then(function () { SIM.savedLoading = false; refreshSim(); });
  }

  function saveScenario(name) {
    SIM.saveErr = null; SIM.savePending = true; refreshSim();
    var steps = SIM.steps.slice();
    api('/api/scenarios', ctxBody({ name: name, changes: steps, preset: CTX.preset, who: window.Session.who() || null }))
      .then(function (sc) {
        SIM.saving = false; SIM.saved = null;
        SIM.savedAs = { name: sc.name, key: JSON.stringify(steps) };
      }).catch(function (e) { SIM.saveErr = e.message; })
      .then(function () { SIM.savePending = false; refreshSim(); });
  }

  function sameWindow(a, b) {
    return !!a && !!b && a.app_from === b.app_from && a.app_to === b.app_to && +a.performance_months === +b.performance_months;
  }

  /** Open a saved scenario: its own product and period first, then its steps, re-run. */
  function openSaved(sc) {
    SIM.view = 'try'; SIM.cmp = null;
    if (sc.product === CTX.product && sameWindow(sc.window, CTX.window)) {
      propose(sc.changes.slice(), function (ok) { openedNotice(sc, ok); });
      return;
    }
    SIM.pendingOpen = sc;
    setContext({ product: sc.product, preset: sc.preset, window: sc.window });
  }
  function openedNotice(sc, ok) {
    if (ok) SIM.savedAs = { name: sc.name, key: JSON.stringify(sc.changes) };
    SIM.notice = ok
      ? { tag: 'OPENED', html: '“' + esc(sc.name) + '” re-run on ' + esc(sc.window.label || 'its period') + '. Every figure below is from this run.' }
      : { tag: 'NOT OPENED', html: '“' + esc(sc.name) + '” no longer runs: ' + esc(SIM.error || 'the engine refused it') + '.' };
    if (!ok) SIM.error = null;
  }

  function scenarioActions() {
    var t = SIM.out && SIM.out.result;
    if (!t) return '';
    var name = savedName();
    var save = !SIM.live ? '' : SIM.saving
      ? '<span class="simsave"><input type="text" class="siminput" id="simname" maxlength="80" placeholder="Name this scenario" ' +
          'aria-label="Scenario name" value="' + esc(SIM.draftName || '') + '">' +
        '<button class="btn sm" data-sim-save-go' + (SIM.savePending ? ' disabled' : '') + '>Save</button>' +
        '<button class="btn ghost sm" data-sim-save-cancel>Cancel</button></span>'
      : '<button class="btn ghost sm" data-sim-save' + N('sim_save') + '>' + (name ? 'Save as new…' : 'Save scenario…') + '</button>';
    return '<div class="simacts">' +
      (name ? '<span class="simsaved">Saved as <b>' + esc(name) + '</b></span>' : '') + save +
      '<button class="btn ghost sm" data-sim-print' + N('sim_print') + '>Print pack</button>' + csvBtn('scenario') +
      (SIM.saveErr ? '<span class="simerr" role="alert">' + esc(SIM.saveErr) + '</span>' : '') + '</div>';
  }

  function savedFig(o) {
    return '<td class="num">' + pct(o.approval_rate) + '<br><small>' + ptsChange(o.approval_change_pp) + '</small></td>' +
      '<td class="num">' + (o.risk_known ? '<span class="' + (o.swap_in ? 'c-inf' : 'c-obs') + '">' + pct(o.expected_bad_rate, 2) + '</span>'
                                          : '<span class="c-nm">no estimate</span>') + '</td>' +
      '<td class="num">' + n0(o.swap_in) + '</td>';
  }

  function viewSaved() {
    if (!SIM.live) return panel('Saved scenarios', '', '<p class="note">Saved scenarios are kept by the engine. ' +
      'Start it (<code>python -m ui.serve</code>) to save, open and compare them.</p>');
    if (SIM.saved === null) { loadSaved(); return panel('Saved scenarios', '', '<p class="note">Loading…</p>'); }
    if (SIM.savedErr) return panel('Saved scenarios', '', caveat('warn', 'REFUSED', esc(SIM.savedErr)));
    var picked = Object.keys(SIM.cmpPick).length;
    var rows = SIM.saved.map(function (sc) {
      return '<tr><td class="savpick"><input type="checkbox" data-sim-cmp="' + esc(sc.id) + '"' + (SIM.cmpPick[sc.id] ? ' checked' : '') +
          ' aria-label="Compare ' + esc(sc.name) + '"></td>' +
        '<td><b class="savname">' + esc(sc.name) + '</b><ul class="savsteps">' +
          sc.steps.map(function (s) { return '<li>' + esc(s.text) + '</li>'; }).join('') + '</ul></td>' +
        '<td>' + esc(sc.product) + '<br><small>' + esc(sc.window.label || '') + '</small></td>' +
        savedFig(sc.outcome) +
        '<td><small>' + esc(sc.saved_by || 'unnamed') + '<br>' + esc(stamp(sc.saved_at)) + '</small></td>' +
        '<td class="savacts"><button class="drlink" data-sim-open-saved="' + esc(sc.id) + '">Open</button>' +
          '<button class="drlink" data-sim-del-saved="' + esc(sc.id) + '">Delete</button></td></tr>';
    });
    var canCmp = picked >= 2 && picked <= SIM.cmpMax;
    var head = (SIM.saved.length ? csvBtn('saved') : '') +
      '<button class="btn sm" data-sim-compare' + (canCmp && !SIM.cmpPending ? '' : ' disabled') + N('sim_compare') + '>' +
        (SIM.cmpPending ? 'Re-running…' : 'Compare' + (picked ? ' ' + picked : '')) + '</button>';
    var body = SIM.saved.length
      ? '<p class="simnote">Tick 2 to ' + SIM.cmpMax + ' to compare them side by side. The figures here are as saved; comparing re-runs them.</p>' +
        '<div class="savtab">' + table('<th></th><th>Scenario</th><th>Product · period</th><th class="num">Approval</th>' +
          '<th class="num">Bad rate</th><th class="num">Newly approved</th><th>Saved by</th><th></th>', rows) + '</div>'
      : '<p class="note">Nothing saved yet. Build a scenario under Try a change or All rules, then Save scenario.</p>';
    return panel('Saved scenarios', head, (SIM.cmpErr ? caveat('warn', 'REFUSED', esc(SIM.cmpErr)) : '') + body, N('sim_saved')) +
      (SIM.cmp ? panel('Side by side', '<button class="btn ghost sm" data-sim-print-cmp>Print pack</button>' + csvBtn('compare'),
        (SIM.cmp.same_context ? '' : caveat('warn', 'DIFFERENT BASES', 'These scenarios were built on different products or periods, ' +
          'so their figures are not measured on the same applications.')) + compareTable(false), N('sim_cmp_table')) : '');
  }

  /** One column per scenario, re-run now. `forPrint` drops the screen-only colour classes. */
  function compareTable(forPrint) {
    var cols = SIM.cmp.scenarios;
    function cmpRow(label, fn) {
      return '<tr><th scope="row">' + label + '</th>' + cols.map(function (c) { return '<td>' + fn(c) + '</td>'; }).join('') + '</tr>';
    }
    function now(fn) { return function (c) { return c.now ? fn(c.now) : '<span class="nodata">—</span>'; }; }
    var body = [
      cmpRow('Product · period', function (c) { return esc(c.scenario.product) + '<br><small>' + esc(c.scenario.window.label || '') + '</small>'; }),
      cmpRow('Changes', function (c) { return '<ol class="savsteps">' + c.scenario.steps.map(function (s) { return '<li>' + esc(s.text) + '</li>'; }).join('') + '</ol>'; }),
      cmpRow('Approval ' + (forPrint ? tag('OBSERVED') : pv('OBSERVED')), now(function (o) { return '<b>' + pct(o.approval_rate) + '</b> (' + ptsChange(o.approval_change_pp) + ')'; })),
      cmpRow('Bad rate ' + (forPrint ? tag(INF) : pv(INF)), now(function (o) {
        return o.risk_known ? '<b' + (forPrint ? '' : ' class="' + (o.swap_in ? 'c-inf' : 'c-obs') + '"') + '>' + pct(o.expected_bad_rate, 2) + '</b>' +
          (o.expected_bad_rate > ceilingRate() ? ' above the limit' : '') : 'no estimate';
      })),
      cmpRow('Newly approved', now(function (o) { return n0(o.swap_in); })),
      cmpRow('Newly declined', now(function (o) { return n0(o.swap_out); })),
      cmpRow('Engine verdict', now(function (o) { return esc(o.verdict || ''); })),
      cmpRow('Since it was saved', function (c) {
        if (c.error) return '<span class="simerr">' + esc(c.error) + '</span>';
        return c.drift.length ? '<span class="simerr">Moved: ' + esc(c.drift.join(', ')) + '</span>' : 'Unchanged';
      }),
      cmpRow('Saved by', function (c) { return esc(c.scenario.saved_by || 'unnamed') + '<br><small>' + esc(stamp(c.scenario.saved_at)) + '</small>'; })
    ];
    return '<div class="' + (forPrint ? '' : 'tablewrap ') + 'cmptab"><table class="' + (forPrint ? 'pp-t' : 't') + '"><thead><tr><th></th>' +
      cols.map(function (c) { return '<th>' + esc(c.scenario.name) + '</th>'; }).join('') + '</tr></thead><tbody>' + body.join('') + '</tbody></table></div>';
  }

  function runCompare() {
    var ids = SIM.saved.filter(function (s) { return SIM.cmpPick[s.id]; }).map(function (s) { return s.id; });
    SIM.cmpPending = true; SIM.cmpErr = null; refreshSim();
    api('/api/scenarios/compare', { ids: ids }).then(function (out) { SIM.cmp = out; })
      .catch(function (e) { SIM.cmpErr = e.message; })
      .then(function () { SIM.cmpPending = false; refreshSim(); });
  }

  function deleteSaved(sc) {
    if (!window.confirm('Delete “' + sc.name + '”? It leaves the list; the record of who saved and deleted it is kept.')) return;
    api('/api/scenarios/delete', { id: sc.id, who: window.Session.who() || null })
      .then(function () { SIM.saved = null; SIM.cmp = null; delete SIM.cmpPick[sc.id]; })
      .catch(function (e) { SIM.savedErr = e.message; })
      .then(function () { refreshSim(); });
  }

  function wireSaved(root) {
    root.querySelectorAll('[data-sim-save]').forEach(function (b) {
      b.addEventListener('click', function () {
        SIM.saving = true; SIM.saveErr = null; SIM.draftName = '';
        SIM.refocus = '#simname'; go('simulator', true);
      });
    });
    var name = root.querySelector('#simname');
    if (name) {
      name.addEventListener('input', function () { SIM.draftName = name.value; });
      name.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') root.querySelector('[data-sim-save-go]').click();
        if (e.key === 'Escape') root.querySelector('[data-sim-save-cancel]').click();
      });
    }
    root.querySelectorAll('[data-sim-save-go]').forEach(function (b) {
      b.addEventListener('click', function () {
        var v = (SIM.draftName || '').trim();
        if (!v) { SIM.saveErr = 'Give the scenario a name.'; SIM.refocus = '#simname'; go('simulator', true); return; }
        saveScenario(v);
      });
    });
    root.querySelectorAll('[data-sim-save-cancel]').forEach(function (b) {
      b.addEventListener('click', function () { SIM.saving = false; SIM.saveErr = null; go('simulator', true); });
    });
    root.querySelectorAll('[data-sim-print]').forEach(function (b) { b.addEventListener('click', printScenario); });
    root.querySelectorAll('[data-sim-print-cmp]').forEach(function (b) { b.addEventListener('click', printComparison); });
    root.querySelectorAll('[data-goal-print]').forEach(function (b) {
      b.addEventListener('click', function () { printGoalOption(+b.getAttribute('data-goal-print')); });
    });
    root.querySelectorAll('[data-sim-cmp]').forEach(function (b) {
      b.addEventListener('change', function () {
        if (b.checked) SIM.cmpPick[b.getAttribute('data-sim-cmp')] = true; else delete SIM.cmpPick[b.getAttribute('data-sim-cmp')];
        SIM.refocus = '[data-sim-cmp="' + b.getAttribute('data-sim-cmp') + '"]';
        go('simulator', true);
      });
    });
    root.querySelectorAll('[data-sim-compare]').forEach(function (b) { b.addEventListener('click', runCompare); });
    function byId(id) { return (SIM.saved || []).filter(function (s) { return s.id === id; })[0]; }
    root.querySelectorAll('[data-sim-open-saved]').forEach(function (b) {
      b.addEventListener('click', function () { var sc = byId(b.getAttribute('data-sim-open-saved')); if (sc) openSaved(sc); });
    });
    root.querySelectorAll('[data-sim-del-saved]').forEach(function (b) {
      b.addEventListener('click', function () { var sc = byId(b.getAttribute('data-sim-del-saved')); if (sc) deleteSaved(sc); });
    });
  }

  function modeNote() {
    if (SIM.live === null) return '<p class="simmode"' + N('sim_mode') + '>Connecting to the engine…</p>';
    if (SIM.live) return '';
    return '<p class="simmode"' + N('sim_mode') + '>Worked out in advance: one change at a time. ' +
      'Start the engine (<code>python -m ui.serve</code>) to stack changes and set your own target.</p>';
  }

  var VIEWS = [['target', 'Set a target'], ['try', 'Try a change'], ['rules', 'All rules'], ['saved', 'Saved']];

  function pageSimulator() {
    var tabs = '<div class="fseg simviews" role="tablist"' + N('sim_views') + '>' + VIEWS.map(function (v) {
      return '<button role="tab" data-sim-view="' + v[0] + '" aria-pressed="' + (SIM.view === v[0]) + '" aria-selected="' +
        (SIM.view === v[0]) + '">' + v[1] + '</button>';
    }).join('') + '</div>';
    var body = SIM.view === 'target' ? viewTarget() : SIM.view === 'try' ? viewTry() :
      SIM.view === 'saved' ? viewSaved() : viewRules();
    var scenario = SIM.view === 'target' || SIM.view === 'saved' ? '' :
      '<div class="simsticky"' + N('sim_outcome') + '>' + outcomeBar() + scenarioActions() +
        (SIM.error ? caveat('warn', 'REFUSED', esc(SIM.error)) : '') + outcomeDetails() + '</div>';
    return '<div class="pagehead simhead"><div><h2' + N('sim_head') + '>Simulator</h2>' +
      '<p>Change today\'s rules and see who moves, or name a target and let the engine find the way.</p>' +
      periodLine() + '</div>' +
      tabs + '</div>' + modeNote() +
      (SIM.notice ? caveat('warn', SIM.notice.tag, SIM.notice.html, N('sim_context')) : '') +
      (SIM.error && SIM.view === 'target' ? caveat('warn', 'REFUSED', esc(SIM.error)) : '') +
      scenario + body;
  }

  /** The side column sticks just below the outcome bar and scrolls on its own if taller than the room left. */
  function syncStick(root) {
    var bar = root.querySelector('.simsticky'), canvas = document.getElementById('canvas');
    if (!bar || !canvas) return;
    var top = bar.offsetHeight + 8;
    // A sticky box cannot pass the bottom of its grid, which ends above the page's bottom padding.
    // Taller than the room left, it would be pushed up under the outcome bar at the end of a scroll.
    var below = parseFloat(getComputedStyle(root).paddingBottom) || 0;
    root.style.setProperty('--simstick', top + 'px');
    root.style.setProperty('--simside-max', Math.max(240, canvas.clientHeight - top - below - 4) + 'px');
  }
  window.addEventListener('resize', function () {
    if (S.page !== 'simulator') return;
    // The rule detail moves between the side column and its row when the layout stacks.
    var narrow = narrowRules();
    if (SIM.view === 'rules' && SIM.picked && narrow !== syncStick.narrow) { syncStick.narrow = narrow; go('simulator', true); return; }
    syncStick.narrow = narrow;
    syncStick(document.getElementById('canvaswrap'));
  });

  function wireSimulator(root) {
    wireSaved(root);
    root.querySelectorAll('[data-sim-view]').forEach(function (b) {
      b.addEventListener('click', function () { SIM.view = b.getAttribute('data-sim-view'); go('simulator', true); });
    });
    root.querySelectorAll('details[data-sim-open]').forEach(function (d) {
      d.addEventListener('toggle', function () { SIM.open[d.getAttribute('data-sim-open')] = d.open; });
    });
    root.querySelectorAll('[data-sim-preset]').forEach(function (b) {
      b.addEventListener('click', function () {
        var p = presets().filter(function (x) { return x.id === b.getAttribute('data-sim-preset'); })[0];
        if (p) propose(p.steps.slice());
      });
    });
    root.querySelectorAll('[data-sim-cutoff]').forEach(function (inp) {
      var field = inp.getAttribute('data-sim-cutoff'), from = +inp.getAttribute('data-from');
      var vals = inp.getAttribute('data-values').split(',').map(Number);
      var show = root.querySelector('[data-sim-val="' + field + '"]');
      inp.addEventListener('input', function () {
        var v = vals[+inp.value];
        show.innerHTML = num(v) + (v === from ? ' <small>today</small>' : ' <small>today ' + num(from) + '</small>');
      });
      inp.addEventListener('change', function () {
        SIM.refocus = '[data-sim-cutoff="' + field + '"]';
        setCutoff(field, from, vals[+inp.value]);
      });
    });
    var search = root.querySelector('#simsearch');
    if (search) {
      search.addEventListener('input', function () {
        SIM.q = search.value;
        clearTimeout(wireSimulator.t);
        wireSimulator.t = setTimeout(function () {
          var at = search.selectionStart;
          go('simulator', true);
          var again = document.getElementById('simsearch');
          if (again) { again.focus(); try { again.setSelectionRange(at, at); } catch (e) { /* type=search */ } }
        }, 180);
      });
    }
    root.querySelectorAll('[data-sim-filter]').forEach(function (b) {
      b.addEventListener('click', function () { SIM.filter = b.getAttribute('data-sim-filter'); go('simulator', true); });
    });
    root.querySelectorAll('[data-sim-more]').forEach(function (b) {
      b.addEventListener('click', function () { SIM.more[b.getAttribute('data-sim-more')] = true; go('simulator', true); });
    });
    root.querySelectorAll('details[data-sim-stage]').forEach(function (d) {
      d.addEventListener('toggle', function () { SIM.shut[d.getAttribute('data-sim-stage')] = !d.open; });
    });
    root.querySelectorAll('[data-sim-pick]').forEach(function (b) {
      b.addEventListener('click', function () {
        var rid = b.getAttribute('data-sim-pick');
        SIM.picked = SIM.picked === rid ? null : rid;
        SIM.refocus = SIM.picked ? '.simdetail [data-sim-close]' : '[data-sim-pick="' + rid + '"]';
        go('simulator', true);
      });
    });
    root.querySelectorAll('[data-sim-close]').forEach(function (b) {
      b.addEventListener('click', function () {
        var rid = SIM.picked;
        SIM.picked = null;
        SIM.refocus = '[data-sim-pick="' + rid + '"]';
        go('simulator', true);
      });
    });
    root.querySelectorAll('[data-sim-drivers]').forEach(function (a) {
      a.addEventListener('click', function (e) { e.preventDefault(); go('drivers'); });
    });
    root.querySelectorAll('[data-sim-rule]').forEach(function (b) {
      b.addEventListener('change', function () {
        SIM.refocus = '[data-sim-rule="' + b.getAttribute('data-sim-rule') + '"]';
        switchRule(b.getAttribute('data-sim-rule'), b.checked);
      });
    });
    root.querySelectorAll('[data-sim-apply]').forEach(function (b) {
      b.addEventListener('click', function () {
        var rid = b.getAttribute('data-sim-apply');
        var row = b.closest('.simedrow');
        var rule = ruleById(rid);
        var t = rule.thresholds[+row.getAttribute('data-i')];
        var lo = row.querySelector('[data-bound="lo"]'), hi = row.querySelector('[data-bound="hi"]');
        if (lo.value === '' || (hi && hi.value === '')) { SIM.error = 'Enter a number for the threshold.'; go('simulator', true); return; }
        setThreshold(rid, t.field, Number(lo.value), hi ? Number(hi.value) : null, t);
      });
    });
    root.querySelectorAll('[data-sim-revert]').forEach(function (b) {
      b.addEventListener('click', function () {
        var i = +b.getAttribute('data-sim-revert');
        propose(SIM.steps.filter(function (_, j) { return j !== i; }));
      });
    });
    root.querySelectorAll('[data-sim-reset]').forEach(function (b) {
      b.addEventListener('click', function () { propose([]); });
    });
    var tgt = root.querySelector('#goaltarget'), cl = root.querySelector('#goalceiling');
    if (tgt) tgt.addEventListener('input', function () { SIM.goal.target = tgt.value === '' ? null : Number(tgt.value); });
    if (cl) cl.addEventListener('input', function () { SIM.goal.ceiling = cl.value === '' ? null : Number(cl.value); });
    [tgt, cl].forEach(function (inp) {
      if (inp) inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') root.querySelector('[data-goal-run]').click(); });
    });
    root.querySelectorAll('[data-goal-freeze]').forEach(function (b) {
      b.addEventListener('click', function () {
        var rid = b.getAttribute('data-goal-freeze'), f = SIM.goal.frozen, at = f.indexOf(rid);
        if (at >= 0) f.splice(at, 1); else f.push(rid);
        go('simulator', true);
      });
    });
    root.querySelectorAll('[data-goal-run]').forEach(function (b) {
      b.addEventListener('click', function () {
        if (tgt) SIM.goal.target = tgt.value === '' ? null : Number(tgt.value);
        if (cl) SIM.goal.ceiling = cl.value === '' ? null : Number(cl.value);
        runGoal();
      });
    });
    root.querySelectorAll('[data-goal-apply]').forEach(function (b) {
      b.addEventListener('click', function () {
        var o = SIM.goal.out && SIM.goal.out.options[+b.getAttribute('data-goal-apply')];
        if (!o || !o.changes) return;
        SIM.view = 'try';
        propose(o.changes.slice());
      });
    });
    syncStick(root);
    root.querySelectorAll('details[data-sim-open]').forEach(function (d) {
      d.addEventListener('toggle', function () { syncStick(root); });
    });
    if (SIM.refocus && !SIM.pending) {
      var el = root.querySelector(SIM.refocus);
      SIM.refocus = null;
      if (el) el.focus({ preventScroll: true });
    }
  }

  /* ------------------------------------------------------------------- nav */
  var PAGES = [
    { id: 'portfolio', t: 'Portfolio', n: '1' },
    { id: 'drivers', t: 'Decline drivers', n: '2' },
    { id: 'simulator', t: 'Simulator', n: '3' }
  ];
  var RENDER = { portfolio: pagePortfolio, drivers: pageDrivers, simulator: pageSimulator };
  // Settings and Administration are pages of their own. Administration is listed only for someone
  // Session (session.js) allows it; the server refuses it for anyone else whatever the rail shows.
  var LINKS = [
    { t: 'Settings', n: '4', href: 'settings.html' },
    { t: 'Administration', n: '5', href: 'admin.html', need: 'admin.view' }
  ];

  function renderNav() {
    document.getElementById('rail').innerHTML =
      '<div class="railgroup"><h4' + N('rail_screens') + '>Screens</h4>' + PAGES.map(function (p) {
        return '<button class="navitem" data-page="' + p.id + '"' +
          (S.page === p.id ? ' aria-current="page"' : '') + '>' +
          '<span class="n">' + p.n + '</span><span class="lbl">' + esc(p.t) + '</span></button>';
      }).join('') + LINKS.filter(function (l) { return !l.need || window.Session.can(l.need); }).map(function (l) {
        return '<a class="navitem" href="' + l.href + '"><span class="n">' + l.n + '</span><span class="lbl">' + esc(l.t) + '</span></a>';
      }).join('') + '</div>' +
      '<div class="railgroup"><h4' + N('rail_prov') + '>Provenance</h4><div style="padding:6px 10px;display:flex;' +
      'flex-direction:column;gap:6px;align-items:flex-start">' +
      pv('OBSERVED', 'OBSERVED') + pv('PREDICTED', 'PREDICTED') + pv('INFERRED', 'INFERRED') +
      pv('NOT_MODELLED', 'NOT MODELLED') + '</div></div>';
    document.getElementById('rail').querySelectorAll('[data-page]').forEach(function (b) {
      b.addEventListener('click', function () { go(b.getAttribute('data-page')); toggleRail(false); });
    });
  }

  function go(page, keepScroll) {
    var canvas = document.getElementById('canvas');
    var at = canvas.scrollTop;
    S.page = page;
    // The hash names the screen, so settings.html and admin.html can link straight to one.
    if (location.hash !== '#' + page) history.replaceState(null, '', '#' + page);
    var wrap = document.getElementById('canvaswrap');
    wrap.innerHTML = RENDER[page]();
    // Changing a slice or a scenario re-renders the screen in place. Jumping to the top
    // would throw away the reader's position halfway down a table.
    canvas.scrollTop = keepScroll ? at : 0;
    renderNav();
    wire(wrap);
    mountFunnel(wrap, !keepScroll);
    applySpec();
  }

  function wire(root) {
    root.querySelectorAll('[data-csv]').forEach(function (b) {
      b.addEventListener('click', function () { downloadCsv(b.getAttribute('data-csv')); });
    });
    root.querySelectorAll('[data-slice]').forEach(function (b) {
      b.addEventListener('click', function () { S.slice = b.getAttribute('data-slice'); go(S.page, true); });
    });
    root.querySelectorAll('[data-trend]').forEach(function (b) {
      b.addEventListener('click', function () { S.trend = b.getAttribute('data-trend'); go(S.page, true); });
    });
    root.querySelectorAll('[data-vby]').forEach(function (b) {
      b.addEventListener('click', function () { S.vintageBy = b.getAttribute('data-vby'); go(S.page, true); });
    });
    root.querySelectorAll('[data-goal]').forEach(function (b) {
      b.addEventListener('click', function () { S.goal = +b.getAttribute('data-goal'); go(S.page, true); });
    });
    wireSimulator(root);
    wireDrivers(root);
  }


  /* ------------------------------------------------------------ spec notes */
  // Off by default. When on, every [data-note] element that is actually visible gets a number
  // and the matching text from client_notes.js is printed at the foot of the page. The same key
  // always gets the same number, so a concept that appears twice (two threshold sweeps, say) is
  // explained once. Numbers follow the page order, so they are reassigned on every render.
  function specBadge(n, label, target) {
    // `target` is a function so the badge can point at an element that does not exist yet.
    var b = document.createElement('span');
    b.className = 'specnum';
    b.textContent = n;
    b.tabIndex = 0;
    b.setAttribute('role', 'link');
    b.setAttribute('aria-label', label);
    function jump() { flashInto(target()); }
    b.addEventListener('click', function (e) { e.stopPropagation(); jump(); });
    b.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); jump(); }
    });
    return b;
  }

  function flashInto(el) {
    if (!el) return;
    var calm = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    el.scrollIntoView({ block: 'center', behavior: calm ? 'auto' : 'smooth' });
    el.classList.remove('is-flash');
    void el.offsetWidth;
    el.classList.add('is-flash');
  }

  function applySpec() {
    document.querySelectorAll('.specnum, #specnotes').forEach(function (el) { el.remove(); });
    var btn = document.getElementById('specbtn');
    btn.setAttribute('aria-pressed', S.spec ? 'true' : 'false');
    if (!S.spec) return;

    var notes = window.__NOTES__(F, S);
    var order = [], number = {}, firstBadge = {}, rows = [];
    document.querySelectorAll('[data-note]').forEach(function (el) {
      var key = el.getAttribute('data-note');
      // Skip anything not on screen (the rail on a phone), so a footnote never explains nothing.
      if (!notes[key] || !el.getClientRects().length || el.closest('[inert]')) return;
      if (!(key in number)) { order.push(key); number[key] = order.length; }
      var n = number[key];
      var badge = specBadge(n, 'Spec note ' + n + ': ' + notes[key].t,
        function () { return document.getElementById('specnote-' + n); });
      el.appendChild(badge);
      if (!(key in firstBadge)) firstBadge[key] = badge;
    });
    if (!order.length) return;

    var section = document.createElement('section');
    section.id = 'specnotes';
    section.className = 'specnotes';
    section.setAttribute('aria-label', 'Spec notes');
    section.innerHTML = '<h3>Spec notes</h3><p class="specsub">What each numbered item on this screen is, ' +
      'and what it stands for. Click a number to jump between the item and its note.</p>';
    order.forEach(function (key) {
      var row = document.createElement('div');
      row.className = 'specrow';
      row.id = 'specnote-' + number[key];
      var num = specBadge(number[key], 'Back to item ' + number[key], function () { return firstBadge[key]; });
      var text = document.createElement('div');
      text.innerHTML = '<b></b><p></p>';
      text.firstChild.textContent = notes[key].t;
      text.lastChild.textContent = notes[key].d;
      row.appendChild(num);
      row.appendChild(text);
      section.appendChild(row);
    });
    document.getElementById('canvaswrap').appendChild(section);
  }

  /* ------------------------------------------------------- product and period
   * Two windows decide every figure: the applications replayed (the period chosen here) and the
   * booked loans old enough to judge (the performance window, under Advanced). The period line on
   * each screen says both, so a figure is never read without knowing what it covers.
   *
   * Offline, only the precomputed contexts exist (context_menu in the fixture). With the engine
   * running, any period can be asked for, and the screens are refetched from /api/view. */
  var PRODUCT_NAMES = { TWQR: 'Tawarruq personal finance', IJMB: 'Ijara' };
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  function ctxWindow(w) {
    w = w || CTX.window;
    return w ? { app_from: w.app_from, app_to: w.app_to, performance_months: w.performance_months } : null;
  }
  function ctxQuery(next) {
    var product = next ? next.product : CTX.product, w = ctxWindow(next ? next.window : null);
    var q = ['product=' + encodeURIComponent(product)];
    if (w) Object.keys(w).forEach(function (k) { if (w[k] !== null && w[k] !== undefined) q.push(k + '=' + encodeURIComponent(w[k])); });
    return '?' + q.join('&');
  }
  function ctxBody(body) {
    body.product = CTX.product;
    var w = ctxWindow();
    if (w) body.window = w;
    return body;
  }
  function productPresets(product) {
    var p = MENU && MENU.products[product];
    return p ? p.presets : [];
  }
  function presetById(product, id) { return productPresets(product).filter(function (p) { return p.id === id; })[0]; }
  function presetName() {
    var p = CTX.preset && presetById(CTX.product, CTX.preset);
    return p ? p.name : 'Custom period';
  }
  /** The phone's top bar has room for one chip: product and period in a few characters. */
  function presetShort() {
    var m = /^last_(\d+)m$/.exec(CTX.preset || '');
    return m ? m[1] + ' mo' : CTX.preset === 'all' ? 'All' : 'Custom';
  }
  function monthYear(iso) {
    if (!iso) return '—';
    var d = String(iso).split('-');
    return MONTHS[+d[1] - 1] + ' ' + d[0];
  }
  /** "2026-08-31" or "2026-09-21 12:36 UTC" as the page prints a date: 31 Aug 2026, 12:36 UTC. */
  function dayMonthYear(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}:\d{2}))?/.exec(iso || '');
    return m ? (+m[3]) + ' ' + MONTHS[+m[2] - 1] + ' ' + m[1] + (m[4] ? ', ' + m[4] + ' UTC' : '') : '—';
  }
  /** How current the figures are: the extract they read, and when the engine computed them. */
  function asOfText() {
    var m = F.meta;
    return (m.data_as_of ? 'Data as of ' + dayMonthYear(m.data_as_of) + ' · ' : '') + 'figures built ' + dayMonthYear(m.generated);
  }
  function defaultMonths() { return MENU ? MENU.outcome.within_months : (CTX.window ? CTX.window.performance_months : 12); }

  function periodLine() {
    var w = F.meta.window;
    if (!w) return '';
    return '<p class="periodline"' + N('period_line') + '><b>' + esc(presetName()) + '</b> ' + esc(w.label) +
      ' · ' + n0(w.applicants) + ' applications replayed · bad rate from ' + n0(w.mature_loans) +
      ' loans booked ' + monthYear(w.mature_booked_from) + ' – ' + monthYear(w.mature_booked_to) +
      ', each observed for ' + w.performance_months + ' months' +
      (MENU && w.performance_months !== MENU.outcome.within_months
        ? '. <b class="warnword">Not comparable with the declared ' + MENU.outcome.within_months +
          '-month bad definition</b>: a shorter window counts fewer loans as bad'
        : '') + '<span class="asof"' + N('as_of') + '>' + esc(asOfText()) + '</span></p>';
  }

  function renderChrome() {
    var pc = document.getElementById('productchip'), wc = document.getElementById('periodchip');
    var many = MENU && Object.keys(MENU.products).length > 1;
    pc.innerHTML = '<span class="fig">' + esc(CTX.product) + '</span>' + (many ? '<span class="caret" aria-hidden="true">▾</span>' : '');
    pc.classList.toggle('is-static', !MENU);
    if (wc) {
      wc.hidden = !F.meta.window;
      wc.innerHTML = (CTX.loading ? '<span class="spin" aria-hidden="true"></span>' : '') +
        '<span class="ctxname">' + esc(presetName()) + '</span>' +
        '<span class="ctxshort">' + esc(CTX.product + ' · ' + presetShort()) + '</span>' +
        '<span class="ctxdates hide-sm">' + esc(F.meta.window ? F.meta.window.label : '') + '</span>' +
        (MENU ? '<span class="caret" aria-hidden="true">▾</span>' : '');
      wc.classList.toggle('is-static', !MENU);
      wc.setAttribute('aria-expanded', CTX.open ? 'true' : 'false');
    }
    pc.setAttribute('aria-expanded', CTX.open ? 'true' : 'false');
    document.getElementById('ruleschip').textContent = F.meta.rules_replayed + ' rules replayed';
    document.getElementById('demostriptext').textContent =
      F.meta.applicants.toLocaleString('en-US') + ' generated applicants · ' +
      (F.meta.window ? F.meta.window.label + ' · ' : '') +
      F.meta.rules_replayed + ' real rules replayed · figures are illustrative, ' +
      'the rules and the method are real';
  }

  function menuHtml() {
    var d = CTX.draft, live = SIM.live === true;
    var products = Object.keys(MENU.products);
    var html = '';
    if (products.length > 1) {
      html += '<h5>Product</h5>' + products.map(function (p) {
        return '<label><input type="radio" name="ctxp" value="' + esc(p) + '"' + (d.product === p ? ' checked' : '') + '> ' +
          '<b>' + esc(p) + '</b><span>' + esc(PRODUCT_NAMES[p] || '') + '</span></label>';
      }).join('');
    }
    var range = MENU.products[d.product].data_range;
    html += '<h5>Applications replayed</h5>' + productPresets(d.product).map(function (p) {
      return '<label><input type="radio" name="ctxw" value="' + esc(p.id) + '"' + (d.preset === p.id ? ' checked' : '') + '> ' +
        '<b>' + esc(p.name) + '</b><span>' + esc(p.label) + '</span></label>';
    }).join('') +
      '<label' + (live ? '' : ' class="is-off"') + '><input type="radio" name="ctxw" value="custom"' +
        (d.preset === 'custom' ? ' checked' : '') + (live ? '' : ' disabled') + '> <b>Custom period</b></label>' +
      '<div class="ctxcustom"' + (d.preset === 'custom' ? '' : ' hidden') + '>' +
        '<label>From <input type="date" id="ctxfrom" min="' + range.app_from + '" max="' + range.app_to + '" value="' + esc(d.from || '') + '"></label>' +
        '<label>To <input type="date" id="ctxto" min="' + range.app_from + '" max="' + range.app_to + '" value="' + esc(d.to || '') + '"></label>' +
      '</div>' +
      (live ? '' : '<p>A custom period needs the engine running (<code>python -m ui.serve</code>). ' +
        'The periods above were worked out in advance.</p>') +
      '<details class="ctxadv"' + (d.months !== defaultMonths() ? ' open' : '') + '><summary>Advanced: performance window</summary>' +
        '<label>Judge a loan over <input type="number" id="ctxmonths" min="1" max="24" value="' + d.months + '"' +
          (live ? '' : ' disabled') + '> months</label>' +
        '<p>A booked loan counts towards the bad rate only once it has been on book this long, and is bad if it ' +
        'reached ' + MENU.outcome.dpd + '+ days past due within it. Newer loans are not yet observable, so they never ' +
        'count as good. The extract is dated ' + esc(MENU.outcome.as_of) + '.</p></details>' +
      (CTX.error ? '<p class="ctxerr" role="alert">' + esc(CTX.error) + '</p>' : '') +
      '<div class="ctxactions"><button type="button" class="chip" data-ctx="cancel">Cancel</button>' +
        '<button type="button" class="chip is-primary" data-ctx="apply"' + (CTX.loading ? ' disabled' : '') + '>' +
        (CTX.loading ? 'Loading…' : 'Apply') + '</button></div>';
    return html;
  }

  function renderCtx() {
    renderChrome();
    var menu = document.getElementById('ctxmenu');
    if (!menu || !MENU) return;
    menu.hidden = !CTX.open;
    if (!CTX.open) return;
    menu.innerHTML = menuHtml();
    menu.querySelectorAll('input[name="ctxp"]').forEach(function (r) {
      r.addEventListener('change', function () {
        CTX.draft.product = r.value;
        if (CTX.draft.preset !== 'custom' && !presetById(r.value, CTX.draft.preset)) CTX.draft.preset = productPresets(r.value)[0].id;
        CTX.error = null; renderCtx();
      });
    });
    menu.querySelectorAll('input[name="ctxw"]').forEach(function (r) {
      r.addEventListener('change', function () { CTX.draft.preset = r.value; CTX.error = null; renderCtx(); });
    });
    [['ctxfrom', 'from'], ['ctxto', 'to'], ['ctxmonths', 'months']].forEach(function (pair) {
      var el = document.getElementById(pair[0]);
      if (el) el.addEventListener('change', function () {
        CTX.draft[pair[1]] = pair[1] === 'months' ? +el.value : el.value;
      });
    });
    menu.querySelector('[data-ctx="cancel"]').addEventListener('click', function () { closeMenu(); });
    menu.querySelector('[data-ctx="apply"]').addEventListener('click', applyDraft);
  }

  function openMenu() {
    if (!MENU) return;
    var w = CTX.window || {};
    CTX.draft = { product: CTX.product, preset: CTX.preset || 'custom', from: w.app_from, to: w.app_to,
                  months: w.performance_months || defaultMonths() };
    CTX.open = true; CTX.error = null;
    renderCtx();
    var first = document.querySelector('#ctxmenu input:checked') || document.querySelector('#ctxmenu input');
    if (first) first.focus();
  }
  function closeMenu() { CTX.open = false; CTX.error = null; renderCtx(); }

  /** Turn the menu's choices into a context and load it. */
  function applyDraft() {
    var d = CTX.draft, w;
    if (d.preset === 'custom') {
      if (!d.from || !d.to) { CTX.error = 'Choose both a start and an end date.'; renderCtx(); return; }
      w = { app_from: d.from, app_to: d.to, performance_months: d.months };
    } else {
      var p = presetById(d.product, d.preset);
      w = { app_from: p.app_from, app_to: p.app_to, performance_months: d.months };
    }
    // A preset with a different performance window is no longer that preset.
    var preset = d.preset !== 'custom' && d.months === defaultMonths() ? d.preset : null;
    setContext({ product: d.product, preset: preset, window: w });
  }

  function fixturePayload(next) {
    if (!next.preset) return null;
    var id = next.product + ':' + next.preset;
    return id === ROOT.meta.context ? ROOT : (ROOT.contexts || {})[id] || null;
  }

  function setContext(next) {
    var fixture = fixturePayload(next);
    if (SIM.live !== true) {
      if (!fixture) {
        CTX.error = SIM.live === null ? 'Still connecting to the engine. Try again in a moment.'
          : 'That period was not worked out in advance, and it needs the engine running.';
        renderCtx(); return;
      }
      applyPayload(fixture, next);
      return;
    }
    CTX.loading = true; CTX.error = null; CTX.seq++;
    var seq = CTX.seq;
    renderCtx();
    api('/api/view' + ctxQuery(next)).then(function (view) {
      if (seq !== CTX.seq) return;
      applyPayload(view, next);
    }).catch(function (e) {
      if (seq !== CTX.seq) return;
      CTX.loading = false; CTX.error = e.message; CTX.open = true;
      renderCtx();
    });
  }

  function applyPayload(payload, next) {
    var sameProduct = payload.meta.product === CTX.product;
    F = payload; FM = null; S.goal = 0;
    CTX.product = payload.meta.product;
    CTX.preset = next.preset || null;
    CTX.window = payload.meta.window;
    CTX.loading = false; CTX.open = false; CTX.error = null;
    CTX.seq++;
    window.AnalysisContext.write({ product: CTX.product, preset: CTX.preset, window: ctxWindow() });
    renderCtx();
    simOnContext(sameProduct);
    go(S.page, true);
  }

  /** The Simulator after a change of context: re-run the scenario on a new period, clear it on a new product. */
  function simOnContext(sameProduct) {
    var had = SIM.steps.slice(), label = F.meta.window ? F.meta.window.label : 'the new period';
    var g = SIM.goal;
    g.out = null; g.error = null; g.pending = false;
    if (F.goal_targets && F.goal_targets.length) g.target = Math.round(F.goal_targets[0] * 100);
    if (!sameProduct) g.frozen = [];
    if (!sameProduct) SIM.picked = null;
    SIM.error = null; SIM.steps = []; SIM.out = null; SIM.pending = false; SIM.notice = null;
    if (SIM.live !== true) {
      SIM.rules = F.rule_catalogue || [];
      if (had.length) SIM.notice = { tag: 'SCENARIO CLEARED', html: 'Your change was cleared: its worked-out result belongs to the previous ' + (sameProduct ? 'period.' : 'product.') };
      return;
    }
    var seq = CTX.seq;
    api('/api/health' + ctxQuery()).then(function (h) {
      if (seq !== CTX.seq) return null;
      SIM.health = h;
      return api('/api/rules' + ctxQuery());
    }).then(function (j) {
      if (!j || seq !== CTX.seq) return;
      SIM.rules = j.rules;
      if (SIM.pendingOpen) {
        var sc = SIM.pendingOpen;
        SIM.pendingOpen = null;
        propose(sc.changes.slice(), function (ok) { openedNotice(sc, ok); });
        return;
      }
      if (!had.length) { refreshSim(); return; }
      if (!sameProduct) {
        SIM.notice = { tag: 'SCENARIO CLEARED', html: 'Your changes were cleared: ' + esc(CTX.product) + ' has its own rules.' };
        refreshSim(); return;
      }
      propose(had, function (ok) {
        SIM.notice = ok
          ? { tag: 'PERIOD CHANGED', html: 'Your ' + (had.length === 1 ? 'change was' : had.length + ' changes were') +
              ' re-run on ' + esc(label) + '. Every figure below is for the new period.' }
          : { tag: 'SCENARIO CLEARED', html: 'Your changes could not be re-run on ' + esc(label) + ': ' + esc(SIM.error || 'the engine refused them') + '.' };
        if (!ok) { SIM.error = null; SIM.steps = []; SIM.out = null; }
      });
    }).catch(function (e) { if (seq === CTX.seq) { SIM.error = e.message; refreshSim(); } });
  }

  /** The last context this viewer chose, if it still exists. A preset is restored at once; a custom period waits for the engine. */
  function restoreContext() {
    var saved = window.AnalysisContext.read();
    if (!saved || !MENU || !MENU.products[saved.product]) return null;
    var fixture = fixturePayload(saved);
    if (fixture) {
      if (fixture !== F) {
        F = fixture; FM = null;
        CTX.product = saved.product; CTX.preset = saved.preset; CTX.window = fixture.meta.window;
        if (F.goal_targets && F.goal_targets.length) SIM.goal.target = Math.round(F.goal_targets[0] * 100);
      }
      return null;
    }
    return saved.window ? saved : null;          // custom: load once the engine answers
  }

  function wireContext() {
    var pc = document.getElementById('productchip'), wc = document.getElementById('periodchip');
    [pc, wc].forEach(function (b) {
      if (b) b.addEventListener('click', function (e) { e.stopPropagation(); if (CTX.open) closeMenu(); else openMenu(); });
    });
    document.getElementById('ctxmenu').addEventListener('click', function (e) { e.stopPropagation(); });
    document.addEventListener('click', function () { if (CTX.open) closeMenu(); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && CTX.open) { closeMenu(); (wc || pc).focus(); }
    });
  }

  /* ------------------------------------------------------------------ boot */
  var pendingCustom = restoreContext();
  if (F.goal_targets && F.goal_targets.length && !pendingCustom) SIM.goal.target = Math.round(F.goal_targets[0] * 100);
  renderChrome();
  wireContext();
  document.getElementById('specbtn').addEventListener('click', function () {
    S.spec = !S.spec;
    applySpec();
  });
  // The rail is hidden on a phone until opened, and what is on screen decides what gets a number.
  window.addEventListener('resize', function () {
    if (!S.spec) return;
    clearTimeout(applySpec.t);
    applySpec.t = setTimeout(applySpec, 150);
  });
  document.getElementById('themebtn').addEventListener('click', function () {
    var cur = document.documentElement.getAttribute('data-theme');
    document.documentElement.setAttribute('data-theme', cur === 'dark' ? 'light' : 'dark');
  });
  // tokens.css hides the rail below 860px and reveals it on `.is-open`, with `.scrim`
  // behind it. Toggling any other class leaves the menu button doing nothing on a phone.
  var rail = document.querySelector('.rail');
  var scrim = document.getElementById('scrim');
  function toggleRail(force) {
    var open = force === undefined ? !rail.classList.contains('is-open') : force;
    rail.classList.toggle('is-open', open);
    scrim.classList.toggle('is-open', open);
    if (S.spec) applySpec();
  }
  document.getElementById('railbtn').addEventListener('click', function () { toggleRail(); });
  scrim.addEventListener('click', function () { toggleRail(false); });
  // A different person (the demo menu, later the server) may see a different rail.
  window.Session.onChange(function () { renderNav(); applySpec(); });
  function fromHash() { var h = location.hash.slice(1); return RENDER[h] ? h : 'portfolio'; }
  window.addEventListener('hashchange', function () { if (fromHash() !== S.page) go(fromHash()); });
  connectEngine(0, pendingCustom);
  go(fromHash());
})();
