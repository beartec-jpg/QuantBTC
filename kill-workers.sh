#!/bin/bash
sshpass -p 'VV3fXsXimWVC' ssh -o StrictHostKeyChecking=no root@46.62.156.169 'pkill -f qbtc-pool-worker.py; echo node2_done'
sshpass -p 'tPRsdiHhKWTc' ssh -o StrictHostKeyChecking=no root@37.27.47.236 'pkill -f qbtc-pool-worker.py; echo node3_done'
