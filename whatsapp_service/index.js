/**
 * WhatsApp bridge for Personal Assistant.
 *
 * What it does:
 *   - Connects to WhatsApp Web via QR code (first run only — session is cached).
 *   - On ready: replays any DMs from the last 24 hours that arrived while
 *     the bridge was offline (catch-up). FastAPI deduplicates via message_id.
 *   - Listens for new incoming DMs and forwards them to FastAPI POST /whatsapp/incoming.
 *   - Exposes POST /send so FastAPI can send approved replies back to WhatsApp.
 *   - Exposes GET /healthz and GET /stats for monitoring.
 *
 * Ports:
 *   - This bridge listens on :3000
 *   - FastAPI is expected on :8000
 */

const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const express = require('express');
const axios = require('axios');

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';
const PORT = parseInt(process.env.BRIDGE_PORT || '3000', 10);
const CATCHUP_HOURS = 24;           // how far back to look for missed messages on startup
const WATCHDOG_INTERVAL_MS = 60_000; // check client health every 60 s

// ---------------------------------------------------------------------------
// Stats counters
// ---------------------------------------------------------------------------

const stats = {
    startedAt: new Date().toISOString(),
    received: 0,       // real-time messages received since startup
    forwarded: 0,      // successfully forwarded to FastAPI
    failed: 0,         // failed to forward
    catchupSent: 0,    // messages replayed during startup catch-up
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function forwardToFastAPI(payload, { isCatchup = false } = {}) {
    try {
        await axios.post(`${FASTAPI_URL}/whatsapp/incoming`, payload, { timeout: 10_000 });
        if (isCatchup) {
            stats.catchupSent++;
        } else {
            stats.forwarded++;
        }
        return true;
    } catch (err) {
        if (!isCatchup) stats.failed++;
        console.error(
            `⚠️  Failed to forward${isCatchup ? ' (catch-up)' : ''} to FastAPI:`,
            err.message,
        );
        return false;
    }
}

function isGroupJid(jid) {
    return jid.endsWith('@g.us') || jid.endsWith('@newsletter');
}

// ---------------------------------------------------------------------------
// Startup catch-up — replay missed DMs from the last CATCHUP_HOURS
// ---------------------------------------------------------------------------

async function catchUpMissedMessages() {
    const cutoff = Math.floor(Date.now() / 1000) - CATCHUP_HOURS * 3600;
    console.log(`🔄 Catch-up: scanning DMs from the last ${CATCHUP_HOURS} hours…`);

    let chats;
    try {
        chats = await client.getChats();
    } catch (err) {
        console.error('⚠️  Could not fetch chats for catch-up:', err.message);
        return;
    }

    const dmChats = chats.filter(c => !c.isGroup && !isGroupJid(c.id._serialized));
    let total = 0;

    for (const chat of dmChats) {
        let messages;
        try {
            messages = await chat.fetchMessages({ limit: 20 });
        } catch {
            continue;
        }

        for (const msg of messages) {
            if (msg.fromMe) continue;
            if (msg.timestamp < cutoff) continue;

            const body = msg.hasMedia
                ? '[Media message — open WhatsApp to view]'
                : (msg.body || '').trim();
            if (!body) continue;

            const contact = await msg.getContact().catch(() => null);
            const name = contact?.pushname || contact?.name || msg.from.replace('@c.us', '');

            await forwardToFastAPI({
                wa_from: msg.from,
                contact_name: name,
                body,
                timestamp: msg.timestamp,
                message_id: msg.id._serialized,
            }, { isCatchup: true });

            total++;
        }
    }

    console.log(`✅ Catch-up complete — ${total} message(s) replayed (FastAPI deduplicates).`);
}

// ---------------------------------------------------------------------------
// WhatsApp client
// ---------------------------------------------------------------------------

const client = new Client({
    authStrategy: new LocalAuth({ dataPath: './.wwebjs_auth' }),
    puppeteer: {
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox'],
    },
});

client.on('qr', (qr) => {
    console.log('\n📱 Scan this QR code with WhatsApp:');
    console.log('   (Settings → Linked Devices → Link a Device)\n');
    qrcode.generate(qr, { small: true });
});

client.on('authenticated', () => {
    console.log('✅ WhatsApp authenticated — session saved.');
});

client.on('auth_failure', (msg) => {
    console.error('❌ WhatsApp auth failed:', msg);
    console.error('   Delete .wwebjs_auth/ and restart to re-scan the QR code.');
});

// ---------------------------------------------------------------------------
// Watchdog — exits if the Puppeteer page detaches or WA goes silent
// ---------------------------------------------------------------------------

let _watchdogTimer = null;

function startWatchdog() {
    if (_watchdogTimer) return;
    _watchdogTimer = setInterval(async () => {
        try {
            const state = await client.getState();
            if (state !== 'CONNECTED') {
                console.error(`❌ Watchdog: unexpected client state "${state}" — restarting.`);
                process.exit(1);
            }
        } catch (err) {
            console.error('❌ Watchdog: client health check failed — restarting.', err.message);
            process.exit(1);
        }
    }, WATCHDOG_INTERVAL_MS);

    // Don't let the timer keep Node alive on its own
    _watchdogTimer.unref();
    console.log(`🐕 Watchdog started (every ${WATCHDOG_INTERVAL_MS / 1000}s).`);
}

client.on('ready', () => {
    console.log('✅ WhatsApp client ready.');
    startWatchdog();
    // Run catch-up in background — don't block the ready event.
    catchUpMissedMessages().catch(err =>
        console.error('⚠️  Catch-up failed:', err.message)
    );
});

client.on('disconnected', (reason) => {
    console.warn('⚠️  WhatsApp disconnected:', reason);
    process.exit(1);   // launchd restarts automatically
});

client.on('message', async (msg) => {
    if (msg.fromMe) return;
    if (msg.from === 'status@broadcast') return;
    if (isGroupJid(msg.from)) return;

    const body = msg.hasMedia
        ? '[Media message — open WhatsApp to view]'
        : (msg.body || '').trim();
    if (!body) return;

    stats.received++;

    const contact = await msg.getContact().catch(() => null);
    const name = contact?.pushname || contact?.name || msg.from.replace('@c.us', '');

    console.log(`📨 New DM from ${name}: ${body.slice(0, 60)}${body.length > 60 ? '…' : ''}`);

    await forwardToFastAPI({
        wa_from: msg.from,
        contact_name: name,
        body,
        timestamp: msg.timestamp,
        message_id: msg.id._serialized,
    });
});

client.initialize();

// ---------------------------------------------------------------------------
// Express server
// ---------------------------------------------------------------------------

const app = express();
app.use(express.json());

app.get('/healthz', (_req, res) => {
    res.json({ ok: true, state: client.info ? 'ready' : 'connecting' });
});

app.get('/stats', (_req, res) => {
    res.json({
        ...stats,
        uptimeSeconds: Math.floor(process.uptime()),
        state: client.info ? 'ready' : 'connecting',
    });
});

app.post('/send', async (req, res) => {
    const { to, body } = req.body || {};
    if (!to || !body) {
        return res.status(400).json({ ok: false, error: 'to and body are required' });
    }
    try {
        await client.sendMessage(to, body);
        console.log(`📤 Sent to ${to}: ${body.slice(0, 60)}${body.length > 60 ? '…' : ''}`);
        res.json({ ok: true });
    } catch (err) {
        console.error('❌ Send failed:', err.message);
        res.status(500).json({ ok: false, error: err.message });
    }
});

app.listen(PORT, '127.0.0.1', () => {
    console.log(`🌐 WhatsApp bridge listening on http://127.0.0.1:${PORT}`);
});
