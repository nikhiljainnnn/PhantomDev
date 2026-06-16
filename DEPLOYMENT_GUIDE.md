# PhantomDev — Production Deployment Guide

## Architecture Overview

```
Internet
    │
    ▼
EC2 Security Group (ports 80, 443, 22)
    │
    ▼
┌─────────────────────────────────────────────┐
│  Docker Network (public)                    │
│                                             │
│  ┌─────────┐    ┌──────────────────────┐   │
│  │  Nginx  │    │   Flower :5555       │   │
│  │ :80/443 │    │  (Celery monitor)    │   │
│  └────┬────┘    └──────────────────────┘   │
│       │                                     │
│  Docker Network (internal)                  │
│       │                                     │
│  ┌────▼────┐    ┌──────────┐               │
│  │   API   │    │  Worker  │               │
│  │ :8000   │    │ (Celery) │               │
│  └────┬────┘    └────┬─────┘               │
│       │              │                      │
│  ┌────▼──────────────▼─────┐               │
│  │         Redis            │               │
│  │  (task store + broker)   │               │
│  └─────────────────────────┘               │
│                                             │
│  ┌─────────────────────────┐               │
│  │         Ollama           │               │
│  │   (local LLM :11434)     │               │
│  └─────────────────────────┘               │
└─────────────────────────────────────────────┘
```

---

## STEP 1 — Launch EC2 Instance

**In AWS Console → EC2 → Launch Instance:**

| Setting | Value |
|---------|-------|
| Name | phantomdev-prod |
| AMI | Ubuntu Server 22.04 LTS |
| Instance type | t3.large (2 vCPU, 8GB RAM) |
| Key pair | Create new → download .pem file |
| Storage | 30GB gp3 |

**Security Group — Add inbound rules:**

| Port | Protocol | Source | Purpose |
|------|----------|--------|---------|
| 22 | TCP | Your IP only | SSH |
| 80 | TCP | 0.0.0.0/0 | HTTP |
| 443 | TCP | 0.0.0.0/0 | HTTPS |
| 5555 | TCP | Your IP only | Flower monitor |

Click **Launch Instance**. Wait ~60 seconds for it to start.

---

## STEP 2 — SSH into EC2

```bash
# On your Windows machine (PowerShell)
ssh -i "your-key.pem" ubuntu@YOUR_EC2_IP

# If permission error on Windows:
icacls "your-key.pem" /inheritance:r /grant:r "%username%:R"
```

---

## STEP 3 — Run the deployment script

```bash
# On EC2, download and run the deploy script
curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/phantomdev/main/scripts/ec2_deploy.sh | bash
```

**OR** copy files manually:

```bash
# On your local machine (PowerShell)
scp -i "your-key.pem" -r "C:\Users\Nikhil Singhvi\OneDrive\Desktop\PhantomDev\*" ubuntu@YOUR_EC2_IP:~/phantomdev/
```

The script automatically:
- Installs Docker, Docker Compose, Node.js, Git
- Installs Ollama and pulls the model
- Builds the React frontend
- Launches all Docker services
- Configures the firewall

---

## STEP 4 — Configure .env on EC2

```bash
nano ~/phantomdev/.env
```

Fill in these values:

```bash
GITHUB_TOKEN=ghp_your_token
TARGET_REPO=your_username/your_repo

# Generate API key:
# python3 -c "import secrets; print(secrets.token_hex(32))"
PHANTOMDEV_API_KEY=your_generated_key

FLOWER_PASSWORD=choose_strong_password

# Your EC2 IP or domain
ALLOWED_ORIGINS=http://YOUR_EC2_IP,https://yourdomain.com
```

After editing:
```bash
cd ~/phantomdev
docker compose up -d --build
```

---

## STEP 5 — Verify deployment

