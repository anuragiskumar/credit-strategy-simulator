/* The shell for the standalone pages (settings.html, admin.html): the rail, the synthetic-data
 * strip, spec notes, theme and the phone menu. client.html has its own shell in client.js; the two
 * look the same and link to each other.
 *
 * A page hands over four things: what it draws, which sections it has (for the rail), its spec
 * notes, and an optional click handler. The shell redraws the page when Session changes, so a
 * different person, or a licence stage that pauses something, shows at once.
 */
(function () {
  'use strict';

  var K = window.SettingsKit, esc = K.esc, N = K.N;
  var F = window.__SETTINGS__;
  var P = null;                 // the page handed to start()
  var spec = false;
  var spy = null;

  // The analysis screens live in client.html; the hash opens the right one.
  var SCREENS = [
    { id: 'portfolio', t: 'Portfolio', href: 'client.html#portfolio' },
    { id: 'drivers', t: 'Decline drivers', href: 'client.html#drivers' },
    { id: 'simulator', t: 'Simulator', href: 'client.html#simulator' },
    { id: 'settings', t: 'Settings', href: 'settings.html' },
    { id: 'administration', t: 'Administration', href: 'admin.html', need: 'admin.view' }
  ];

  var rail = document.getElementById('rail');
  var canvas = document.getElementById('canvas');
  var wrap = document.getElementById('canvaswrap');
  var scrim = document.getElementById('scrim');

  function renderRail() {
    var secs = P.sections();
    var groups = {};
    var order = [];
    secs.forEach(function (s) {
      var g = s.group || 'On this page';
      if (!groups[g]) { groups[g] = []; order.push(g); }
      groups[g].push(s);
    });
    rail.innerHTML =
      '<div class="railgroup"><h4' + N('sh_screens') + '>Screens</h4>' + SCREENS.filter(function (s) {
        return !s.need || window.Session.can(s.need);
      }).map(function (s, i) {
        return '<a class="navitem" href="' + s.href + '"' + (s.id === P.id ? ' aria-current="page"' : '') + '>' +
          '<span class="n">' + (i + 1) + '</span><span class="lbl">' + esc(s.t) + '</span></a>';
      }).join('') + '</div>' +
      order.map(function (g, i) {
        return '<div class="railgroup"><h4' + (i === 0 ? N('sh_sections') : '') + '>' + esc(g) + '</h4>' + groups[g].map(function (s) {
          return '<button type="button" class="navitem" data-jump="' + s.id + '"><span class="lbl">' + esc(s.t) + '</span></button>';
        }).join('') + '</div>';
      }).join('') +
      '<div class="railgroup"><h4' + N('sh_tags') + '>Tags</h4><div style="padding:6px 10px;display:flex;flex-direction:column;gap:6px;align-items:flex-start">' +
      K.pv('OBSERVED') + K.sim() + '</div></div>';
  }

  function draw(keepScroll) {
    var at = canvas.scrollTop;
    wrap.innerHTML = P.render();
    canvas.scrollTop = keepScroll ? at : 0;
    renderRail();
    watch();
    applySpec();
  }

  /** Replace one section in place, keeping the scroll and any open state the page tracks. */
  function update(id, html) {
    var el = document.getElementById('sec-' + id);
    if (!el) return;
    var t = document.createElement('div');
    t.innerHTML = html;
    var fresh = t.firstChild;
    el.replaceWith(fresh);
    if (spy) spy.observe(fresh);
    applySpec();
  }

  /* ------------------------------------------------------------ navigation within the page */
  function jump(id) {
    var el = document.getElementById('sec-' + id);
    if (!el) return;
    var calm = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (el.tagName === 'DETAILS') el.open = true;
    el.scrollIntoView({ block: 'start', behavior: calm ? 'auto' : 'smooth' });
    mark(id);
  }
  function mark(id) {
    rail.querySelectorAll('[data-jump]').forEach(function (a) {
      if (a.getAttribute('data-jump') === id) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
    });
  }
  function watch() {
    if (spy) spy.disconnect();
    spy = null;
    if (!('IntersectionObserver' in window)) return;
    spy = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) mark(en.target.id.replace('sec-', '')); });
    }, { root: canvas, rootMargin: '-15% 0px -75% 0px' });
    wrap.querySelectorAll('[id^="sec-"]').forEach(function (el) { spy.observe(el); });
  }

  /* ------------------------------------------------------------ spec notes */
  // Same behaviour as client.js: off by default; when on, each visible [data-note] gets a number
  // and its note is printed at the foot of the page.
  function badge(n, label, target) {
    var b = document.createElement('span');
    b.className = 'specnum';
    b.textContent = n;
    b.tabIndex = 0;
    b.setAttribute('role', 'link');
    b.setAttribute('aria-label', label);
    function go() {
      var el = target();
      if (!el) return;
      var calm = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      el.scrollIntoView({ block: 'center', behavior: calm ? 'auto' : 'smooth' });
      el.classList.remove('is-flash'); void el.offsetWidth; el.classList.add('is-flash');
    }
    b.addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); go(); });
    b.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); go(); } });
    return b;
  }
  function applySpec() {
    document.querySelectorAll('.specnum, #specnotes').forEach(function (el) { el.remove(); });
    document.getElementById('specbtn').setAttribute('aria-pressed', spec ? 'true' : 'false');
    if (!spec) return;
    var notes = P.notes();
    var order = [], number = {}, first = {};
    document.querySelectorAll('[data-note]').forEach(function (el) {
      var key = el.getAttribute('data-note');
      if (!notes[key] || !el.getClientRects().length) return;
      if (!(key in number)) { order.push(key); number[key] = order.length; }
      var n = number[key];
      var b = badge(n, 'Spec note ' + n + ': ' + notes[key].t, function () { return document.getElementById('specnote-' + n); });
      el.appendChild(b);
      if (!(key in first)) first[key] = b;
    });
    if (!order.length) return;
    var sec = document.createElement('section');
    sec.id = 'specnotes';
    sec.className = 'specnotes';
    sec.setAttribute('aria-label', 'Spec notes');
    sec.innerHTML = '<h3>Spec notes</h3><p class="specsub">What each numbered item on this screen is, and what it stands for. ' +
      'Click a number to jump between the item and its note.</p>';
    order.forEach(function (key) {
      var row = document.createElement('div');
      row.className = 'specrow';
      row.id = 'specnote-' + number[key];
      var text = document.createElement('div');
      text.innerHTML = '<b></b><p></p>';
      text.firstChild.textContent = notes[key].t;
      text.lastChild.textContent = notes[key].d;
      row.appendChild(badge(number[key], 'Back to item ' + number[key], function () { return first[key]; }));
      row.appendChild(text);
      sec.appendChild(row);
    });
    wrap.appendChild(sec);
  }

  /* ------------------------------------------------------------ phone menu */
  function toggleRail(force) {
    var open = force === undefined ? !rail.classList.contains('is-open') : force;
    rail.classList.toggle('is-open', open);
    scrim.classList.toggle('is-open', open);
    if (spec) applySpec();
  }

  function start(page) {
    P = page;
    document.getElementById('demostriptext').textContent =
      K.n0(F.dataset.rows) + ' generated applicants · ' + K.n0(F.run.rules_replayed) +
      ' real rules replayed · figures are illustrative, the rules and the method are real';
    document.getElementById('productchip').innerHTML = '<span class="fig">' + esc(F.meta.product) + '</span>';

    document.getElementById('specbtn').addEventListener('click', function () { spec = !spec; applySpec(); });
    document.getElementById('themebtn').addEventListener('click', function () {
      var cur = document.documentElement.getAttribute('data-theme');
      document.documentElement.setAttribute('data-theme', cur === 'dark' ? 'light' : 'dark');
    });
    document.getElementById('railbtn').addEventListener('click', function () { toggleRail(); });
    scrim.addEventListener('click', function () { toggleRail(false); });
    window.addEventListener('resize', function () {
      if (!spec) return;
      clearTimeout(applySpec.t);
      applySpec.t = setTimeout(applySpec, 150);
    });

    rail.addEventListener('click', function (e) {
      var j = e.target.closest('[data-jump]');
      if (j) { e.preventDefault(); jump(j.getAttribute('data-jump')); toggleRail(false); }
    });
    wrap.addEventListener('click', function (e) {
      if (P.click && P.click(e)) return;
      var j = e.target.closest('[data-jump]');
      if (j) { e.preventDefault(); jump(j.getAttribute('data-jump')); }
    });
    // <details> does not bubble its toggle event, so listen in the capture phase.
    wrap.addEventListener('toggle', function (e) {
      var d = e.target;
      if (d.hasAttribute && d.hasAttribute('data-acc')) { if (P.toggled) P.toggled(d.getAttribute('data-acc'), d.open); applySpec(); }
    }, true);
    if (P.change) wrap.addEventListener('change', P.change);
    if (P.input) wrap.addEventListener('input', P.input);

    window.Session.onChange(function () { draw(true); });
    draw(false);
    if (location.hash.indexOf('#sec-') === 0) jump(location.hash.slice(5));
  }

  window.PageShell = { start: start, draw: draw, update: update, refreshSpec: applySpec, jump: jump };
})();
