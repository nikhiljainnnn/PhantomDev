# 👻 PhantomDev
**An Autonomous AI Software Engineering Pipeline**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![React + Vite](https://img.shields.io/badge/React-Vite-blueviolet.svg)](https://reactjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-00a393.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Enabled-2496ED.svg)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> A multi-agent AI system that takes a natural language feature request or GitHub Issue and autonomously produces a production-ready Pull Request—complete with code, tests, security review, and documentation.

---

## 🌟 Key Features

- **Multi-Agent Orchestration:** Powered by AutoGen, tasks are routed through specialized AI personas (PM, Architect, Engineer, QA, Security, Tech Writer, PR).
- **100% Local & Private:** Utilizes Ollama (`qwen2.5-coder:7b`) to process all agent reasoning and code generation locally. Zero external API costs.
- **Asynchronous Execution:** Built on FastAPI, Celery, and Redis to reliably offload heavy agent workflows to background workers without blocking the API.
- **Real-Time Telemetry Dashboard:** A beautifully designed "Glassmorphism" React dashboard that streams live agent dialogue, active pipeline steps, and generated code artifacts via WebSockets.
- **Production-Ready Infrastructure:** Fully containerized via Docker Compose, served behind an Nginx reverse proxy, and ready for AWS EC2 deployment.

## 🏗️ Architecture Workflow

```text
User Request / GitHub Issue
           │
           ▼
     API Gateway (FastAPI) ──► Redis Queue ──► Celery Worker
           │                                        │
      WebSocket                                     ▼
           │                         ┌────────────────────────────────────┐
           ▼                         │        AUTOGEN GROUP CHAT          │
   Real-Time Dashboard               │                                    │
(React, Vite, Glassmorphism)         │  PM Agent ──► Architect Agent      │
                                     │                    │               │
                                     │          ┌─────────┼─────────┐     │
                                     │          ▼         ▼         ▼     │
                                     │      Eng #1     Eng #2    Eng #3   │
                                     │          └─────────┼─────────┘     │
                                     │                    ▼               │
                                     │                 QA Agent           │
                                     │                    ▼               │
                                     │              Security Agent        │
                                     │                    ▼               │
                                     │             Tech Writer Agent      │
                                     │                    ▼               │
                                     │       PR Agent ──► GitHub / Git    │
                                     └────────────────────────────────────┘
```

## 🛠️ Tech Stack

- **Orchestration:** AutoGen (GroupChat)
- **AI / LLMs:** Ollama + Qwen2.5-Coder:7b (Local)
- **Backend:** FastAPI + WebSockets
- **Task Queue:** Celery + Redis
- **Frontend:** React + Vite (Custom PhantomDev Design System)
- **Testing & Security:** pytest, coverage.py, Bandit, Safety
- **Infrastructure:** Docker Compose, Nginx
- **Deployment:** AWS EC2 Shell Scripts

## 🚀 Quick Start (Local Development)

### 1. Install Dependencies
You need Docker and Ollama installed. Pull the required model:
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5-coder:7b
```

### 2. Clone & Configure
```bash
git clone https://github.com/yourname/phantomdev
cd phantomdev
cp .env.example .env   # Add your GitHub token if needed
```

### 3. Launch the Stack
Start the entire stack (API, Redis, Celery Worker, Frontend, Nginx):
```bash
docker compose -f docker-compose.local.yml up -d --build
```

### 4. Open the Dashboard
Navigate to [http://localhost](http://localhost) in your browser. Click **+ New Task** to trigger the autonomous pipeline.

## 📂 Repository Structure

```text
phantomdev/
├── agents/                  # AI personas (pm, architect, engineer, qa, etc.)
├── api/                     # FastAPI application and WebSocket handlers
├── evaluation/              # Automated eval pipeline and metrics scoring
├── frontend/                # React Vite dashboard (Stitch PhantomDev Theme)
├── infra/                   # Nginx config and deployment files
├── orchestrator/            # AutoGen GroupChat logic and Shared State
├── scripts/                 # EC2 Bootstrap and deployment scripts
├── tests/                   # Pytest suite
├── tools/                   # Agent tools (execution, GitHub API, file system)
└── worker/                  # Celery queue workers for async execution
```

## ☁️ AWS Deployment

Ready for production? We have included automated bootstrap scripts for an AWS EC2 instance (recommended `t3.xlarge` or GPU instance for local LLM inference).

Refer to the [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for step-by-step instructions.

---
*Built with PhantomDev.*
