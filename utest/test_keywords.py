import pytest

from MongoDBLibrary.connection_pool import ConnectionManager
from MongoDBLibrary.keywords import MongoDBKeywords


@pytest.fixture
def mock_connection_manager():
    return ConnectionManager()

@pytest.fixture
def mongo_keywords(mock_connection_manager):
    return MongoDBKeywords(mock_connection_manager)

def test_connect_to_database(mongo_keywords, mocker):
    mock_client = mocker.MagicMock(name="MockMongoClient")
    mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=mock_client)

    mongo_keywords.connect_to_database(alias="test_alias", db_user="user", db_password="pass", db_host="localhost", db_port=27017)

    # Verify the state of db_connection_pool
    assert "test_alias" in mongo_keywords.connection_manager.db_connection_pool
    assert mongo_keywords.connection_manager.db_connection_pool["test_alias"] == mock_client

def test_connect_to_database_using_connection_string(mongo_keywords, mocker):
    mock_client = mocker.MagicMock(name="MockMongoClient")
    mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=mock_client)

    mongo_keywords.connect_to_database_using_connection_string(alias="test_alias", db_conn_string="mongodb://localhost:27017")

    # Verify the state of db_connection_pool
    assert "test_alias" in mongo_keywords.connection_manager.db_connection_pool
    assert mongo_keywords.connection_manager.db_connection_pool["test_alias"] == mock_client

def test_disconnect_from_database(mongo_keywords, mocker):
    mock_client1 = mocker.MagicMock(name="MockMongoClient1")
    mock_client2 = mocker.MagicMock(name="MockMongoClient2")

    # Use add_to_connection_pool to set up the connection pool
    mongo_keywords.connection_manager.add_to_connection_pool(mock_client1, "alias1")
    mongo_keywords.connection_manager.add_to_connection_pool(mock_client2, "alias2")

    mongo_keywords.disconnect_from_database(alias="alias1")

    # Verify that alias1 is removed from the connection pool
    assert "alias1" not in mongo_keywords.connection_manager.db_connection_pool
    # Verify that the close method was called on the client
    mock_client1.close.assert_called_once()

def test_insert_document(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"test_alias": mock_db}

    # Properly mock the inserted_id attribute
    mock_collection.__getitem__.return_value = mock_collection
    mock_insert_result = mocker.MagicMock()
    mock_insert_result.inserted_id = "mock_id"
    mock_collection.insert_one.return_value = mock_insert_result

    result = mongo_keywords.insert_document(alias="test_alias", collection_name="test_collection", document={"key": "value"})

    assert result == "mock_id"
    mock_collection.insert_one.assert_called_once_with({"key": "value"})

def test_find_document(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"test_alias": mock_db}

    mock_collection.find_one.return_value = {"key": "value"}

    result = mongo_keywords.find_document("test_alias", "test_collection", key="value")

    assert result == {"key": "value"}
    mock_collection.find_one.assert_called_once_with({"key": "value"})

def test_update_document(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"test_alias": mock_db}

    updated_document = {"key": "new_value"}
    mock_collection.find_one_and_update.return_value = updated_document

    result = mongo_keywords.update_document("test_alias", "test_collection", {"key": "value"}, {"key": "new_value"})

    assert result == updated_document
    mock_collection.find_one_and_update.assert_called_once_with({"key": "value"}, {"$set": {"key": "new_value"}}, return_document=mocker.ANY)

def test_delete_document(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"test_alias": mock_db}

    mock_delete_result = mocker.MagicMock()
    mock_delete_result.deleted_count = 1
    mock_collection.delete_one.return_value = mock_delete_result

    result = mongo_keywords.delete_document("test_alias", "test_collection", key="value")

    assert result == 1
    mock_collection.delete_one.assert_called_once_with({"key": "value"})

def test_delete_many(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"test_alias": mock_db}

    mock_delete_result = mocker.MagicMock()
    mock_delete_result.deleted_count = 3
    mock_collection.delete_many.return_value = mock_delete_result

    result = mongo_keywords.delete_many("test_alias", "test_collection", key="value")

    assert result == 3
    mock_collection.delete_many.assert_called_once_with({"key": "value"})

def test_execute_query(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"test_alias": mock_db}

    mock_cursor = mocker.MagicMock()
    mock_cursor.__iter__.return_value = iter([{"key": "value"}])
    mock_collection.aggregate.return_value = mock_cursor

    pipeline = [{"$match": {"key": "value"}}]
    result = mongo_keywords.execute_query("test_alias", "test_collection", pipeline)

    assert result == [{"key": "value"}]
    mock_collection.aggregate.assert_called_once_with(pipeline)

def test_count_documents(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"test_alias": mock_db}

    mock_collection.count_documents.return_value = 5

    query = {"key": "value"}
    result = mongo_keywords.count_documents("test_alias", "test_collection", query)

    assert result == 5
    mock_collection.count_documents.assert_called_once_with(query)

def test_delete_all_documents_from_collection(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"test_alias": mock_db}

    mock_delete_result = mocker.MagicMock()
    mock_delete_result.deleted_count = 10
    mock_collection.delete_many.return_value = mock_delete_result

    result = mongo_keywords.delete_all_documents_from_collection("test_alias", "test_collection")

    assert result == 10
    mock_collection.delete_many.assert_called_once_with({})

def test_switch_database(mongo_keywords, mocker):
    mock_client1 = mocker.MagicMock(name="MockMongoClient1")
    mock_client2 = mocker.MagicMock(name="MockMongoClient2")
    mongo_keywords.connection_manager.db_connection_pool = {"alias1": mock_client1, "alias2": mock_client2}

    mongo_keywords.switch_database("alias2")

    assert mongo_keywords.connection_manager.default_alias == "alias2"

def test_check_query_result(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"test_alias": mock_db}
    mongo_keywords.connection_manager.default_alias = "test_alias"

    mock_collection.find.return_value = [{"key": "value"}]

    # Expect no exceptions if the assertion passes
    mongo_keywords.check_query_result(
        collection_name="test_collection",
        query={"key": "value"},
        assertion_operator="==",
        expected_value="value",
        field="key"
    )

    mock_collection.find.assert_called_once_with({"key": "value"})
