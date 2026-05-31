#!/bin/bash
# Exécuté sur l'instance EC2 par Terraform après copie des fichiers
set -euo pipefail

cd /home/ubuntu/restaurant-agent

echo "=== [1/5] Attente Docker ==="
for i in {1..20}; do
    docker info >/dev/null 2>&1 && break
    echo "  Attente Docker... ($i)"
    sleep 5
done

echo "=== [2/5] Répertoires ==="
mkdir -p data
chmod 777 data

echo "=== [3/5] Configuration .env ==="
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  .env créé depuis .env.example"
fi

# Récupérer l'IP publique et l'injecter
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 || echo "")
if [ -n "$PUBLIC_IP" ]; then
    sed -i "s|^BASE_URL=.*|BASE_URL=http://${PUBLIC_IP}:8000|" .env
    sed -i "s|^PUBLIC_IP=.*|PUBLIC_IP=${PUBLIC_IP}|" .env
    # Ajouter PUBLIC_IP si absent
    grep -q "^PUBLIC_IP=" .env || echo "PUBLIC_IP=${PUBLIC_IP}" >> .env
    echo "  IP publique: ${PUBLIC_IP}"
fi

echo "=== [4/5] Build Docker ==="
docker compose build --no-cache

echo "=== [5/5] Démarrage ==="
docker compose up -d

echo ""
echo "=============================================="
echo "  Installation terminée!"
echo "  Dashboard : http://${PUBLIC_IP}:8000"
echo "  SIP test  : ${PUBLIC_IP}:5060"
echo "  SSH       : ssh -i ~/.ssh/labsuser.pem ubuntu@${PUBLIC_IP}"
echo "=============================================="
