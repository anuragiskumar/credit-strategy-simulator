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
  var S = { page: 'portfolio', slice: 'employer_segment', toggle: 0, goal: 0, spec: false };

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

    var max = F.funnel[0].left;
    var steps = F.funnel.map(function (r) {
      var isDrop = r.dropped > 0;
      return '<div class="rulestep' + (isDrop ? ' is-drop' : '') + '">' +
        '<div class="lbl"' + N('stage_' + r.stage) + '>' + esc(r.stage.replace(/_/g, ' ')) + '</div>' +
        '<div class="bar"><i style="width:' + ((r.left / max) * 100).toFixed(1) + '%"></i>' +
        '<b>' + n0(r.left) + ' in · ' + r.left_pct.toFixed(1) + '%</b></div>' +
        '<div class="drop">' + (isDrop ? '−' + n0(r.dropped) : '') + '</div></div>';
    }).join('');

    var funnelPanel = panel('Where applicants drop out', pv('OBSERVED'),
      '<div class="rulefunnel">' +
        '<div class="rulestep rulehead" aria-hidden="true"><div class="lbl">Stage</div>' +
        '<div class="bar-h">Still in<span class="hide-sm"> after this stage</span></div>' +
        '<div class="drop">Lost here</div></div>' + steps + '</div>' +
      caveat('', 'NOTE',
        'Every stage here is derived by replaying the rules, never assigned. The reason ' +
        'attached to each declined applicant is the rule that actually caught them.'), N('funnel'));

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

  /* =============================================================== screen 3 */
  function pageSimulator() {
    if (!F.rule_toggles.length) {
      return '<div class="pagehead"><h2>Simulator</h2></div>' +
        caveat('warn', 'DATA', 'This fixture was built with <code>--quick</code>, which skips ' +
          'the scenario grid. Run <code>python -m ui.client_export</code> for the full build.');
    }

    var t = F.rule_toggles[S.toggle];
    var chips = F.rule_toggles.map(function (r, i) {
      return '<button class="chip" data-toggle="' + i + '"' + (i === S.toggle ? ' aria-current="true"' : '') +
        '>' + esc(r.rule_id) + '</button>';
    }).join(' ');

    var swapRows = Object.keys(t.swap_in_by_channel || {}).map(function (k) {
      var v = t.swap_in_by_channel[k];
      return '<tr><td>' + esc(k) + '</td><td class="num">' + n0(v.swap_in) + '</td>' +
        '<td class="num">' + n0(v.swap_out) + '</td></tr>';
    });

    var togglePanel = panel('Switch one rule off', chips,
      '<p class="note">' + esc(t.description) + '</p>' +
      '<div class="tiles c4" style="margin-top:12px">' +
        tile('Approval rate ' + pv('OBSERVED'), pct(t.approval_rate),
             pp(t.approval_change_pp) + ' from ' + pct(F.headline.approval_rate), '', N('t_approval')) +
        tile('Newly approved ' + pv('OBSERVED'), n0(t.swap_in), 'swap-ins', '', N('t_in')) +
        tile('Newly declined ' + pv('OBSERVED'), n0(t.swap_out), 'swap-outs', '', N('t_out')) +
        tile('Expected bad rate ' + riskPill(t.risk_known),
             t.risk_known ? pct(t.expected_bad_rate, 2) : '<span class="nodata">—</span>',
             'was ' + pct(F.headline.booked_bad_rate, 2),
             t.risk_known ? '' : 'hatch-nm', N('t_bad')) +
      '</div>' +
      caveat(t.risk_known ? '' : 'warn', t.risk_known ? 'SWAP-IN' : 'UNKNOWN', esc(t.verdict), N('verdict_tag')) +
      table('<th' + N('th_sw_channel') + '>Channel</th><th class="num">Newly approved</th>' +
            '<th class="num">Newly declined</th>', swapRows), N('sw_panel'));

    var sweepPanels = F.sweeps.map(function (sw) {
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
      '<p>Change one thing, and see who moves.</p></div>' + togglePanel + sweepPanels + goalPanel();
  }

  function goalPanel() {
    if (!F.goal_seek.length) return '';
    var chips = F.goal_seek.map(function (g, i) {
      return '<button class="chip" data-goal="' + i + '"' + (i === S.goal ? ' aria-current="true"' : '') +
        '>' + pct(g.target, 0) + ' approval</button>';
    }).join(' ');
    var g = F.goal_seek[S.goal];

    var opts = g.options.map(function (o, i) {
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

    return panel('Goal-seek: reach a target approval rate', chips,
      caveat(g.reached ? 'obs' : 'warn', g.reached ? 'REACHED' : 'OUT OF REACH',
        g.reached
          ? 'Options are ranked by <strong>risk cost</strong> — the cheapest way to get there, ' +
            'not the largest change. Anything above the ' + pct(g.ceiling, 0) +
            ' bad-rate ceiling is flagged and never ranked first.'
          : 'No combination of the changes available reaches ' + pct(g.target, 0) +
            '. These are the closest the engine can get, best first. ' +
            '"Maximise approvals" on its own is solved by approving everyone, so every search ' +
            'is bounded by the ' + pct(g.ceiling, 0) + ' bad-rate ceiling.', N('goal_tag')) +
      opts +
      caveat('', 'LIMIT',
        'This is a ranked shortlist for a human to take to a risk committee, not a proof of ' +
        'optimality. Loosening a policy is a committee decision, not a calculation.', N('limit')), N('goal'));
  }

  /* ------------------------------------------------------------------- nav */
  var PAGES = [
    { id: 'portfolio', t: 'Portfolio', n: '1' },
    { id: 'drivers', t: 'Decline drivers', n: '2' },
    { id: 'simulator', t: 'Simulator', n: '3' }
  ];
  var RENDER = { portfolio: pagePortfolio, drivers: pageDrivers, simulator: pageSimulator };

  function renderNav() {
    document.getElementById('rail').innerHTML =
      '<div class="railgroup"><h4' + N('rail_screens') + '>Screens</h4>' + PAGES.map(function (p) {
        return '<button class="navitem" data-page="' + p.id + '"' +
          (S.page === p.id ? ' aria-current="page"' : '') + '>' +
          '<span class="n">' + p.n + '</span><span class="lbl">' + esc(p.t) + '</span></button>';
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
    var wrap = document.getElementById('canvaswrap');
    wrap.innerHTML = RENDER[page]();
    // Changing a slice or a scenario re-renders the screen in place. Jumping to the top
    // would throw away the reader's position halfway down a table.
    canvas.scrollTop = keepScroll ? at : 0;
    renderNav();
    wire(wrap);
    applySpec();
  }

  function wire(root) {
    root.querySelectorAll('[data-slice]').forEach(function (b) {
      b.addEventListener('click', function () { S.slice = b.getAttribute('data-slice'); go(S.page, true); });
    });
    root.querySelectorAll('[data-toggle]').forEach(function (b) {
      b.addEventListener('click', function () { S.toggle = +b.getAttribute('data-toggle'); go(S.page, true); });
    });
    root.querySelectorAll('[data-goal]').forEach(function (b) {
      b.addEventListener('click', function () { S.goal = +b.getAttribute('data-goal'); go(S.page, true); });
    });
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
      if (!notes[key] || !el.getClientRects().length) return;
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
  go('portfolio');
})();
