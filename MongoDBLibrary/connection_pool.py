from typing import Optional

from pymongo.database import Database
from robot.api import logger


class ConnectionManager:
    """
    Manages the connection pool for MongoDB databases.
    """
    def __init__(self):
        self.db_connection_pool: dict[str, Database] = {}
        self.default_alias: str = "default"
        self.current_alias: str | None = None

    def get_current_connection(self) -> Database:
        """
        Get the current MongoDB database connection by alias.

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

    def add_to_connection_pool(self, database: Database,  db_name: str, alias: Optional[str] = None) -> None:
        """
        Add a MongoDB database to the connection pool with an alias and select a database.

        :param database: MongoClient instance
        :param alias: Alias for the connection
        :param db_name: Name of the database to select
        """
        if alias is None:
            if self.default_alias in self.db_connection_pool:
                logger.warn(f"Connection with alias '{self.default_alias}' already exists. Overwriting it.")
            self.db_connection_pool[self.default_alias] = database
        elif alias in self.db_connection_pool:
            logger.warn(f"Connection with alias '{alias}' already exists. Overwriting it.")
            self.db_connection_pool[alias] = database
        else:
            self.db_connection_pool[alias] = database

        logger.info(f"Added connection with alias '{alias}' to the connection pool.")

    def remove_from_connection_pool(self, alias: str) -> None:
        """
        Remove a MongoDB database from the connection pool using its alias.

        :param alias: Alias of the connection to remove
        """
        try:
            database = self.db_connection_pool.pop(alias)
            logger.debug(f"Attempting to close database for alias '{alias}'")
            database.client.close()
            logger.info(f"Removed connection with alias '{alias}' from the connection pool.")
        except KeyError:
            raise KeyError(f"Alias '{alias}' not found in the connection pool.")

    def clear_connection_pool(self) -> None:
        """
        Clear all connections in the connection pool.
        """
        for database in self.db_connection_pool.values():
            database.close()
        self.db_connection_pool.clear()
        logger.info("Cleared all connections from the connection pool.")

    def list_connection_pool(self) -> list[str]:
        """
        List all aliases in the connection pool.

        :return: List of aliases
        """
        return list(self.db_connection_pool.keys())
