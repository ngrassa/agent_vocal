# 🍽️ AI Restaurant Order Agent

Agent vocal IA qui répond automatiquement aux appels téléphoniques, prend les commandes en français (+ arabe tunisien) et les envoie sur Telegram.

---

## ✅ Déploiement réalisé automatiquement

| Étape | Résultat |
|---|---|
| Credentials AWS lus | `ASIARHM27EOZ5IVSBQMD` |
| Terraform init + apply | EC2 t3.medium créé |
| Elastic IP | **54.226.12.85** (permanente) |
| Security Group | SSH + 8000 + SIP 5060 + RTP 10000-10100 |
| Telegram Chat ID | **8484002816** (Nordine Grassa) |
| FastAPI Dashboard | http://54.226.12.85:8000 ✅ |
| Asterisk PBX | Running, dialplan configuré ✅ |
| Test commande | Sauvegardé en SQLite ✅ |
| Notification Telegram | Envoyée sur votre compte ✅ |

---

## Schéma d'architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    AWS EC2 t3.medium (54.226.12.85)             │
│                                                                 │
│  Téléphone/Zoiper ──SIP──► Asterisk PBX (port 5060)            │
│                                    │                            │
│                              AGI Python                         │
│                                    │                            │
│                    ┌───────────────┼───────────────┐            │
│                    ▼               ▼               ▼            │
│             faster-whisper    Mistral AI        gTTS           │
│              (STT local)     (NLU/réponse)    (TTS audio)      │
│                    └───────────────┼───────────────┘            │
│                                    │                            │
│                    ┌───────────────┼───────────────┐            │
│                    ▼               ▼               ▼            │
│              FastAPI API      SQLite DB       Telegram Bot      │
│             (Dashboard)    (historique)    (notification)       │
│                                                                 │
│  http://54.226.12.85:8000          @resto_appel_bot             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📱 Tester un vrai appel MAINTENANT (sans SIP trunk payant)

### Option A — Zoiper (Android/iOS, gratuit)

1. Installez **Zoiper5** depuis le Play Store / App Store
2. Créez un compte → **Ajouter compte SIP**
3. Entrez exactement :

| Champ | Valeur |
|---|---|
| **Nom d'utilisateur** | `1000` |
| **Mot de passe** | `restaurant2024` |
| **Serveur/Domaine** | `54.226.12.85` |
| **Nom d'auth** | `1000` |
| **Port** | `5060` |
| **Transport** | `UDP` |

4. Composez le **7000** → l'agent vocal répond en français

### Option B — MizuDroid (Android)

| Champ | Valeur |
|---|---|
| **Username** | `1000` |
| **Password** | `restaurant2024` |
| **Server** | `54.226.12.85` |
| **Port** | `5060` |

Composez le **7000** pour tester.

### Option C — Linphone (PC/Linux)

```bash
# Installer Linphone
sudo apt install linphone

# Ou utiliser linphone-cli
linphonecsh init
linphonecsh register --host 54.226.12.85 --username 1000 --password restaurant2024
linphonecsh call sip:7000@54.226.12.85
```

---

## 📞 Recevoir de vrais appels téléphoniques (SIP Trunk)

Pour avoir un vrai numéro de téléphone, inscrivez-vous chez un fournisseur SIP :

### Fournisseur recommandé : VoIP.ms (~0.009$/min)

