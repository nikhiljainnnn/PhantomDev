# PhantomDev — Complete Step-by-Step Implementation Guide

## Prerequisites Check

Run this first. Everything below assumes these pass:

```bash
python --version     # 3.11+
node --version       # 20+
docker --version     # 24+
git --version        # any recent version
```

---

## PHASE 1 — Local Setup (Day 1, ~2 hours)

### Step 1: Install Ollama + pull the coding model

```bash
# Windows (PowerShell as Administrator)
winget install Ollama.Ollama

# OR Linux/macOS
curl -fsSL https://ollama.com/install.sh | sh

# Pull the coding model (~4.5 GB, takes 5-10 mins)
ollama pull qwen2.5-coder:7b

# Verify it works
ollama run qwen2.5-coder:7b "Write a Python hello world function"
# You should see code output. Ctrl+D to exit.
```

**Why qwen2.5-coder:7b?**  
Best free coding model at 7B params. Outperforms GPT-3.5 on code tasks.
Runs on 8GB RAM. Upgrade to `qwen2.5-coder:14b` if you have 16GB+ RAM.

---

### Step 2: Clone and configure

```bash
git clone https://github.com/YOUR_USERNAME/phantomdev.git
cd phantomdev

cp .env.example .env
```

Edit `.env` — minimum required settings:

```bash
# Leave these as-is for local development:
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:7b
WORKSPACE_DIR=./workspace
CHROMA_PERSIST_DIR=./data/chroma

# Optional (for real GitHub PR creation):
# GITHUB_TOKEN=ghp_yourtoken
# TARGET_REPO=owner/reponame
```

---

### Step 3: Python virtual environment + install dependencies

```bash
# Create venv
python -m venv venv

# Activate (Windows PowerShell)
.\venv\Scripts\Activate.ps1
# Activate (Linux/macOS/Git Bash)
source venv/bin/activate

# Install all dependencies
pip install -r requirements.txt

# Verify key packages
python -c "import autogen; print('AutoGen:', autogen.__version__)"
python -c "import chromadb; print('ChromaDB OK')"
python -c "import fastapi; print('FastAPI OK')"
```

---

### Step 4: Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

---

### Step 5: Run the test suite to verify everything works

```bash
# Run all unit tests (should pass without Ollama)
python -m pytest tests/ -v --tb=short

# Expected output:
# tests/test_pipeline.py::TestTaskState::test_initial_state PASSED
# tests/test_pipeline.py::TestTaskState::test_set_status PASSED
# ... (12 tests total)
# ✅ 12 passed
```

---

### Step 6: Start all services

**Option A — Individual terminals (easier for development):**

Terminal 1 — Ollama (if not already running as service):
```bash
ollama serve
```

Terminal 2 — API:
```bash
source venv/bin/activate
uvicorn api.main:app --reload --port 8000
```

Terminal 3 — Frontend:
```bash
cd frontend
npm run dev
```

**Option B — Docker Compose (single command):**
```bash
cp infra/docker-compose.yml docker-compose.yml
docker compose up
# First run takes ~10 mins (pulls Ollama image + model)
```

---

### Step 7: Verify everything is running

```bash
# API health check
curl http://localhost:8000/health

# Expected:
# {"status":"ok","tasks_in_memory":0,"ollama_url":"http://localhost:11434",...}

# Open dashboard
open http://localhost:3000   # macOS
# OR: http://localhost:3000 in browser
```

---

## PHASE 2 — Index Your Codebase for RAG (Day 1, 15 mins)

This lets the Architect and Engineer agents search your existing code for patterns.

```bash
# Index a local repo (point to any Python project you have)
python scripts/index_codebase.py --repo ./path/to/your/project

# Index a GitHub repo (clones it automatically)
python scripts/index_codebase.py --repo https://github.com/tiangolo/fastapi

# Verify indexing worked
python -c "
import chromadb
client = chromadb.PersistentClient('./data/chroma')
col = client.get_collection('codebase')
print(f'Indexed chunks: {col.count()}')
"
# Should show: Indexed chunks: 500+ (depends on repo size)
```

**Skip this step if:** you're starting a greenfield project.
The agents will still work — they'll just use their training knowledge instead of your codebase patterns.

---

## PHASE 3 — Run Your First Task (Day 1-2, 30 mins)

### Option A: Via the dashboard (recommended)

1. Open `http://localhost:3000`
2. Click **+ New Task**
3. Fill in:
   - **Title:** `Add user authentication with JWT`
   - **Body:**
     ```
     ## Requirements
     - POST /auth/register — accepts email + password, creates user, returns user_id
     - POST /auth/login — accepts email + password, returns JWT access token
     - GET /auth/me — requires Bearer token, returns current user info
     - Passwords must be hashed with bcrypt
     - JWT tokens expire after 24 hours
     - Return 401 for invalid credentials, 400 for validation errors
     
     ## Tech Stack
     - FastAPI + SQLAlchemy + PostgreSQL
     - PyJWT for tokens, passlib for bcrypt
     ```
4. Click **🚀 Launch Pipeline**
5. Watch agents work in real-time in the message feed

### Option B: Via API directly

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Add user authentication with JWT",
    "body": "Implement POST /auth/register, POST /auth/login, GET /auth/me with bcrypt + JWT",
    "repo": "your_username/your_repo"
  }'

# Returns: {"task_id": "abc123...", "status": "pending", ...}

