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
    view: 'target',      // 'target' | 'try' | 'rules'
    steps: [], out: null, pending: false, error: null,
    q: '', filter: 'all', showAll: false, editing: null,
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
  function propose(steps) {
    SIM.error = null;
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
    return ruleName(s.rule_id) + ': ' + fieldName(s.field) + ' → ' + num(s.value_low) +
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
      (rows.length ? table('<th' + N('th_sw_channel') + '>Channel</th><th class="num">Newly approved</th>' +
        (tightens ? '<th class="num">Newly declined</th>' : ''), rows) : ''));
  }

  function legend() {
    return '<div class="simlegend"' + N('sim_legend') + '><span><i class="c-obs"></i>counted from the replay</span>' +
      '<span><i class="c-inf"></i>estimated for applicants never booked</span>' +
      '<span><i class="c-nm"></i>no estimate possible</span></div>';
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
    var W = 560, H = 300, L = 56, R = 16, T = 14, B = 42;
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
    var out = SIM.out, h = F.headline;
    if (!SIM.steps.length) {
      return panel('Your scenario', '', '<p class="note">Nothing changed yet. Each change you make is a step. ' +
        'Add more to build on it, and remove any step to see the scenario without it.</p>', N('sim_stack'));
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
    return panel('Your scenario', SIM.pending ? '<span class="simbusy">Replaying…</span>' : '',
      '<div class="wfall">' + rows + '</div>' +
      '<p class="simnote">Bars show approval rate; the axis starts at ' + pct(lo, 0) + '.</p>' +
      '<button class="fmore" data-sim-reset' + (SIM.pending ? ' disabled' : '') + '>Reset to today\'s rules</button>', N('sim_stack'));
  }

  /* ---- Try a change: story presets, two sliders, the busiest rules */
  function presets() {
    var list = [], rules = (SIM.rules || []).filter(function (r) { return r.editable && r.declines_alone; });
    if (rules[0]) {
      list.push({ id: 'bottleneck', t: 'Remove the biggest bottleneck',
        d: 'Switch off “' + rules[0].label + '”, which on its own stops ' + n0(rules[0].declines_alone) + ' applicants.',
        steps: [{ type: 'off', rule_id: rules[0].rule_id }] });
    }
    // Rules whose release keeps the book's bad rate at or below today's, biggest gain first.
    var safe = (F.rule_toggles || []).filter(function (t) {
      return t.risk_known && t.expected_bad_rate <= F.headline.booked_bad_rate;
    }).sort(function (a, b) { return b.approval_change_pp - a.approval_change_pp; }).slice(0, 2);
    if (safe.length) {
      list.push({ id: 'safe', t: 'Grow approvals safely',
        d: 'Switch off ' + joinWords(safe.map(function (t) { return '“' + ruleName(t.rule_id) + '”'; })) +
           ': each one alone keeps the bad rate at or below today\'s.',
        steps: safe.map(function (t) { return { type: 'off', rule_id: t.rule_id }; }) });
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
    }).join('') + '</div>';
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
        panel('Where this leaves the book', '', frontier(pointsList, { aria: 'Approval rate against bad rate, today and your scenario' }) + legend()) +
        waterfall() +
      '</div></div>';
  }

  /* ---- All rules: the analyst's workbench */
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
      '<div class="rc">' + n0(r.declines_alone) + '<small>only this</small></div>' +
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
    var filters = [['all', 'All'], ['alone', 'Stops someone on its own'], ['editable', 'Can be changed'], ['changed', 'Changed']]
      .map(function (f) {
        return '<button data-sim-filter="' + f[0] + '" aria-pressed="' + (SIM.filter === f[0]) + '">' + f[1] + '</button>';
      }).join('');
    var body =
      '<div class="simtools"><input type="search" class="siminput simsearch" id="simsearch" placeholder="Search rules, fields, policy codes" ' +
        'value="' + esc(SIM.q) + '" aria-label="Search rules"><div class="fseg">' + filters + '</div></div>' +
      '<div class="fdrill-cols simcols"><span></span><span>Rule</span><span' + N('sim_alone') + '>Only this rule stops</span><span></span></div>' +
      '<ul class="fdrill-list simlist" id="simlist">' +
        (shown.length ? shown.map(function (r, i) { return ruleRow(r, i === 0); }).join('')
                      : '<li class="simempty">No rule matches.</li>') + '</ul>' +
      (all.length > shown.length
        ? '<button class="fmore" data-sim-more>Show all ' + all.length + ' rules</button>' : '');
    return panel((SIM.rules.length) + ' decline rules, all on today', '', body, N('sim_rules'));
  }

  function sweepPanels() {
    return (F.sweeps || []).map(function (sw) {
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
  }

  function viewRules() {
    return '<div class="simgrid"><div class="simmain">' + rulesPanel() + '</div>' +
      '<div class="simside">' + waterfall() + '</div></div>' +
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
    api('/api/goal-seek', { target: g.target === null ? null : g.target / 100,
                             ceiling: g.ceiling === null ? null : g.ceiling / 100, frozen: g.frozen }).then(function (out) {
      g.out = out;
    }).catch(function (e) { g.error = e.message; })
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
      (canApply ? '<button class="btn" data-goal-apply="0"' + N('goal_apply') + '>Try this as a scenario</button>' : '') +
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
        (SIM.live && o.changes && o.changes.length ? '<button class="btn ghost sm" data-goal-apply="' + i + '">Try this as a scenario</button>' : '') +
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
    return '<div class="simgoal">' +
      '<label class="simfield"' + N('goal_target') + '><span>Reach an approval rate of</span>' +
        '<span class="simunit"><input type="number" class="siminput" id="goaltarget" min="0" max="100" step="0.5" value="' + esc(g.target) + '">%</span>' +
        '<small>today ' + pct(F.headline.approval_rate) + '</small></label>' +
      '<label class="simfield"' + N('goal_ceiling') + '><span>without the bad rate going above</span>' +
        '<span class="simunit"><input type="number" class="siminput" id="goalceiling" min="0" max="100" step="0.5" value="' + esc(g.ceiling) + '">%</span>' +
        '<small>today ' + pct(F.headline.booked_bad_rate, 2) + '</small></label>' +
      '<button class="btn" data-goal-run' + (g.pending ? ' disabled' : '') + '>' + (g.pending ? 'Searching…' : 'Find the way') + '</button>' +
      '</div>' +
      disclose('constraints', 'Constraints',
        '<div class="simfrozen"><span class="simedk"' + N('goal_frozen') + '>Rules the search may switch off. Click one to keep it on:</span> ' + chips +
        '<p class="simnote">It may also try ' + gs.field_moves.length + ' cutoff moves set in config' +
        (gs.field_moves.length ? ' (' + esc(gs.field_moves.join('; ')) + ')' : '') + ', combined up to ' +
        gs.max_depth + ' at a time.</p></div>');
  }

  function goalResult(res) {
    return '<div class="simgrid is-goal"><div>' + recommendation(res) + otherOptions(res) + '</div>' +
      '<div>' + goalChart(res) + legend() + '</div></div>' +
      '<p class="simfoot"' + N('limit') + '>A shortlist for the risk committee, not a decision.</p>';
  }

  function viewTarget() {
    if (SIM.live) {
      var g = SIM.goal;
      return panel('How do we reach a target approval rate?', '',
        goalForm() +
        (g.error ? caveat('warn', 'REFUSED', esc(g.error)) : '') +
        (g.pending ? '<p class="note simbusy">Searching combinations — this takes several seconds.</p>' : '') +
        (g.out && !g.pending ? goalResult(g.out) : ''), N('goal'));
    }
    if (SIM.live === null || !F.goal_seek.length) return '';
    var chips = F.goal_seek.map(function (gg, i) {
      return '<button class="chip" data-goal="' + i + '"' + (i === S.goal ? ' aria-current="true"' : '') +
        '>' + pct(gg.target, 0) + ' approval</button>';
    }).join(' ');
    return panel('How do we reach a target approval rate?', chips, goalResult(F.goal_seek[S.goal]), N('goal'));
  }

  function modeNote() {
    if (SIM.live === null) return '<p class="simmode"' + N('sim_mode') + '>Connecting to the engine…</p>';
    if (SIM.live) return '';
    return '<p class="simmode"' + N('sim_mode') + '>Worked out in advance: one change at a time. ' +
      'Start the engine (<code>python -m ui.serve</code>) to stack changes and set your own target.</p>';
  }

  var VIEWS = [['target', 'Set a target'], ['try', 'Try a change'], ['rules', 'All rules']];

  function pageSimulator() {
    var tabs = '<div class="fseg simviews" role="tablist"' + N('sim_views') + '>' + VIEWS.map(function (v) {
      return '<button role="tab" data-sim-view="' + v[0] + '" aria-pressed="' + (SIM.view === v[0]) + '" aria-selected="' +
        (SIM.view === v[0]) + '">' + v[1] + '</button>';
    }).join('') + '</div>';
    var body = SIM.view === 'target' ? viewTarget() : SIM.view === 'try' ? viewTry() : viewRules();
    var scenario = SIM.view === 'target' ? '' :
      '<div class="simsticky"' + N('sim_outcome') + '>' + outcomeBar() +
        (SIM.error ? caveat('warn', 'REFUSED', esc(SIM.error)) : '') + outcomeDetails() + '</div>';
    return '<div class="pagehead simhead"><div><h2' + N('sim_head') + '>Simulator</h2>' +
      '<p>Change today\'s rules and see who moves, or name a target and let the engine find the way.</p></div>' +
      tabs + '</div>' + modeNote() +
      (SIM.error && SIM.view === 'target' ? caveat('warn', 'REFUSED', esc(SIM.error)) : '') +
      scenario + body;
  }

  function wireSimulator(root) {
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
      b.addEventListener('click', function () { SIM.showAll = true; go('simulator', true); });
    });
    root.querySelectorAll('[data-sim-rule]').forEach(function (b) {
      b.addEventListener('change', function () {
        SIM.refocus = '[data-sim-rule="' + b.getAttribute('data-sim-rule') + '"]';
        switchRule(b.getAttribute('data-sim-rule'), b.checked);
      });
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
    mountFunnel(wrap);
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
  // A different person (the demo menu, later the server) may see a different rail.
  window.Session.onChange(function () { renderNav(); applySpec(); });
  function fromHash() { var h = location.hash.slice(1); return RENDER[h] ? h : 'portfolio'; }
  window.addEventListener('hashchange', function () { if (fromHash() !== S.page) go(fromHash()); });
  connectEngine(0);
  go(fromHash());
})();
