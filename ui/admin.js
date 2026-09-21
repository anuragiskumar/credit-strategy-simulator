/* Administration: is it healthy, is data flowing, who has access, and does anything need me?
 *
 * Only for someone Session allows 'admin.view'. Anyone else who opens admin.html gets the refusal
 * the product itself would give. In the deployed product the server refuses every action here
 * whatever this page draws; hiding it is presentation, not security.
 *
 * Six tabs, in the order an administrator works: Overview (one card per concern, only the ones that
 * need attention open) · Data (the source in use, connecting a new one, field mapping, outcomes, rule
 * workbooks) · Users & access · Audit log · System · Licence, last because it is rarely the task.
 *
 * Most of this page is drawn from the fixture's `simulated` key, so it carries one PREVIEW tag at the
 * top rather than one per section. What is real says so: the data in use and its field mapping and
 * bad definition (OBSERVED), the rule workbooks, and in the audit log every change to a governed
 * setting and the last recompute, which the engine records (GET /api/settings, read-only; the
 * fixture's copy when the engine is not answering). Nothing else leaves the browser: a chosen file is
 * never read (only its name is shown), the password field is never read, and nothing here changes a
 * figure on another screen.
 *
 * The licence shows its current state only. The stages a licence passes through are contract terms
 * that differ by client, so they live in the spec notes and the licence file, never on a screen.
 */
