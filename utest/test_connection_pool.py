import pytest

from MongoDBLibrary.connection_pool import ConnectionManager


@pytest.fixture
def connection_manager():
    return ConnectionManager()

def test_add_to_connection_pool_with_mocked_client(connection_manager, mocker):
    mock_client = mocker.MagicMock(name="MockMongoClient")
    alias = "test_alias"

    connection_manager.add_to_connection_pool(mock_client, db_name="test_db", alias=alias)

    assert len(connection_manager.db_connection_pool) == 1
    assert alias in connection_manager.db_connection_pool
    assert connection_manager.db_connection_pool[alias] == mock_client

def test_add_to_connection_pool_with_default_alias(connection_manager, mocker):
    mock_client = mocker.MagicMock(name="MockMongoClient")

    connection_manager.add_to_connection_pool(mock_client, db_name="test_db")

    assert connection_manager.default_alias in connection_manager.db_connection_pool
    assert connection_manager.db_connection_pool[connection_manager.default_alias] == mock_client

def test_add_to_connection_pool_with_default_alias_overwrite(connection_manager, mocker):
    mock_client1 = mocker.MagicMock(name="MockMongoClient1")
    mock_client2 = mocker.MagicMock(name="MockMongoClient2")

    connection_manager.add_to_connection_pool(mock_client1, db_name="test_db")
    connection_manager.add_to_connection_pool(mock_client2, db_name="test_db")

    assert connection_manager.db_connection_pool[connection_manager.default_alias] == mock_client2

def test_add_to_connection_pool_with_alias_overwrite(connection_manager, mocker, caplog):
    mock_client1 = mocker.MagicMock(name="MockMongoClient1")
    mock_client2 = mocker.MagicMock(name="MockMongoClient2")
    alias = "test_alias"

    connection_manager.add_to_connection_pool(mock_client1, db_name="test_db", alias=alias)
    connection_manager.add_to_connection_pool(mock_client2, db_name="test_db", alias=alias)

    assert connection_manager.db_connection_pool[alias] == mock_client2
    assert f"Connection with alias '{alias}' already exists. Overwriting it." in caplog.text

def test_remove_from_connection_pool_with_mocked_client(connection_manager, mocker):
    mock_client = mocker.MagicMock(name="MockMongoClient")
    alias = "test_alias"

    connection_manager.add_to_connection_pool(mock_client, db_name="test_db", alias=alias)
    connection_manager.remove_from_connection_pool(alias)

    assert len(connection_manager.db_connection_pool) == 0
    assert alias not in connection_manager.db_connection_pool

def test_remove_from_connection_pool_with_invalid_alias(connection_manager):
    alias = "invalid_alias"

    with pytest.raises(KeyError, match=f"Alias '{alias}' not found in the connection pool."):
        connection_manager.remove_from_connection_pool(alias)

def test_remove_from_connection_pool_nonexistent_alias(connection_manager):
    with pytest.raises(KeyError):
        connection_manager.remove_from_connection_pool("nonexistent_alias")

def test_clear_connection_pool_with_mocked_clients(connection_manager, mocker):
    mock_client1 = mocker.MagicMock(name="MockMongoClient1")
    mock_client2 = mocker.MagicMock(name="MockMongoClient2")
    alias1 = "test_alias1"
    alias2 = "test_alias2"

    connection_manager.add_to_connection_pool(mock_client1, db_name="test_db1", alias=alias1)
    connection_manager.add_to_connection_pool(mock_client2, db_name="test_db2", alias=alias2)
    connection_manager.clear_connection_pool()

    assert len(connection_manager.db_connection_pool) == 0

def test_clear_connection_pool(connection_manager, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    connection_manager.db_connection_pool = {"test_alias": mock_db}

    connection_manager.clear_connection_pool()

    assert len(connection_manager.db_connection_pool) == 0
    mock_db.close.assert_called_once()

def test_list_connection_pool_with_mocked_clients(connection_manager, mocker):
    mock_client1 = mocker.MagicMock(name="MockMongoClient1")
    mock_client2 = mocker.MagicMock(name="MockMongoClient2")
    alias1 = "test_alias1"
    alias2 = "test_alias2"

    connection_manager.add_to_connection_pool(mock_client1, db_name="test_db1", alias=alias1)
    connection_manager.add_to_connection_pool(mock_client2, db_name="test_db2", alias=alias2)

    aliases = connection_manager.list_connection_pool()

    assert alias1 in aliases
    assert alias2 in aliases

def test_list_connection_pool(connection_manager):
    connection_manager.db_connection_pool = {"alias1": None, "alias2": None}

    aliases = connection_manager.list_connection_pool()

    assert aliases == ["alias1", "alias2"]

def test_get_current_connection_with_valid_alias(connection_manager, mocker):
    mock_client = mocker.MagicMock(name="MockMongoClient")
    alias = "test_alias"

    connection_manager.add_to_connection_pool(mock_client, db_name="test_db", alias=alias)
    connection_manager.current_alias = alias

    current_connection = connection_manager.get_current_connection()

    assert current_connection == mock_client

def test_get_current_connection_with_no_alias_set(connection_manager):
    with pytest.raises(ValueError, match="No current connection alias set."):
        connection_manager.get_current_connection()

def test_get_current_connection_with_invalid_alias(connection_manager):
    connection_manager.current_alias = "invalid_alias"

    with pytest.raises(ValueError, match="Connection with alias 'invalid_alias' not found."):
        connection_manager.get_current_connection()

def test_library_initialization():
    from MongoDBLibrary import MongoDBLibrary

    library = MongoDBLibrary()

    assert hasattr(library, 'connection_manager')
    assert library.connection_manager is not None
