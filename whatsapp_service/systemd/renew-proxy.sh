#!/usr/bin/env bash
#
# Renews the IPRoyal residential-proxy sticky session used to route the
# WhatsApp bridge's WebSocket around WhatsApp's block on this box's
# datacenter IP (see hetzner-infra/hetzner.md, "WhatsApp bridge —
# residential proxy"). IPRoyal's sticky sessions expire after 7 days max;
# this generates a fresh session, sanity-checks the exit IP, and only then
# swaps it into the live pm2 process. On any failure before the restart it
# leaves the running bridge untouched and just alerts via Telegram — a bad
# renewal should never take down a working connection.
#
# The bridge runs under alphathiam's pm2 (PM2_HOME=/home/alphathiam/.pm2,
# resurrected at boot by pm2-alphathiam.service). Every pm2 call here goes
# through as_bridge so it hits that daemon — a bare `pm2` as root spawns a
# separate root daemon and a second, root-owned bridge, which is what broke
# things in Sep 2026 (renewals "succeeded" against the wrong process and
# left root-owned files in auth/).
#
# Run by whatsapp-proxy-renew.timer as root (needs the root-only env file).

set -uo pipefail

ENV_FILE="/opt/whatsapp-bridge/proxy-renew.env"
LOG_FILE="/var/log/whatsapp-proxy-renew.log"
BRIDGE_DIR="/opt/whatsapp-bridge"
BRIDGE_USER="alphathiam"
BRIDGE_PM2_HOME="/home/${BRIDGE_USER}/.pm2"
PROXY_PORT=12321

# shellcheck disable=SC1090
source "$ENV_FILE"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG_FILE"; }

as_bridge() { runuser -u "$BRIDGE_USER" -- env PM2_HOME="$BRIDGE_PM2_HOME" "$@"; }

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

Check the box: ssh hetzner then pm2 logs whatsapp-bridge (as ${BRIDGE_USER}, not sudo)"
    exit 1
}

NEW_SESSION=$(tr -dc 'a-z0-9' < /dev/urandom | head -c 8)
NEW_PROXY_URL="http://${IPROYAL_USER}:${IPROYAL_PASS}_country-us_state-florida_session-${NEW_SESSION}_lifetime-7d@geo.iproyal.com:${PROXY_PORT}"

log "Renewing proxy session -> ${NEW_SESSION}"

EXIT_IP=$(curl -s --max-time 15 -x "$NEW_PROXY_URL" https://ipv4.icanhazip.com | tr -d '[:space:]')
if [ -z "$EXIT_IP" ]; then
    fail "new proxy session ${NEW_SESSION} did not return an exit IP (proxy unreachable or credentials rejected) -- bridge left untouched"
fi

GEO=$(curl -s --max-time 10 "https://ipinfo.io/${EXIT_IP}/json")
COUNTRY=$(echo "$GEO" | node -e 'process.stdin.once("data",d=>{try{console.log(JSON.parse(d).country||"")}catch(e){console.log("")}})' 2>/dev/null)
ORG=$(echo "$GEO" | node -e 'process.stdin.once("data",d=>{try{console.log(JSON.parse(d).org||"")}catch(e){console.log("")}})' 2>/dev/null)

if [ "$COUNTRY" != "US" ]; then
    fail "new exit IP ${EXIT_IP} is not US (got '${COUNTRY}') -- refusing to switch, bridge left untouched"
fi

log "New exit IP ${EXIT_IP} (${ORG}) looks OK, applying to bridge"

# Self-heal: anything in auth/ not owned by the bridge user makes Baileys
# fail to persist keys (EACCES on creds.json) and the session degrades.
chown -R "${BRIDGE_USER}:${BRIDGE_USER}" "$BRIDGE_DIR/auth"

as_bridge pm2 delete whatsapp-bridge >> "$LOG_FILE" 2>&1
as_bridge PROXY_URL="$NEW_PROXY_URL" pm2 start "$BRIDGE_DIR/index.js" \
    --name whatsapp-bridge --cwd "$BRIDGE_DIR" >> "$LOG_FILE" 2>&1
# Persists PROXY_URL into the dump so a reboot resurrects the bridge on the proxy.
as_bridge pm2 save >> "$LOG_FILE" 2>&1

# Verify the *new* process is the one serving :3000, was started with this
# session, holds a connection to the proxy, and reports connected -- a bare
# healthz check passes against any bridge that happens to own the port.
PID="" LISTEN_PID="" HEALTH=""
for _ in $(seq 1 12); do
    sleep 5
    PID=$(as_bridge pm2 pid whatsapp-bridge 2>/dev/null | tr -d '[:space:]')
    [ -n "$PID" ] && [ "$PID" != "0" ] || continue
    LISTEN_PID=$(ss -ltnpH 'sport = :3000' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
    [ "$LISTEN_PID" = "$PID" ] || continue
    tr '\0' '\n' < "/proc/${PID}/environ" 2>/dev/null | grep -q "_session-${NEW_SESSION}_" || continue
    ss -tnpH state established "dport = :${PROXY_PORT}" | grep -q "pid=${PID}," || continue
    HEALTH=$(curl -s --max-time 10 http://127.0.0.1:3000/healthz)
    if echo "$HEALTH" | grep -q '"connected":true'; then
        log "SUCCESS: bridge pid ${PID} reconnected via new session ${NEW_SESSION}, exit IP ${EXIT_IP}"
        notify "✅ WhatsApp proxy session renewed. New exit IP: ${EXIT_IP} (${ORG}). Bridge (pid ${PID}) verified on the proxy and connected. Next renewal due in ~6 days."
        exit 0
    fi
done

fail "bridge not verified on new session ${NEW_SESSION} after 60s (pm2 pid='${PID}', :3000 owner pid='${LISTEN_PID}', health='${HEALTH}') -- may need manual re-pairing, check pm2 logs"
