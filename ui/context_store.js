/* The product and period this viewer is looking at: the one place it is kept.
 *
 * client.html sets it from the period control on every analysis screen; Settings shows it on the
 * Analysis tab and lets it be changed there too. It is a per-viewer convenience held in this
 * browser: it changes what this person sees and nothing anyone else sees, so it is not a governed
 * setting and needs no approval. A private window or blocked storage just starts on the default.
 *
 *   { product: 'TWQR', preset: 'last_12m' | null, window: { app_from, app_to, performance_months } }
 */
(function () {
  'use strict';
  var KEY = 'cso.context';
  window.AnalysisContext = {
    read: function () {
      try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (e) { return null; }
    },
    write: function (ctx) {
      try { localStorage.setItem(KEY, JSON.stringify(ctx)); return true; } catch (e) { return false; }
    }
  };
})();
