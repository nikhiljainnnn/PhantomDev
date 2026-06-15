# PhantomDev — Autonomous Software Engineering Team

> Multi-agent AI system that takes a GitHub Issue and autonomously produces
> a production-ready Pull Request with code, tests, security review, and docs.

## Architecture

```
GitHub Issue
     │
     ▼
API Gateway (FastAPI)
     │
     ▼
┌─────────────────────────────────────────┐
│         AUTOGEN GROUP CHAT              │
│                                         │
│  PM Agent ──► Architect Agent           │
│                    │                    │
│          ┌─────────┼─────────┐          │
│          ▼         ▼         ▼          │
│     Eng Agent  Eng Agent  Eng Agent     │
│          └─────────┼─────────┘          │
│                    ▼                    │
│             QA Agent                   │
│                    ▼                    │
│           Security Agent               │
│                    ▼                    │
│          Tech Writer Agent             │
│                    ▼                    │
│             PR Agent ──► GitHub        │
└─────────────────────────────────────────┘
     │
     ▼
Human Review Gate ──► Merge / Reject
```

## Tech Stack (Zero Cost)
- **Orchestration**: AutoGen 0.4 (GroupChat)
- **LLM**: Ollama + Qwen2.5-Coder:7b (local, FREE)
- **Codebase RAG**: ChromaDB + sentence-transformers
- **API**: FastAPI + WebSockets (real-time logs)
- **Code Execution**: Docker sandbox (subprocess)
- **GitHub Integration**: PyGithub + webhooks
- **Frontend**: React + Vite (real-time agent dashboard)
- **Testing**: pytest + coverage.py
- **Security Scan**: Bandit + Safety
- **Observability**: LangSmith (free tier) + structured logs
- **Deployment**: Docker Compose → single AWS EC2 t3.medium

## Quick Start
```bash
# 1. Install Ollama + pull model (one-time, ~4.5GB)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5-coder:7b

# 2. Clone and setup
git clone https://github.com/yourname/phantomdev
cd phantomdev
cp .env.example .env   # fill in your GitHub token

# 3. Launch
docker compose up -d
open http://localhost:3000
```

## Project Structure
```
phantomdev/
├── orchestrator/
│   ├── group_chat.py        # AutoGen GroupChat supervisor
│   ├── state.py             # Shared task state machine
│   └── router.py            # Agent selection logic
├── agents/
│   ├── base_agent.py        # Base class with memory + tools
│   ├── pm_agent.py          # Product Manager
│   ├── architect_agent.py   # System Architect
│   ├── engineer_agent.py    # Code Engineer (x3 parallel)
│   ├── qa_agent.py          # QA + test runner
│   ├── security_agent.py    # Bandit + Safety scanner
│   ├── writer_agent.py      # Tech documentation
│   └── pr_agent.py          # GitHub PR creator
├── tools/
│   ├── code_executor.py     # Sandboxed Python runner
│   ├── github_tools.py      # GitHub API wrapper
│   ├── file_tools.py        # Read/write workspace files
│   ├── rag_tools.py         # ChromaDB codebase search
│   ├── test_runner.py       # pytest executor
│   └── security_scanner.py  # Bandit + Safety
├── api/
│   ├── main.py              # FastAPI app
│   ├── routes/
│   │   ├── webhook.py       # GitHub webhook handler
│   │   ├── tasks.py         # Task CRUD
│   │   └── ws.py            # WebSocket live logs
│   └── models.py            # Pydantic schemas
├── evaluation/
│   ├── eval_harness.py      # Automated evaluation pipeline
│   └── metrics.py           # Quality metrics
├── frontend/                # React dashboard
├── infra/
│   ├── docker-compose.yml
│   ├── Dockerfile
│   └── nginx.conf
├── scripts/
│   ├── index_codebase.py    # Index repo into ChromaDB
│   └── ec2_setup.sh         # EC2 bootstrap
└── tests/
```
