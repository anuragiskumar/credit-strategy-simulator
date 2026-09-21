/* Settings screen: licence, rule set, applicant data, field mapping, policy, run status,
 * and the platform items the deployed product needs. One page of client.html.
 *
 * This file contains no arithmetic beyond turning a number into a string or a percentage.
 * Every figure and every sentence is read from window.__SETTINGS__, produced by
 * ui/settings_export.py. Content the export puts under `simulated` sits under a PREVIEW tag:
 * one per block, not one per element, so the page reads as a product rather than a demo.
 * Nothing outside that key is ever tagged.
 *
 * The page speaks in product voice: labels and plain status. Why a thing is built the way it is
 * belongs in settings_notes.js, which the spec-notes icon shows, not on the page.
 *
 * What the simulated parts do in this demo:
 *   - nothing leaves the browser. There is no fetch, no XHR and no browser storage.
 *   - a file chosen for upload is never read; only its name is shown.
 *   - the password field is inert: no name, never read, never stored, never sent.
 *   - none of it changes the figures on any other screen.
 *
 * Colour encodes provenance and nothing else. Preview content is marked by a dashed
 * achromatic tag, so it is never mistaken for a fifth kind of number.
 *
 * client.js owns the shell (rail, spec-note numbering, theme). This file owns one page and
 * exposes it as window.SettingsScreen; client.js calls page(), rail(), after() and init().
 * Every class it adds is prefixed `su-`.
 */
