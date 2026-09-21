/* What the signed-in person may do. The only place a screen asks.
 *
 * A screen never checks a role. It asks Session.can('<action>'), and draws only what comes back
 * true. In the deployed product the answer comes from the server's policy decision (attribute-based
 * access control): the server refuses the action whatever the screen draws, and this file only
 * keeps the screen from offering what would be refused. Hiding a control here is presentation,
 * not security.
 *
 * Nothing in this file knows a role name. Until the server exists, a provider supplies the state:
 * in the demo that is demo_bar.js. With no provider at all, nothing is allowed beyond what every
 * signed-in person sees, so a missing provider fails closed.
 *
 * State, as a provider sets it:
 *   can      actions this person may take, e.g. 'data.view', 'recompute.run', 'admin.view'
 *   paused   actions the current licence stage pauses for everyone, e.g. 'recompute.run'
 *   licence  the licence snapshot, only for someone allowed 'licence.view'; otherwise null
 *   who      a display label for the person, or ''
 *
 * Actions the screens use:
 *   data.view       applicant data facts and the field mapping (read-only)
 *   recompute.run   start a recompute
 *   policy.propose  propose a new risk-appetite value (the maker)
 *   policy.approve  approve or reject someone else's proposal (the checker)
 *   assumptions.change  change a replay assumption
 *   audit.view      the audit log
 *   admin.view      the Administration screen
 *   licence.view    licence status and entitlements
 *   assistant.use   the Simulator's Ask view: requests in plain words, sent to a language model
 *   data.load, rules.load, config.change, analysis.view   used by licence pauses
 */
(function () {
  'use strict';

  var state = { can: [], paused: [], licence: null, who: '' };
  var handlers = { refreshLicence: null, applyLicence: null };
  var listeners = [];

  function has(list, a) { return list.indexOf(a) >= 0; }

  window.Session = {
    can: function (action) { return has(state.can, action); },
    paused: function (action) { return has(state.paused, action); },
    licence: function () { return state.licence; },
    who: function () { return state.who; },

    /** A provider (the server, or demo_bar.js in the demo) replaces the whole state at once. */
    set: function (next) {
      state = {
        can: (next && next.can) || [], paused: (next && next.paused) || [],
        licence: (next && next.licence) || null, who: (next && next.who) || ''
      };
      listeners.forEach(function (fn) { fn(); });
    },
    /** A provider answers the licence actions; with none, they report that nothing changed. */
    handle: function (h) { Object.keys(handlers).forEach(function (k) { if (h[k]) handlers[k] = h[k]; }); },
    refreshLicence: function (done) {
      if (handlers.refreshLicence) handlers.refreshLicence(done); else done({ found: false });
    },
    applyLicence: function (name, done) {
      if (handlers.applyLicence) handlers.applyLicence(name, done); else done({ applied: false });
    },
    /** Screens redraw on change: a different person, or a licence stage that pauses something. */
    onChange: function (fn) { listeners.push(fn); }
  };
})();
