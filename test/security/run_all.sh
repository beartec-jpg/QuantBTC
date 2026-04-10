#!/bin/bash
# QuantumBTC PQC Security Test Suite Runner
# Runs all security tests against a live local testnet node.
#
# Prerequisites:
#   ./contrib/qbtc-testnet/qbtc-testnet.sh start
#   ./pqc_sign_tool  (built from contrib/testgen/pqc_sign_tool.cpp)
#
# Usage:
#   ./test/security/run_all.sh

set -e
cd "$(dirname "$0")/../.."

RED='\033[0;31m'
GREEN='\033[0;32m'
BOLD='\033[1m'
NC='\033[0m'

echo "=================================================================="
echo "  QuantumBTC PQC Security Test Suite"
echo "  $(date)"
echo "=================================================================="

TOTAL=0
PASSED=0
FAILED=0
ERRORS=()

run_test() {
    local name="$1"
    local script="$2"
    TOTAL=$((TOTAL + 1))
    echo ""
    echo -e "${BOLD}── Running: ${name} ──${NC}"
    if python3 "$script" ; then
        PASSED=$((PASSED + 1))
        echo -e "${GREEN}  ✓ ${name}: ALL PASSED${NC}"
    else
        FAILED=$((FAILED + 1))
        ERRORS+=("$name")
        echo -e "${RED}  ✗ ${name}: HAD FAILURES${NC}"
    fi
}

# Check node is running
if ! ./src/bitcoin-cli -qbtctestnet getblockchaininfo >/dev/null 2>&1; then
    echo "ERROR: Testnet node not running. Start with:"
    echo "  ./contrib/qbtc-testnet/qbtc-testnet.sh start"
    exit 1
fi

# Run tests
run_test "PQC Witness Downgrade Bypass"          test/security/test_pqc_security.py
run_test "PQC Pubkey Not Bound to UTXO"          test/security/test_pqc_pubkey_unbinding.py
run_test "SPHINCS+ & Dilithium Verify Real/Stub"  test/security/test_sphincs_verify.py

# Summary
echo ""
echo "=================================================================="
echo -e "  ${BOLD}SUITE RESULTS: ${PASSED}/${TOTAL} test files passed${NC}"
if [ ${#ERRORS[@]} -gt 0 ]; then
    echo ""
    echo "  Failed:"
    for e in "${ERRORS[@]}"; do
        echo -e "    ${RED}- ${e}${NC}"
    done
fi
echo "=================================================================="

exit $FAILED
