# Matrix Kalenderbot

En självhostad Matrix-bot som använder Ollama (lokal AI) och Google Calendar för att hjälpa dig organisera din dag. Chatta med boten via Element och låt den läsa och boka händelser direkt i din kalender.

## Funktioner

- Chatta med en lokal AI-modell via Matrix (Element)
- Läs kommande händelser från Google Calendar
- Boka nya händelser via naturligt språk
- Konversationsminne — boten kommer ihåg vad du sagt i samtalet
- Helt självhostad och gratis — ingen molntjänst för AI krävs

## Arkitektur

```
Element (webbklient)
      ↓
Synapse (Matrix-server, Docker)
      ↓
bot.py (Python)
      ↓               ↓
Ollama (lokal AI)   Google Calendar API
```

## Krav

- Debian/Ubuntu-baserad Linux
- Docker installerat
- Python 3.11+
- Ollama installerat med minst en modell (t.ex. mistral)
- Ett Google-konto med Google Calendar

---

## Installation

### 1. Starta Synapse Matrix-server

Skapa katalog och generera konfiguration:

```bash
mkdir -p ~/matrix/synapse
cd ~/matrix/synapse

docker run -it --rm \
  -v $(pwd)/data:/data \
  -e SYNAPSE_SERVER_NAME=localhost \
  -e SYNAPSE_REPORT_STATS=no \
  matrixdotorg/synapse:latest generate
```

Starta Synapse:

```bash
docker run -d \
  --name synapse \
  --restart unless-stopped \
  -v $(pwd)/data:/data \
  -p 8448:8448 \
  -p 8008:8008 \
  matrixdotorg/synapse:latest
```

Verifiera att den körs:

```bash
curl http://localhost:8008/_matrix/client/versions
```

Inaktivera rate-limiting (lägg till i slutet av `~/matrix/synapse/data/homeserver.yaml`):

```yaml
rc_login:
  address:
    per_second: 10
    burst_count: 100
  account:
    per_second: 10
    burst_count: 100
  failed_attempts:
    per_second: 10
    burst_count: 100
```

Starta om Synapse:

```bash
docker restart synapse
```

### 2. Skapa användarkonton

Skapa ditt eget konto (admin):

```bash
docker exec -it synapse register_new_matrix_user \
  http://localhost:8008 \
  -c /data/homeserver.yaml \
  -u dittanvändarnamn \
  -p 'DittLösenord' \
  --admin
```

Skapa botkonto:

```bash
docker exec -it synapse register_new_matrix_user \
  http://localhost:8008 \
  -c /data/homeserver.yaml \
  -u matrixbot \
  -p 'BotLösenord' \
  --no-admin
```

> **Tips:** Använd enkla citattecken runt lösenord som innehåller specialtecken som `&`, `#`, `!`.

### 3. Starta Element webbklient

Hitta en ledig port (kontrollera med `docker ps`) och starta Element:

```bash
docker run -d \
  --name element \
  --restart unless-stopped \
  -p 8090:80 \
  vectorim/element-web:latest
```

Öppna `http://localhost:8090` i webbläsaren. Logga in med:
- **Homeserver:** `http://DIN_IP:8008`
- **Username:** dittanvändarnamn
- **Password:** DittLösenord

### 4. Skapa ett rum för boten

1. Klicka **"+"** bredvid Rooms i Element
2. Välj **"New room"**
3. Klicka **"More options"** och **stäng av** "Enable end-to-end encryption"
4. Bjud in `@matrixbot:localhost`

> **Viktigt:** End-to-end kryptering måste vara avstängd för att boten ska kunna läsa meddelanden.

### 5. Konfigurera Python-miljö

```bash
cd ~/matrix
python3 -m venv venv
source venv/bin/activate
pip install matrix-nio google-auth google-auth-oauthlib google-api-python-client aiohttp
```

### 6. Konfigurera Google Calendar API

1. Gå till [https://console.cloud.google.com](https://console.cloud.google.com)
2. Skapa ett nytt projekt
3. Gå till **APIs & Services** → **Enable APIs** → aktivera **Google Calendar API**
4. Gå till **APIs & Services** → **OAuth consent screen**
   - Välj **External**
   - Fyll i appnamn
   - Lägg till din e-postadress som testanvändare
5. Gå till **Credentials** → **Create Credentials** → **OAuth client ID**
   - Välj **Desktop app**
   - Ladda ner JSON-filen

Flytta credentials-filen:

```bash
mv ~/Downloads/client_secret_*.json ~/matrix/credentials.json
```

Autentisera mot Google (körs en gång):

```bash
cd ~/matrix
source venv/bin/activate
python3 auth_google.py
```

`auth_google.py`:

```python
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle

SCOPES = ['https://www.googleapis.com/auth/calendar']
flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
creds = flow.run_local_server(port=0)
with open('token.pickle', 'wb') as token:
    pickle.dump(creds, token)
print(" Autentisering klar!")
```

### 7. Starta boten

```bash
cd ~/matrix
source venv/bin/activate
python3 bot.py
```

---

## Användning

Skriv meddelanden i Element-rummet:

| Vad du skriver | Vad boten gör |
|---|---|
| "Vad har jag för aktiviteter denna vecka?" | Visar kommande händelser |
| "Lägg till möte den 25 mars kl 10-11" | Bokar i Google Calendar |
| "Är jag ledig på fredag?" | Kontrollerar kalendern |

---

## Filstruktur

```
~/matrix/
├── bot.py                  # Huvudskript för boten
├── auth_google.py          # Engångsskript för Google-autentisering
├── credentials.json        # Google OAuth credentials (lägg inte upp på GitHub!)
├── token.pickle            # Google auth token (lägg inte upp på GitHub!)
├── synapse/                # Synapse-konfiguration
│   └── data/
│       └── homeserver.yaml
└── venv/                   # Python virtual environment
```

---

## .gitignore

Lägg till denna `.gitignore` för att inte råka ladda upp känsliga filer:

```
credentials.json
token.pickle
venv/
synapse/data/
__pycache__/
*.pyc
```

---

## Teknisk stack

| Komponent | Teknologi |
|---|---|
| Matrix-server | Synapse (Docker) |
| Matrix-klient | Element Web (Docker) |
| AI-modell | Ollama + Mistral (lokal) |
| Bot-bibliotek | matrix-nio (Python) |
| Kalender | Google Calendar API |
| Språk | Python 3.11 |

---

## Kända begränsningar

- Boten kräver okrypterade rum (E2E-kryptering stöds inte i nuläget)
- Datumtolkning kan ibland bli fel år — var tydlig med att skriva ut hela året
- Boten måste vara igång för att svara (ingen systemd-service ännu)

---

## Framtida förbättringar

- [ ] Systemd-service för automatisk uppstart
- [ ] Ta bort/redigera kalenderh händelser
- [ ] Påminnelser innan möten
- [ ] Stöd för flera kalendrar
- [ ] E2E-kryptering via matrix-nio crypto

---

## Licens

MIT