# Poll status
curl http://localhost:8000/tasks/abc123...
```

### Option C: GitHub Webhook (automatic trigger)

1. In your GitHub repo → Settings → Webhooks → Add webhook
2. Payload URL: `http://YOUR_EC2_IP:8000/webhook/github`
3. Content type: `application/json`
4. Events: Issues
5. Now label any issue with `phantomdev` → auto-triggers pipeline

---

## PHASE 4 — Review Generated Output (Day 2)

After the pipeline completes (~15-30 mins for a simple feature):

### Check the generated files
```bash
ls ./workspace/
# Shows all generated code files

cat ./workspace/app/models/user.py
cat ./workspace/app/api/auth.py
cat ./workspace/tests/test_auth.py
```

### Run evaluation
```bash
python -m evaluation.eval_harness --demo
# Replace --demo with --task-id YOUR_TASK_ID for real evaluation
```

### Review the PR (if GitHub token configured)
- Dashboard shows PR link → click to open on GitHub
- Review code, click **✅ Approve** in dashboard (or manually on GitHub)

---

## PHASE 5 — AWS EC2 Deployment (Day 3, 1 hour)

### Recommended EC2 instance
- **t3.medium** (2 vCPU, 4GB RAM) — minimum for Ollama 7B
- **t3.large** (2 vCPU, 8GB RAM) — better, comfortable for 7B model
- **AMI:** Ubuntu 22.04 LTS (free tier eligible for t2.micro, but too small for Ollama)
- **Storage:** 20GB gp3 (Ollama model = ~4.5GB, leave headroom)
- **Security Group:** Allow inbound TCP 3000, 8000, 22 (SSH)

### Deploy

```bash
# 1. SSH to your EC2
ssh -i your-key.pem ubuntu@YOUR_EC2_IP

# 2. Run the setup script
curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/phantomdev/main/scripts/ec2_setup.sh | bash

# 3. Edit .env
nano /home/ubuntu/phantomdev/.env
# Set: GITHUB_TOKEN, TARGET_REPO

# 4. Restart services
cd /home/ubuntu/phantomdev
docker compose restart api

# 5. Access
open http://YOUR_EC2_IP:3000
```

### Keep it running (EC2 reboot safe)

```bash
# Docker compose services already set restart: unless-stopped
# To confirm auto-start after reboot:
sudo systemctl enable docker
```

---

## PHASE 6 — Observability with LangSmith (Optional, Free)

LangSmith gives you traces of every agent turn — great for debugging and demos.

```bash
# 1. Sign up at smith.langchain.com (free tier: 10K traces/month)
# 2. Get your API key
# 3. Add to .env:
LANGCHAIN_API_KEY=ls__your_key_here
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=phantomdev

# 4. Restart API
# Now every agent call appears in LangSmith with full token usage, latency, outputs
```

---

## Troubleshooting

### "Connection refused" to Ollama
```bash
# Check Ollama is running
ollama list   # should show qwen2.5-coder:7b
curl http://localhost:11434/api/tags  # should return model list

# Restart Ollama
sudo systemctl restart ollama  # Linux
# OR on Windows: restart from system tray
```

### Agents produce empty/garbage code
This usually means the model context window is too small.
```bash
# In .env, switch to a better model:
OLLAMA_MODEL=qwen2.5-coder:14b  # needs 16GB RAM
# OR use OpenAI:
OPENAI_API_KEY=sk-your-key
```

### ChromaDB errors
```bash
# Clear and re-index
rm -rf ./data/chroma
python scripts/index_codebase.py --repo ./your/repo
```

### Tests timing out
```bash
# Increase timeout in .env
AGENT_TIMEOUT=300  # 5 minutes per agent turn
MAX_ROUNDS=60      # allow more rounds
```

### PR creation fails
```bash
# Verify token has correct permissions
# GitHub → Settings → Developer Settings → Personal Access Tokens
# Required scopes: repo (full control)
```

---

## Architecture Decisions Explained

### Why AutoGen over LangGraph?
For PhantomDev, AutoGen's GroupChat is more natural than LangGraph because:
- Agents need to TALK to each other (not just pass state)
- The conversation history IS the working memory
- GroupChat natively handles the "who speaks next" problem

### Why Ollama over cloud LLMs?
- Zero cost (runs on your hardware/EC2)
- No API rate limits
- Code never leaves your machine (important for proprietary repos)
- qwen2.5-coder outperforms GPT-3.5 on code benchmarks

### Why ChromaDB for RAG?
- Runs locally, no external service
- Persistent across restarts
- AST-based chunking gives much better retrieval than naive text splitting

### Why the human approval gate?
- PhantomDev is meant to ASSIST engineers, not replace review
- Autonomous merge without review is a security/correctness risk
- The dashboard makes approval a 1-click action, not a burden

---

## Resume/Interview Talking Points

When a recruiter asks about this project, lead with:

1. **"I built a multi-agent system using AutoGen GroupChat where 7 specialized agents each own a distinct phase of the SDLC — from requirements through PR creation."**

2. **"The RAG pipeline uses AST-based chunking — chunking at the function level rather than by character count — which gives the architect agent much more precise codebase retrieval."**

3. **"I designed the human-in-the-loop gate at the PR creation step specifically because autonomous merge without review is a security risk. The system is autonomous but not uncontrolled."**

4. **"The evaluation harness runs before the PR is created — it measures test coverage, security findings, and type hint coverage as first-class pipeline outputs, not afterthoughts."**

5. **"The entire system runs on Ollama locally — zero LLM API cost — using qwen2.5-coder:7b which outperforms GPT-3.5 on HumanEval benchmarks."**
