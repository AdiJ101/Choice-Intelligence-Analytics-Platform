# Technical README

This document serves as the comprehensive technical guide for developers, DevOps, and system administrators working on the **Choice Intelligence Platform**.

## 🏗 System Architecture

The platform follows a decoupled architecture, with a modern frontend communicating with a high-performance Python backend via REST APIs.

### 1. Frontend: Next.js + React
- **Location:** `dashboard/nextjs/`
- **Port:** `3000` (Locally)
- **Tech Stack:** Next.js 14 (App Router), React, TypeScript, GSAP (for animations), Vanilla CSS (for styling).
- **Responsibility:** Renders the premium UI, handles client-side state, and communicates with the Python backend via proxy routes in `lib/api.ts`.

### 2. Backend: FastAPI (Python)
- **Location:** `dashboard/backend/` and `src/`
- **Port:** `8000` (Locally)
- **Tech Stack:** FastAPI, Uvicorn, Python 3.10+.
- **Responsibility:** Exposes REST endpoints (`/api/scraper/status`, `/api/ai-analytics/*`, `/api/posts/*`). Coordinates database queries, manages background tasks for AI analysis, and handles scraper orchestration.

### 3. Data Ingestion: Scraper Orchestrator
- **Location:** `src/scraper/`
- **Responsibility:** A daemonized process that continuously fetches social data (views, likes, comments) via platform adapters (e.g., YouTube API).
- **Features:** 
  - Iterates over active `handles` based on intervals.
  - Maintains a history log in `storage/scraper_history.jsonl`.
  - State is communicated via `storage/scraper_state.json`.

### 4. Databases
- **Relational DB:** MySQL (Ports 3306). Stores relational data: platforms, handles, posts, comments, engagement history, and configurations.
- **Vector DB:** Qdrant (Port 6333). Runs as a local binary (`./qdrant`). Stores vectorized semantic representations of text (like comments) for RAG (Retrieval-Augmented Generation) based LLM analysis.

---

## ⚙️ Environment Setup

### Prerequisites
1. Node.js (v18+)
2. Python (v3.10+)
3. MySQL Server running locally on port 3306.
4. Download the Qdrant binary and place it in the root directory.

### Configuration (`.env`)
You must define your `.env` file at the root of the repository. Important keys include:
- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` (MySQL connection)
- `OPENAI_API_KEY` or equivalent for LLM analysis.
- `YOUTUBE_API_KEY` (For the scraper adapter)

---

## 🚀 Running the Project

To streamline development, we use unified bash scripts located in `scripts/`.

### Starting the Backend Services
Open your terminal at the project root and run:
```bash
./scripts/start.sh
```
**What this script does:**
1. Starts the local Qdrant Vector DB on port `6333`.
2. Starts the FastAPI backend on port `8000`.
3. Starts the Scraper Orchestrator in the background.
4. Generates logs in `.system_generated/tasks/` or `logs/`.

### Starting the Frontend
In a new terminal window, navigate to the Next.js directory:
```bash
cd dashboard/nextjs
npm install
npm run dev
```

### Stopping the Services
To safely shut down the Python backend, Qdrant, and the scraper, run:
```bash
./scripts/stop.sh
```

---

## 📂 Directory Structure

```text
├── dashboard/
│   ├── nextjs/          # Next.js frontend code
│   │   ├── app/         # App router pages (content, statistics, analytics)
│   │   ├── components/  # React components (FloatingChat, GradientHeader)
│   │   ├── lib/         # API wrappers and utilities
│   │   └── globals.css  # Unified styling
│   └── backend/         # FastAPI code
│       ├── main.py      # FastAPI entry point
│       └── routers/     # API endpoints (scraper_status.py, analytics.py)
├── src/
│   └── scraper/         # Core scraping engine and platform adapters
├── storage/             # File storage (scraper_history.jsonl, states)
├── scripts/             # Shell scripts for managing processes
└── qdrant               # Vector DB binary
```

---

## 🛠 Key Developer Workflows

### Modifying the Database Schema
1. Create a raw SQL migration script inside `migrations/`.
2. Ensure you update the corresponding Python data classes in `src/scraper/models.py`.

### Updating AI Analytics
1. The AI analytics rely on BackgroundTasks in FastAPI (located in `dashboard/backend/routers/analytics.py`).
2. Changes to prompts or OpenAI calls should be made in `src/ai/` or the corresponding router.
3. The frontend polls `/api/ai-analytics/job/{jobId}` until completion.

### Troubleshooting Scraper Issues
- The scraper runs natively inside `src/scraper/main.py`.
- Check `storage/scraper_history.jsonl` for exact failure points.
- Missing timestamps in the UI? Ensure `dashboard/backend/routers/scraper_status.py` correctly parses the JSONL log file.
