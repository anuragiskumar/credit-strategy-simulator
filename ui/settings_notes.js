/* Spec notes for settings.html, and for the shell both standalone pages share (page_shell.js).
 *
 * settings.js tags an element with data-note="<key>"; when the spec-notes icon is on, every tagged
 * element gets a number and the matching entry below is printed as a footnote. admin.html loads
 * this file too and adds admin_notes.js on top, so no key may appear in both. Text only: no
 * arithmetic, and nothing here shows until the icon is pressed.
 *
 * This is where the reasoning lives. The page itself keeps to labels and plain status.
 */
window.__SETTINGS_NOTES__ = function (F) {
  'use strict';
  var count = function (v) { return Number(v).toLocaleString('en-US'); };
  var R = F.run || {}, T = F.rulepack.totals;

  return {
    /* ------------------------------------------------------------ shell */
    sh_strip: {
      t: 'Synthetic applicants, real rules',
      d: 'The rules and the method are real. The applicants are generated, so every figure is illustrative and none ' +
         'comes from any client book.'
    },
    sh_screens: {
      t: 'Screens',
      d: 'The analysis screens, Settings, and Administration. Administration is listed only for someone allowed to ' +
         'administer the product. In the deployed product that is decided by the server from the signed-in user\'s ' +
         'attributes, and the server refuses the action whatever the screen shows.'
    },
    sh_sections: {
      t: 'On this page',
      d: 'Jumps to a section of this page. The list changes with who is signed in, because the page shows each person ' +
         'only the sections their role uses.'
    },
    sh_tags: {
      t: 'Tags',
      d: 'OBSERVED means the figure is counted from the engine. PREVIEW marks something the deployed product does that ' +
         'is inert here: it looks and reads as the real thing would, but nothing leaves the browser and nothing changes ' +
         'a figure. PREVIEW is deliberately not a colour: colour on these screens means how much we know about a number.'
    },

    /* ------------------------------------------------------------ page */
    pg_head: {
      t: 'Settings',
      d: 'What the analysis runs on, and the values the risk committee owns. Every signed-in person sees this page; what ' +
         'each one may change on it depends on their role. The licence, the data source, the rule workbooks and the ' +
         'audit log are on Administration, for administrators only.'
    },
    pg_tabs: {
      t: 'Four tabs',
      d: 'Analysis: what the figures cover. Risk appetite: the bad-rate ceiling and the values under it, changed by one ' +
         'person and approved by another. Replay assumptions: what the replay does where the rule files are silent, with ' +
         'what each decides. Data health: what the data cannot answer.'
    },

    /* ------------------------------------------------------------ analysis */
    an_head: {
      t: 'What the figures cover',
      d: 'The product and period this person is looking at, the bad definition every bad rate is read against, the rule ' +
         'pack (one line: ' + count(T.rules) + ' rules from ' + count(T.files) + ' workbooks; the table-by-table inventory ' +
         'is on Administration), and when the figures were computed. The rule pack version is a fingerprint of the ' +
         'workbooks: it changes whenever any of them does, so two sets of figures can be checked against the same rules.'
    },
    an_choose: {
      t: 'Product and period',
      d: 'The same choice as the period control at the top of every analysis screen, kept in this browser. It is each ' +
         'person\'s own view: it changes nothing anyone else sees, so it needs no approval. Custom ranges and a different ' +
         'performance window are chosen on the analysis screens, where the engine works them out.'
    },
    an_recompute_head: {
      t: 'Recompute',
      d: 'Rebuilds every figure on the rules, the data and the approved settings. An approved value changes nothing until ' +
         'this runs, so a figure is never read as if it already used a value it does not. With the engine running this is ' +
         'real: the engine rebuilds in the background and swaps the new figures in when they are ready.'
    },
    an_recompute: {
      t: 'Recompute button',
      d: 'Shown to analysts and risk approvers. When the licence stage pauses recomputes, the button is disabled with a ' +
         'plain message and no licence dates. The worked-out figures used without the engine are refreshed by the export.'
    },
    gv_waiting: {
      t: 'Approved, not applied',
      d: 'An approved value waits for the next recompute. Until then every screen still shows figures computed on the ' +
         'old value, and this line says which values are waiting.'
    },

    /* ------------------------------------------------------------ risk appetite */
    ra_head: {
      t: 'Bad-rate ceiling',
      d: 'The one number that bounds every recommendation: goal-seek never proposes a strategy above it, and the ' +
         'Simulator flags a scenario that breaches it. Without it, "maximise approvals" is solved by approving everyone.'
    },
    ra_ceiling: {
      t: 'The value in force',
      d: 'The approved value, or the configuration file\'s where nothing has been approved. The line below says who ' +
         'approved it and when, and whether the figures use it yet.'
    },
    ra_pending: {
      t: 'Waiting for approval',
      d: 'Maker and checker. One person proposes a value with a reason; a different person approves or rejects it. The ' +
         'engine refuses an approval from the person who proposed the change, whatever the screen shows, and allows ' +
         'only one open proposal per setting. The proposer may withdraw it.'
    },
    ra_propose: {
      t: 'Propose a change',
      d: 'Shown to analysts. The engine checks the value is in range and that the setting has not moved since, and ' +
         'records the proposal with who and when. Nothing changes until someone else approves it and a recompute runs.'
    },
    ra_advanced: {
      t: 'Advanced',
      d: 'The multiples that class swap-ins as riskier or safer and decide whether a rule earns its place. Same maker and ' +
         'checker route as the ceiling. Kept under Advanced because a committee rarely moves them.'
    },
    ra_history: {
      t: 'Changes',
      d: 'Every proposal, approval, rejection, withdrawal and direct change, newest first, with who and when. Nothing is ' +
         'ever removed from it: the history of a value is its audit. Until sign-in is built, "who" is the name the ' +
         'signed-in role sends; the field is where the single sign-on identity goes.'
    },
    ra_other: {
      t: 'Other values',
      d: 'Values the analysis uses that are set in the configuration file only: the risk model\'s minimums, the ' +
         'portfolio thresholds and the product limits.'
    },
    po_head: {
      t: 'What the optimiser may touch',
      d: 'Two lists that bound the search, set in the configuration file.'
    },
    po_hard: {
      t: 'Never relaxed',
      d: 'Rules resting on a regulatory or staff fact are never offered as a relaxation, whatever they cost in approvals. ' +
         'Code can measure what a rule costs; it cannot know a bank may drop it. Hover a check for the engine field.'
    },
    po_levers: {
      t: 'What goal-seek may move',
      d: 'The thresholds goal-seek may move when it searches for a strategy, and the size of each move. Hover a row for ' +
         'the engine field it moves.'
    },

    /* ------------------------------------------------------------ replay assumptions */
    as_head: {
      t: 'Replay assumptions',
      d: 'The rule files say what each rule tests, not what to do where they are silent. These fill the gap. Each is a ' +
         'decision, not a fact, and each is an open question with the bank. Only the risk approver changes one; the ' +
         'change is recorded and applies on the next recompute.'
    },
    as_impact: {
      t: 'What it decides',
      d: 'Counted by replaying every application with the switch flipped and comparing who a rule declines. A switch ' +
         'that moves nobody is said to move nobody, so a committee does not spend time on it. Counted on the figures in ' +
         'use, for the product being viewed.'
    },
    as_fixed: {
      t: 'Fixed, not a switch',
      d: 'The configuration file has a setting for this, but the engine never reads it: the rule files only decline, so ' +
         'an applicant no rule catches is approved. It is shown as fixed rather than as a switch that does nothing.'
    },

    /* ------------------------------------------------------------ data health */
    dh_head: {
      t: 'Data health',
      d: 'What the data cannot answer. A rule on a missing field declines no one, which looks exactly like a rule that ' +
         'never fires; this tab says which is which. Counted.'
    },
    dh_fields: {
      t: 'Required fields',
      d: 'How many of the fields the rules require the applicant table supplies.'
    },
    dh_uneval: {
      t: 'Rules not evaluated',
      d: 'A rule that names data the applicant table does not carry. It is named here rather than silently treated as a ' +
         'rule that never fires. The value is often a whole expression over the bureau record, so the page names it in ' +
         'a tooltip on "derived value".'
    },
    rn_never: {
      t: 'Rules that catch nobody',
      d: 'Out of ' + count(R.rules_replayed) + ' replayed rules, ' + count(R.never_fire_count) + ' matched no applicant. ' +
         'Either the rule is redundant or it reads a field the data never populates. The list is on Decline drivers.'
    },
    rn_nulls: {
      t: 'Fields with missing values',
      d: 'A missing bureau score is not a blank to fill in: those applicants are a segment of their own, and about a hundred ' +
         'rules test the score.'
    },
    mp_head: {
      t: 'Fields the rules read',
      d: 'Every field the engine reads, what kind it is, how many rules need it, and how often it is missing. Shown to ' +
         'those who work with data. An administrator edits the mapping on Administration.'
    },
    mp_need: {
      t: 'Need',
      d: 'Required: read by at least one rule that applies. Needed for the funnel: the walk-away outcome. Recommended: ' +
         'used by the analysis, not by a rule. Columns that exist only in the synthetic data are not listed.'
    },

    /* ------------------------------------------------------------ on Administration, shared with it */
    rp_head: {
      t: 'Rule workbooks',
      d: 'The decision tables the bank supplied. Each workbook holds one or more tables; each table row is one rule: ' +
         'conditions on an applicant that end in a decline, a pass, or a cap on the amount offered. Counted. Business ' +
         'users see one line of this on Settings.'
    },
    rp_table: {
      t: 'Table',
      d: 'A decision table inside a workbook. A workbook can hold several, and the analysis treats each separately.'
    },
    rp_role: {
      t: 'Role',
      d: 'A decision table is replayed. A lookup is not a rule: it is a list, such as the employer keywords, that rules read. ' +
         '"Not replayed" means no rule in the table applies to ' + F.rulepack.product + '.'
    },
    rp_scope: {
      t: 'In scope',
      d: 'Rules that apply to ' + F.rulepack.product + ' and are switched on. Only these are replayed.'
    },
    ds_preview: {
      t: 'Example rows',
      d: 'A few rows from the source, with personal fields masked in the deployed product. In the demo they come from ' +
         'the generated table; for a simulated connection they are the same example rows.'
    },
    au_head: {
      t: 'Audit log',
      d: 'Who did what and when across the product: uploads, runs and access decisions. A preview. Changes to the risk ' +
         'appetite and the replay assumptions are recorded for real, on Settings.'
    }
  };
};
