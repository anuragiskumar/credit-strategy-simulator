/* Spec notes for admin.html. Loaded after settings_notes.js, whose shell notes the page also uses;
 * no key may appear in both files.
 *
 * The licence's term and renewal stages are explained here and nowhere on a screen: they are
 * contract terms that differ by client (a longer grace for a client who pays yearly, an extra stage
 * for another), and they are read from each client's signed licence file.
 */
window.__ADMIN_NOTES__ = function (F) {
  'use strict';
  var L = F.simulated.licence;
  var stages = L.ladder.map(function (s, i) {
    return s.label + (i === 0 ? '' : ' from ' + s.from) + ': ' + s.does;
  }).join(' ');

  return {
    ad_head: {
      t: 'Administration',
      d: 'How the installed product is licensed, fed, secured and maintained. Only for administrators: in the deployed ' +
         'product the server decides from the signed-in user\'s attributes and refuses these actions for anyone else. ' +
         'Everything here is a preview. It looks and reads as the real thing would but does nothing, and carries one ' +
         'PREVIEW tag for the page. Nothing here changes a figure on any other screen.'
    },
    ad_refused: {
      t: 'No access',
      d: 'What someone who is not an administrator sees if they open this page directly. The server would refuse every ' +
         'action here anyway; this message only says so plainly.'
    },

    /* ------------------------------------------------------------ licence */
    lic_head: {
      t: 'Licence',
      d: 'The licence is a signed file checked offline; there is no server to call. Only administrators see it. Everyone ' +
         'else meets the licence only as a paused action with a plain message, never as a date. Term and renewal are ' +
         'contract terms and differ by client, so the stages are read from each client\'s licence file and are not shown ' +
         'on screen. In this demo licence: ' + stages + ' In every stage, client data is never deleted and export is ' +
         'never blocked. Simulated.'
    },
    lic_status: {
      t: 'Status and validity',
      d: 'The current stage, when the licence runs to and how long is left. The days remaining are worked out by the ' +
         'export, never on the page. When a stage pauses something, the reason is shown here.'
    },
    lic_refresh: {
      t: 'Refresh',
      d: 'Re-reads the licence store and re-verifies the signature. It cannot ask anyone whether a payment arrived, ' +
         'because the deployed product has no outbound internet. After payment Azentio issues a new signed file and ' +
         'refresh picks it up.'
    },
    lic_apply: {
      t: 'Apply licence file',
      d: 'For a renewed licence delivered as a file rather than through the patch channel. The file is checked against ' +
         'the Azentio public key held in the product. In this demo the file is not read.'
    },
    lic_ent: {
      t: 'Entitlements',
      d: 'What the licence covers: product, modules, environments and named users. Simulated.'
    },
    lic_sig: {
      t: 'Signature',
      d: 'Every licence file is signed by Azentio and verified offline, so it cannot be edited to extend the term. ' +
         'The fingerprint identifies which key signed it.'
    },
    lic_rem: {
      t: 'Renewal reminders',
      d: 'Who is told, and how many days before expiry, so a renewal is never a surprise. Sent by the bank\'s own mail relay.'
    },

    /* ------------------------------------------------------------ data source */
    ds_admin: {
      t: 'Data source',
      d: 'Where the applications come from. The demo runs on a generated population; the deployed product reads a file ' +
         'or connects to the bank\'s own database. What the data looks like is on Settings.'
    },
    ds_src: {
      t: 'Source',
      d: 'Current dataset: what the analysis runs on now. The other four are simulated: a file upload, and read-only ' +
         'connections to Oracle, PostgreSQL and MySQL.'
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

    /* ------------------------------------------------------------ mapping and rules */
    mp_admin: {
      t: 'Field mapping',
      d: 'Which source column supplies each field the rules read. Everyone who works with data sees the result, ' +
         'read-only, on Settings; only an administrator edits it.'
    },
    mp_example: {
      t: 'Example bank layout',
      d: 'An illustration of a real database with its own column names, and what happens when some required fields ' +
         'are not mapped. It is not the client\'s schema, which has not arrived. Simulated.'
    },
    rp_upload: {
      t: 'Load a rule workbook',
      d: 'Where a new rule pack is loaded. The deployed product parses every table, reports rules it cannot evaluate, and ' +
         'keeps the old pack until a risk approver accepts the new one. In the demo a chosen file is never read; only its ' +
         'name is shown. Simulated.'
    },

    /* ------------------------------------------------------------ the rest */
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
    vr_head: {
      t: 'Versions and updates',
      d: 'What is installed and when it last changed. Updates arrive through an encrypted patch channel signed by Azentio ' +
         'and do not overwrite the bank\'s configuration. Simulated.'
    },
    dg_head: {
      t: 'Diagnostics and export',
      d: 'A support bundle with no applicant data, for reporting a problem to Azentio when there is no remote access, and ' +
         'exports of configuration. Results exports belong on the analysis screens. Export works in every licence ' +
         'state. Simulated.'
    }
  };
};
