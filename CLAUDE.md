# CLAUDE.md — Reprise du projet Agent Vocal Restaurant

## Contexte

Projet d'agent vocal IA pour restaurant, répondant aux appels téléphoniques SIP.  
Deux versions : **français** et **arabe tunisien (darija)**.  
Stack : Asterisk PBX + Python AGI + Mistral LLM + Whisper STT + TTS local/cloud.

---

## Serveur actuel

| Paramètre | Valeur |
|-----------|--------|
| IP publique | `54.226.12.85` (Elastic IP AWS) |
| Région | `us-east-1` |
| Instance | `t3.medium` (2 vCPU, 4 Go RAM) |
| SSH | `ssh -i ~/.ssh/labsuser.pem ubuntu@54.226.12.85` |
| Clé SSH locale | `~/.ssh/labsuser.pem` (chmod 600 obligatoire) |

---

## Structure des projets

```
/home/grassa/Agent_vocal/
├── README.md                          ← Guide complet (aussi sur GitHub)
├── CLAUDE.md                          ← Ce fichier
├── restaurant-agent/                  ← Agent FRANÇAIS
│   ├── .env                           ← Secrets (non commité)
│   ├── .env.example                   ← Template public
│   ├── docker-compose.yml
│   ├── menu.json                      ← Menu du restaurant
│   ├── Dockerfile                     ← FastAPI app
│   ├── requirements.txt
│   ├── app/                           ← FastAPI (dashboard + API)
│   ├── asterisk/
│   │   ├── Dockerfile                 ← Asterisk + Python + Piper
│   │   ├── start.sh                   ← Config Asterisk + démarrage services
│   │   └── agi/
│   │       ├── restaurant_agi.py      ← Script principal (STT→LLM→TTS)
│   │       ├── whisper_service.py     ← HTTP service Whisper (port 5001)
│   │       ├── piper_service.py       ← HTTP service Piper TTS (port 5002)
│   │       ├── requirements.txt
│   │       └── menu.json              ← Copie du menu pour le container
│   ├── terraform/                     ← Infrastructure AWS
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   └── scripts/
└── tunisian-restaurant-agent/         ← Agent TUNISIEN (darija)
    ├── .env                           ← Secrets (non commité)
    ├── .env.example
    ├── docker-compose.yml
    ├── menu.json                      ← Menu en arabe
    ├── Dockerfile
    ├── requirements.txt
    ├── app/                           ← Même FastAPI que FR
    └── asterisk/
        ├── Dockerfile
        ├── start.sh
        └── agi/
            ├── restaurant_agi.py      ← AGI en darija tunisien
            ├── whisper_service.py     ← Whisper Arabic (language="ar")
            ├── edgetts_service.py     ← gTTS Arabic (port 5002)
            └── requirements.txt
```

---

## État actuel des containers (sur le serveur)

L'agent **tunisien** est actif en dernier. Pour vérifier :
```bash
ssh -i ~/.ssh/labsuser.pem ubuntu@54.226.12.85 "docker ps"
```

Pour basculer :
```bash
./switch-agent.sh fr   # Agent français
./switch-agent.sh tn   # Agent tunisien
```

---

## Stack technique

### Agent français (`restaurant-agent/`)
| Composant | Techno | Détail |
|-----------|--------|--------|
| STT | `faster-whisper` small | `language="fr"`, VAD, initial_prompt resto |
| TTS | `piper-tts` | Voix `fr_FR-upmc-medium` (ONNX, féminine) |
| LLM | Mistral `mistral-small-latest` | JSON mode, protocole commande |
| SIP | Asterisk 18 + PJSIP | Extension 7000, port 5060 UDP |
| Services | whisper:5001, piper:5002 | Persistants en RAM entre appels |

