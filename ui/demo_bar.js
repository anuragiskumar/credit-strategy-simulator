/* DEMO ONLY. Never ships in the product.
 *
 * The "View as" menu at the top right of every page. It stands in for the server: it decides what
 * each role may do and hands that to Session (session.js), which is all the screens ever read. In
 * the deployed product the server's access-control decision replaces this file, so deleting its one
 * <script> tag leaves every page working, as a person with no extra permissions.
 *
 * This is the only file that knows role names, and the only one that uses browser storage: the
 * chosen role, presenter notes and licence stage survive moving between client.html, settings.html
 * and admin.html in the same tab. Its styles are injected from here so removal is one tag, not two.
 *
 * It replaces the old ?dev=1 and ?role= switches.
 */
(function () {
  'use strict';

  var ROLES = [
    { id: 'business', label: 'Business user', can: [] },
    { id: 'analyst', label: 'Analyst', can: ['data.view', 'recompute.run'] },
    { id: 'approver', label: 'Risk approver', can: ['data.view', 'audit.view'] },
    { id: 'admin', label: 'Administrator', can: ['data.view', 'audit.view', 'admin.view', 'licence.view'] }
  ];
  var STAGES = [
    { id: 'current', label: 'As of today' }, { id: 'expiring', label: 'Expiring' }, { id: 'grace', label: 'Grace' },
    { id: 'read_only', label: 'Read-only' }, { id: 'suspended', label: 'Suspended' }, { id: 'renewed', label: 'Renewed' }
  ];
  var KEY = 'azentio-demo';
  var LIC = window.__SETTINGS__ && window.__SETTINGS__.simulated && window.__SETTINGS__.simulated.licence;

  var D = { role: 'business', presenter: false, stage: 'current', renewal: false };
  try { Object.assign(D, JSON.parse(sessionStorage.getItem(KEY) || '{}')); } catch (e) { /* private window: defaults */ }
  if (!ROLES.some(function (r) { return r.id === D.role; })) D.role = 'business';
  // A page without the licence fixture keeps the stage it was given, so moving between pages never resets it.
  if (LIC && !LIC.scenarios[D.stage]) D.stage = 'current';

  function save() { try { sessionStorage.setItem(KEY, JSON.stringify(D)); } catch (e) { /* not kept */ } }
  function role() { return ROLES.filter(function (r) { return r.id === D.role; })[0]; }
  function snap() { return LIC ? LIC.scenarios[D.stage] : null; }

  /** What the server would send for this person. */
  function publish() {
    var r = role(), s = snap();
    window.Session.set({
      can: r.can, who: r.label,
      paused: s ? s.paused : [],
      licence: s && r.can.indexOf('licence.view') >= 0 ? s : null
    });
  }

  window.Session.handle({
    refreshLicence: function (done) {
      setTimeout(function () {
        var found = D.renewal;
        if (found) { D.stage = 'renewed'; D.renewal = false; save(); draw(); publish(); }
        done({ found: found });
      }, 900);
    },
    applyLicence: function (name, done) {
      D.stage = 'renewed'; D.renewal = false; save(); draw(); publish();
      done({ applied: true, name: name });
    }
  });

  /* ------------------------------------------------------------------ menu */
  var css =
    '.dm{position:relative;flex:0 0 auto}' +
    '.dm>summary{list-style:none;display:inline-flex;align-items:center;gap:7px;height:28px;padding:0 10px;' +
      'border:1px dashed var(--line-hard);border-radius:6px;cursor:pointer;font-family:var(--mono);font-size:11px;' +
      'color:var(--ink-2);white-space:nowrap;background:var(--surface)}' +
    '.dm>summary::-webkit-details-marker{display:none}' +
    '.dm>summary:hover{background:var(--sunken)}' +
    '.dm>summary:focus-visible{outline:2px solid var(--ink);outline-offset:1px}' +
    '.dm>summary i{font-style:normal;font-size:9px;letter-spacing:.1em;color:var(--faint)}' +
    '.dm>summary::after{content:"";width:5px;height:5px;border-right:1.3px solid currentColor;' +
      'border-bottom:1.3px solid currentColor;transform:rotate(45deg) translateY(-2px)}' +
    '.dm-menu{position:absolute;inset-inline-end:0;top:34px;z-index:50;width:250px;padding:8px;background:var(--surface);' +
      'border:1px solid var(--line-hard);border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.12);font-size:12.5px}' +
    '.dm-menu h5{margin:4px 6px 6px;font-family:var(--mono);font-size:9.5px;font-weight:500;letter-spacing:.1em;' +
      'text-transform:uppercase;color:var(--faint)}' +
    '.dm-menu label{display:flex;align-items:center;gap:8px;padding:6px;border-radius:5px;cursor:pointer;color:var(--ink-2)}' +
    '.dm-menu label:hover{background:var(--sunken)}' +
    '.dm-menu input{margin:0;accent-color:var(--ink-2)}' +
    '.dm-menu hr{border:0;border-top:1px solid var(--line-soft);margin:8px 0}' +
    '.dm-menu select{margin-inline-start:auto;height:26px;border:1px solid var(--line-hard);border-radius:5px;' +
      'background:var(--surface);color:var(--ink);font-size:12px}' +
    '.dm-menu p{margin:6px;font-size:11px;line-height:1.45;color:var(--faint)}' +
    '.dm-note{display:flex;gap:10px;padding:7px 16px;border-bottom:1px dashed var(--line-hard);background:var(--sunken);' +
      'font-size:12px;line-height:1.5;color:var(--ink-2)}' +
    '.dm-note b{font-family:var(--mono);font-size:10px;letter-spacing:.1em;color:var(--faint);white-space:nowrap;padding-top:1px}' +
    '@media (max-width:640px){.dm>summary .dm-who{display:none}}';

  function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

  var box = document.createElement('details');
  box.className = 'dm';
  box.id = 'demobar';

  function draw() {
    var open = box.open;
    box.innerHTML =
      '<summary aria-label="Demo: view as ' + esc(role().label) + '"><i>DEMO</i><span class="dm-who">' + esc(role().label) + '</span></summary>' +
      '<div class="dm-menu" role="group" aria-label="Demo controls">' +
        '<h5>View as</h5>' +
        ROLES.map(function (r) {
          return '<label><input type="radio" name="dm-role" value="' + r.id + '"' + (r.id === D.role ? ' checked' : '') + '>' + esc(r.label) + '</label>';
        }).join('') +
        '<hr><h5>Presenter</h5>' +
        '<label><input type="checkbox" data-dm="presenter"' + (D.presenter ? ' checked' : '') + '>Show what is live</label>' +
        (LIC
          ? '<label>Licence stage <select data-dm="stage" aria-label="Licence stage">' + STAGES.map(function (s) {
              return '<option value="' + s.id + '"' + (s.id === D.stage ? ' selected' : '') + '>' + esc(s.label) + '</option>';
            }).join('') + '</select></label>' +
            '<label><input type="checkbox" data-dm="renewal"' + (D.renewal ? ' checked' : '') + '>A renewed licence has arrived</label>'
          : '') +
        '<p>Demo only. The product decides this from the signed-in user.</p>' +
      '</div>';
    box.open = open;
    presenterNote();
  }

  function presenterNote() {
    var el = document.getElementById('dm-note');
    if (!D.presenter) { if (el) el.remove(); return; }
    if (el) return;
    el = document.createElement('div');
    el.id = 'dm-note';
    el.className = 'dm-note';
    el.innerHTML = '<b>PRESENTER</b><span>Live from the engine: the rule set, dataset facts, field requirements, policy values ' +
      'and replay timings. Anything under a PREVIEW tag is inert: nothing leaves the browser, a chosen file is never ' +
      'read, and none of it changes a figure on another screen.</span>';
    var strip = document.querySelector('.demostrip');
    if (strip) strip.after(el);
  }

  box.addEventListener('change', function (e) {
    var t = e.target;
    if (t.name === 'dm-role') D.role = t.value;
    else if (t.getAttribute('data-dm') === 'presenter') D.presenter = t.checked;
    else if (t.getAttribute('data-dm') === 'stage') D.stage = t.value;
    else if (t.getAttribute('data-dm') === 'renewal') D.renewal = t.checked;
    save(); draw(); publish();
  });
  document.addEventListener('click', function (e) { if (box.open && !box.contains(e.target)) box.open = false; });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && box.open) { box.open = false; box.querySelector('summary').focus(); }
  });

  var style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);
  var anchor = document.getElementById('specbtn');
  if (anchor) anchor.before(box); else document.querySelector('.topbar').appendChild(box);
  draw();
  publish();
})();
