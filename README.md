# Guide complet — Agent Vocal Restaurant (FR & TN)

## Architecture

```
MizuDroid (SIP) ──► Asterisk PBX ──► AGI (Python)
                                         │
                         ┌───────────────┼───────────────┐
                         ▼               ▼               ▼
                   Whisper STT      Mistral LLM      gTTS / Piper TTS
                   (local, free)    (API key)        (gratuit)
                         └───────────────┼───────────────┘
                                         ▼
                                  Telegram Bot  +  FastAPI Dashboard
```

## Projets disponibles

| Dossier | Langue | STT | TTS |
|---------|--------|-----|-----|
| `restaurant-agent/` | Français | Whisper small (fr) | Piper fr_FR-upmc-medium |
| `tunisian-restaurant-agent/` | Arabe tunisien | Whisper small (ar) | gTTS arabe |

---

## Étape 1 — Prérequis locaux

### 1.1 Clé SSH AWS
La clé doit avoir les permissions correctes :
```bash
chmod 600 ~/.ssh/labsuser.pem
```

### 1.2 Terraform installé
```bash
terraform --version   # doit afficher >= 1.0
```

### 1.3 Variables d'environnement (`.env`)
Chaque projet contient un fichier `.env`. Vérifier :
```
MISTRAL_API_KEY=<clé Mistral>
TELEGRAM_BOT_TOKEN=<token bot Telegram>
TELEGRAM_CHAT_ID=<chat ID>
PUBLIC_IP=<IP publique EC2>
SIP_EXTENSION=1000
SIP_EXTENSION_PASS=restaurant2024   # ou tunisian2024
WHISPER_MODEL=small
```

---

## Étape 2 — Créer le serveur avec Terraform

### 2.1 Initialiser et déployer
```bash
cd ~/Agent_vocal/restaurant-agent/terraform

terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

Terraform crée automatiquement :
- Instance EC2 **t3.medium** (2 vCPU, 4 Go RAM)
- Elastic IP fixe
- Security Group (ports 22, 8000, 5060/udp, 10000-10100/udp)
- Installation Docker + Docker Compose sur l'instance
- Upload et démarrage du projet

### 2.2 Récupérer l'IP publique
```bash
terraform output elastic_ip
# Ex: 54.226.12.85
```

Mettre à jour `.env` avec cette IP :
```
PUBLIC_IP=54.226.12.85
BASE_URL=http://54.226.12.85:8000
```

### 2.3 Vérifier le déploiement
```bash
ssh -i ~/.ssh/labsuser.pem ubuntu@54.226.12.85
docker ps
# Doit afficher: restaurant-asterisk (Up) et restaurant-agent (healthy)
```

### 2.4 Détruire le serveur (économie de coûts)
```bash
terraform destroy
```

---

## Étape 3 — Déploiement manuel (sans Terraform)

Si le serveur existe déjà :

### 3.1 Déployer l'agent français
```bash
rsync -av --exclude='data/' --exclude='__pycache__/' \
  -e "ssh -i ~/.ssh/labsuser.pem" \
  ~/Agent_vocal/restaurant-agent/ \
  ubuntu@54.226.12.85:~/restaurant-agent/

ssh -i ~/.ssh/labsuser.pem ubuntu@54.226.12.85 \
  "cd ~/restaurant-agent && docker compose up -d --build"
```

### 3.2 Déployer l'agent tunisien
```bash
rsync -av --exclude='data/' --exclude='__pycache__/' \
  -e "ssh -i ~/.ssh/labsuser.pem" \
  ~/Agent_vocal/tunisian-restaurant-agent/ \
  ubuntu@54.226.12.85:~/tunisian-restaurant-agent/

ssh -i ~/.ssh/labsuser.pem ubuntu@54.226.12.85 \
  "cd ~/tunisian-restaurant-agent && docker compose up -d --build"
```

> **Important** : les deux agents ne peuvent pas tourner en même temps (même port SIP 5060). Utiliser `switch-agent.sh`.

---

## Étape 4 — Basculer entre les agents

Un script `switch-agent.sh` est disponible sur le serveur :

```bash
ssh -i ~/.ssh/labsuser.pem ubuntu@54.226.12.85

# Passer à l'agent français
./switch-agent.sh fr

# Passer à l'agent tunisien
./switch-agent.sh tn
```

Le script arrête l'agent actif et démarre l'autre.  
Le premier démarrage prend ~3 min (Whisper télécharge le modèle).

---

## Étape 5 — Configuration MizuDroid

### 5.1 Installer MizuDroid
Télécharger depuis Google Play : **MizuDroid SIP Softphone**

### 5.2 Configurer le compte SIP
Dans MizuDroid → Settings → SIP Account :

| Champ | Valeur |
|-------|--------|
| SIP Server | `54.226.12.85` |
| Username | `1000` |
| Password | `restaurant2024` (FR) ou `tunisian2024` (TN) |
| Port | `5060` |
| Transport | UDP |

### 5.3 Vérifier l'enregistrement
En haut de MizuDroid : indicateur **vert "Registered"**  
Si rouge : attendre 30s ou redémarrer MizuDroid.

### 5.4 Tester un appel
Composer **7000** → l'agent répond en français ou en arabe tunisien.

### 5.5 Après redémarrage des containers
MizuDroid perd son enregistrement SIP à chaque redémarrage Asterisk.  
Attendre ~30 secondes que le statut redevienne vert avant d'appeler.

---

## Étape 6 — Configuration Telegram

### 6.1 Créer un bot
1. Ouvrir Telegram → rechercher **@BotFather**
2. `/newbot` → choisir un nom et un username
3. Copier le **token** fourni

### 6.2 Obtenir son Chat ID
1. Envoyer un message au bot
2. Ouvrir : `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Chercher `"id"` dans `"chat"` → c'est votre `TELEGRAM_CHAT_ID`

