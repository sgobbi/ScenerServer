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

    @staticmethod
    @retry_on_db_lock
    def insert_asset(
        conn: sqlite3.Connection,
        cursor: sqlite3.Cursor,
        name: str,
        image: str | None,
        mesh: str | None,
        description: str | None,
    ):
        """Insert a new asset into the 'asset' table if the name does not already exist."""
        if not name:
            logger.error("Trying to insert an asset with an empty name")
            raise ValueError("Asset name cannot be empty")

        # Check if asset with the same name already exists rename if it does
        try:
            cursor.execute(
                "SELECT COUNT(*) FROM asset WHERE LOWER(name) = LOWER(?)", (name,)
            )
            nb = cursor.fetchone()[0]
            if nb > 0:
                logger.info(f"Asset name '{name}' already exists.")
                return

            """
            if nb > 0:
                name = name + f"_{nb}"
                logger.info(
                    f"Asset name already exists. Inserting as '{name}' instead."
                )"""
        except sqlite3.Error as e:
            logger.error(f"Failed to SELECT from 'asset' table: {e}")
            raise

        # Then, insert operation
        try:
            cursor.execute(
                "INSERT INTO asset (name, image, mesh, description) VALUES (?, ?, ?, ?)",
                (name, image, mesh, description),
            )
            conn.commit()
            logger.info(f"Inserted asset '{name}' into the database.")
        except sqlite3.Error as e:
            logger.error(f"Failed to INSERT into 'asset' table: {e}")
            try:
                conn.rollback()
            except sqlite3.Error as e:
                logger.critical(f"Failed to rollback: {e}")
                raise
            raise

    @staticmethod
    @retry_on_db_lock
    def query_assets(cursor: sqlite3.Cursor):
        """Fetch all assets from the 'asset' table."""
        try:
            cursor.execute("SELECT * FROM asset")
            return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error("Failed to SELECT from 'asset' table")
            raise

    @staticmethod
    @retry_on_db_lock
    def query_asset_by_name(cursor: sqlite3.Cursor, name: str):
        """Helper method to fetch an asset by its name."""
        try:
            cursor.execute("SELECT * FROM asset WHERE name = ?", (name,))
            return cursor.fetchone()
        except sqlite3.Error as e:
            logger.error(f"Failed to fetch asset '{name}': {e}")
            raise

    @staticmethod
    @retry_on_db_lock
    def update_asset(
        conn: sqlite3.Connection,
        cursor: sqlite3.Cursor,
        name: str,
        image: str = None,
        mesh: str = None,
        description: str = None,
    ):
        """Update an existing asset's information by its name."""

        # Build the SET clause for the SQL query dynamically based on the non-None parameters
        update_fields = []
        update_values = []

        if image is not None:
            update_fields.append("image = ?")
            update_values.append(image)

        if mesh is not None:
            update_fields.append("mesh = ?")
            update_values.append(mesh)

        if description is not None:
            update_fields.append("description = ?")
            update_values.append(description)

        if not update_fields:
            logger.warning(
                f"Attempting to update asset '{name}' with no fields to update."
            )
            raise ValueError(
                "No fields to update provided to the asset '{name}'"
            )  # If no fields to update, return early

        # Add the asset name at the end of the update_values to match the WHERE clause
        update_fields_str = ", ".join(update_fields)
        update_values.append(name)

        # Execute the update query
        try:
            cursor.execute(
                f"UPDATE asset SET {update_fields_str} WHERE name = ?",
                tuple(update_values),
            )
            conn.commit()
            logger.info(f"Updated asset '{name}' in the database.")
        except sqlite3.Error as e:
            logger.error(f"Faield to UPDATE the 'asset' table: {e}")
            try:
                conn.rollback()
            except sqlite3.Error as e:
                logger.critical(f"Failed to rollback: {e}")
                raise
            raise

    @staticmethod
    @retry_on_db_lock
    def delete_asset(conn: sqlite3.Connection, cursor: sqlite3.Cursor, name: str):
        """Delete an asset by its name."""
        try:
            cursor.execute("DELETE FROM asset WHERE name = ?", (name,))
            conn.commit()
            logger.info(f"Deleted asset '{name}' from the database.")
        except sqlite3.Error as e:
            logger.error(f"Failed DELETE from 'asset' table: {e}")
            try:
                conn.rollback()
            except sqlite3.Error as e:
                logger.critical(f"Failed to rollback: {e}")
                raise
            raise
