import mongomock
import pytest

from MongoDBLibrary.connection_pool import ConnectionManager
from MongoDBLibrary.keywords import MongoDBKeywords


@pytest.fixture
def connection_manager():
    return ConnectionManager()


@pytest.fixture
def database():
    """A real (in-memory) pymongo-compatible Database, so API misuse fails the test."""
    return mongomock.MongoClient()["test_db"]


@pytest.fixture
def mongo_keywords(connection_manager):
    return MongoDBKeywords(connection_manager)


@pytest.fixture
def mongo(mongo_keywords):
    """Keywords backed by an in-memory MongoDB under the ``default`` alias.

    Using a pymongo-compatible database rather than a MagicMock means misuse of the
    Database/Collection API, or a query whose value has the wrong type, fails the test.
    """
    client = mongomock.MongoClient()
    mongo_keywords.connection_manager.add_to_connection_pool(client["test_db"], "default")
    return mongo_keywords


@pytest.fixture
def no_coercion(connection_manager):
    """Keywords with ObjectId coercion switched off, backed by an in-memory MongoDB."""
    keywords = MongoDBKeywords(connection_manager, coerce_object_ids=False)
    client = mongomock.MongoClient()
    connection_manager.add_to_connection_pool(client["test_db"], "default")
    return keywords


@pytest.fixture
def mock_db(mongo_keywords, mocker):
    """Keywords backed by a MagicMock database, for driver-error paths only."""
    database = mocker.MagicMock(name="MockDatabase")
    mongo_keywords.connection_manager.db_connection_pool["default"] = database
    return database
