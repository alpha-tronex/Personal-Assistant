/**
 * Outage tracking for the bridge's WhatsApp connection.
 *
 * Why: on 2026-10-08 the proxy's residential exit IP rotated, the WebSocket
 * dropped, and the reconnect hung silently for ~11.5 h. pm2 still showed
 * "online" and nothing alerted. Now:
 *   - a reconnect that isn't open within CONNECT_TIMEOUT_MS exits the process
 *     (pm2 restarts it with a fresh socket + proxy connection);
 *   - when an outage passes ALERT_AFTER_MS, the backend sends a Telegram
 *     alert (re-sent at most every ALERT_COOLDOWN_MS), and a "recovered"
 *     notice once the connection opens again.
 *
 * Outage start and last-alert time live in small files so they survive the
 * process restarts the timeout triggers. Decision logic is pure for tests
 * (`node --test`).
 */

const fs = require('fs');
const os = require('os');
const path = require('path');

const CONNECT_TIMEOUT_MS = 90_000;
const ALERT_AFTER_MS     = 10 * 60_000;
const ALERT_COOLDOWN_MS  = 60 * 60_000;

/** Should we send a "still disconnected" alert right now? */
function shouldAlert({ now, outageSince, lastAlertAt,
                       alertAfterMs = ALERT_AFTER_MS, cooldownMs = ALERT_COOLDOWN_MS }) {
    if (outageSince == null) return false;
    if (now - outageSince < alertAfterMs) return false;
    return lastAlertAt == null || now - lastAlertAt >= cooldownMs;
}

/** On reconnect: was the user alerted about this outage (so owed a "recovered")? */
function owesRecoveryNotice({ outageSince, lastAlertAt }) {
    return outageSince != null && lastAlertAt != null && lastAlertAt >= outageSince;
}

/** Tiny file-backed store: { outageSince, lastAlertAt } as epoch ms or null. */
function createStore(dir = path.join(os.tmpdir(), 'whatsapp-bridge')) {
    fs.mkdirSync(dir, { recursive: true });
    const file = (name) => path.join(dir, name);
    const read = (name) => {
        try { return Number(fs.readFileSync(file(name), 'utf8')) || null; } catch { return null; }
    };
    const write = (name, value) => {
        if (value == null) fs.rmSync(file(name), { force: true });
        else fs.writeFileSync(file(name), String(value));
    };
    return {
        get outageSince() { return read('outage-since'); },
        get lastAlertAt() { return read('last-alert'); },
        /** Start an outage unless one is already running (keeps the original start). */
        markDown(now) { if (read('outage-since') == null) write('outage-since', now); },
        markAlerted(now) { write('last-alert', now); },
        /** Connection is open: the outage is over. */
        clear() { write('outage-since', null); write('last-alert', null); },
    };
}

module.exports = {
    CONNECT_TIMEOUT_MS, ALERT_AFTER_MS, ALERT_COOLDOWN_MS,
    shouldAlert, owesRecoveryNotice, createStore,
};
