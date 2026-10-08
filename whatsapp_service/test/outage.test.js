const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { shouldAlert, owesRecoveryNotice, createStore, ALERT_AFTER_MS, ALERT_COOLDOWN_MS } = require('../lib/outage');

const MIN = 60_000;

test('no alert while connected or during short blips', () => {
    assert.equal(shouldAlert({ now: 0, outageSince: null, lastAlertAt: null }), false);
    assert.equal(shouldAlert({ now: 9 * MIN, outageSince: 0, lastAlertAt: null }), false);
});

test('alerts once the outage passes the threshold', () => {
    assert.equal(shouldAlert({ now: ALERT_AFTER_MS, outageSince: 0, lastAlertAt: null }), true);
});

test('re-alerts only after the cooldown', () => {
    const since = 0;
    const alerted = 11 * MIN;
    assert.equal(shouldAlert({ now: alerted + 30 * MIN, outageSince: since, lastAlertAt: alerted }), false);
    assert.equal(shouldAlert({ now: alerted + ALERT_COOLDOWN_MS, outageSince: since, lastAlertAt: alerted }), true);
});

test('recovery notice is owed only if this outage was alerted', () => {
    assert.equal(owesRecoveryNotice({ outageSince: 100, lastAlertAt: 200 }), true);
    assert.equal(owesRecoveryNotice({ outageSince: 100, lastAlertAt: null }), false);
    assert.equal(owesRecoveryNotice({ outageSince: null, lastAlertAt: 200 }), false);
});

test('store keeps the original outage start across restarts and clears on reconnect', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'outage-test-'));
    const a = createStore(dir);
    a.markDown(1000);
    a.markDown(5000);                 // a restart mid-outage must not reset the clock
    const b = createStore(dir);       // new process, same files
    assert.equal(b.outageSince, 1000);
    b.markAlerted(7000);
    assert.equal(createStore(dir).lastAlertAt, 7000);
    b.clear();
    assert.equal(b.outageSince, null);
    assert.equal(b.lastAlertAt, null);
    fs.rmSync(dir, { recursive: true, force: true });
});
