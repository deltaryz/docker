#!/bin/bash
RESTART_HOUR=4
LOG_PID=""

cleanup() {
    echo ""
    echo "[$(date)] Shutting down..."
    docker compose down
    kill $LOG_PID 2>/dev/null
    wait $LOG_PID 2>/dev/null
    exit 0
}
trap cleanup INT TERM

attach_logs() {
    local tail="${1:-50}"
    docker compose logs -f --tail "$tail" &
    LOG_PID=$!
}

restart_stack() {
    echo "[$(date)] Scheduled restart — detaching logs..."
    kill $LOG_PID 2>/dev/null
    wait $LOG_PID 2>/dev/null
    docker compose down
    sleep 5
    echo "[$(date)] Cleanup pass..."
    docker compose down
    sleep 5
    echo "[$(date)] Bringing stack back up..."
    docker compose up -d
    echo "[$(date)] Stack restarted — reattaching logs..."
    attach_logs 0   # tail=0: only new logs after restart
    sleep 61        # avoid double-fire within same minute
}

echo "[$(date)] Starting stack..."
docker compose up -d
attach_logs 50  # show last 50 lines of history on initial attach

LAST_RESTART_MINUTE=""
while true; do
    now=$(date +%H:%M)
    target=$(printf "%02d:00" $RESTART_HOUR)

    if [[ "$now" == "$target" && "$now" != "$LAST_RESTART_MINUTE" ]]; then
        LAST_RESTART_MINUTE="$now"
        restart_stack
    fi

    # reattach if log process died unexpectedly
    if ! kill -0 $LOG_PID 2>/dev/null; then
        echo "[$(date)] Log stream ended — reattaching..."
        attach_logs 0
    fi

    sleep 5
done
