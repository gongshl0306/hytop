#!/usr/bin/env bash
# Deploy hytop source to a DCU node over ssh. Nothing is installed on the
# target: it only needs python3 (>=3.8) and the HCU driver under /opt/hyhal.
#
# Usage: ./scripts/deploy.sh [user@]host [target_dir]
#   ./scripts/deploy.sh user@dcu-host
#   ssh user@dcu-host PYTHONPATH=/tmp/hytop/src python3 -m hytop --once
set -euo pipefail

HOST="${1:?usage: deploy.sh <user@host> [target_dir]}"
TARGET="${2:-/tmp/hytop}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

rsync -a --delete "$ROOT/src" "$ROOT/bin" "$HOST:$TARGET/"
echo "deployed to $HOST:$TARGET (src/ + bin/)"
echo "run:   ssh $HOST 'PYTHONPATH=$TARGET/src python3 -m hytop --once'"
echo "tui:   ssh -t $HOST 'PYTHONPATH=$TARGET/src python3 -m hytop'"
echo "install: ln -sfn $TARGET/bin/hytop /usr/local/bin/hytop   # then just: hytop"
