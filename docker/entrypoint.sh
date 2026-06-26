#!/bin/sh
# Daemon supervisor entrypoint.
#
# Runs as PID 1 and keeps the container alive across daemon restarts. The
# daemon intentionally exits whenever the client issues `StopRequest`
# (settings-change mtime mismatch, version upgrade, etc.); the `while`
# loop respawns it in place so the container stays up.
#
# Why not `exec rag4trex run-daemon`: if the daemon were PID 1, any daemon
# exit would take the container down with it — breaking auto-restart on
# `global_settings.yml` edits.
#
# The SIGTERM/SIGINT trap forwards `docker stop` to the daemon child so
# graceful shutdown still flows through the normal cleanup path.
set -e

if [ -n "$PUID" ] && [ -n "$PGID" ]; then
    groupmod -o -g "$PGID" coco
    usermod -o -u "$PUID" coco
    chown -R coco:coco /var/cocoindex /var/run/rag4trex
    if [ -d /workspace/.rag4trex ]; then
        chown coco:coco /workspace/.rag4trex 2>/dev/null || true
    fi
fi

run_daemon() {
    if [ -n "$PUID" ] && [ -n "$PGID" ]; then
        gosu coco rag4trex run-daemon
    else
        rag4trex run-daemon
    fi
}

child=""
trap 'if [ -n "$child" ]; then kill -TERM "$child" 2>/dev/null; wait "$child" 2>/dev/null; fi; exit 0' TERM INT

while true; do
    start_ts=$(date +%s)
    run_daemon &
    child=$!
    wait "$child" || true
    # Rate-limit respawns: sleep just long enough that successive starts are
    # >=1s apart. A clean settings-change exit with a long-running daemon
    # doesn't pay the 1s tax — only tight crash loops do.
    now=$(date +%s)
    delay=$((start_ts + 1 - now))
    if [ "$delay" -gt 0 ]; then
        sleep "$delay"
    fi
done