### 6.3 Mettre à jour `.env`
```
TELEGRAM_BOT_TOKEN=8719315506:AAFcTN92hYWbQU96P6v25Q_FIgdOvIvpVEM
TELEGRAM_CHAT_ID=8484002816
```

### 6.4 Format de notification reçue
Après chaque commande confirmée, Telegram reçoit :
```
📦 Nouvelle Commande — REF12345

👤 Client: Mohamed Ben Ali
📞 Téléphone: 99 123 456

🍽️ Produits:
  • 1x كسكسي بالدجاج — 15 TND
  • 2x بريك بالتونة — 8 TND

💰 Total: 23 TND

🚗 توصيل
📍 Adresse: 12 rue Habib Bourguiba

🕒 2026-05-31 16:00
```

---

## Étape 7 — Vérifier que tout fonctionne

### 7.1 État des containers
```bash
ssh -i ~/.ssh/labsuser.pem ubuntu@54.226.12.85 \
  "docker ps --format 'table {{.Names}}\t{{.Status}}'"
```
Attendu :
```
NAMES               STATUS
restaurant-asterisk  Up X minutes
restaurant-agent     Up X minutes (healthy)
```

### 7.2 Services STT / TTS internes
```bash
ssh -i ~/.ssh/labsuser.pem ubuntu@54.226.12.85 \
  "docker exec restaurant-asterisk curl -s http://127.0.0.1:5001/ && echo ' Whisper OK'"
  "docker exec restaurant-asterisk curl -s http://127.0.0.1:5002/ && echo ' TTS OK'"
```

### 7.3 Fichiers audio statiques
```bash
ssh -i ~/.ssh/labsuser.pem ubuntu@54.226.12.85 \
  "docker exec restaurant-asterisk ls /var/lib/asterisk/sounds/restaurant_*.wav"
```
Attendu : `restaurant_greeting.wav`, `restaurant_silence.wav`, `restaurant_timeout.wav`, `restaurant_error.wav`

### 7.4 Logs en temps réel
```bash
# Logs AGI (appels)
ssh -i ~/.ssh/labsuser.pem ubuntu@54.226.12.85 \
  "docker exec restaurant-asterisk tail -f /var/log/asterisk/restaurant_agi.log"

# Logs Whisper STT
ssh -i ~/.ssh/labsuser.pem ubuntu@54.226.12.85 \
  "docker exec restaurant-asterisk tail -f /var/log/asterisk/whisper_service.log"

# Logs TTS
ssh -i ~/.ssh/labsuser.pem ubuntu@54.226.12.85 \
  "docker exec restaurant-asterisk tail -f /var/log/asterisk/edgetts_service.log"
```

### 7.5 Dashboard web
Ouvrir dans le navigateur : `http://54.226.12.85:8000`

---

## Étape 8 — Menu du restaurant

### Modifier le menu
Éditer `menu.json` à la racine du projet :

**Agent français** (`restaurant-agent/menu.json`) :
```json
{
  "restaurant": { "nom": "Restaurant Al Baraka", ... },
  "menu": {
    "pizza_margherita": { "nom": "Pizza Margherita", "prix": 12 },
    ...
  }
}
```

**Agent tunisien** (`tunisian-restaurant-agent/menu.json`) :
```json
{
  "restaurant": { "nom": "مطعم البركة", ... },
  "menu": {
    "couscous_djeij": { "nom": "كسكسي بالدجاج", "prix": 15 },
    ...
  }
}
```

Après modification :
```bash
rsync -av -e "ssh -i ~/.ssh/labsuser.pem" menu.json ubuntu@54.226.12.85:~/restaurant-agent/menu.json
ssh -i ~/.ssh/labsuser.pem ubuntu@54.226.12.85 "cd ~/restaurant-agent && docker compose restart asterisk"
```

---

## Coûts

| Service | Coût |
|---------|------|
| EC2 t3.medium | ~$0.0416/h ≈ $30/mois |
| Elastic IP (si arrêtée) | $0.005/h |
| Mistral small-latest | ~$0.001 par appel |
| Whisper STT | Gratuit (local) |
| gTTS / Piper TTS | Gratuit |
| Telegram | Gratuit |

> Pour économiser : `terraform destroy` quand non utilisé, `terraform apply` pour relancer.

---

## Dépannage rapide

| Problème | Solution |
|----------|----------|
| MizuDroid non enregistré | Attendre 30s, vérifier IP dans settings |
| "No response from server" | MizuDroid a perdu son enregistrement → attendre vert |
| Agent ne répond pas | `docker logs restaurant-asterisk --tail 50` |
| Whisper lent au 1er appel | Normal — modèle en cache après 1er transcription |
| Telegram ne reçoit rien | Vérifier `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID` dans `.env` |
| gTTS erreur réseau | Vérifier que le container a accès internet |
| Switch agent tn ne démarre pas | Première fois = ~3-5 min pour télécharger Whisper |
