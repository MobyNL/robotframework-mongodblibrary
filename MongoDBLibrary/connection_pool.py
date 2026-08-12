from typing import Any, Callable

from pymongo import MongoClient
from pymongo.database import Database
from robot.api import logger


class ConnectionManager:
    """
    Manages the connection pool for MongoDB databases.

    Aliases map to databases, and several aliases may share one underlying client.
    A client is only closed once no pooled database still uses it.
    """
    def __init__(self) -> None:
        self.db_connection_pool: dict[str, Database] = {}
        self.default_alias: str = "default"
        self.client_cache: dict[Any, MongoClient] = {}

    def get_or_create_client(self, cache_key: Any, create_client: Callable[[], MongoClient]) -> MongoClient:
        """
        Return the client for ``cache_key``, creating it with ``create_client`` if needed.

        Reusing a client means several aliases against the same server share one
        connection pool instead of opening one each.

        :param cache_key: Value identifying the connection parameters
        :param create_client: Callable building a new client when none is cached
        :return: MongoClient instance
        """
        client = self.client_cache.get(cache_key)
        if client is not None:
            logger.debug(f"Reusing the existing client for {cache_key!r}.")
            return client
        client = create_client()
        self.client_cache[cache_key] = client
        return client

    def discard_client(self, client: MongoClient) -> None:
        """
        Close a client and drop it from the cache, whether or not it was ever pooled.

        :param client: MongoClient instance to close
        """
        self._forget_client(client)
        client.close()

    def add_to_connection_pool(self, database: Database, alias: str) -> None:
        """
        Add a MongoDB database to the connection pool with an alias.

        :param database: Database instance to store
        :param alias: Alias for the connection
        """
        if alias in self.db_connection_pool:
            logger.warn(f"Connection with alias '{alias}' already exists. Overwriting it.")
            self._close_if_unused(self.db_connection_pool.pop(alias))
        self.db_connection_pool[alias] = database
        logger.info(f"Added connection with alias '{alias}' to the connection pool.")

    def remove_from_connection_pool(self, alias: str) -> None:
        """
        Remove a MongoDB database from the connection pool using its alias.

        :param alias: Alias of the connection to remove
        """
        try:
            database = self.db_connection_pool.pop(alias)
        except KeyError:
            raise KeyError(f"Alias '{alias}' not found in the connection pool.")
        logger.debug(f"Attempting to close database for alias '{alias}'")
        self._close_if_unused(database)
        logger.info(f"Removed connection with alias '{alias}' from the connection pool.")

    def clear_connection_pool(self) -> None:
        """
        Clear all connections in the connection pool.
        """
        clients = {id(database.client): database.client for database in self.db_connection_pool.values()}
        self.db_connection_pool.clear()
        for client in clients.values():
            self.discard_client(client)
        logger.info("Cleared all connections from the connection pool.")

    def list_connection_pool(self) -> list[str]:
        """
        List all aliases in the connection pool.

        :return: List of aliases
        """
        return list(self.db_connection_pool.keys())

    def _close_if_unused(self, database: Database) -> None:
        """Close the database's client unless another pooled alias still shares it."""
        client = database.client
        if any(other.client is client for other in self.db_connection_pool.values()):
            logger.debug("Client left open because another alias still uses it.")
            return
        self.discard_client(client)

    def _forget_client(self, client: MongoClient) -> None:
        for key, cached in list(self.client_cache.items()):
            if cached is client:
                del self.client_cache[key]
