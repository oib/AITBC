#!/bin/bash
# AITBC Memory Monitoring Script
# Monitors service memory usage and system memory status
set -euo pipefail

# Configuration
ALERT_THRESHOLD=90  # System memory usage alert threshold
LOG_FILE="${AITBC_MEMMON_LOG:-/var/log/aitbc/memory-monitor.log}"
ALERT_EMAIL="admin@aitbc.bubuit.net"  # Optional: configure email alerts
# Scope-cgroup OOM accounting (MEMMON-ROOT-OOM-1): the kills that took the
# hub down on 22 Oct were enforced by the container root cgroup -- every
# per-unit memory.events read 0 while the root counter climbed to 18.
CGROUP_ROOT="${AITBC_CGROUP_ROOT:-/sys/fs/cgroup}"
TEXTFILE_DIR="${AITBC_TEXTFILE_DIR:-/var/lib/prometheus/node-exporter}"
# Previous-run oom_kill counts, so the log line distinguishes a NEW kill from
# the cumulative-since-boot counter. Lives under the same writable log dir.
STATE_FILE="${AITBC_MEMMON_STATE:-$(dirname "$LOG_FILE")/memory-monitor.oom-state}"

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Function to log messages
log_message() {
    local level=$1
    local message=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
}

# Function to check system memory
check_system_memory() {
    local total_mem=$(free -m | awk '/^Mem:/{print $2}')
    local used_mem=$(free -m | awk '/^Mem:/{print $3}')

    if [ -z "$total_mem" ] || [ "$total_mem" -eq 0 ]; then
        echo "SKIPPED: Unable to get system memory information (permission issue)"
        log_message "WARNING" "Unable to get system memory information (permission issue)"
        return 0  # Don't fail on permission issues
    fi

    local mem_percent=$((used_mem * 100 / total_mem))

    echo "=== System Memory Status ==="
    echo "Total: ${total_mem}MB"
    echo "Used: ${used_mem}MB (${mem_percent}%)"
    echo "Available: $((total_mem - used_mem))MB"

    if [ $mem_percent -gt $ALERT_THRESHOLD ]; then
        echo -e "${YELLOW}WARNING: System memory usage is ${mem_percent}% (threshold: ${ALERT_THRESHOLD}%)${NC}"
        log_message "WARNING" "System memory usage is ${mem_percent}% (threshold: ${ALERT_THRESHOLD}%)"
    else
        echo -e "${GREEN}OK: System memory usage is ${mem_percent}%${NC}"
        log_message "INFO" "System memory usage is ${mem_percent}%"
        return 0
    fi
}

# Function to check service memory
check_service_memory() {
    echo ""
    echo "=== Service Memory Status ==="

    # --no-legend --plain drops the header/footer AND the "●" attention
    # marker: without --plain a flagged unit's row leads with ●, which used
    # to be fed to `systemctl show` as a unit name ("Invalid unit name").
    # The awk also strips any surviving non-unit token in column 1.
    local services=$(systemctl list-units --type=service --state=running --no-legend --plain 'aitbc*' \
        | awk '{n=($1=="●")?$2:$1; if(n~/\.service$/) print n}')
    local alert_count=0

    for service in $services; do
        local memory_current memory_max memory_limit
        memory_current=$(systemctl show "$service" -p MemoryCurrent --value)
        memory_max=$(systemctl show "$service" -p MemoryMax --value)
        memory_limit=$(systemctl show "$service" -p MemoryLimit --value)

        # systemctl --value prints "[not set]"/"infinity" for absent or
        # unbounded properties. Feeding either into $((...)) used to abort
        # the run with exit 1; a non-numeric limit is "no limit" instead.
        if ! [[ "$memory_current" =~ ^[0-9]+$ ]]; then
            echo "SKIPPED: $service - MemoryCurrent not numeric (${memory_current:-empty})"
            log_message "WARNING" "$service MemoryCurrent not numeric (${memory_current:-empty})"
            continue
        fi
        local limit_bytes=""
        local v
        for v in "$memory_max" "$memory_limit"; do
            if [[ "$v" =~ ^[0-9]+$ ]] && [ "$v" != "18446744073709551615" ]; then
                limit_bytes="$v"
                break
            fi
        done

        # Convert bytes to MB
        local memory_current_mb=$((memory_current / 1024 / 1024))
        local memory_limit_mb=""
        [ -n "$limit_bytes" ] && memory_limit_mb=$((limit_bytes / 1024 / 1024))

        # Check if service is near limit. High usage is a warning, not a unit
        # failure: % of MemoryMax counts reclaimable page cache and says nothing
        # about pressure on its own -- ffmpeg sat at 94% of a 512M cap with
        # every memory.events counter at 0. The kernel's own pressure counters
        # (oom_kill below, and the max/high events logged alongside) are what
        # mark a real problem, so usage never drives the exit code.
        if [ -n "$limit_bytes" ]; then
            local usage_percent=$((memory_current * 100 / limit_bytes))
            if [ $usage_percent -gt 80 ]; then
                echo -e "${YELLOW}WARNING: $service - ${memory_current_mb}MB/${memory_limit_mb}MB (${usage_percent}%)${NC}"
                log_message "WARNING" "$service memory usage is ${usage_percent}% (${memory_current_mb}MB/${memory_limit_mb}MB)"
                alert_count=$((alert_count + 1))
            elif [ $usage_percent -gt 60 ]; then
                echo -e "${YELLOW}WARNING: $service - ${memory_current_mb}MB/${memory_limit_mb}MB (${usage_percent}%)${NC}"
                log_message "WARNING" "$service memory usage is ${usage_percent}% (${memory_current_mb}MB/${memory_limit_mb}MB)"
            else
                echo "OK: $service - ${memory_current_mb}MB/${memory_limit_mb}MB (${usage_percent}%)"
            fi
        else
            echo "OK: $service - ${memory_current_mb}MB (no limit)"
        fi
    done

    # Usage alerts are reported but never fail the unit -- see above.
    return 0
}

