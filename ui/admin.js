/* Administration: how the installed product is licensed, fed, secured and maintained.
 *
 * Only for someone Session allows 'admin.view'. Anyone else who opens admin.html gets the refusal
 * the product itself would give. In the deployed product the server refuses every action here
 * whatever this page draws; hiding it is presentation, not security.
 *
 * Most of this page is drawn from the fixture's `simulated` key, so it carries one PREVIEW tag at the
 * top rather than one per section. The two exceptions are real and say so with OBSERVED: the field
 * mapping's state (what the data in use supplies) and the bad definition (config `outcome`, with the
 * loans it can judge). Their example and planned parts are labelled in place. Nothing leaves the browser, a chosen file is never read
 * (only its name is shown), the password field is never read, and nothing here changes a figure on
 * another screen.
 *
 * The licence shows its current state only. The stages a licence passes through are contract terms
 * that differ by client, so they live in the spec notes and the licence file, never on a screen.
 */
(function () {
  'use strict';

  var K = window.SettingsKit;
  var esc = K.esc, n0 = K.n0, sim = K.sim, pv = K.pv, N = K.N;
  var section = K.section, caveat = K.caveat, table = K.table, kv = K.kv;
  var F = window.__SETTINGS__, SIM = F.simulated, L = SIM.licence;
  var can = window.Session.can, paused = window.Session.paused;

  var S = {
    refreshing: false, licMsg: '',
    src: 'current', auth: 'vault', form: { x: {}, a: {} }, test: null, previewed: false,
    up: { data: null, rules: null }
  };
  var timers = { test: 0 };

  /** A control a licence stage can pause: disabled, with the reason beside it. */
  function pausedNote(action) {
    return paused(action) ? '<p class="su-help su-gap" role="status">' + esc(L.refresh.paused_message) + '</p>' : '';
  }
  function dis(action) { return paused(action) ? ' disabled' : ''; }

  /* ================================================================ licence */
  function refreshIcon() {
    return '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9"/>' +
      '<path d="M13.5 2.5v3h-3"/></svg>';
  }
  function secLicence() {
    var sn = window.Session.licence();
    if (!sn) return '';
    return section('licence', 'Licence', '',
      '<div class="su-lic"><div>' +
        '<div class="su-licstate"' + N('lic_status') + '>Status · ' + esc(sn.status_label) + '</div>' +
        '<div class="su-lichead">' + esc(sn.headline) + '</div>' +
        '<p class="su-licmeta">' + esc(sn.remaining) + ' · licence period ' + esc(sn.term) + '</p>' +
        (sn.status !== 'active' ? '<div class="su-gap">' + caveat('warn', sn.status_label.toUpperCase(), esc(sn.does)) + '</div>' : '') +
        '<div class="su-licact">' +
          '<button type="button" class="iconbtn su-refresh' + (S.refreshing ? ' is-busy' : '') + '" id="su-refresh" data-act="refresh"' +
            ' aria-label="Check for a renewed licence" title="Check for a renewed licence"' + (S.refreshing ? ' disabled' : '') + '>' +
            refreshIcon() + '</button>' +
          '<span' + N('lic_refresh') + ' class="su-faint su-mono" style="font-size:11px">Check for a renewed licence</span>' +
          '<div class="spacer"></div>' +
          '<button type="button" class="btn ghost sm" data-act="pick" data-for="lic"' + N('lic_apply') + '>Apply licence file</button>' +
          '<input type="file" id="su-file-lic" data-file="lic" accept=".lic,.json,.txt" hidden>' +
        '</div>' +
        '<div class="su-licmsg" role="status" aria-live="polite">' + esc(S.licMsg) + '</div>' +
        '<div class="su-sub"' + N('lic_rem') + '>Renewal reminders</div>' +
        kv([{ key: 'Sent to', value: L.reminders.contacts.join(', ') },
            { key: 'Days before expiry', value: L.reminders.notice_days.join(' · ') }]) +
      '</div><div>' +
        '<div class="su-sub"' + N('lic_ent') + '>Entitlements</div>' +
        kv(L.entitlements.concat([{ key: 'Licence ID', value: L.licence_id }])) +
        '<div class="su-sub"' + N('lic_sig') + '>Signature</div>' +
        kv([{ key: 'Issued by', value: L.issued_by }, { key: 'Algorithm', value: L.signature.algorithm },
            { key: 'Verified', value: L.signature.verified ? 'Yes, offline' : 'No' },
            { key: 'Fingerprint', value: L.signature.fingerprint }], true) +
      '</div></div>', N('lic_head'));
  }
  function doRefresh() {
    if (S.refreshing) return;
    S.refreshing = true; S.licMsg = '';
    window.PageShell.update('licence', secLicence());
    window.Session.refreshLicence(function (r) {
      S.refreshing = false;
      S.licMsg = r.found ? L.refresh.found : L.refresh.none;
      // A renewal redraws the page through Session; otherwise only this section changes.
      window.PageShell.update('licence', secLicence());
      var b = document.getElementById('su-refresh');
      if (b) b.focus();
    });
  }

  /* ================================================================ data source */
  var SOURCES = [{ id: 'current', label: 'Current dataset' }, { id: 'upload', label: 'Upload a file' },
                 { id: 'oracle', label: 'Oracle' }, { id: 'postgres', label: 'PostgreSQL' }, { id: 'mysql', label: 'MySQL' }];

  function connector(id) { return SIM.connectors.types.filter(function (t) { return t.id === id; })[0]; }
  function sv(scope, key, dflt) {
    var o = S.form[scope] || {};
    return o[key] === undefined ? (dflt === undefined ? '' : dflt) : o[key];
  }
  function fieldHtml(scope, f) {
    var id = 'su-' + scope + '-' + f.key, val = sv(scope, f.key, f.default), input;
    if (f.type === 'select') {
      input = '<select class="su-input" id="' + id + '" data-s="' + scope + '" data-f="' + f.key + '">' +
        f.choices.map(function (c) { return '<option' + ((val || f.choices[0]) === c ? ' selected' : '') + '>' + esc(c) + '</option>'; }).join('') + '</select>';
    } else {
      input = '<input class="su-input" id="' + id + '" data-s="' + scope + '" data-f="' + f.key + '" type="text"' +
        (f.type === 'number' ? ' inputmode="numeric"' : '') + ' value="' + esc(val) + '" placeholder="' + esc(f.placeholder || '') + '"' +
        ' autocomplete="off" spellcheck="false">';
    }
    // Only a free-text field with no default and no requirement is really optional.
    var optional = !f.required && f.type === 'text' && !f.default;
    return '<div class="su-field"><label for="' + id + '">' + esc(f.label) + (optional ? ' <i>optional</i>' : '') + '</label>' + input + '</div>';
  }
  function simpleField(scope, key, label, opt) {
    opt = opt || {};
    var id = 'su-' + scope + '-' + key, val = sv(scope, key, opt.dflt);
    var input = opt.area
      ? '<textarea class="su-input" id="' + id + '" data-s="' + scope + '" data-f="' + key + '" placeholder="' + esc(opt.ph || '') + '" spellcheck="false">' + esc(val) + '</textarea>'
      : '<input class="su-input" id="' + id + '" data-s="' + scope + '" data-f="' + key + '" value="' + esc(val) + '" placeholder="' + esc(opt.ph || '') + '" autocomplete="off" spellcheck="false">';
    return '<div class="su-field' + (opt.wide ? ' wide' : '') + '"><label for="' + id + '">' + esc(label) + (opt.optional ? ' <i>optional</i>' : '') + '</label>' + input + '</div>';
  }
  function selectField(scope, key, label, choices) {
    var id = 'su-' + scope + '-' + key, val = sv(scope, key, choices[0]);
    return '<div class="su-field"><label for="' + id + '">' + esc(label) + '</label><select class="su-input" id="' + id + '" data-s="' + scope + '" data-f="' + key + '">' +
      choices.map(function (c) { return '<option' + (val === c ? ' selected' : '') + '>' + esc(c) + '</option>'; }).join('') + '</select></div>';
  }

  function dbForm() {
    var C = SIM.connectors, t = connector(S.src);
    var conn = '<div class="su-sub"' + N('ds_form') + '>Connection · ' + esc(t.label) + '</div>' +
      '<div class="su-grid">' + t.fields.map(function (f) { return fieldHtml(S.src, f); }).join('') + '</div>';
    var auth = '<div class="su-sub"' + N('ds_auth') + '>Authentication</div><div class="su-choice" role="radiogroup" aria-label="Authentication">' +
      C.auth.map(function (a) {
        return '<label class="su-radio"><input type="radio" name="su-auth" data-auth="' + a.id + '"' + (S.auth === a.id ? ' checked' : '') + '>' +
          '<div><b>' + esc(a.label) + '</b><span>' + esc(a.help) + '</span></div></label>';
      }).join('') + '</div><div class="su-grid su-gap">' +
      (S.auth === 'vault'
        ? simpleField('a', 'vault', 'Secret reference', { ph: 'vault://los/readonly', wide: true })
        : simpleField('a', 'user', 'Username', { ph: 'svc_csopt_ro' }) +
          '<div class="su-field"><label for="su-pw">Password</label>' +
          '<input class="su-input" id="su-pw" type="password" autocomplete="new-password" placeholder="••••••••">' +
          '<span class="su-help">Not stored in this environment.</span></div>') +
      '</div><p class="su-help su-gap">' + esc(C.extraction.read_only_note) + '</p>';
    var isSql = sv('x', 'obj', C.extraction.objects[0]) === C.extraction.objects[1];
    var extract = '<div class="su-sub"' + N('ds_extract') + '>What to read</div><div class="su-grid">' +
      selectField('x', 'obj', 'Read from', C.extraction.objects) +
      (isSql ? simpleField('x', 'sql', 'SQL query', { area: true, wide: true, ph: 'SELECT ... FROM ...' })
             : simpleField('x', 'name', 'Table or view', { ph: 'LOS.APPLICATIONS_V' })) +
      simpleField('x', 'datecol', 'Application date column', { ph: 'APP_DT' }) +
      simpleField('x', 'product', 'Product filter', { dflt: F.rulepack.product }) +
      selectField('x', 'window', 'Window', ['Last 12 months', 'Last 24 months', 'All history']) +
      selectField('x', 'refresh', 'Refresh', C.extraction.refresh) +
      simpleField('x', 'limit', 'Row limit', { optional: true, ph: 'No limit' }) + '</div>';
    var actions = '<div class="su-row su-gap"><button type="button" class="btn sm" id="su-test" data-act="test"' + N('ds_test') + dis('data.load') + '>Test connection</button>' +
      '<button type="button" class="btn ghost sm" data-act="example">Use example values</button>' +
      '<button type="button" class="btn ghost sm" data-act="preview"' + (S.test && S.test.done ? '' : ' disabled') + '>Preview rows</button></div>' +
      pausedNote('data.load') +
      '<div id="su-testout" aria-live="polite">' + testHtml() + '</div>' +
      (S.previewed && S.test && S.test.done ? K.previewRows(F) : '');
    return conn + auth + extract + actions;
  }
  function testHtml() {
    var T = S.test;
    if (!T) return '';
    var lis = T.steps.map(function (s) {
      return '<li><span class="mk">✓</span><span class="lb">' + esc(s.label) + '</span><span class="dt">' + esc(s.detail) + '</span><span class="ms">' + esc(s.ms) + ' ms</span></li>';
    });
    if (T.fail) lis.push('<li class="is-fail"><span class="mk">✗</span><span class="lb">' + esc(T.fail.label) + '</span><span class="dt">' + esc(T.fail.detail) + '</span><span class="ms"></span></li>');
    return '<ul class="su-steps">' + lis.join('') + '</ul>' +
      (T.done ? '<div class="su-verdict">' + esc(SIM.connection_test.done) + '</div>' : '') +
      (T.fail ? '<div class="su-verdict">Correct this and test again.</div>' : '');
  }
  function paintTest() {
    var el = document.getElementById('su-testout');
    if (el) el.innerHTML = testHtml();
    var b = document.querySelector('[data-act="preview"]');
    if (b) b.disabled = !(S.test && S.test.done);
  }
  function runTest() {
    if (paused('data.load')) return;
    var CT = SIM.connection_test, t = connector(S.src), vals = S.form[S.src] || {};
    clearTimeout(timers.test);
    S.previewed = false;
    var fail = null;
    var host = (vals.host || '').trim();
    var portRaw = vals.port === undefined ? String(t.default_port) : String(vals.port).trim();
    if (!host) fail = CT.failures.host_missing;
    else if (!/^\d+$/.test(portRaw)) fail = CT.failures.port_invalid;
    else {
      var missing = t.fields.some(function (f) { return f.required && !(vals[f.key] || '').trim(); });
      var isSql = sv('x', 'obj') === SIM.connectors.extraction.objects[1];
      if (S.auth === 'vault' && !(S.form.a.vault || '').trim()) missing = true;
      if (S.auth === 'password' && !(S.form.a.user || '').trim()) missing = true;
      if (!(isSql ? (S.form.x.sql || '') : (S.form.x.name || '')).trim()) missing = true;
      if (missing) fail = CT.failures.required_missing;
    }
    if (fail) { S.test = { steps: [], fail: fail, done: false }; paintTest(); return; }
    S.test = { steps: [], fail: null, done: false };
    var i = 0;
    (function next() {
      if (i >= CT.steps.length) { S.test.done = true; paintTest(); return; }
      S.test.steps.push(CT.steps[i]); i += 1;
      paintTest();
      timers.test = setTimeout(next, 320);
    })();
  }
  function exampleValues() {
    var t = connector(S.src);
    S.form[S.src] = S.form[S.src] || {};
    t.fields.forEach(function (f) { if (f.type === 'text' && f.placeholder) S.form[S.src][f.key] = f.placeholder; });
    S.form.a.vault = 'vault://los/readonly';
    S.form.a.user = 'svc_csopt_ro';
    S.form.x.name = 'LOS.APPLICATIONS_V';
    S.form.x.datecol = 'APP_DT';
  }
  function currentBlock() {
    var D = F.dataset;
    return kv([{ key: 'Source', value: D.label }, { key: 'Applicants', value: n0(D.rows) },
               { key: 'Applications between', value: D.date_from + ' and ' + D.date_to }]) +
      '<p class="su-help su-gap">Facts and example rows are on <a href="settings.html#sec-data">Settings</a>.</p>';
  }
  function uploadBlock() {
    return '<div class="su-drop"><p><b>Drop an applicant file here</b>, or choose one. Accepted: ' + esc(SIM.upload.accept_data) + '.</p>' +
      '<button type="button" class="btn ghost sm" data-act="pick" data-for="data"' + dis('data.load') + '>Choose file</button>' +
      '<input type="file" id="su-file-data" data-file="data" accept="' + esc(SIM.upload.accept_data) + '" hidden></div>' +
      pausedNote('data.load') +
      (S.up.data ? '<p class="su-help su-gap" role="status"><span class="su-file">' + esc(S.up.data) + '</span> · ' + esc(SIM.upload.data) + '</p>' : '');
  }
  function secData() {
    var picker = '<div class="su-row" style="margin-bottom:14px"><div class="seg"' + N('ds_src') + ' role="group" aria-label="Where the applicant data comes from">' +
      SOURCES.map(function (s) {
        return '<button type="button" data-act="src" data-v="' + s.id + '" aria-pressed="' + (S.src === s.id) + '">' + esc(s.label) + '</button>';
      }).join('') + '</div></div>';
    var body = S.src === 'current' ? currentBlock() : S.src === 'upload' ? uploadBlock() : dbForm();
    return section('data', 'Data source', '',
      '<p class="su-lead">Where the applications come from: a file, or a read-only connection to the loan origination database.</p>' +
      picker + body, N('ds_admin'));
  }

  /* ================================================================ field mapping editor */
  function secMapping() {
    var ex = SIM.example_layout, C = F.fields;
    var srcBy = {};
    ex.mapping.forEach(function (m) { srcBy[m.column] = m.source; });
    var rows = C.columns.filter(function (r) { return r.need !== 'Not requested'; }).map(function (r) {
      var src = srcBy[r.column] ? '<span class="su-mono">' + esc(srcBy[r.column]) + '</span>' : '<span class="su-unmapped">UNMAPPED</span>';
      return '<tr><td><span class="rid">' + esc(r.column) + '</span></td><td class="su-mono su-muted">' + esc(r.dtype) + '</td>' +
        '<td><span class="su-tag need-' + esc(r.need.split(' ')[0]) + '">' + esc(r.need) + '</span></td>' +
        '<td class="num">' + (r.rules ? n0(r.rules) : '<span class="nodata">—</span>') + '</td><td>' + src + '</td></tr>';
    });
    var complete = C.required_mapped === C.required;
    return section('mapping', 'Field mapping', pv('OBSERVED'),
      '<p class="su-lead">Which source column supplies each field the rules read.</p>' +
      caveat(complete ? 'obs' : 'warn', 'IN USE',
        '<strong>' + n0(C.required_mapped) + ' of ' + n0(C.required) + ' required fields supplied by the data in use.</strong> ' +
        (complete ? 'Every replay runs on it.' : 'Rules that read a missing field are not evaluated.'), N('mp_state')) +
      '<div class="su-sub su-gap"' + N('mp_example') + '>Mapping a new source · example</div>' +
      caveat(ex.summary.unmapped_required.length ? 'warn' : '', 'EXAMPLE',
        '<strong>' + esc(ex.source_object) + ': ' + n0(ex.summary.required_mapped) + ' of ' + n0(ex.summary.required) +
        ' required fields mapped.</strong> This source could not be analysed until the rest are mapped or supplied. ' + esc(ex.note)) +
      '<div class="su-scroll su-gap"><div class="tablewrap"><table class="t su-compact"><thead><tr><th>Field</th><th>Type</th>' +
      '<th>Need</th><th class="num">Rules</th><th>Example source column</th></tr></thead><tbody>' + rows.join('') + '</tbody></table></div></div>',
      N('mp_admin'));
  }

  /* ================================================================ rule workbooks */
  /** The workbooks and decision tables in use. Business users see one line of this on Settings. */
  function inventory() {
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
    return '<div class="su-sub">In use · rule pack ' + esc(RP.version) + ' ' + pv('OBSERVED') + '</div>' +
      table('<th>Workbook</th><th' + N('rp_table') + '>Table</th><th' + N('rp_role') + '>Role</th><th>Stage</th>' +
            '<th class="num">Rules</th><th class="num"' + N('rp_scope') + '>In scope for ' + esc(RP.product) + '</th><th class="num">Inactive</th>', rows) +
      '<p class="su-help su-gap">' + n0(R.rules_replayed) + ' rules replayed for ' + esc(RP.product) +
      '. Inactive rules are ' + (RP.options.include_inactive_rules ? 'replayed' : 'left off') + ', a replay assumption the risk approver sets on ' +
      '<a href="settings.html#assumptions">Settings</a>.</p>';
  }
  function secRules() {
    return section('rules', 'Rule workbooks', '',
      '<p class="su-lead">The rule pack the analysis replays, and where a new or replacement workbook is loaded.</p>' +
      inventory() +
      '<div class="su-sub su-gap">Load a workbook</div>' +
      '<div class="su-drop"' + N('rp_upload') + '><p><b>Drop a workbook here</b>, or choose one. Accepted: ' + esc(SIM.upload.accept_rules) + '.</p>' +
      '<button type="button" class="btn ghost sm" data-act="pick" data-for="rules"' + dis('rules.load') + '>Choose file</button>' +
      '<input type="file" id="su-file-rules" data-file="rules" accept="' + esc(SIM.upload.accept_rules) + '" hidden></div>' +
      pausedNote('rules.load') +
      (S.up.rules ? '<p class="su-help su-gap" role="status"><span class="su-file">' + esc(S.up.rules) + '</span> · ' + esc(SIM.upload.rules) + '</p>' : ''), N('rp_head'));
  }

  /* ================================================================ audit log */
  function secAudit() {
    return section('audit', 'Audit log', '',
      '<p class="su-lead">Who did what, across the product. Changes to the risk appetite and the replay assumptions, with ' +
      'who proposed and approved each, are recorded for real on <a href="settings.html#appetite">Settings</a>.</p>' +
      table('<th>When</th><th>Who</th><th>What</th>', SIM.audit.map(function (a) {
        return '<tr><td class="su-mono su-muted">' + esc(a.when) + '</td><td>' + esc(a.who) + '</td><td>' + esc(a.what) + '</td></tr>';
      })), N('au_head'));
  }

  /* ================================================================ the rest */
  function secOutcomes() {
    var O = F.outcome, P = SIM.outcomes;
    var judged = O.products.length ? table('<th>Product</th><th class="num">Booked</th><th class="num">Old enough to judge</th>' +
      '<th class="num">Went bad</th><th class="num">Bad rate</th>', O.products.map(function (r) {
        return '<tr><td>' + esc(r.product) + '</td><td class="num">' + n0(r.booked) + '</td><td class="num">' + n0(r.judged) + '</td>' +
          '<td class="num">' + n0(r.bad) + '</td><td class="num">' + (r.bad_rate === null ? '<span class="nodata">—</span>' :
          (100 * r.bad_rate).toFixed(1) + '%') + '</td></tr>';
      })) : '';
    return section('outcomes', 'Outcomes and performance', pv('OBSERVED'),
      '<p class="su-lead">How a loan is classed as bad. Every bad rate in the product is read against this definition.</p>' +
      '<div class="cols2"><div><div class="su-sub">What counts as bad</div>' + kv(O.definition) + '</div>' +
      '<div><div class="su-sub">Read from</div>' + kv(O.sources, true) + '<p class="su-help su-gap">' + esc(O.rule) + '</p></div></div>' +
      (judged ? '<div class="su-sub su-gap"' + N('oc_judged') + '>Loans the definition can judge</div>' + judged : '') +
      '<div class="su-sub su-gap"' + N('oc_planned') + '>Planned · not applied yet</div>' +
      '<p class="su-help">' + esc(P.note) + '</p>' +
      '<div class="cols2"><div>' + kv(P.exclusions) + '</div><div>' + kv(P.sources, true) + '</div></div>' +
      '<div class="su-gap">' + caveat('', 'RECONCILE', esc(P.reconciliation), N('oc_recon')) + '</div>', N('oc_head'));
  }
  function secPlatform() {
    var groups = SIM.governance.map(function (g) { return '<div><div class="su-sub">' + esc(g.group) + '</div>' + kv(g.items) + '</div>'; }).join('');
    return section('platform', 'Platform, access and security', '',
      '<div class="cols2">' + groups + '<div><div class="su-sub">Regional</div>' + kv(SIM.regional) + '</div></div>', N('gv_head'));
  }
  function secVersions() {
    return section('versions', 'Versions and updates', '', kv(SIM.versions, true) +
      '<p class="su-help su-gap">Updates arrive through the encrypted patch channel and never overwrite your configuration.</p>', N('vr_head'));
  }
  function secDiagnostics() {
    var D = SIM.diagnostics;
    return section('diagnostics', 'Diagnostics and export', '',
      '<div class="cols2"><div><div class="su-sub">Support bundle</div><p class="su-help">' + esc(D.bundle) + '</p>' +
      '<button type="button" class="btn ghost sm" data-act="noop">Create bundle</button></div>' +
      '<div><div class="su-sub">Exports</div>' + D.exports.map(function (e) {
        return '<div class="su-pv"><div><b>' + esc(e) + '</b></div><button type="button" class="btn ghost sm" data-act="noop">Export</button></div>';
      }).join('') + '<p class="su-help su-gap">' + esc(D.note) + '</p></div></div>', N('dg_head'));
  }

  /* ================================================================ page */
  var SECTIONS = [
    { id: 'licence', t: 'Licence', build: secLicence, need: 'licence.view' },
    { id: 'data', t: 'Data source', build: secData },
    { id: 'mapping', t: 'Field mapping', build: secMapping },
    { id: 'rules', t: 'Rule workbooks', build: secRules },
    { id: 'outcomes', t: 'Outcomes', build: secOutcomes },
    { id: 'audit', t: 'Audit log', build: secAudit, need: 'audit.view' },
    { id: 'platform', t: 'Platform and security', build: secPlatform },
    { id: 'versions', t: 'Versions and updates', build: secVersions },
    { id: 'diagnostics', t: 'Diagnostics and export', build: secDiagnostics }
  ];
  function visible() {
    if (!can('admin.view')) return [];
    return SECTIONS.filter(function (s) { return !s.need || can(s.need); });
  }

  function render() {
    if (!can('admin.view')) {
      var who = window.Session.who();
      return '<div class="pagehead"><h2' + N('ad_head') + '>Administration</h2></div>' +
        caveat('', 'NO ACCESS', 'Administration is available to administrators' + (who ? '. You are signed in as ' + esc(who) + '.' : '.') +
          ' <a href="settings.html">Go to Settings</a>.', N('ad_refused'));
    }
    return '<div class="pagehead"><div class="su-row"><h2' + N('ad_head') + '>Administration</h2>' + sim() + '</div>' +
      '<p>How the installed product is licensed, fed, secured and maintained. Sections marked OBSERVED are read from ' +
      'the data in use; the rest is a preview.</p></div>' +
      visible().map(function (s) { return s.build(); }).join('');
  }

  function click(e) {
    var a = e.target.closest('[data-act]');
    if (!a) return false;
    var act = a.getAttribute('data-act');
    if (act === 'refresh') doRefresh();
    else if (act === 'pick') { var fi = document.getElementById('su-file-' + a.getAttribute('data-for')); if (fi) fi.click(); }
    else if (act === 'src') {
      S.src = a.getAttribute('data-v'); S.test = null; S.previewed = false; clearTimeout(timers.test);
      window.PageShell.update('data', secData());
      var pressed = document.querySelector('[data-act="src"][data-v="' + S.src + '"]'); if (pressed) pressed.focus();
    }
    else if (act === 'test') runTest();
    else if (act === 'example') { exampleValues(); S.test = null; window.PageShell.update('data', secData()); }
    else if (act === 'preview') { S.previewed = true; window.PageShell.update('data', secData()); }
    else if (act === 'noop' && !a.parentNode.querySelector('.su-noop')) {
      var m = document.createElement('span');
      m.className = 'su-help su-noop';
      m.setAttribute('role', 'status');
      m.textContent = ' ' + K.UNAVAILABLE;
      a.after(m);
    }
    return true;
  }
  function input(e) {
    var t = e.target;
    if (t.hasAttribute('data-s') && t.hasAttribute('data-f')) {
      var sc = t.getAttribute('data-s');
      S.form[sc] = S.form[sc] || {};
      S.form[sc][t.getAttribute('data-f')] = t.value;
    }
  }
  function change(e) {
    var t = e.target;
    if (t.hasAttribute('data-s') && t.tagName === 'SELECT') {
      input(e);
      if (t.getAttribute('data-f') === 'obj') window.PageShell.update('data', secData());
    } else if (t.hasAttribute('data-auth')) {
      S.auth = t.getAttribute('data-auth'); S.test = null; window.PageShell.update('data', secData());
    } else if (t.hasAttribute('data-file') && t.files && t.files.length) {
      // Only the name is used. The file is never read.
      var kind = t.getAttribute('data-file'), name = t.files[0].name;
      if (kind === 'lic') {
        window.Session.applyLicence(name, function () { S.licMsg = L.refresh.apply + ' (' + name + ')'; window.PageShell.update('licence', secLicence()); });
      } else {
        S.up[kind] = name;
        window.PageShell.update(kind === 'rules' ? 'rules' : 'data', kind === 'rules' ? secRules() : secData());
      }
    }
  }

  window.PageShell.start({
    id: 'administration', sections: visible, render: render,
    // Shell notes (rail, tags, strip) come from settings_notes.js; the keys never overlap.
    notes: function () { return Object.assign({}, window.__SETTINGS_NOTES__(F), window.__ADMIN_NOTES__(F)); },
    click: click, input: input, change: change
  });
})();
