#!/bin/bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║     Restaurant AI Agent — Installation       ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── Prérequis ──────────────────────────────────────────────────────

command -v docker >/dev/null 2>&1 || error "Docker n'est pas installé. Installez-le depuis https://docs.docker.com/engine/install/"
command -v docker-compose >/dev/null 2>&1 || error "Docker Compose n'est pas installé."
info "Docker et Docker Compose détectés."

# ── Fichier .env ───────────────────────────────────────────────────

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        warn "Fichier .env créé à partir de .env.example"
        warn "IMPORTANT: Éditez .env avec vos vraies clés avant de continuer!"
        warn "  → nano .env"
        echo ""
        read -p "Appuyez sur Entrée après avoir configuré .env... " _
    else
        error "Fichier .env.example introuvable. Vérifiez votre installation."
    fi
else
    info "Fichier .env existant trouvé."
fi

# ── Vérification variables ─────────────────────────────────────────

source .env 2>/dev/null || true

missing=0
for var in MISTRAL_API_KEY TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN BASE_URL; do
    val="${!var:-}"
    if [ -z "$val" ] || [[ "$val" == *"your_"* ]] || [[ "$val" == *"example"* ]]; then
        warn "Variable non configurée: $var"
        missing=$((missing + 1))
    fi
done

if [ $missing -gt 0 ]; then
    error "$missing variable(s) non configurée(s) dans .env. Corrigez-les et relancez."
fi
info "Variables d'environnement OK."

# ── Répertoires ────────────────────────────────────────────────────

mkdir -p data
info "Répertoire data/ créé."

# ── Build & Start ──────────────────────────────────────────────────

info "Construction de l'image Docker..."
docker-compose build --no-cache

info "Démarrage du conteneur..."
docker-compose up -d

# ── Health check ───────────────────────────────────────────────────

info "Attente du démarrage (15s)..."
sleep 15

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    info "Agent démarré avec succès! ✓"
else
    warn "L'agent ne répond pas encore (code=$HTTP_CODE). Vérifiez les logs:"
    warn "  docker-compose logs -f agent"
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║            Installation terminée!            ║"
echo "╠══════════════════════════════════════════════╣"
echo "║  Dashboard : http://localhost:8000           ║"
echo "║  Health    : http://localhost:8000/health    ║"
echo "║  API JSON  : http://localhost:8000/api/orders║"
echo "║  Export CSV: http://localhost:8000/export/csv║"
echo "╠══════════════════════════════════════════════╣"
echo "║  Logs      : docker-compose logs -f agent    ║"
echo "║  Stop      : docker-compose down             ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
info "Configurez Twilio pour pointer vers: ${BASE_URL:-<BASE_URL>}/webhook/voice"
