#!/usr/bin/env bash
# Fly a SkyTrace SITL plan (data/sitl/plan.tsv) headless and collect the logs.
# Plan columns: run_id, scenario (clean|gps|battery|motor), hover_s, fault_s, value.
#
# Run inside Ubuntu / WSL (or use run_scenarios.ps1 from Windows, which also keeps
# the PC awake):
#   bash eval/sitl/run_scenarios.sh [plan.tsv]
#
# Each run: start PX4 SITL + Gazebo (gz_x500, headless) -> wait "Ready for takeoff"
# -> send the scenario's commands with the px4-* clients -> wait for disarm ->
# shut down -> copy the new log to data/raw/<run_id>.ulg -> append to
# data/sitl/manifest.tsv. Runs whose log already exists are skipped (resume).
#
# Env: PX4_DIR (default ~/PX4-Autopilot), SKYTRACE_DIR (default: this repo).

set -uo pipefail

PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"
SKYTRACE_DIR="${SKYTRACE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PLAN="${1:-$SKYTRACE_DIR/data/sitl/plan.tsv}"
OUT="$SKYTRACE_DIR/data/raw"
MANIFEST="$SKYTRACE_DIR/data/sitl/manifest.tsv"
BIN="$PX4_DIR/build/px4_sitl_default/bin"
ROOTFS="$PX4_DIR/build/px4_sitl_default/rootfs"
WORK="$(mktemp -d)"

READY_TIMEOUT=300     # first start may rebuild
TAKEOFF_TIMEOUT=60
LAND_TIMEOUT=180      # after "commander land"
BATTERY_EXTRA=240     # battery runs: drain time + this before giving up

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
px() { "$BIN/px4-$1" "${@:2}" >>"$WORK/clients.log" 2>&1; }

stop_sim() {
    px shutdown || true
    for _ in $(seq 1 15); do pgrep -x px4 >/dev/null || break; sleep 1; done
    # The sim runs in its own process group (setsid): kill make, px4, gz and the
    # stdin feeder together, then sweep leftovers.
    [[ -n "${SIM_PID:-}" ]] && kill -- "-$SIM_PID" 2>/dev/null
    sleep 2
    [[ -n "${SIM_PID:-}" ]] && kill -9 -- "-$SIM_PID" 2>/dev/null
    pkill -x px4 2>/dev/null; pkill -f "gz sim" 2>/dev/null
    SIM_PID=""
    return 0
}
trap 'log "interrupted"; stop_sim; exit 130' INT TERM

# wait_for <pattern> <file> <timeout_s>: 0 when the pattern appears.
wait_for() {
    local pattern="$1" file="$2" timeout="$3" t=0
    while (( t < timeout )); do
        grep -q -- "$pattern" "$file" 2>/dev/null && return 0
        sleep 1; t=$((t + 1))
    done
    return 1
}

# record <status>: one manifest row for the current run.
record() {
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$run_id" "$scenario" "$1" "$hover" "$fault" "$value" \
        >>"$MANIFEST"
}

[[ -x "$BIN/px4-commander" ]] || { echo "PX4 SITL not built: run 'make px4_sitl gz_x500' in $PX4_DIR first"; exit 1; }
[[ -f "$PLAN" ]] || { echo "plan not found: $PLAN (make one with eval/sitl_plan.py)"; exit 1; }
mkdir -p "$OUT" "$(dirname "$MANIFEST")"
[[ -f "$MANIFEST" ]] || printf 'run_id\tscenario\tstatus\thover_s\tfault_s\tvalue\n' >"$MANIFEST"
if pgrep -x px4 >/dev/null; then
    echo "A PX4 instance is already running. Close it first (Ctrl+C in its terminal)."; exit 1
fi

total=$(($(wc -l <"$PLAN") - 1)); n=0
while IFS=$'\t' read -r run_id scenario hover fault value; do
    n=$((n + 1))
    [[ -z "$run_id" ]] && continue
    value="${value:-0}"
    if [[ -f "$OUT/$run_id.ulg" ]]; then log "[$n/$total] $run_id: already recorded, skip"; continue; fi
    log "[$n/$total] $run_id ($scenario, hover ${hover}s, fault ${fault}s, value $value)"

    RUNOUT="$WORK/$run_id.out"; MARK="$WORK/$run_id.mark"; touch "$MARK"
    # PX4's console exits on EOF, so feed it a stdin that never ends.
    setsid bash -c 'cd "$1" && tail -f /dev/null | HEADLESS=1 make px4_sitl gz_x500' _ "$PX4_DIR" \
        >"$RUNOUT" 2>&1 &
    SIM_PID=$!

    if ! wait_for "Ready for takeoff" "$RUNOUT" "$READY_TIMEOUT"; then
        log "  not ready after ${READY_TIMEOUT}s"; record "failed:not_ready"
        stop_sim; continue
    fi
    sleep 5
    # SITL keeps parameters between runs: set what this run needs, reset the rest.
    px param set NAV_DLL_ACT 0          # no GCS in SITL
    px param set SYS_FAILURE_EN 1
    px param reset SIM_GZ_EC_MAX1       # weak-motor cap from an earlier run
    if [[ "$scenario" == "battery" ]]; then
        px param set SIM_BAT_DRAIN "$fault"
        px param set SIM_BAT_MIN_PCT 5
    else
        px param reset SIM_BAT_DRAIN
        px param reset SIM_BAT_MIN_PCT
    fi

    px commander takeoff
    if ! wait_for "Takeoff detected" "$RUNOUT" "$TAKEOFF_TIMEOUT"; then
        log "  no takeoff"; record "failed:no_takeoff"
        stop_sim; continue
    fi
    sleep "$hover"

    land_timeout=$LAND_TIMEOUT
    case "$scenario" in
        clean)   ;;
        gps)     px failure gps off; sleep "$fault"; px failure gps ok; sleep 5 ;;
        # Gazebo ignores "failure motor off": cap motor 1's rpm instead (weak motor).
        motor)   px param set SIM_GZ_EC_MAX1 "$value"; sleep "$fault"
                 px param reset SIM_GZ_EC_MAX1; sleep 5 ;;
        battery) land_timeout=$(( ${fault%.*} + BATTERY_EXTRA )) ;;  # PX4 lands on its own
    esac
    [[ "$scenario" != "battery" ]] && px commander land

    status=ok
    if ! wait_for "Disarmed" "$RUNOUT" "$land_timeout"; then
        log "  still armed after ${land_timeout}s, forcing disarm"
        px commander disarm -f; sleep 3; status="ok:forced_disarm"
    fi
    sleep 3
    stop_sim

    newest=$(find "$ROOTFS" -name '*.ulg' -newer "$MARK" -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)
    if [[ -z "$newest" ]]; then
        log "  no new log found"; record "failed:no_log"; continue
    fi
    cp "$newest" "$OUT/$run_id.ulg"
    record "$status"
    log "  saved $OUT/$run_id.ulg ($(du -h "$OUT/$run_id.ulg" | cut -f1), $status)"
done < <(tail -n +2 "$PLAN" | tr -d '\r')

rm -rf "$WORK"
log "done. Next (Windows): uv run python eval/label_sitl.py && uv run python eval/run_eval.py"
