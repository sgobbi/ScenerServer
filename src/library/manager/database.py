import os
import sqlite3

from beartype import beartype
from colorama import Fore
from library.sql.connection import SQL as SQL_conn
from library.sql.table import SQL as SQL_table
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
class Database:
    retry_on_db_lock = retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, min=0.1, max=2),
        retry=retry_if_exception_type(sqlite3.OperationalError),
        before_sleep=before_sleep_log(logger, "ERROR"),
        after=after_log(logger, "INFO"),
        reraise=True,
    )

    def __init__(self, path: str):
        self.path = path
        self._conn = None
        try:
            self._check_path_and_init_db()
            logger.info(f"Database initialized at {Fore.GREEN}{self.path}{Fore.RESET}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def _is_opened_connection(self):
        # Check if the connection is open
        try:
            self._conn.cursor()
            return True
        except Exception as e:
            return False

    def _check_path_and_init_db(self):
        # Ensure that the database is properly initialized
        if not os.path.exists(self.path):
            logger.warning(
                f"Database file not found. Creating it at {Fore.GREEN}{self.path}{Fore.RESET}."
            )

        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create directory for database: {e}")
            raise

        try:
            self._conn = SQL_conn.connect_db(self.path)
            cursor = SQL_conn.get_cursor(self._conn)
            SQL_table.create_table_asset(self._conn, cursor)
            logger.success(f"Connected to database {Fore.GREEN}{self.path}{Fore.RESET}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            if self._conn:
                try:
                    SQL_conn.close_connection(self._conn)
                except Exception as close_e:
                    logger.error(f"Failed to close connection: {close_e}")
                    raise
                finally:
                    self._conn = None
            raise

    def get_connection(self):
        # Create a new connection each time it's needed, no need to cache
        if self._is_opened_connection():
            return self._conn
        else:
            try:
                self._conn = SQL_conn.connect_db(self.path)
                return self._conn
            except Exception as e:
                self._conn = None
                logger.error(f"Failed to create a new connection: {e}")
                raise

    def _get_cursor(self):
        # Get a fresh cursor for each operation
        try:
            conn = self.get_connection()
            return SQL_conn.get_cursor(conn)
        except Exception as e:
            logger.error(f"Failed to get a cursor: {e}")
            raise

    def close(self, conn: sqlite3.Connection = None):
        # Close the specific connection
        if conn:
            try:
                SQL_conn.close_connection(conn)
            except Exception as e:
                logger.error(f"Failed to close connection: {e}")
                raise
        else:
            logger.warning("No connection to close.")

    @retry_on_db_lock
    def clear_asset_table(self):
        """
        Delete all records from the 'asset' table.
        """
        cursor = self._get_cursor()
        conn = self.get_connection()
        try:
            cursor.execute("DELETE FROM asset")
            conn.commit()
            logger.info("Successfully cleared all records from the 'asset' table.")

        except sqlite3.Error as e:
            logger.error(f"Failed to clear the 'asset' table: {e}")
            try:
                conn.rollback()
            except sqlite3.Error as e:
                logger.critical(f"Failed to rollback after clear attempt: {e}")
                raise
            raise
