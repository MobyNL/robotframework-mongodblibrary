import pytest
from pytest import param
from robot.utils import DotDict

from MongoDBLibrary.connection_pool import ConnectionManager
from MongoDBLibrary.keywords import AssertionOperator, MongoDBKeywords


@pytest.fixture
def mock_connection_manager():
    return ConnectionManager()


@pytest.fixture
def mongo_keywords(mock_connection_manager):
    return MongoDBKeywords(mock_connection_manager)


def test_connect_to_database(mongo_keywords, mocker):
    mock_client = mocker.MagicMock(name="MockMongoClient")
    mock_client.__getitem__.return_value.name = "test_db"
    mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=mock_client)

    mongo_keywords.connect_to_database(
        db_name="test_db",
        alias="default",
        db_user="user",
        db_password="pass",
        db_host="localhost",
        db_port=27017,
    )

    # Verify the state of db_connection_pool
    assert "default" in mongo_keywords.connection_manager.db_connection_pool
    assert mongo_keywords.connection_manager.db_connection_pool["default"].name == "test_db"


def test_connect_to_database_using_connection_string(mongo_keywords, mocker):
    mock_client = mocker.MagicMock(name="MockMongoClient")
    mock_client.__getitem__.return_value.name = "test_db"
    mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=mock_client)

    mongo_keywords.connect_to_database_using_connection_string(
        db_conn_string="mongodb://localhost:27017", db_name="test_db", alias="test_alias"
    )

    # Verify the state of db_connection_pool
    assert "test_alias" in mongo_keywords.connection_manager.db_connection_pool
    assert mongo_keywords.connection_manager.db_connection_pool["test_alias"].name == "test_db"


def test_connect_to_database_failure(mongo_keywords, mocker):
    mocker.patch("MongoDBLibrary.keywords.MongoClient", side_effect=Exception("Connection failed"))

    with pytest.raises(Exception, match="Connection failed") as excinfo:
        mongo_keywords.connect_to_database(db_name="test_db", db_host="localhost", db_port=27017)
    assert "Connection failed" in str(excinfo.value)


def test_connect_to_database_using_connection_string_failure(mongo_keywords, mocker):
    mocker.patch("MongoDBLibrary.keywords.MongoClient", side_effect=Exception("Invalid connection string"))

    with pytest.raises(Exception, match="Invalid connection string") as excinfo:
        mongo_keywords.connect_to_database_using_connection_string(db_conn_string="invalid", db_name="test_db")
    assert "Invalid connection string" in str(excinfo.value)


def test_disconnect_from_database(mongo_keywords, mocker):
    mock_client = mocker.MagicMock(name="MockMongoClient")
    mongo_keywords.connection_manager.add_to_connection_pool(mock_client, db_name="test_db", alias="test_alias")

    # Ensure alias is properly added to the pool
    assert "test_alias" in mongo_keywords.connection_manager.db_connection_pool

    mongo_keywords.disconnect_from_database(alias="test_alias")

    assert "test_alias" not in mongo_keywords.connection_manager.db_connection_pool


def test_disconnect_from_nonexistent_database(mongo_keywords):
    with pytest.raises(ValueError, match="Connection with alias 'nonexistent_alias' is not connected.") as excinfo:
        mongo_keywords.disconnect_from_database(alias="nonexistent_alias")
    assert "nonexistent_alias" in str(excinfo.value)


def test_disconnect_from_database_no_alias(mongo_keywords, mocker):
    mock_client = mocker.MagicMock(name="MockMongoClient")
    mongo_keywords.connection_manager.add_to_connection_pool(mock_client, db_name="test_db", alias="default")

    # Ensure alias is properly added to the pool
    assert "default" in mongo_keywords.connection_manager.db_connection_pool

    mongo_keywords.disconnect_from_database()

    assert "default" not in mongo_keywords.connection_manager.db_connection_pool


