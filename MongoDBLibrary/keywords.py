import time
from typing import Any, Callable, Optional

from assertionengine import AssertionOperator, verify_assertion
from pymongo import MongoClient, ReturnDocument
from pymongo.collection import Collection
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

    # ----------------------------------------------------------------- #
    # Internals
    # ----------------------------------------------------------------- #

    def _resolve_alias(self, alias: Optional[str] = None) -> str:
        """Return ``alias``, or the currently active alias when None."""
        return self.connection_manager.default_alias if alias is None else alias

    def _get_database(self, alias: Optional[str] = None) -> Database:
        """Return the pooled database for ``alias``, raising if it is not connected."""
        alias = self._resolve_alias(alias)
        if alias not in self.connection_manager.db_connection_pool:
            raise KeyError(f"Alias '{alias}' not found in connection pool.")
        return self.connection_manager.db_connection_pool[alias]

    def _get_collection(self, collection_name: str, alias: Optional[str] = None) -> Collection:
        """Return a collection from the pooled database for ``alias``."""
        return self._get_database(alias)[collection_name]

    def _retry_until_no_assertion_error(self, check: Callable[[], None], retry_timeout: str, retry_pause: str) -> None:
        """
        Run ``check`` until it stops raising AssertionError or ``retry_timeout`` elapses.

        The deadline is measured against a real clock, so the loop terminates even
        when ``retry_pause`` is zero and regardless of how long ``check`` itself takes.
        """
        deadline = time.monotonic() + timestr_to_secs(retry_timeout)
        pause = timestr_to_secs(retry_pause)
        while True:
            try:
                check()
                return
            except AssertionError:
                if time.monotonic() >= deadline:
                    logger.info(f"Timeout '{retry_timeout}' reached")
                    raise
                BuiltIn().sleep(pause)

    # ----------------------------------------------------------------- #
    # Connecting
    # ----------------------------------------------------------------- #

    @keyword
    def connect_to_database(self, db_name: str, db_user: Optional[str] = None, db_password: Optional[str] = None, db_host: Optional[str] = None, db_port: Optional[int] = None, alias: Optional[str] = None) -> None:
        """
        Connects to MongoDB and adds the database object to the connection pool.

        The connection is verified before the keyword passes, so a failure to reach
        the server or to authenticate is reported here rather than by a later keyword.

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
        alias = self._resolve_alias(alias)
        client: MongoClient = MongoClient(
            host=db_host,
            port=int(db_port) if db_port else 27017,
            username=db_user,
            password=db_password
        )
        try:
            client.admin.command("ping")
        except Exception:
            client.close()
            raise
        self.connection_manager.add_to_connection_pool(client[db_name], alias)
        logger.info(f"Connected to MongoDB with alias '{alias}' at {db_host}:{db_port}")

    @keyword
    def connect_to_database_using_connection_string(self, db_conn_string: str, db_name: str, alias: Optional[str] = None) -> None:
        """
        Connects to MongoDB using a connection string and adds the database object to the connection pool.

        The connection is verified before the keyword passes, so a failure to reach
        the server or to authenticate is reported here rather than by a later keyword.

        Arguments:
        - ``db_conn_string``: MongoDB connection string.
        - ``db_name``: Name of the database to connect to.
        - ``alias``: Alias for the connection (optional).

        Example:
        | Connect To Database Using Connection String    db_conn_string=mongodb://localhost:27017    db_name=mydb

        """
        alias = self._resolve_alias(alias)
        client: MongoClient = MongoClient(db_conn_string)
        try:
            client.admin.command("ping")
        except Exception:
            client.close()
            raise
        self.connection_manager.add_to_connection_pool(client[db_name], alias)
        logger.info(f"Connected to MongoDB with alias '{alias}' using connection string.")


    @keyword
    def disconnect_from_database(self, alias: Optional[str] = None) -> None:
        """
        Disconnect a specific database connection using its alias.

        Arguments:
        - ``alias``: Alias of the connection to disconnect (optional, defaults to the active alias).

        Example:
        | Disconnect From Database    alias=myalias

        """
        alias = self._resolve_alias(alias)
        if alias not in self.connection_manager.db_connection_pool:
            logger.error(f"Attempted to disconnect non-existent alias: {alias}")
            raise ValueError(f"Connection with alias '{alias}' is not connected.")
        self.connection_manager.remove_from_connection_pool(alias)
        logger.info(f"Disconnected alias: {alias}")

    @keyword
    def disconnect_from_all_databases(self) -> None:
        """
        Disconnect every connection in the connection pool.

        Useful as a suite teardown, since the library has ``GLOBAL`` scope and
        otherwise keeps its connections open for the whole run.

        Example:
        | Disconnect From All Databases

        """
        self.connection_manager.clear_connection_pool()

    @keyword
    def list_database_connections(self) -> list[str]:
        """
        List the aliases of all currently connected databases.

        Returns:
        - A list of connection aliases.

        Example:
        | ${aliases}    List Database Connections

        """
        return self.connection_manager.list_connection_pool()


    @keyword
    def switch_database(self, alias: str) -> None:
        """
        Switch the active database connection using its alias.

        Keywords called afterwards without an explicit ``alias`` use this connection.

        Arguments:
        - ``alias``: Alias of the connection to switch to.

        Example:
        | Switch Database    alias=myalias

        """
        if alias not in self.connection_manager.db_connection_pool:
            raise ValueError(f"Connection with alias '{alias}' is not connected.")
        self.connection_manager.default_alias = alias


    @keyword
    def check_if_database_connection_exists(self, alias: Optional[str] = None) -> None:
        """
        Check if a database connection exists for the given alias.

        Arguments:
        - ``alias``: Alias of the connection to check (optional, defaults to the active alias).

        Raises:
        - ValueError: If the connection does not exist.

        Example:
        | Check If Database Connection Exists    alias=myalias

        """
        alias = self._resolve_alias(alias)
        if alias not in self.connection_manager.db_connection_pool:
            raise ValueError(f"No database connection exists for alias '{alias}'.")


    # ----------------------------------------------------------------- #
    # Documents
    # ----------------------------------------------------------------- #

    @keyword
    def insert_document(self, collection_name: str, document: dict, alias: Optional[str] = None) -> Any:
        """
        Insert a document into a collection.

        Arguments:
        - ``collection_name``: Name of the collection where the document will be inserted.
        - ``document``: Document to insert as a dictionary.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - The ID of the inserted document. This is a BSON ``ObjectId`` unless the
          document supplied its own ``_id``, so it has no length and keywords such as
          `Should Not Be Empty` do not apply to it.

        Example:
        | ${doc_id}    Insert Document    collection_name=mycollection    document={"key": "value"}

        """
        collection = self._get_collection(collection_name, alias)
        return collection.insert_one(document).inserted_id


    # ----------------------------------------------------------------- #
    # Reading
    # ----------------------------------------------------------------- #

    @keyword
    def find_document(self, collection_name: str, alias: Optional[str] = None, **params: Any) -> Optional[dict]:
        """
        Find a single document in a collection.

        Arguments:
        - ``collection_name``: Name of the collection to search.
        - ``params``: Query parameters to locate the document.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - The found document, or None if no document matches the query.

        Example:
        | ${document}    Find Document    collection_name=mycollection    key=value

        """
        collection = self._get_collection(collection_name, alias)
        result = collection.find_one(params)
        return DotDict(result) if result is not None else None




    @keyword
    def count_documents(self, collection_name: str, alias: Optional[str] = None, **params: Any) -> int:
        """
        Count the number of documents in a collection matching a query.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``params``: key-value pairs to count matching documents.

        Returns:
        - The count of matching documents.

        Example:
        | ${count}    Count Documents    collection_name=mycollection    key=value

        """
        collection = self._get_collection(collection_name, alias)
        return collection.count_documents(params)


    @keyword
    def execute_query(self, collection_name: str, pipeline: list, alias: Optional[str] = None) -> list:
        """
        Execute an aggregation pipeline query on a collection.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``pipeline``: Aggregation pipeline as a list of stages.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - A list of query results.

        Example:
        | ${results}    Execute Query    collection_name=mycollection    pipeline=[{"$match": {"key": "value"}}]

        """
        if not isinstance(pipeline, list):
            raise Exception("Invalid pipeline: must be a list of stages.")

        collection = self._get_collection(collection_name, alias)
        return list(collection.aggregate(pipeline))

    # ----------------------------------------------------------------- #
    # Updating
    # ----------------------------------------------------------------- #

    @keyword
    def update_document(self, collection_name: str, query: dict, update: dict, alias: Optional[str] = None) -> Optional[dict]:
        """
        Update a single document in a collection.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``query``: Query to find the document to update.
        - ``update``: Fields to set on the document.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - The updated document, or None if no document matches.

        Example:
        | ${updated_doc}    Update Document    collection_name=mycollection    query={"key": "value"}    update={"key": "new_value"}

        """
        collection = self._get_collection(collection_name, alias)
        return collection.find_one_and_update(query, {'$set': update}, return_document=ReturnDocument.AFTER)

    @keyword
    def update_document_with_operators(self, collection_name: str, query: dict, update: dict, alias: Optional[str] = None) -> Optional[dict]:
        """
        Update a single document in a collection using raw MongoDB update operators.

        This keyword allows you to use MongoDB update operators like $set, $push, $pull, etc.
        directly without automatic wrapping. Use this when you need operations other than $set.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``query``: Query to find the document to update.
        - ``update``: Raw MongoDB update document with operators (e.g., {"$push": {...}, "$set": {...}}).
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - The updated document, or None if no document matches.

        Example:
        | ${updated_doc}    Update Document With Operators    collection_name=mycollection    query={"key": "value"}    update={"$push": {"items": "new_item"}, "$set": {"modified": "2025-01-01"}}

        """
        collection = self._get_collection(collection_name, alias)
        return collection.find_one_and_update(query, update, return_document=ReturnDocument.AFTER)



    # ----------------------------------------------------------------- #
    # Deleting
    # ----------------------------------------------------------------- #

    @keyword
    def delete_document(self, collection_name: str, alias: Optional[str] = None, **params: Any) -> int:
        """
        Delete a single document from a collection.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``params``: Query parameters to locate the document to delete.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - The count of deleted documents (0 or 1).

        Example:
        | ${deleted_count}    Delete Document    collection_name=mycollection    key=value

        """
        collection = self._get_collection(collection_name, alias)
        return collection.delete_one(params).deleted_count

    @keyword
    def delete_many(self, collection_name: str, alias: Optional[str] = None, **params: Any) -> int:
        """
        Delete multiple documents from a collection.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``params``: Query parameters to find the documents to delete.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - Count of deleted documents.

        Example:
        | ${deleted_count}    Delete Many    collection_name=mycollection    key=value

        """
        collection = self._get_collection(collection_name, alias)
        return collection.delete_many(params).deleted_count

    @keyword
    def delete_documents_with_query(self, collection_name: str, query: dict, alias: Optional[str] = None) -> int:
        """
        Delete multiple documents from a collection using a complex MongoDB query.

        This keyword allows you to use MongoDB query operators like $gte, $lt, $in, $regex, etc.
        directly without limitations. Use this when you need operations beyond simple key=value matching.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``query``: MongoDB query document with operators (e.g., {"date": {"$gte": start, "$lt": end}}).
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - Count of deleted documents.

        Example:
        | ${start_date}    Get Current Date    result_format=datetime
        | ${end_date}      Evaluate    $start_date + timedelta(days=1)    modules=datetime
        | ${query}         Create Dictionary    userId=user123
        | ${date_range}    Create Dictionary    $gte=${start_date}    $lt=${end_date}
        | Set To Dictionary    ${query}    date=${date_range}
        | ${deleted_count}    Delete Documents With Query    collection_name=activity    query=${query}

        """
        collection = self._get_collection(collection_name, alias)
        return collection.delete_many(query).deleted_count

    @keyword
    def delete_all_documents_from_collection(self, collection_name: str, alias: Optional[str] = None) -> int:
        """
        Delete all documents from a collection.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - The count of deleted documents.

        Example:
        | ${deleted_count}    Delete All Documents From Collection    collection_name=mycollection

        """
        collection = self._get_collection(collection_name, alias)
        return collection.delete_many({}).deleted_count




    # ----------------------------------------------------------------- #
    # Assertions
    # ----------------------------------------------------------------- #

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
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Example:
        | Check Query Result    collection_name=mycollection    query={"key": "value"}    assertion_operator= ==    expected_value=42    field=key

        """
        collection = self._get_collection(collection_name, alias)

        def check() -> None:
            results = list(collection.find(query))
            if not results:
                raise AssertionError("Query returned no results.")

            for document in results:
                if field not in document:
                    raise AssertionError(f"Field '{field}' not found in document.")

                verify_assertion(
                    document[field],
                    assertion_operator,
                    expected_value,
                    f"Field '{field}' value mismatch:",
                    assertion_message
                )

        self._retry_until_no_assertion_error(check, retry_timeout, retry_pause)

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
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Example:
        | Check Document Count    collection_name=mycollection    query={"key": "value"}    assertion_operator= ==    expected_count=5

        """
        collection = self._get_collection(collection_name, alias)

        def check() -> None:
            verify_assertion(
                collection.count_documents(query),
                assertion_operator,
                expected_count,
                "Wrong document count:",
                assertion_message
            )

        self._retry_until_no_assertion_error(check, retry_timeout, retry_pause)
