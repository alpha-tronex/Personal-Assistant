/**
 * WhatsApp bridge for Personal Assistant.
 *
 * What it does:
 *   - Connects to WhatsApp Web via QR code (first run only — session is cached).
 *   - Listens for incoming DMs and forwards them to FastAPI POST /whatsapp/incoming.
 *   - Exposes POST /send so FastAPI can send approved replies back to WhatsApp.
 *   - Exposes GET /healthz for status checks.
 *
 * Ports:
 *   - This bridge listens on :3000
 *   - FastAPI is expected on :8000
 *
 * First-time setup:
 *   cd whatsapp_service && npm install && node index.js
 *   Scan the QR code with WhatsApp → Settings → Linked Devices → Link a Device.
 *   Subsequent starts reuse the saved session (no QR needed).
 */

const { Client, LocalAuth, MessageTypes } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const express = require('express');
const axios = require('axios');

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';
const PORT = parseInt(process.env.BRIDGE_PORT || '3000', 10);

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

client.on('ready', () => {
    console.log('✅ WhatsApp client ready.');
});

client.on('disconnected', (reason) => {
    console.warn('⚠️  WhatsApp disconnected:', reason);
    // launchd will restart the process if it exits.
    process.exit(1);
});

client.on('message', async (msg) => {
    // Skip own messages, group chats, status updates, and non-text messages.
    if (msg.fromMe) return;
    if (msg.from === 'status@broadcast') return;
    if (msg.from.endsWith('@g.us')) return;    // group chat JID suffix

    const body = msg.hasMedia
        ? '[Media message — open WhatsApp to view]'
        : (msg.body || '').trim();

    if (!body) return;

    const contact = await msg.getContact().catch(() => null);
    const name = contact?.pushname || contact?.name || msg.from.replace('@c.us', '');

    const payload = {
        wa_from: msg.from,
        contact_name: name,
        body,
        timestamp: msg.timestamp,
        message_id: msg.id._serialized,
    };

    console.log(`📨 New DM from ${name}: ${body.slice(0, 60)}${body.length > 60 ? '…' : ''}`);

    try {
        await axios.post(`${FASTAPI_URL}/whatsapp/incoming`, payload, { timeout: 10_000 });
    } catch (err) {
        console.error('⚠️  Failed to forward to FastAPI:', err.message);
        // Message is still visible in WhatsApp — no data is permanently lost.
    }
});

client.initialize();

// ---------------------------------------------------------------------------
// Express server — receives send commands from Python
// ---------------------------------------------------------------------------

const app = express();
app.use(express.json());

app.get('/healthz', (_req, res) => {
    res.json({ ok: true, state: client.info ? 'ready' : 'connecting' });
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
