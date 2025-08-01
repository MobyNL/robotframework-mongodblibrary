from typing import Any, Optional

from assertionengine import AssertionOperator, verify_assertion
from pymongo import MongoClient, ReturnDocument
from pymongo.database import Database
from robot.api import logger
from robot.api.deco import keyword
from robot.libraries.BuiltIn import BuiltIn
from robot.utils import DotDict, timestr_to_secs

from MongoDBLibrary.connection_pool import ConnectionManager


class MongoDBKeywords:
    """
    Provides keywords for interacting with MongoDB.

    This class contains Robot Framework keywords for MongoDB operations.
    """

    def __init__(self, connection_manager: ConnectionManager):
        """
        Initializes the MongoDBKeywords library.

        Arguments:
        - ``connection_manager``: Manages connections to MongoDB.
        """
        self.connection_manager = connection_manager
        self.default_alias: str = "default"

    @keyword
    def connect_to_database(self, db_name: str, db_user: Optional[str] = None, db_password: Optional[str] = None, db_host: Optional[str] = None, db_port: Optional[int] = None, alias: Optional[str] = None) -> None:
        """
        Connects to MongoDB and adds the database object to the connection pool.

        Arguments:
        - ``db_name``: Name of the database to connect to.
        - ``db_user``: Username for authentication (optional).
        - ``db_password``: Password for authentication (optional).
        - ``db_host``: Hostname or IP address of the MongoDB server (optional).
        - ``db_port``: Port number of the MongoDB server (optional, defaults to 27017).
        - ``alias``: Alias for the connection (optional).

        Example:
        | Connect To Database    db_name=mydb    db_user=user    db_password=pass    db_host=localhost    db_port=27017

        """
        if alias is None:
            alias = self.default_alias
        try:
            database: Database = MongoClient(
                host=db_host,
                port=int(db_port) if db_port else 27017,
                username=db_user,
                password=db_password
            )[db_name]
            self.connection_manager.add_to_connection_pool(database, db_name, alias)
            logger.info(f"Connected to MongoDB with alias '{alias}' at {db_host}:{db_port}")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    @keyword
    def connect_to_database_using_connection_string(self, db_conn_string: str, db_name: str, alias: Optional[str] = None) -> None:
        """
        Connects to MongoDB using a connection string and adds the database object to the connection pool.

        Arguments:
        - ``db_conn_string``: MongoDB connection string.
        - ``db_name``: Name of the database to connect to.
        - ``alias``: Alias for the connection (optional).

        Example:
        | Connect To Database Using Connection String    db_conn_string=mongodb://localhost:27017    db_name=mydb

        """
        if alias is None:
            alias = self.default_alias
        try:
            database: Database = MongoClient(db_conn_string)[db_name]
            self.connection_manager.add_to_connection_pool(database, db_name, alias)
            logger.info(f"Connected to MongoDB with alias '{alias}' using connection string.")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB using connection string: {e}")
            raise

    @keyword
    def disconnect_from_database(self, alias: Optional[str] = None) -> None:
        """
        Disconnect a specific database connection using its alias.

        Arguments:
        - ``alias``: Alias of the connection to disconnect (optional, defaults to default_alias).

        Example:
        | Disconnect From Database    alias=myalias

        """
        if alias is None:
            alias = self.default_alias
        if alias not in self.connection_manager.db_connection_pool:
            logger.error(f"Attempted to disconnect non-existent alias: {alias}")
            raise ValueError(f"Connection with alias '{alias}' is not connected.")
        self.connection_manager.remove_from_connection_pool(alias)
        logger.info(f"Disconnected alias: {alias}")

    @keyword
    def insert_document(self, collection_name: str, document: dict, alias: Optional[str] = None) -> str:
        """
        Insert a document into a collection.

        Arguments:
        - ``collection_name``: Name of the collection where the document will be inserted.
        - ``document``: Document to insert as a dictionary.
        - ``alias``: Alias of the connection (optional, defaults to default_alias).

        Returns:
        - The ID of the inserted document.

        Example:
        | ${doc_id}    Insert Document    collection_name=mycollection    document={"key": "value"}

        """
        if alias is None:
            alias = self.default_alias
        if alias not in self.connection_manager.db_connection_pool:
            raise KeyError(f"Alias '{alias}' not found in connection pool.")
        db = self.connection_manager.db_connection_pool[alias]
        collection = db[collection_name]
        return collection.insert_one(document).inserted_id

    @keyword
    def find_document(self, collection_name: str, alias: Optional[str] = None, **params: str) -> Optional[dict]:
        """
        Find a single document in a collection.

        Arguments:
        - ``collection_name``: Name of the collection to search.
        - ``params``: Query parameters to locate the document.
        - ``alias``: Alias of the connection (optional, defaults to default_alias).

        Returns:
        - The found document as a dictionary, or None if no document matches the query.

        Example:
        | ${document}    Find Document    collection_name=mycollection    key=value

        """
        if alias is None:
            alias = self.default_alias
        db = self.connection_manager.db_connection_pool[alias]
        collection = db[collection_name]

        result = collection.find_one(params)
        if result is not None:
            return DotDict(result)
        return None

    @keyword
    def update_document(self, collection_name: str, query: dict, update: dict, alias: Optional[str] = None) -> Optional[dict]:
        """
        Update a single document in a collection.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``query``: Query to find the document to update.
        - ``update``: Update operations to apply to the document.
        - ``alias``: Alias of the connection (optional, defaults to default_alias).

        Returns:
        - Updated document as a dictionary, or None if no document matches.

        Example:
        | ${updated_doc}    Update Document    collection_name=mycollection    query={"key": "value"}    update={"key": "new_value"}

        """
        if alias is None:
            alias = self.default_alias
        if alias not in self.connection_manager.db_connection_pool:
            raise KeyError(f"Alias '{alias}' not found in connection pool.")
        db = self.connection_manager.db_connection_pool[alias]
        collection = db[collection_name]
        return collection.find_one_and_update(query, {'$set': update}, return_document=ReturnDocument.AFTER)

    @keyword
    def delete_document(self, collection_name: str, alias: Optional[str] = None, **params: str) -> int:
        """
        Delete a single document from a collection.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``params``: Query parameters to locate the document to delete.
        - ``alias``: Alias of the connection (optional, defaults to default_alias).

        Returns:
        - The count of deleted documents (0 or 1).

        Example:
        | ${deleted_count}    Delete Document    collection_name=mycollection    key=value

        """
        if alias is None:
            alias = self.default_alias
        if alias not in self.connection_manager.db_connection_pool:
            raise KeyError(f"Alias '{alias}' not found in connection pool.")
        db = self.connection_manager.db_connection_pool[alias]
        collection = db[collection_name]
        return collection.delete_one(params).deleted_count

    @keyword
    def delete_many(self, collection_name: str, alias: Optional[str] = None, **params: str) -> int:
        """
        Delete multiple documents from a collection.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``params``: Query parameters to find the documents to delete.
        - ``alias``: Alias of the connection (optional, defaults to default_alias).

        Returns:
        - Count of deleted documents.

        Example:
        | ${deleted_count}    Delete Many    collection_name=mycollection    key=value

        """
        if alias is None:
            alias = self.default_alias
        if alias not in self.connection_manager.db_connection_pool:
            raise KeyError(f"Alias '{alias}' not found in connection pool.")
        db = self.connection_manager.db_connection_pool[alias]
        collection = db[collection_name]
        return collection.delete_many(params).deleted_count

    @keyword
    def execute_query(self, collection_name: str, pipeline: list, alias: Optional[str] = None) -> list:
        """
        Execute an aggregation pipeline query on a collection.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``pipeline``: Aggregation pipeline as a list of stages.
        - ``alias``: Alias of the connection (optional, defaults to default_alias).

        Returns:
        - A list of query results.

        Example:
        | ${results}    Execute Query    collection_name=mycollection    pipeline=[{"$match": {"key": "value"}}]

        """
        if alias is None:
            alias = self.default_alias

        if not isinstance(pipeline, list):
            raise Exception("Invalid pipeline: must be a list of stages.")

        if alias not in self.connection_manager.db_connection_pool:
            raise KeyError(f"Alias '{alias}' not found in connection pool.")

        db = self.connection_manager.db_connection_pool[alias]
        collection = db[collection_name]
        return list(collection.aggregate(pipeline))

    @keyword
    def count_documents(self, collection_name: str, alias: Optional[str] = None,  **params) -> int:
        """
        Count the number of documents in a collection matching a query.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``alias``: Alias of the connection (optional, defaults to default_alias).
        - ``params``: key-value pairs to count matching documents.

        Returns:
        - The count of matching documents.

        Example:
        | ${count}    Count Documents    collection_name=mycollection    query={"key": "value"}

        """
        if alias is None:
            alias = self.default_alias
        db = self.connection_manager.db_connection_pool[alias]
        collection = db[collection_name]
        return collection.count_documents(params)

    @keyword
    def delete_all_documents_from_collection(self, collection_name: str, alias: Optional[str] = None) -> int:
        """
        Delete all documents from a collection.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``alias``: Alias of the connection (optional, defaults to default_alias).

        Returns:
        - The count of deleted documents.

        Example:
        | ${deleted_count}    Delete All Documents From Collection    collection_name=mycollection

        """
        if alias is None:
            alias = self.default_alias
        if alias not in self.connection_manager.db_connection_pool:
            raise KeyError(f"Alias '{alias}' not found in connection pool.")
        db = self.connection_manager.db_connection_pool[alias]
        collection = db[collection_name]
        result = collection.delete_many({})
        return result.deleted_count

    @keyword
    def switch_database(self, alias: str) -> None:
        """
        Switch the active database connection using its alias.

        Arguments:
        - ``alias``: Alias of the connection to switch to.

        Example:
        | Switch Database    alias=myalias

        """
        if alias not in self.connection_manager.db_connection_pool:
            raise ValueError(f"Connection with alias '{alias}' is not connected.")
        self.connection_manager.default_alias = alias

    @keyword
    def check_query_result(
        self,
        collection_name: str,
        query: dict,
        assertion_operator: AssertionOperator,
        expected_value: Any,
        field: str,
        assertion_message: Optional[str] = None,
        retry_timeout: str = "0 seconds",
        retry_pause: str = "0.5 seconds",
        alias: Optional[str] = None
    ) -> None:
        """
        Check the result of a query against an expected value.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``query``: Query to find the document.
        - ``assertion_operator``: Operator for assertion (e.g., ==, !=, >, <).
        - ``expected_value``: Expected value for the assertion.
        - ``field``: Field in the document to check.
        - ``assertion_message``: Custom message for assertion failure (optional).
        - ``retry_timeout``: Timeout for retrying the query (optional).
        - ``retry_pause``: Pause duration between retries (optional).
        - ``alias``: Alias of the connection (optional, defaults to default_alias).

        Example:
        | Check Query Result    collection_name=mycollection    query={"key": "value"}    assertion_operator==    expected_value=42    field=key

        """
        if alias is None:
            alias = self.default_alias

        if alias not in self.connection_manager.db_connection_pool:
            logger.error(f"Alias '{alias}' not found in connection pool.")
            raise KeyError(f"Alias '{alias}' not found in connection pool.")

        check_ok = False
        time_counter = 0

        db = self.connection_manager.db_connection_pool[alias]
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
                    verify_assertion(
                        actual_value,
                        assertion_operator,
                        expected_value,
                        f"Field '{field}' value mismatch:",
                        assertion_message
                    )

                check_ok = True
            except AssertionError as e:
                if time_counter >= timestr_to_secs(retry_timeout):
                    logger.info(f"Timeout '{retry_timeout}' reached")
                    raise e
                BuiltIn().sleep(retry_pause)
                time_counter += timestr_to_secs(retry_pause)

    @keyword
    def check_document_count(
        self,
        collection_name: str,
        query: dict,
        assertion_operator: AssertionOperator,
        expected_count: int,
        assertion_message: Optional[str] = None,
        retry_timeout: str = "0 seconds",
        retry_pause: str = "0.5 seconds",
        alias: Optional[str] = None
    ) -> None:
        """
        Check the count of documents matching a query against an expected value.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``query``: Query to count matching documents.
        - ``assertion_operator``: Operator for assertion (e.g., ==, !=, >, <).
        - ``expected_count``: Expected count for the assertion.
        - ``assertion_message``: Custom message for assertion failure (optional).
        - ``retry_timeout``: Timeout for retrying the query (optional).
        - ``retry_pause``: Pause duration between retries (optional).
        - ``alias``: Alias of the connection (optional, defaults to default_alias).

        Example:
        | Check Document Count    collection_name=mycollection    query={"key": "value"}    assertion_operator==    expected_count=5

        """
        if alias is None:
            alias = self.default_alias

        if alias not in self.connection_manager.db_connection_pool:
            logger.error(f"Alias '{alias}' not found in connection pool.")
            raise KeyError(f"Alias '{alias}' not found in connection pool.")

        check_ok = False
        time_counter = 0

        db = self.connection_manager.db_connection_pool[alias]
        collection = db[collection_name]

        while not check_ok:
            try:
                actual_count = collection.count_documents(query)
                verify_assertion(
                    actual_count,
                    assertion_operator,
                    expected_count,
                    "Wrong document count:",
                    assertion_message
                )
                check_ok = True
            except AssertionError as e:
                if time_counter >= timestr_to_secs(retry_timeout):
                    logger.info(f"Timeout '{retry_timeout}' reached")
                    raise e
                BuiltIn().sleep(retry_pause)
                time_counter += timestr_to_secs(retry_pause)
