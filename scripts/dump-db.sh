#!/usr/bin/env bash
# dump-db.sh - dumpar postgres-databasen till en gzippad SQL-fil för nedladdning.
# Körs på servern efter att backfillen är klar.

set -euo pipefail

REPO_DIR="${TRAVAI_REPO_DIR:-/root/travai}"
OUTPUT="${OUTPUT:-$HOME/travai-dump-$(date -I).sql.gz}"

cd "$REPO_DIR"

echo "Dumpar databasen till $OUTPUT ..."
docker compose exec -T postgres pg_dump \
    -U travai \
    -d travai \
    --no-owner --no-acl --clean --if-exists \
    | gzip -9 > "$OUTPUT"

SIZE=$(du -h "$OUTPUT" | cut -f1)
echo "✓ Klar! Storlek: $SIZE"
echo
echo "Hämta dumpen till din lokala dator:"
echo "  scp root@$(curl -s ifconfig.me):$OUTPUT ."
echo
echo "Importera lokalt med:"
echo "  bash scripts/import-dump.sh $(basename "$OUTPUT")"