1. Créer compte sur [voip.ms](https://voip.ms)
2. Acheter un DID (numéro tunisien ou français)
3. Configurer les credentials sur le serveur :

```bash
ssh -i ~/.ssh/labsuser.pem ubuntu@54.226.12.85
nano restaurant-agent/.env
```

Remplir les lignes :
```env
SIP_TRUNK_HOST=toronto1.voip.ms
SIP_TRUNK_USER=VOTRE_USERNAME_VOIPMS
SIP_TRUNK_PASS=VOTRE_MOT_DE_PASSE
```

Puis redémarrer :
```bash
cd restaurant-agent
docker compose restart asterisk
```

Dans votre compte VoIP.ms, configurer le **Routing** vers : `sip:54.226.12.85`

---

## Accès serveur

```bash
# SSH
ssh -i ~/.ssh/labsuser.pem ubuntu@54.226.12.85

# Dashboard web
http://54.226.12.85:8000

# Logs en temps réel
ssh ubuntu@54.226.12.85 'cd restaurant-agent && docker compose logs -f'

# État des containers
ssh ubuntu@54.226.12.85 'docker ps'
```

---

## Structure du projet

```
restaurant-agent/
├── Dockerfile                 ← Image FastAPI
├── docker-compose.yml         ← Orchestration (agent + asterisk)
├── .env                       ← Variables d'environnement
├── menu.json                  ← Menu du restaurant (modifiable)
├── data/orders.db             ← SQLite (créé automatiquement)
├── app/
│   ├── main.py                ← FastAPI dashboard + API + endpoint interne
│   ├── config.py              ← Paramètres pydantic-settings
│   ├── models.py              ← SQLAlchemy (Order, OrderItem, CallSession)
│   ├── mistral_client.py      ← Conversation Mistral AI
│   ├── telegram_sender.py     ← Envoi Telegram formaté
│   ├── order_parser.py        ← Enrichissement/validation commande
│   └── call_handler.py        ← (legacy Twilio, remplacé par AGI)
├── asterisk/
│   ├── Dockerfile             ← Asterisk + Python + ffmpeg + Whisper
│   ├── start.sh               ← Génère configs depuis env vars
│   └── agi/
│       └── restaurant_agi.py  ← Script AGI (cœur de l'agent vocal)
└── terraform/
    ├── main.tf                ← EC2 + EIP + Security Group
    ├── variables.tf
    └── outputs.tf
```

---

## Flux d'un appel

```
1. Appel entrant (SIP trunk ou Zoiper)
       ↓
2. Asterisk reçoit → extensions.conf → AGI(restaurant_agi.py)
       ↓
3. AGI répond (Answer)
4. gTTS génère le message d'accueil → Asterisk le joue
       ↓
5. Boucle de conversation :
   a. Asterisk enregistre la voix du client (RECORD FILE)
   b. ffmpeg convertit en 16kHz WAV
   c. faster-whisper transcrit (fr + darija)
   d. Mistral AI analyse → génère réponse JSON
   e. gTTS génère l'audio de la réponse
   f. Asterisk joue la réponse (STREAM FILE)
   g. Si action=order_complete → sortir de la boucle
       ↓
6. POST http://localhost:8000/api/internal/order (FastAPI)
   → Sauvegarde SQLite
   → Envoi Telegram (@resto_appel_bot)
       ↓
7. AGI dit "Merci, au revoir" → Hangup
```

---

## Message Telegram envoyé

```
📦 Nouvelle Commande — A1B2C3D4

👤 Client: Ahmed Kairouan
📞 Téléphone: 98765432

🍽️ Produits:
  • 2x Pizza Margherita — 24 TND
  • 1x Coca Cola 1L — 4 TND

💰 Total: 28 TND

🚗 Mode: Livraison à domicile
📍 Adresse:
Rue Habib Bourguiba, Kairouan

🕒 Heure: 2026-05-31 11:27
```

---

## Variables d'environnement (.env)

```env
# Mistral AI
MISTRAL_API_KEY=votre_clé_mistral

# Telegram
TELEGRAM_BOT_TOKEN=8719315506:AAFcTN92hYWbQU96P6v25Q_FIgdOvIvpVEM
TELEGRAM_CHAT_ID=8484002816
TELEGRAM_ADMIN_CHAT_ID=8484002816

# Serveur
BASE_URL=http://54.226.12.85:8000
PUBLIC_IP=54.226.12.85

# Asterisk SIP
SIP_EXTENSION=1000
SIP_EXTENSION_PASS=restaurant2024

# SIP Trunk (optionnel)
SIP_TRUNK_HOST=
SIP_TRUNK_USER=
SIP_TRUNK_PASS=

# Whisper STT
WHISPER_MODEL=small

# Base de données
DATABASE_URL=sqlite:///./data/orders.db
```

---

## Personnaliser le menu

Éditez `menu.json` sur le serveur :

```bash
ssh -i ~/.ssh/labsuser.pem ubuntu@54.226.12.85
nano restaurant-agent/menu.json
docker compose -f restaurant-agent/docker-compose.yml restart
```

---

## Commandes utiles

```bash
# Logs en temps réel
docker compose logs -f

# Redémarrer tout
docker compose restart

# État des services
docker compose ps

# Logs Asterisk (appels)
docker compose logs asterisk -f

# CLI Asterisk interactif
docker exec -it restaurant-asterisk asterisk -rvvvv

# Commandes CLI Asterisk utiles
# pjsip show endpoints        → voir les extensions SIP
# pjsip show contacts         → voir les clients connectés
# dialplan show restaurants   → voir le dialplan
# core show channels          → voir les appels en cours

# Base de données SQLite
docker exec -it restaurant-agent sqlite3 /app/data/orders.db "SELECT * FROM orders ORDER BY created_at DESC LIMIT 10;"

# Export CSV
curl http://54.226.12.85:8000/export/csv -o commandes.csv
```

---

## Comparatif solutions téléphonie

| Solution | Coût | Complexité | Choix |
|---|---|---|---|
| **Asterisk** | Gratuit | Moyenne | ✅ **Utilisé** |
| Twilio | ~0.01$/min | Faible | Remplacé |
| FreeSWITCH | Gratuit | Élevée | Non |
| FreePBX | Gratuit | Élevée | Non |

---

## Infrastructure AWS

| Ressource | Valeur |
|---|---|
| Instance ID | `i-061659d76dd7dae81` |
| Type | `t3.medium` (2 vCPU, 4 GB RAM) |
| Elastic IP | `54.226.12.85` |
| Région | `us-east-1` |
| Stockage | 30 GB gp3 |
| Clé SSH | `vockey` (`~/.ssh/labsuser.pem`) |
| OS | Ubuntu 22.04 LTS |

---

## Tests de validation

```bash
# 1. Health check
curl http://54.226.12.85:8000/health

# 2. Simuler une commande (sans appel)
curl -X POST http://54.226.12.85:8000/api/internal/order \
  -H 'Content-Type: application/json' \
  -d '{
    "call_sid": "TEST001",
    "caller_id": "+21698765432",
    "order": {
      "customer_name": "Ahmed",
      "customer_phone": "98765432",
      "delivery_type": "livraison",
      "address": "Rue Bourguiba, Kairouan",
      "items": [{"product_key": "pizza_margherita", "product_name": "Pizza Margherita", "quantity": 2, "unit_price": 12}],
      "total": 24
    }
  }'

# 3. Voir les commandes
curl http://54.226.12.85:8000/api/orders | python3 -m json.tool

# 4. Dashboard
open http://54.226.12.85:8000

# 5. Test SIP (Asterisk CLI)
ssh -i ~/.ssh/labsuser.pem ubuntu@54.226.12.85
docker exec restaurant-asterisk asterisk -rx 'pjsip show endpoints'
docker exec restaurant-asterisk asterisk -rx 'pjsip show contacts'
```

---

## Améliorations futures

| Amélioration | Effort | Impact |
|---|---|---|
| SIP trunk VoIP.ms (vrai numéro) | Faible | ⭐⭐⭐⭐ |
| TTS amélioré (ElevenLabs/Coqui) | Moyen | ⭐⭐⭐ |
| Rappel client si commande incomplète | Faible | ⭐⭐⭐ |
| Interface admin menu en ligne | Moyen | ⭐⭐⭐ |
| Notifications SMS client | Faible | ⭐⭐⭐ |
| Graphiques dashboard (Chart.js) | Faible | ⭐⭐ |
| Redis pour pics d'appels | Moyen | ⭐⭐ |
| Kubernetes (K3s) | Élevé | ⭐ |
