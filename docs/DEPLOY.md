# Deploya backfill till DigitalOcean

En guide för att köra den historiska TravAI-backfillen på en DigitalOcean-droplet
istället för din egen dator. **Kostnad: 0 kr** (med $200 free credit för nya
användare, gott och väl innan 60-dagarsperioden går ut).

## Översikt

1. Skapa DigitalOcean-konto (5 min, du får $200 credit)
2. Spinna upp en droplet (1 min)
3. Köra setup-skript på droppen (~10 min)
4. Starta backfillen i bakgrund (~7-10 dygn körtid)
5. Dumpa databasen, ladda ner till din dator
6. Importera lokalt och förstöra droppen

Total handpåläggning: ~30 min spridda över tio dygn.

## 1. Skapa DigitalOcean-konto

Gå till https://www.digitalocean.com och skapa konto. Du behöver kreditkort
för verifiering, men du blir inte debiterad något om du håller dig inom de
$200 credits du får automatiskt.

Verifiera att krediten är aktiv: efter inloggning, gå till Settings → Billing.
Du ska se "$200 in credits remaining – expires in 60 days".

## 2. Lägg till SSH-key

Generera en SSH-key på din dator om du inte redan har en:

```bash
ls ~/.ssh/id_ed25519.pub  # Finns redan?
# Om inte:
ssh-keygen -t ed25519 -C "travai-backfill"
cat ~/.ssh/id_ed25519.pub
```

Kopiera innehållet. I DigitalOcean: Settings → Security → SSH Keys → Add.
Klistra in pubkey, ge namn (t.ex. "min-laptop"), spara.

## 3. Spinna upp droplet

Klicka **Create → Droplets** uppe till höger.

**Konfiguration:**
- **Region:** Frankfurt (FRA1) — närmast Sverige, snabbt mot ATG
- **OS:** Ubuntu 24.04 (LTS) x64
- **Plan:** Basic / Regular CPU / **$24/mån (4GB RAM, 2 CPU, 80GB SSD)**
  - Med credit blir 10 dygn ≈ $8, ryms gott i $200
  - Du kan välja billigare $6/mån (1GB RAM) men disken blir trång
- **Authentication:** SSH Key – välj den du lade upp
- **Hostname:** `travai-backfill`

Klicka **Create Droplet**. Vänta ~30 sek tills droppen är "Active".

Anteckna **IP-adressen** (visas i listan).

## 4. SSH in

```bash
ssh root@<DIN_DROPLET_IP>
# Säg ja på SSH fingerprint-frågan
```

Du är nu inne på servern.

## 5. Skaffa GitHub Personal Access Token

Eftersom `wslund/travai` är ett privat repo behöver setup-skriptet ett token
för att klona. Skapa ett på https://github.com/settings/tokens:

- **Generate new token (classic)**
- Note: "travai-backfill"
- Expiration: 30 days
- Scopes: bocka i **`repo`** (hela)
- Generate, kopiera tokenet (börjar med `ghp_...`)

På droppen:

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxx
```

## 6. Kör setup-skriptet

På droppen (fortfarande inloggad som root):

```bash
curl -fsSL https://raw.githubusercontent.com/wslund/travai/main/scripts/server-setup.sh -H "Authorization: token $GITHUB_TOKEN" -o server-setup.sh
bash server-setup.sh
```

Skriptet installerar Docker, klonar repot, sätter upp Postgres, kör migrations
och seeds, och kör testerna. Tar ~5-10 minuter.

När det är klart ser du:
```
✓ Setup klart!
```

## 7. Starta backfillen

```bash
cd /root/travai
FROM_DATE=2020-01-01 bash scripts/run-backfill.sh
```

Backfillen startar i en tmux-session och fortsätter köra även om du loggar ut.

**Vill du backa längre? Justera FROM_DATE:**
```bash
FROM_DATE=2018-01-01 bash scripts/run-backfill.sh
```

## 8. Kolla in då och då

Logga in och kolla framstegen:

```bash
ssh root@<DIN_DROPLET_IP>

# Snabb databas-statistik
cd /root/travai
docker compose exec postgres psql -U travai -d travai -c "
SELECT 'raw_payloads' AS t, COUNT(*) FROM raw_payloads
UNION ALL SELECT 'meetings', COUNT(*) FROM meetings
UNION ALL SELECT 'races', COUNT(*) FROM races
UNION ALL SELECT 'starts', COUNT(*) FROM starts;
"

# Se vad skriptet gör live
tmux attach -t backfill
# Ctrl-b d för att detacha utan att stoppa

# Eller följ loggen utan tmux
tail -f /root/travai/backfill.log

# Hur långt har vi kommit?
grep "backfill_progress" /root/travai/backfill.log | tail -3
```

## 9. När backfillen är klar

Du ser `backfill_done` i loggen. Dumpa databasen:

```bash
cd /root/travai
bash scripts/dump-db.sh
```

Detta skapar `/root/travai-dump-YYYY-MM-DD.sql.gz` (typ 50-200 MB).

Ladda ner till din egen dator:

```bash
# Från din lokala dator (inte servern):
scp root@<DIN_DROPLET_IP>:/root/travai-dump-*.sql.gz ~/Hämtningar/
```

## 10. Importera lokalt

På din lokala dator i travai-repots rotmapp:

```bash
cd ~/Repos/travai
bash scripts/import-dump.sh ~/Hämtningar/travai-dump-YYYY-MM-DD.sql.gz
```

Verifiera datan kom in:

```bash
docker compose exec postgres psql -U travai -d travai -c \
    "SELECT COUNT(*) FROM starts;"
# Borde vara minst 100 000+ för 5 år
```

## 11. Förstör droplet (sluta betala)

På DigitalOcean: gå till din droplet → **Destroy → Destroy this droplet**.

Eller via DigitalOcean CLI om du har det. Detta är viktigt – annars fortsätter
krediten tickas ner och efter 60 dagar börjar du betala på riktigt.

## Vad gör jag om något brakar?

**Backfillen kraschar mitt i:**
- Inget problem, den är idempotent
- SSH in, kör om: `cd /root/travai && bash scripts/run-backfill.sh`
- Den hoppar över allt vi redan har och fortsätter där den slutade

**Disken fyller upp sig:**
- raw_payloads-tabellen växer ca 1-2 MB per dag
- 5 års data ≈ 3-5 GB
- 80 GB-droppen ska räcka. Vid 50 GB använd `df -h` för att kolla
- Vid utrymmesbrist: gör mellan-dump och radera raw_payloads

**Du tappar SSH-anslutningen:**
- Inget problem. Tmux fortsätter köra. SSH in igen och `tmux attach -t backfill`

**Du vill köra om en specifik period:**
```bash
uv run python scripts/backfill.py --from 2024-01-01 --to 2024-01-31 --force
```

**Du vill se varnings/fel:**
```bash
grep -i "error\|warning" /root/travai/backfill.log | head -20
```
