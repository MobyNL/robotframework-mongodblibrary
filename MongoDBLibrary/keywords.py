import time
from typing import Any, Callable, Optional

from assertionengine import AssertionOperator, verify_assertion
from bson import ObjectId
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

    def __init__(self, connection_manager: ConnectionManager, coerce_object_ids: bool = True):
        """
        Initializes the MongoDBKeywords library.

        Arguments:
        - ``connection_manager``: Manages connections to MongoDB.
        - ``coerce_object_ids``: Whether a string ``_id`` in a query is converted to an
          ObjectId.
        """
        self.connection_manager = connection_manager
        self.coerce_object_ids = coerce_object_ids

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

    @staticmethod
    def _coerce_object_id(value: Any) -> Any:
        """Turn a string that is a valid ObjectId into one, leaving anything else alone."""
        if isinstance(value, str) and ObjectId.is_valid(value):
            return ObjectId(value)
        return value

    def _normalise_query(self, query: Any) -> Any:
        """
        Convert a string ``_id`` in a query into an ObjectId.

        Robot Framework turns every value it stores in a variable into a string when it
        is written back out, so a document id obtained from `Insert Document` arrives
        here as text and would otherwise never match. Disabled by importing the library
        with ``coerce_object_ids=${False}``, after which queries are passed through
        exactly as given.
        """
        if not self.coerce_object_ids:
            return query
        if not isinstance(query, dict) or "_id" not in query:
            return query
        normalised = dict(query)
        value = normalised["_id"]
        if isinstance(value, dict):
            normalised["_id"] = {
                operator: [self._coerce_object_id(item) for item in operand]
                if isinstance(operand, list)
                else self._coerce_object_id(operand)
                for operator, operand in value.items()
            }
        else:
            normalised["_id"] = self._coerce_object_id(value)
        if normalised["_id"] != value:
            logger.debug(f"Converted the query '_id' to an ObjectId: {normalised['_id']!r}")
        return normalised

    @staticmethod
    def _as_dot_dict(value: Any) -> Any:
        """Wrap documents so Robot Framework's ``${doc.field}`` access works."""
        if isinstance(value, list):
            return [DotDict(item) if isinstance(item, dict) else item for item in value]
        return DotDict(value) if isinstance(value, dict) else value

    @staticmethod
    def _as_sort_list(sort: Optional[dict]) -> Optional[list]:
        """Turn ``{"name": 1}`` into pymongo's ``[("name", 1)]``."""
        return list(sort.items()) if sort else None

    def _find(self, collection_name: str, query: Any, alias: Optional[str], projection: Optional[dict],
              sort: Optional[dict], limit: int, skip: int) -> list:
        collection = self._get_collection(collection_name, alias)
        cursor = collection.find(self._normalise_query(query), projection, skip=skip, limit=limit)
        sort_list = self._as_sort_list(sort)
        if sort_list:
            cursor = cursor.sort(sort_list)
        return self._as_dot_dict(list(cursor))

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
    def connect_to_database(self, db_name: str, db_user: Optional[str] = None, db_password: Optional[str] = None, db_host: Optional[str] = None, db_port: Optional[int] = None, alias: Optional[str] = None, srv: bool = False, tls: Optional[bool] = None, auth_source: Optional[str] = None, server_selection_timeout: Optional[str] = None) -> None:
        """
        Connects to MongoDB and adds the database object to the connection pool.

        The connection is verified before the keyword passes, so a failure to reach
        the server or to authenticate is reported here rather than by a later keyword.
        Connecting several aliases to the same server reuses one client.

        Arguments:
        - ``db_name``: Name of the database to connect to.
        - ``db_user``: Username for authentication (optional).
        - ``db_password``: Password for authentication (optional).
        - ``db_host``: Hostname or IP address of the MongoDB server (optional).
        - ``db_port``: Port number of the MongoDB server (optional, defaults to 27017). Ignored when ``srv`` is true.
        - ``alias``: Alias for the connection (optional).
        - ``srv``: Resolve ``db_host`` as a DNS seed list (``mongodb+srv``) instead of a
          single host. Required for hosted clusters such as MongoDB Atlas, whose
          cluster names have no address record of their own. Enables TLS by default.
        - ``tls``: Force TLS on or off (optional). Leave unset to use the default for
          the connection type, which is on for ``srv`` and off otherwise.
        - ``auth_source``: Database holding the user's credentials (optional). Needed
          whenever the user was not created in ``db_name`` itself.
        - ``server_selection_timeout``: How long to wait for a reachable server before
          failing, as a Robot Framework time string (optional, pymongo defaults to 30
          seconds).

        Credentials should come from variables rather than being written literally in a
        suite, because Robot Framework writes the argument as it appears in the source
        into the log.

        Example:
        | Connect To Database    db_name=mydb    db_user=user    db_password=pass    db_host=localhost    db_port=27017
        | Connect To Database    db_name=mydb    db_user=user    db_password=pass    db_host=mycluster.abcde.mongodb.net    srv=${True}
        | Connect To Database    db_name=mydb    db_user=user    db_password=pass    db_host=localhost    auth_source=admin    server_selection_timeout=5 seconds

        """
        options: dict[str, Any] = {}
        host: Optional[str]
        port: Optional[int]
        if srv:
            host = f"mongodb+srv://{db_host}"
            port = None
            if db_port:
                logger.warn("'db_port' is ignored when 'srv' is enabled, because a seed list supplies its own ports.")
        else:
            host = db_host
            port = int(db_port) if db_port else 27017
        if tls is not None:
            options["tls"] = tls
        if auth_source:
            options["authSource"] = auth_source
        if server_selection_timeout:
            options["serverSelectionTimeoutMS"] = int(timestr_to_secs(server_selection_timeout) * 1000)

        cache_key = ("host", host, port, db_user, db_password, tuple(sorted(options.items())))
        self._connect(cache_key, lambda: MongoClient(host=host, port=port, username=db_user, password=db_password, **options), db_name, alias)
        logger.info(f"Connected to MongoDB with alias '{self._resolve_alias(alias)}' at {db_host}")

    @keyword
    def connect_to_database_using_connection_string(self, db_conn_string: str, db_name: str, alias: Optional[str] = None, server_selection_timeout: Optional[str] = None) -> None:
        """
        Connects to MongoDB using a connection string and adds the database object to the connection pool.

        The connection is verified before the keyword passes, so a failure to reach
        the server or to authenticate is reported here rather than by a later keyword.
        Connecting several aliases with the same connection string reuses one client.

        Arguments:
        - ``db_conn_string``: MongoDB connection string. Both ``mongodb://`` and
          ``mongodb+srv://`` are accepted.
        - ``db_name``: Name of the database to connect to.
        - ``alias``: Alias for the connection (optional).
        - ``server_selection_timeout``: How long to wait for a reachable server before
          failing, as a Robot Framework time string (optional, pymongo defaults to 30
          seconds).

        The connection string should come from a variable rather than being written
        literally in a suite, because Robot Framework writes the argument as it appears
        in the source into the log.

        Example:
        | Connect To Database Using Connection String    db_conn_string=mongodb://localhost:27017    db_name=mydb

        """
        options: dict[str, Any] = {}
        if server_selection_timeout:
            options["serverSelectionTimeoutMS"] = int(timestr_to_secs(server_selection_timeout) * 1000)

        cache_key = ("uri", db_conn_string, tuple(sorted(options.items())))
        self._connect(cache_key, lambda: MongoClient(db_conn_string, **options), db_name, alias)
        logger.info(f"Connected to MongoDB with alias '{self._resolve_alias(alias)}' using connection string.")

    def _connect(self, cache_key: Any, create_client: Callable[[], MongoClient], db_name: str, alias: Optional[str]) -> None:
        """Create or reuse a client, verify it, and pool its database under ``alias``."""
        alias = self._resolve_alias(alias)
        client = self.connection_manager.get_or_create_client(cache_key, create_client)
        try:
            client.admin.command("ping")
        except Exception:
            self.connection_manager.discard_client(client)
            raise
        self.connection_manager.add_to_connection_pool(client[db_name], alias)

    @keyword
    def disconnect_from_database(self, alias: Optional[str] = None) -> None:
        """
        Disconnect a specific database connection using its alias.

        The underlying client stays open if another alias still shares it.

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
    def switch_connection(self, alias: str) -> None:
        """
        Make the connection stored under ``alias`` the active one.

        Keywords called afterwards without an explicit ``alias`` use this connection.

        Arguments:
        - ``alias``: Alias of the connection to switch to.

        Example:
        | Switch Connection    alias=myalias

        """
        if alias not in self.connection_manager.db_connection_pool:
            raise ValueError(f"Connection with alias '{alias}' is not connected.")
        self.connection_manager.default_alias = alias

    @keyword
    def switch_database(self, alias: str) -> None:
        """
        *DEPRECATED* Use `Switch Connection` instead, which is named for what it does.

        Switches the active connection, not the database within a connection.

        Arguments:
        - ``alias``: Alias of the connection to switch to.

        """
        self.switch_connection(alias)

    @keyword
    def get_active_alias(self) -> str:
        """
        Return the alias used by keywords called without an explicit ``alias``.

        Returns:
        - The active connection alias.

        Example:
        | ${alias}    Get Active Alias

        """
        return self.connection_manager.default_alias

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
    # Conversion helpers
    # ----------------------------------------------------------------- #

    @keyword
    def convert_to_object_id(self, value: str) -> ObjectId:
        """
        Convert a document id in string form into a BSON ObjectId.

        Query keywords convert a string ``_id`` automatically, so this is only needed
        when building a query document yourself or when nesting an id inside an
        aggregation pipeline.

        Arguments:
        - ``value``: The 24-character hexadecimal id.

        Returns:
        - The value as an ObjectId.

        Example:
        | ${oid}    Convert To Object Id    ${doc_id}

        """
        return ObjectId(value)

    # ----------------------------------------------------------------- #
    # Inserting
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

    @keyword
    def insert_documents(self, collection_name: str, documents: list, alias: Optional[str] = None) -> list:
        """
        Insert several documents into a collection in one round trip.

        Arguments:
        - ``collection_name``: Name of the collection where the documents will be inserted.
        - ``documents``: List of documents to insert.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - The IDs of the inserted documents, in the order given.

        Example:
        | ${ids}    Insert Documents    collection_name=mycollection    documents=[{"key": "a"}, {"key": "b"}]

        """
        collection = self._get_collection(collection_name, alias)
        return collection.insert_many(documents).inserted_ids

    # ----------------------------------------------------------------- #
    # Reading
    # ----------------------------------------------------------------- #

    @keyword
    def find_document(self, collection_name: str, alias: Optional[str] = None, **params: Any) -> Optional[dict]:
        """
        Find a single document in a collection.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

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
        return self._as_dot_dict(collection.find_one(self._normalise_query(params)))

    @keyword
    def find_document_with_query(self, collection_name: str, query: dict, alias: Optional[str] = None, projection: Optional[dict] = None, sort: Optional[dict] = None) -> Optional[dict]:
        """
        Find a single document using a MongoDB query document.

        Use this when the query needs operators such as ``$gte``, ``$in`` or ``$regex``,
        which simple key=value parameters cannot express.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection to search.
        - ``query``: MongoDB query document.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``projection``: Fields to include or exclude, e.g. ``{"name": 1}`` (optional).
        - ``sort``: Fields to sort by before taking the first match, where 1 is
          ascending and -1 descending, e.g. ``{"created": -1}`` (optional).

        Returns:
        - The found document, or None if no document matches the query.

        Example:
        | ${document}    Find Document With Query    collection_name=mycollection    query={"score": {"$gte": 10}}    sort={"score": -1}

        """
        documents = self._find(collection_name, query, alias, projection, sort, limit=1, skip=0)
        return documents[0] if documents else None

    @keyword
    def find_documents(self, collection_name: str, alias: Optional[str] = None, projection: Optional[dict] = None, sort: Optional[dict] = None, limit: int = 0, skip: int = 0, **params: Any) -> list:
        """
        Find every document in a collection matching the given parameters.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection to search.
        - ``params``: Query parameters to locate the documents. Omit them to return the
          whole collection.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``projection``: Fields to include or exclude, e.g. ``{"name": 1}`` (optional).
        - ``sort``: Fields to sort by, where 1 is ascending and -1 descending (optional).
        - ``limit``: Maximum number of documents to return, 0 for no limit (optional).
        - ``skip``: Number of matching documents to skip (optional).

        Returns:
        - A list of documents, empty when nothing matches.

        Example:
        | ${documents}    Find Documents    collection_name=mycollection    key=value    sort={"created": -1}    limit=10

        """
        return self._find(collection_name, params, alias, projection, sort, limit, skip)

    @keyword
    def find_documents_with_query(self, collection_name: str, query: dict, alias: Optional[str] = None, projection: Optional[dict] = None, sort: Optional[dict] = None, limit: int = 0, skip: int = 0) -> list:
        """
        Find every document matching a MongoDB query document.

        Use this when the query needs operators such as ``$gte``, ``$in`` or ``$regex``,
        which simple key=value parameters cannot express.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection to search.
        - ``query``: MongoDB query document.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``projection``: Fields to include or exclude, e.g. ``{"name": 1}`` (optional).
        - ``sort``: Fields to sort by, where 1 is ascending and -1 descending (optional).
        - ``limit``: Maximum number of documents to return, 0 for no limit (optional).
        - ``skip``: Number of matching documents to skip (optional).

        Returns:
        - A list of documents, empty when nothing matches.

        Example:
        | ${documents}    Find Documents With Query    collection_name=mycollection    query={"score": {"$gte": 10}}    limit=5

        """
        return self._find(collection_name, query, alias, projection, sort, limit, skip)

    @keyword
    def count_documents(self, collection_name: str, alias: Optional[str] = None, **params: Any) -> int:
        """
        Count the number of documents in a collection matching a query.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

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
        return collection.count_documents(self._normalise_query(params))

    @keyword
    def count_documents_with_query(self, collection_name: str, query: dict, alias: Optional[str] = None) -> int:
        """
        Count the documents matching a MongoDB query document.

        Use this when the query needs operators such as ``$gte``, ``$in`` or ``$regex``,
        which simple key=value parameters cannot express.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``query``: MongoDB query document.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - The count of matching documents.

        Example:
        | ${count}    Count Documents With Query    collection_name=mycollection    query={"score": {"$gte": 10}}

        """
        collection = self._get_collection(collection_name, alias)
        return collection.count_documents(self._normalise_query(query))

    @keyword
    def execute_query(self, collection_name: str, pipeline: list, alias: Optional[str] = None) -> list:
        """
        Execute an aggregation pipeline query on a collection.

        A string ``_id`` inside a pipeline is not converted automatically; use
        `Convert To Object Id` when a stage needs to match one.

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
            raise TypeError("Invalid pipeline: must be a list of stages.")

        collection = self._get_collection(collection_name, alias)
        return self._as_dot_dict(list(collection.aggregate(pipeline)))

    # ----------------------------------------------------------------- #
    # Updating
    # ----------------------------------------------------------------- #

    @keyword
    def update_document(self, collection_name: str, query: dict, update: dict, alias: Optional[str] = None) -> Optional[dict]:
        """
        Update a single document in a collection.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

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
        return self._as_dot_dict(
            collection.find_one_and_update(self._normalise_query(query), {'$set': update}, return_document=ReturnDocument.AFTER)
        )

    @keyword
    def update_document_with_operators(self, collection_name: str, query: dict, update: dict, alias: Optional[str] = None) -> Optional[dict]:
        """
        Update a single document in a collection using raw MongoDB update operators.

        This keyword allows you to use MongoDB update operators like $set, $push, $pull, etc.
        directly without automatic wrapping. Use this when you need operations other than $set.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

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
        return self._as_dot_dict(
            collection.find_one_and_update(self._normalise_query(query), update, return_document=ReturnDocument.AFTER)
        )

    @keyword
    def update_documents(self, collection_name: str, query: dict, update: dict, alias: Optional[str] = None) -> int:
        """
        Update every document in a collection matching a query.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``query``: Query to find the documents to update.
        - ``update``: Fields to set on each matching document.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - The count of documents that were changed.

        Example:
        | ${updated_count}    Update Documents    collection_name=mycollection    query={"key": "value"}    update={"checked": ${True}}

        """
        collection = self._get_collection(collection_name, alias)
        return collection.update_many(self._normalise_query(query), {'$set': update}).modified_count

    @keyword
    def update_documents_with_operators(self, collection_name: str, query: dict, update: dict, alias: Optional[str] = None) -> int:
        """
        Update every matching document using raw MongoDB update operators.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``query``: Query to find the documents to update.
        - ``update``: Raw MongoDB update document with operators.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - The count of documents that were changed.

        Example:
        | ${updated_count}    Update Documents With Operators    collection_name=mycollection    query={"key": "value"}    update={"$inc": {"attempts": 1}}

        """
        collection = self._get_collection(collection_name, alias)
        return collection.update_many(self._normalise_query(query), update).modified_count

    # ----------------------------------------------------------------- #
    # Deleting
    # ----------------------------------------------------------------- #

    @keyword
    def delete_document(self, collection_name: str, alias: Optional[str] = None, **params: Any) -> int:
        """
        Delete a single document from a collection.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

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
        return collection.delete_one(self._normalise_query(params)).deleted_count

    @keyword
    def delete_many(self, collection_name: str, alias: Optional[str] = None, **params: Any) -> int:
        """
        Delete multiple documents from a collection.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

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
        return collection.delete_many(self._normalise_query(params)).deleted_count

    @keyword
    def delete_documents_with_query(self, collection_name: str, query: dict, alias: Optional[str] = None) -> int:
        """
        Delete multiple documents from a collection using a complex MongoDB query.

        This keyword allows you to use MongoDB query operators like $gte, $lt, $in, $regex, etc.
        directly without limitations. Use this when you need operations beyond simple key=value matching.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

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
        return collection.delete_many(self._normalise_query(query)).deleted_count

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
    # Indexes
    # ----------------------------------------------------------------- #

    @keyword
    def create_index(self, collection_name: str, keys: dict, alias: Optional[str] = None, unique: bool = False, index_name: Optional[str] = None) -> str:
        """
        Create an index on a collection.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``keys``: Fields to index, where 1 is ascending and -1 descending,
          e.g. ``{"email": 1}``.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``unique``: Whether the index rejects duplicate values (optional).
        - ``index_name``: Name for the index (optional, MongoDB derives one otherwise).

        Returns:
        - The name of the created index.

        Example:
        | ${name}    Create Index    collection_name=mycollection    keys={"email": 1}    unique=${True}

        """
        collection = self._get_collection(collection_name, alias)
        options: dict[str, Any] = {"unique": unique}
        if index_name:
            options["name"] = index_name
        return collection.create_index(list(keys.items()), **options)

    @keyword
    def list_indexes(self, collection_name: str, alias: Optional[str] = None) -> list:
        """
        List the indexes defined on a collection.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - A list of index definitions. Every collection has at least the ``_id_`` index.

        Example:
        | ${indexes}    List Indexes    collection_name=mycollection

        """
        collection = self._get_collection(collection_name, alias)
        return self._as_dot_dict(list(collection.list_indexes()))

    @keyword
    def drop_index(self, collection_name: str, index_name: str, alias: Optional[str] = None) -> None:
        """
        Drop an index from a collection.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``index_name``: Name of the index to drop, as reported by `List Indexes`.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Example:
        | Drop Index    collection_name=mycollection    index_name=email_1

        """
        collection = self._get_collection(collection_name, alias)
        collection.drop_index(index_name)

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

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

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
        normalised = self._normalise_query(query)

        def check() -> None:
            results = list(collection.find(normalised))
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

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

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
        normalised = self._normalise_query(query)

        def check() -> None:
            verify_assertion(
                collection.count_documents(normalised),
                assertion_operator,
                expected_count,
                "Wrong document count:",
                assertion_message
            )

        self._retry_until_no_assertion_error(check, retry_timeout, retry_pause)