(function () {
  'use strict';

  var K = window.SettingsKit;
  var esc = K.esc, n0 = K.n0, sim = K.sim, pv = K.pv, N = K.N, plural = K.plural, when = K.when;
  var section = K.section, caveat = K.caveat, table = K.table, kv = K.kv;
  var F = window.__SETTINGS__, SIM = F.simulated, L = SIM.licence, AC = SIM.access;
  var can = window.Session.can, paused = window.Session.paused;

  var TABS = [
    { id: 'overview', t: 'Overview' },
    { id: 'data', t: 'Data' },
    { id: 'access', t: 'Users & access' },
    { id: 'audit', t: 'Audit log', need: 'audit.view' },
    { id: 'system', t: 'System' },
    { id: 'licence', t: 'Licence', need: 'licence.view' }
  ];

  var S = {
    tab: 'overview',
    gov: F.governed, live: null,          // the governed-settings history, as the engine or the fixture gave it
    refreshing: false, licMsg: '',
    wiz: null,                            // connecting a source: { step, kind: 'file' | 'db', db }
    auth: 'vault', form: { x: {}, a: {} }, test: null,
    up: { data: null, rules: null },
    audit: { kind: '', who: '', since: '', q: '' }
  };
  var timers = { test: 0 };

  function tabs() { return TABS.filter(function (t) { return !t.need || can(t.need); }); }
  function tabFrom(hash) {
    var id = String(hash || '').replace(/^#(sec-)?/, '');
    return tabs().some(function (t) { return t.id === id; }) ? id : 'overview';
  }

  /* ================================================================ engine (read-only) */
  function load() {
    fetch('/api/settings').then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (j) { S.gov = j; S.live = true; }, function () { S.live = false; })
      .then(function () { if (S.tab === 'overview' || S.tab === 'audit') window.PageShell.draw(true); });
  }

  /** A control a licence stage can pause: disabled, with the reason beside it. */
  function pausedNote(action) {
    return paused(action) ? '<p class="su-help su-gap" role="status">' + esc(L.refresh.paused_message) + '</p>' : '';
  }
  function dis(action) { return paused(action) ? ' disabled' : ''; }
  function go(tab, label) { return '<button type="button" class="btn ghost sm" data-tab="' + tab + '">' + esc(label) + '</button>'; }
  function requests() { return AC.users.filter(function (u) { return u.status === 'Requested'; }); }

  /* ================================================================ overview */
  /** One concern. `attn` opens it: its detail and the way to deal with it. */
  function card(o) {
    return '<div class="su-card' + (o.attn ? ' is-attn' : '') + (o.big ? ' is-big' : '') + '"' + (o.note || '') + '>' +
      '<div class="su-card-h"><span class="su-flag">' + esc(o.title.toUpperCase()) + '</span>' +
        (o.attn ? '<span class="su-need">NEEDS YOU</span>' : '') + '<div class="spacer"></div>' + (o.right || '') + '</div>' +
      '<div class="su-card-v">' + o.line + '</div>' +
      (o.attn && o.detail ? '<p class="su-card-d">' + o.detail + '</p>' : '') +
      (o.attn && o.tab ? '<div class="su-row su-gap">' + go(o.tab, o.action) + '</div>' : '') + '</div>';
  }
  function cards() {
    var out = [], sn = can('licence.view') ? window.Session.licence() : null;
    var D = F.dataset, FD = F.fields, R = S.gov && S.gov.recompute, V = SIM.versions;
    if (sn) {
      var ok = sn.status === 'active';
      out.push({ id: 'licence', title: 'Licence', attn: !ok, big: !ok, note: N('ov_licence'),
        line: ok ? esc(sn.headline) + ' · signature verified' : '<span class="su-lichead">' + (/^Expired/.test(sn.headline) ? 'Expired ' : '') + esc(sn.remaining) + '</span>',
        detail: '<b>' + esc(sn.status_label) + '.</b> ' + esc(sn.headline) + '. ' + esc(sn.does),
        tab: 'licence', action: 'Go to Licence' });
    }
    var failed = R && R.error, running = R && R.running;
    var computed = S.gov && S.gov.computed_at ? when(S.gov.computed_at) : esc(F.run.generated);
    out.push({ id: 'data', title: 'Data', attn: !!failed, right: pv('OBSERVED'), note: N('ov_data'),
      line: n0(D.rows) + ' applicants · ' + esc(D.date_from) + ' to ' + esc(D.date_to) +
        '<span class="su-card-s">' + (running ? 'Recompute running' : 'Figures computed ' + computed) + '</span>',
      detail: failed ? 'The last recompute did not finish: ' + esc(R.error) + '. The figures in use are unchanged.' : '',
      tab: 'data', action: 'Go to Data' });
    var mapped = FD.required_mapped === FD.required;
    out.push({ id: 'mapping', title: 'Field mapping', attn: !mapped, right: pv('OBSERVED'), note: N('ov_mapping'),
      line: n0(FD.required_mapped) + ' of ' + n0(FD.required) + ' required fields supplied',
      detail: 'Rules that read a missing field are not evaluated, so some declines are not replayed.',
      tab: 'data', action: 'Go to Data' });
    var waiting = requests();
    out.push({ id: 'access', title: 'Users & access', attn: waiting.length > 0, note: N('ov_access'),
      line: n0(AC.users.filter(function (u) { return u.status === 'Active'; }).length) + ' active users · sign-in ' + esc(AC.sso.status.toLowerCase()),
      detail: waiting.map(function (u) { return esc(u.name) + ' asked for ' + esc(u.role); }).join('; ') + '.',
      tab: 'access', action: 'Review ' + plural(waiting.length, 'request') });
    var ver = function (k) { return (V.filter(function (x) { return x.key === k; })[0] || {}).value || '—'; };
    out.push({ id: 'version', title: 'Version', note: N('ov_version'),
      line: 'Application ' + esc(ver('Application')) + '<span class="su-card-s">Last patch ' + esc(ver('Last patch')) + '</span>' });
    return out;
  }
  function secOverview() {
    var all = cards(), attn = all.filter(function (c) { return c.attn; });
    var answer = attn.length
      ? '<b>' + n0(attn.length) + ' ' + plural(attn.length, 'thing needs', 'things need') + ' you:</b> ' +
        attn.map(function (c) { return esc(c.title.toLowerCase()); }).join(', ') + '.'
      : '<b>Nothing needs you.</b> The product is licensed, data is loaded and every required field is supplied.';
    // What needs attention comes first and opens; the rest stay one line each.
    return '<p class="su-answer"' + N('ov_head') + '>' + answer + '</p>' +
      '<div class="su-cards">' + attn.concat(all.filter(function (c) { return !c.attn; })).map(card).join('') + '</div>';
  }

  /* ================================================================ data: the source */
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

  function secSource() {
    var D = F.dataset;
    return section('source', 'Source in use', pv('OBSERVED'),
      kv([{ key: 'Source', value: D.label }, { key: 'Applicants', value: n0(D.rows) },
          { key: 'Applications between', value: D.date_from + ' and ' + D.date_to }]) +
      (S.wiz ? '' : '<div class="su-row su-gap"><button type="button" class="btn sm" data-act="wiz-open"' + N('ds_connect') + dis('data.load') + '>Connect a new source</button></div>' +
        pausedNote('data.load')), N('ds_admin'));
  }

  /* The steps of connecting a source. A file skips the connection and its check. */
  function steps() {
    return S.wiz.kind === 'file' ? ['Kind', 'File', 'Map fields', 'Review'] : ['Kind', 'Connect', 'Check', 'Map fields', 'Review'];
  }
  function stepName() { return steps()[S.wiz.step]; }
  function canNext() {
    var s = stepName();
    if (s === 'Kind') return !!S.wiz.kind;
    if (s === 'File') return !!S.up.data;
    if (s === 'Check') return !!(S.test && S.test.done);
    return s !== 'Review';
  }
  function stepKind() {
    var kinds = [
      { id: 'file', label: 'A file', help: 'An extract from the loan origination system. Accepted: ' + SIM.upload.accept_data + '.' },
      { id: 'db', label: 'A database', help: 'A read-only connection to Oracle, PostgreSQL or MySQL, refreshed on a schedule.' }
    ];
    return '<div class="su-choice" role="radiogroup" aria-label="What kind of source"' + N('ds_kind') + '>' + kinds.map(function (k) {
      return '<label class="su-radio"><input type="radio" name="su-kind" data-kind="' + k.id + '"' + (S.wiz.kind === k.id ? ' checked' : '') + '>' +
        '<div><b>' + esc(k.label) + '</b><span>' + esc(k.help) + '</span></div></label>';
    }).join('') + '</div>';
  }
  function stepFile() {
    return '<div class="su-drop"><p><b>Drop an applicant file here</b>, or choose one. Accepted: ' + esc(SIM.upload.accept_data) + '.</p>' +
      '<button type="button" class="btn ghost sm" data-act="pick" data-for="data">Choose file</button>' +
      '<input type="file" id="su-file-data" data-file="data" accept="' + esc(SIM.upload.accept_data) + '" hidden></div>' +
      (S.up.data ? '<p class="su-help su-gap" role="status">Chosen: <span class="su-file">' + esc(S.up.data) + '</span></p>' : '');
  }
  function stepConnect() {
    var C = SIM.connectors, t = connector(S.wiz.db);
    var type = '<div class="su-grid"><div class="su-field"><label for="su-db">Database</label><select class="su-input" id="su-db" data-db="1">' +
      C.types.map(function (x) { return '<option value="' + x.id + '"' + (x.id === S.wiz.db ? ' selected' : '') + '>' + esc(x.label) + '</option>'; }).join('') +
      '</select></div></div>';
    var conn = '<div class="su-sub su-gap"' + N('ds_form') + '>Connection</div>' +
      '<div class="su-grid">' + t.fields.map(function (f) { return fieldHtml(S.wiz.db, f); }).join('') + '</div>';
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
      simpleField('x', 'limit', 'Row limit', { optional: true, ph: 'No limit' }) + '</div>' +
      '<div class="su-row su-gap"><button type="button" class="btn ghost sm" data-act="example">Use example values</button></div>';
    return type + conn + auth + extract;
  }
  function stepCheck() {
    return '<div class="su-row"><button type="button" class="btn sm" id="su-test" data-act="test"' + N('ds_test') + '>Test connection</button></div>' +
      '<div id="su-testout" aria-live="polite">' + testHtml() + '</div>';
  }
  function stepMap() {
    var ex = SIM.example_layout, C = F.fields, srcBy = {};
    ex.mapping.forEach(function (m) { srcBy[m.column] = m.source; });
    var rows = C.columns.filter(function (r) { return r.need !== 'Not requested'; }).map(function (r) {
      var src = srcBy[r.column] ? '<span class="su-mono">' + esc(srcBy[r.column]) + '</span>' : '<span class="su-unmapped">UNMAPPED</span>';
      return '<tr><td><span class="rid">' + esc(r.column) + '</span></td><td class="su-mono su-muted">' + esc(r.dtype) + '</td>' +
        '<td><span class="su-tag need-' + esc(r.need.split(' ')[0]) + '">' + esc(r.need) + '</span></td>' +
        '<td class="num">' + (r.rules ? n0(r.rules) : '<span class="nodata">—</span>') + '</td><td>' + src + '</td></tr>';
    });
    return caveat(ex.summary.unmapped_required.length ? 'warn' : '', 'EXAMPLE',
        '<strong>' + esc(ex.source_object) + ': ' + n0(ex.summary.required_mapped) + ' of ' + n0(ex.summary.required) +
        ' required fields mapped.</strong> This source could not be analysed until the rest are mapped or supplied. ' + esc(ex.note), N('mp_example')) +
      '<div class="su-scroll su-gap"><div class="tablewrap"><table class="t su-compact"><thead><tr><th>Field</th><th>Type</th>' +
      '<th>Need</th><th class="num">Rules</th><th>Source column</th></tr></thead><tbody>' + rows.join('') + '</tbody></table></div></div>';
  }
  function stepReview() {
    var ex = SIM.example_layout, short = ex.summary.unmapped_required.length;
    var what = S.wiz.kind === 'file' ? S.up.data : connector(S.wiz.db).label + ' · ' + (sv('x', 'name') || ex.source_object);
    return kv([{ key: 'Source', value: what },
               { key: 'Refresh', value: S.wiz.kind === 'file' ? 'When a new file is loaded' : sv('x', 'refresh', SIM.connectors.extraction.refresh[0]) },
               { key: 'Required fields mapped', value: n0(ex.summary.required_mapped) + ' of ' + n0(ex.summary.required) }]) +
      '<div class="su-gap">' + K.previewRows(F) + '</div>' +
      (short ? '<div class="su-gap">' + caveat('warn', 'NOT READY', n0(short) + ' required ' + plural(short, 'field is', 'fields are') +
        ' not mapped. Go back to Map fields, or ask for them in the extract.') + '</div>' : '') +
      '<div class="su-row su-gap"><button type="button" class="btn sm" data-act="noop"' + N('ds_review') + (short ? ' disabled' : '') +
        '>Switch the analysis to this source</button></div>';
  }
  function secConnect() {
    if (!S.wiz) return '';
    var list = steps(), at = S.wiz.step;
    var body = { Kind: stepKind, File: stepFile, Connect: stepConnect, Check: stepCheck, 'Map fields': stepMap, Review: stepReview }[stepName()]();
    var nav = '<ol class="su-stepper" aria-label="Steps">' + list.map(function (s, i) {
      return '<li' + (i === at ? ' aria-current="step"' : '') + (i < at ? ' class="is-done"' : '') + '><span>' + (i + 1) + '</span>' + esc(s) + '</li>';
    }).join('') + '</ol>';
    var foot = '<div class="su-row su-wizfoot">' +
      (at > 0 ? '<button type="button" class="btn ghost sm" data-act="wiz-back">Back</button>' : '') +
      '<div class="spacer"></div><button type="button" class="btn ghost sm" data-act="wiz-close">Cancel</button>' +
      (stepName() !== 'Review' ? '<button type="button" class="btn sm" data-act="wiz-next"' + (canNext() ? '' : ' disabled') + '>Next</button>' : '') + '</div>';
    return section('connect', 'Connect a source', '', nav + '<div class="su-wizbody">' + body + '</div>' + foot, N('ds_wizard'));
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
      (T.fail ? '<div class="su-verdict">Go back, correct this and test again.</div>' : '');
  }
  function paintTest() {
    var el = document.getElementById('su-testout');
    if (el) el.innerHTML = testHtml();
    var b = document.querySelector('[data-act="wiz-next"]');
    if (b) b.disabled = !canNext();
  }
  function runTest() {
    var CT = SIM.connection_test, t = connector(S.wiz.db), vals = S.form[S.wiz.db] || {};
    clearTimeout(timers.test);
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
    var t = connector(S.wiz.db);
    S.form[S.wiz.db] = S.form[S.wiz.db] || {};
    t.fields.forEach(function (f) { if (f.type === 'text' && f.placeholder) S.form[S.wiz.db][f.key] = f.placeholder; });
    S.form.a.vault = 'vault://los/readonly';
    S.form.a.user = 'svc_csopt_ro';
    S.form.x.name = 'LOS.APPLICATIONS_V';
    S.form.x.datecol = 'APP_DT';
  }

  /* ================================================================ data: mapping, outcomes, rules */
  function secMapping() {
    var C = F.fields, complete = C.required_mapped === C.required;
    return section('mapping', 'Field mapping', pv('OBSERVED'),
      caveat(complete ? 'obs' : 'warn', 'IN USE',
        '<strong>' + n0(C.required_mapped) + ' of ' + n0(C.required) + ' required fields supplied by the data in use.</strong> ' +
        (complete ? 'Every replay runs on it.' : 'Rules that read a missing field are not evaluated.'), N('mp_state')) +
      '<p class="su-help su-gap">A new source is mapped as a step of connecting it. Everyone who works with data sees the ' +
      'fields in use on <a href="settings.html#health">Settings</a>.</p>', N('mp_admin'));
  }
  function secOutcomes() {
    var O = F.outcome, P = SIM.outcomes;
    var judged = O.products.length ? table('<th>Product</th><th class="num">Booked</th><th class="num">Old enough to judge</th>' +
      '<th class="num">Went bad</th><th class="num">Bad rate</th>', O.products.map(function (r) {
        return '<tr><td>' + esc(r.product) + '</td><td class="num">' + n0(r.booked) + '</td><td class="num">' + n0(r.judged) + '</td>' +
          '<td class="num">' + n0(r.bad) + '</td><td class="num">' + (r.bad_rate === null ? '<span class="nodata">—</span>' :
          (100 * r.bad_rate).toFixed(1) + '%') + '</td></tr>';
      })) : '';
    return section('outcomes', 'Outcomes and performance', pv('OBSERVED'),
      '<div class="cols2"><div><div class="su-sub">What counts as bad</div>' + kv(O.definition) + '</div>' +
      '<div><div class="su-sub">Read from</div>' + kv(O.sources, true) + '<p class="su-help su-gap">' + esc(O.rule) + '</p></div></div>' +
      (judged ? '<div class="su-sub su-gap"' + N('oc_judged') + '>Loans the definition can judge</div>' + judged : '') +
      '<div class="su-sub su-gap"' + N('oc_planned') + '>Planned · not applied yet</div>' +
      '<p class="su-help">' + esc(P.note) + '</p>' +
      '<div class="cols2"><div>' + kv(P.exclusions) + '</div><div>' + kv(P.sources, true) + '</div></div>' +
      '<div class="su-gap">' + caveat('', 'RECONCILE', esc(P.reconciliation), N('oc_recon')) + '</div>', N('oc_head'));
  }
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
      inventory() +
      '<div class="su-sub su-gap">Load a workbook</div>' +
      '<div class="su-drop"' + N('rp_upload') + '><p><b>Drop a workbook here</b>, or choose one. Accepted: ' + esc(SIM.upload.accept_rules) + '.</p>' +
      '<button type="button" class="btn ghost sm" data-act="pick" data-for="rules"' + dis('rules.load') + '>Choose file</button>' +
      '<input type="file" id="su-file-rules" data-file="rules" accept="' + esc(SIM.upload.accept_rules) + '" hidden></div>' +
      pausedNote('rules.load') +
      (S.up.rules ? '<p class="su-help su-gap" role="status"><span class="su-file">' + esc(S.up.rules) + '</span> · ' + esc(SIM.upload.rules) + '</p>' : ''), N('rp_head'));
  }

  /* ================================================================ users and access */
  function secAccess() {
    var U = AC.users, SSO = AC.sso;
    var users = table('<th>Person</th><th>Role</th><th>Status</th><th>Last sign-in</th><th></th>', U.map(function (u) {
      return '<tr><td><b>' + esc(u.name) + '</b><br><small class="su-muted su-mono">' + esc(u.email) + '</small></td>' +
        '<td>' + esc(u.role) + '</td><td>' + (u.status === 'Active' ? esc(u.status) : '<b>' + esc(u.status) + '</b>') + '</td>' +
        '<td class="su-mono su-muted">' + (u.last ? when(u.last) : 'Never') + '</td>' +
        '<td>' + (u.status === 'Requested' ? '<button type="button" class="btn ghost sm" data-act="noop">Review request</button>' : '') + '</td></tr>';
    }));
    var roles = table('<th>Role</th><th>Directory group</th><th>May</th><th class="num">People</th>', AC.roles.map(function (r) {
      var g = SSO.groups.filter(function (x) { return x.role === r.role; })[0];
      var n = U.filter(function (u) { return u.role === r.role && u.status === 'Active'; }).length;
      return '<tr><td><b>' + esc(r.role) + '</b></td><td class="su-mono">' + esc(g ? g.group : '—') + '</td><td>' + esc(r.may) + '</td>' +
        '<td class="num">' + n0(n) + '</td></tr>';
    }));
    return section('signin', 'Sign-in', '',
        kv([{ key: 'Single sign-on', value: SSO.provider + ' · ' + SSO.status },
            { key: 'Last synchronised', value: when(SSO.synced) }, { key: 'Session', value: SSO.session }]) +
        '<p class="su-help su-gap">' + esc(SSO.note) + '</p>', N('ac_sso')) +
      section('users', 'People', '', users, N('ac_users')) +
      section('roles', 'Roles', '', roles, N('ac_roles'));
  }

  /* ================================================================ audit log */
  /** Every event, newest first: governed-setting changes as the engine recorded them, then the rest. */
  function events() {
    var out = [], H = S.gov ? S.gov.history : [], R = S.gov && S.gov.recompute;
    H.forEach(function (r) {
      var change = r.label + ' ' + K.setVal(r, r.from) + ' → ' + K.setVal(r, r.to);
      if (r.route === 'direct') { out.push({ at: r.decided_at, who: r.decided_by, kind: 'Settings', what: 'Changed ' + change, real: true }); return; }
      out.push({ at: r.proposed_at, who: r.proposed_by, kind: 'Settings', what: 'Proposed ' + change + (r.reason ? ': “' + r.reason + '”' : ''), real: true });
      if (r.decided_at) {
        out.push({ at: r.decided_at, who: r.decided_by, kind: 'Settings', real: true,
          what: r.status.charAt(0).toUpperCase() + r.status.slice(1) + ' ' + change + (r.note ? ': “' + r.note + '”' : '') });
      }
    });
    if (R && R.finished_at) out.push({ at: R.finished_at, who: R.by || '—', kind: 'Analysis', real: true,
      what: R.error ? 'Recompute failed; the figures in use were kept' : 'Recomputed the figures' });
    SIM.audit.forEach(function (a) { out.push({ at: a.at, who: a.who, kind: a.kind, what: a.what, real: false }); });
    // Newest first; within the same second, the later record (a decision after its proposal) first.
    out.forEach(function (e, i) { e.i = i; });
    return out.sort(function (a, b) { return a.at < b.at ? 1 : a.at > b.at ? -1 : b.i - a.i; });
  }
  var SINCE = [{ id: '', t: 'Any time' }, { id: '1', t: 'Last 24 hours' }, { id: '7', t: 'Last 7 days' }, { id: '30', t: 'Last 30 days' }];
  function shown(all) {
    var A = S.audit, q = A.q.trim().toLowerCase(), from = A.since ? Date.now() - Number(A.since) * 864e5 : 0;
    return all.filter(function (e) {
      return (!A.kind || e.kind === A.kind) && (!A.who || e.who === A.who) && (!from || Date.parse(e.at) >= from) &&
        (!q || (e.what + ' ' + e.who + ' ' + e.kind).toLowerCase().indexOf(q) >= 0);
    });
  }
  function auditRows(all) {
    var rows = shown(all);
    return '<p class="su-help" role="status">' + (rows.length === all.length ? 'All ' + n0(all.length) + ' events.'
        : n0(rows.length) + ' of ' + n0(all.length) + ' events.') + '</p>' +
      (rows.length ? table('<th>When</th><th>Who</th><th>Area</th><th>What</th><th' + N('au_source') + '>Record</th>', rows.map(function (e) {
        return '<tr><td class="su-mono su-muted">' + when(e.at) + '</td><td>' + esc(e.who) + '</td><td>' + esc(e.kind) + '</td>' +
          '<td>' + esc(e.what) + '</td><td class="su-mono su-muted">' + (e.real ? 'Recorded' : 'Example') + '</td></tr>';
      })) : '<p class="su-help">Nothing matches. Clear a filter to see more.</p>');
  }
  function pick(key, label, options) {
    return '<div class="su-field"><label for="su-au-' + key + '">' + esc(label) + '</label><select class="su-input" id="su-au-' + key + '" data-au="' + key + '">' +
      options.map(function (o) { return '<option value="' + esc(o.id) + '"' + (S.audit[key] === o.id ? ' selected' : '') + '>' + esc(o.t) + '</option>'; }).join('') + '</select></div>';
  }
  function uniq(all, key) {
    return all.map(function (e) { return e[key]; }).filter(function (v, i, a) { return a.indexOf(v) === i; }).sort()
      .map(function (v) { return { id: v, t: v }; });
  }
  function secAudit() {
    var all = events();
    var filters = '<div class="su-grid su-grid4"' + N('au_filter') + '>' +
      pick('kind', 'Area', [{ id: '', t: 'Every area' }].concat(uniq(all, 'kind'))) +
      pick('who', 'Who', [{ id: '', t: 'Anyone' }].concat(uniq(all, 'who'))) +
      pick('since', 'When', SINCE) +
      '<div class="su-field"><label for="su-au-q">Contains</label><input class="su-input" id="su-au-q" data-au="q" type="search" value="' +
        esc(S.audit.q) + '" placeholder="e.g. ceiling" autocomplete="off" spellcheck="false"></div></div>';
    return section('audit', 'Audit log', '',
      filters + '<div class="su-row su-gap"><div class="spacer"></div><button type="button" class="btn ghost sm" data-act="csv">Download these events (CSV)</button></div>' +
      '<div id="su-au-rows" class="su-gap">' + auditRows(all) + '</div>', N('au_head'));
  }
  function csv() {
    var q = function (v) { return '"' + String(v === null || v === undefined ? '' : v).replace(/"/g, '""') + '"'; };
    var lines = [['When (UTC)', 'Who', 'Area', 'What', 'Record'].map(q).join(',')].concat(shown(events()).map(function (e) {
      return [e.at, e.who, e.kind, e.what, e.real ? 'Recorded' : 'Example'].map(q).join(',');
    }));
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([lines.join('\r\n') + '\r\n'], { type: 'text/csv;charset=utf-8' }));
    a.download = 'audit-log.csv';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }

  /* ================================================================ system */
  function secPlatform() {
    var groups = SIM.governance.map(function (g) { return '<div><div class="su-sub">' + esc(g.group) + '</div>' + kv(g.items) + '</div>'; }).join('');
    return section('platform', 'Platform and security', '',
      '<div class="cols2">' + groups + '<div><div class="su-sub">Regional</div>' + kv(SIM.regional) + '</div></div>', N('gv_head'));
  }
  function secVersions() {
    return section('versions', 'Versions and updates', '', kv(SIM.versions, true) +
      '<p class="su-help su-gap">Updates arrive through the encrypted patch channel and never overwrite your configuration.</p>', N('vr_head'));
  }
  function secDiagnostics() {
    var D = SIM.diagnostics;
    return section('diagnostics', 'Support bundle and exports', '',
      '<div class="cols2"><div><div class="su-sub">Support bundle</div><p class="su-help">' + esc(D.bundle) + '</p>' +
      '<button type="button" class="btn ghost sm" data-act="noop">Create bundle</button></div>' +
      '<div><div class="su-sub">Exports</div>' + D.exports.map(function (e) {
        return '<div class="su-pv"><div><b>' + esc(e) + '</b></div><button type="button" class="btn ghost sm" data-act="noop">Export</button></div>';
      }).join('') + '<p class="su-help su-gap">' + esc(D.note) + '</p></div></div>', N('dg_head'));
  }

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
        '<div class="su-lichead">' + esc(sn.headline) + '</div>' +
        '<p class="su-licmeta"' + N('lic_status') + '><b>' + esc(sn.status_label) + '</b> · ' + esc(sn.remaining) +
          ' · signature ' + (L.signature.verified ? 'verified' : 'not verified') + '</p>' +
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
        kv([{ key: 'Licence ID', value: L.licence_id + ' (quote it to Azentio support)' }].concat(L.entitlements).concat(
           [{ key: 'Licence period', value: sn.term }])) +
      '</div></div>' +
      '<details class="su-tech"><summary' + N('lic_tech') + '>Technical details</summary>' +
        kv([{ key: 'Issued by', value: L.issued_by }, { key: 'Algorithm', value: L.signature.algorithm },
            { key: 'Fingerprint', value: L.signature.fingerprint }], true) + '</details>', N('lic_head'));
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

  /* ================================================================ page */
  var BUILD = {
    overview: [secOverview],
    data: [secSource, secConnect, secMapping, secOutcomes, secRules],
    access: [secAccess],
    audit: [secAudit],
    system: [secPlatform, secVersions, secDiagnostics],
    licence: [secLicence]
  };

  function tabBar() {
    return '<div class="su-tabs" role="tablist" aria-label="Administration"' + N('ad_tabs') + '>' + tabs().map(function (t) {
      var on = t.id === S.tab;
      return '<button type="button" class="chip" role="tab" data-tab="' + t.id + '" aria-selected="' + on + '"' +
        (on ? ' aria-current="true"' : '') + '>' + esc(t.t) + '</button>';
    }).join('') + '</div>';
  }
  function render() {
    if (!can('admin.view')) {
      var who = window.Session.who();
      return '<div class="pagehead"><h2' + N('ad_head') + '>Administration</h2></div>' +
        caveat('', 'NO ACCESS', 'Administration is available to administrators' + (who ? '. You are signed in as ' + esc(who) + '.' : '.') +
          ' <a href="settings.html">Go to Settings</a>.', N('ad_refused'));
    }
    S.tab = tabFrom('#' + S.tab);          // a role change can take a tab away
    return '<div class="pagehead"><div class="su-row"><h2' + N('ad_head') + '>Administration</h2>' + sim() + '</div>' +
      '<p>Is it healthy, is data flowing, who has access, and does anything need you.</p></div>' +
      tabBar() + '<div role="tabpanel" aria-label="' + esc(TABS.filter(function (t) { return t.id === S.tab; })[0].t) + '">' +
      BUILD[S.tab].map(function (b) { return b(); }).join('') + '</div>';
  }
  function select(id) {
    var next = tabFrom('#' + id);
    if (next !== S.tab) { S.tab = next; window.PageShell.draw(false); window.scrollTo(0, 0); }
    if (location.hash !== '#' + next) history.replaceState(null, '', '#' + next);
  }
  function redrawData() { window.PageShell.draw(true); }

  function click(e) {
    var t = e.target.closest('[data-tab]');
    if (t) { e.preventDefault(); select(t.getAttribute('data-tab')); return true; }
    var a = e.target.closest('[data-act]');
    if (!a) return false;
    var act = a.getAttribute('data-act');
    if (act === 'refresh') doRefresh();
    else if (act === 'pick') { var fi = document.getElementById('su-file-' + a.getAttribute('data-for')); if (fi) fi.click(); }
    else if (act === 'wiz-open') { S.wiz = { step: 0, kind: null, db: SIM.connectors.types[0].id }; S.test = null; redrawData(); }
    else if (act === 'wiz-close') { S.wiz = null; S.test = null; clearTimeout(timers.test); redrawData(); }
    else if (act === 'wiz-next' && canNext()) { S.wiz.step += 1; redrawData(); }
    else if (act === 'wiz-back') { S.wiz.step -= 1; clearTimeout(timers.test); redrawData(); }
    else if (act === 'test') runTest();
    else if (act === 'example') { exampleValues(); S.test = null; redrawData(); }
    else if (act === 'csv') csv();
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
    } else if (t.getAttribute('data-au') === 'q') {
      // Only the rows change, so the search box keeps its focus.
      S.audit.q = t.value;
      document.getElementById('su-au-rows').innerHTML = auditRows(events());
    }
  }
  function change(e) {
    var t = e.target;
    if (t.hasAttribute('data-au') && t.tagName === 'SELECT') {
      S.audit[t.getAttribute('data-au')] = t.value;
      document.getElementById('su-au-rows').innerHTML = auditRows(events());
    } else if (t.hasAttribute('data-db')) {
      S.wiz.db = t.value; S.test = null; redrawData();
    } else if (t.hasAttribute('data-kind')) {
      S.wiz.kind = t.getAttribute('data-kind'); S.test = null; redrawData();
    } else if (t.hasAttribute('data-s') && t.tagName === 'SELECT') {
      input(e);
      if (t.getAttribute('data-f') === 'obj') redrawData();
    } else if (t.hasAttribute('data-auth')) {
      S.auth = t.getAttribute('data-auth'); S.test = null; redrawData();
    } else if (t.hasAttribute('data-file') && t.files && t.files.length) {
      // Only the name is used. The file is never read.
      var kind = t.getAttribute('data-file'), name = t.files[0].name;
      if (kind === 'lic') {
        window.Session.applyLicence(name, function () { S.licMsg = L.refresh.apply + ' (' + name + ')'; window.PageShell.update('licence', secLicence()); });
      } else {
        S.up[kind] = name;
        redrawData();
      }
    }
  }

  S.tab = tabFrom(location.hash);
  window.PageShell.start({
    id: 'administration',
    sections: function () {
      if (!can('admin.view')) return [];
      return tabs().map(function (t) { return { id: t.id, t: t.t, current: t.id === S.tab }; });
    },
    select: select,
    render: render,
    // Shell notes (rail, tags, strip) come from settings_notes.js; the keys never overlap.
    notes: function () { return Object.assign({}, window.__SETTINGS_NOTES__(F), window.__ADMIN_NOTES__(F)); },
    click: click, input: input, change: change
  });
  if (can('admin.view')) load();
})();
