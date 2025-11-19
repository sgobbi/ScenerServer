import sqlite3

from beartype import beartype
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log,
)

from lib import logger


@beartype
class SQL:
    retry_on_db_lock = retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, min=0.1, max=2),
        retry=retry_if_exception_type(sqlite3.OperationalError),
        before_sleep=before_sleep_log(logger, "ERROR"),
        after=after_log(logger, "INFO"),
        reraise=True,
    )

    @staticmethod
    @retry_on_db_lock
    def create_table_asset(conn: sqlite3.Connection, cursor: sqlite3.Cursor):
        """Create an 'asset' table if it doesn't exist."""
        try:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS asset (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    image TEXT,
                    mesh TEXT,
                    description TEXT
                )
            """
            )
            conn.commit()
            logger.info("Created the 'asset' table.")
        except sqlite3.Error as e:
            logger.error(f"Failed to create the 'asset' table: {e}")
            try:
                conn.rollback()
            except sqlite3.Error as e:
                logger.critical(f"Failed to rollback: {e}")
                raise
            raise