@pytest.mark.parametrize(
    "alias, collection_name, document, expected_result",
    [
        param("test_alias", "test_collection", {"key": "value"}, "mock_id", id="valid_alias"),
        param(None, "test_collection", {"key": "value"}, "mock_id", id="default_alias"),
    ],
)
def test_insert_document(mongo_keywords, mocker, alias, collection_name, document, expected_result):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {alias or "default": mock_db}

    mock_insert_result = mocker.MagicMock()
    mock_insert_result.inserted_id = expected_result
    mock_collection.insert_one.return_value = mock_insert_result

    result = mongo_keywords.insert_document(alias=alias, collection_name=collection_name, document=document)

    assert result == expected_result
    mock_collection.insert_one.assert_called_once_with(document)


@pytest.mark.parametrize(
    "alias, collection_name, query, update, expected_result",
    [
        param("test_alias", "test_collection", {"key": "value"}, {"key": "new_value"}, {"key": "new_value"}, id="valid_alias"),
        param(None, "test_collection", {"key": "value"}, {"key": "new_value"}, {"key": "new_value"}, id="default_alias"),
    ],
)
def test_update_document(mongo_keywords, mocker, alias, collection_name, query, update, expected_result):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {alias or "default": mock_db}

    mock_collection.find_one_and_update.return_value = expected_result

    result = mongo_keywords.update_document(alias=alias, collection_name=collection_name, query=query, update=update)

    assert result == expected_result
    mock_collection.find_one_and_update.assert_called_once_with(query, {"$set": update}, return_document=mocker.ANY)


@pytest.mark.parametrize(
    "alias, collection_name, key, expected_deleted_count",
    [
        param("test_alias", "test_collection", {"key": "value"}, 1, id="valid_alias"),
        param(None, "test_collection", {"key": "value"}, 1, id="default_alias"),
    ],
)
def test_delete_document(mongo_keywords, mocker, alias, collection_name, key, expected_deleted_count):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {alias or "default": mock_db}

    mock_collection.delete_one.return_value.deleted_count = expected_deleted_count

    # Fix: Ensure the key is passed correctly
    result = mongo_keywords.delete_document(alias=alias, collection_name=collection_name, key=key["key"])

    assert result == expected_deleted_count
    mock_collection.delete_one.assert_called_once_with(key)


@pytest.mark.parametrize(
    "alias, collection_name, expected_deleted_count",
    [
        param("test_alias", "test_collection", 10, id="valid_alias"),
        param(None, "test_collection", 10, id="default_alias"),
    ],
)
def test_delete_all_documents_from_collection(mongo_keywords, mocker, alias, collection_name, expected_deleted_count):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {alias or "default": mock_db}

    mock_collection.delete_many.return_value.deleted_count = expected_deleted_count

    result = mongo_keywords.delete_all_documents_from_collection(alias=alias, collection_name=collection_name)

    assert result == expected_deleted_count
    mock_collection.delete_many.assert_called_once_with({})


