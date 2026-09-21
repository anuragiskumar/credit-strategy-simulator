// Unit tests for the shared funnel model. Node's built-in runner, no dependencies:
//   node --test ui/tests/*.test.js
// Run from pytest by tests/test_client_funnel_model.py.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const FunnelModel = require('../client_funnel_model.js');

const FIXTURE = path.join(__dirname, '..', 'client_fixture.json');
const load = () => JSON.parse(fs.readFileSync(FIXTURE, 'utf8'));

test('every figure is the exported figure, unchanged', () => {
  const F = load(), M = FunnelModel.build(F);
  const rows = Object.fromEntries(F.funnel.map((r) => [r.stage, r]));
  assert.equal(M.start.stillIn, rows[F.funnel_layout.order[0]].left);
  assert.equal(M.end.stillIn, rows[F.funnel_layout.order.at(-1)].left);
  for (const s of M.stages) {
    const r = rows[s.id];
    assert.equal(s.entered, r.entered);
    assert.equal(s.stillIn, r.left);
    assert.equal(s.lost, r.dropped);
    assert.equal(s.pctLostOfReaching, r.dropped_pct_of_entered);
    assert.equal(s.pctLostOfTotal, r.dropped_pct_of_total);
    assert.equal(s.pctStillInOfTotal, r.left_pct);
  }
});

test('the exported fixture adds up, so the dev assertion is silent', () => {
  assert.deepEqual(FunnelModel.build(load()).issues, []);
});

test('the dev assertion names a stage whose "in" does not follow from the previous one', () => {
  const F = load();
  F.funnel.find((r) => r.stage === 'credit_policy').entered += 1;
  const issues = FunnelModel.build(F).issues;
  assert.ok(issues.some((i) => i.stage === 'credit_policy' && i.msg.startsWith('credit_policy: in')), JSON.stringify(issues));
});

test('a drill-down that does not sum to its stage is reported, not hidden', () => {
  const F = load();
  F.funnel_rules.find((b) => b.stage === 'hard_reject').rules[0].count -= 5;
  const issues = FunnelModel.build(F).issues;
  assert.ok(issues.some((i) => i.stage === 'hard_reject' && i.msg.startsWith('hard_reject: rule counts sum to')), JSON.stringify(issues));
});

test('a stage carries its own issues so the drill-down can show them in place', () => {
  const F = load();
  F.funnel_rules.find((b) => b.stage === 'hard_reject').rules[0].count -= 5;
  const M = FunnelModel.build(F);
  assert.ok(M.stages.find((s) => s.id === 'hard_reject').issues.length > 0);
  assert.equal(M.stages.find((s) => s.id === 'credit_policy').issues.length, 0);
});

test('applied and booked are endpoints, and booked appears exactly once', () => {
  const M = FunnelModel.build(load());
  const ids = M.stages.map((s) => s.id);
  assert.ok(!ids.includes(M.start.id) && !ids.includes(M.end.id));
  assert.equal([M.start.id, M.end.id, ...ids].filter((id) => id === 'booked').length, 1);
});

test('grouping and loss type follow config, not row position', () => {
  const F = load();
  let M = FunnelModel.build(F);
  const byId = Object.fromEntries(M.stages.map((s) => [s.id, s]));
  assert.equal(byId.eligibility.lossType, 'lender');
  assert.equal(byId.walked_away.lossType, 'customer');

  F.funnel_layout.stages.eligibility.group = 'customer_choice';
  M = FunnelModel.build(F);
  const elig = M.stages.find((s) => s.id === 'eligibility');
  assert.equal(elig.lossType, 'customer');
  assert.deepEqual(M.groups.find((g) => g.id === 'customer_choice').stages.map((s) => s.id),
                   ['eligibility', 'walked_away']);
});

test('drill-down is available where a stage has recorded reasons, and not where config turns it off', () => {
  const M = FunnelModel.build(load());
  const byId = Object.fromEntries(M.stages.map((s) => [s.id, s]));
  assert.ok(byId.hard_reject.drillable && byId.credit_policy.drillable && byId.eligibility.drillable);
  assert.equal(byId.walked_away.drillable, false);
  assert.equal(byId.credit_policy.rules.length, byId.credit_policy.nRules, 'no top-N cut');
});

