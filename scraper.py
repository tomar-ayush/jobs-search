"""Job scraping module using python-jobspy.

Scrapes LinkedIn, Indeed, and Google Jobs for positions matching
Ayush's profile: backend, data engineering, AI/LLM, full-stack.
"""

import logging
import pandas as pd
from jobspy import scrape_jobs

from config import (
    SEARCH_QUERIES,
    LOCATION,
    RESULTS_PER_QUERY,
    HOURS_OLD,
)

logger = logging.getLogger(__name__)


def scrape_all() -> pd.DataFrame:
    """Scrape jobs across all configured queries and platforms.

    Returns a deduplicated DataFrame with columns including:
    job_url, title, company, location, description, site, date_posted.
    """
    all_jobs: list[pd.DataFrame] = []

    logger.info("Scraping jobs in %s (last %dh)", LOCATION, HOURS_OLD)
    logger.info("Queries: %s", ", ".join(SEARCH_QUERIES))

    for query in SEARCH_QUERIES:
        try:
            jobs = scrape_jobs(
                site_name=["linkedin", "indeed", "google"],
                search_term=query,
                location=LOCATION,
                results_wanted=RESULTS_PER_QUERY,
                hours_old=HOURS_OLD,
                country_indeed="India",
                linkedin_fetch_description=True,
            )
            if not jobs.empty:
                jobs["search_query"] = query
                all_jobs.append(jobs)
                logger.info("  ✓ %-25s → %d results", query, len(jobs))
            else:
                logger.info("  - %-25s → 0 results", query)
        except Exception as e:
            logger.warning("  ✗ %-25s → %s", query, e)

    if not all_jobs:
        logger.warning("No jobs found across any query.")
        return pd.DataFrame()

    df = pd.concat(all_jobs, ignore_index=True)
    before = len(df)
    df.drop_duplicates(subset=["job_url"], inplace=True)
    logger.info("Total: %d scraped, %d dupes removed → %d unique", before, before - len(df), len(df))

    return df
