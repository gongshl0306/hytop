#!/usr/bin/env bash
# Deploy hytop source to a DCU node over ssh. Nothing is installed on the
# target: it only needs python3 (>=3.8) and the HCU driver under /opt/hyhal.
#
# Usage: ./scripts/deploy.sh [user@]host [target_dir]
#   ./scripts/deploy.sh x8950_2
#   ssh x8950_2 PYTHONPATH=/tmp/hytop/src python3 -m hytop --once
set -euo pipefail

HOST="${1:-x8950_2}"
TARGET="${2:-/tmp/hytop}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

rsync -a --delete "$ROOT/src/" "$HOST:$TARGET/src/"
echo "deployed to $HOST:$TARGET/src"
echo "run:   ssh $HOST 'PYTHONPATH=$TARGET/src python3 -m hytop --once'"
echo "tui:   ssh -t $HOST 'PYTHONPATH=$TARGET/src python3 -m hytop'"