```bash
# All containers running?
docker compose ps

# Expected output:
# phantomdev-nginx    running   0.0.0.0:80->80/tcp
# phantomdev-api      running   (healthy)
# phantomdev-worker   running
# phantomdev-redis    running   (healthy)
# phantomdev-ollama   running   (healthy)
# phantomdev-flower   running   0.0.0.0:5555->5555/tcp

# API health check
curl http://YOUR_EC2_IP/health

# Expected:
# {"status":"ok","redis":"connected","celery":true,...}
```

Open in browser:
- **Dashboard**: `http://YOUR_EC2_IP`
- **Flower (queue monitor)**: `http://YOUR_EC2_IP:5555`
- **API docs**: `http://YOUR_EC2_IP/api/docs`

---

## STEP 6 — Update frontend API URL for production

The frontend currently hardcodes `http://localhost:8000`. Update it for production:

```jsx
// frontend/src/App.jsx — change lines 7-8:
const API = "/api";          // Goes through Nginx proxy
const WS_BASE = `ws${window.location.protocol === 'https:' ? 's' : ''}://${window.location.host}`;
```

Rebuild frontend on EC2:
```bash
cd ~/phantomdev/frontend
npm run build
docker compose restart nginx
```

---

## STEP 7 — (Optional) Add a domain + HTTPS

If you have a domain name (e.g. from Namecheap, GoDaddy, or AWS Route 53):

**Point domain to EC2:**
```
A record: yourdomain.com → YOUR_EC2_IP
```

**Get free SSL certificate (Let's Encrypt):**
```bash
# On EC2
sudo apt-get install -y certbot
sudo certbot certonly --standalone -d yourdomain.com --email your@email.com --agree-tos

# Certs stored at: /etc/letsencrypt/live/yourdomain.com/
```

**Switch Nginx to HTTPS config:**
```bash
# Update domain in nginx.conf
sed -i 's/YOUR_DOMAIN/yourdomain.com/g' ~/phantomdev/infra/nginx/nginx.conf

# Swap to HTTPS config
cp ~/phantomdev/infra/nginx/nginx.conf /path/to/nginx/conf.d/default.conf
docker compose restart nginx
```

**Auto-renew SSL:**
```bash
# Add to crontab
crontab -e
# Add this line:
0 0 * * * certbot renew --quiet && docker compose -f ~/phantomdev/docker-compose.yml restart nginx
```

---

## Useful commands on EC2

```bash
# View live logs
docker compose logs -f api        # API logs
docker compose logs -f worker     # Pipeline execution logs
docker compose logs -f nginx      # Request logs

# Restart a service
docker compose restart api
docker compose restart worker

# Rebuild after code change
git pull
cd frontend && npm run build && cd ..
docker compose up -d --build api worker

# Check Redis task store
docker compose exec redis redis-cli keys "phantomdev:*"

# Check Celery queue
docker compose exec worker celery -A worker.celery_app inspect active

# View Ollama model status
curl http://localhost:11434/api/tags

# Resource usage
docker stats

# Disk usage
df -h
docker system df
```

---

## Cost estimate (AWS)

| Resource | Type | Monthly cost |
|----------|------|-------------|
| EC2 | t3.large | ~$60 |
| Storage | 30GB gp3 | ~$2.40 |
| Data transfer | ~10GB | ~$0.90 |
| **Total** | | **~$63/month** |

**To reduce cost:**
- Use **t3.medium** ($30/mo) with `qwen2.5-coder:3b` model (less capable but runs on 4GB RAM)
- Stop EC2 when not using it (tasks persist in Redis)
- Use **Spot Instance** for 70% savings (risk of interruption)

---

## Monitoring checklist

After going live, check these daily for the first week:

```bash
# 1. All containers healthy?
docker compose ps

# 2. Disk not full? (Ollama model + ChromaDB can grow)
df -h

# 3. Memory not exhausted?
free -h

# 4. Any failed tasks?
docker compose exec redis redis-cli keys "phantomdev:task:*" | wc -l

# 5. Worker processing jobs?
# Visit http://YOUR_EC2_IP:5555
```
