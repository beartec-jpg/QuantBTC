#!/usr/bin/env bash
# deploy-sim-miners.sh
# Deploys sim-miner.py to nodes 4 and 5 and starts 2 throttled workers on each.
#
# Each worker mines at ~15% CPU to simulate realistic pool traffic.
# Mining reward address: qbtct1qdtnzfm4r0w5853rjy3gy4xgft3chmklgx2yh6a
#
# Usage: bash deploy-sim-miners.sh

set -euo pipefail

POOL="89.167.109.241:3333"
ADDR="qbtct1qdtnzfm4r0w5853rjy3gy4xgft3chmklgx2yh6a"
SCRIPT_SRC="$(dirname "$0")/contrib/sim-miner.py"
REMOTE_SCRIPT="/root/sim-miner.py"
CPU=15

NODE4_HOST="100.66.168.9"
NODE4_USER="seed1"
NODE4_PASS="seed1!"

NODE5_HOST="100.99.31.82"
NODE5_USER="seed2"
NODE5_PASS="seed2!"

SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"

echo "=== Deploying sim-miner.py ==="

# Copy script to both nodes via SCP
scp $SSH_OPTS "$SCRIPT_SRC" "${NODE4_USER}@${NODE4_HOST}:${REMOTE_SCRIPT}"
scp $SSH_OPTS "$SCRIPT_SRC" "${NODE5_USER}@${NODE5_HOST}:${REMOTE_SCRIPT}"

echo "=== Starting miners on node 4 (seed1) ==="
ssh $SSH_OPTS "${NODE4_USER}@${NODE4_HOST}" bash <<EOF
  pkill -f sim-miner.py 2>/dev/null || true
  sleep 1
  nohup python3 ${REMOTE_SCRIPT} \
    --pool ${POOL} \
    --user ${ADDR}.node4_w1 \
    --cpu ${CPU} \
    > /root/sim-miner-w1.log 2>&1 &
  echo "node4 worker1 PID=\$!"
  sleep 2
  nohup python3 ${REMOTE_SCRIPT} \
    --pool ${POOL} \
    --user ${ADDR}.node4_w2 \
    --cpu ${CPU} \
    > /root/sim-miner-w2.log 2>&1 &
  echo "node4 worker2 PID=\$!"
EOF

echo "=== Starting miners on node 5 (seed2) ==="
ssh $SSH_OPTS "${NODE5_USER}@${NODE5_HOST}" bash <<EOF
  pkill -f sim-miner.py 2>/dev/null || true
  sleep 1
  nohup python3 ${REMOTE_SCRIPT} \
    --pool ${POOL} \
    --user ${ADDR}.node5_w1 \
    --cpu ${CPU} \
    > /root/sim-miner-w1.log 2>&1 &
  echo "node5 worker1 PID=\$!"
  sleep 2
  nohup python3 ${REMOTE_SCRIPT} \
    --pool ${POOL} \
    --user ${ADDR}.node5_w2 \
    --cpu ${CPU} \
    > /root/sim-miner-w2.log 2>&1 &
  echo "node5 worker2 PID=\$!"
EOF

echo ""
echo "=== Done! 4 workers running (2 per node) ==="
echo "  node4: ${ADDR}.node4_w1  ${ADDR}.node4_w2"
echo "  node5: ${ADDR}.node5_w1  ${ADDR}.node5_w2"
echo ""
echo "Check logs:  ssh seed1@${NODE4_HOST} 'tail -f /root/sim-miner-w1.log'"
echo "Pool stats:  curl http://89.167.109.241:8088/stats | python3 -m json.tool"
