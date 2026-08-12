from pymongo.database import Database
from robot.api import logger


class ConnectionManager:
    """
    Manages the connection pool for MongoDB databases.
    """
    def __init__(self):
        self.db_connection_pool: dict[str, Database] = {}
        self.default_alias: str = "default"

    def add_to_connection_pool(self, database: Database, alias: str) -> None:
        """
        Add a MongoDB database to the connection pool with an alias.

        :param database: Database instance to store
        :param alias: Alias for the connection
        """
        if alias in self.db_connection_pool:
            logger.warn(f"Connection with alias '{alias}' already exists. Overwriting it.")
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
        database.client.close()
        logger.info(f"Removed connection with alias '{alias}' from the connection pool.")

    def clear_connection_pool(self) -> None:
        """
        Clear all connections in the connection pool.
        """
        for database in self.db_connection_pool.values():
            database.client.close()
        self.db_connection_pool.clear()
        logger.info("Cleared all connections from the connection pool.")

    def list_connection_pool(self) -> list[str]:
        """
        List all aliases in the connection pool.

        :return: List of aliases
        """
        return list(self.db_connection_pool.keys())
