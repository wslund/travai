#!/usr/bin/env bash
# run-backfill.sh - startar den stora historiska backfillen i en tmux-session
# så den överlever att du kopplar ner från SSH.
#
# Konfigurera intervall via env-variabler:
#   FROM_DATE=2018-01-01 TO_DATE=2026-05-18 bash scripts/run-backfill.sh
#
# Default-intervall: 2020-01-01 till idag (justera om du vill backa längre).

set -euo pipefail

REPO_DIR="${TRAVAI_REPO_DIR:-/root/travai}"
FROM_DATE="${FROM_DATE:-2020-01-01}"
TO_DATE="${TO_DATE:-$(date -I)}"
SESSION_NAME="${SESSION_NAME:-backfill}"
LOG_FILE="${LOG_FILE:-$REPO_DIR/backfill.log}"

cd "$REPO_DIR"

# Stoppa befintlig session med samma namn
tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true

# Starta i en ny detached tmux-session
tmux new-session -d -s "$SESSION_NAME" \
    "export PATH=\"\$HOME/.local/bin:\$PATH\"; \
     uv run python scripts/backfill.py --from $FROM_DATE --to $TO_DATE 2>&1 | tee $LOG_FILE; \
     echo 'BACKFILL DONE. Press any key to exit.'; \
     read"

echo "✓ Backfill startad i tmux-session: $SESSION_NAME"
echo
echo "Intervall: $FROM_DATE → $TO_DATE"
echo "Logg:      $LOG_FILE"
echo
echo "Användbara kommandon:"
echo "  Attach till sessionen:    tmux attach -t $SESSION_NAME"
echo "  Detacha igen:             Ctrl-b d (i tmux)"
echo "  Tail loggen utan tmux:    tail -f $LOG_FILE"
echo "  Lista tmux-sessioner:     tmux ls"
echo "  Stoppa backfillen:        tmux kill-session -t $SESSION_NAME"
echo
echo "Snabb status (räkna data):"
echo "  cd $REPO_DIR && docker compose exec postgres psql -U travai -d travai -c \\"
echo "    \"SELECT COUNT(*) AS raw FROM raw_payloads WHERE entity_type='game';\""
