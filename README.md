# AI Job Hunter 🕵️‍♂️💼

An automated, cross-platform job scraper that finds relevant jobs, deduplicates them using DataStax Astra DB, scores your fit using Gemini AI models, and emails you the top matches. Designed to run completely hands-free via GitHub Actions.

## ✨ Features
* **Multi-Platform Scraping**: Pulls jobs from LinkedIn, Google Jobs, and Indeed.
* **Smart Deduplication**: Remembers what jobs you've already seen using Astra DB so you never process the same job twice.
* **AI Fit Scoring**: Sends the job description and your resume to Gemini (with automatic fallback models) to evaluate technical fit, experience level, and domain relevance.
* **Email Alerts**: Sends a clean HTML email containing only jobs that score above your customizable threshold.
* **CI/CD Automation**: Runs automatically every 4 hours via GitHub Actions.

## 🚀 Setup

### 1. Requirements
- Python 3.12+
- A DataStax Astra DB account (Free tier)
- A Google Gemini API Key
- A Gmail account with an App Password

### 2. Local Configuration
Copy the `.env.example` file to `.env` and fill in your credentials:
```bash
cp .env.example .env
```
Ensure you have downloaded your `secure-connect-bundle.zip` from Astra DB and placed it in the project root.
Update `resume_text.txt` with your own plain-text resume.

### 3. Run Locally
```bash
pip install -r requirements.txt
python main.py
```

### 4. GitHub Actions Deployment
Add the following secrets to your repository (`Settings` > `Secrets and variables` > `Actions`):
- `ASTRA_DB_BUNDLE_BASE64`: The base64 encoded string of your Astra secure connect bundle.
- `ASTRA_DB_CLIENT_ID`
- `ASTRA_DB_CLIENT_SECRET`
- `ASTRA_DB_TOKEN`
- `ASTRA_DB_KEYSPACE`
- `GEMINI_API_KEY`
- `SMTP_EMAIL`
- `SMTP_PASSWORD`
- `NOTIFY_EMAIL`

Once secrets are set, the pipeline will run automatically on the schedule defined in `.github/workflows/job_scan.yml`.

## 🛠️ Configuration
You can tweak thresholds, search queries, location, and the AI models used inside `config.py`.
