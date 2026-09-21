/* Settings: what the analysis runs on, in four tabs. Every signed-in person sees this page; what
 * each one may change on it is decided by Session (session.js), never by a role name here.
 *
 *   Analysis            the product and period this person is looking at (their own view, kept by
 *                       context_store.js), the rule pack, the bad definition, when the figures were
 *                       computed, and the Recompute button (recompute.run)
 *   Risk appetite       the bad-rate ceiling, the multiples under Advanced, what the optimiser may
 *                       never relax and what goal-seek may move. Maker and checker: policy.propose
 *                       proposes, policy.approve approves someone else's proposal
 *   Replay assumptions  what the replay does where the rule files are silent, with what each one
 *                       decides; assumptions.change edits them
 *   Data health         missing values, rules the data cannot evaluate, and (data.view) the fields
 *
 * An approved value changes no figure until the next recompute, and the page says so wherever it
 * shows one. The workbook inventory, the data source and the audit log are on admin.html.
 *
 * Figures come from window.__SETTINGS__ (ui/settings_export.py) and, with the engine running,
 * from /api/settings. The page computes nothing: it only formats. Its one conversation with the
 * server is the settings API: reading the governed settings, proposing, deciding, changing and
 * recomputing. Nothing else leaves the browser.
 */
(function () {
  'use strict';

  var K = window.SettingsKit;
  var esc = K.esc, n0 = K.n0, pct = K.pct, pv = K.pv, N = K.N, plural = K.plural;
  var tile = K.tile, section = K.section, accordion = K.accordion, caveat = K.caveat, table = K.table, kv = K.kv;
  var F = window.__SETTINGS__, SIM = F.simulated, CX = F.context;
  var can = window.Session.can, paused = window.Session.paused;

  var TABS = [
    { id: 'analysis', t: 'Analysis' },
    { id: 'appetite', t: 'Risk appetite' },
    { id: 'assumptions', t: 'Replay assumptions' },
    { id: 'health', t: 'Data health' }
  ];

  var S = {
    tab: tabFrom(location.hash),
    live: null,            // null connecting · true engine answering · false fixture only
    gov: F.governed,       // the governed settings, as the fixture or the engine last gave them
    busy: null,            // the action waiting on the engine, e.g. 'propose:bad_rate_ceiling'
    msg: null,             // { kind, text } the last thing the engine said
    form: {},              // which propose forms are open, and what is typed in them
    ctx: null, ctxMsg: null,
    open: {}
  };
  var poll = 0;

  function tabFrom(hash) {
    var id = String(hash || '').replace(/^#(sec-)?/, '');
    return TABS.some(function (t) { return t.id === id; }) ? id : 'analysis';
  }

  /* ================================================================ engine */
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
  function product() { return (S.ctx && S.ctx.product) || (CX ? CX.default_product : F.meta.product); }

  function load(quiet) {
    if (location.protocol === 'file:') { S.live = false; redraw(); return; }
    api('/api/settings?product=' + encodeURIComponent(product())).then(function (g) {
      S.gov = g; S.live = true;
      clearTimeout(poll);
      if (g.recompute && g.recompute.running) poll = setTimeout(function () { load(true); }, 1500);
      redraw();
    }).catch(function () {
      if (!quiet) { S.live = false; redraw(); }
    });
  }
  function act(kind, path, body, done) {
    if (S.busy) return;
    S.busy = kind; S.msg = null; redraw();
    body.who = window.Session.who() || null;
    api(path, body).then(function (r) {
      S.busy = null;
      if (done) done(r);
      load(true);
    }).catch(function (e) {
      S.busy = null; S.msg = { kind: 'warn', text: e.message }; redraw();
    });
  }
  function redraw() { window.PageShell.draw(true); }

  /* ================================================================ formatting */
  var when = K.when, val = K.setVal;
  function setting(key) { return (S.gov ? S.gov.settings : []).filter(function (s) { return s.key === key; })[0]; }
  function group(g) { return (S.gov ? S.gov.settings : []).filter(function (s) { return s.group === g; }); }
  function impacts() {
    if (!S.gov) return null;
    if (S.gov.impacts && S.gov.impacts.product) return S.gov.impacts;          // the engine: one product
    return S.gov.impacts ? S.gov.impacts[product()] || null : null;          // the fixture: every product
  }
  function offline() {
    return S.live === false ? '<p class="su-help">Changing a setting needs the engine running. These are the values the figures were computed on.</p>' : '';
  }
  function message() {
    return S.msg ? '<div class="su-gap" role="alert">' + caveat(S.msg.kind === 'warn' ? 'warn' : '', S.msg.kind === 'warn' ? 'REFUSED' : 'DONE', esc(S.msg.text)) + '</div>' : '';
  }
  function awaiting() {
    if (!S.gov || !S.gov.awaiting_recompute) return '';
    var list = S.gov.settings.filter(function (s) { return s.awaiting_recompute; }).map(function (s) {
      return esc(s.label) + ' ' + val(s, s.value);
    }).join(' · ');
    return '<div class="su-gap"' + N('gv_waiting') + '>' + caveat('warn', 'APPROVED · NOT APPLIED',
      '<strong>The figures do not use these values yet:</strong> ' + list + '. They take effect on the next recompute' +
      (can('recompute.run') ? ', on the <a href="#analysis" data-tab="analysis">Analysis</a> tab.' : '.')) + '</div>';
  }

  /* ================================================================ tab: analysis */
  function presets(p) { return CX && CX.products[p] ? CX.products[p].presets : []; }
  function presetOf(ctx) {
    var list = presets(ctx.product);
    return list.filter(function (x) { return x.id === ctx.preset; })[0] || null;
  }
  function currentCtx() {
    var saved = S.ctx;
    if (saved && CX && CX.products[saved.product]) return saved;
    return CX ? { product: CX.default_product, preset: CX.default_preset } : { product: F.meta.product, preset: null };
  }
  function periodText(ctx) {
    var p = presetOf(ctx);
    if (p) return esc(p.name) + ' · ' + esc(p.label);
    if (ctx.window && ctx.window.app_from) return 'Custom period · ' + esc(ctx.window.app_from) + ' to ' + esc(ctx.window.app_to);
    return 'The default period';
  }

  function secContext() {
    var ctx = currentCtx(), RP = F.rulepack, O = F.outcome;
    var name = CX && CX.products[ctx.product] ? CX.products[ctx.product].name : '';
    var computed = S.live && S.gov && S.gov.computed_at ? when(S.gov.computed_at) : esc(F.run.generated || F.meta.generated);
    var rows = [
      { k: 'Product', v: '<b>' + esc(ctx.product) + '</b>' + (name ? ' · ' + esc(name) : '') },
      { k: 'Applications replayed', v: periodText(ctx) },
      { k: 'A loan is bad when', v: esc(O.definition[0].value) + ' within ' + esc(O.definition[1].value) },
      { k: 'Performance read as of', v: esc(O.as_of) },
      { k: 'Rule pack', v: n0(F.run.rules_replayed) + ' rules replayed for ' + esc(RP.product) + ', from ' + n0(RP.totals.files) +
          ' workbooks updated ' + esc(RP.updated) +
          ' <span class="su-faint su-mono">· version ' + esc(RP.version) + '</span>' +
          (can('admin.view') ? ' <a class="su-manage" href="admin.html#sec-rules">Workbooks</a>' : '') },
      { k: 'Figures computed', v: computed }
    ];
    return section('context', 'What the figures cover', '',
      '<div class="su-kv">' + rows.map(function (r) {
        return '<div class="k">' + esc(r.k) + '</div><div class="v">' + r.v + '</div>';
      }).join('') + '</div>' + chooser(ctx), N('an_head'));
  }

  /** Product and period: this person's own view, the same choice as the period control on each screen. */
  function chooser(ctx) {
    if (!CX) return '';
    var d = S.form.ctx || (S.form.ctx = { product: ctx.product, preset: presetOf(ctx) ? ctx.preset : null });
    var products = Object.keys(CX.products);
    return '<div class="su-sub su-gap"' + N('an_choose') + '>Change what you are looking at</div>' +
      '<div class="su-grid">' +
      (products.length > 1 ? '<div class="su-field"><span class="su-legend">Product</span><div class="su-choice">' + products.map(function (p) {
        return '<label class="su-radio"><input type="radio" name="su-cp" value="' + esc(p) + '"' + (d.product === p ? ' checked' : '') + '>' +
          '<div><b>' + esc(p) + '</b><span>' + esc(CX.products[p].name) + '</span></div></label>';
      }).join('') + '</div></div>' : '') +
      '<div class="su-field"><span class="su-legend">Applications replayed</span><div class="su-choice">' + presets(d.product).map(function (x) {
        return '<label class="su-radio"><input type="radio" name="su-cw" value="' + esc(x.id) + '"' + (d.preset === x.id ? ' checked' : '') + '>' +
          '<div><b>' + esc(x.name) + '</b><span>' + esc(x.label) + '</span></div></label>';
      }).join('') + '</div></div></div>' +
      '<div class="su-row su-gap"><button type="button" class="btn sm" data-act="ctx"' + (d.preset ? '' : ' disabled') + '>Apply</button>' +
      '<span class="su-help">Your own view: it changes what you see on every screen, and nothing anyone else sees. ' +
      'A custom range is chosen from the period control on the analysis screens.</span></div>' +
      (S.ctxMsg ? '<p class="su-help su-gap" role="status">' + S.ctxMsg + '</p>' : '');
  }
  function applyCtx() {
    var d = S.form.ctx, p = presets(d.product).filter(function (x) { return x.id === d.preset; })[0];
    if (!p) return;
    var next = { product: d.product, preset: p.id, window: { app_from: p.app_from, app_to: p.app_to, performance_months: p.performance_months } };
    var kept = window.AnalysisContext.write(next);
    S.ctx = next;
    S.ctxMsg = kept
      ? 'Every screen now opens on ' + esc(d.product) + ', ' + esc(p.name.toLowerCase()) + '. <a href="client.html#portfolio">Open Portfolio</a>'
      : 'This browser keeps nothing between pages, so the screens open on the default.';
    load(true);
    redraw();
  }

  function secRecompute() {
    var R = S.gov && S.gov.recompute, running = R && R.running;
    var body = '<p class="su-lead">Rebuilds every figure on the rules, the data and the approved settings. The figures in use keep ' +
      'answering until the new ones are ready.</p>';
    if (R && R.error) body += caveat('warn', 'FAILED', 'The last recompute failed and the figures were left as they were: ' + esc(R.error));
    else if (R && R.finished_at && !running) body += '<p class="su-help" role="status">Last recomputed ' + when(R.finished_at) + (R.by ? ' by ' + esc(R.by) : '') + '.</p>';
    if (can('recompute.run')) {
      var stopped = paused('recompute.run');
      body += '<div class="su-row su-gap"><button type="button" class="btn sm" data-act="recompute"' + N('an_recompute') +
        (stopped || running || S.live !== true || S.busy ? ' disabled' : '') + '>' + (running ? 'Recomputing…' : 'Recompute') + '</button>' +
        '<span class="su-help" aria-live="polite">' + esc(stopped ? SIM.licence.refresh.paused_message
          : running ? 'Started ' + when(R.started_at) + '. This takes under a minute.'
          : S.live === true ? '' : 'Recompute needs the engine running.') + '</span></div>';
    }
    return section('recompute', 'Recompute', '', body + awaiting(), N('an_recompute_head'));
  }

  /* ================================================================ tab: risk appetite */
  function status(s) {
    var a = s.approved;
    var line = a ? 'Approved by ' + esc(a.by) + ', ' + when(a.at) + (a.proposed_by && a.proposed_by !== a.by ? ' · proposed by ' + esc(a.proposed_by) : '')
                 : 'As set in the configuration file';
    if (s.awaiting_recompute) line += ' · <b>the figures still use ' + val(s, s.applied) + ' until the next recompute</b>';
    return '<p class="su-status">' + line + '</p>';
  }
  function pending(s) {
    var p = s.pending;
    if (!p) return '';
    var who = window.Session.who(), mine = who && who === p.proposed_by;
    var busy = S.busy && S.busy.indexOf(p.id) >= 0;
    var acts = '';
    if (S.live === true) {
      if (mine) acts = '<button type="button" class="btn ghost sm" data-act="decide" data-id="' + esc(p.id) + '" data-ok="0"' + (busy ? ' disabled' : '') + '>Withdraw</button>';
      else if (can('policy.approve')) acts =
        '<button type="button" class="btn sm" data-act="decide" data-id="' + esc(p.id) + '" data-ok="1"' + (busy ? ' disabled' : '') + '>Approve</button>' +
        '<button type="button" class="btn ghost sm" data-act="decide" data-id="' + esc(p.id) + '" data-ok="0"' + (busy ? ' disabled' : '') + '>Reject</button>';
    }
    return '<div class="su-pending"' + N('ra_pending') + '><div class="su-pending-h"><span class="su-flag">WAITING FOR APPROVAL</span>' +
      '<b>' + val(s, p.from) + ' → ' + val(s, p.to) + '</b></div>' +
      '<p>Proposed by ' + esc(p.proposed_by) + ', ' + when(p.proposed_at) + ': “' + esc(p.reason) + '”</p>' +
      (acts ? '<div class="su-row">' + acts + '</div>'
            : '<p class="su-help">' + (mine ? '' : 'A risk approver other than the proposer approves or rejects it.') + '</p>') + '</div>';
  }
  function proposeForm(s) {
    if (!can('policy.propose') || s.pending) return '';
    if (S.live !== true) return '';
    var f = S.form[s.key];
    if (!f) return '<button type="button" class="btn ghost sm su-gap" data-act="open" data-key="' + esc(s.key) + '"' + N('ra_propose') + '>Propose a change</button>';
    var rate = s.unit === 'rate';
    return '<div class="su-form su-gap"><div class="su-grid">' +
      '<div class="su-field"><label for="su-v-' + esc(s.key) + '">New value <i>' + (rate ? '%' : '×') + ', ' +
        (rate ? (s.lo * 100) + ' to ' + (s.hi * 100) : s.lo + ' to ' + s.hi) + '</i></label>' +
        '<input class="su-input" id="su-v-' + esc(s.key) + '" data-f="' + esc(s.key) + '" data-k="v" type="number" step="' + (rate ? '0.5' : '0.05') + '" value="' + esc(f.v) + '"></div>' +
      '<div class="su-field wide"><label for="su-r-' + esc(s.key) + '">Reason <i>the approver reads this</i></label>' +
        '<textarea class="su-input" id="su-r-' + esc(s.key) + '" data-f="' + esc(s.key) + '" data-k="r" maxlength="280">' + esc(f.r) + '</textarea></div></div>' +
      '<div class="su-row su-gap"><button type="button" class="btn sm" data-act="propose" data-key="' + esc(s.key) + '"' + (S.busy ? ' disabled' : '') + '>Send for approval</button>' +
      '<button type="button" class="btn ghost sm" data-act="close" data-key="' + esc(s.key) + '">Cancel</button></div></div>';
  }
  function settingRow(s) {
    return '<div class="su-setting"><div class="su-setting-h"><div><b>' + esc(s.label) + '</b><span>' + esc(s.help) + '</span></div>' +
      '<div class="val">' + val(s, s.value) + '</div></div>' + status(s) + pending(s) + proposeForm(s) + '</div>';
  }

  function secCeiling() {
    var s = setting('bad_rate_ceiling');
    if (!s) return section('ceiling', 'Bad-rate ceiling', '', '<p class="su-help">Not available.</p>');
    return section('ceiling', 'Bad-rate ceiling', '',
      '<div class="su-headline"><div class="su-big fig"' + N('ra_ceiling') + '>' + val(s, s.value) + '</div>' +
      '<p class="su-lead">' + esc(s.help) + ' Goal-seek searches under it, and the Simulator flags any scenario above it.</p></div>' +
      status(s) + pending(s) + proposeForm(s) + offline(), N('ra_head'));
  }
  function secAdvanced() {
    return accordion('advanced', 'Advanced: how swap-ins and rules are judged', '',
      group('advanced').map(settingRow).join('') + offline(), N('ra_advanced'), S.open.advanced);
  }
  function secBounds() {
    var P = F.policy;
    var levers = table('<th>Change</th><th class="num">From</th><th class="num">To</th>',
      P.levers.map(function (l) {
        return '<tr><td title="' + esc(l.field) + '">' + esc(l.label) + '</td><td class="num">' + esc(l.from) + '</td><td class="num">' + esc(l.to) + '</td></tr>';
      }));
    return section('bounds', 'What the optimiser may and may not touch', '',
      '<div class="su-policy"><div><div class="su-sub"' + N('po_hard') + '>Never relaxed</div>' +
        '<p class="su-help">Regulatory and staff checks stay in force in every strategy:</p>' +
        '<ul class="su-list">' + P.hard_reject.map(function (h) { return '<li title="' + esc(h.field) + '">' + esc(h.label) + '</li>'; }).join('') + '</ul></div>' +
      '<div><div class="su-sub"' + N('po_levers') + '>What goal-seek may move</div>' + levers + '</div></div>' +
      '<p class="su-help su-gap">Both lists are set in the configuration file.</p>', N('po_head'));
  }
  function secHistory() {
    var H = S.gov ? S.gov.history : [];
    var STATUS = { approved: 'Approved', rejected: 'Rejected', withdrawn: 'Withdrawn', pending: 'Waiting' };
    var body = H.length ? table('<th>Proposed</th><th>Setting</th><th class="num">Change</th><th>By</th><th>Decision</th>',
      H.map(function (r) {
        var direct = r.route === 'direct';
        return '<tr><td class="su-mono su-muted">' + when(r.proposed_at) + '</td><td>' + esc(r.label) +
          (r.reason ? '<br><small class="su-muted">“' + esc(r.reason) + '”</small>' : '') + '</td>' +
          '<td class="num">' + val(r, r.from) + ' → ' + val(r, r.to) + '</td><td>' + esc(r.proposed_by) + '</td>' +
          '<td>' + (direct ? 'Changed directly' : esc(STATUS[r.status] || r.status) +
            (r.decided_by ? ' by ' + esc(r.decided_by) + '<br><small class="su-muted">' + when(r.decided_at) + '</small>' : '')) + '</td></tr>';
      })) : '<p class="su-help">No change has been proposed yet. Every value is as set in the configuration file.</p>';
    return section('history', 'Changes', '', body, N('ra_history'));
  }
  function secOther() {
    var P = F.policy;
    return accordion('other', 'Other values the analysis uses', '',
      '<div class="su-policy"><div><div class="su-sub">Risk model</div>' + K.pvRows(P.model) + '</div>' +
      '<div><div class="su-sub">Portfolio and product</div>' + K.pvRows(P.portfolio.concat(P.product)) + '</div></div>' +
      '<p class="su-help su-gap">Set in the configuration file.</p>', N('ra_other'), S.open.other);
  }

  /* ================================================================ tab: replay assumptions */
  function secAssumptions() {
    var I = impacts(), prod = I ? I.product : product();
    var rows = group('assumption').map(function (s) {
      var imp = I && I[s.key];
      var effect = !imp ? '' : imp.changed
        ? 'Switching it would change whether a rule declines <b>' + n0(imp.changed) + '</b> of ' + n0(I.applicants) + ' ' + esc(prod) +
          ' applications (' + pct(imp.share, 1) + '): ' + n0(imp.newly_declined) + ' newly declined, ' + n0(imp.newly_passed) + ' newly passed.'
        : 'Switching it would change no ' + esc(prod) + ' applicant\'s decision: everyone it would decline is already declined by another rule.';
      var ctl = can('assumptions.change') && S.live === true
        ? '<button type="button" class="btn ghost sm" data-act="flip" data-key="' + esc(s.key) + '"' + (S.busy ? ' disabled' : '') + '>Change to ' + val(s, !s.value) + '</button>'
        : '';
      return '<div class="su-setting"><div class="su-setting-h"><div><b>' + esc(s.label) + '</b><span>' + esc(s.help) + '</span></div>' +
        '<div class="val">' + val(s, s.value) + '</div></div>' +
        (effect ? '<p class="su-impact"' + N('as_impact') + '>' + effect + ' ' + pv('OBSERVED') + '</p>' : '') +
        status(s) + (ctl ? '<div class="su-row">' + ctl + '</div>' : '') + '</div>';
    });
    var free = I && I.no_rule_matched;
    rows.push('<div class="su-setting"><div class="su-setting-h"><div><b>An applicant no rule declines is approved</b>' +
      '<span>Fixed, not a switch: the rule files hold decline rules only, so there is no rule to approve with.</span></div>' +
      '<div class="val">Approve</div></div>' +
      (free ? '<p class="su-impact"' + N('as_fixed') + '>It decides <b>' + n0(free.applies) + '</b> of ' + n0(I.applicants) + ' ' + esc(prod) +
        ' applications (' + pct(free.share, 1) + '). ' + pv('OBSERVED') + '</p>' : '') + '</div>');
    return section('assumptions', 'Replay assumptions', '',
      '<p class="su-lead">What the replay does where the rule files are silent. Only the risk approver changes these; each change is ' +
      'recorded and takes effect on the next recompute. What each one decides is counted on the figures in use.</p>' +
      rows.join('') + offline(), N('as_head'));
  }

  /* ================================================================ tab: data health */
  function secHealth() {
    var R = F.run, D = F.dataset, C = F.fields;
    if (!R.available || !D.available) return section('health', 'Data health', '', caveat('warn', 'NO DATA', 'No applicant dataset is loaded.'), N('dh_head'));
    var nulls = (D.nulls || []).map(function (n) {
      return '<tr><td><span class="rid">' + esc(n.column) + '</span></td><td class="num">' + pct(n.share, 1) + '</td>' +
        '<td style="width:140px"><span class="su-nullbar" style="width:' + Math.max(1, Math.round(n.share * 100)) + '%"></span></td></tr>';
    });
    var nu = R.unevaluable.length;
    var uneval = nu
      ? caveat('warn', 'NOT EVALUATED', '<strong>' + n0(nu) + ' ' + plural(nu, 'rule reads', 'rules read') +
          ' data the applicant table does not carry</strong>, so ' + plural(nu, 'it declines', 'they decline') + ' no one: ' +
          R.unevaluable.map(function (id) { return '<span class="rid">' + esc(id) + '</span>'; }).join(', ') + '.' +
          (C.unsupplied.length ? ' Missing: ' + C.unsupplied.map(function (u) {
            return 'a <abbr class="su-expr" title="' + esc(u.field) + '">derived value</abbr> read by ' + n0(u.rules) + ' ' + plural(u.rules, 'rule');
          }).join('; ') + '.' : ''), N('dh_uneval'))
      : caveat('obs', 'EVALUATED', 'Every rule in scope can be evaluated on the data.');
    return section('health', 'Data health', pv('OBSERVED'),
      '<div class="tiles c4">' +
        tile('Required fields', n0(C.required_mapped) + ' of ' + n0(C.required), 'supplied by the data', 'on-obs', N('dh_fields')) +
        tile('Fields with gaps', n0(nulls.length), 'have missing values', 'on-obs') +
        tile('Rules not evaluated', n0(nu), 'the data cannot answer them', 'on-obs') +
        tile('Rules that catch nobody', n0(R.never_fire_count), 'of ' + n0(R.rules_replayed) + ' · listed on <a href="client.html#drivers">Decline drivers</a>', 'on-obs', N('rn_never')) +
      '</div>' +
      '<div class="su-gap">' + uneval + '</div>' +
      '<div class="su-sub su-gap"' + N('rn_nulls') + '>Fields with missing values</div>' +
      table('<th>Field</th><th class="num">Missing</th><th></th>', nulls) +
      '<p class="su-help su-gap">' + n0(D.rows) + ' applications, ' + esc(D.date_from) + ' to ' + esc(D.date_to) + '. Checked ' + esc(R.generated) + '.</p>',
      N('dh_head'));
  }
  function secMapping() {
    var C = F.fields;
    var rows = C.columns.filter(function (r) { return r.need !== 'Not requested'; }).map(function (r) {
      return '<tr><td><span class="rid">' + esc(r.column) + '</span></td><td class="su-mono su-muted">' + esc(r.dtype) + '</td>' +
        '<td><span class="su-tag need-' + esc(r.need.split(' ')[0]) + '">' + esc(r.need) + '</span></td>' +
        '<td class="num">' + (r.rules ? n0(r.rules) : '<span class="nodata">—</span>') + '</td>' +
        '<td class="num">' + (r.null_share ? pct(r.null_share, 1) : '<span class="nodata">—</span>') + '</td></tr>';
    });
    return accordion('mapping', 'Fields the rules read', pv('OBSERVED'),
      '<p class="su-help">Each field in the applicant table, whether the rules need it, and how many read it.' +
      (can('admin.view') ? ' <a class="su-manage" href="admin.html#sec-mapping">Edit the mapping</a>' : '') + '</p>' +
      '<div class="su-scroll su-gap"><div class="tablewrap"><table class="t su-compact"><thead><tr><th>Field</th><th>Type</th>' +
      '<th' + N('mp_need') + '>Need</th><th class="num">Rules</th><th class="num">Missing</th></tr></thead><tbody>' +
      rows.join('') + '</tbody></table></div></div>', N('mp_head'), S.open.mapping);
  }

  /* ================================================================ page */
  var BUILD = {
    analysis: [secContext, secRecompute],
    appetite: [function () { return message() + awaiting(); }, secCeiling, secAdvanced, secBounds, secHistory, secOther],
    assumptions: [function () { return message() + awaiting(); }, secAssumptions],
    health: [secHealth, function () { return can('data.view') ? secMapping() : ''; }]
  };

  function tabs() {
    return '<div class="su-tabs" role="tablist" aria-label="Settings"' + N('pg_tabs') + '>' + TABS.map(function (t) {
      var on = t.id === S.tab;
      return '<button type="button" class="chip" role="tab" data-tab="' + t.id + '" aria-selected="' + on + '"' +
        (on ? ' aria-current="true"' : '') + '>' + esc(t.t) + '</button>';
    }).join('') + '</div>';
  }
  function render() {
    return '<div class="pagehead"><h2' + N('pg_head') + '>Settings</h2>' +
      '<p>What the analysis runs on, and the values the risk committee owns.</p></div>' +
      tabs() + '<div role="tabpanel" aria-label="' + esc(TABS.filter(function (t) { return t.id === S.tab; })[0].t) + '">' +
      BUILD[S.tab].map(function (b) { return b(); }).join('') + '</div>';
  }
  function select(id) {
    var next = tabFrom('#' + id);
    S.msg = null;
    if (next !== S.tab) { S.tab = next; window.PageShell.draw(false); }
    if (location.hash !== '#' + next) history.replaceState(null, '', '#' + next);
  }

  function click(e) {
    var t = e.target.closest('[data-tab]');
    if (t) { e.preventDefault(); select(t.getAttribute('data-tab')); return true; }
    var b = e.target.closest('[data-act]');
    if (!b) return false;
    var a = b.getAttribute('data-act'), key = b.getAttribute('data-key');
    if (a === 'ctx') applyCtx();
    else if (a === 'recompute') act('recompute', '/api/recompute', {});
    else if (a === 'open') {
      var s = setting(key);
      S.form[key] = { v: s.unit === 'rate' ? Math.round(s.value * 1000) / 10 : s.value, r: '' };
      redraw();
    } else if (a === 'close') { delete S.form[key]; redraw(); }
    else if (a === 'propose') {
      var st = setting(key), f = S.form[key];
      var to = st.unit === 'rate' ? Number(f.v) / 100 : Number(f.v);
      act('propose:' + key, '/api/settings/propose', { setting: key, to: to, reason: f.r }, function () {
        delete S.form[key];
        S.msg = { kind: 'done', text: st.label + ': sent for approval.' };
      });
    } else if (a === 'decide') {
      var ok = b.getAttribute('data-ok') === '1', id = b.getAttribute('data-id');
      act('decide:' + id, '/api/settings/decide', { id: id, approve: ok }, function (r) {
        S.msg = { kind: 'done', text: 'Change ' + r.status + '.' + (r.status === 'approved' ? ' It takes effect on the next recompute.' : '') };
      });
    } else if (a === 'flip') {
      var sw = setting(key);
      if (!window.confirm(sw.label + ': change to ' + val(sw, !sw.value) + '? It is recorded under your name and takes effect on the next recompute.')) return true;
      act('flip:' + key, '/api/settings/change', { setting: key, to: !sw.value }, function () {
        S.msg = { kind: 'done', text: sw.label + ': changed. It takes effect on the next recompute.' };
      });
    } else return false;
    return true;
  }
  function change(e) {
    var r = e.target;
    if (r.name === 'su-cp') {
      S.form.ctx.product = r.value;
      if (!presets(r.value).some(function (x) { return x.id === S.form.ctx.preset; })) S.form.ctx.preset = CX.default_preset;
      S.ctxMsg = null; redraw();
    } else if (r.name === 'su-cw') { S.form.ctx.preset = r.value; S.ctxMsg = null; redraw(); }
  }
  function input(e) {
    var r = e.target, key = r.getAttribute('data-f');
    if (key && S.form[key]) S.form[key][r.getAttribute('data-k')] = r.value;
  }

  S.ctx = window.AnalysisContext.read();
  window.PageShell.start({
    id: 'settings',
    sections: function () { return TABS.map(function (t) { return { id: t.id, t: t.t, current: t.id === S.tab }; }); },
    select: select,
    render: render,
    notes: function () { return window.__SETTINGS_NOTES__(F); },
    click: click,
    change: change,
    input: input,
    toggled: function (id, open) { S.open[id] = open; }
  });
  load(false);
})();
