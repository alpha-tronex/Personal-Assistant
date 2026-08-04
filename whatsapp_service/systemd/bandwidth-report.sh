#!/usr/bin/env bash
#
# One-time bandwidth report for the WhatsApp bridge, ~3 days after nethogs
# started logging (2026-08-04). Sums nethogs -t's per-60s KB/s samples for
# the bridge process, extrapolates to a monthly figure, and estimates what
# that costs on IPRoyal's $1.75/GB rotating-proxy pricing -- the whole
# reason nethogs was installed (see hetzner-infra/hetzner.md, "WhatsApp
# bridge -- residential proxy").
#
# Matches on the stable "node /opt/whatsapp-bridge/index.js/" command
# prefix rather than a fixed PID, since the bridge restarts periodically
# (proxy renewal every 6 days, plus any manual restarts) and nethogs
# tracks each restart under a new PID.
#
# Triggered once by whatsapp-bandwidth-report.timer (OnActiveSec=3d, no
# repeat). Reports to the same Telegram bot/chat as proxy renewal.

set -uo pipefail

ENV_FILE="/opt/whatsapp-bridge/proxy-renew.env"
NETHOGS_LOG="/tmp/nethogs-wa.log"
REFRESH_SEC=60

# shellcheck disable=SC1090
source "$ENV_FILE"

notify() {
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=$1" \
        > /dev/null
}

if [ ! -f "$NETHOGS_LOG" ]; then
    notify "⚠️ WhatsApp bandwidth report: ${NETHOGS_LOG} doesn't exist -- nethogs may have stopped or been removed. No usage data available."
    exit 1
fi

READ=$(grep '^node /opt/whatsapp-bridge/index.js/' "$NETHOGS_LOG" | \
    awk -F'\t' -v refresh="$REFRESH_SEC" '
        { sent_kb += $2 * refresh; recv_kb += $3 * refresh; rows++ }
        END {
            if (rows == 0) { print "0 0 0"; exit }
            total_kb = sent_kb + recv_kb
            total_gb = total_kb / (1024*1024)
            elapsed_days = (rows * refresh) / 86400
            monthly_gb = elapsed_days > 0 ? (total_gb / elapsed_days) * 30 : 0
            printf "%d %.6f %.2f %.2f\n", rows, total_gb, elapsed_days, monthly_gb
        }
    ')

ROWS=$(echo "$READ" | awk '{print $1}')
TOTAL_GB=$(echo "$READ" | awk '{print $2}')
ELAPSED_DAYS=$(echo "$READ" | awk '{print $3}')
MONTHLY_GB=$(echo "$READ" | awk '{print $4}')

if [ "$ROWS" -eq 0 ] 2>/dev/null || [ -z "$ROWS" ]; then
    notify "⚠️ WhatsApp bandwidth report: no matching nethogs entries found for the bridge process in ${NETHOGS_LOG}. Either nethogs isn't tracking it correctly, or the log format changed. Worth checking by hand."
    exit 1
fi

MONTHLY_COST=$(awk -v gb="$MONTHLY_GB" 'BEGIN { printf "%.2f", gb * 1.75 }')

MSG="📊 WhatsApp bridge bandwidth report (${ELAPSED_DAYS} days of data, ${ROWS} samples)

Total so far: ${TOTAL_GB} GB
Extrapolated monthly: ${MONTHLY_GB} GB/month
Estimated IPRoyal cost at \$1.75/GB: ~\$${MONTHLY_COST}/month

For comparison, a flat-rate static residential/ISP proxy plan runs roughly \$2-7/month per IP regardless of usage -- worth switching if the per-GB estimate above is higher than that."

notify "$MSG"
echo "$MSG"
