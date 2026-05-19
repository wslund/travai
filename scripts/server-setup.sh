#!/usr/bin/env bash
# server-setup.sh - kör på en färsk Ubuntu 24.04 VPS för att förbereda
# travai för historisk backfill. Idempotent - kan köras flera gånger.
#
# Användning på servern:
#   curl -fsSL https://raw.githubusercontent.com/wslund/travai/main/scripts/server-setup.sh | bash
# eller efter klonat repo:
#   bash scripts/server-setup.sh

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[setup]${NC} $1"; }
warn() { echo -e "${YELLOW}[setup]${NC} $1"; }

# ---------- 1. System packages ----------
log "Uppdaterar apt-cache..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    git curl ca-certificates gnupg lsb-release \
    tmux htop jq postgresql-client-16

# ---------- 2. Docker ----------
if ! command -v docker &> /dev/null; then
    log "Installerar Docker..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
else
    log "Docker redan installerat, hoppar över"
fi

# ---------- 3. uv (python pkg manager) ----------
if [ ! -f "$HOME/.local/bin/uv" ]; then
    log "Installerar uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

# ---------- 4. Repo ----------
REPO_DIR="${TRAVAI_REPO_DIR:-/root/travai}"
if [ ! -d "$REPO_DIR" ]; then
    log "Klonar travai-repot..."
    if [ -n "${GITHUB_TOKEN:-}" ]; then
        # Med GitHub Personal Access Token
        git clone "https://${GITHUB_TOKEN}@github.com/wslund/travai.git" "$REPO_DIR"
    else
        warn "Ingen GITHUB_TOKEN satt. Försöker SSH-klon..."
        git clone git@github.com:wslund/travai.git "$REPO_DIR"
    fi
else
    log "Repot finns redan, drar senaste..."
    cd "$REPO_DIR" && git pull
fi
cd "$REPO_DIR"

# ---------- 5. Konfiguration ----------
if [ ! -f .env ]; then
    log "Kopierar .env.example till .env"
    cp .env.example .env
fi

# ---------- 6. Postgres via Docker ----------
log "Startar Postgres..."
docker compose up -d
log "Väntar på att Postgres ska bli redo..."
sleep 8
until docker compose exec -T postgres pg_isready -U travai &>/dev/null; do
    sleep 2
done

# ---------- 7. Python deps ----------
log "Installerar Python-beroenden via uv..."
uv sync --all-extras

# ---------- 8. Databas migration & seed ----------
log "Kör Alembic-migrationer..."
uv run alembic upgrade head

log "Seedar referensdata..."
uv run python scripts/seed_reference_data.py

# ---------- 9. Verifiering ----------
log "Verifierar..."
uv run pytest -q

echo
echo -e "${GREEN}✓ Setup klart!${NC}"
echo
echo "Nästa steg:"
echo "  1. Starta backfillen i bakgrunden:"
echo "       bash scripts/run-backfill.sh"
echo "  2. Eller justera intervall och kör manuellt:"
echo "       cd $REPO_DIR"
echo "       tmux new -s backfill"
echo "       uv run python scripts/backfill.py --from 2020-01-01 --to 2026-05-18 2>&1 | tee backfill.log"
echo "       (Ctrl-b d för att detacha)"
echo
