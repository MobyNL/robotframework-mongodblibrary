from typing import Any, Optional

from pymongo import MongoClient, ReturnDocument
from robot.api import logger
from robot.api.deco import keyword

from .connection_pool import ConnectionManager


class MongoDBKeywords:
    """
    Provides keywords for interacting with MongoDB.
    """
    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
        self.default_alias: str = "default"

    @keyword
    def connect_to_database(self, db_user: Optional[str] = None, db_password: Optional[str] = None, db_host: Optional[str] = None, db_port: Optional[int] = None, alias: Optional[str] = None) -> None:
        """
        Connect to MongoDB and add the client object to the connection pool.

        :param alias: Alias for the connection
        :param db_user: Username for authentication (optional)
        :param db_password: Password for authentication (optional)
        :param db_host: Hostname or IP address of the MongoDB server (optional)
        :param db_port: Port number of the MongoDB server (optional, defaults to 27017)
        """
        if alias is None:
            alias = self.default_alias
        try:
            client: MongoClient = MongoClient(
                host=db_host,
                port=int(db_port) if db_port else 27017,
                username=db_user,
                password=db_password
            )
            self.connection_manager.add_to_connection_pool(client, alias)
            logger.info(f"Connected to MongoDB with alias '{alias}' at {db_host}:{db_port}")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
    @keyword
    def connect_to_database_using_connection_string(self, db_conn_string: str, alias: Optional[str] = None) -> None:
        """
        Connect to MongoDB using a connection string and add the client object to the connection pool.

        :param alias: Alias for the connection
        :param db_conn_string: MongoDB connection string
        """
        if alias is None:
            alias = self.default_alias
        try:
            client: MongoClient = MongoClient(db_conn_string)
            self.connection_manager.add_to_connection_pool(client, alias)
            logger.info(f"Connected to MongoDB with alias '{alias}' using connection string.")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB using connection string: {e}")
            raise
            logger.error(f"Failed to connect to MongoDB using connection string: {e}")
            raise

    @keyword
    def disconnect_from_database(self, alias: Optional[str] = None) -> None:
        """
        Disconnect a specific database connection using its alias.

        :param alias: Alias of the connection to disconnect
        """
        if alias is None:
            alias = self.default_alias
        self.connection_manager.remove_from_connection_pool(alias)

    @keyword
    def insert_document(self, alias: str, collection_name: str, document: dict) -> str:
        """
        Insert a document into a collection.

        :param alias: Alias of the connection
        :param collection_name: Name of the collection
        :param document: Document to insert
        :return: ID of the inserted document
        """
        db = self.connection_manager.db_connection_pool[alias]
        collection = db[collection_name]
        return collection.insert_one(document).inserted_id

    @keyword
    def find_document(self, alias: str, collection_name: str, **params: dict) -> Optional[dict]:
        """
        Find a single document in a collection.

        :param alias: Alias of the connection
        :param collection_name: Name of the collection
        :param params: Query parameters to find the document
        :return: Found document as a dictionary, or None if no document matches
        """
        db = self.connection_manager.db_connection_pool[alias]
        collection = db[collection_name]
        return collection.find_one(params)

    @keyword
    def update_document(self, alias: str, collection_name: str, query: dict, update: dict) -> Optional[dict]:
        """
        Update a single document in a collection.

        :param alias: Alias of the connection
        :param collection_name: Name of the collection
        :param query: Query to find the document to update
        :param update: Update operations to apply to the document
        :return: Updated document as a dictionary, or None if no document matches
        """
        db = self.connection_manager.db_connection_pool[alias]
        collection = db[collection_name]
        return collection.find_one_and_update(query, {'$set': update}, return_document=ReturnDocument.AFTER)

    @keyword
    def delete_document(self, alias: str, collection_name: str, **params: dict) -> int:
        """
        Delete a single document from a collection.

        :param alias: Alias of the connection
        :param collection_name: Name of the collection
        :param params: Query parameters to find the document to delete
        :return: Count of deleted documents (0 or 1)
        """
        db = self.connection_manager.db_connection_pool[alias]
        collection = db[collection_name]
        return collection.delete_one(params).deleted_count

    @keyword
    def delete_many(self, alias: str, collection_name: str, **params: dict) -> int:
        """
        Delete multiple documents from a collection.

        :param alias: Alias of the connection
        :param collection_name: Name of the collection
        :param params: Query parameters to find the documents to delete
        :return: Count of deleted documents
        """
        db = self.connection_manager.db_connection_pool[alias]
        collection = db[collection_name]
        return collection.delete_many(params).deleted_count

    @keyword
    def execute_query(self, alias: str, collection_name: str, pipeline: list) -> list:
        """
        Execute an aggregation pipeline query on a collection.

        :param alias: Alias of the connection
        :param collection_name: Name of the collection
        :param pipeline: Aggregation pipeline as a list of stages
        :return: List of query results
        """
        db = self.connection_manager.db_connection_pool[alias]
        collection = db[collection_name]
        return list(collection.aggregate(pipeline))

    @keyword
    def count_documents(self, alias: str, collection_name: str, query: dict) -> int:
        """
        Count the number of documents in a collection matching a query.

        :param alias: Alias of the connection
        :param collection_name: Name of the collection
        :param query: Query to count matching documents
        :return: Count of matching documents
        """
        db = self.connection_manager.db_connection_pool[alias]
        collection = db[collection_name]
        return collection.count_documents(query)

    @keyword
    def delete_all_documents_from_collection(self, alias: str, collection_name: str) -> int:
        """
        Delete all documents from a collection.

        :param alias: Alias of the connection
        :param collection_name: Name of the collection
        :return: Count of deleted documents
        """
        db = self.connection_manager.db_connection_pool[alias]
        collection = db[collection_name]
        result = collection.delete_many({})
        return result.deleted_count

    @keyword
    def switch_database(self, alias: str) -> None:
        """
        Switch the active database connection using its alias.

        :param alias: Alias of the connection to switch to
        """
        if alias not in self.connection_manager.db_connection_pool:
            raise ValueError(f"Connection with alias '{alias}' is not connected.")
        self.connection_manager.default_alias = alias

    @keyword
    def check_query_result(
        self,
        collection_name: str,
        query: dict,
        assertion_operator: str,
        expected_value: Any,
        field: str,
        assertion_message: Optional[str] = None,
        retry_timeout: str = "0 seconds",
        retry_pause: str = "0.5 seconds",
    ) -> None:
        """
        Check the value of a field in query results using an assertion operator and expected value.

        :param collection_name: Name of the collection to query
        :param query: MongoDB query to execute
        :param assertion_operator: Operator for the assertion (e.g., '==', 'contains')
        :param expected_value: Value to compare against
        :param field: Field in the document to check
        :param assertion_message: Custom error message (optional)
        :param retry_timeout: Timeout for retrying the assertion (default: '0 seconds')
        :param retry_pause: Pause between retries (default: '0.5 seconds')
        """
        from robot.libraries.BuiltIn import BuiltIn
        from robot.utils import timestr_to_secs

        check_ok = False
        time_counter = 0

        db = self.connection_manager.db_connection_pool[self.connection_manager.default_alias]
        collection = db[collection_name]

        while not check_ok:
            try:
                results = list(collection.find(query))
                if not results:
                    raise AssertionError("Query returned no results.")

                for document in results:
                    if field not in document:
                        raise AssertionError(f"Field '{field}' not found in document.")

                    actual_value = document[field]
                    if assertion_operator == "==":
                        assert actual_value == expected_value, assertion_message or f"Expected {expected_value}, got {actual_value}."
                    elif assertion_operator == "contains":
                        assert expected_value in actual_value, assertion_message or f"Expected {expected_value} to be in {actual_value}."
                    else:
                        raise ValueError(f"Unsupported assertion operator: {assertion_operator}")

                check_ok = True
            except AssertionError as e:
                if time_counter >= timestr_to_secs(retry_timeout):
                    logger.info(f"Timeout '{retry_timeout}' reached")
                    raise e
                BuiltIn().sleep(retry_pause)
                time_counter += timestr_to_secs(retry_pause)
