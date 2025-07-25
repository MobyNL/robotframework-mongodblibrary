from typing import Optional

from pymongo import MongoClient
from robot.api import logger


class ConnectionManager:
    """
    Manages the connection pool for MongoDB clients.
    """
    def __init__(self):
        self.db_connection_pool: dict[str, MongoClient] = {}
        self.default_alias: str = "default"
        self.current_alias: str | None = None

    def get_current_connection(self) -> MongoClient:
        """
        Get the current MongoDB client connection by alias.

        :param alias: Alias of the connection to retrieve, defaults to None
        :return: MongoClient instance
        """
        if self.current_alias is None:
            logger.error("No current connection alias set. Please connect to a database first.")
            raise ValueError("No current connection alias set.")
        try:
            return self.db_connection_pool[self.current_alias]
        except KeyError:
            logger.error(f"Connection with alias '{self.current_alias}' not found in the connection pool.")
            raise ValueError(f"Connection with alias '{self.current_alias}' not found.")

    def add_to_connection_pool(self, client: MongoClient, alias: Optional[str] = None) -> None:
        """
        Add a MongoDB client to the connection pool with an alias.

        :param client: MongoClient instance
        :param alias: Alias for the connection
        """
        if alias is None:
            if self.default_alias in self.db_connection_pool:
                logger.warn(f"Connection with alias '{self.default_alias}' already exists. Overwriting it.")
            self.db_connection_pool[self.default_alias] = client
        elif alias in self.db_connection_pool:
            logger.warn(f"Connection with alias '{alias}' already exists. Overwriting it.")
            self.db_connection_pool[alias] = client
        else:
            self.db_connection_pool[alias] = client
        logger.info(f"Added connection with alias '{alias}' to the connection pool.")

    def remove_from_connection_pool(self, alias: str) -> None:
        """
        Remove a MongoDB client from the connection pool using its alias.

        :param alias: Alias of the connection to remove
        """
        try:
            client = self.db_connection_pool.pop(alias)
            logger.debug(f"Attempting to close client for alias '{alias}'")
            client.close()
            logger.info(f"Removed connection with alias '{alias}' from the connection pool.")
        except KeyError:
            logger.error(f"Connection with alias '{alias}' not found in the connection pool.")

    def clear_connection_pool(self) -> None:
        """
        Clear all connections in the connection pool.
        """
        for client in self.db_connection_pool.values():
            client.close()
        self.db_connection_pool.clear()
        logger.info("Cleared all connections from the connection pool.")

    def list_connection_pool(self) -> list[str]:
        """
        List all aliases in the connection pool.

        :return: List of aliases
        """
        return list(self.db_connection_pool.keys())
