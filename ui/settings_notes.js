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
  var R = F.run || {}, D = F.dataset || {}, T = F.rulepack.totals;

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
      d: 'What the analysis runs on, read from the engine: the rule set, policy values, the last run and, for those who ' +
         'work with data, the applicant table and field mapping. Every signed-in person sees this page; what they see on ' +
         'it depends on their role. The licence and platform items are on Administration, for administrators only.'
    },
    ready: {
      t: 'Readiness',
      d: 'Three tiles that answer "is this set up?" at a glance. Each one is explained below.'
    },
    t_rules: {
      t: 'Rule set tile',
      d: count(R.rules_replayed) + ' rules were replayed against every applicant, out of ' + count(T.rules) +
         ' rows across ' + count(T.files) + ' workbooks. The difference is rules for other products, lookup rows and rules ' +
         'switched off. Counted.'
    },
    t_data: {
      t: 'Applicant data tile',
      d: 'How many applicants the analysis ran on and the period they cover. In the demo these are generated; the ' +
         'strip at the top of every screen says so. Counted.'
    },
    t_fields: {
      t: 'Field coverage tile',
      d: 'How many of the fields the rules require the applicant table supplies. A rule cannot be evaluated on a field ' +
         'that is missing. Counted.'
    },

    /* ------------------------------------------------------------ rule set */
    rp_head: {
      t: 'Rule set',
      d: 'The decision tables the bank supplied. Each workbook holds one or more tables; each table row is one rule: ' +
         'conditions on an applicant that end in a decline, a pass, or a cap on the amount offered. Counted. An ' +
         'administrator loads new workbooks on Administration.'
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
    rp_uneval: {
      t: 'Rules not evaluated',
      d: 'A rule that names a field the applicant data does not carry. It is named here rather than silently treated as ' +
         'a rule that never fires, which would hide a gap. Field mapping shows which value is missing.'
    },

    /* ------------------------------------------------------------ policy */
    po_head: {
      t: 'Policy and risk appetite',
      d: 'The numbers a risk committee owns, read from the engine\'s configuration. The page shows them and does not ' +
         'edit them, because changing one is a committee decision followed by a recompute. In the deployed product an ' +
         'analyst proposes a change and a risk approver accepts it.'
    },
    po_assume: {
      t: 'Replay assumptions',
      d: 'The rule files say what each rule tests but not how rules combine or what happens to an applicant no rule ' +
         'catches. ' + count(F.policy.assumptions.length) + ' assumptions fill that gap. Each is still to be confirmed ' +
         'with the client, and the funnel moves when one changes. Raise them in the meeting; the page states them neutrally.'
    },
    po_hard: {
      t: 'Never relaxed',
      d: 'Rules resting on a regulatory or staff fact are never offered as a relaxation, whatever they cost in approvals. ' +
         'Code can measure what a rule costs; it cannot know a bank may drop it. Hover a check for the engine field.'
    },
    po_levers: {
      t: 'Thresholds the optimiser may move',
      d: 'The thresholds the optimiser is allowed to move when it searches for a strategy, and the size of each move. ' +
         'Hover a row for the engine field it moves.'
    },

    /* ------------------------------------------------------------ run */
    rn_head: {
      t: 'Run and data quality',
      d: 'What the last analysis run looked like and whether the data behaved. The counts and the timing are measured, ' +
         'not quoted.'
    },
    rn_never: {
      t: 'Rules that catch nobody',
      d: 'Out of ' + count(R.rules_replayed) + ' replayed rules, ' + count(R.never_fire_count) + ' matched no applicant. ' +
         'Either the rule is redundant or it reads a field the data never populates. On a real book this list is the ' +
         'first thing to check.'
    },
    rn_nulls: {
      t: 'Fields with missing values',
      d: 'A missing bureau score is not a blank to fill in: those applicants are a segment of their own, and about a hundred ' +
         'rules test the score.'
    },
    rn_recompute: {
      t: 'Recompute',
      d: 'Reruns the analysis after the data, the rules or a policy value changes. Shown to analysts. The real run takes ' +
         'minutes and works as a background job. When the licence stage pauses recomputes, the button is disabled with ' +
         'a plain message and no licence dates. Simulated.'
    },

    /* ------------------------------------------------------------ applicant data */
    ds_head: {
      t: 'Applicant data',
      d: 'The applicant table the analysis runs on. Shown to those who work with data: analysts, risk approvers and ' +
         'administrators. Where it comes from is managed on Administration.'
    },
    ds_demo: {
      t: 'Demo dataset facts',
      d: count(D.rows) + ' generated applicants. No figure on any screen describes a real customer. Counted from the table.'
    },
    ds_preview: {
      t: 'Example rows',
      d: 'A few rows from the source, with personal fields masked in the deployed product. In the demo they come from ' +
         'the generated table; for a simulated connection they are the same example rows.'
    },

    /* ------------------------------------------------------------ mapping */
    mp_head: {
      t: 'Field mapping',
      d: 'Every field the engine reads, what kind it is, how many rules need it, and which source column supplies it. ' +
         'This is the list a bank\'s data team works from. Read-only here; an administrator edits it on Administration. ' +
         'Counted from the rules.'
    },
    mp_need: {
      t: 'Need',
      d: 'Required: read by at least one rule that applies. Needed for the funnel: the walk-away outcome. Recommended: ' +
         'used by the analysis, not by a rule. Columns that exist only in the synthetic data are not listed.'
    },
    mp_unsupplied: {
      t: 'Not supplied',
      d: 'A rule that names data the applicant table does not carry. It cannot be evaluated until the data is supplied. ' +
         'The value is often a whole expression over the bureau record, so the page names it in a tooltip on "derived value".'
    },

    /* ------------------------------------------------------------ audit */
    au_head: {
      t: 'Audit log',
      d: 'Who did what and when: uploads, runs, configuration changes and access decisions. Shown to risk approvers and ' +
         'administrators, because governance is part of their job. Simulated.'
    }
  };
};
