#!/usr/bin/env bash
# stop-sim-miners.sh — Kill all sim-miner processes on nodes 4 and 5

SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"

for NODE in "seed1@100.66.168.9" "seed2@100.99.31.82"; do
  echo "Stopping miners on $NODE ..."
  ssh $SSH_OPTS "$NODE" "pkill -f sim-miner.py 2>/dev/null && echo stopped || echo none running"
done
