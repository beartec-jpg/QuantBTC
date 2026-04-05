#!/bin/bash
# ============================================================
# QuantumBTC — CI Integration Test Runner
#
# Runs all stability/resilience tests in sequence.
# Exit code: 0 if all pass, 1 if any fail.
#
# Usage:
#   ./ci_test_runner.sh              # Run all tests
#   ./ci_test_runner.sh --quick      # Skip the 10k-block test
# ============================================================

set -o pipefail

SRCDIR="$(cd "$(dirname "$0")" && pwd)"
TOTAL_PASS=0
TOTAL_FAIL=0
RESULTS=()

run_test() {
    local name="$1"
    local script="$2"
    echo ""
    echo "================================================================"
    echo " Running: $name"
    echo "================================================================"

    if bash "$script"; then
        TOTAL_PASS=$((TOTAL_PASS + 1))
        RESULTS+=("✓ $name")
    else
        TOTAL_FAIL=$((TOTAL_FAIL + 1))
        RESULTS+=("✗ $name")
    fi
}

# ----------------------------------------------------------
# Parse args
# ----------------------------------------------------------
QUICK=false
for arg in "$@"; do
    case "$arg" in
        --quick) QUICK=true ;;
    esac
done

echo "============================================================"
echo " QuantumBTC CI Test Runner"
echo " $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================================"

# ----------------------------------------------------------
# Build check
# ----------------------------------------------------------
if [[ ! -x "$SRCDIR/build-fresh/src/bitcoind" ]]; then
    echo "ERROR: bitcoind not found at $SRCDIR/build-fresh/src/bitcoind"
    echo "Run: cd build-fresh && make -j\$(nproc)"
    exit 1
fi

# ----------------------------------------------------------
# Core integration test
# ----------------------------------------------------------
run_test "Full Integration Test" "$SRCDIR/run_full_test.sh"

# ----------------------------------------------------------
# Kill-9 crash recovery (fast — ~1000 blocks)
# ----------------------------------------------------------
run_test "Kill-9 Crash Recovery" "$SRCDIR/test_kill9_recovery.sh"

# ----------------------------------------------------------
# IBD from genesis (2-node, 2000 blocks)
# ----------------------------------------------------------
run_test "IBD From Genesis" "$SRCDIR/test_ibd_genesis.sh"

# ----------------------------------------------------------
# Restart after 10k blocks (long, skip with --quick)
# ----------------------------------------------------------
if [[ "$QUICK" == "false" ]]; then
    run_test "Restart After 10k Blocks" "$SRCDIR/test_restart_10k.sh"
else
    echo ""
    echo "  ⊘ Skipping restart-after-10k test (--quick mode)"
    RESULTS+=("⊘ Restart After 10k Blocks (skipped)")
fi

# ----------------------------------------------------------
# Summary
# ----------------------------------------------------------
echo ""
echo "================================================================"
echo " CI Test Summary"
echo " $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "================================================================"
for r in "${RESULTS[@]}"; do echo "  $r"; done
echo ""
echo " Total: $((TOTAL_PASS + TOTAL_FAIL)) suites, $TOTAL_PASS passed, $TOTAL_FAIL failed"
echo "================================================================"

if [[ $TOTAL_FAIL -gt 0 ]]; then
    exit 1
fi
exit 0
