/* Spec notes for the Settings page of client.html: what each element on screen is and what it stands for.
 *
 * settings.js and client.html tag an element with data-note="<key>"; when the spec-notes icon is on,
 * client.js merges these entries with client_notes.js, so no key may appear in both. Text only:
 * no arithmetic, and nothing here shows until the icon is pressed.
 *
 * Values that can change with the data or the config (rule counts, applicant counts) are read
 * from the fixture, so a note cannot drift from the screen. Each note says whether the item is
 * counted from the engine or simulated for this demo.
 */
window.__SETTINGS_NOTES__ = function (F) {
  'use strict';
  var count = function (v) { return Number(v).toLocaleString('en-US'); };
  var R = F.run || {}, D = F.dataset || {}, T = F.rulepack.totals;

  return {
    /* ------------------------------------------------------------ frame */
    lic_chip: {
      t: 'Licence chip',
      d: 'The licence state in one line, always visible. It follows the licence panel below. Simulated in the demo.'
    },
    pg_head: {
      t: 'Settings',
      d: 'One page for the things an administrator sets up once and checks after. The top half is what the analysis ' +
         'runs on, read from the engine: the rule set, policy values, the last run, the applicant data and field mapping. ' +
         'The bottom half is how the installed product is run, and is a preview. On the page itself the copy is kept to ' +
         'labels and status; the reasoning behind each item is here.'
    },
    rail_sections: {
      t: 'On this page',
      d: 'Jumps to a section of the Settings page. The Administration group is collapsed by default: it is a preview ' +
         'of the deployed product and rarely needed when reviewing the analysis.'
    },
    dp_head: {
      t: 'Deployment and administration',
      d: 'Licence, outcomes, platform and security, audit, versions and diagnostics: what a deployed product needs beyond ' +
         'the analysis. Everything in this group is a preview. It looks and reads as the real thing would but does ' +
         'nothing, and carries one dashed PREVIEW tag for the whole group rather than one per item. Nothing in it ' +
         'changes a figure on any other screen.'
    },

    /* ------------------------------------------------------------ readiness */
    ready: {
      t: 'Readiness',
      d: 'Four tiles that answer "is this set up?" at a glance. Each one is explained below.'
    },
    t_lic: { t: 'Licence tile', d: 'The date the licence runs to and its state. Simulated.' },
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

    /* ------------------------------------------------------------ licence */
    lic_head: {
      t: 'Licence',
      d: 'The contractual term of the licence, shown in the product so nobody is surprised by it. The licence is a signed ' +
         'file checked offline; there is no server to call. It sits in the Administration group, collapsed, because it ' +
         'is an administrator\'s concern rather than part of the analysis. Simulated.'
    },
    lic_status: {
      t: 'Status and validity',
      d: 'Where the licence is on the ladder below, when it runs to, and how long is left. The days remaining are worked ' +
         'out by the export, never on the page.'
    },
    lic_refresh: {
      t: 'Refresh',
      d: 'Re-reads the licence store and re-verifies the signature. It cannot ask anyone whether a payment arrived, ' +
         'because the deployed product has no outbound internet. After payment the vendor issues a new signed file and ' +
         'refresh picks it up.'
    },
    lic_apply: {
      t: 'Apply licence file',
      d: 'For a renewed licence delivered as a file rather than through the patch channel. The file is checked against ' +
         'the vendor public key held in the product. In this demo the file is not read.'
    },
    lic_ent: {
      t: 'Entitlements',
      d: 'What the licence covers: product, modules, environments and named users. Simulated.'
    },
    lic_sig: {
      t: 'Signature',
      d: 'Every licence file is signed by the vendor and verified offline, so it cannot be edited to extend the term. ' +
         'The fingerprint identifies which key signed it.'
    },
    lic_ladder: {
      t: 'Term and renewal',
      d: 'The stages, in order, and what each one does. The durations are set by the licence agreement; those shown are ' +
         'illustrative. Stating them here is the point: the term and its consequences are agreed and visible.'
    },
    lic_always: {
      t: 'Two things that never change',
      d: 'In every licence state, client data is not deleted and export is not blocked.'
    },
    lic_rem: {
      t: 'Renewal reminders',
      d: 'Who is told, and how many days before expiry, so a renewal is never a surprise. Sent by the bank\'s own mail relay.'
    },

    /* ------------------------------------------------------------ rule set */
    rp_head: {
      t: 'Rule set',
      d: 'The decision tables the bank supplied. Each workbook holds one or more tables; each table row is one rule: ' +
         'conditions on an applicant that end in a decline, a pass, or a cap on the amount offered. Counted.'
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
    rp_upload: {
      t: 'Load a rule workbook',
      d: 'Where a new rule pack is loaded. The deployed product parses every table, reports rules it cannot evaluate, and ' +
         'keeps the old pack until the new one is accepted. In the demo a chosen file is never read; only its name is ' +
         'shown. Simulated.'
    },

    /* ------------------------------------------------------------ applicant data */
    ds_head: {
      t: 'Applicant data',
      d: 'Where the applications come from. The demo uses a generated population; the deployed product reads a file or ' +
         'connects to the bank\'s own database.'
    },
    ds_src: {
      t: 'Source',
      d: 'Demo dataset: what the demo runs on, counted. The other four are simulated: a file upload, and read-only ' +
         'connections to Oracle, PostgreSQL and MySQL.'
    },
    ds_demo: {
      t: 'Demo dataset facts',
      d: count(D.rows) + ' generated applicants. No figure on any screen describes a real customer. Counted from the table.'
    },
    ds_form: {
      t: 'Connection',
      d: 'The fields change with the database type: Oracle takes a service name, PostgreSQL and MySQL a database name. ' +
         'Port and transport security have the type\'s usual defaults.'
    },
    ds_auth: {
      t: 'Authentication',
      d: 'A vault reference is recommended: the credential lives in the bank\'s secrets store and is never typed into a ' +
         'browser. The password option exists for estates without a vault. In the demo the password field is inert: it ' +
         'is not read, stored or sent.'
    },
    ds_extract: {
      t: 'What to read',
      d: 'A table or view, or a query, filtered to the product and to a window of application dates, refreshed manually or ' +
         'on a schedule. The account should be read-only; the product never writes to the source.'
    },
    ds_test: {
      t: 'Test connection',
      d: 'Walks through reaching the host, securing the channel, authenticating, confirming the account is read-only, ' +
         'finding the object and counting rows, and stops at the first failure. In the demo nothing is contacted; ' +
         'a blank host or a bad port fails for real so the validation can be seen.'
    },
    ds_preview: {
      t: 'Example rows',
      d: 'A few rows from the connected source, with personal fields masked in the deployed product. Shown for the ' +
         'demo dataset from the generated table; for a simulated connection they are the same example rows.'
    },

    /* ------------------------------------------------------------ mapping */
    mp_head: {
      t: 'Field mapping',
      d: 'Every field the engine reads, what kind it is, how many rules need it, and which source column supplies it. ' +
         'This is the list a bank\'s data team works from. Counted from the rules.'
    },
    mp_need: {
      t: 'Need',
      d: 'Required: read by at least one rule that applies. Needed for the funnel: the walk-away outcome. Recommended: ' +
         'used by the analysis, not by a rule. Not requested: exists only in the synthetic data.'
    },
    mp_unsupplied: {
      t: 'Not supplied',
      d: 'A rule that names data the applicant table does not carry. It cannot be evaluated until the data is supplied. ' +
         'The value is often a whole expression over the bureau record, so the page names it in a tooltip on "derived value".'
    },
    mp_example: {
      t: 'Example bank layout',
      d: 'An illustration of a real database with its own column names, and what happens when some required fields ' +
         'are not mapped. It is not the client\'s schema, which has not arrived. Simulated.'
    },

    /* ------------------------------------------------------------ policy */
    po_head: {
      t: 'Policy and risk appetite',
      d: 'The numbers a risk committee owns, read from the engine\'s configuration. The page shows them and does not ' +
         'edit them, because changing one is a committee decision followed by a recompute.'
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
         'Code can measure what a rule costs; it cannot know a bank may drop it.'
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
      d: 'Reruns the analysis after the data, the rules or a policy value changes. The real run takes minutes and works ' +
         'as a background job. Simulated.'
    },

    /* ------------------------------------------------------------ accordions */
    oc_head: {
      t: 'Outcomes and performance',
      d: 'How a loan is called bad, and where the repayment history comes from. Real data has no ground truth for declined ' +
         'applicants. In the demo the bad flag is generated with the applicants, so every bad rate on the analysis ' +
         'screens is a property of the synthetic population. Simulated.'
    },
    oc_recon: {
      t: 'Reconciliation',
      d: 'The bank\'s actual decision is compared with the replay, application by application. A difference means the rules ' +
         'were read differently, and it is better found here than by a customer.'
    },
    gv_head: {
      t: 'Platform, access and security',
      d: 'Deployment, sign-in, roles, data protection and the language model. The deployed product runs inside the bank\'s ' +
         'estate with no outbound internet, and the language model only translates a question into an engine call; it ' +
         'never computes a figure. Simulated.'
    },
    au_head: {
      t: 'Audit log',
      d: 'Who did what and when: uploads, runs, configuration changes. Simulated.'
    },
    vr_head: {
      t: 'Versions and updates',
      d: 'What is installed and when it last changed. Updates arrive through an encrypted, vendor-signed patch channel and ' +
         'do not overwrite the bank\'s configuration. Simulated.'
    },
    dg_head: {
      t: 'Diagnostics and export',
      d: 'A support bundle with no applicant data, for reporting a problem when there is no remote access, and exports of ' +
         'results and configuration. Export works in every licence state. Simulated.'
    }
  };
};
