#!/bin/bash
# scripts/ec2_setup.sh
# One-shot EC2 (Ubuntu 22.04/24.04) bootstrap for PhantomDev
# Run: bash ec2_setup.sh
# Takes ~10 mins on t3.medium (recommended for Ollama + 7B model)

set -e
echo "🚀 PhantomDev EC2 Setup"

# ── System update ───────────────────────────────────────────────────────────
sudo apt-get update -y
sudo apt-get upgrade -y

# ── Docker ──────────────────────────────────────────────────────────────────
echo "📦 Installing Docker..."
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo systemctl enable docker
sudo systemctl start docker
sudo apt-get install -y docker-compose-plugin

# ── Node.js 20 (for frontend) ───────────────────────────────────────────────
echo "📦 Installing Node.js 20..."
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# ── Git ─────────────────────────────────────────────────────────────────────
sudo apt-get install -y git curl wget

# ── Ollama (for local LLM) ───────────────────────────────────────────────────
echo "🧠 Installing Ollama..."
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable ollama
sudo systemctl start ollama
sleep 5

# Pull model (runs in background, takes ~5 min)
echo "📥 Pulling qwen2.5-coder:7b (~4.5GB, this takes a few minutes)..."
ollama pull qwen2.5-coder:7b &

# ── Clone PhantomDev ────────────────────────────────────────────────────────
echo "📂 Setting up PhantomDev..."
cd /home/$USER
git clone https://github.com/YOUR_USERNAME/phantomdev.git
cd phantomdev

# ── Environment ─────────────────────────────────────────────────────────────
cp .env.example .env
echo ""
echo "⚠️  EDIT YOUR .env FILE NOW:"
echo "   nano /home/$USER/phantomdev/.env"
echo ""
echo "   Set: GITHUB_TOKEN, TARGET_REPO"
echo "   OLLAMA_BASE_URL=http://localhost:11434 (already set)"
echo ""

# ── Open firewall ports ──────────────────────────────────────────────────────
# In AWS Console: Security Group → Inbound Rules → Add:
# Port 3000 (frontend), Port 8000 (API)
echo "🔥 IMPORTANT: Open ports 3000 and 8000 in your EC2 Security Group"

# ── Docker Compose ───────────────────────────────────────────────────────────
echo "🐳 Starting services..."
# Wait for model pull to complete
wait
echo "✅ Model pulled!"

# Use the compose file
cp infra/docker-compose.yml docker-compose.yml
docker compose up -d

echo ""
echo "✅ PhantomDev is running!"
echo ""
EC2_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "YOUR_EC2_IP")
echo "   Dashboard: http://$EC2_IP:3000"
echo "   API docs:  http://$EC2_IP:8000/docs"
echo "   Health:    http://$EC2_IP:8000/health"
echo ""
echo "   Logs: docker compose logs -f api"
echo "   Stop: docker compose down"
