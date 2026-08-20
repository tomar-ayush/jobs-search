# auto-linkedin-jobs 🤖📬

**Your personalized job digest, fully automated.**

A self-running pipeline that scrapes freshly posted jobs (last 4 hours) from multiple platforms — LinkedIn, Indeed, and Google Jobs — matches them against your resume using Gemini AI, scores each job for relevance (1–10), stores the best matches in Astra DB to avoid duplicates, and delivers a clean email digest straight to your inbox. Runs every 4 hours via GitHub Actions — completely hands-free.

---

## How It Works

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Scrape     │───▶│  Deduplicate │───▶│  AI Scoring   │───▶│  Store in DB │───▶│  Email You   │
│  LinkedIn    │    │  (Astra DB)  │    │  (Gemini)     │    │  (Astra DB)  │    │  Top Matches │
│  Indeed      │    │  Skip seen   │    │  Score 1-10   │    │  For dedup   │    │  HTML Digest  │
│  Google Jobs │    │  jobs        │    │  per job      │    │  next run    │    │              │
└─────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
```

1. **Scrape** — Pulls jobs posted in the last 4 hours across LinkedIn, Indeed, and Google Jobs using customizable search queries (e.g., "Backend Developer", "AI Engineer").
2. **Deduplicate** — Checks every scraped job URL against Astra DB. Already seen it? Skip it.
3. **Score** — Sends your resume + each batch of new jobs to Gemini AI. Gets back a relevance score (1–10), matched/missing skills, and seniority fit. Automatically falls back to alternate Gemini models if one hits its quota limit.
4. **Store** — Saves all scored jobs to Astra DB so they're never processed again.
5. **Email** — Filters for high-scoring jobs (default: score ≥ 6), sorts by score, and sends you an HTML email with the top matches.

---

## Project Structure

| File | Purpose |
|---|---|
| `main.py` | Orchestrator — runs the 5-step pipeline |
| `scraper.py` | Multi-platform job scraping via `python-jobspy` |
| `scorer.py` | Gemini AI scoring with automatic model fallback |
| `db.py` | Astra DB interface — dedup + storage |
| `notifier.py` | HTML email builder + Gmail SMTP sender |
| `config.py` | All configuration in one place (queries, models, thresholds) |
| `resume_text.txt` | Your plain-text resume (used by Gemini for scoring) |
| `.github/workflows/job_scan.yml` | GitHub Actions — runs every 4 hours |

---

## Quick Start

### Prerequisites
- Python 3.12+
- [DataStax Astra DB](https://astra.datastax.com) account (free tier — 40 GB)
- [Google Gemini API Key](https://aistudio.google.com/apikey)
- Gmail account with an [App Password](https://myaccount.google.com/apppasswords)

### Local Setup

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/auto-linkedin-jobs.git
cd auto-linkedin-jobs

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env with your Astra DB, Gemini, and Gmail credentials

# 4. Add your resume
# Edit resume_text.txt with your plain-text resume

# 5. Place your Astra secure connect bundle in the project root
# Download from: Astra Dashboard → Your DB → Connect → Drivers → Python

# 6. Run
python main.py
```

### GitHub Actions (Fully Automated)

Add these **repository secrets** (`Settings` → `Secrets and variables` → `Actions`):

| Secret | Description |
|---|---|
| `ASTRA_DB_BUNDLE_BASE64` | `base64 -i secure-connect-*.zip \| tr -d '\n'` |
| `ASTRA_DB_CLIENT_ID` | From your Astra token JSON |
| `ASTRA_DB_CLIENT_SECRET` | From your Astra token JSON |
| `ASTRA_DB_TOKEN` | Starts with `AstraCS:...` |
| `ASTRA_DB_KEYSPACE` | Your keyspace name |
| `GEMINI_API_KEY` | From Google AI Studio |
| `SMTP_EMAIL` | Your Gmail address |
| `SMTP_PASSWORD` | Gmail App Password |
| `NOTIFY_EMAIL` | Email to receive the digest |

Once secrets are configured, the pipeline runs automatically every 4 hours. You can also trigger it manually from the Actions tab.

---

## Configuration

All tunables live in [`config.py`](config.py):

| Setting | Default | Description |
|---|---|---|
| `SEARCH_QUERIES` | Backend, Python, AI, etc. | Job titles to search for |
| `LOCATION` | India | Geographic filter |
| `HOURS_OLD` | 4 | Only scrape jobs posted within this window |
| `GEMINI_MODEL` | `gemini-3.7-flash` | Primary scoring model |
| `FALLBACK_MODELS` | 6 fallback models | Auto-switches when quota is hit |
| `MIN_SCORE_TO_NOTIFY` | 6 | Only email jobs scoring ≥ this |
| `MAX_JOBS_IN_EMAIL` | 50 | Cap on jobs per email |

---

## Tech Stack

- **Scraping**: [python-jobspy](https://github.com/Bunsly/JobSpy)
- **Database**: [DataStax Astra DB](https://astra.datastax.com) (Cassandra)
- **AI Scoring**: [Google Gemini](https://ai.google.dev) (`google-genai` SDK)
- **Email**: Gmail SMTP
- **CI/CD**: GitHub Actions

## License

MIT
