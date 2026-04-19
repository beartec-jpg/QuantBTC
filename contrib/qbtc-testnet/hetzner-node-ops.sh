#!/usr/bin/env bash
# hetzner-node-ops.sh — keep qBTC testnet nodes under a safer CPU profile and sweep wallets periodically
#
# Usage examples:
#   export QBTC_NODE1_PASS='...'
#   export QBTC_NODE2_PASS='...'
#   export QBTC_NODE3_PASS='...'
#   ./contrib/qbtc-testnet/hetzner-node-ops.sh status
#   ./contrib/qbtc-testnet/hetzner-node-ops.sh apply-lowcpu 30
#   ./contrib/qbtc-testnet/hetzner-node-ops.sh setup-drain qbtct1qdtnzfm4r0w5853rjy3gy4xgft3chmklgx2yh6a 30 1.0
#   ./contrib/qbtc-testnet/hetzner-node-ops.sh deploy-all

set -euo pipefail

TARGET_ADDR_DEFAULT="qbtct1qdtnzfm4r0w5853rjy3gy4xgft3chmklgx2yh6a"
CPU_LIMIT_DEFAULT="30"
DRAIN_INTERVAL_DEFAULT="30"
KEEP_DEFAULT="1.0"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_HELPER="$SCRIPT_DIR/qbtc-testnet.sh"
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"

NODES=(S1 S2 S3)
declare -A NODE_IP=(
  [S1]="46.62.156.169"
  [S2]="37.27.47.236"
  [S3]="89.167.109.241"
)
declare -A NODE_PASS=(
  [S1]="${QBTC_NODE1_PASS:-}"
  [S2]="${QBTC_NODE2_PASS:-}"
  [S3]="${QBTC_NODE3_PASS:-}"
)

die() {
  echo "ERROR: $*" >&2
  exit 1
}

need_passwords() {
  for n in "${NODES[@]}"; do
    [[ -n "${NODE_PASS[$n]}" ]] || die "Missing password env for $n. Set QBTC_NODE1_PASS / QBTC_NODE2_PASS / QBTC_NODE3_PASS first."
  done
}

ssh_node() {
  local node="$1"; shift
  sshpass -p "${NODE_PASS[$node]}" ssh $SSH_OPTS "root@${NODE_IP[$node]}" "$@"
}

scp_node() {
  local node="$1" src="$2" dst="$3"
  sshpass -p "${NODE_PASS[$node]}" scp $SSH_OPTS "$src" "root@${NODE_IP[$node]}:$dst"
}

