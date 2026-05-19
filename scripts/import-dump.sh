#!/usr/bin/env bash
# import-dump.sh - importerar en dump-fil till din lokala Postgres-databas.
# Körs på din egen dator i travai-repots rotmapp.

set -euo pipefail

DUMP_FILE="${1:-}"

if [ -z "$DUMP_FILE" ] || [ ! -f "$DUMP_FILE" ]; then
    echo "Användning: bash scripts/import-dump.sh <dump.sql.gz>"
    echo
    echo "Exempel:"
    echo "  bash scripts/import-dump.sh ~/Hämtningar/travai-dump-2026-05-25.sql.gz"
    exit 1
fi

echo "Detta kommer att SKRIVA ÖVER din lokala databas med dumpen."
read -p "Fortsätta? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Avbryter."
    exit 0
fi

echo "Säkerställer att Postgres kör..."
docker compose up -d
sleep 5

echo "Importerar..."
gunzip -c "$DUMP_FILE" | docker compose exec -T postgres psql -U travai -d travai

echo
echo "✓ Import klar. Kollar storleken på data:"
docker compose exec -T postgres psql -U travai -d travai -c "
SELECT 'meetings' AS t, COUNT(*) FROM meetings
UNION ALL SELECT 'races', COUNT(*) FROM races
UNION ALL SELECT 'starts', COUNT(*) FROM starts
UNION ALL SELECT 'horses', COUNT(*) FROM horses
UNION ALL SELECT 'persons', COUNT(*) FROM persons
UNION ALL SELECT 'raw_payloads', COUNT(*) FROM raw_payloads;
"
