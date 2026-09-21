/* Settings: what the analysis runs on. Every signed-in person sees this page; what each one sees
 * on it is decided by Session (session.js), never by a role name here.
 *
 *   everyone        readiness, rule set, policy and risk appetite, run and data quality
 *   data.view       applicant data facts and the field mapping, read-only
 *   recompute.run   the Recompute button (unless the licence stage pauses it)
 *   audit.view      the audit log
 *   admin.view      links to where each item is managed, on admin.html
 *
 * Licence, data connections, uploads and platform items are on admin.html. The licence is not
 * shown here to anyone: a person who is not an administrator only ever meets it as a paused
 * action with a plain message.
 *
 * Every figure and sentence is read from window.__SETTINGS__ (ui/settings_export.py). The page
 * speaks in product voice; why a thing is built the way it is belongs in settings_notes.js.
 * Nothing leaves the browser, nothing is stored, and no simulated action changes a figure.
 */
(function () {
  'use strict';

  var K = window.SettingsKit;
  var esc = K.esc, n0 = K.n0, pct = K.pct, pv = K.pv, sim = K.sim, N = K.N, plural = K.plural;
  var tile = K.tile, section = K.section, accordion = K.accordion, caveat = K.caveat, table = K.table, kv = K.kv;
  var F = window.__SETTINGS__, SIM = F.simulated;
  var can = window.Session.can, paused = window.Session.paused;

  var S = { recompute: null, open: {} };
  var timer = 0;

  /** Where an administrator manages an item; nothing for anyone else. */
  function manage(anchor, text) {
    return can('admin.view') ? ' <a class="su-manage" href="admin.html#sec-' + anchor + '">' + esc(text) + '</a>' : '';
  }

  /* ================================================================ readiness */
  function readyHtml() {
    var R = F.run, D = F.dataset;
    return '<div class="tiles c3 su-ready" id="su-ready"' + N('ready') + '>' +
      tile('Rule set ' + pv('OBSERVED'), n0(R.rules_replayed), 'rules replayed · ' + n0(F.rulepack.totals.rules) +
           ' in ' + n0(F.rulepack.totals.files) + ' workbooks', 'on-obs', N('t_rules')) +
      tile('Applicant data ' + pv('OBSERVED'), D.available ? n0(D.rows) : '—',
           D.available ? esc(D.date_from) + ' to ' + esc(D.date_to) : 'No dataset loaded', 'on-obs', N('t_data')) +
      tile('Field coverage ' + pv('OBSERVED'), n0(F.fields.required_mapped) + ' of ' + n0(F.fields.required),
           'required fields supplied', 'on-obs', N('t_fields')) +
      '</div>';
  }

  /* ================================================================ rule set */
  function secRules() {
    var RP = F.rulepack, T = RP.totals, R = F.run;
    var rows = [];
    RP.files.forEach(function (f) {
      f.tables.forEach(function (t, i) {
        rows.push('<tr><td class="su-file-cell">' +
          (i === 0 ? '<b title="SHA-256 ' + esc(f.sha12) + '…">' + esc(f.file) + '</b><span>updated ' + esc(f.modified) + '</span>' : '') + '</td>' +
          '<td><span class="rid">' + esc(t.table) + '</span></td><td>' + esc(t.role) + '</td>' +
          '<td>' + (t.stage ? esc(t.stage.replace(/_/g, ' ')) : '<span class="nodata">—</span>') + '</td>' +
          '<td class="num">' + n0(t.rules) + '</td><td class="num">' + n0(t.in_scope) + '</td><td class="num">' + n0(t.inactive) + '</td></tr>');
      });
    });
    rows.push('<tr class="is-total"><td>' + n0(T.files) + ' workbooks</td><td>' + n0(T.tables) + ' tables</td><td></td><td></td>' +
      '<td class="num">' + n0(T.rules) + '</td><td class="num">' + n0(T.in_scope) + '</td><td class="num">' + n0(T.inactive) + '</td></tr>');

    var nu = R.unevaluable.length;
    var uneval = nu
      ? '<div class="su-gap">' + caveat('warn', 'NOT EVALUATED', '<strong>' + n0(nu) + ' ' + plural(nu, 'rule reads', 'rules read') +
          ' data the applicant table does not carry:</strong> ' +
          R.unevaluable.map(function (id) { return '<span class="rid">' + esc(id) + '</span>'; }).join(', ') + '.' +
          (can('data.view') ? ' See <a href="#sec-mapping" data-jump="mapping">field mapping</a>.' : ''), N('rp_uneval')) + '</div>'
      : '';

    return section('rules', 'Rule set', pv('OBSERVED'),
      '<p class="su-lead">The decision tables in the rule pack. Tables that apply to ' + esc(RP.product) + ' are replayed.' +
      manage('rules', 'Load a rule workbook') + '</p>' +
      table('<th>Workbook</th><th' + N('rp_table') + '>Table</th><th' + N('rp_role') + '>Role</th><th>Stage</th>' +
            '<th class="num">Rules</th><th class="num"' + N('rp_scope') + '>In scope</th><th class="num">Inactive</th>', rows) +
      uneval +
      '<div class="su-sub">Scope</div>' +
      kv([{ key: 'Product', value: RP.product },
          { key: 'Include inactive rules', value: RP.options.include_inactive_rules ? 'Yes' : 'No' }]), N('rp_head'));
  }

  /* ================================================================ policy */
  function secPolicy() {
    var P = F.policy;
    var levers = table('<th>Change</th><th class="num">From</th><th class="num">To</th>',
      P.levers.map(function (l) {
        return '<tr><td title="' + esc(l.field) + '">' + esc(l.label) + '</td><td class="num">' + esc(l.from) + '</td><td class="num">' + esc(l.to) + '</td></tr>';
      }));
    return section('policy', 'Policy and risk appetite', pv('OBSERVED'),
      '<p class="su-lead">Values set by the risk committee. They change through configuration and take effect on the next recompute.</p>' +
      '<div class="su-policy"><div><div class="su-sub">Risk appetite</div>' + K.pvRows(P.appetite) + '</div>' +
      '<div><div class="su-sub">Risk model</div>' + K.pvRows(P.model) + '</div>' +
      '<div><div class="su-sub">Portfolio and product</div>' + K.pvRows(P.portfolio.concat(P.product)) + '</div></div>' +
      '<div class="su-policy su-gap">' +
      '<div><div class="su-sub"' + N('po_assume') + '>Replay assumptions</div>' + K.pvRows(P.assumptions) + '</div>' +
      '<div><div class="su-sub"' + N('po_hard') + '>Never relaxed by the optimiser</div>' +
        '<p class="su-help">Regulatory and staff checks stay in force in every strategy:</p>' +
        '<ul class="su-list">' + P.hard_reject.map(function (h) { return '<li title="' + esc(h.field) + '">' + esc(h.label) + '</li>'; }).join('') + '</ul>' +
      '<div class="su-sub"' + N('po_levers') + '>Thresholds the optimiser may move</div>' + levers + '</div></div>', N('po_head'));
  }

  /* ================================================================ run and data quality */
  function recomputeBlock() {
    if (!can('recompute.run')) return '';
    var stopped = paused('recompute.run');
    var busy = S.recompute && !S.recompute.done;
    return '<div class="su-sub">Recompute ' + sim() + '</div><div class="su-row">' +
      '<button type="button" class="btn sm" id="su-recompute" data-act="recompute"' + N('rn_recompute') +
      (stopped || busy ? ' disabled' : '') + '>Recompute</button>' +
      '<span class="su-help">' + esc(stopped ? SIM.licence.refresh.paused_message : SIM.recompute.note) + '</span></div>' +
      '<div id="su-recout" aria-live="polite">' + recomputeHtml() + '</div>';
  }
  function recomputeHtml() {
    var Rc = S.recompute;
    if (!Rc) return '';
    return '<ul class="su-steps">' + Rc.steps.map(function (s) {
      return '<li><span class="mk">✓</span><span class="lb">' + esc(s) + '</span><span class="dt"></span><span class="ms"></span></li>';
    }).join('') + '</ul>' + (Rc.done ? '<div class="su-verdict">' + esc(SIM.recompute.done) + '</div>' : '');
  }
  function runRecompute() {
    if (paused('recompute.run')) return;
    clearTimeout(timer);
    S.recompute = { steps: [], done: false };
    var i = 0, all = SIM.recompute.steps;
    (function next() {
      if (i >= all.length) S.recompute.done = true; else S.recompute.steps.push(all[i]);
      i += 1;
      var out = document.getElementById('su-recout');
      if (out) out.innerHTML = recomputeHtml();
      var b = document.getElementById('su-recompute');
      if (b) b.disabled = !S.recompute.done;
      if (!S.recompute.done) timer = setTimeout(next, 380);
    })();
  }

  function secRun() {
    var R = F.run, D = F.dataset;
    if (!R.available) return section('run', 'Run and data quality', '', caveat('warn', 'NO DATA', 'No dataset, so nothing was replayed.'), N('rn_head'));
    var nulls = (D.nulls || []).map(function (n) {
      return '<tr><td><span class="rid">' + esc(n.column) + '</span></td><td class="num">' + pct(n.share, 1) + '</td>' +
        '<td style="width:140px"><span class="su-nullbar" style="width:' + Math.max(1, Math.round(n.share * 100)) + '%"></span></td></tr>';
    });
    return section('run', 'Run and data quality', pv('OBSERVED'),
      '<div class="tiles c4">' +
        tile('Applicants replayed', n0(R.applicants), 'in the last run', 'on-obs') +
        tile('Rules replayed', n0(R.rules_replayed), n0(R.rules_in_scope) + ' in scope', 'on-obs') +
        tile('Replay time', R.replay_seconds.toFixed(1) + 's', 'last run') +
        tile('Rules that catch nobody', n0(R.never_fire_count), 'of ' + n0(R.rules_replayed) + ' replayed · listed on ' +
             '<a href="client.html#drivers">Decline drivers</a>', '', N('rn_never')) +
      '</div>' +
      '<div class="su-gap"><div class="su-sub"' + N('rn_nulls') + '>Fields with missing values</div>' +
        table('<th>Field</th><th class="num">Missing</th><th></th>', nulls) + '</div>' +
      recomputeBlock() +
      '<p class="su-help su-gap">Run at ' + esc(R.generated) + '.</p>', N('rn_head'));
  }

  /* ================================================================ applicant data (data.view) */
  function secData() {
    var D = F.dataset;
    if (!D.available) return section('data', 'Applicant data', '', caveat('warn', 'NO DATA', 'No applicant dataset is loaded.'), N('ds_head'));
    var nulls = D.nulls.filter(function (n) { return n.column === 'simah_score'; })[0];
    return section('data', 'Applicant data', pv('OBSERVED'),
      '<p class="su-lead">The applicant table the analysis runs on.' + manage('data', 'Manage the data source') + '</p>' +
      '<div class="tiles c4"' + N('ds_demo') + '>' +
        tile('Applicants', n0(D.rows), esc(D.label), 'on-obs') +
        tile('Applications between', esc(D.date_from), 'to ' + esc(D.date_to)) +
        tile('Columns', n0(D.columns), 'in the applicant table') +
        tile('No bureau score', nulls ? pct(nulls.share, 1) : '—', 'applicants with no SIMAH score') +
      '</div>' +
      (D.schema_problems.length ? caveat('warn', 'SCHEMA', esc(D.schema_problems.join('; '))) : caveat('obs', 'SCHEMA', 'Passes all schema checks.')) +
      K.previewRows(F), N('ds_head'));
  }

  /* ================================================================ field mapping (data.view) */
  function secMapping() {
    var C = F.fields;
    // A "Not requested" column exists only in the generated data; a bank is never asked for it.
    var rows = C.columns.filter(function (r) { return r.need !== 'Not requested'; }).map(function (r) {
      return '<tr><td><span class="rid">' + esc(r.column) + '</span></td><td class="su-mono su-muted">' + esc(r.dtype) + '</td>' +
        '<td><span class="su-tag need-' + esc(r.need.split(' ')[0]) + '">' + esc(r.need) + '</span></td>' +
        '<td class="num">' + (r.rules ? n0(r.rules) : '<span class="nodata">—</span>') + '</td>' +
        '<td><span class="su-mono">' + esc(r.column) + '</span></td>' +
        '<td class="num">' + (r.null_share ? pct(r.null_share, 1) : '<span class="nodata">—</span>') + '</td></tr>';
    });
    var unsup = C.unsupplied.length
      ? '<div class="su-gap">' + caveat('warn', 'NOT SUPPLIED', '<strong>Data the applicant table does not carry.</strong> ' +
          C.unsupplied.map(function (u) {
            return n0(u.rules) + ' ' + plural(u.rules, 'rule reads', 'rules read') +
              ' a <abbr class="su-expr" title="' + esc(u.field) + '">derived value</abbr>';
          }).join('; ') + '. Not evaluated until supplied.', N('mp_unsupplied')) + '</div>'
      : '';
    return section('mapping', 'Field mapping', pv('OBSERVED'),
      '<p class="su-lead">The fields the rules read from each applicant record, and how many rules read each.' +
      manage('mapping', 'Edit the mapping') + '</p>' +
      caveat('obs', 'MAPPED', '<strong>' + n0(C.required_mapped) + ' of ' + n0(C.required) + ' required fields supplied.</strong>') +
      '<div class="su-scroll su-gap"><div class="tablewrap"><table class="t su-compact"><thead><tr><th>Field</th><th>Type</th>' +
      '<th' + N('mp_need') + '>Need</th><th class="num">Rules</th><th>Source column</th><th class="num">Missing</th></tr></thead><tbody>' +
      rows.join('') + '</tbody></table></div></div>' + unsup, N('mp_head'));
  }

  /* ================================================================ audit log (audit.view) */
  function secAudit() {
    return accordion('audit', 'Audit log', sim(),
      table('<th>When</th><th>Who</th><th>What</th>', SIM.audit.map(function (a) {
        return '<tr><td class="su-mono su-muted">' + esc(a.when) + '</td><td>' + esc(a.who) + '</td><td>' + esc(a.what) + '</td></tr>';
      })), N('au_head'), S.open.audit);
  }

  /* ================================================================ page */
  var SECTIONS = [
    { id: 'rules', t: 'Rule set', build: secRules },
    { id: 'policy', t: 'Policy and risk appetite', build: secPolicy },
    { id: 'run', t: 'Run and data quality', build: secRun },
    { id: 'data', t: 'Applicant data', build: secData, need: 'data.view' },
    { id: 'mapping', t: 'Field mapping', build: secMapping, need: 'data.view' },
    { id: 'audit', t: 'Audit log', build: secAudit, need: 'audit.view' }
  ];
  function visible() { return SECTIONS.filter(function (s) { return !s.need || can(s.need); }); }

  function render() {
    return '<div class="pagehead"><h2' + N('pg_head') + '>Settings</h2>' +
      '<p>The rules, data and policy values the analysis runs on.</p></div>' +
      readyHtml() + visible().map(function (s) { return s.build(); }).join('');
  }

  window.PageShell.start({
    id: 'settings',
    sections: visible,
    render: render,
    notes: function () { return window.__SETTINGS_NOTES__(F); },
    click: function (e) {
      if (!e.target.closest('[data-act="recompute"]')) return false;
      runRecompute();
      return true;
    },
    toggled: function (id, open) { S.open[id] = open; }
  });
})();
