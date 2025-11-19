import sqlite3

from beartype import beartype
from lib import logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log,
)


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

    # Init
    @staticmethod
    def connect_db(path: str):
        """Connect to an SQLite database (create it if doesn't exist) and return the connection."""
        try:
            conn = sqlite3.connect(path)
            logger.info(f"Connected to the database {path}.")
            return conn
        except sqlite3.Error as e:
            logger.error(f"Failed to connect to the database {path}: {e}")
            raise

    @staticmethod
    def get_cursor(conn: sqlite3.Connection):
        """Return a cursor from the connection."""
        try:
            return conn.cursor()
        except sqlite3.Error as e:
            logger.error(f"Failed to get a cursor from the connection {conn}: {e}")
            raise

    # Closing
    @staticmethod
    @retry_on_db_lock
    def close_connection(conn: sqlite3.Connection):
        """Close the SQLite connection."""
        try:
            conn.close()
            logger.info(f"Closed the database connection {conn}.")
        except sqlite3.Error as e:
            logger.error(f"Failed to close the {conn} connection: {e}")
            raise
