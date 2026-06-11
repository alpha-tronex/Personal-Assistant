/**
 * WhatsApp bridge — powered by Baileys (no Puppeteer).
 *
 * What it does:
 *   - Connects to WhatsApp using the multi-device Web protocol directly.
 *   - First run: prints a QR code to the terminal — scan once, session is saved.
 *   - On connect: forwards all new incoming DMs to FastAPI POST /whatsapp/incoming.
 *   - Exposes POST /send so FastAPI can send approved replies back to WhatsApp.
 *   - Exposes GET /healthz and GET /stats for monitoring.
 *   - Watchdog: alerts via FastAPI if no message is received for 6+ daytime hours.
 *   - Auto-reconnects on dropped connection; exits on logout (so Docker restarts it).
 *
 * Ports:
 *   - This bridge listens on :3000
 *   - FastAPI is expected on :8000 (set via FASTAPI_URL env var)
 *
 * Auth:
 *   - Session stored in AUTH_DIR (default: ./auth) as JSON files.
 *   - Mount this directory as a Docker volume to persist across restarts.
 */

const {
    makeWASocket,
    useMultiFileAuthState,
    DisconnectReason,
    fetchLatestBaileysVersion,
    isJidGroup,
    isJidBroadcast,
    isJidStatusBroadcast,
} = require('@whiskeysockets/baileys');
const { Boom } = require('@hapi/boom');
const pino = require('pino');
const qrcode = require('qrcode-terminal');
const express = require('express');
const axios = require('axios');
const fs = require('fs');

const FASTAPI_URL   = process.env.FASTAPI_URL   || 'http://127.0.0.1:8000';
const PORT          = parseInt(process.env.BRIDGE_PORT || '3000', 10);
const AUTH_DIR      = process.env.AUTH_DIR       || './auth';

const SILENCE_THRESHOLD_MS    = 6 * 60 * 60 * 1000;  // alert after 6 h quiet
const SILENCE_COOLDOWN_MS     = 4 * 60 * 60 * 1000;  // re-alert at most every 4 h
const DAYTIME_START           = 8;
const DAYTIME_END             = 22;
const WATCHDOG_INTERVAL_MS    = 60_000;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const stats = {
    startedAt: new Date().toISOString(),
    received: 0,
    forwarded: 0,
    failed: 0,
};

let sock           = null;
let isConnected    = false;
let lastMessageAt  = Date.now();
let lastAlertAt    = 0;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Extract plain text from any message type. Returns null for pure media. */
function extractBody(msg) {
    const m = msg.message;
    if (!m) return null;
    return (
        m.conversation                        ||
        m.extendedTextMessage?.text           ||
        m.imageMessage?.caption               ||
        m.videoMessage?.caption               ||
        m.buttonsResponseMessage?.selectedDisplayText ||
        m.listResponseMessage?.title          ||
        null
    );
}

function isMedia(msg) {
    const m = msg.message;
    if (!m) return false;
    return !!(
        m.imageMessage   || m.videoMessage  || m.audioMessage ||
        m.documentMessage || m.stickerMessage || m.ptvMessage
    );
}

/** Normalise JID to @s.whatsapp.net (Baileys format). */
function normaliseJid(jid) {
    return jid.replace('@c.us', '@s.whatsapp.net');
}

async function forwardToFastAPI(payload) {
    try {
        await axios.post(`${FASTAPI_URL}/whatsapp/incoming`, payload, { timeout: 10_000 });
        stats.forwarded++;
        return true;
    } catch (err) {
        stats.failed++;
        console.error('⚠️  Forward to FastAPI failed:', err.message);
        return false;
    }
}

async function sendSilenceAlert(silentMs) {
    const hours = (silentMs / 3_600_000).toFixed(1);
    try {
        await axios.post(
            `${FASTAPI_URL}/whatsapp/silence-alert`,
            { silent_for_hours: parseFloat(hours) },
            { timeout: 8_000 },
        );
        lastAlertAt = Date.now();
        console.warn(`⚠️  Silence alert sent — ${hours}h with no messages.`);
    } catch (err) {
        console.error('⚠️  Could not send silence alert:', err.message);
    }
}

// ---------------------------------------------------------------------------
// Watchdog
// ---------------------------------------------------------------------------

