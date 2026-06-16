#!/bin/bash
# =============================================================================
# PhantomDev — AWS EC2 Production Deployment Script
# =============================================================================
# Recommended: t3.large (2 vCPU, 8GB RAM) — Ubuntu 22.04 LTS
# Storage: 30GB gp3
# Security Group: Allow 22 (SSH), 80 (HTTP), 443 (HTTPS), 5555 (Flower)
#
# Usage:
#   1. SSH into EC2:  ssh -i key.pem ubuntu@YOUR_EC2_IP
#   2. Run:           bash ec2_deploy.sh
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

info "Starting PhantomDev production deployment..."
EC2_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "unknown")
info "EC2 Public IP: $EC2_IP"

# ── 1. System update ──────────────────────────────────────────────────────────
info "Updating system packages..."
sudo apt-get update -y && sudo apt-get upgrade -y
sudo apt-get install -y git curl wget unzip htop

# ── 2. Docker ─────────────────────────────────────────────────────────────────
info "Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker $USER
    sudo systemctl enable docker
    sudo systemctl start docker
    info "Docker installed"
else
    info "Docker already installed: $(docker --version)"
fi

# Docker Compose plugin
sudo apt-get install -y docker-compose-plugin
info "Docker Compose: $(docker compose version)"

# ── 3. Ollama ─────────────────────────────────────────────────────────────────
info "Installing Ollama..."
if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
    sudo systemctl enable ollama
    sudo systemctl start ollama
    sleep 5
    info "Ollama installed"
else
    info "Ollama already installed"
fi

# Pull model in background
info "Pulling qwen2.5-coder:7b (~4.5GB, runs in background)..."
nohup ollama pull qwen2.5-coder:7b > /tmp/ollama-pull.log 2>&1 &
PULL_PID=$!
info "Model pull started (PID $PULL_PID). Continuing deployment..."

# ── 4. Clone PhantomDev ───────────────────────────────────────────────────────
info "Setting up PhantomDev..."
APP_DIR="/home/$USER/phantomdev"

if [ -d "$APP_DIR" ]; then
    warning "Directory exists. Pulling latest changes..."
    cd "$APP_DIR" && git pull
else
    # Replace with your actual GitHub repo URL
    git clone https://github.com/YOUR_USERNAME/phantomdev.git "$APP_DIR"
    cd "$APP_DIR"
fi

# ── 5. Environment ────────────────────────────────────────────────────────────
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    warning "Created .env from template. EDIT IT NOW before continuing!"
    warning "Required: GITHUB_TOKEN, TARGET_REPO, PHANTOMDEV_API_KEY"
    echo ""
    echo "  nano $APP_DIR/.env"
    echo ""
    read -p "Press ENTER after editing .env to continue..."
fi

# ── 6. Build frontend ─────────────────────────────────────────────────────────
info "Building React frontend..."
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

cd "$APP_DIR/frontend"
npm install --silent
npm run build
info "Frontend built: $(ls dist/ | wc -l) files"

# ── 7. Wait for model pull ────────────────────────────────────────────────────
info "Waiting for Ollama model download to complete..."
wait $PULL_PID || true
if ollama list | grep -q "qwen2.5-coder:7b"; then
    info "Model qwen2.5-coder:7b ready"
else
    warning "Model may still be downloading. Check: tail -f /tmp/ollama-pull.log"
fi

# ── 8. Launch with Docker Compose ─────────────────────────────────────────────
info "Starting PhantomDev services..."
cd "$APP_DIR"
cp infra/docker-compose.yml docker-compose.yml

# Override Ollama URL to use host Ollama (already installed)
export OLLAMA_BASE_URL="http://host-gateway:11434"

docker compose up -d --build

# ── 9. Wait for services ──────────────────────────────────────────────────────
info "Waiting for services to be healthy..."
sleep 30

MAX_WAIT=120
ELAPSED=0
until curl -sf http://localhost:8000/health > /dev/null 2>&1; do
    sleep 5
    ELAPSED=$((ELAPSED + 5))
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        error "API health check failed after ${MAX_WAIT}s. Check: docker compose logs api"
    fi
    echo -n "."
done
echo ""
info "API is healthy!"

# ── 10. Swap Nginx to connect to Docker Ollama ────────────────────────────────
# Actually Ollama runs on host, API is in Docker pointing to host Ollama
# Update docker-compose to use host.docker.internal
docker compose exec api curl -sf http://ollama:11434/api/tags > /dev/null 2>&1 && \
    info "Ollama reachable from API container" || \
    warning "Ollama not yet reachable from container — may need a minute"

# ── 11. Setup UFW firewall ────────────────────────────────────────────────────
info "Configuring firewall..."
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw allow 5555/tcp  # Flower (restrict this in production!)
sudo ufw --force enable
info "Firewall configured"

# ── 12. Docker restart policy ─────────────────────────────────────────────────
# Already set in docker-compose (restart: unless-stopped)
# Ensure Docker auto-starts
sudo systemctl enable docker
info "Docker configured to auto-start on reboot"

# ── 13. Summary ───────────────────────────────────────────────────────────────
echo ""
echo "======================================================================"
echo "  ✅ PhantomDev deployed successfully!"
echo "======================================================================"
echo ""
echo "  Dashboard:     http://$EC2_IP"
echo "  API docs:      http://$EC2_IP/api/docs"
echo "  Health check:  http://$EC2_IP/health"
echo "  Flower (queue): http://$EC2_IP:5555"
echo ""
echo "  Useful commands:"
echo "    docker compose logs -f api       # API logs"
echo "    docker compose logs -f worker    # Celery worker logs"
echo "    docker compose logs -f ollama    # Ollama logs"
echo "    docker compose ps                # Service status"
echo "    docker compose restart api       # Restart API"
echo ""
echo "  To update after code changes:"
echo "    cd ~/phantomdev"
echo "    git pull"
echo "    cd frontend && npm run build && cd .."
echo "    docker compose up -d --build api worker"
echo "======================================================================"
