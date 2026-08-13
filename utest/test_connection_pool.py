import pytest


def test_default_alias_is_default(connection_manager):
    assert connection_manager.default_alias == "default"


def test_add_to_connection_pool(connection_manager, database):
    connection_manager.add_to_connection_pool(database, "test_alias")

    assert connection_manager.db_connection_pool == {"test_alias": database}


def test_add_to_connection_pool_overwrites_existing_alias(connection_manager, mocker, caplog):
    first = mocker.MagicMock(name="MockDatabase1")
    second = mocker.MagicMock(name="MockDatabase2")

    connection_manager.add_to_connection_pool(first, "test_alias")
    connection_manager.add_to_connection_pool(second, "test_alias")

    assert connection_manager.db_connection_pool["test_alias"] == second
    assert "Connection with alias 'test_alias' already exists. Overwriting it." in caplog.text


def test_remove_from_connection_pool_closes_the_client(connection_manager, mocker):
    database = mocker.MagicMock(name="MockDatabase")
    connection_manager.add_to_connection_pool(database, "test_alias")

    connection_manager.remove_from_connection_pool("test_alias")

    assert connection_manager.db_connection_pool == {}
    database.client.close.assert_called_once()


def test_remove_from_connection_pool_with_invalid_alias(connection_manager):
    with pytest.raises(KeyError, match="Alias 'invalid_alias' not found in the connection pool."):
        connection_manager.remove_from_connection_pool("invalid_alias")


def test_clear_connection_pool_closes_every_client(connection_manager, mocker):
    first = mocker.MagicMock(name="MockDatabase1")
    second = mocker.MagicMock(name="MockDatabase2")
    connection_manager.add_to_connection_pool(first, "alias1")
    connection_manager.add_to_connection_pool(second, "alias2")

    connection_manager.clear_connection_pool()

    assert connection_manager.db_connection_pool == {}
    first.client.close.assert_called_once()
    second.client.close.assert_called_once()


def test_clear_connection_pool_uses_a_real_database_api(connection_manager, database):
    """Regression: `Database` has no close(); closing must go through `database.client`."""
    connection_manager.add_to_connection_pool(database, "test_alias")

    connection_manager.clear_connection_pool()

    assert connection_manager.db_connection_pool == {}


def test_clear_connection_pool_when_empty(connection_manager):
    connection_manager.clear_connection_pool()

    assert connection_manager.db_connection_pool == {}


def test_list_connection_pool(connection_manager, mocker):
    connection_manager.add_to_connection_pool(mocker.MagicMock(), "alias1")
    connection_manager.add_to_connection_pool(mocker.MagicMock(), "alias2")

    assert connection_manager.list_connection_pool() == ["alias1", "alias2"]


def test_list_connection_pool_when_empty(connection_manager):
    assert connection_manager.list_connection_pool() == []


def test_library_initialization():
    from MongoDBLibrary import MongoDBLibrary

    library = MongoDBLibrary()

    assert hasattr(library, 'connection_manager')
    assert library.connection_manager is not None


def test_the_library_reports_its_version():
    """Libdoc and `Get Library Instance` both read this.

    'unknown' means the distribution name in the importlib.metadata lookup no longer
    matches the one in pyproject.toml, which is the realistic way this breaks.
    """
    import re

    from MongoDBLibrary import MongoDBLibrary

    assert MongoDBLibrary.ROBOT_LIBRARY_VERSION != "unknown"
    assert re.fullmatch(r"\d+\.\d+\.\d+.*", MongoDBLibrary.ROBOT_LIBRARY_VERSION)
