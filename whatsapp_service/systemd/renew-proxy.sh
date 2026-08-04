#!/usr/bin/env bash
#
# Renews the IPRoyal residential-proxy sticky session used to route the
# WhatsApp bridge's WebSocket around WhatsApp's block on this box's
# datacenter IP (see hetzner-infra/hetzner.md, "WhatsApp bridge —
# residential proxy"). IPRoyal's sticky sessions expire after 7 days max;
# this generates a fresh session, sanity-checks the exit IP, and only then
# swaps it into the live pm2 process. On any failure it leaves the running
# bridge untouched and just alerts via Telegram — a bad renewal should
# never take down a working connection.
#
# Run by whatsapp-proxy-renew.timer as root.

set -uo pipefail

ENV_FILE="/opt/whatsapp-bridge/proxy-renew.env"
LOG_FILE="/var/log/whatsapp-proxy-renew.log"
BRIDGE_DIR="/opt/whatsapp-bridge"

# shellcheck disable=SC1090
source "$ENV_FILE"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG_FILE"; }

notify() {
    local text="$1"
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=${text}" \
        > /dev/null
}

fail() {
    log "FAILED: $1"
    notify "⚠️ WhatsApp proxy renewal failed: $1

The bridge was left untouched (still on the old session). Check the box before it expires: ssh hetzner then sudo pm2 logs whatsapp-bridge"
    exit 1
}

NEW_SESSION=$(tr -dc 'a-z0-9' < /dev/urandom | head -c 8)
NEW_PROXY_URL="http://${IPROYAL_USER}:${IPROYAL_PASS}_country-us_state-florida_session-${NEW_SESSION}_lifetime-7d@geo.iproyal.com:12321"

log "Renewing proxy session -> ${NEW_SESSION}"

EXIT_IP=$(curl -s --max-time 15 -x "$NEW_PROXY_URL" https://ipv4.icanhazip.com | tr -d '[:space:]')
if [ -z "$EXIT_IP" ]; then
    fail "new proxy session ${NEW_SESSION} did not return an exit IP (proxy unreachable or credentials rejected)"
fi

GEO=$(curl -s --max-time 10 "https://ipinfo.io/${EXIT_IP}/json")
COUNTRY=$(echo "$GEO" | node -e 'process.stdin.once("data",d=>{try{console.log(JSON.parse(d).country||"")}catch(e){console.log("")}})' 2>/dev/null)
ORG=$(echo "$GEO" | node -e 'process.stdin.once("data",d=>{try{console.log(JSON.parse(d).org||"")}catch(e){console.log("")}})' 2>/dev/null)

if [ "$COUNTRY" != "US" ]; then
    fail "new exit IP ${EXIT_IP} is not US (got '${COUNTRY}') -- refusing to switch"
fi

log "New exit IP ${EXIT_IP} (${ORG}) looks OK, applying to bridge"

pm2 delete whatsapp-bridge >> "$LOG_FILE" 2>&1
cd "$BRIDGE_DIR" || fail "cannot cd to ${BRIDGE_DIR}"
PROXY_URL="$NEW_PROXY_URL" pm2 start index.js --name whatsapp-bridge >> "$LOG_FILE" 2>&1
pm2 save >> "$LOG_FILE" 2>&1

sleep 15

HEALTH=$(curl -s --max-time 10 http://127.0.0.1:3000/healthz)
if echo "$HEALTH" | grep -q '"connected":true'; then
    log "SUCCESS: bridge reconnected via new session ${NEW_SESSION}, exit IP ${EXIT_IP}"
    notify "✅ WhatsApp proxy session renewed. New exit IP: ${EXIT_IP} (${ORG}). Bridge reconnected cleanly. Next renewal due in ~7 days."
    exit 0
fi

fail "bridge did not report connected:true after restart with new session ${NEW_SESSION} (health response: ${HEALTH}) -- may need manual re-pairing, check pm2 logs"