test('the headline reads the stage that loses the most and its top-N share from the export', () => {
  const F = load(), M = FunnelModel.build(F);
  const most = Math.max(...M.stages.map((s) => s.lost));
  assert.equal(M.headline.worst.lost, most);
  const block = F.funnel_rules.find((b) => b.stage === M.headline.worst.id);
  assert.equal(M.headline.topNPct, block.top_n_pct);
  assert.equal(M.headline.nRules, block.n_rules);
  assert.equal(M.headline.topN, F.funnel_layout.headline_top_n);
});

// ------------------------------------------------------------------ funnel geometry
for (const [width, narrow] of [[900, false], [320, true]]) {
  test(`funnel bands are exactly proportional to still-in (${width}px)`, () => {
    const M = FunnelModel.build(load()), G = FunnelModel.geometry(M, { width, narrow });
    for (const b of G.bands) {
      assert.ok(Math.abs(b.w - (b.value / M.total) * G.midW) < 1e-9, `${b.id}: ${b.w}`);
      assert.ok(Math.abs(b.x + b.w / 2 - G.cx) < 1e-9, `${b.id} is centred`);
    }
    assert.equal(G.bands[0].w, G.midW, 'applied fills the band column');
  });

  test(`each trapezoid joins the band above to the band below (${width}px)`, () => {
    const M = FunnelModel.build(load()), G = FunnelModel.geometry(M, { width, narrow });
    G.connectors.forEach((c, i) => {
      const above = G.bands[i], below = G.bands[i + 1];
      assert.ok(Math.abs(c.points[1][0] - c.points[0][0] - above.w) < 1e-9, c.id);
      assert.ok(Math.abs(c.points[2][0] - c.points[3][0] - below.w) < 1e-9, c.id);
    });
  });
}

test('booked is drawn once, as the last band', () => {
  const M = FunnelModel.build(load()), G = FunnelModel.geometry(M, { width: 900 });
  assert.equal(G.bands.filter((b) => b.id === M.end.id).length, 1);
  assert.equal(G.bands.at(-1).kind, 'end');
  assert.equal(G.bands.length, M.stages.length + 1);
  assert.equal(G.names.filter((n) => n.id === M.end.id).length, 1);
});

test('leak stroke grows with the loss and stays within its bounds', () => {
  const M = FunnelModel.build(load()), G = FunnelModel.geometry(M, { width: 900 });
  const pairs = G.leaks.map((l, i) => [M.stages[i].lost, l.sw]).sort((a, b) => a[0] - b[0]);
  for (let i = 1; i < pairs.length; i++) assert.ok(pairs[i][1] >= pairs[i - 1][1]);
  for (const l of G.leaks) assert.ok(l.sw >= 2 && l.sw <= 12);
  assert.deepEqual(G.leaks.map((l) => l.lossType), M.stages.map((s) => s.lossType));
});

for (const [width, narrow, minRun] of [[900, false, 48], [311, true, 16]]) {
  test(`every leak arrow starts on its trapezoid's right edge and has room to curve (${width}px)`, () => {
    const M = FunnelModel.build(load()), G = FunnelModel.geometry(M, { width, narrow });
    G.leaks.forEach((l, i) => {
      const [, tr, br] = G.connectors[i].points;
      const m = /^M([\d.]+),([\d.]+) C/.exec(l.d), x = +m[1], y = +m[2];
      const t = (y - tr[1]) / (br[1] - tr[1]);
      const edge = tr[0] + (br[0] - tr[0]) * t;
      assert.ok(t > 0 && t < 1, `${l.id} starts within its row`);
      assert.ok(x <= edge && x >= edge - 4, `${l.id} starts on the edge (${x} vs ${edge})`);
      assert.ok(l.run >= minRun, `${l.id} run ${l.run}`);
    });
  });
}