(function () {
  'use strict';

  var F = window.__SETTINGS__;
  var SIM = F.simulated;
  var DEV = /[?&]dev=1\b/.test(location.search);

  var S = {
    lic: 'current', renewalWaiting: false, refreshing: false, licMsg: '',
    src: 'demo', auth: 'vault', form: { x: {}, a: {} }, test: null, previewed: false,
    up: { data: null, rules: null }, layout: 'demo', open: {}, recompute: null
  };
  var timers = { test: 0, recompute: 0, refresh: 0 };
  var host = null;      // set by init(): the shell's wrap, rail and callbacks
  var spy = null;       // scroll-spy observer, rebuilt every time the page is drawn
  function refreshSpec() { if (host) host.refreshSpec(); }

  /* ------------------------------------------------------------- formatting */
  function esc(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function n0(v) { return v === null || v === undefined ? '—' : Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 }); }
  function pct(v, dp) { return v === null || v === undefined ? '—' : (Number(v) * 100).toFixed(dp === undefined ? 1 : dp) + '%'; }
  function fmtVal(v, fmt) {
    if (fmt === 'pct0') return pct(v, 0);
    if (fmt === 'x2') return Number(v).toFixed(2) + '×';
    if (fmt === 'x1') return Number(v).toFixed(1) + '×';
    if (fmt === 'n0') return n0(v);
    if (fmt === 'list') return v.join(' · ');
    return String(v);
  }
  function cell(v) { return v === null || v === undefined ? '<span class="nodata">—</span>' : esc(v); }

  /** The only place provenance is decided. Settings shows only counted facts, so only OBSERVED. */
  function pv(kind, text) {
    return '<span class="pv pv-' + kind + '">' + esc(text || kind.replace('_', ' ')) + '</span>';
  }
  /** Marks a block drawn from `simulated`. Deliberately not a provenance kind. */
  function sim(text) { return '<span class="su-sim" title="Not active in this environment">' + esc(text || 'PREVIEW') + '</span>'; }
  /** What a simulated action says when it is used. */
  var UNAVAILABLE = 'Not available in this environment.';

  function N(key) { return ' data-note="' + key + '"'; }
  function plural(n, one, many) { return n === 1 ? one : (many || one + 's'); }

  function tile(key, value, detail, cls, note) {
    return '<div class="tile ' + (cls || '') + '"><div class="k"' + (note || '') + '>' + key + '</div>' +
      '<div class="v fig">' + value + '</div>' +
      (detail ? '<div class="d">' + detail + '</div>' : '') + '</div>';
  }
  function panelHtml(title, right, body, note) {
    return '<div class="panel"><div class="panelhead"><h2' + (note || '') + '>' + esc(title) + '</h2>' +
      '<div class="spacer"></div>' + (right || '') + '</div><div class="panelbody">' + body + '</div></div>';
  }
  function section(id, title, right, body, note) {
    return '<section class="su-sec" id="sec-' + id + '">' + panelHtml(title, right, body, note) + '</section>';
  }
  /** A collapsed section. `open` survives a re-render of the section. */
  function accordion(id, title, right, body, note) {
    return '<details class="su-acc" id="sec-' + id + '" data-acc="' + id + '"' + (S.open[id] ? ' open' : '') + '>' +
      '<summary><h3' + (note || '') + '>' + esc(title) + '</h3><div class="spacer"></div>' + (right || '') +
      '</summary><div class="panelbody">' + body + '</div></details>';
  }
  function caveat(kind, tag, html, note) {
    return '<div class="caveat ' + kind + '"><div class="ci"' + (note || '') + '>' + esc(tag) + '</div><div><p>' + html + '</p></div></div>';
  }
  function table(head, rows) {
    return '<div class="tablewrap"><table class="t"><thead><tr>' + head + '</tr></thead><tbody>' +
      rows.join('') + '</tbody></table></div>';
  }
  function kv(pairs, mono) {
    return '<div class="su-kv">' + pairs.map(function (p) {
      return '<div class="k">' + esc(p.key) + '</div><div class="v' + (mono ? ' fig' : '') + '">' + esc(p.value) + '</div>';
    }).join('') + '</div>';
  }

  /* ================================================================ licence */
  var SCENARIOS = { current: 'As of today', active: 'Active', expiring: 'Expiring', grace: 'Grace',
                    read_only: 'Read-only', suspended: 'Suspended', renewed: 'Renewed' };

  function licenceSnap() { return SIM.licence.scenarios[S.lic]; }

  function refreshIcon() {
    return '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9"/>' +
      '<path d="M13.5 2.5v3h-3"/></svg>';
  }

  function secLicence() {
    var L = SIM.licence, sn = licenceSnap();

    var rungs = L.ladder.map(function (r, i) {
      return '<li class="su-rung"' + (r.id === sn.status ? ' aria-current="step"' : '') + '>' +
        '<b>' + esc(r.label) + '</b><span class="from">' + (i === 0 ? '' : 'from ') + esc(r.from) + '</span>' +
        '<p>' + esc(r.does) + '</p></li>';
    }).join('');

    var dev = DEV
      ? '<div class="su-dev"><b>Presenter</b>' +
        '<label>Show state <select class="su-input" style="width:auto;display:inline-block" data-dev="lic">' +
        Object.keys(SCENARIOS).map(function (k) {
          return '<option value="' + k + '"' + (S.lic === k ? ' selected' : '') + '>' + SCENARIOS[k] + '</option>';
        }).join('') + '</select></label>' +
        '<label><input type="checkbox" data-dev="renew"' + (S.renewalWaiting ? ' checked' : '') + '> ' +
        'A renewed licence file has arrived</label></div>'
      : '';

    var body =
      '<div class="su-lic"><div>' +
        '<div class="su-licstate"' + N('lic_status') + '>Status · ' + esc(sn.status_label) + '</div>' +
        '<div class="su-lichead">' + esc(sn.headline) + '</div>' +
        '<p class="su-licmeta">' + esc(sn.remaining) + ' · term ' + esc(sn.term) + '</p>' +
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
      '</div><div>' +
        '<div class="su-sub"' + N('lic_ent') + '>Entitlements</div>' +
        kv(L.entitlements.concat([{ key: 'Licence ID', value: L.licence_id }])) +
        '<div class="su-sub"' + N('lic_sig') + '>Signature</div>' +
        kv([{ key: 'Algorithm', value: L.signature.algorithm },
            { key: 'Verified', value: L.signature.verified ? 'Yes, offline' : 'No' },
            { key: 'Fingerprint', value: L.signature.fingerprint }], true) +
      '</div></div>' +
      (sn.status !== 'active'
        ? '<div class="su-gap">' + caveat('warn', sn.status_label.toUpperCase(), esc(sn.does)) + '</div>' : '') +
      '<div class="su-sub"' + N('lic_ladder') + '>Term and renewal</div>' +
      '<ol class="su-ladder">' + rungs + '</ol>' +
      '<ul class="su-always"' + N('lic_always') + '>' + L.always.map(function (a) { return '<li>' + esc(a) + '</li>'; }).join('') + '</ul>' +
      '<div class="su-sub"' + N('lic_rem') + '>Renewal reminders</div>' +
      kv([{ key: 'Sent to', value: L.reminders.contacts.join(', ') },
          { key: 'Days before expiry', value: L.reminders.notice_days.join(' · ') }]) +
      dev;

    return accordion('licence', 'Licence', '<span class="su-faint su-mono su-summ">' + esc(sn.headline) + '</span>', body, N('lic_head'));
  }

  function paintChip() {
    var sn = licenceSnap(), chip = document.getElementById('licchip');
    chip.textContent = sn.chip;
    refreshSpec();
  }

  function doRefresh() {
    if (S.refreshing) return;
    S.refreshing = true; S.licMsg = '';
    update('licence'); focusId('su-refresh');
    clearTimeout(timers.refresh);
    timers.refresh = setTimeout(function () {
      S.refreshing = false;
      if (S.renewalWaiting) { S.lic = 'renewed'; S.renewalWaiting = false; S.licMsg = SIM.licence.refresh.found; }
      else { S.licMsg = SIM.licence.refresh.none; }
      update('licence'); paintChip(); paintReady(); focusId('su-refresh');
    }, 900);
  }

  /* ================================================================ readiness */
  function readyHtml() {
    var sn = licenceSnap(), R = F.run, D = F.dataset;
    return '<div class="tiles c4 su-ready" id="su-ready"' + N('ready') + '>' +
      tile('Rule set ' + pv('OBSERVED'), n0(R.rules_replayed), 'rules replayed · ' + n0(F.rulepack.totals.rules) +
           ' in ' + n0(F.rulepack.totals.files) + ' workbooks', 'on-obs', N('t_rules')) +
      tile('Applicant data ' + pv('OBSERVED'), D.available ? n0(D.rows) : '—',
           D.available ? esc(D.date_from) + ' to ' + esc(D.date_to) : 'No dataset loaded', 'on-obs', N('t_data')) +
      tile('Field coverage ' + pv('OBSERVED'), n0(F.fields.required_mapped) + ' of ' + n0(F.fields.required),
           'required fields supplied', 'on-obs', N('t_fields')) +
      tile('Licence ' + sim(), esc(sn.valid_to), esc(sn.status_label) + ' · ' + esc(sn.remaining), '', N('t_lic')) +
      '</div>';
  }
  function paintReady() {
    var el = document.getElementById('su-ready');
    if (!el) return;
    var t = document.createElement('div');
    t.innerHTML = readyHtml();
    el.replaceWith(t.firstChild);
    refreshSpec();
  }

  /* ================================================================ rule set */
  function secRules() {
    var RP = F.rulepack, T = RP.totals, R = F.run;
    var rows = [];
    RP.files.forEach(function (f) {
      f.tables.forEach(function (t, i) {
        rows.push('<tr><td class="su-file-cell">' +
          (i === 0 ? '<b title="SHA-256 ' + esc(f.sha12) + '…">' + esc(f.file) + '</b><span>updated ' + esc(f.modified) + '</span>' : '') + '</td>' +
          '<td><span class="rid">' + esc(t.table) + '</span></td>' +
          '<td>' + esc(t.role) + '</td>' +
          '<td>' + (t.stage ? esc(t.stage.replace(/_/g, ' ')) : '<span class="nodata">—</span>') + '</td>' +
          '<td class="num">' + n0(t.rules) + '</td>' +
          '<td class="num">' + n0(t.in_scope) + '</td>' +
          '<td class="num">' + n0(t.inactive) + '</td></tr>');
      });
    });
    rows.push('<tr class="is-total"><td>' + n0(T.files) + ' workbooks</td><td>' + n0(T.tables) + ' tables</td><td></td><td></td>' +
      '<td class="num">' + n0(T.rules) + '</td><td class="num">' + n0(T.in_scope) + '</td><td class="num">' + n0(T.inactive) + '</td></tr>');

    var nu = R.unevaluable.length;
    var uneval = nu
      ? caveat('warn', 'NOT EVALUATED', '<strong>' + n0(nu) + ' ' + plural(nu, 'rule reads', 'rules read') +
          ' data the applicant table does not carry:</strong> ' +
          R.unevaluable.map(function (id) { return '<span class="rid">' + esc(id) + '</span>'; }).join(', ') +
          '. See <a href="#sec-mapping" data-jump="mapping">field mapping</a>.', N('rp_uneval'))
      : '';

    var upload = '<div class="su-sub">Load a rule workbook ' + sim() + '</div>' +
      '<div class="su-drop"' + N('rp_upload') + '><p><b>Drop a workbook here</b>, or choose one. Accepted: ' + esc(SIM.upload.accept_rules) + '.</p>' +
      '<button type="button" class="btn ghost sm" data-act="pick" data-for="rules">Choose file</button>' +
      '<input type="file" id="su-file-rules" data-file="rules" accept="' + esc(SIM.upload.accept_rules) + '" hidden></div>' +
      (S.up.rules ? '<p class="su-help su-gap" role="status"><span class="su-file">' + esc(S.up.rules) + '</span> · ' + esc(SIM.upload.rules) + '</p>' : '');

    var opts = '<div class="su-sub">Scope</div>' +
      kv([{ key: 'Product', value: RP.product },
          { key: 'Include inactive rules', value: RP.options.include_inactive_rules ? 'Yes' : 'No' }]);

    return section('rules', 'Rule set', pv('OBSERVED'),
      '<p class="su-lead">The decision tables in the rule pack. Tables that apply to ' + esc(RP.product) + ' are replayed.</p>' +
      table('<th>Workbook</th><th' + N('rp_table') + '>Table</th><th' + N('rp_role') + '>Role</th><th>Stage</th>' +
            '<th class="num">Rules</th><th class="num"' + N('rp_scope') + '>In scope</th><th class="num">Inactive</th>', rows) +
      '<div class="su-gap">' + uneval + '</div>' + opts + upload, N('rp_head'));
  }

  /* ================================================================ applicant data */
  var SOURCES = [{ id: 'demo', label: 'Demo dataset' }, { id: 'upload', label: 'Upload a file' },
                 { id: 'oracle', label: 'Oracle' }, { id: 'postgres', label: 'PostgreSQL' }, { id: 'mysql', label: 'MySQL' }];

  function connector(id) { return SIM.connectors.types.filter(function (t) { return t.id === id; })[0]; }
  function sv(scope, key, dflt) {
    var o = S.form[scope] || {};
    return o[key] === undefined ? (dflt === undefined ? '' : dflt) : o[key];
  }

  function fieldHtml(scope, f) {
    var id = 'su-' + scope + '-' + f.key, val = sv(scope, f.key, f.default);
    var input;
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
    return '<div class="su-field' + (opt.wide ? ' wide' : '') + '"><label for="' + id + '">' + esc(label) + (opt.optional ? ' <i>optional</i>' : '') + '</label>' + input +
      (opt.help ? '<span class="su-help">' + esc(opt.help) + '</span>' : '') + '</div>';
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
      (isSql
        ? simpleField('x', 'sql', 'SQL query', { area: true, wide: true, ph: 'SELECT ... FROM ...' })
        : simpleField('x', 'name', 'Table or view', { ph: 'LOS.APPLICATIONS_V' })) +
      simpleField('x', 'datecol', 'Application date column', { ph: 'APP_DT' }) +
      simpleField('x', 'product', 'Product filter', { dflt: F.rulepack.product }) +
      selectField('x', 'window', 'Window', ['Last 12 months', 'Last 24 months', 'All history']) +
      selectField('x', 'refresh', 'Refresh', C.extraction.refresh) +
      simpleField('x', 'limit', 'Row limit', { optional: true, ph: 'No limit' }) +
      '</div>';

    var actions = '<div class="su-row su-gap"><button type="button" class="btn sm" id="su-test" data-act="test"' + N('ds_test') + '>Test connection</button>' +
      '<button type="button" class="btn ghost sm" data-act="example">Use example values</button>' +
      '<button type="button" class="btn ghost sm" data-act="preview"' + (S.test && S.test.done ? '' : ' disabled') + '>Preview rows</button></div>' +
      '<div id="su-testout" aria-live="polite">' + testHtml() + '</div>' +
      (S.previewed && S.test && S.test.done ? previewBlock('Example rows') : '');
    return conn + auth + extract + actions;
  }

  function testHtml() {
    var T = S.test;
    if (!T) return '';
    var lis = T.steps.map(function (s) {
      return '<li><span class="mk">✓</span><span class="lb">' + esc(s.label) + '</span><span class="dt">' + esc(s.detail) + '</span><span class="ms">' + esc(s.ms) + ' ms</span></li>';
    });
    if (T.fail) {
      lis.push('<li class="is-fail"><span class="mk">✗</span><span class="lb">' + esc(T.fail.label) + '</span><span class="dt">' + esc(T.fail.detail) + '</span><span class="ms"></span></li>');
    }
    return '<ul class="su-steps">' + lis.join('') + '</ul>' +
      (T.done ? '<div class="su-verdict">' + esc(SIM.connection_test.done) + '</div>' : '') +
      (T.fail ? '<div class="su-verdict">Correct this and test again.</div>' : '');
  }
  function paintTest() {
    var el = document.getElementById('su-testout');
    if (el) el.innerHTML = testHtml();
  }

  /** The section header already carries the tag, OBSERVED or PREVIEW, so the block repeats neither. */
  function previewBlock(title) {
    var P = F.dataset.preview;
    return '<div class="su-sub"' + N('ds_preview') + '>' + esc(title) + '</div>' +
      table(P.columns.map(function (c, i) { return '<th' + (i > 3 ? ' class="num"' : '') + '>' + esc(c.replace(/_/g, ' ')) + '</th>'; }).join(''),
        P.rows.map(function (r) {
          return '<tr>' + r.map(function (v, i) { return '<td' + (i > 3 ? ' class="num"' : '') + '>' + cell(v) + '</td>'; }).join('') + '</tr>';
        }));
  }

  function demoBlock() {
    var D = F.dataset;
    if (!D.available) return caveat('warn', 'NO DATA', 'No applicant dataset is loaded.');
    var nulls = D.nulls.filter(function (n) { return n.column === 'simah_score'; })[0];
    return '<div class="tiles c4"' + N('ds_demo') + '>' +
      tile('Applicants', n0(D.rows), esc(D.label), 'on-obs') +
      tile('Applications between', esc(D.date_from), 'to ' + esc(D.date_to)) +
      tile('Columns', n0(D.columns), 'in the applicant table') +
      tile('No bureau score', nulls ? pct(nulls.share, 1) : '—', 'applicants with no SIMAH score') +
      '</div>' +
      (D.schema_problems.length
        ? caveat('warn', 'SCHEMA', esc(D.schema_problems.join('; ')))
        : caveat('obs', 'SCHEMA', 'Passes all schema checks.')) +
      previewBlock('Example rows');
  }

  function uploadBlock() {
    return '<div class="su-drop"><p><b>Drop an applicant file here</b>, or choose one. Accepted: ' + esc(SIM.upload.accept_data) + '.</p>' +
      '<button type="button" class="btn ghost sm" data-act="pick" data-for="data">Choose file</button>' +
      '<input type="file" id="su-file-data" data-file="data" accept="' + esc(SIM.upload.accept_data) + '" hidden></div>' +
      (S.up.data ? '<p class="su-help su-gap" role="status"><span class="su-file">' + esc(S.up.data) + '</span> · ' + esc(SIM.upload.data) +
        ' The fields a file must carry are listed under <a href="#sec-mapping" data-jump="mapping">field mapping</a>.</p>' : '');
  }

  function secData() {
    var picker = '<div class="su-row" style="margin-bottom:14px"><div class="seg"' + N('ds_src') + ' role="group" aria-label="Where the applicant data comes from">' +
      SOURCES.map(function (s) {
        return '<button type="button" data-act="src" data-v="' + s.id + '" aria-pressed="' + (S.src === s.id) + '">' + esc(s.label) + '</button>';
      }).join('') + '</div></div>';
    var body = S.src === 'demo' ? demoBlock() : S.src === 'upload' ? uploadBlock() : dbForm();
    return section('data', 'Applicant data', S.src === 'demo' ? pv('OBSERVED') : sim(),
      '<p class="su-lead">Where the applications come from: a file, or a read-only connection to the loan origination database.</p>' +
      picker + body, N('ds_head'));
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

  function runTest() {
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
    if (fail) { S.test = { steps: [], fail: fail, done: false }; paintTest(); syncPreviewBtn(); return; }
    S.test = { steps: [], fail: null, done: false };
    var i = 0;
    (function next() {
      if (i >= CT.steps.length) { S.test.done = true; paintTest(); syncPreviewBtn(); return; }
      S.test.steps.push(CT.steps[i]); i += 1;
      paintTest();
      timers.test = setTimeout(next, 320);
    })();
  }
  function syncPreviewBtn() {
    var b = document.querySelector('[data-act="preview"]');
    if (b) b.disabled = !(S.test && S.test.done);
  }

  /* ================================================================ field mapping */
  function secMapping() {
    var ex = SIM.example_layout, C = F.fields;
    var isEx = S.layout === 'example';
    var srcBy = {};
    ex.mapping.forEach(function (m) { srcBy[m.column] = m.source; });
    var nullBy = {};
    (F.dataset.nulls || []).forEach(function (n) { nullBy[n.column] = n.share; });

    // A "Not requested" column exists only in the generated data; a bank is never asked for it.
    var rows = C.columns.filter(function (r) { return r.need !== 'Not requested'; }).map(function (r) {
      var src;
      if (!isEx) src = '<span class="su-mono">' + esc(r.column) + '</span>';
      else src = srcBy[r.column] ? '<span class="su-mono">' + esc(srcBy[r.column]) + '</span>' : '<span class="su-unmapped">UNMAPPED</span>';
      var miss = !isEx && r.null_share ? pct(r.null_share, 1) : '<span class="nodata">' + (isEx ? '' : '—') + '</span>';
      return '<tr><td><span class="rid">' + esc(r.column) + '</span></td><td class="su-mono su-muted">' + esc(r.dtype) + '</td>' +
        '<td><span class="su-tag need-' + esc(r.need.split(' ')[0]) + '">' + esc(r.need) + '</span></td>' +
        '<td class="num">' + (r.rules ? n0(r.rules) : '<span class="nodata">—</span>') + '</td>' +
        '<td>' + src + '</td><td class="num">' + miss + '</td></tr>';
    });

    var summary = isEx
      ? caveat(ex.summary.unmapped_required.length ? 'warn' : '', 'EXAMPLE',
          '<strong>' + n0(ex.summary.required_mapped) + ' of ' + n0(ex.summary.required) + ' required fields mapped.</strong> ' +
          'Nothing can run until the rest are mapped or supplied. ' + esc(ex.note), N('mp_example'))
      : caveat('obs', 'MAPPED', '<strong>' + n0(C.required_mapped) + ' of ' + n0(C.required) + ' required fields supplied.</strong>');

    // A rule field can be a whole expression, so it is named in a tooltip, not printed.
    var unsup = C.unsupplied.length
      ? '<div class="su-gap">' + caveat('warn', 'NOT SUPPLIED',
          '<strong>Data the applicant table does not carry.</strong> ' +
          C.unsupplied.map(function (u) {
            return n0(u.rules) + ' ' + plural(u.rules, 'rule reads', 'rules read') +
              ' a <abbr class="su-expr" title="' + esc(u.field) + '">derived value</abbr>';
          }).join('; ') + '. Not evaluated until supplied.',
          N('mp_unsupplied')) + '</div>'
      : '';

    var picker = '<div class="su-row" style="margin-bottom:14px"><div class="seg" role="group" aria-label="Which layout to show">' +
      '<button type="button" data-act="layout" data-v="demo" aria-pressed="' + !isEx + '">Current dataset</button>' +
      '<button type="button" data-act="layout" data-v="example" aria-pressed="' + isEx + '">Example bank layout</button></div></div>';

    return section('mapping', 'Field mapping', isEx ? sim() : pv('OBSERVED'),
      '<p class="su-lead">The fields the rules read from each applicant record, and how many rules read each.</p>' + picker + summary +
      '<div class="su-scroll su-gap"><div class="tablewrap"><table class="t su-compact"><thead><tr><th>Field</th><th>Type</th>' +
      '<th' + N('mp_need') + '>Need</th><th class="num">Rules</th><th>Source column</th><th class="num">Missing</th></tr></thead><tbody>' +
      rows.join('') + '</tbody></table></div></div>' + unsup, N('mp_head'));
  }

  /* ================================================================ policy */
  function pvRows(list) {
    return list.map(function (p) {
      return '<div class="su-pv"><div><b>' + esc(p.key) + '</b><span>' + esc(p.help) + '</span></div>' +
        '<div class="val">' + esc(typeof p.value === 'string' ? p.value : fmtVal(p.value, p.fmt)) + '</div></div>';
    }).join('');
  }

  function secPolicy() {
    var P = F.policy;
    var levers = table('<th>Change</th><th class="num">From</th><th class="num">To</th>',
      P.levers.map(function (l) {
        return '<tr><td title="' + esc(l.field) + '">' + esc(l.label) + '</td><td class="num">' + esc(l.from) + '</td><td class="num">' + esc(l.to) + '</td></tr>';
      }));
    return section('policy', 'Policy and risk appetite', pv('OBSERVED'),
      '<p class="su-lead">Values set by the risk committee. They change through configuration and take effect on the next recompute.</p>' +
      '<div class="su-policy"><div><div class="su-sub">Risk appetite</div>' + pvRows(P.appetite) + '</div>' +
      '<div><div class="su-sub">Risk model</div>' + pvRows(P.model) + '</div>' +
      '<div><div class="su-sub">Portfolio and product</div>' + pvRows(P.portfolio.concat(P.product)) + '</div></div>' +
      '<div class="su-policy su-gap">' +
      '<div><div class="su-sub"' + N('po_assume') + '>Replay assumptions</div>' + pvRows(P.assumptions) + '</div>' +
      '<div><div class="su-sub"' + N('po_hard') + '>Never relaxed by the optimiser</div>' +
        '<p class="su-help">Regulatory and staff checks stay in force in every strategy:</p>' +
        '<ul class="su-list">' + P.hard_reject.map(function (h) { return '<li title="' + esc(h.field) + '">' + esc(h.label) + '</li>'; }).join('') + '</ul>' +
      '<div class="su-sub"' + N('po_levers') + '>Thresholds the optimiser may move</div>' + levers + '</div></div>', N('po_head'));
  }

  /* ================================================================ run and data quality */
  function secRun() {
    var R = F.run, D = F.dataset;
    if (!R.available) return section('run', 'Run and data quality', '', caveat('warn', 'NO DATA', 'No dataset, so nothing was replayed.'), N('rn_head'));
    var never = R.never_fire.map(function (r) {
      return '<tr><td><span class="rid">' + esc(r.rule_id) + '</span></td><td>' + esc(r.description) + '</td></tr>';
    });
    var nulls = (D.nulls || []).map(function (n) {
      return '<tr><td><span class="rid">' + esc(n.column) + '</span></td><td class="num">' + pct(n.share, 1) + '</td>' +
        '<td style="width:140px"><span class="su-nullbar" style="width:' + Math.max(1, Math.round(n.share * 100)) + '%"></span></td></tr>';
    });
    var rec = '<div class="su-sub">Recompute ' + sim() + '</div><div class="su-row"><button type="button" class="btn sm" id="su-recompute" data-act="recompute"' + N('rn_recompute') +
      (S.recompute && !S.recompute.done ? ' disabled' : '') + '>Recompute</button><span class="su-help">' + esc(SIM.recompute.note) + '</span></div>' +
      '<div id="su-recout" aria-live="polite">' + recomputeHtml() + '</div>';

    return section('run', 'Run and data quality', pv('OBSERVED'),
      '<div class="tiles c4">' +
        tile('Applicants replayed', n0(R.applicants), 'in the last run', 'on-obs') +
        tile('Rules replayed', n0(R.rules_replayed), n0(R.rules_in_scope) + ' in scope', 'on-obs') +
        tile('Replay time', R.replay_seconds.toFixed(1) + 's', 'last run') +
        tile('Rules that catch nobody', n0(R.never_fire_count), 'of ' + n0(R.rules_replayed) + ' replayed', '', N('rn_never')) +
      '</div>' +
      '<div class="cols2 su-gap"><div><div class="su-sub">Rules that catch nobody · first ' + n0(R.never_fire.length) + '</div>' +
        table('<th>Rule</th><th>Description</th>', never) + '</div>' +
      '<div><div class="su-sub"' + N('rn_nulls') + '>Fields with missing values</div>' +
        table('<th>Field</th><th class="num">Missing</th><th></th>', nulls) + '</div></div>' + rec +
      '<p class="su-help su-gap">Run at ' + esc(R.generated) + '.</p>', N('rn_head'));
  }

  function recomputeHtml() {
    var Rc = S.recompute;
    if (!Rc) return '';
    return '<ul class="su-steps">' + Rc.steps.map(function (s) {
      return '<li><span class="mk">✓</span><span class="lb">' + esc(s) + '</span><span class="dt"></span><span class="ms"></span></li>';
    }).join('') + '</ul>' + (Rc.done ? '<div class="su-verdict">' + esc(SIM.recompute.done) + '</div>' : '');
  }
  function paintRecompute() {
    var el = document.getElementById('su-recout');
    if (el) el.innerHTML = recomputeHtml();
    var b = document.getElementById('su-recompute');
    if (b) b.disabled = !!(S.recompute && !S.recompute.done);
  }
  function runRecompute() {
    clearTimeout(timers.recompute);
    S.recompute = { steps: [], done: false };
    var i = 0, all = SIM.recompute.steps;
    paintRecompute();
    (function next() {
      if (i >= all.length) { S.recompute.done = true; paintRecompute(); return; }
      S.recompute.steps.push(all[i]); i += 1; paintRecompute();
      timers.recompute = setTimeout(next, 380);
    })();
  }

  /* ================================================================ accordions (all simulated)
   * They sit under one "Deployment and administration" heading that carries the only PREVIEW tag,
   * so each accordion does not repeat it. */
  function secOutcomes() {
    var O = SIM.outcomes;
    return accordion('outcomes', 'Outcomes and performance', '',
      '<p class="su-lead">' + esc(O.note) + '</p>' +
      '<div class="cols2"><div><div class="su-sub">What counts as bad</div>' + kv(O.definition) + '</div>' +
      '<div><div class="su-sub">Where the outcome comes from</div>' + kv(O.sources, true) + '</div></div>' +
      '<div class="su-gap">' + caveat('', 'RECONCILE', esc(O.reconciliation), N('oc_recon')) + '</div>', N('oc_head'));
  }
  function secPlatform() {
    var groups = SIM.governance.map(function (g) {
      return '<div><div class="su-sub">' + esc(g.group) + '</div>' + kv(g.items) + '</div>';
    }).join('');
    return accordion('platform', 'Platform, access and security', '',
      '<div class="cols2">' + groups + '<div><div class="su-sub">Regional</div>' + kv(SIM.regional) + '</div></div>', N('gv_head'));
  }
  function secAudit() {
    return accordion('audit', 'Audit log', '',
      table('<th>When</th><th>Who</th><th>What</th>', SIM.audit.map(function (a) {
        return '<tr><td class="su-mono su-muted">' + esc(a.when) + '</td><td>' + esc(a.who) + '</td><td>' + esc(a.what) + '</td></tr>';
      })), N('au_head'));
  }
  function secVersions() {
    return accordion('versions', 'Versions and updates', '', kv(SIM.versions, true) +
      '<p class="su-help su-gap">Updates arrive through the encrypted patch channel and never overwrite your configuration.</p>', N('vr_head'));
  }
  function secDiagnostics() {
    var D = SIM.diagnostics;
    return accordion('diagnostics', 'Diagnostics and export', '',
      '<div class="cols2"><div><div class="su-sub">Support bundle</div><p class="su-help">' + esc(D.bundle) + '</p>' +
      '<button type="button" class="btn ghost sm" data-act="noop">Create bundle</button></div>' +
      '<div><div class="su-sub">Exports</div>' + D.exports.map(function (e) {
        return '<div class="su-pv"><div><b>' + esc(e) + '</b></div><button type="button" class="btn ghost sm" data-act="noop">Export</button></div>';
      }).join('') + '<p class="su-help su-gap">' + esc(D.note) + '</p></div></div>', N('dg_head'));
  }

  /* ================================================================ page */
  // What the analysis runs on comes first; how the installed product is run comes after, collapsed.
  var SECTIONS = [
    { id: 'rules', t: 'Rule set', build: secRules },
    { id: 'policy', t: 'Policy and risk appetite', build: secPolicy },
    { id: 'run', t: 'Run and data quality', build: secRun },
    { id: 'data', t: 'Applicant data', build: secData },
    { id: 'mapping', t: 'Field mapping', build: secMapping },
    { id: 'licence', t: 'Licence', build: secLicence, admin: true },
    { id: 'outcomes', t: 'Outcomes', build: secOutcomes, admin: true },
    { id: 'platform', t: 'Platform and security', build: secPlatform, admin: true },
    { id: 'audit', t: 'Audit log', build: secAudit, admin: true },
    { id: 'versions', t: 'Versions and updates', build: secVersions, admin: true },
    { id: 'diagnostics', t: 'Diagnostics and export', build: secDiagnostics, admin: true }
  ];
  var ADMIN_TITLE = 'Deployment and administration';

  function adminHead() {
    return '<div class="su-group"><h3' + N('dp_head') + '>' + esc(ADMIN_TITLE) + '</h3>' + sim() + '</div>' +
      '<p class="su-help">How the installed product is licensed, secured and maintained.</p>';
  }

  function pageHtml() {
    var core = SECTIONS.filter(function (s) { return !s.admin; });
    var admin = SECTIONS.filter(function (s) { return s.admin; });
    return '<div class="pagehead"><h2' + N('pg_head') + '>Settings</h2>' +
      '<p>The rules, data and policy values the analysis runs on.</p></div>' +
      // The presenter sees which parts are live; the client sees one PREVIEW tag per block instead.
      (DEV ? caveat('', 'PRESENTER', 'Rule set, dataset facts, field requirements, policy values and replay timings are ' +
        'read from the engine. Anything under a ' + sim() + ' tag is inert.') : '') +
      '<div class="su-gap">' + readyHtml() + '</div>' +
      core.map(function (s) { return s.build(); }).join('') +
      adminHead() +
      admin.map(function (s) { return s.build(); }).join('');
  }

  function update(id) {
    var s = SECTIONS.filter(function (x) { return x.id === id; })[0];
    var el = document.getElementById('sec-' + id);
    if (!s || !el) return;          // the page is not on screen
    var t = document.createElement('div');
    t.innerHTML = s.build();
    var fresh = t.firstChild;
    el.replaceWith(fresh);
    if (spy) spy.observe(fresh);
    refreshSpec();
  }
  function focusId(id) { var el = document.getElementById(id); if (el) el.focus(); }

  /** Sub-navigation shown in the rail while this page is open. */
  function railHtml() {
    function item(s) {
      return '<button type="button" class="navitem" data-jump="' + s.id + '"><span class="lbl">' + esc(s.t) + '</span></button>';
    }
    return '<div class="railgroup"><h4' + N('rail_sections') + '>On this page</h4>' +
      SECTIONS.filter(function (s) { return !s.admin; }).map(item).join('') + '</div>' +
      '<div class="railgroup"><h4>Administration</h4>' +
      SECTIONS.filter(function (s) { return s.admin; }).map(item).join('') + '</div>';
  }

  function jump(id) {
    var el = document.getElementById('sec-' + id);
    if (!el) return;
    var calm = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    el.scrollIntoView({ block: 'start', behavior: calm ? 'auto' : 'smooth' });
    if (el.tagName === 'DETAILS') { el.open = true; S.open[id] = true; }
    markCurrent(id);
  }
  function markCurrent(id) {
    document.querySelectorAll('#rail [data-jump]').forEach(function (a) {
      if (a.getAttribute('data-jump') === id) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
    });
  }

  /** Called after the page is put on screen: keeps the rail's current item in step with the scroll. */
  function after() {
    if (spy) spy.disconnect();
    spy = null;
    if (!('IntersectionObserver' in window)) return;
    spy = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) markCurrent(en.target.id.replace('sec-', ''));
      });
    }, { root: document.getElementById('canvas'), rootMargin: '-15% 0px -75% 0px' });
    SECTIONS.forEach(function (s) { var el = document.getElementById('sec-' + s.id); if (el) spy.observe(el); });
    paintChip();
  }

  /* ---------------------------------------------------------------- events (delegated once)
   * The wrap and the rail persist while client.js swaps the page inside them, so the listeners
   * are attached once, here, and act only on the data- attributes this page draws. */
  function init(h) {
    host = h;
    var wrap = h.wrap;

    wrap.addEventListener('click', function (e) {
      var a = e.target.closest('[data-act]');
      if (!a) {
        var j = e.target.closest('[data-jump]');
        if (j) { e.preventDefault(); jump(j.getAttribute('data-jump')); }
        return;
      }
      var act = a.getAttribute('data-act');
      if (act === 'refresh') doRefresh();
      else if (act === 'pick') { var fi = document.getElementById('su-file-' + a.getAttribute('data-for')); if (fi) fi.click(); }
      else if (act === 'src') {
        S.src = a.getAttribute('data-v'); S.test = null; S.previewed = false; clearTimeout(timers.test);
        update('data'); var pressed = document.querySelector('[data-act="src"][data-v="' + S.src + '"]'); if (pressed) pressed.focus();
      }
      else if (act === 'layout') {
        S.layout = a.getAttribute('data-v'); update('mapping');
        var lb = document.querySelector('[data-act="layout"][data-v="' + S.layout + '"]'); if (lb) lb.focus();
      }
      else if (act === 'test') runTest();
      else if (act === 'example') { exampleValues(); S.test = null; update('data'); }
      else if (act === 'preview') { S.previewed = true; update('data'); }
      else if (act === 'recompute') runRecompute();
      else if (act === 'noop') {
        if (!a.parentNode.querySelector('.su-noop')) {
          var m = document.createElement('span');
          m.className = 'su-help su-noop';
          m.setAttribute('role', 'status');
          m.textContent = ' ' + UNAVAILABLE;
          a.after(m);
        }
      }
    });

    wrap.addEventListener('input', function (e) {
      var t = e.target;
      if (t.hasAttribute('data-s') && t.hasAttribute('data-f')) {
        var sc = t.getAttribute('data-s');
        S.form[sc] = S.form[sc] || {};
        S.form[sc][t.getAttribute('data-f')] = t.value;
      }
    });

    wrap.addEventListener('change', function (e) {
      var t = e.target;
      if (t.hasAttribute('data-s') && t.tagName === 'SELECT') {
        var sc = t.getAttribute('data-s');
        S.form[sc] = S.form[sc] || {};
        S.form[sc][t.getAttribute('data-f')] = t.value;
        if (t.getAttribute('data-f') === 'obj') update('data');
      } else if (t.hasAttribute('data-auth')) {
        S.auth = t.getAttribute('data-auth'); S.test = null; update('data');
      } else if (t.getAttribute('data-dev') === 'lic') {
        S.lic = t.value; S.licMsg = ''; update('licence'); paintChip(); paintReady();
      } else if (t.getAttribute('data-dev') === 'renew') {
        S.renewalWaiting = t.checked;
      } else if (t.hasAttribute('data-file') && t.files && t.files.length) {
        // Only the name is used. The file is never read.
        var kind = t.getAttribute('data-file'), name = t.files[0].name;
        if (kind === 'lic') {
          S.lic = 'renewed'; S.renewalWaiting = false; S.licMsg = SIM.licence.refresh.apply + ' (' + name + ')';
          update('licence'); paintChip(); paintReady();
        } else {
          S.up[kind] = name; update(kind === 'rules' ? 'rules' : 'data');
        }
      }
    });

    // <details> does not bubble its toggle event, so listen in the capture phase.
    wrap.addEventListener('toggle', function (e) {
      var d = e.target;
      if (d.hasAttribute && d.hasAttribute('data-acc')) { S.open[d.getAttribute('data-acc')] = d.open; refreshSpec(); }
    }, true);

    // The rail's sub-navigation is redrawn by the shell on every page change, so listen on its container.
    h.rail.addEventListener('click', function (e) {
      var j = e.target.closest('[data-jump]');
      if (j) { e.preventDefault(); jump(j.getAttribute('data-jump')); h.closeRail(); }
    });

    // The licence chip in the topbar: open this page at the licence.
    document.getElementById('licchip').addEventListener('click', function () { h.go('settings'); jump('licence'); });
    paintChip();
  }

  window.SettingsScreen = { init: init, page: pageHtml, rail: railHtml, after: after };
})();