# Function to check for OOM killer events
check_oom_events() {
    echo ""
    echo "=== OOM Killer Events ==="

    # Read the per-service cgroup v2 counters rather than grepping dmesg. These
    # hosts run with kernel.dmesg_restrict=1 and cannot read the kernel ring
    # buffer at all -- not even as unsandboxed root -- so a dmesg-based check is
    # permanently blind here. It used to pipe into `wc -l`, which turned that
    # into a count of 0 and reported "no OOM events" on every run.
    #
    # memory.events is world-readable, needs no privilege, and attributes each
    # kill to the service it happened in instead of to the host as a whole.
    local oom_total=0
    local found=0

    for unit in $(systemctl list-units --type=service --state=running --no-legend --plain 'aitbc*' | awk '{n=($1=="●")?$2:$1; if(n~/\.service$/) print n}'); do
        local cgroup
        cgroup=$(systemctl show -p ControlGroup --value "$unit" 2>/dev/null)
        [ -z "$cgroup" ] && continue

        local events="$CGROUP_ROOT${cgroup}/memory.events"
        [ -r "$events" ] || continue
        found=1

        local kills max_events
        kills=$(awk '/^oom_kill /{print $2}' "$events" 2>/dev/null)
        max_events=$(awk '/^max /{print $2}' "$events" 2>/dev/null)
        [[ "$kills" =~ ^[0-9]+$ ]] || continue

        # max>0 means the hard cap forced synchronous reclaim -- the thrashing
        # signature a unit shows before it is ever killed. Report it as a
        # warning so the pressure is visible without failing the unit.
        if [[ "$max_events" =~ ^[0-9]+$ ]] && [ "$max_events" -gt 0 ]; then
            echo -e "${YELLOW}WARNING: $unit hit its memory.max $max_events time(s)${NC}"
            log_message "WARNING" "$unit hit memory.max $max_events time(s) (reclaim pressure)"
        fi

        if [ "$kills" -gt 0 ]; then
            echo -e "${RED}ALERT: $unit has $kills OOM kill(s) recorded${NC}"
            log_message "ALERT" "$unit has $kills OOM kill(s) recorded"
            oom_total=$((oom_total + kills))
        fi
    done

    if [ "$found" -eq 0 ]; then
        echo -e "${YELLOW}SKIPPED: no readable per-unit cgroup memory.events; per-unit OOM check did not run${NC}"
        log_message "WARNING" "No readable per-unit cgroup memory.events; per-unit OOM check did not run"
    fi

    # --- Scope-level counters (MEMMON-ROOT-OOM-1) ---
    # Per-unit memory.events stayed at 0 through the whole 22 Oct incident
    # because the kills were enforced by the container ROOT cgroup's 3.9 GiB
    # wall (root oom_kill 18, unit counters 0). A check that only reads unit
    # cgroups prints "no kills" while the kernel is killing processes, so the
    # root, user.slice and system.slice counters are read here too.
    local scope_found=0
    local scope_new=0
    local scope_report=""
    local metrics=""

    for scope in root user.slice system.slice; do
        local sdir="$CGROUP_ROOT"
        [ "$scope" != "root" ] && sdir="$CGROUP_ROOT/$scope"
        local sevents="$sdir/memory.events"
        [ -r "$sevents" ] || continue
        local sk
        sk=$(awk '/^oom_kill /{print $2}' "$sevents" 2>/dev/null)
        [[ "$sk" =~ ^[0-9]+$ ]] || continue
        scope_found=1
        scope_report="$scope_report $scope=$sk"
        metrics="${metrics}aitbc_cgroup_oom_kill_total{cgroup=\"$scope\"} $sk
"
    done

    local m_cur="" m_peak="" m_max=""
    if [ -r "$CGROUP_ROOT/memory.current" ]; then
        m_cur=$(cat "$CGROUP_ROOT/memory.current" 2>/dev/null)
    fi
    if [ -r "$CGROUP_ROOT/memory.peak" ]; then
        m_peak=$(cat "$CGROUP_ROOT/memory.peak" 2>/dev/null)
    fi
    if [ -r "$CGROUP_ROOT/memory.max" ]; then
        m_max=$(cat "$CGROUP_ROOT/memory.max" 2>/dev/null)
    fi
    [[ "$m_cur" =~ ^[0-9]+$ ]] && metrics="${metrics}aitbc_cgroup_memory_current_bytes{cgroup=\"root\"} $m_cur
"
    [[ "$m_peak" =~ ^[0-9]+$ ]] && metrics="${metrics}aitbc_cgroup_memory_peak_bytes{cgroup=\"root\"} $m_peak
"
    if [[ "$m_max" =~ ^[0-9]+$ ]]; then
        metrics="${metrics}aitbc_cgroup_memory_max_bytes{cgroup=\"root\"} $m_max
"
    elif [ "$m_max" = "max" ]; then
        # Uncapped in cgroup v2 reads as the literal word "max"; +Inf is the
        # honest encoding -- 0 would look like a zero limit.
        metrics="${metrics}aitbc_cgroup_memory_max_bytes{cgroup=\"root\"} +Inf
"
    fi

    # Emit the textfile whenever any counter was read -- a missing or
    # unwritable textfile dir degrades to a warning, never a failed unit.
    if [ "$scope_found" -eq 1 ] || [ -n "$m_cur" ]; then
        local tmp
        if [ -d "$TEXTFILE_DIR" ] && tmp=$(mktemp "$TEXTFILE_DIR/.memory-monitor.XXXXXX" 2>/dev/null); then
            {
                echo "# HELP aitbc_cgroup_oom_kill_total Cumulative OOM kills recorded by a scope cgroup (root/slice), as reported by memory.events."
                echo "# TYPE aitbc_cgroup_oom_kill_total counter"
                echo "# HELP aitbc_cgroup_memory_current_bytes Root cgroup memory.current."
                echo "# TYPE aitbc_cgroup_memory_current_bytes gauge"
                echo "# HELP aitbc_cgroup_memory_peak_bytes Root cgroup memory.peak (high-water mark)."
                echo "# TYPE aitbc_cgroup_memory_peak_bytes gauge"
                echo "# HELP aitbc_cgroup_memory_max_bytes Root cgroup memory.max; +Inf when uncapped."
                echo "# TYPE aitbc_cgroup_memory_max_bytes gauge"
                printf '%s' "$metrics"
            } > "$tmp"
            chmod 644 "$tmp" 2>/dev/null || true
            # temp-then-rename so a scrape never catches a partial file.
            mv -f "$tmp" "$TEXTFILE_DIR/memory-monitor.prom" 2>/dev/null \
                || { rm -f "$tmp"; log_message "WARNING" "could not publish memory-monitor.prom under $TEXTFILE_DIR"; }
        else
            log_message "WARNING" "textfile dir $TEXTFILE_DIR not writable; cgroup OOM metrics skipped"
        fi
    fi

    # Delta vs the previous run: oom_kill counters are cumulative since boot,
    # so the log/exit verdict must compare against the stored baseline or a
    # one-time kill would fail every future run forever.
    local prev_line=""
    [ -r "$STATE_FILE" ] && prev_line=$(cat "$STATE_FILE" 2>/dev/null)
    local deltas=""
    if [ "$scope_found" -eq 1 ]; then
        for scope in root user.slice system.slice; do
            local sdir="$CGROUP_ROOT"
            [ "$scope" != "root" ] && sdir="$CGROUP_ROOT/$scope"
            local sk
            sk=$(awk '/^oom_kill /{print $2}' "$sdir/memory.events" 2>/dev/null)
            [[ "$sk" =~ ^[0-9]+$ ]] || continue
            local pv
            pv=$(echo "$prev_line" | tr ' ' '\n' | awk -F= -v s="$scope" '$1==s{print $2}')
            if [[ ! "$pv" =~ ^[0-9]+$ ]]; then
                # No prior record for this scope (first run, or a scope that
                # only just appeared): its cumulative count is the baseline,
                # not "new kills" -- otherwise the known pre-existing root
                # count would fire a one-time false alert on deploy.
                pv=$sk
            fi
            local d=$((sk - pv))
            [ "$d" -lt 0 ] && d=0
            scope_new=$((scope_new + d))
            [ "$d" -gt 0 ] && deltas="$deltas $scope:+$d"
        done
        # Persist the new baseline every run -- also after an alert, so one
        # incident alerts once instead of permanently.
        if [ -n "$scope_report" ]; then
            mkdir -p "$(dirname "$STATE_FILE")" 2>/dev/null || true
            echo "$scope_report" > "$STATE_FILE" 2>/dev/null \
                || log_message "WARNING" "could not write OOM state file $STATE_FILE"
        fi
    fi

    if [ "$oom_total" -gt 0 ]; then
        echo -e "${RED}ALERT: $oom_total OOM kill(s) recorded across AITBC services${NC}"
        log_message "ALERT" "$oom_total OOM kill(s) recorded across AITBC services"
    fi
    if [ "$scope_new" -gt 0 ]; then
        echo -e "${RED}ALERT: $scope_new new cgroup OOM kill(s) at scope level (${deltas# })${NC}"
        log_message "ALERT" "$scope_new new cgroup OOM kill(s) at scope level (${deltas# }); counters:${scope_report}"
    fi
    if [ "$oom_total" -gt 0 ] || [ "$scope_new" -gt 0 ]; then
        return 1
    fi

    # No "OK" unless BOTH sides were actually read and show no new kills --
    # the failure that made this rewrite necessary was an OK printed off a
    # scan that could not see the enforcing cgroup at all.
    if [ "$found" -eq 1 ] && [ "$scope_found" -eq 1 ]; then
        echo -e "${GREEN}OK: no OOM kills recorded for any AITBC service or scope cgroup${NC}"
        log_message "INFO" "No OOM kills: per-unit counters clean; scope counters${scope_report} unchanged"
        return 0
    fi

    echo -e "${YELLOW}INCOMPLETE: OOM check partial -- per-unit readable=$found scope readable=$scope_found; no kills seen on what could be read (counters:${scope_report:-none})${NC}"
    log_message "WARNING" "OOM check partial (per-unit readable=$found scope readable=$scope_found); counters:${scope_report:-none}"
    return 0
}


# Main execution
main() {
    echo "AITBC Memory Monitoring Report"
    echo "=============================="
    echo ""

    # Create log directory if it doesn't exist
    mkdir -p "$(dirname "$LOG_FILE")"

    # Run checks. Usage findings are warnings only; only a recorded OOM kill
    # fails the unit, so a routine high-usage report does not put the timer's
    # last service run into the failed-units list. The two non-fatal checks
    # must not let set -e kill the run before the summary prints.
    check_system_memory || true
    check_service_memory || true
    local oom_status=0
    check_oom_events || oom_status=$?

    echo ""
    echo "=== Summary ==="
    if [ $oom_status -eq 0 ]; then
        echo -e "${GREEN}Service memory checks passed${NC}"
        log_message "INFO" "Service memory checks passed"
        exit 0
    else
        echo -e "${RED}OOM kills recorded - check log file: $LOG_FILE${NC}"
        log_message "ALERT" "OOM kills recorded"
        exit 1
    fi
}

# Run main function
main "$@"