cmd_status() {
  need_passwords
  printf '%-4s %-16s %-8s %-8s %-8s %-10s %s\n' "Node" "IP" "CPU%" "Height" "Peers" "Balance" "Process"
  printf '%-4s %-16s %-8s %-8s %-8s %-10s %s\n' "----" "----------------" "--------" "--------" "--------" "----------" "-------"
  for n in "${NODES[@]}"; do
    data=$(ssh_node "$n" '
      idle=$(top -bn1 | awk "NR==3 {for(i=1;i<=NF;i++) if (\$i ~ /id,/) {print \$(i-1); exit}}" | tr -d "%" )
      cpu=$(python3 - <<PY
idle = float("${idle:-100}" or 100)
print(f"{100-idle:.1f}")
PY
)
      height=$(/root/QuantBTC/src/bitcoin-cli -chain=qbtctestnet getblockcount 2>/dev/null || echo ?)
      peers=$(/root/QuantBTC/src/bitcoin-cli -chain=qbtctestnet getconnectioncount 2>/dev/null || echo ?)
      balance=$(/root/QuantBTC/src/bitcoin-cli -chain=qbtctestnet -rpcwallet=miner getbalance 2>/dev/null || echo ?)
      proc=$(ps -eo pcpu,pmem,cmd --sort=-pcpu | grep -E "bitcoind|cpulimit" | grep -v grep | head -n 1 | sed "s/^ *//")
      echo "$cpu|$height|$peers|$balance|${proc:-down}"
    ' 2>/dev/null || echo '?|?|?|?|unreachable')
    IFS='|' read -r cpu height peers balance proc <<< "$data"
    printf '%-4s %-16s %-8s %-8s %-8s %-10s %s\n' "$n" "${NODE_IP[$n]}" "$cpu" "$height" "$peers" "$balance" "$proc"
  done
}

cmd_apply_lowcpu() {
  need_passwords
  local pct="${1:-$CPU_LIMIT_DEFAULT}"
  echo "Applying low-CPU profile at ${pct}% across all nodes..."
  for n in "${NODES[@]}"; do
    echo "  $n (${NODE_IP[$n]})"
    scp_node "$n" "$LOCAL_HELPER" "/root/qbtc-testnet.sh"
    ssh_node "$n" "chmod +x /root/qbtc-testnet.sh && \
      if command -v apt-get >/dev/null 2>&1; then DEBIAN_FRONTEND=noninteractive apt-get update -qq >/dev/null 2>&1 || true; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq cpulimit >/dev/null 2>&1 || true; fi && \
      python3 - <<'PY'
from pathlib import Path
conf = Path('/root/.bitcoin/bitcoin.conf')
conf.parent.mkdir(parents=True, exist_ok=True)
text = conf.read_text() if conf.exists() else 'chain=qbtctestnet\n\n[qbtctestnet]\n'
lines = [ln for ln in text.splitlines() if not any(ln.startswith(k) for k in ('maxconnections=','dbcache=','maxmempool=','maxsigcachesize=','par='))]
lines += ['maxconnections=16','dbcache=128','maxmempool=100','maxsigcachesize=16','par=1']
conf.write_text('\n'.join(lines).rstrip() + '\n')
print('config-updated')
PY
      /root/qbtc-testnet.sh throttle ${pct} || true"
  done
}

cmd_setup_drain() {
  need_passwords
  local addr="${1:-$TARGET_ADDR_DEFAULT}"
  local every="${2:-$DRAIN_INTERVAL_DEFAULT}"
  local keep="${3:-$KEEP_DEFAULT}"
  echo "Installing periodic wallet drain to ${addr} ..."
  for n in "${NODES[@]}"; do
    echo "  $n (${NODE_IP[$n]})"
    scp_node "$n" "$LOCAL_HELPER" "/root/qbtc-testnet.sh"
    ssh_node "$n" "chmod +x /root/qbtc-testnet.sh && /root/qbtc-testnet.sh autosweep ${addr} ${every} ${keep}"
  done
}

cmd_deploy_all() {
  local pct="${1:-$CPU_LIMIT_DEFAULT}"
  local addr="${2:-$TARGET_ADDR_DEFAULT}"
  local every="${3:-$DRAIN_INTERVAL_DEFAULT}"
  local keep="${4:-$KEEP_DEFAULT}"
  cmd_apply_lowcpu "$pct"
  cmd_setup_drain "$addr" "$every" "$keep"
  echo
  cmd_status
}

usage() {
  cat <<EOF
Usage: $0 <command> [args]

Commands:
  status                           Show CPU, height, peers, and miner balance
  apply-lowcpu [pct]               Push a low-resource profile and throttle bitcoind
  setup-drain [addr] [mins] [keep] Install periodic wallet drain on each node
  deploy-all [pct] [addr] [mins] [keep]

Environment:
  QBTC_NODE1_PASS / QBTC_NODE2_PASS / QBTC_NODE3_PASS
EOF
}

cmd="${1:-}"
shift || true
case "$cmd" in
  status) cmd_status "$@" ;;
  apply-lowcpu) cmd_apply_lowcpu "$@" ;;
  setup-drain) cmd_setup_drain "$@" ;;
  deploy-all) cmd_deploy_all "$@" ;;
  help|-h|--help|"") usage ;;
  *) usage; exit 1 ;;
esac
