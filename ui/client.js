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

  var F = window.__CLIENT__;
  var S = { page: 'portfolio', slice: 'employer_segment', goal: 0, spec: false,
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
           'observed on the book only', 'on-obs', N('k_bad')) +
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

    var portfolioPanel = panel('The booked book, sliced', sliceBtns,
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
      '<p>What the current strategy books, and what that book is made of.</p></div>' +
      tiles + funnelPanel + portfolioPanel + sourcePanel();
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

  /* Funnel view. Drawn after insertion because its geometry depends on the width it gets. */
  function svgEl(tag, attrs, text) {
    var el = document.createElementNS(SVGNS, tag);
    Object.keys(attrs || {}).forEach(function (k) { el.setAttribute(k, attrs[k]); });
    if (text !== undefined) el.textContent = text;
    return el;
  }
  function pts(list) { return list.map(function (p) { return p[0].toFixed(1) + ',' + p[1].toFixed(1); }).join(' '); }

  function drawFunnel(host) {
    var M = funnelModel(), width = host.clientWidth;
    if (!width) return;
    var G = window.FunnelModel.geometry(M, { width: width, narrow: width < 560 });
    var svg = svgEl('svg', { width: G.width, height: G.height, viewBox: '0 0 ' + G.width + ' ' + G.height,
      'class': 'fsvg', role: 'group', 'aria-label': 'Funnel from ' + n0(M.total) + ' applicants to ' + n0(M.end.stillIn) + ' booked' });

    G.groupLabels.forEach(function (g) {
      svg.appendChild(svgEl('text', { x: 0, y: g.y, 'class': 'f-gl' }, g.label));
      svg.appendChild(svgEl('line', { x1: 0, x2: G.leftW, y1: g.y + 6, y2: g.y + 6, 'class': 'f-gdiv' }));
    });
    G.names.forEach(function (n) {
      var t = svgEl('text', { x: 0, y: n.y + (n.sub && !G.narrow ? -3 : 4), 'class': 'f-name is-' + n.kind });
      t.textContent = n.label;
      svg.appendChild(t);
      if (n.sub && !G.narrow) svg.appendChild(svgEl('text', { x: 0, y: n.y + 12, 'class': 'f-sub' }, n.sub));
    });
    G.connectors.forEach(function (c) {
      svg.appendChild(svgEl('polygon', { points: pts(c.points), 'class': 'f-conn' }));
    });
    G.bands.forEach(function (b) {
      svg.appendChild(svgEl('rect', { x: b.x, y: b.y, width: b.w, height: b.h, rx: 3, 'class': 'f-band is-' + b.kind }));
      if (b.kind === 'end') {
        // An accounting total's double rule: the terminal result, not another stage.
        svg.appendChild(svgEl('line', { x1: b.x, x2: b.x + b.w, y1: b.y + b.h + 3, y2: b.y + b.h + 3, 'class': 'f-total' }));
        svg.appendChild(svgEl('line', { x1: b.x, x2: b.x + b.w, y1: b.y + b.h + 6, y2: b.y + b.h + 6, 'class': 'f-total' }));
      }
      var anchor = b.place === 'inside' ? 'middle' : b.place === 'right' ? 'start' : 'end';
      svg.appendChild(svgEl('text', { x: b.tx, y: b.ty + 4, 'text-anchor': anchor,
        'class': 'f-blabel' + (b.place === 'inside' ? ' is-in' : '') + (b.kind === 'end' ? ' is-end' : '') }, b.text));
    });
    G.leaks.forEach(function (l) {
      var s = stageById(M, l.id), open = S.fdrill === l.id;
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
      g.appendChild(svgEl('path', { d: l.d, 'stroke-width': l.sw.toFixed(2), 'class': 'f-arrow' }));
      g.appendChild(svgEl('polygon', { points: pts(l.head), 'class': 'f-head' }));
      g.appendChild(svgEl('text', { x: l.lx, y: l.ly - 1, 'class': 'f-l1' }, l.line1 + (l.drillable ? (open ? ' ▾' : ' ›') : '')));
      g.appendChild(svgEl('text', { x: l.lx, y: l.ly + 12, 'class': 'f-l2' }, l.line2));
      svg.appendChild(g);
    });
    host.replaceChildren(svg);
  }

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
        '<div class="ffunnelhost"></div></div>' +
      '<div class="fview' + (view === 'bars' ? ' is-on' : '') + '" data-view="bars"' + (view === 'bars' ? '' : ' inert aria-hidden="true"') + '>' +
        funnelBarsHtml(M) + '</div></div>';

    return '<div class="fpanel">' + panel('Where applicants drop out', seg + pv('OBSERVED'),
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

  function mountFunnel(root) {
    var panelEl = root.querySelector('.fpanel');
    if (!panelEl) return;
    var host = panelEl.querySelector('.ffunnelhost');
    drawFunnel(host);
    panelEl.addEventListener('click', function (e) {
      var v = e.target.closest('[data-fview]');
      if (v) { setView(panelEl, v.getAttribute('data-fview')); return; }
      if (e.target.closest('[data-drill-close]')) { setDrill(panelEl, null); return; }
      if (e.target.closest('[data-drill-more]')) { toggleAllRules(panelEl); return; }
      var t = e.target.closest('[data-drill]');
      // A click with detail 0 came from the keyboard (Enter or Space on a button).
      if (t) setDrill(panelEl, t.getAttribute('data-drill'), t.getAttribute('data-drill'), e.detail === 0);
    });
    panelEl.addEventListener('keydown', function (e) {
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
    return panel('Declines by channel', pv('OBSERVED'),
      table('<th>Channel</th><th class="num">Applicants</th><th class="num"' + N('th_ch_approval') + '>Approval</th>' +
            '<th' + N('th_ch_declines') + '>Declines</th><th class="num"' + N('th_ch_n') + '>n</th>' +
            '<th class="num"' + N('th_ch_share') + '>Share of declines</th>', rows), N('ch_panel'));
  }

  /* =============================================================== screen 2 */
  function pageDrivers() {
    var d = F.drivers;
    var maxD = Math.max.apply(null, d.map(function (r) { return r.declines; }));
    var rows = d.map(function (r) {
      var verdict;
      if (!r.relaxable) {
        verdict = pv('NOT_MODELLED', 'NOT RELAXABLE');
      } else if (r.risk_known) {
        verdict = pv('INFERRED', pct(r.est_bad_rate_if_relaxed, 1)) +
          (r.earns_its_place === false ? ' <span class="verdict">buys no safety</span>' : '');
      } else {
        verdict = pv('NOT_MODELLED', 'NO ESTIMATE');
      }
      return '<tr><td><span class="rid">' + esc(r.rule_id) + '</span><br>' +
        '<span class="verdict">' + esc((r.description || '').slice(0, 72)) + '</span></td>' +
        '<td class="num">' + n0(r.declines) + '</td>' +
        '<td style="width:120px">' + bar(r.declines, maxD) + bar(r.declines_alone, maxD, 'alone') + '</td>' +
        '<td class="num">' + n0(r.declines_alone) + '</td>' +
        '<td>' + verdict + '</td></tr>';
    });

    var noSafety = d.filter(function (r) { return r.earns_its_place === false && r.relaxable; });
    var lead = noSafety.length
      ? caveat('warn', 'Q10',
          '<strong>' + noSafety.length + ' rules cost approvals without buying safety.</strong> ' +
          'The applicants each one declines on its own are no riskier than the book already ' +
          'carries. Top of the list: <span class="rid">' + esc(noSafety[0].rule_id) + '</span> — ' +
          esc(noSafety[0].description) + ' — declining ' + n0(noSafety[0].declines_alone) +
          ' applicants nobody else catches, at an estimated ' + pct(noSafety[0].est_bad_rate_if_relaxed) +
          ' bad rate against a booked ' + pct(F.headline.booked_bad_rate) + '.', N('dr_q10'))
      : '';

    return '<div class="pagehead"><h2' + N('dr_head') + '>Decline drivers</h2>' +
      '<p>Which rule declines the most applicants — and how many it declines on its own, ' +
      'with no other rule catching them.</p></div>' + lead +
      panel('Ranked by applicants declined alone',
        pv('OBSERVED', 'COUNTS') + ' ' + pv('INFERRED', 'RISK'),
        table('<th' + N('th_rule') + '>Rule</th><th class="num"' + N('th_declines') + '>Declines</th>' +
              '<th' + N('th_allalone') + '>All / alone</th><th class="num"' + N('th_alone') + '>Alone</th>' +
              '<th' + N('th_relaxed') + '>Bad rate if relaxed</th>', rows) +
        caveat('', 'WHY ALONE',
          'Switching off a rule that always fires alongside another buys nothing: the other ' +
          'rule still catches those applicants. <em>Alone</em> is the column that answers ' +
          '"what is the one thing I change?".', N('why_alone')) +
        caveat('', 'RISK',
          'A declined applicant has no repayment history, so the bad rate of relaxing a rule ' +
          'is inferred, never observed. Where the group sits outside anything the bank has ' +
          'booked, the engine returns ' + pv('NOT_MODELLED', 'NO ESTIMATE') + ' rather than a ' +
          'number — a confident figure there would tell you to loosen a rule for free.', N('risk_tag')),
        N('dr_rank')) +
      panel('Rules the engine will not judge', pv('NOT_MODELLED'),
        '<p class="note">A rule resting on a regulatory or bureau fact — politically exposed ' +
        'persons, diplomatic service, staff — is never offered as a relaxation, whatever it ' +
        'costs in approvals. Code can measure what a rule costs; it cannot know the bank is ' +
        'allowed to drop it.</p>' +
        table('<th>Rule</th><th class="num">Declines alone</th><th' + N('th_rests') + '>Rests on</th>',
          d.filter(function (r) { return !r.relaxable; }).map(function (r) {
            return '<tr><td><span class="rid">' + esc(r.rule_id) + '</span> ' +
              esc((r.description || '').slice(0, 60)) + '</td>' +
              '<td class="num">' + n0(r.declines_alone) + '</td>' +
              '<td class="verdict">' + esc(r.fields) + '</td></tr>';
          })), N('dr_guard'));
  }

  /* =============================================================== screen 3
   * The simulator starts from today's rules, all on. A person switches rules off or edits a
   * threshold, one step at a time; each step is replayed by the engine behind ui/serve.py and
   * shows what it added on top of the steps before it. Reverting a step asks again without it.
   *
   * With no engine running (the page opened from disk, or `serve --static`) it falls back to
   * the precomputed fixture: the same rule list, but only the switch-offs exported in
   * `rule_toggles` can be tried, one at a time, and goal-seek shows its two precomputed runs.
   * Every figure still comes from the engine; the page only formats. */
  var SIM = {
    live: null,          // null while checking, then true (engine) or false (fixture only)
    health: null, rules: null,
    steps: [], out: null, pending: false, error: null,
    q: '', filter: 'all', showAll: false, editing: null,
    goal: { target: 30, ceiling: null, frozen: [], out: null, pending: false, error: null }
  };
  var RULE_PAGE = 25;
  var OPS = { lt: '<', lte: '≤', gt: '>', gte: '≥' };

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
  function connectEngine(tries) {
    if (location.protocol === 'file:') { engineUnavailable(); return; }
    api('/api/health').then(function (h) {
      if (h.ready) {
        SIM.health = h;
        if (SIM.goal.ceiling === null) SIM.goal.ceiling = +(h.bad_rate_ceiling * 100).toFixed(1);
        return api('/api/rules').then(function (j) {
          SIM.rules = j.rules; SIM.live = true; SIM.steps = []; SIM.out = null;
          refreshSim();
        });
      }
      if (h.loading && (tries || 0) < 60) { setTimeout(function () { connectEngine((tries || 0) + 1); }, 1500); return; }
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

  /* ---- the scenario: an ordered list of changes, at most one per threshold */
  function stepIndex(fn) { for (var i = 0; i < SIM.steps.length; i++) if (fn(SIM.steps[i])) return i; return -1; }
  function stepsFor(rid) { return SIM.steps.filter(function (s) { return s.rule_id === rid; }); }
  function precomputed(rid) { return (F.rule_toggles || []).filter(function (t) { return t.rule_id === rid; })[0]; }

  /** Replace the scenario, replay it, and keep the old one if the engine refuses. */
  function propose(steps) {
    SIM.error = null;
    if (!steps.length) { SIM.steps = []; SIM.out = null; refreshSim(); return; }
    if (!SIM.live) {
      // Fixture mode: one precomputed switch-off at a time, shaped like an engine result.
      var t = precomputed(steps[steps.length - 1].rule_id);
      if (!t) { SIM.error = 'This change needs the engine running. Start it with python -m ui.serve.'; refreshSim(); return; }
      var step = Object.assign({}, t, { change: 'switch off ' + t.rule_id, change_direction: 'loosen',
        direction: 'loosen', added_pp: t.approval_change_pp, added_swap_in: t.swap_in, added_swap_out: t.swap_out });
      SIM.steps = [steps[steps.length - 1]];
      SIM.out = { steps: [step], result: step };
      refreshSim();
      return;
    }
    SIM.pending = true; refreshSim();
    api('/api/simulate', { changes: steps }).then(function (out) {
      SIM.steps = steps; SIM.out = out;
    }).catch(function (e) {
      SIM.error = e.message;
    }).then(function () { SIM.pending = false; refreshSim(); });
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
    SIM.editing = null;
    propose(next);
  }

  /* ---- rendering */
  function num(v) { return v === null || v === undefined ? '—' : Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 }); }
  function fieldName(f) { return String(f).split('.').pop(); }
  function condText(t) {
    if (t.operator === 'between') return fieldName(t.field) + ' between ' + num(t.value_low) + ' and ' + num(t.value_high);
    if (t.operator === 'outside') return fieldName(t.field) + ' outside ' + num(t.value_low) + '–' + num(t.value_high);
    return fieldName(t.field) + ' ' + (OPS[t.operator] || t.operator) + ' ' + num(t.value_low);
  }
  function stepText(s) {
    if (s.type === 'off') return 'Switch off ' + s.rule_id;
    return s.rule_id + ': ' + fieldName(s.field) + ' → ' + num(s.value_low) +
      (s.value_high !== undefined ? '–' + num(s.value_high) : '');
  }
  function signed(v) { return v === null || v === undefined ? '—' : (v > 0 ? '+' : v < 0 ? '−' : '') + n0(Math.abs(v)); }

  function lockIcon(r) {
    if (!r.locked && !r.fixed_field) return '';
    return '<span class="rlock ' + (r.locked ? 'is-locked' : 'is-fixed') + '" aria-hidden="true">' +
      '<svg width="10" height="11" viewBox="0 0 10 11"><path d="M2.5 5V3.5a2.5 2.5 0 0 1 5 0V5" fill="none" stroke="currentColor" stroke-width="1.2"/>' +
      '<rect x="1" y="5" width="8" height="5.5" rx="1.2" stroke="currentColor" stroke-width="1.2"/></svg></span>';
  }

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

  function ruleRow(r, first) {
    var mine = stepsFor(r.rule_id);
    var off = mine.some(function (s) { return s.type === 'off'; });
    var canTry = r.editable && (SIM.live || precomputed(r.rule_id));
    var why = !r.editable ? r.reason : (!canTry ? 'needs the engine running' : '');
    var state = mine.map(function (s) {
      return '<span class="simtag">step ' + (SIM.steps.indexOf(s) + 1) + ': ' +
        esc(s.type === 'off' ? 'off' : fieldName(s.field) + ' → ' + num(s.value_low) +
            (s.value_high !== undefined ? '–' + num(s.value_high) : '')) + '</span>';
    }).join('');
    var editBtn = r.editable && SIM.live && r.thresholds.length && !off
      ? '<button class="btn ghost sm" data-sim-edit="' + esc(r.rule_id) + '"' + (first ? N('sim_edit') : '') + '>' +
        (SIM.editing === r.rule_id ? 'Close' : 'Edit threshold') + '</button>' : '';
    var editor = SIM.editing === r.rule_id ? thresholdEditor(r) : '';
    return '<li class="simrule' + (off ? ' is-off' : '') + (mine.length && !off ? ' is-edited' : '') + '">' +
      '<label class="simsw' + (canTry ? '' : ' is-disabled') + '">' +
        '<input type="checkbox" data-sim-rule="' + esc(r.rule_id) + '"' + (off ? '' : ' checked') +
        (canTry && !SIM.pending ? '' : ' disabled') + ' aria-label="' + esc(r.rule_id) + ' on"></label>' +
      '<div class="rn"><span class="rl">' + lockIcon(r) + esc(r.label) + '</span>' +
        '<span class="rsub"><span class="rid">' + esc(r.rule_id) + '</span>' +
        (r.tests ? '<span>' + esc(r.tests) + '</span>' : '') +
        (why ? '<span class="simwhy">' + esc(why) + '</span>' : '') +
        (r.editable && !r.declines_alone ? '<span class="simwhy">no effect on its own</span>' : '') +
        state + '</span></div>' +
      '<div class="rc">' + n0(r.declines_alone) + '<small>alone</small></div>' +
      '<div class="rcell">' + editBtn + '</div>' + editor + '</li>';
  }

  function thresholdEditor(r) {
    var rows = r.thresholds.map(function (t, i) {
      var cur = SIM.steps.filter(function (s) { return s.rule_id === r.rule_id && s.field === t.field; })[0];
      var lo = cur ? cur.value_low : t.value_low;
      var hi = cur && cur.value_high !== undefined ? cur.value_high : t.value_high;
      var range = t.value_high !== null && t.value_high !== undefined;
      return '<div class="simedrow" data-sim-field="' + esc(t.field) + '" data-i="' + i + '">' +
        '<span class="simedk">Declines when ' + esc(condText(t)) + ' today</span>' +
        '<span class="simedv">' + esc(fieldName(t.field)) + ' ' +
          (range ? esc(t.operator) + ' ' : esc(OPS[t.operator] || t.operator) + ' ') +
          '<input type="number" step="any" class="siminput" data-bound="lo" value="' + esc(lo) + '" aria-label="' + esc(fieldName(t.field)) + ' threshold">' +
          (range ? ' and <input type="number" step="any" class="siminput" data-bound="hi" value="' + esc(hi) + '" aria-label="' + esc(fieldName(t.field)) + ' upper bound">' : '') +
          ' <button class="btn sm" data-sim-apply="' + esc(r.rule_id) + '">Try it</button></span></div>';
    }).join('');
    return '<div class="simeditor">' + rows +
      '<p class="simnote">Raising or lowering a threshold can loosen <em>or</em> tighten the rule. The result says which, ' +
      'and a tightening is the only way anyone approved today is newly declined.</p></div>';
  }

  function rulesPanel() {
    if (!SIM.rules) return panel('Rules', '', '<p class="note">Loading the rule list…</p>');
    var all = visibleRules();
    var shown = SIM.showAll || SIM.q ? all : all.slice(0, RULE_PAGE);
    var filters = [['all', 'All'], ['alone', 'Declines someone alone'], ['editable', 'Can be changed'], ['changed', 'Changed']]
      .map(function (f) {
        return '<button data-sim-filter="' + f[0] + '" aria-pressed="' + (SIM.filter === f[0]) + '">' + f[1] + '</button>';
      }).join('');
    var body =
      '<div class="simtools"><input type="search" class="siminput simsearch" id="simsearch" placeholder="Search rules, fields, policy codes" ' +
        'value="' + esc(SIM.q) + '" aria-label="Search rules"><div class="fseg">' + filters + '</div></div>' +
      '<div class="fdrill-cols simcols"><span></span><span>Rule</span><span' + N('sim_alone') + '>Declines alone</span><span></span></div>' +
      '<ul class="fdrill-list simlist" id="simlist">' +
        (shown.length ? shown.map(function (r, i) { return ruleRow(r, i === 0); }).join('')
                      : '<li class="simempty">No rule matches.</li>') + '</ul>' +
      (all.length > shown.length
        ? '<button class="fmore" data-sim-more>Show all ' + all.length + ' rules</button>' : '');
    return panel((SIM.rules.length) + ' decline rules, all on today', '', body, N('sim_rules'));
  }

  function stackPanel() {
    var out = SIM.out;
    var items = SIM.steps.map(function (s, i) {
      var st = out && out.steps[i];
      var dir = st && st.change_direction;
      return '<li><span class="simn">' + (i + 1) + '</span><div class="rn"><span class="rl">' + esc(stepText(s)) + '</span>' +
        '<span class="rsub">' + (dir ? '<span>' + esc(dir === 'tighten' ? 'tightens' : dir === 'loosen' ? 'loosens' : dir) + '</span>' : '') +
        (st ? '<span' + (i === 0 ? N('sim_added') : '') + '>' + pp(st.added_pp) + ' · ' + signed(st.added_swap_in) + ' approved' +
          (st.added_swap_out ? ' · ' + signed(st.added_swap_out) + ' declined' : '') + '</span>' : '') +
        '</span></div><button class="btn ghost sm" data-sim-revert="' + i + '"' + (SIM.pending ? ' disabled' : '') +
        ' aria-label="Revert step ' + (i + 1) + '">Revert</button></li>';
    }).join('');
    var body = SIM.steps.length
      ? '<ol class="simstack">' + items + '</ol>' +
        '<button class="fmore" data-sim-reset' + (SIM.pending ? ' disabled' : '') + '>Reset to today\'s rules</button>'
      : '<p class="note">Nothing changed yet. Untick a rule to switch it off, or edit a threshold. Each change is a ' +
        'step; add more to build on it, and revert any step to see the scenario without it.</p>';
    return panel('Your scenario', SIM.pending ? '<span class="simbusy">Replaying…</span>' : '', body, N('sim_stack'));
  }

  function resultPanel() {
    var t = SIM.out && SIM.out.result;
    if (!t) return '';
    var tightens = t.swap_out > 0 || SIM.out.steps.some(function (s) { return s.change_direction === 'tighten' || s.change_direction === 'mixed'; });
    var swapRows = Object.keys(t.swap_in_by_channel || {}).map(function (k) {
      var v = t.swap_in_by_channel[k];
      return '<tr><td>' + esc(k) + '</td><td class="num">' + n0(v.swap_in) + '</td>' +
        (tightens ? '<td class="num">' + n0(v.swap_out) + '</td>' : '') + '</tr>';
    });
    return panel('After ' + (SIM.steps.length === 1 ? 'this change' : 'all ' + SIM.steps.length + ' changes'), '',
      '<div class="tiles c4">' +
        tile('Approval rate ' + pv('OBSERVED'), pct(t.approval_rate),
             pp(t.approval_change_pp) + ' from ' + pct(F.headline.approval_rate), '', N('t_approval')) +
        tile('Newly approved ' + pv('OBSERVED'), n0(t.swap_in), 'swap-ins', '', N('t_in')) +
        tile('Newly declined ' + pv('OBSERVED'), n0(t.swap_out),
             t.swap_out ? 'their observed bad rate ' + pct(t.swap_out_observed_bad_rate, 1) : 'swap-outs', '', N('t_out')) +
        tile('Expected bad rate ' + (t.swap_in ? riskPill(t.risk_known) : pv('OBSERVED')),
             t.risk_known ? pct(t.expected_bad_rate, 2) : '<span class="nodata">—</span>',
             'was ' + pct(F.headline.booked_bad_rate, 2),
             t.risk_known ? '' : 'hatch-nm', N('t_bad')) +
      '</div>' +
      caveat(t.risk_known ? '' : 'warn', t.risk_known ? 'VERDICT' : 'UNKNOWN', esc(t.verdict), N('verdict_tag')) +
      table('<th' + N('th_sw_channel') + '>Channel</th><th class="num">Newly approved</th>' +
            (tightens ? '<th class="num">Newly declined</th>' : ''), swapRows) +
      (tightens ? '' : '<p class="note simnote">No one is newly declined: every change here loosens a rule. ' +
        'Tighten a threshold to see who today\'s approvals would lose.</p>'), N('sw_panel'));
  }

  function modeNote() {
    if (SIM.live === null) return caveat('', 'ENGINE', 'Connecting to the engine…', N('sim_mode'));
    if (SIM.live) return '';
    return caveat('warn', 'PRECOMPUTED',
      'The engine is not running, so this screen shows scenarios worked out in advance: the ' +
      (F.rule_toggles || []).length + ' busiest rules can be switched off, one at a time, and goal-seek shows two ' +
      'fixed targets. Start the engine with <code>python -m ui.serve</code> to switch off any rule, edit thresholds, ' +
      'stack changes and set your own target.', N('sim_mode'));
  }

  function pageSimulator() {
    var sweepPanels = (F.sweeps || []).map(function (sw) {
      var cells = sw.rows.map(function (r, i) {
        return '<div class="s' + (r.note === 'current' ? ' is-current' : '') + '">' +
          '<div class="c"' + (i === 0 ? N('sweep_cell') : '') + '>' + esc(sw.field === 'simahcreditscore' ? 'SIMAH ' : 'CRIF ') + r.cutoff + '</div>' +
          '<div class="a">' + pct(r.approval_rate) + '</div>' +
          '<div class="b">' + (r.note === 'current' ? 'current' : pp(r.approval_change_pp)) + '<br>' +
          (r.risk_known ? 'bad ' + pct(r.expected_bad_rate, 2) : '<span class="nodata">no estimate</span>') +
          '</div></div>';
      }).join('');
      return panel(sw.label, pv('OBSERVED', 'APPROVAL') + ' ' + pv('INFERRED', 'RISK'),
        '<div class="sweep">' + cells + '</div>', N('sweep'));
    }).join('');

    return '<div class="pagehead"><h2' + N('sim_head') + '>Simulator</h2>' +
      '<p>Start from today\'s rules. Switch rules off or move a threshold, one step at a time, and see who moves.</p></div>' +
      modeNote() +
      (SIM.error ? caveat('warn', 'REFUSED', esc(SIM.error)) : '') +
      '<div class="simgrid"><div class="simmain">' + rulesPanel() + '</div>' +
      '<div class="simside">' + stackPanel() + '</div></div>' + resultPanel() +
      goalPanel() + sweepPanels;
  }

  /* ---- goal-seek */
  function goalCandidates() {
    var gs = SIM.health && SIM.health.goal_search;
    if (!gs || !SIM.rules) return [];
    return SIM.rules.filter(function (r) { return r.editable && r.declines_alone >= gs.min_declines_alone; })
      .slice(0, gs.max_rule_candidates);
  }

  function runGoal() {
    var g = SIM.goal;
    g.pending = true; g.error = null; refreshSim();
    api('/api/goal-seek', { target: g.target === null ? null : g.target / 100,
                             ceiling: g.ceiling === null ? null : g.ceiling / 100, frozen: g.frozen }).then(function (out) {
      g.out = out;
    }).catch(function (e) { g.error = e.message; })
      .then(function () { g.pending = false; refreshSim(); });
  }

  function goalOptions(g) {
    return g.options.map(function (o, i) {
      var cls = o.breaches_ceiling ? 'is-breach' : (i === 0 && o.reaches_target ? 'is-best' : '');
      var steps = String(o.option).replace(/^[A-Z]:\s*/, '').split(' + ')
        .map(function (s, j) { return '<li' + (j === 0 ? N('opt_steps') : '') + '>' + esc(s) + '</li>'; }).join('');
      return '<div class="opt ' + cls + '"><h4' + N('opt_head') + '>' + esc(String(o.option).slice(0, 2)) +
        (o.reaches_target ? pv('OBSERVED', 'REACHES TARGET') : pv('NOT_MODELLED', 'FALLS SHORT')) +
        (o.breaches_ceiling ? pv('NOT_MODELLED', 'BREACHES BAD-RATE CEILING') : '') + '</h4>' +
        '<div class="optgrid">' +
          '<div><div class="k">Approval</div><div class="v">' + pct(o.approval_rate) + '</div></div>' +
          '<div><div class="k">Change</div><div class="v">' + pp(o.approval_change_pp) + '</div></div>' +
          '<div><div class="k">Newly approved</div><div class="v">' + n0(o.swap_in) + '</div></div>' +
          '<div><div class="k">Expected bad</div><div class="v">' +
            (o.risk_known ? pct(o.expected_bad_rate, 2) : '<span class="nodata">—</span>') + '</div></div>' +
          '<div><div class="k"' + N('opt_risk') + '>Risk cost</div><div class="v">' + pp(o.risk_cost_pp) + '</div></div>' +
        '</div><ul class="steps">' + steps + '</ul></div>';
    }).join('');
  }

  function goalVerdict(g) {
    return caveat(g.reached ? 'obs' : 'warn', g.reached ? 'REACHED' : 'OUT OF REACH',
      g.reached
        ? 'Options are ranked by <strong>risk cost</strong> — the cheapest way to get there, ' +
          'not the largest change. Anything above the ' + pct(g.ceiling, 1) +
          ' bad-rate ceiling is flagged and never ranked first.'
        : 'No combination of the changes available reaches ' + pct(g.target, 1) +
          '. These are the closest the engine can get, best first. ' +
          '"Maximise approvals" on its own is solved by approving everyone, so every search ' +
          'is bounded by the ' + pct(g.ceiling, 1) + ' bad-rate ceiling.', N('goal_tag'));
  }

  function goalForm() {
    var g = SIM.goal, gs = SIM.health.goal_search, cands = goalCandidates();
    var chips = cands.map(function (r) {
      var frozen = g.frozen.indexOf(r.rule_id) >= 0;
      return '<button class="chip" data-goal-freeze="' + esc(r.rule_id) + '" aria-pressed="' + frozen + '" title="' + esc(r.label) + '">' +
        (frozen ? lockIcon({ locked: true }) : '') + esc(r.rule_id) + '</button>';
    }).join(' ');
    return '<div class="simgoal">' +
      '<label class="simfield"' + N('goal_target') + '><span>Target approval rate</span>' +
        '<span class="simunit"><input type="number" class="siminput" id="goaltarget" min="0" max="100" step="0.5" value="' + esc(g.target) + '">%</span>' +
        '<small>today ' + pct(F.headline.approval_rate) + '</small></label>' +
      '<label class="simfield"' + N('goal_ceiling') + '><span>Bad-rate ceiling</span>' +
        '<span class="simunit"><input type="number" class="siminput" id="goalceiling" min="0" max="100" step="0.5" value="' + esc(g.ceiling) + '">%</span>' +
        '<small>today\'s book ' + pct(F.headline.booked_bad_rate, 2) + '</small></label>' +
      '<button class="btn" data-goal-run' + (g.pending ? ' disabled' : '') + '>' + (g.pending ? 'Searching…' : 'Find options') + '</button>' +
      '</div>' +
      '<div class="simfrozen"><span class="simedk"' + N('goal_frozen') + '>Rules the search may switch off. Click one to keep it on:</span> ' + chips +
      '<p class="simnote">It may also try ' + gs.field_moves.length + ' cutoff moves set in config' +
      (gs.field_moves.length ? ' (' + esc(gs.field_moves.join('; ')) + ')' : '') + ', combined up to ' +
      gs.max_depth + ' at a time.</p></div>';
  }

  function goalPanel() {
    if (SIM.live) {
      var g = SIM.goal;
      return panel('Goal-seek: reach a target approval rate', '',
        goalForm() +
        (g.error ? caveat('warn', 'REFUSED', esc(g.error)) : '') +
        (g.pending ? '<p class="note simbusy">Searching combinations — this takes several seconds.</p>' : '') +
        (g.out && !g.pending ? goalVerdict(g.out) + goalOptions(g.out) : '') +
        caveat('', 'LIMIT',
          'This is a ranked shortlist for a human to take to a risk committee, not a proof of ' +
          'optimality. Loosening a policy is a committee decision, not a calculation.', N('limit')), N('goal'));
    }
    if (!F.goal_seek.length) return '';
    var chips = F.goal_seek.map(function (gg, i) {
      return '<button class="chip" data-goal="' + i + '"' + (i === S.goal ? ' aria-current="true"' : '') +
        '>' + pct(gg.target, 0) + ' approval</button>';
    }).join(' ');
    var pre = F.goal_seek[S.goal];
    return panel('Goal-seek: reach a target approval rate', chips,
      '<p class="note">Two targets worked out in advance. With the engine running you type your own target and ceiling.</p>' +
      goalVerdict(pre) + goalOptions(pre) +
      caveat('', 'LIMIT',
        'This is a ranked shortlist for a human to take to a risk committee, not a proof of ' +
        'optimality. Loosening a policy is a committee decision, not a calculation.', N('limit')), N('goal'));
  }

  function wireSimulator(root) {
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
      b.addEventListener('click', function () { SIM.showAll = true; go('simulator', true); });
    });
    root.querySelectorAll('[data-sim-rule]').forEach(function (b) {
      b.addEventListener('change', function () { switchRule(b.getAttribute('data-sim-rule'), b.checked); });
    });
    root.querySelectorAll('[data-sim-edit]').forEach(function (b) {
      b.addEventListener('click', function () {
        var rid = b.getAttribute('data-sim-edit');
        SIM.editing = SIM.editing === rid ? null : rid;
        go('simulator', true);
      });
    });
    root.querySelectorAll('[data-sim-apply]').forEach(function (b) {
      b.addEventListener('click', function () {
        var rid = b.getAttribute('data-sim-apply');
        var row = b.closest('.simedrow');
        var rule = SIM.rules.filter(function (r) { return r.rule_id === rid; })[0];
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
  }

  /* ------------------------------------------------------------------- nav */
  var PAGES = [
    { id: 'portfolio', t: 'Portfolio', n: '1' },
    { id: 'drivers', t: 'Decline drivers', n: '2' },
    { id: 'simulator', t: 'Simulator', n: '3' },
    { id: 'settings', t: 'Settings', n: '4' }
  ];
  // The Settings page lives in settings.js, which owns its own state and events.
  var RENDER = { portfolio: pagePortfolio, drivers: pageDrivers, simulator: pageSimulator,
                 settings: function () { return window.SettingsScreen.page(); } };

  function renderNav() {
    document.getElementById('rail').innerHTML =
      '<div class="railgroup"><h4' + N('rail_screens') + '>Screens</h4>' + PAGES.map(function (p) {
        return '<button class="navitem" data-page="' + p.id + '"' +
          (S.page === p.id ? ' aria-current="page"' : '') + '>' +
          '<span class="n">' + p.n + '</span><span class="lbl">' + esc(p.t) + '</span></button>';
      }).join('') + '</div>' +
      (S.page === 'settings' ? window.SettingsScreen.rail() : '') +
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
    var wrap = document.getElementById('canvaswrap');
    wrap.innerHTML = RENDER[page]();
    // Changing a slice or a scenario re-renders the screen in place. Jumping to the top
    // would throw away the reader's position halfway down a table.
    canvas.scrollTop = keepScroll ? at : 0;
    renderNav();
    wire(wrap);
    mountFunnel(wrap);
    if (page === 'settings') window.SettingsScreen.after();
    applySpec();
  }

  function wire(root) {
    root.querySelectorAll('[data-slice]').forEach(function (b) {
      b.addEventListener('click', function () { S.slice = b.getAttribute('data-slice'); go(S.page, true); });
    });
    root.querySelectorAll('[data-goal]').forEach(function (b) {
      b.addEventListener('click', function () { S.goal = +b.getAttribute('data-goal'); go(S.page, true); });
    });
    wireSimulator(root);
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

    // The Settings page keeps its notes in settings_notes.js; the keys never overlap.
    var notes = Object.assign({}, window.__NOTES__(F, S), window.__SETTINGS_NOTES__(window.__SETTINGS__));
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

  /* ------------------------------------------------------------------ boot */
  document.getElementById('ruleschip').textContent = F.meta.rules_replayed + ' rules replayed';
  document.getElementById('productchip').innerHTML = '<span class="fig">' + esc(F.meta.product) + '</span>';
  document.getElementById('demostriptext').textContent =
    F.meta.applicants.toLocaleString('en-US') + ' generated applicants · ' +
    F.meta.rules_replayed + ' real rules replayed · figures are illustrative, ' +
    'the rules and the method are real';
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
  window.SettingsScreen.init({
    wrap: document.getElementById('canvaswrap'), rail: document.getElementById('rail'),
    go: go, closeRail: function () { toggleRail(false); }, refreshSpec: applySpec
  });
  connectEngine(0);
  go('portfolio');
})();
