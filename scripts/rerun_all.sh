#!/bin/bash
# Driver: three draws, CADEC first, then FiNER. Scratch — the protocol is scripts/consolidated_rerun.sh.
cd "$(dirname "$0")/.."
for d in 0 1 2; do scripts/consolidated_rerun.sh cadec $d; done
for d in 0 1 2; do scripts/consolidated_rerun.sh finer $d; done
echo "=== $(date '+%F %T') ALL DRAWS DONE ==="
