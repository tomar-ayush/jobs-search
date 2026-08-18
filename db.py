"""Astra DB (Cassandra) module for job storage and deduplication.

Stores all scraped jobs with their Gemini relevance scores.
Used to avoid re-scoring and re-notifying about the same jobs.
"""

import logging
from datetime import datetime, timezone

from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider
from cassandra.query import SimpleStatement

from config import (
    ASTRA_DB_BUNDLE_PATH,
    ASTRA_DB_TOKEN,
    ASTRA_DB_KEYSPACE,
)

logger = logging.getLogger(__name__)

CREATE_TABLE_CQL = """
CREATE TABLE IF NOT EXISTS jobs (
    job_url     TEXT,
    title       TEXT,
    company     TEXT,
    location    TEXT,
    site        TEXT,
    search_query TEXT,
    description TEXT,
    date_posted TEXT,
    score       INT,
    reasoning   TEXT,
    matching    TEXT,
    missing     TEXT,
    scraped_at  TIMESTAMP,
    notified    BOOLEAN,
    PRIMARY KEY (job_url)
);
"""

INSERT_CQL = """
INSERT INTO jobs (
    job_url, title, company, location, site, search_query,
    description, date_posted, score, reasoning, matching,
    missing, scraped_at, notified
) VALUES (
    %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s,
    %s, %s, %s
);
"""


class JobDB:
    """Interface to the Astra DB jobs table."""

    def __init__(self):
        logger.info("Connecting to Astra DB (keyspace: %s)...", ASTRA_DB_KEYSPACE)
        cloud_config = {"secure_connect_bundle": ASTRA_DB_BUNDLE_PATH}
        auth_provider = PlainTextAuthProvider("token", ASTRA_DB_TOKEN)
        self.cluster = Cluster(cloud=cloud_config, auth_provider=auth_provider)
        self.session = self.cluster.connect(ASTRA_DB_KEYSPACE)
        self._ensure_table()
        logger.info("Connected to Astra DB.")

    def _ensure_table(self):
        """Create the jobs table if it doesn't exist."""
        self.session.execute(CREATE_TABLE_CQL)

    def get_seen_urls(self, urls: list[str]) -> set[str]:
        """Return the subset of URLs that already exist in the database.
        
        Uses individual lookups since Cassandra doesn't support IN on
        the partition key efficiently for large sets.
        """
        seen = set()
        for url in urls:
            try:
                row = self.session.execute(
                    SimpleStatement("SELECT job_url FROM jobs WHERE job_url = %s"),
                    [url]
                ).one()
                if row:
                    seen.add(url)
            except Exception:
                pass  # treat errors as "not seen" to avoid missing jobs
        return seen

    def filter_new(self, urls: list[str]) -> set[str]:
        """Return only the URLs that are NOT in the database."""
        seen = self.get_seen_urls(urls)
        new = set(urls) - seen
        logger.info("Dedup check: %d total, %d already seen, %d new", len(urls), len(seen), len(new))
        return new

    def insert_job(self, job: dict) -> None:
        """Insert or update a single job record."""
        try:
            self.session.execute(INSERT_CQL, [
                str(job.get("job_url", "")),
                str(job.get("title", "")),
                str(job.get("company", "")),
                str(job.get("location", "")),
                str(job.get("site", "")),
                str(job.get("search_query", "")),
                str(job.get("description", ""))[:5000],  # cap description size
                str(job.get("date_posted", "")),
                int(job.get("score", 0)),
                str(job.get("reasoning", "")),
                str(job.get("matching", "")),
                str(job.get("missing", "")),
                datetime.now(timezone.utc),
                bool(job.get("notified", False)),
            ])
        except Exception as e:
            logger.error("Failed to insert job %s: %s", job.get("job_url"), e)

    def insert_jobs(self, jobs: list[dict]) -> int:
        """Insert multiple jobs. Returns the count of successfully inserted jobs."""
        count = 0
        for job in jobs:
            self.insert_job(job)
            count += 1
        logger.info("Inserted %d jobs into Astra DB.", count)
        return count

    def close(self):
        """Shutdown the Cassandra cluster connection."""
        try:
            self.cluster.shutdown()
            logger.info("Astra DB connection closed.")
        except Exception as e:
            logger.warning("Error closing Astra DB connection: %s", e)
