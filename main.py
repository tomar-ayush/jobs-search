"""Job Scraper v2 — Orchestrator

Flow: Scrape → Dedupe (Astra DB) → Score (Gemini) → Store → Email Alert

Designed to run every 4 hours via GitHub Actions.
"""

import logging
import sys
from pathlib import Path

# Load .env file if it exists (for local development)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not required in CI

import config
from scraper import scrape_all
from db import JobDB
from scorer import score_jobs
from notifier import send_email

# ── Logging setup ─────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("job-scraper")


def main():
    """Main pipeline: scrape → dedupe → score → store → notify."""

    # ── Step 0: Validate configuration ────────────────────────────────
    logger.info("="*60)
    logger.info("Job Scraper v2 — Starting pipeline")
    logger.info("="*60)

    try:
        config.validate()
    except (ValueError, FileNotFoundError) as e:
        logger.error("Configuration error: %s", e)
        sys.exit(1)

    # ── Step 1: Scrape jobs ───────────────────────────────────────────
    logger.info("\n📡 Step 1/5: Scraping jobs...")
    df = scrape_all()

    if df.empty:
        logger.info("No jobs found. Exiting.")
        return

    logger.info("Scraped %d unique jobs.", len(df))

    # ── Step 2: Deduplicate against Astra DB ─────────────────────────
    logger.info("\n🗄️  Step 2/5: Checking Astra DB for duplicates...")
    db = JobDB()

    try:
        all_urls = df["job_url"].tolist()
        new_urls = db.filter_new(all_urls)

        if not new_urls:
            logger.info("All %d jobs already seen. Nothing new to score.", len(all_urls))
            db.close()
            return

        # Filter DataFrame to only new jobs
        df_new = df[df["job_url"].isin(new_urls)].copy()
        logger.info("%d new jobs to score (out of %d total).", len(df_new), len(df))

        # ── Step 3: Score with Gemini ─────────────────────────────────
        logger.info("\n🤖 Step 3/5: Scoring with Gemini AI...")

        # Convert to list of dicts for scoring
        # score_jobs returns ONLY successfully scored jobs.
        # Failed batches are dropped — those jobs stay out of DB
        # and will be re-scraped and re-scored on the next run.
        jobs_to_score = df_new.to_dict(orient="records")
        scored_jobs = score_jobs(jobs_to_score, delay=2.0)
        failed_count = len(jobs_to_score) - len(scored_jobs)

        # ── Step 4: Store in Astra DB ─────────────────────────────────
        logger.info("\n💾 Step 4/5: Storing results in Astra DB...")
        if scored_jobs:
            db.insert_jobs(scored_jobs)
        else:
            logger.warning("No jobs were successfully scored. Nothing to store.")

        # ── Step 5: Notify via email ──────────────────────────────────
        logger.info("\n📧 Step 5/5: Sending email notification...")

        # Filter to high-relevance jobs and sort by score
        notify_jobs = [
            j for j in scored_jobs
            if j.get("score", 0) >= config.MIN_SCORE_TO_NOTIFY
        ]
        notify_jobs.sort(key=lambda x: x.get("score", 0), reverse=True)

        if notify_jobs:
            logger.info("%d jobs scored >= %d (notification threshold).", len(notify_jobs), config.MIN_SCORE_TO_NOTIFY)
            sent = send_email(notify_jobs)

            # Mark notified jobs in DB
            if sent:
                for job in notify_jobs[:config.MAX_JOBS_IN_EMAIL]:
                    job["notified"] = True
                    db.insert_job(job)  # upsert with notified=True
        else:
            logger.info("No jobs scored >= %d. Skipping notification.", config.MIN_SCORE_TO_NOTIFY)

        # ── Summary ───────────────────────────────────────────────────
        logger.info("\n" + "="*60)
        logger.info("Pipeline complete!")
        logger.info("  Scraped:     %d jobs", len(df))
        logger.info("  New:         %d jobs", len(df_new))
        logger.info("  Scored:      %d jobs", len(scored_jobs))
        logger.info("  Failed:      %d jobs (will retry next run)", failed_count)
        logger.info("  Notifiable:  %d jobs (score >= %d)", len(notify_jobs), config.MIN_SCORE_TO_NOTIFY)
        logger.info("  Email sent:  %s", "Yes" if notify_jobs else "No (no high-scoring jobs)")
        logger.info("="*60)

    finally:
        db.close()


if __name__ == "__main__":
    main()