def test_switch_database(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mongo_keywords.connection_manager.db_connection_pool = {"test_alias": mock_db}

    mongo_keywords.switch_database(alias="test_alias")

    assert mongo_keywords.connection_manager.default_alias == "test_alias"


def test_switch_to_nonexistent_database(mongo_keywords):
    with pytest.raises(ValueError, match="Connection with alias 'nonexistent_alias' is not connected."):
        mongo_keywords.switch_database(alias="nonexistent_alias")


def test_execute_query(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"test_alias": mock_db}

    mock_collection.aggregate.return_value = [{"key": "value"}]

    result = mongo_keywords.execute_query(
        alias="test_alias",
        collection_name="test_collection",
        pipeline=[{"$match": {"key": "value"}}],
    )

    assert result == [{"key": "value"}]
    mock_collection.aggregate.assert_called_once_with([{"$match": {"key": "value"}}])


def test_execute_query_invalid_pipeline(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"default": mock_db}

    with pytest.raises(Exception, match="Invalid pipeline"):
        mongo_keywords.execute_query(
            collection_name="test_collection", pipeline="invalid_pipeline"
        )


def test_execute_query_missing_alias(mongo_keywords):
    with pytest.raises(KeyError, match="Alias 'missing_alias' not found in connection pool."):
        mongo_keywords.execute_query(
            collection_name="test_collection",
            pipeline=[{"$match": {"key": "value"}}],
            alias="missing_alias",
        )


def test_count_documents(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"test_alias": mock_db}

    mock_collection.count_documents.return_value = 5

    result = mongo_keywords.count_documents(
        alias="test_alias", collection_name="test_collection", key="value"
    )

    assert result == 5
    mock_collection.count_documents.assert_called_once_with({"key": "value"})


def test_count_documents_invalid_query(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"default": mock_db}

    mock_collection.count_documents.side_effect = Exception("Invalid query")

    with pytest.raises(Exception, match="Invalid query"):
        mongo_keywords.count_documents(
            collection_name="test_collection", query="invalid_query"
        )


def test_count_documents_missing_alias(mongo_keywords):
    with pytest.raises(KeyError, match="'missing_alias'"):
        mongo_keywords.count_documents(
            collection_name="test_collection", query={"key": "value"}, alias="missing_alias"
        )


def test_check_query_result(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"default": mock_db}

    mock_collection.find.return_value = [{"field": 42}]

    mongo_keywords.check_query_result(
        collection_name="test_collection",
        query={"key": "value"},
        assertion_operator=AssertionOperator.equal,
        expected_value=42,
        field="field",
    )

    mock_collection.find.assert_called_once_with({"key": "value"})


def test_check_query_result_failure(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"test_alias": mock_db}

    mock_collection.find.return_value = []  # Simulate no results

    with pytest.raises(AssertionError, match="Query returned no results."):
        mongo_keywords.check_query_result(
            collection_name="test_collection",
            query={"key": "value"},
            assertion_operator=AssertionOperator.equals,
            expected_value="value",
            field="key",
            alias="test_alias",
        )


def test_check_query_result_invalid_operator(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"default": mock_db}

    mock_collection.find.return_value = [{"field": 42}]

    with pytest.raises(RuntimeError, match="is not a valid assertion operator"):
        mongo_keywords.check_query_result(
            collection_name="test_collection",
            query={"key": "value"},
            assertion_operator="invalid_operator",
            expected_value=42,
            field="field",
        )


def test_check_document_count(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"default": mock_db}

    mock_collection.count_documents.return_value = 5

    mongo_keywords.check_document_count(
        collection_name="test_collection",
        query={"key": "value"},
        assertion_operator=AssertionOperator.equal,
        expected_count=5,
    )

    mock_collection.count_documents.assert_called_once_with({"key": "value"})


def test_check_document_count_invalid_operator(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"default": mock_db}

    mock_collection.count_documents.return_value = 5

    with pytest.raises(RuntimeError, match="is not a valid assertion operator"):
        mongo_keywords.check_document_count(
            collection_name="test_collection",
            query={"key": "value"},
            assertion_operator="invalid_operator",
            expected_count=5,
        )


def test_check_query_result_no_field_in_document(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"default": mock_db}

    mock_collection.find.return_value = [{"other_field": 42}]

    with pytest.raises(AssertionError, match="Field 'field' not found in document."):
        mongo_keywords.check_query_result(
            collection_name="test_collection",
            query={"key": "value"},
            assertion_operator=AssertionOperator.equal,
            expected_value=42,
            field="field",
        )


def test_check_document_count_no_connection(mongo_keywords):
    with pytest.raises(KeyError, match="Alias 'nonexistent_alias' not found in connection pool."):
        mongo_keywords.check_document_count(
            collection_name="test_collection",
            query={"key": "value"},
            assertion_operator=AssertionOperator.equal,
            expected_count=5,
            alias="nonexistent_alias",
        )


def test_check_query_result_no_results(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"default": mock_db}

    mock_collection.find.return_value = []

    with pytest.raises(AssertionError, match="Query returned no results."):
        mongo_keywords.check_query_result(
            collection_name="test_collection",
            query={"key": "value"},
            assertion_operator=AssertionOperator.equal,
            expected_value=42,
            field="field",
        )


def test_check_document_count_timeout(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"default": mock_db}

    mock_collection.count_documents.return_value = 0

    with pytest.raises(AssertionError, match="Wrong document count:"):
        mongo_keywords.check_document_count(
            collection_name="test_collection",
            query={"key": "value"},
            assertion_operator=AssertionOperator.equal,
            expected_count=5,
            retry_timeout="1 second",
            retry_pause="0.5 seconds",
        )


def test_check_query_result_timeout(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"default": mock_db}

    mock_collection.find.return_value = []

    with pytest.raises(AssertionError, match="Query returned no results."):
        mongo_keywords.check_query_result(
            collection_name="test_collection",
            query={"key": "value"},
            assertion_operator=AssertionOperator.equal,
            expected_value=42,
            field="field",
            retry_timeout="1 second",
            retry_pause="0.5 seconds",
        )


def test_check_document_count_field_not_found(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"default": mock_db}

    mock_collection.count_documents.return_value = 0

    with pytest.raises(AssertionError, match="Wrong document count:"):
        mongo_keywords.check_document_count(
            collection_name="test_collection",
            query={"key": "value"},
            assertion_operator=AssertionOperator.equal,
            expected_count=5,
            retry_timeout="1 second",
            retry_pause="0.5 seconds",
        )


def test_delete_many_no_alias(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"default": mock_db}

    mock_collection.delete_many.return_value.deleted_count = 2

    result = mongo_keywords.delete_many(
        collection_name="test_collection", key="value"
    )

    assert result == 2
    mock_collection.delete_many.assert_called_once_with({"key": "value"})


def test_delete_many_invalid_alias(mongo_keywords):
    with pytest.raises(KeyError, match="Alias 'invalid_alias' not found in connection pool."):
        mongo_keywords.delete_many(
            collection_name="test_collection", alias="invalid_alias", key="value"
        )


def test_mongo_keywords_initialization(mock_connection_manager):
    mongo_keywords = MongoDBKeywords(mock_connection_manager)
    assert mongo_keywords.default_alias == "default"
    assert mongo_keywords.connection_manager == mock_connection_manager


def test_insert_document_invalid_alias(mongo_keywords):
    with pytest.raises(KeyError, match="Alias 'invalid_alias' not found in connection pool.") as excinfo:
        mongo_keywords.insert_document(alias="invalid_alias", collection_name="test_collection", document={"key": "value"})
    assert "invalid_alias" in str(excinfo.value)


def test_disconnect_from_database_missing_alias(mongo_keywords):
    with pytest.raises(ValueError, match="Connection with alias 'nonexistent_alias' is not connected."):
        mongo_keywords.disconnect_from_database(alias="nonexistent_alias")


def test_insert_document_missing_alias(mongo_keywords):
    with pytest.raises(KeyError, match="Alias 'nonexistent_alias' not found in connection pool."):
        mongo_keywords.insert_document(
            alias="nonexistent_alias",
            collection_name="test_collection",
            document={"key": "value"}
        )


def test_find_document_no_results(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"test_alias": mock_db}

    mock_collection.find_one.return_value = None

    result = mongo_keywords.find_document(
        collection_name="test_collection",
        alias="test_alias",
        key="value"
    )

    assert result is None


def test_update_document_missing_alias(mongo_keywords):
    with pytest.raises(KeyError, match="Alias 'nonexistent_alias' not found in connection pool."):
        mongo_keywords.update_document(
            alias="nonexistent_alias",
            collection_name="test_collection",
            query={"key": "value"},
            update={"key": "new_value"}
        )


def test_delete_document_missing_alias(mongo_keywords):
    with pytest.raises(KeyError, match="Alias 'nonexistent_alias' not found in connection pool."):
        mongo_keywords.delete_document(
            alias="nonexistent_alias",
            collection_name="test_collection",
            key="value"
        )


def test_delete_all_documents_missing_alias(mongo_keywords):
    with pytest.raises(KeyError, match="Alias 'nonexistent_alias' not found in connection pool."):
        mongo_keywords.delete_all_documents_from_collection(
            alias="nonexistent_alias",
            collection_name="test_collection"
        )


def test_check_query_result_missing_field(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"default": mock_db}

    # Simulate documents missing the specified field
    mock_collection.find.return_value = [{"other_field": 42}]

    with pytest.raises(AssertionError, match="Field 'missing_field' not found in document."):
        mongo_keywords.check_query_result(
            collection_name="test_collection",
            query={"key": "value"},
            assertion_operator=AssertionOperator.equal,
            expected_value=42,
            field="missing_field"
        )


def test_check_query_result_missing_field_edge_case(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"default": mock_db}

    # Simulate documents with multiple fields but missing the target field
    mock_collection.find.return_value = [
        {"irrelevant_field": 1},
        {"another_field": 2}
    ]

    with pytest.raises(AssertionError, match="Field 'target_field' not found in document."):
        mongo_keywords.check_query_result(
            collection_name="test_collection",
            query={"key": "value"},
            assertion_operator=AssertionOperator.equal,
            expected_value=42,
            field="target_field"
        )


def test_check_query_result_multiple_documents_missing_field(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"default": mock_db}

    # Simulate multiple documents, none containing the target field
    mock_collection.find.return_value = [
        {"irrelevant_field": 1},
        {"another_field": 2},
        {"yet_another_field": 3}
    ]

    with pytest.raises(AssertionError, match="Field 'target_field' not found in document."):
        mongo_keywords.check_query_result(
            collection_name="test_collection",
            query={"key": "value"},
            assertion_operator=AssertionOperator.equal,
            expected_value=42,
            field="target_field"
        )


def test_delete_all_documents_no_alias_refined(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"default": mock_db}

    mock_collection.delete_many.return_value.deleted_count = 10

    result = mongo_keywords.delete_all_documents_from_collection(collection_name="test_collection")

    assert result == 10
    mock_collection.delete_many.assert_called_once_with({})


def test_switch_database_refined(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mongo_keywords.connection_manager.db_connection_pool = {"test_alias": mock_db}

    mongo_keywords.switch_database(alias="test_alias")

    assert mongo_keywords.connection_manager.default_alias == "test_alias"


def test_switch_to_nonexistent_database_refined(mongo_keywords):
    with pytest.raises(ValueError, match="Connection with alias 'nonexistent_alias' is not connected."):
        mongo_keywords.switch_database(alias="nonexistent_alias")


def test_check_query_result_alias_not_found(mongo_keywords, mocker):
    # Mock the connection pool to simulate alias not found
    mock_connection_pool = {}
    mocker.patch.object(mongo_keywords.connection_manager, 'db_connection_pool', mock_connection_pool)

    with pytest.raises(KeyError, match="Alias 'nonexistent_alias' not found in connection pool."):
        mongo_keywords.check_query_result(
            collection_name="test_collection",
            query={},
            assertion_operator=AssertionOperator.equals,
            expected_value=42,
            field="key",
            alias="nonexistent_alias"
        )


def test_find_document_with_result(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"test_alias": mock_db}

    # Ensure the mock returns a dictionary
    mock_collection.find_one.return_value = {"key": "value"}

    result = mongo_keywords.find_document(
        collection_name="test_collection",
        alias="test_alias",
        key="value"
    )

    # Verify the result is a DotDict and contains the expected data
    assert isinstance(result, DotDict)
    assert result["key"] == "value"
    mock_collection.find_one.assert_called_once_with({"key": "value"})


def test_find_document_no_result(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"test_alias": mock_db}

    # Ensure the mock returns None
    mock_collection.find_one.return_value = None

    result = mongo_keywords.find_document(
        collection_name="test_collection",
        alias="test_alias",
        key="value"
    )

    # Verify the result is None
    assert result is None
    mock_collection.find_one.assert_called_once_with({"key": "value"})


def test_find_document_with_default_alias(mongo_keywords, mocker):
    mock_db = mocker.MagicMock(name="MockDatabase")
    mock_collection = mocker.MagicMock(name="MockCollection")
    mock_db.__getitem__.return_value = mock_collection
    mongo_keywords.connection_manager.db_connection_pool = {"default": mock_db}

    # Ensure the mock returns a dictionary
    mock_collection.find_one.return_value = {"key": "value"}

    result = mongo_keywords.find_document(
        collection_name="test_collection",
        key="value"
    )

    # Verify the result is a DotDict and contains the expected data
    assert isinstance(result, DotDict)
    assert result["key"] == "value"
    mock_collection.find_one.assert_called_once_with({"key": "value"})
