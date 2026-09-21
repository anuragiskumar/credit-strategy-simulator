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
      d: 'For the bank\'s IT or application administrator: is it healthy, is data flowing, who has access, and does ' +
         'anything need me? Only for administrators: in the deployed product the server decides from the signed-in ' +
         'user\'s attributes and refuses these actions for anyone else. Most of it is a preview and carries one PREVIEW ' +
         'tag for the page. Real: the data in use, its field mapping and bad definition, the rule workbooks, and the ' +
         'settings changes and recompute in the audit log. Nothing here changes a figure on any other screen.'
    },
    ad_refused: {
      t: 'No access',
      d: 'What someone who is not an administrator sees if they open this page directly. The server would refuse every ' +
         'action here anyway; this message only says so plainly.'
    },

    /* ------------------------------------------------------------ tabs and overview */
    ad_tabs: {
      t: 'Tabs',
      d: 'Overview · Data · Users & access · Audit log · System · Licence, in the order an administrator works. The ' +
         'licence is last: it is rarely the task, and the overview raises it when it is. The audit log needs audit.view ' +
         'and the licence licence.view, so a tab someone may not see is not drawn.'
    },
    ov_head: {
      t: 'What needs you',
      d: 'The answer first: how many concerns need the administrator, or that none do. It is the count of cards below ' +
         'that need attention.'
    },
    ov_licence: {
      t: 'Licence card',
      d: 'One line while the licence is active. It opens and goes large only when a stage other than Active applies ' +
         '(expiring, grace, read-only, suspended), with what that stage does. Try the licence stages in the demo menu.'
    },
    ov_data: {
      t: 'Data card',
      d: 'When the figures were last computed, and from which source. How many applicants and which dates are on the ' +
         'Data tab, the one place they are shown. It needs you only ' +
         'when the last recompute failed, which the engine reports; the old figures stay in use.'
    },
    ov_mapping: {
      t: 'Field mapping card',
      d: 'Counted: how many of the fields the rules read are supplied by the data in use. It needs you when one is missing, ' +
         'because rules on that field are then not evaluated.'
    },
    ov_access: {
      t: 'Users & access card',
      d: 'Active users and whether single sign-on is connected. It needs you when someone has asked for access. Simulated.'
    },
    ov_version: {
      t: 'Version card',
      d: 'What is installed and the last patch. Details are under System. Simulated.'
    },

    /* ------------------------------------------------------------ connect a source */
    ds_connect: {
      t: 'Connect a new source',
      d: 'Replaces the Oracle / PostgreSQL / MySQL tabs with one guided flow. Paused when the licence stage pauses data loads.'
    },
    ds_wizard: {
      t: 'Connect a source',
      d: 'Kind → connect → check → map fields → review for a database; kind → file → map fields → review for a file. ' +
         'Next stays disabled until a step is done: a kind chosen, a file chosen, a connection checked. The last step ' +
         'shows what would be switched to and example rows; switching is not available in this environment.'
    },
    ds_kind: {
      t: 'Kind of source',
      d: 'A file extract, or a read-only database connection refreshed on a schedule. The database type is a field of ' +
         'the connection, not a separate tab.'
    },
    ds_review: {
      t: 'Switch the analysis',
      d: 'In the deployed product this reloads the analysis on the new source, after a risk approver accepts it, and ' +
         'the old source stays available until then. Simulated.'
    },
    lic_tech: {
      t: 'Technical details',
      d: 'Who issued the licence, the signing algorithm and the key fingerprint. For Azentio support, not the client, so ' +
         'folded away. The status line already says whether the signature verified.'
    },

    /* ------------------------------------------------------------ users and access */
    ac_sso: {
      t: 'Sign-in',
      d: 'Single sign-on through the bank\'s directory. Roles are assigned by directory group, so access is granted ' +
         'where the bank already manages it, and the product reads it at each sign-in. Simulated.'
    },
    ac_users: {
      t: 'People',
      d: 'Everyone with an account, their role, status and last sign-in. A request waits for an administrator to ' +
         'review it. Simulated.'
    },
    ac_roles: {
      t: 'Roles',
      d: 'What each role may do, and which directory group grants it. These are the roles the demo menu switches ' +
         'between, with the same permissions. An administrator cannot change the risk appetite: that is the risk ' +
         'committee\'s, by proposal and approval on Settings.'
    },

    /* ------------------------------------------------------------ audit */
    au_filter: {
      t: 'Filters',
      d: 'By area, person, time and text. The rows change as you type; the download takes the rows shown.'
    },
    au_source: {
      t: 'Record',
      d: 'Recorded: written by the engine. Every proposal, decision and direct change to a governed setting, with who ' +
         'and when, and the last recompute. Example: an illustration of the other events the deployed product records ' +
         '(licence, data, rules, access, system).'
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
      t: 'Status line',
      d: 'The stage, days remaining and whether the signature verified, in one line. The days remaining are worked out ' +
         'by the export, never on the page. When a stage pauses something, the reason is shown under it.'
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
    lic_rem: {
      t: 'Renewal reminders',
      d: 'Who is told, and how many days before expiry, so a renewal is never a surprise. Sent by the bank\'s own mail relay.'
    },

    /* ------------------------------------------------------------ data source */
    ds_admin: {
      t: 'Source in use',
      d: 'What the analysis runs on now, counted from the applicant table. The demo runs on a generated population; ' +
         'the deployed product reads a file or connects to the bank\'s own database.'
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
      d: 'Whether the data in use supplies every field the rules read. Mapping a new source\'s columns is a step of ' +
         'connecting it, so it is no longer a separate editor. Everyone who works with data sees the fields on Settings.'
    },
    mp_state: {
      t: 'Fields in use',
      d: 'Counted from the applicant table every screen runs on: how many of the fields the rules read it supplies. ' +
         'This is the real state, and it is why the analysis runs.'
    },
    mp_example: {
      t: 'Example mapping',
      d: 'Step four of connecting a source: which source column supplies each field. Shown with an illustrative bank ' +
         'layout where some required fields are not mapped, so the refusal can be seen. It is not the client\'s schema, ' +
         'which has not arrived, and it does not touch the data in use. Simulated.'
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
      d: 'How a loan is called bad. Read from config `outcome`: the days-past-due mark, the months on book it must be reached ' +
         'within, and the extract date. The engine reads booking_date and bad_date against it and never sees a ground-truth ' +
         'flag. In the demo those dates are generated with the synthetic applicants, so the rates describe that population.'
    },
    oc_judged: {
      t: 'Loans the definition can judge',
      d: 'Per product, over every application in the file: loans booked, the ones on book long enough to judge, and how many ' +
         'went bad. These are the loans behind every bad rate, whatever application period a screen shows.'
    },
    oc_planned: {
      t: 'Planned refinements',
      d: 'Exclusions (early settlement, fraud) and reading performance straight from the bank\'s collections tables. ' +
         'Neither is applied yet: every loan booked and old enough is judged. Simulated.'
    },
    oc_recon: {
      t: 'Reconciliation',
      d: 'The bank\'s actual decision is compared with the replay, application by application. A difference means the rules ' +
         'were read differently, and it is better found here than by a customer.'
    },
    gv_head: {
      t: 'Platform and security',
      d: 'Deployment, data protection, the language model and regional settings. The deployed product runs inside the ' +
         'bank\'s estate with no outbound internet, and the language model only translates a question into an engine ' +
         'call; it never computes a figure. Sign-in and roles moved to Users & access. Simulated.'
    },
    vr_head: {
      t: 'Versions and updates',
      d: 'What is installed and when it last changed. Updates arrive through an encrypted patch channel signed by Azentio ' +
         'and do not overwrite the bank\'s configuration. Simulated.'
    },
    dg_head: {
      t: 'Support bundle and exports',
      d: 'A support bundle with no applicant data, for reporting a problem to Azentio when there is no remote access, ' +
         'and exports of configuration and the audit log. Results exports belong on the analysis screens. Export works ' +
         'in every licence state. Simulated.'
    }
  };
};
