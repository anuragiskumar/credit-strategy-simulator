/* Rendering helpers shared by settings.js and admin.js.
 *
 * No arithmetic beyond turning a number into a string or a percentage, and no knowledge of who is
 * signed in: pages ask Session for that.
 *
 * Colour encodes provenance and nothing else. pv() draws a provenance tag (only OBSERVED here: these
 * pages show counted facts). sim() draws the achromatic PREVIEW tag for anything drawn from the
 * fixture's `simulated` key, once per block rather than once per element.
 */
(function () {
  'use strict';

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
  function plural(n, one, many) { return n === 1 ? one : (many || one + 's'); }

  /** The only place provenance is drawn on these pages. */
  function pv(kind, text) { return '<span class="pv pv-' + kind + '">' + esc(text || kind.replace('_', ' ')) + '</span>'; }
  /** Marks a block drawn from `simulated`. Deliberately not a provenance kind. */
  function sim(text) { return '<span class="su-sim" title="Not active in this environment">' + esc(text || 'PREVIEW') + '</span>'; }
  function N(key) { return ' data-note="' + key + '"'; }

  function tile(key, value, detail, cls, note) {
    return '<div class="tile ' + (cls || '') + '"><div class="k"' + (note || '') + '>' + key + '</div>' +
      '<div class="v fig">' + value + '</div>' + (detail ? '<div class="d">' + detail + '</div>' : '') + '</div>';
  }
  function section(id, title, right, body, note) {
    return '<section class="su-sec" id="sec-' + id + '"><div class="panel"><div class="panelhead"><h2' + (note || '') + '>' +
      esc(title) + '</h2><div class="spacer"></div>' + (right || '') + '</div><div class="panelbody">' + body + '</div></div></section>';
  }
  /** A collapsed section. `open` is the caller's record of whether the reader opened it. */
  function accordion(id, title, right, body, note, open) {
    return '<details class="su-acc" id="sec-' + id + '" data-acc="' + id + '"' + (open ? ' open' : '') + '>' +
      '<summary><h3' + (note || '') + '>' + esc(title) + '</h3><div class="spacer"></div>' + (right || '') +
      '</summary><div class="panelbody">' + body + '</div></details>';
  }
  function caveat(kind, tag, html, note) {
    return '<div class="caveat ' + kind + '"><div class="ci"' + (note || '') + '>' + esc(tag) + '</div><div><p>' + html + '</p></div></div>';
  }
  function table(head, rows) {
    return '<div class="tablewrap"><table class="t"><thead><tr>' + head + '</tr></thead><tbody>' + rows.join('') + '</tbody></table></div>';
  }
  function kv(pairs, mono) {
    return '<div class="su-kv">' + pairs.map(function (p) {
      return '<div class="k">' + esc(p.key) + '</div><div class="v' + (mono ? ' fig' : '') + '">' + esc(p.value) + '</div>';
    }).join('') + '</div>';
  }
  function pvRows(list) {
    return list.map(function (p) {
      return '<div class="su-pv"><div><b>' + esc(p.key) + '</b><span>' + esc(p.help) + '</span></div>' +
        '<div class="val">' + esc(typeof p.value === 'string' ? p.value : fmtVal(p.value, p.fmt)) + '</div></div>';
    }).join('');
  }
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  /** An engine timestamp (ISO, UTC) as the pages print it. */
  function when(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso || '');
    return m ? (+m[3]) + ' ' + MONTHS[+m[2] - 1] + ' ' + m[1] + ', ' + m[4] + ':' + m[5] + ' UTC' : esc(iso || '—');
  }
  /** A governed setting's value in its own unit. */
  function setVal(s, v) {
    if (s.unit === 'bool') return v ? 'Yes' : 'No';
    if (s.unit === 'rate') return (Math.round(v * 1000) / 10) + '%';
    return Number(v).toFixed(2) + '×';
  }
  /** The example rows of the applicant table. The section header carries the tag, so this repeats none. */
  function previewRows(F) {
    var P = F.dataset.preview;
    return '<div class="su-sub"' + N('ds_preview') + '>Example rows</div>' +
      table(P.columns.map(function (c, i) { return '<th' + (i > 3 ? ' class="num"' : '') + '>' + esc(c.replace(/_/g, ' ')) + '</th>'; }).join(''),
        P.rows.map(function (r) {
          return '<tr>' + r.map(function (v, i) { return '<td' + (i > 3 ? ' class="num"' : '') + '>' + cell(v) + '</td>'; }).join('') + '</tr>';
        }));
  }

  window.SettingsKit = {
    esc: esc, n0: n0, pct: pct, fmtVal: fmtVal, cell: cell, plural: plural, pv: pv, sim: sim, N: N,
    tile: tile, section: section, accordion: accordion, caveat: caveat, table: table, kv: kv, pvRows: pvRows,
    previewRows: previewRows, when: when, setVal: setVal,
    /** What a simulated action says when it is used. */
    UNAVAILABLE: 'Not available in this environment.'
  };
})();
