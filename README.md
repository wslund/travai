# TravAI

Data-driven travanalys. Bygger sannolikhetsmodeller över svenska travlopp och hittar värdespel jämfört med marknadsodds.

## Stack

- Python 3.12+ med `uv` för pakethantering
- PostgreSQL 16 (i Docker)
- SQLAlchemy 2.0 + Alembic för databas
- httpx för API-anrop
- pydantic för datavalidering
- structlog för logging
- LightGBM för modellen (kommer i senare steg)

## Setup

```bash
# 1. Installera uv om du inte har det
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Klona/öppna projektet
cd travai

# 3. Skapa virtual env och installera dependencies
uv sync

# 4. Kopiera env-fil och redigera vid behov
cp .env.example .env

# 5. Starta Postgres
docker compose up -d

# 6. Verifiera att db kör
docker compose ps
```

## Köra första utforskning

```bash
uv run python scripts/explore.py
```

Detta hämtar dagens travkalender från ATG och visar vilka lopp som körs.

## Projektstruktur

```
travai/
├── src/travai/
│   ├── config.py          # Settings via pydantic-settings
│   ├── atg/
│   │   ├── client.py      # HTTP-klient mot ATG:s API
│   │   └── models.py      # Pydantic-modeller för API-svar
├── scripts/
│   └── explore.py         # Utforska ATG:s endpoints
├── tests/
├── docker-compose.yml
├── pyproject.toml
└── .env.example
```

## Roadmap

- [x] Steg 1: Projektgrund + ATG-klient
- [ ] Steg 2: Databasschema (races, starts, horses, drivers, trainers)
- [ ] Steg 3: Historisk backfill av 2-3 års data
- [ ] Steg 4: Feature engineering
- [ ] Steg 5: LightGBM-modell + backtesting
- [ ] Steg 6: FastAPI-lager

## Datakällor

- **ATG inofficiellt JSON-API** (`https://www.atg.se/services/racinginfo/v1/api/`) — för start och prototyp
- **ATG partner-API (AIS)** — ansök parallellt för produktion
- **travsport.se** — för utökad sportdata, scrape med försiktighet

## Etik och juridik

Detta projekt bygger ett analysverktyg, ingen spelförmedling. Före publik lansering:
- Partneravtal med ATG för stabil datatillgång
- Juristkonsultation för marknadsföringsregler
- Inbyggt stöd för ansvarsfullt spelande