function startWatchdog() {
    const timer = setInterval(async () => {
        if (!isConnected) return; // reconnect logic handles this

        const now       = Date.now();
        const hour      = new Date().getHours();
        const daytime   = hour >= DAYTIME_START && hour < DAYTIME_END;
        const silentMs  = now - lastMessageAt;
        const cooledDown = (now - lastAlertAt) > SILENCE_COOLDOWN_MS;

        if (daytime && silentMs > SILENCE_THRESHOLD_MS && cooledDown) {
            await sendSilenceAlert(silentMs);
        }
    }, WATCHDOG_INTERVAL_MS);
    timer.unref();
    console.log(`🐕 Watchdog started (every ${WATCHDOG_INTERVAL_MS / 1000}s).`);
}

// ---------------------------------------------------------------------------
// WhatsApp connection
// ---------------------------------------------------------------------------

async function connectToWhatsApp() {
    fs.mkdirSync(AUTH_DIR, { recursive: true });
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const { version }          = await fetchLatestBaileysVersion();

    console.log(`📡 Using WA version ${version.join('.')}`);

    sock = makeWASocket({
        version,
        auth: state,
        logger: pino({ level: 'silent' }),
        // Avoid stale-message fetch errors on reconnect
        getMessage: async () => ({ conversation: '' }),
    });

    // Persist credentials whenever they update
    sock.ev.on('creds.update', saveCreds);

    // Connection lifecycle
    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            console.log('\n📱 Scan this QR code with WhatsApp:');
            console.log('   Settings → Linked Devices → Link a Device\n');
            qrcode.generate(qr, { small: true });
        }

        if (connection === 'close') {
            isConnected = false;
            const code = new Boom(lastDisconnect?.error)?.output?.statusCode;
            console.warn(`⚠️  Connection closed. Code: ${code}`);

            if (code === DisconnectReason.loggedOut) {
                console.error('❌ Logged out — re-auth required. Exiting so Docker can restart.');
                process.exit(1);
            } else {
                console.log('🔄 Reconnecting in 5 s…');
                setTimeout(connectToWhatsApp, 5_000);
            }
        } else if (connection === 'open') {
            isConnected    = true;
            lastMessageAt  = Date.now();
            console.log('✅ WhatsApp connected and ready.');
            startWatchdog();
        }
    });

    // Incoming messages
    sock.ev.on('messages.upsert', async ({ messages, type }) => {
        if (type !== 'notify') return;

        for (const msg of messages) {
            const jid = msg.key.remoteJid || '';
            if (msg.key.fromMe)            continue;
            if (isJidGroup(jid))           continue;
            if (isJidBroadcast(jid))       continue;
            if (isJidStatusBroadcast(jid)) continue;

            const media = isMedia(msg);
            const body  = media
                ? '[Media message — open WhatsApp to view]'
                : extractBody(msg);

            if (!body) continue;

            stats.received++;
            lastMessageAt = Date.now();

            const name = msg.pushName || jid.replace('@s.whatsapp.net', '');
            console.log(`📨 ${name}: ${body.slice(0, 80)}${body.length > 80 ? '…' : ''}`);

            await forwardToFastAPI({
                wa_from:      jid,
                contact_name: name,
                body,
                timestamp:    Number(msg.messageTimestamp) || Math.floor(Date.now() / 1000),
                message_id:   msg.key.id,
            });
        }
    });
}

// ---------------------------------------------------------------------------
// Express server
// ---------------------------------------------------------------------------

const app = express();
app.use(express.json());

app.get('/healthz', (_req, res) => {
    res.json({ ok: true, connected: isConnected });
});

app.get('/stats', (_req, res) => {
    res.json({
        ...stats,
        connected:         isConnected,
        uptimeSeconds:     Math.floor(process.uptime()),
        lastMessageAt:     new Date(lastMessageAt).toISOString(),
        silentForMinutes:  Math.floor((Date.now() - lastMessageAt) / 60_000),
    });
});

app.post('/send', async (req, res) => {
    const { to, body } = req.body || {};
    if (!to || !body) {
        return res.status(400).json({ ok: false, error: 'to and body are required' });
    }
    if (!sock || !isConnected) {
        return res.status(503).json({ ok: false, error: 'WhatsApp not connected' });
    }
    try {
        const jid = normaliseJid(to);   // handle legacy @c.us JIDs from DB
        await sock.sendMessage(jid, { text: body });
        console.log(`📤 Sent to ${jid}: ${body.slice(0, 60)}${body.length > 60 ? '…' : ''}`);
        res.json({ ok: true });
    } catch (err) {
        console.error('❌ Send failed:', err.message);
        res.status(500).json({ ok: false, error: err.message });
    }
});

app.listen(PORT, '0.0.0.0', () => {
    console.log(`🌐 WhatsApp bridge listening on :${PORT}`);
});

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

connectToWhatsApp().catch(err => {
    console.error('Fatal error:', err);
    process.exit(1);
});
