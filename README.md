# Choice Intelligence Platform

Welcome to the **Choice Intelligence Platform**. This is a premium, full-stack analytics application built to aggregate, analyse, and present social media performance metrics across all Choice Group brands.

The platform continuously scrapes data from social platforms (such as YouTube), processes and stores the video performance metrics, uses LLMs for semantic audience analysis, and presents the insights on an aesthetically premium Next.js dashboard.

---

## 📚 Documentation Directory

To keep documentation clean and targeted to the right audience, we have split it into two primary guides:

### 1. [Technical Documentation](docs/TECHNICAL.md)
*For Developers and System Administrators.*
Contains complete details on:
- System Architecture (Next.js, FastAPI, MySQL, Qdrant Vector DB)
- Environment Setup & Prerequisites
- How to start, stop, and manage the services (`scripts/start.sh`)
- Scraper orchestration and LLM integrations
- Directory structure and file responsibilities

### 2. [User Manual](docs/USER_MANUAL.md)
*For Executives, Analysts, and End Users.*
Contains clear-cut instructions on:
- How to navigate the UI
- Understanding the Statistics and Executive Summaries
- Using the Content Explorer to view video performance
- Running AI Analyses on specific date ranges and brands
- Using the Floating AI Chat Assistant

---

## 🚀 Quick Start (Developers)

If you have already configured your `.env` files and MySQL database, you can start the entire platform using the unified script:

```bash
# Start all backend services (FastAPI, Scraper, Qdrant)
./scripts/start.sh

# In a separate terminal, start the Next.js frontend
cd dashboard/nextjs
npm run dev



# Important instruction

Please add a.env file with required values before deploying this app.
```

- Frontend UI: `http://localhost:3000`
- Backend API Docs: `http://localhost:8000/docs`
