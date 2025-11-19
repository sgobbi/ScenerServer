import library
import pytest
import sqlite3
import os

from colorama import Fore
from library.sql.function import SQL
from library.library_database import Database
from library.library_asset import Asset
from library.library_list import Library
from unittest.mock import MagicMock, patch, call


@pytest.fixture
def mock_conn():
    with patch("sqlite3.connect", spec=sqlite3.Connection) as mock_conn:
        yield mock_conn


@pytest.fixture
def mock_cursor():
    with patch("sqlite3.Cursor", spec=sqlite3.Cursor) as mock_cursor:
        yield mock_cursor


class TestSql:
    @pytest.fixture()
    def mock_logger(self):
        with patch("library.sql.logger") as mock_logger:
            yield mock_logger

    def test_connect_db_success(self, mock_conn, mock_logger):
        db_name = "test.db"

        Sql.connect_db(db_name)

        mock_conn.assert_called_once_with(db_name)

        mock_logger.info.assert_called_once_with(
            f"Connected to the database {db_name}."
        )

    @patch("sqlite3.connect", side_effect=sqlite3.Error("test"))
    def test_connect_db_failure(
        self,
        mock_conn,
        mock_logger,
    ):
        db_name = "test.db"
        err = sqlite3.Error("test")

        with pytest.raises(sqlite3.Error, match="test"):
            Sql.connect_db(db_name)

        mock_conn.assert_called_once_with(db_name)

        mock_logger.error.assert_called_once_with(
            f"Failed to connect to the database {db_name}: {err}"
        )

    def test_get_cursor_success(self, mock_conn):
        mock_conn.cursor.return_value = MagicMock()

        Sql.get_cursor(mock_conn)

        mock_conn.cursor.assert_called_once()

    def test_get_cursor_failure(self, mock_conn, mock_logger):
        err = sqlite3.Error("test")
        mock_conn.cursor.side_effect = err

        with pytest.raises(sqlite3.Error, match="test"):
            Sql.get_cursor(mock_conn)

        mock_conn.cursor.assert_called_once()

        mock_logger.error.assert_called_once_with(
            f"Failed to get a cursor from the connection {mock_conn}: {err}"
        )

    def test_create_table_asset_success(self, mock_conn, mock_cursor, mock_logger):
        Sql.create_table_asset(mock_conn, mock_cursor)

        mock_cursor.execute.assert_called_once_with(
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
        mock_conn.commit.assert_called_once()

        mock_logger.info.assert_any_call("Created the 'asset' table.")

    def test_create_table_asset_failure_execute(
        self, mock_conn, mock_cursor, mock_logger
    ):
        err = sqlite3.Error("test")
        mock_cursor.execute.side_effect = err

        with pytest.raises(sqlite3.Error, match="test"):
            Sql.create_table_asset(mock_conn, mock_cursor)

        mock_conn.rollback.assert_called_once()

        mock_logger.error.assert_any_call(f"Failed to create the 'asset' table: {err}")

    def test_create_table_asset_failure_rollback(
        self, mock_conn, mock_cursor, mock_logger
    ):
        exec_err = sqlite3.Error("oups")
        rollback_err = sqlite3.Error("OUPSSSSS")
        mock_cursor.execute.side_effect = exec_err
        mock_conn.rollback.side_effect = rollback_err

        with pytest.raises(sqlite3.Error, match="OUPSSSSS"):
            Sql.create_table_asset(mock_conn, mock_cursor)

        mock_conn.rollback.assert_called_once()

        mock_logger.error.assert_any_call(
            f"Failed to create the 'asset' table: {exec_err}"
        )
        mock_logger.critical.assert_called_once_with(
            f"Failed to rollback: {rollback_err}"
        )

    def test_insert_asset_success_new_name(self, mock_conn, mock_cursor, mock_logger):
        mock_cursor.fetchone.return_value = (0,)

        Sql.insert_asset(
            mock_conn, mock_cursor, "asset", "img.png", "mesh.obj", "desc.txt"
        )

        calls = [
            call("SELECT COUNT(*) FROM asset WHERE LOWER(name) = LOWER(?)", ("asset",)),
            call(
                "INSERT INTO asset (name, image, mesh, description) VALUES (?, ?, ?, ?)",
                ("asset", "img.png", "mesh.obj", "desc.txt"),
            ),
        ]

        assert mock_cursor.execute.call_count == 2
        mock_cursor.execute.assert_has_calls(calls)

        mock_conn.commit.assert_called_once()

        mock_logger.info.assert_any_call("Inserted asset 'asset' into the database.")

    """
    /!\ We need to define sameName policy /!\

    def test_insert_asset_success_existing_name(
        self, mock_conn, mock_cursor, mock_logger
    ):
        mock_cursor.fetchone.return_value = (1,)

        Sql.insert_asset(
            mock_conn, mock_cursor, "asset", "img.png", "mesh.obj", "desc.txt"
        )

        calls = [
            call("SELECT COUNT(*) FROM asset WHERE LOWER(name) = LOWER(?)", ("asset",)),
            call(
                "INSERT INTO asset (name, image, mesh, description) VALUES (?, ?, ?, ?)",
                ("asset_1", "img.png", "mesh.obj", "desc.txt"),
            ),
        ]

        assert mock_cursor.execute.call_count == 2
        mock_cursor.execute.assert_has_calls(calls)

        mock_conn.commit.assert_called_once()

        assert mock_cursor.execute.call_count == 2
        mock_logger.info.assert_any_call(
            "Asset name already exists. Inserting as 'asset_1' instead."
        )
        mock_logger.info.assert_any_call("Inserted asset 'asset_1' into the database.")
    """

    def test_insert_asset_empty_name(self, mock_conn, mock_cursor, mock_logger):
        with pytest.raises(ValueError, match="Asset name cannot be empty"):
            Sql.insert_asset(
                mock_conn, mock_cursor, "", "img.png", "mesh.obj", "desc.txt"
            )

        mock_logger.error.assert_called_once_with(
            "Trying to insert an asset with an empty name"
        )

    def test_insert_asset_select_error(self, mock_conn, mock_cursor, mock_logger):
        err = sqlite3.Error("test")
        mock_cursor.execute.side_effect = err

        with pytest.raises(sqlite3.Error, match="test"):
            Sql.insert_asset(
                mock_conn, mock_cursor, "asset", "img.png", "mesh.obj", "desc.txt"
            )

        mock_conn.commit.assert_not_called()
        mock_conn.rollback.assert_not_called()

        mock_cursor.execute.assert_called_once_with(
            "SELECT COUNT(*) FROM asset WHERE LOWER(name) = LOWER(?)", ("asset",)
        )

        mock_logger.error.assert_called_once_with(
            f"Failed to SELECT from 'asset' table: {err}"
        )

    def test_insert_asset_insert_error(self, mock_conn, mock_cursor, mock_logger):
        def execute_side_effect(query, params):
            if query.startswith("INSERT"):
                raise err
            else:
                return MagicMock()

        err = sqlite3.Error("test")
        mock_cursor.execute.side_effect = err
        mock_cursor.execute.side_effect = execute_side_effect
        mock_cursor.fetchone.return_value = (0,)

        with pytest.raises(sqlite3.Error, match="test"):
            Sql.insert_asset(
                mock_conn, mock_cursor, "asset", "img.png", "mesh.obj", "desc.txt"
            )

        calls = [
            call("SELECT COUNT(*) FROM asset WHERE LOWER(name) = LOWER(?)", ("asset",)),
            call(
                "INSERT INTO asset (name, image, mesh, description) VALUES (?, ?, ?, ?)",
                ("asset", "img.png", "mesh.obj", "desc.txt"),
            ),
        ]

        assert mock_cursor.execute.call_count == 2
        mock_cursor.execute.assert_has_calls(calls)

        mock_conn.rollback.assert_called_once()

        mock_logger.error.assert_called_once_with(
            f"Failed to INSERT into 'asset' table: {err}"
        )

    def test_insert_asset_insert_rollback_error(
        self, mock_conn, mock_cursor, mock_logger
    ):
        def execute_side_effect(query, params):
            if query.startswith("INSERT"):
                raise insert_err
            else:
                return MagicMock()

        insert_err = sqlite3.Error("bim")
        rollback_err = sqlite3.Error("bim bam la sauce")
        mock_cursor.execute.side_effect = execute_side_effect
        mock_conn.rollback.side_effect = rollback_err
        mock_cursor.fetchone.return_value = (0,)

        with pytest.raises(sqlite3.Error, match="bim bam la sauce"):
            Sql.insert_asset(
                mock_conn, mock_cursor, "asset", "img.png", "mesh.obj", "desc.txt"
            )

        calls = [
            call("SELECT COUNT(*) FROM asset WHERE LOWER(name) = LOWER(?)", ("asset",)),
            call(
                "INSERT INTO asset (name, image, mesh, description) VALUES (?, ?, ?, ?)",
                ("asset", "img.png", "mesh.obj", "desc.txt"),
            ),
        ]

        assert mock_cursor.execute.call_count == 2
        mock_cursor.execute.assert_has_calls(calls)

        mock_conn.rollback.assert_called_once()

        mock_logger.error.assert_called_once_with(
            f"Failed to INSERT into 'asset' table: {insert_err}"
        )
        mock_logger.critical.assert_called_once_with(
            f"Failed to rollback: {rollback_err}"
        )

    def test_query_assets_success(self, mock_cursor, mock_logger):
        expected_assets = [("test1",), ("test2",)]
        mock_cursor.fetchall.return_value = expected_assets

        assets = Sql.query_assets(mock_cursor)

        mock_cursor.execute.assert_called_once_with("SELECT * FROM asset")

        assert assets == expected_assets

    def test_query_assets_error(self, mock_cursor, mock_logger):
        error = sqlite3.Error("sadlife")

        mock_cursor.execute.side_effect = error

        with pytest.raises(sqlite3.Error, match="sadlife"):
            Sql.query_assets(mock_cursor)

        mock_logger.error.assert_any_call("Failed to SELECT from 'asset' table")

    def test_update_asset_success_all(self, mock_conn, mock_cursor, mock_logger):
        Sql.update_asset(
            mock_conn,
            mock_cursor,
            "asset",
            "img.png",
            "mesh.obj",
            "desc.txt",
        )

        expected_query = (
            "UPDATE asset SET image = ?, mesh = ?, description = ? WHERE name = ?"
        )
        expected_values = ("img.png", "mesh.obj", "desc.txt", "asset")

        mock_cursor.execute.assert_called_once_with(expected_query, expected_values)

        mock_conn.commit.assert_called_once()

        mock_logger.info.assert_called_once_with(
            "Updated asset 'asset' in the database."
        )

    def test_update_asset_success_partial(self, mock_conn, mock_cursor, mock_logger):
        Sql.update_asset(
            mock_conn,
            mock_cursor,
            "asset",
            image="new_img.png",
            description="new_desc.txt",
        )

        expected_query = "UPDATE asset SET image = ?, description = ? WHERE name = ?"
        expected_values = ("new_img.png", "new_desc.txt", "asset")

        mock_cursor.execute.assert_called_once_with(expected_query, expected_values)
        mock_conn.commit.assert_called_once()

        mock_logger.info.assert_called_once_with(
            "Updated asset 'asset' in the database."
        )

    def test_update_asset_no_fields_to_update(
        self, mock_conn, mock_cursor, mock_logger
    ):
        with pytest.raises(
            ValueError, match="No fields to update provided to the asset '{name}'"
        ):
            Sql.update_asset(mock_conn, mock_cursor, "asset")

        mock_cursor.execute.assert_not_called()

        mock_conn.commit.assert_not_called()

        mock_logger.info.assert_not_called()

    def test_update_asset_error(self, mock_conn, mock_cursor, mock_logger):
        err = sqlite3.Error("zzz")
        mock_cursor.execute.side_effect = err

        with pytest.raises(sqlite3.Error, match="zzz"):
            Sql.update_asset(mock_conn, mock_cursor, "asset", image="new_img.png")

        mock_conn.rollback.assert_called_once()

        mock_logger.error.assert_called_once_with(
            f"Faield to UPDATE the 'asset' table: {err}"
        )

    def test_update_asset_rollback_error(self, mock_conn, mock_cursor, mock_logger):
        update_err = sqlite3.Error("sad")
        rollback_err = sqlite3.Error("bad")
        mock_cursor.execute.side_effect = update_err
        mock_conn.rollback.side_effect = rollback_err

        with pytest.raises(sqlite3.Error, match="bad"):
            Sql.update_asset(mock_conn, mock_cursor, "asset", image="new_img.png")

        mock_conn.rollback.assert_called_once()

        mock_logger.error.assert_called_once_with(
            f"Faield to UPDATE the 'asset' table: {update_err}"
        )
        mock_logger.critical.assert_called_once_with(
            f"Failed to rollback: {rollback_err}"
        )

    def test_delete_asset_success(self, mock_conn, mock_cursor, mock_logger):
        Sql.delete_asset(mock_conn, mock_cursor, "asset")

        mock_cursor.execute.assert_called_once_with(
            "DELETE FROM asset WHERE name = ?", ("asset",)
        )

        mock_logger.info.assert_called_once_with(
            "Deleted asset 'asset' from the database."
        )

        mock_conn.commit.assert_called_once()

    def test_delete_asset_error(self, mock_conn, mock_cursor, mock_logger):
        err = sqlite3.Error("Delete failed")
        mock_cursor.execute.side_effect = err

        with pytest.raises(sqlite3.Error, match="Delete failed"):
            Sql.delete_asset(mock_conn, mock_cursor, "asset")

        mock_conn.rollback.assert_called_once()

        mock_logger.error.assert_called_once_with(
            f"Failed DELETE from 'asset' table: {err}"
        )

    def test_delete_asset_rollback_error(self, mock_conn, mock_cursor, mock_logger):
        delete_err = sqlite3.Error("bim")
        rollback_err = sqlite3.Error("BAM")
        mock_cursor.execute.side_effect = delete_err
        mock_conn.rollback.side_effect = rollback_err

        with pytest.raises(sqlite3.Error, match="BAM"):
            Sql.delete_asset(mock_conn, mock_cursor, "asset")

        mock_conn.rollback.assert_called_once()

        mock_logger.error.assert_called_once_with(
            f"Failed DELETE from 'asset' table: {delete_err}"
        )
        mock_logger.critical.assert_called_once_with(
            f"Failed to rollback: {rollback_err}"
        )

    def test_close_connection_success(self, mock_conn, mock_logger):
        Sql.close_connection(mock_conn)

        mock_conn.close.assert_called_once()

        mock_logger.info.assert_called_once_with(
            f"Closed the database connection {mock_conn}."
        )

    def test_close_connection_error(self, mock_conn, mock_logger):
        err = sqlite3.Error("aoaiaioa")
        mock_conn.close.side_effect = err

        with pytest.raises(sqlite3.Error, match="aoaiaioa"):
            Sql.close_connection(mock_conn)

        mock_logger.error.assert_called_once_with(
            f"Failed to close the {mock_conn} connection: {err}"
        )

    def test_retry(self, mock_logger, mock_conn, mock_cursor, monkeypatch):
        err = sqlite3.OperationalError("Database is locked")
        mock_cursor.execute.side_effect = err

        func = Sql.create_table_asset
        monkeypatch.setattr(func.retry, "before_sleep", mock_logger.error)
        monkeypatch.setattr(func.retry, "after", mock_logger.info)
        monkeypatch.setattr(func.retry, "wait", 0)

        with pytest.raises(sqlite3.OperationalError, match="Database is locked"):
            Sql.create_table_asset(mock_conn, mock_cursor)

        assert mock_cursor.execute.call_count == 4

        assert mock_conn.rollback.call_count == 4

        assert mock_logger.error.call_count == 7
        assert mock_logger.info.call_count == 4


@pytest.fixture
def mock_os_db():
    with patch("library.library_database.os", spec=os) as mock_os_db:
        yield mock_os_db


@pytest.fixture
def mock_sql_db():
    with patch("library.library_database.Sql", spec=library.sql.Sql) as mock_sql_db:
        yield mock_sql_db


DB_PATH = "test.db"


@pytest.fixture
def mock_db(mock_sql_db, mock_os_db, mock_conn, mock_cursor):
    mock_os_db.path.exists.return_value = True
    mock_sql_db.connect_db.return_value = mock_conn
    mock_sql_db.get_cursor.return_value = mock_cursor
    with patch("library.library_database.logger"):
        return Database(DB_PATH)


class TestDatabase:

    @pytest.fixture
    def mock_logger(self):
        with patch("library.library_database.logger") as mock_logger:
            yield mock_logger

    def test_init_success_db_exists(
        self, mock_sql_db, mock_logger, mock_os_db, mock_conn, mock_cursor
    ):
        mock_os_db.path.exists.return_value = True
        mock_sql_db.connect_db.return_value = mock_conn
        mock_sql_db.get_cursor.return_value = mock_cursor

        db = Database(DB_PATH)

        assert db.path == DB_PATH
        assert db._conn == mock_conn

        mock_os_db.path.exists.assert_called_once_with(DB_PATH)
        mock_os_db.makedirs.assert_called_once_with(
            mock_os_db.path.dirname(DB_PATH), exist_ok=True
        )

        mock_sql_db.connect_db.assert_called_once_with(DB_PATH)
        mock_sql_db.get_cursor.assert_called_once_with(db._conn)
        mock_sql_db.create_table_asset.assert_called_once_with(mock_conn, mock_cursor)

        mock_logger.info.assert_any_call(
            f"Database initialized at {Fore.GREEN}{DB_PATH}{Fore.RESET}"
        )
        mock_logger.success.assert_called_once_with(
            f"Connected to database {Fore.GREEN}{DB_PATH}{Fore.RESET}"
        )

    def test_init_success_db_not_exists(
        self, mock_sql_db, mock_logger, mock_os_db, mock_conn, mock_cursor
    ):
        mock_os_db.path.exists.return_value = False
        mock_sql_db.connect_db.return_value = mock_conn
        mock_sql_db.get_cursor.return_value = mock_cursor

        db = Database(DB_PATH)

        assert db.path == DB_PATH
        assert db._conn == mock_conn

        mock_os_db.path.exists.assert_called_once_with(DB_PATH)
        mock_os_db.makedirs.assert_called_once_with(
            mock_os_db.path.dirname(DB_PATH), exist_ok=True
        )

        mock_sql_db.connect_db.assert_called_once_with(DB_PATH)
        mock_sql_db.get_cursor.assert_called_once_with(db._conn)
        mock_sql_db.create_table_asset.assert_called_once_with(mock_conn, mock_cursor)

        mock_logger.info.assert_any_call(
            f"Database initialized at {Fore.GREEN}{DB_PATH}{Fore.RESET}"
        )
        mock_logger.success.assert_called_once_with(
            f"Connected to database {Fore.GREEN}{DB_PATH}{Fore.RESET}"
        )
        mock_logger.warning.assert_called_once_with(
            f"Database file not found. Creating it at {Fore.GREEN}{DB_PATH}{Fore.RESET}."
        )

    def test_init_makedir_error(self, mock_logger, mock_os_db):
        err = OSError("euh")
        mock_os_db.path.exists.return_value = False
        mock_os_db.makedirs.side_effect = err

        with pytest.raises(OSError, match="euh"):
            _ = Database(DB_PATH)

        mock_logger.warning.assert_called_once_with(
            f"Database file not found. Creating it at {Fore.GREEN}{DB_PATH}{Fore.RESET}."
        )
        assert mock_logger.error.call_count == 2
        mock_logger.error.assert_any_call(
            f"Failed to create directory for database: {err}"
        )
        mock_logger.error.assert_any_call(f"Failed to initialize database: {err}")

    def test_init_connect_error(self, mock_sql_db, mock_logger, mock_os_db):
        err = sqlite3.Error("ah")
        mock_os_db.path.exists.return_value = True
        mock_sql_db.connect_db.side_effect = err

        with pytest.raises(sqlite3.Error, match="ah"):
            db = Database(DB_PATH)
            assert db._conn is None

        assert mock_logger.error.call_count == 2
        mock_logger.error.assert_any_call(f"Failed to initialize database: {err}")

    def test_init_get_cursor_error_close_conn_success(
        self, mock_sql_db, mock_logger, mock_os_db, mock_conn
    ):
        err = sqlite3.Error("oh")
        mock_os_db.path.exists.return_value = True
        mock_sql_db.connect_db.return_value = mock_conn
        mock_sql_db.get_cursor.side_effect = err

        with pytest.raises(sqlite3.Error, match="oh"):
            db = Database(DB_PATH)
            assert db._conn is None

        mock_sql_db.connect_db.assert_called_once_with(DB_PATH)
        mock_sql_db.close_connection.assert_called_once_with(mock_conn)

        assert mock_logger.error.call_count == 2
        mock_logger.error.assert_any_call(f"Failed to initialize database: {err}")

    def test_init_get_cursor_error_close_conn_error(
        self, mock_sql_db, mock_logger, mock_os_db, mock_conn
    ):
        get_cursor_err = sqlite3.Error("ba")
        close_err = sqlite3.Error("daboum")
        mock_os_db.path.exists.return_value = True
        mock_sql_db.connect_db.return_value = mock_conn
        mock_sql_db.get_cursor.side_effect = get_cursor_err
        mock_sql_db.close_connection.side_effect = close_err

        with pytest.raises(sqlite3.Error, match="daboum"):
            db = Database(DB_PATH)
            assert db._conn is None

        mock_sql_db.connect_db.assert_called_once_with(DB_PATH)
        mock_sql_db.get_cursor.assert_called_once_with(mock_conn)
        mock_sql_db.close_connection.assert_called_once_with(mock_conn)

        assert mock_logger.error.call_count == 3
        mock_logger.error.assert_any_call(
            f"Failed to initialize database: {get_cursor_err}"
        )
        mock_logger.error.assert_any_call(f"Failed to close connection: {close_err}")

    def test_init_create_asset_error(
        self, mock_sql_db, mock_logger, mock_os_db, mock_conn, mock_cursor
    ):
        err = sqlite3.Error("pims sont sous-cotés")
        mock_os_db.path.exists.return_value = True
        mock_sql_db.connect_db.return_value = mock_conn
        mock_sql_db.get_cursor.return_value = mock_cursor
        mock_sql_db.create_table_asset.side_effect = err

        with pytest.raises(sqlite3.Error, match="pims sont sous-coté"):
            db = Database(DB_PATH)
            assert db._conn is None

        mock_sql_db.connect_db.assert_called_once_with(DB_PATH)
        mock_sql_db.get_cursor.assert_called_once_with(mock_conn)
        mock_sql_db.close_connection.assert_called_once_with(mock_conn)

        assert mock_logger.error.call_count == 2
        mock_logger.error.assert_any_call(f"Failed to initialize database: {err}")

    def test_get_conn_already_opened(self, mock_db, mock_sql_db, mock_conn):
        conn = mock_db.get_connection()

        assert conn == mock_conn

        mock_sql_db.get_cursor.assert_called_once_with(mock_conn)

        assert mock_db._is_opened_connection() is True

    def test_get_conn_new_conn_success(self, mock_db, mock_sql_db, mock_conn):
        mock_db._conn = None
        mock_sql_db.get_cursor.side_effect = sqlite3.Error("test")

        assert mock_db._is_opened_connection() is False

        conn = mock_db.get_connection()

        assert conn == mock_conn

        mock_sql_db.get_cursor.assert_called_once()

    def test_get_conn_new_conn_error(self, mock_db, mock_sql_db, mock_logger):
        err = sqlite3.Error("test")
        mock_db._conn = None
        mock_sql_db.connect_db.side_effect = err
        mock_sql_db.get_cursor.side_effect = err

        assert mock_db._is_opened_connection() is False

        with pytest.raises(sqlite3.Error, match="test"):
            mock_db.get_connection()

        mock_sql_db.get_cursor.assert_called_once()

        mock_logger.error.assert_called_once_with(
            f"Failed to create a new connection: {err}"
        )

    def test_get_cursor_success(self, mock_db, mock_sql_db, mock_conn, mock_cursor):
        cursor = mock_db._get_cursor()

        assert cursor == mock_cursor

        assert mock_sql_db.get_cursor.call_count == 2
        mock_sql_db.get_cursor.assert_any_call(mock_conn)

    def test_get_cursor_error(self, mock_db, mock_sql_db, mock_conn, mock_logger):
        err = sqlite3.Error("test")
        mock_sql_db.get_cursor.side_effect = err

        with pytest.raises(sqlite3.Error, match="test"):
            mock_db._get_cursor()

        assert mock_sql_db.get_cursor.call_count == 2
        mock_sql_db.get_cursor.assert_any_call(mock_conn)

        mock_logger.error.assert_called_once_with(f"Failed to get a cursor: {err}")

    def test_close_connection_no_opened_connecion(self, mock_db, mock_logger):
        mock_db._conn = None
        mock_db.close()

        mock_logger.warning.assert_called_once_with("No connection to close.")

    def test_close_connection_success(self, mock_db, mock_sql_db):
        mock_db.close(mock_db._conn)

        mock_sql_db.close_connection.assert_called_once_with(mock_db._conn)

    def test_close_connection_error(self, mock_db, mock_sql_db, mock_logger):
        err = sqlite3.Error("test")
        mock_sql_db.close_connection.side_effect = err

        with pytest.raises(sqlite3.Error, match="test"):
            mock_db.close(mock_db._conn)

        mock_sql_db.close_connection.assert_called_once_with(mock_db._conn)

        mock_logger.error.assert_called_once_with(f"Failed to close connection: {err}")


class TestAsset:
    patch(
        "library.library_asset.Fore", MagicMock(GREEN="", YELLOW="", RED="", RESET="")
    ).start()

    @pytest.fixture
    def mock_sql(self):
        with patch("library.library_asset.Sql", spec=library.sql.Sql) as mock_sql:
            yield mock_sql

    @pytest.fixture
    def mock_logger(self):
        with patch("library.library_asset.logger") as mock_logger:
            yield mock_logger

    @pytest.fixture
    def mock_asset(self, mock_db):
        return Asset(mock_db)

    def test_add_empty_name(self, mock_asset, mock_logger):
        with pytest.raises(ValueError, match="Asset name is required for addition!"):
            mock_asset.add("", "img.png", "mesh.obj", "desc.txt")

        mock_logger.error.assert_called_once_with(
            "Asset name is required for addition!"
        )

    def test_add_name_exists(self, mock_asset, mock_logger, mock_cursor):
        mock_asset._get_asset_by_name = MagicMock(return_value=(1,))
        mock_asset.db._get_cursor = MagicMock(return_value=mock_cursor)

        with pytest.raises(
            ValueError,
            match=f"Asset with name 'asset' already exists.",
        ):
            mock_asset.add("asset", "img.png", "mesh.obj", "desc.txt")

        mock_asset.db._get_cursor.assert_called_once()
        mock_asset._get_asset_by_name.assert_called_once_with(mock_cursor, "asset")

        mock_logger.error.assert_called_once_with(
            f"Asset with name 'asset' already exists."
        )

    def test_add_success(
        self, mock_asset, mock_sql, mock_logger, mock_cursor, mock_conn
    ):
        mock_asset._get_asset_by_name = MagicMock(return_value=None)
        mock_asset.db._get_cursor = MagicMock(return_value=mock_cursor)

        mock_asset.add("asset", "img.png", "mesh.obj", "desc.txt")

        mock_asset.db._get_cursor.assert_called_once()
        mock_asset._get_asset_by_name.assert_called_once_with(mock_cursor, "asset")

        mock_sql.insert_asset.assert_called_once_with(
            mock_conn, mock_cursor, "asset", "img.png", "mesh.obj", "desc.txt"
        )

        mock_logger.success.assert_called_once_with(
            f"Asset 'asset' added successfully."
        )

    def test_add_insert_error(
        self, mock_asset, mock_sql, mock_logger, mock_conn, mock_cursor
    ):
        err = sqlite3.Error("inner")
        mock_asset._get_asset_by_name = MagicMock(return_value=None)
        mock_asset.db._get_cursor = MagicMock(return_value=mock_cursor)
        mock_sql.insert_asset.side_effect = err

        with pytest.raises(sqlite3.Error, match="inner"):
            mock_asset.add("asset", "img.png", "mesh.obj", "desc.txt")

        mock_asset.db._get_cursor.assert_called_once()
        mock_asset._get_asset_by_name.assert_called_once_with(mock_cursor, "asset")
        mock_sql.insert_asset.assert_called_once_with(
            mock_conn, mock_cursor, "asset", "img.png", "mesh.obj", "desc.txt"
        )
        mock_logger.error.assert_called_once_with(
            f"Failed to add the asset 'asset': {err}"
        )

    def test_add_get_cursor_error(
        self,
        mock_asset,
        mock_logger,
    ):
        err = sqlite3.Error("aie")
        mock_asset.db._get_cursor = MagicMock(side_effect=err)

        with pytest.raises(sqlite3.Error, match="aie"):
            mock_asset.add("asset", "img.png", "mesh.obj", "desc.txt")

        mock_asset.db._get_cursor.assert_called_once()

        mock_logger.error.assert_called_once_with(
            f"Failed to add the asset 'asset': {err}"
        )

    def test_add_get_asset_error(self, mock_asset, mock_logger, mock_cursor):
        err = sqlite3.Error("aie")
        mock_asset.db._get_cursor = MagicMock(return_value=mock_cursor)
        mock_asset._get_asset_by_name = MagicMock(side_effect=err)

        with pytest.raises(sqlite3.Error, match="aie"):
            mock_asset.add("asset", "img.png", "mesh.obj", "desc.txt")

        mock_asset.db._get_cursor.assert_called_once()
        mock_asset._get_asset_by_name.assert_called_once_with(mock_cursor, "asset")

        mock_logger.error.assert_called_once_with(
            f"Failed to add the asset 'asset': {err}"
        )

    def test_delete_empty_name(self, mock_asset, mock_logger):
        with pytest.raises(ValueError, match="Asset name is required for deletion!"):
            mock_asset.delete("")

        mock_logger.error.assert_called_once_with(
            "Asset name is required for deletion!"
        )

    def test_delete_success(
        self, mock_asset, mock_sql, mock_logger, mock_cursor, mock_conn
    ):
        mock_asset._get_asset_by_name = MagicMock(return_value=(1, "asset"))
        mock_asset.db._get_cursor = MagicMock(return_value=mock_cursor)

        mock_asset.delete("asset")

        mock_asset.db._get_cursor.assert_called_once()
        mock_asset._get_asset_by_name.assert_called_once_with(mock_cursor, "asset")

        mock_sql.delete_asset.assert_called_once_with(mock_conn, mock_cursor, "asset")

        mock_logger.success.assert_called_once_with(
            f"Asset 'asset' deleted successfully."
        )

    def test_delete_sql_delete_error(
        self, mock_asset, mock_sql, mock_logger, mock_conn, mock_cursor
    ):
        err = sqlite3.Error("inner")
        mock_asset._get_asset_by_name = MagicMock(return_value=(1, "asset"))
        mock_asset.db._get_cursor = MagicMock(return_value=mock_cursor)
        mock_sql.delete_asset.side_effect = err

        with pytest.raises(sqlite3.Error, match="inner"):
            mock_asset.delete("asset")

        mock_asset.db._get_cursor.assert_called_once()
        mock_asset._get_asset_by_name.assert_called_once_with(mock_cursor, "asset")
        mock_sql.delete_asset.assert_called_once_with(
            mock_conn,
            mock_cursor,
            "asset",
        )
        mock_logger.error.assert_called_once_with(
            f"Failed to delete the asset 'asset': {err}"
        )

    def test_delete_get_cursor_error(
        self,
        mock_asset,
        mock_logger,
    ):
        err = sqlite3.Error("aie")
        mock_asset.db._get_cursor = MagicMock(side_effect=err)

        with pytest.raises(sqlite3.Error, match="aie"):
            mock_asset.delete("asset")

        mock_asset.db._get_cursor.assert_called_once()

        mock_logger.error.assert_called_once_with(
            f"Failed to delete the asset 'asset': {err}"
        )

    def test_delete_get_asset_error(self, mock_asset, mock_logger, mock_cursor):
        err = sqlite3.Error("aie")
        mock_asset.db._get_cursor = MagicMock(return_value=mock_cursor)
        mock_asset._get_asset_by_name = MagicMock(side_effect=err)

        with pytest.raises(sqlite3.Error, match="aie"):
            mock_asset.delete("asset")

        mock_asset.db._get_cursor.assert_called_once()
        mock_asset._get_asset_by_name.assert_called_once_with(mock_cursor, "asset")

        mock_logger.error.assert_called_once_with(
            f"Failed to delete the asset 'asset': {err}"
        )

    def test_update_empty_name(self, mock_asset, mock_logger):
        with pytest.raises(ValueError, match="Asset name is required for update!"):
            mock_asset.update("")

        mock_logger.error.assert_called_once_with("Asset name is required for update!")

    def test_update_success(
        self, mock_asset, mock_sql, mock_logger, mock_cursor, mock_conn
    ):
        mock_asset._get_asset_by_name = MagicMock(return_value=(1, "asset"))
        mock_asset.db._get_cursor = MagicMock(return_value=mock_cursor)

        mock_asset.update("asset")

        mock_asset.db._get_cursor.assert_called_once()
        mock_asset._get_asset_by_name.assert_called_once_with(mock_cursor, "asset")

        mock_sql.update_asset.assert_called_once_with(
            mock_conn,
            mock_cursor,
            "asset",
            None,
            None,
            None,
        )

        mock_logger.success.assert_called_once_with(
            f"Asset 'asset' updated successfully."
        )

    def test_update_sql_update_error(
        self, mock_asset, mock_sql, mock_logger, mock_conn, mock_cursor
    ):
        err = sqlite3.Error("inner")
        mock_asset._get_asset_by_name = MagicMock(return_value=(1, "asset"))
        mock_asset.db._get_cursor = MagicMock(return_value=mock_cursor)
        mock_sql.update_asset.side_effect = err

        with pytest.raises(sqlite3.Error, match="inner"):
            mock_asset.update("asset")

        mock_asset.db._get_cursor.assert_called_once()
        mock_asset._get_asset_by_name.assert_called_once_with(mock_cursor, "asset")
        mock_sql.update_asset.assert_called_once_with(
            mock_conn, mock_cursor, "asset", None, None, None
        )
        mock_logger.error.assert_called_once_with(
            f"Failed to update the asset 'asset': {err}"
        )

    def test_update_get_cursor_error(
        self,
        mock_asset,
        mock_logger,
    ):
        err = sqlite3.Error("aie")
        mock_asset.db._get_cursor = MagicMock(side_effect=err)

        with pytest.raises(sqlite3.Error, match="aie"):
            mock_asset.update("asset")

        mock_asset.db._get_cursor.assert_called_once()

        mock_logger.error.assert_called_once_with(
            f"Failed to update the asset 'asset': {err}"
        )

    def test_update_get_asset_error(self, mock_asset, mock_logger, mock_cursor):
        err = sqlite3.Error("aie")
        mock_asset.db._get_cursor = MagicMock(return_value=mock_cursor)
        mock_asset._get_asset_by_name = MagicMock(side_effect=err)

        with pytest.raises(sqlite3.Error, match="aie"):
            mock_asset.update("asset")

        mock_asset.db._get_cursor.assert_called_once()
        mock_asset._get_asset_by_name.assert_called_once_with(mock_cursor, "asset")

        mock_logger.error.assert_called_once_with(
            f"Failed to update the asset 'asset': {err}"
        )

    def test_get_asset_by_name_success(self, mock_asset, mock_cursor):
        name = "test_asset"
        expected_result = (1, "test_asset", "img.png", "mesh.obj", "desc.txt")
        mock_cursor.fetchone.return_value = expected_result

        result = mock_asset._get_asset_by_name(mock_cursor, name)

        assert result == expected_result
        mock_cursor.execute.assert_called_once_with(
            "SELECT * FROM asset WHERE name = ?", (name,)
        )
        mock_cursor.fetchone.assert_called_once()

    def test_get_asset_by_name_exec_error(self, mock_asset, mock_logger, mock_cursor):
        name = "test_asset"
        err = sqlite3.Error("rrr")
        mock_cursor.execute.side_effect = err

        with pytest.raises(sqlite3.Error, match="rrr"):
            mock_asset._get_asset_by_name(mock_cursor, name)

        mock_cursor.execute.assert_called_once_with(
            "SELECT * FROM asset WHERE name = ?", (name,)
        )
        mock_cursor.fetchone.assert_not_called()

        mock_logger.error.assert_called_once_with(
            f"Failed to fetch asset '{name}': {err}"
        )

    def test_get_asset_by_name_fetch_error(self, mock_asset, mock_logger, mock_cursor):
        name = "test_asset"
        err = sqlite3.Error("rrr")
        mock_cursor.execute.return_value = (1,)
        mock_cursor.fetchone.side_effect = err

        with pytest.raises(sqlite3.Error, match="rrr"):
            mock_asset._get_asset_by_name(mock_cursor, name)

        mock_cursor.execute.assert_called_once_with(
            "SELECT * FROM asset WHERE name = ?", (name,)
        )
        mock_cursor.fetchone.assert_called_once()

        mock_logger.error.assert_called_once_with(
            f"Failed to fetch asset '{name}': {err}"
        )


ASSET_PATH = "tests/assets"


class TestLibrary:
    patch(
        "library.library_list.Fore", MagicMock(GREEN="", YELLOW="", RED="", RESET="")
    ).start()

    @pytest.fixture
    def mock_os(self):
        with patch("library.library_list.os", spec=os) as mock_os:
            yield mock_os

    @pytest.fixture
    def mock_sql(self):
        with patch("library.library_list.Sql", spec=library.sql.Sql) as mock_sql_db:
            yield mock_sql_db

    @pytest.fixture
    def mock_logger(self):
        with patch("library.library_list.logger") as mock_logger:
            yield mock_logger

    @pytest.fixture
    def mock_lib(self, mock_db):
        return Library(mock_db)

    def test_fill_success(
        self, mock_lib, mock_sql, mock_logger, mock_os, mock_conn, mock_cursor
    ):
        mock_os.path.exists.return_value = True
        mock_os.path.isdir.side_effect = [
            True,
            True,
            True,
        ]
        mock_os.listdir.side_effect = [
            ["asset_folder1", "asset_folder2"],
            ["img1.png", "mesh1.obj", "desc1.txt"],
            ["img2.png", "mesh2.obj", "desc2.txt"],
        ]

        mock_os.path.join.side_effect = lambda *args: os.path.join(*args)
        mock_os.path.abspath.side_effect = lambda x: "/abs/" + x

        mock_lib.db._get_cursor = MagicMock(return_value=mock_cursor)

        mock_lib.fill(ASSET_PATH)

        assert mock_sql.insert_asset.call_count == 2
        mock_sql.insert_asset.assert_any_call(
            mock_conn,
            mock_cursor,
            "asset_folder1",
            "/abs/" + os.path.join(ASSET_PATH, "asset_folder1", "img1.png"),
            "/abs/" + os.path.join(ASSET_PATH, "asset_folder1", "mesh1.obj"),
            "/abs/" + os.path.join(ASSET_PATH, "asset_folder1", "desc1.txt"),
        )
        mock_sql.insert_asset.assert_any_call(
            mock_conn,
            mock_cursor,
            "asset_folder2",
            "/abs/" + os.path.join(ASSET_PATH, "asset_folder2", "img2.png"),
            "/abs/" + os.path.join(ASSET_PATH, "asset_folder2", "mesh2.obj"),
            "/abs/" + os.path.join(ASSET_PATH, "asset_folder2", "desc2.txt"),
        )

        assert mock_logger.info.call_count == 2
        mock_logger.info.assert_any_call(f"Inserted asset: asset_folder1")
        mock_logger.info.assert_any_call(f"Inserted asset: asset_folder2")

    def test_fill_path_not_exists(self, mock_lib, mock_logger, mock_os):
        mock_os.path.exists.return_value = False

        with pytest.raises(
            FileNotFoundError, match=f"Path to fill from does not exists: {ASSET_PATH}"
        ):
            mock_lib.fill(ASSET_PATH)

        mock_logger.error.assert_called_once_with(
            f"Path to fill from does not exists: {ASSET_PATH}"
        )

    def test_fill_path_not_dir(self, mock_lib, mock_logger, mock_os):
        mock_os.path.exists.return_value = True
        mock_os.path.isdir.return_value = False

        with pytest.raises(
            NotADirectoryError,
            match=f"Path to fill from is not a directory: {ASSET_PATH}",
        ):
            mock_lib.fill(ASSET_PATH)

        mock_logger.error.assert_called_once_with(
            f"Path to fill from is not a directory: {ASSET_PATH}"
        )

    def test_fill_listdir_error(self, mock_lib, mock_logger, mock_os):
        mock_os.path.exists.return_value = True
        mock_os.path.isdir.return_value = True

        err = OSError("meeeh")
        mock_os.listdir.side_effect = err

        with pytest.raises(OSError, match="meeeh"):
            mock_lib.fill(ASSET_PATH)

        mock_logger.error.assert_called_once_with(
            f"Failed to list directory {ASSET_PATH}: {err}"
        )

    def test_fill_insert_error(
        self,
        mock_lib,
        mock_sql,
        mock_logger,
        mock_os,
    ):
        mock_os.path.exists.return_value = True
        mock_os.path.isdir.return_value = True
        mock_os.listdir.side_effect = [
            ["asset_folder1"],
            ["img.png"],
        ]
        mock_os.path.isdir.side_effect = [True, True]

        err = sqlite3.Error("nonono")
        mock_sql.insert_asset.side_effect = err

        mock_os.path.join.side_effect = lambda *args: os.path.join(*args)
        mock_os.path.abspath.side_effect = lambda x: "/abs/" + x

        mock_lib.fill(ASSET_PATH)

        mock_logger.error.assert_called_once_with(
            f"Failed to insert asset asset_folder1: {err}"
        )

    def test_fill_listsubdir_error(
        self,
        mock_lib,
        mock_logger,
        mock_os,
    ):
        err = OSError("tungtungtung")
        mock_os.path.exists.return_value = True
        mock_os.path.isdir.return_value = True
        mock_os.listdir.side_effect = [
            ["asset_folder1"],
            err,
        ]
        mock_os.path.isdir.side_effect = [True, True]

        mock_os.path.join.side_effect = lambda *args: os.path.join(*args)
        mock_os.path.abspath.side_effect = lambda x: "/abs/" + x

        mock_lib.fill(ASSET_PATH)

        mock_logger.error.assert_called_once_with(
            f"Failed to list subdirectory tests/assets/asset_folder1: {err}"
        )

    def test_read_success(self, mock_lib, mock_sql, capsys):
        mock_assets_data = [
            (1, "Asset1", "img1.png", "mesh1.obj", "desc1.txt"),
            (2, "Asset2", None, "mesh2.obj", None),
        ]
        mock_sql.query_assets.return_value = mock_assets_data

        mock_lib.read()

        captured = capsys.readouterr()
        assert "ID   Name       Image      Mesh       Description" in captured.out
        assert "1    Asset1     ok         ok         ok" in captured.out
        assert "2    Asset2     None       ok         None" in captured.out

        mock_sql.query_assets.assert_called_once()

    def test_read_no_assets(self, mock_lib, mock_sql, capsys):
        mock_sql.query_assets.return_value = []

        mock_lib.read()

        captured = capsys.readouterr()
        assert "No assets found." in captured.out

    def test_read_get_cursor_error(self, mock_lib, mock_sql, mock_logger):
        err = Exception("DBbd")
        mock_lib.db._get_cursor = MagicMock(side_effect=err)

        with pytest.raises(Exception, match="DBbd"):
            mock_lib.read()

        mock_lib.db._get_cursor.assert_called_once()
        mock_sql.query_assets.assert_not_called()

        mock_logger.error.assert_called_once_with(
            f"Failed to read assets from the database: {err}"
        )

    def test_read_query_error(self, mock_lib, mock_sql, mock_logger, mock_cursor):
        err = Exception("DBbd")
        mock_sql.query_assets.side_effect = err

        with pytest.raises(Exception, match="DBbd"):
            mock_lib.read()

        mock_sql.query_assets.assert_called_once_with(mock_cursor)

        mock_logger.error.assert_called_once_with(
            f"Failed to read assets from the database: {err}"
        )

    def test_get_list_success(self, mock_lib, mock_sql):
        mock_assets_data = [
            (1, "Asset1", "img1.png", "mesh1.obj", "desc1.txt"),
            (2, "Asset2", None, "mesh2.obj", None),
        ]
        mock_sql.query_assets.return_value = mock_assets_data

        expected_list = [
            {
                "id": 1,
                "name": "Asset1",
                "image": "img1.png",
                "mesh": "mesh1.obj",
                "description": "desc1.txt",
            },
            {
                "id": 2,
                "name": "Asset2",
                "image": None,
                "mesh": "mesh2.obj",
                "description": None,
            },
        ]

        result = mock_lib.get_list()
        assert result == expected_list

    def test_get_list_get_cursor_error(self, mock_lib, mock_sql, mock_logger):
        err = Exception("bdDB")
        mock_lib.db._get_cursor = MagicMock(side_effect=err)

        with pytest.raises(Exception, match="bdDB"):
            mock_lib.get_list()

        mock_lib.db._get_cursor.assert_called_once()
        mock_sql.query_assets.assert_not_called()

        mock_logger.error.assert_called_once_with(
            f"Failed to read assets from the database: {err}"
        )

    def test_get_list_query_error(self, mock_lib, mock_sql, mock_logger):
        err = Exception("bdDB")
        mock_sql.query_assets.side_effect = err

        with pytest.raises(Exception, match="bdDB"):
            mock_lib.get_list()

        mock_sql.query_assets.assert_called_once()

        mock_logger.error.assert_called_once_with(
            f"Failed to read assets from the database: {err}"
        )