### Agent tunisien (`tunisian-restaurant-agent/`)
| Composant | Techno | Détail |
|-----------|--------|--------|
| STT | `faster-whisper` small | `language="ar"`, initial_prompt arabe |
| TTS | `gTTS` | `lang="ar"`, Google TTS gratuit |
| LLM | Mistral `mistral-small-latest` | Prompt en darija tunisien |
| SIP | Asterisk 18 + PJSIP | Extension 7000, port 5060 UDP |
| Services | whisper:5001, gtts:5002 | |

---

## Secrets / Variables d'environnement

Fichier `.env` dans chaque projet (jamais commité) :
```
MISTRAL_API_KEY=8kXpojpl3q10CBQ2YJ7JJOYhIYyCcgww
TELEGRAM_BOT_TOKEN=8719315506:AAFcTN92hYWbQU96P6v25Q_FIgdOvIvpVEM
TELEGRAM_CHAT_ID=8484002816
PUBLIC_IP=54.226.12.85
SIP_EXTENSION=1000
SIP_EXTENSION_PASS=restaurant2024   # ou tunisian2024
WHISPER_MODEL=small
DATABASE_URL=sqlite:///./data/orders.db
```

---

## MizuDroid (test SIP)

| Champ | Valeur |
|-------|--------|
| SIP Server | `54.226.12.85` |
| Username | `1000` |
| Password FR | `restaurant2024` |
| Password TN | `tunisian2024` |
| Extension à composer | `7000` |

Après chaque redémarrage des containers : attendre le statut vert **Registered** avant d'appeler.

---

## GitHub

```
Repo  : https://github.com/ngrassa/agent_vocal
Branch: main
```

Commandes de sync :
```bash
cd /home/grassa/Agent_vocal

# Pousser des changements
git add <fichiers>
git commit -m "message"
git push

# Sync un projet vers le serveur
rsync -av --exclude='data/' --exclude='__pycache__/' \
  -e "ssh -i ~/.ssh/labsuser.pem" \
  restaurant-agent/ ubuntu@54.226.12.85:~/restaurant-agent/
```

---

## Problèmes résolus (ne pas rerégler)

| Problème | Fix appliqué |
|----------|-------------|
| Audio unidirectionnel (MizuDroid) | `rtp_symmetric=yes`, `force_rport=yes`, `rewrite_contact=yes` dans PJSIP |
| SIGPIPE silencieux au raccrochage | `signal.signal(SIGPIPE, SIG_IGN)` + classe `HangupError` |
| Chemin AGI Ubuntu | `/usr/share/asterisk/agi-bin/` |
| Whisper tiny mauvais (FR) | Modèle `small` + `initial_prompt` vocabulaire resto |
| edge-tts 403 (TN) | Remplacé par `gTTS lang="ar"` (Microsoft bloque l'API WebSocket) |
| Latence élevée | Services Whisper/Piper persistants en RAM, audio statique pré-généré, `silence_s=1` |

---

## Commandes utiles

```bash
# Logs AGI en temps réel
docker exec restaurant-asterisk tail -f /var/log/asterisk/restaurant_agi.log
docker exec tunisian-asterisk tail -f /var/log/asterisk/restaurant_agi.log

# Logs Whisper
docker exec <container> tail -f /var/log/asterisk/whisper_service.log

# Regénérer les fichiers audio statiques manuellement
docker exec <container> python3 -c "
import urllib.request, subprocess, os
# ... voir start.sh section PYEOF
"

# Rebuild complet d'un agent
cd ~/restaurant-agent && docker compose down && docker compose up -d --build

# Terraform
cd restaurant-agent/terraform
terraform init && terraform apply   # Créer serveur
terraform destroy                   # Supprimer serveur
```

---

## Prochaines améliorations possibles

- [ ] Support STT multilingue auto-detect (sans fixer `language=`)
- [ ] Dashboard web pour éditer le menu en live
- [ ] Reconnexion SIP automatique dans MizuDroid après restart
- [ ] TTS tunisien de meilleure qualité si une voix darija gratuite sort
- [ ] Tests automatisés de l'AGI (simuler canal Asterisk)
- [ ] Déploiement multi-restaurants sur un seul serveur (ports SIP différents)
