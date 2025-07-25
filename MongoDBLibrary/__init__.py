from robotlibcore import DynamicCore

from .connection_pool import ConnectionManager
from .keywords import MongoDBKeywords


class MongoDBLibrary(DynamicCore):

    """MongoDB Library for Robot Framework.

    This is the keyword documentation for MongoDB Library. For information
    about installation, support, and more, please visit the
    [https://github.com/MarketSquare/robotframework-mongodblibrary|project pages].
    For more information about Robot Framework itself, see [https://robotframework.org|robotframework.org].

    MongoDB Library provides keywords for interacting with MongoDB databases.
    It supports operations such as connecting to a database, inserting,
    updating, deleting, and querying documents.

    = Usage =

    | *** Settings ***
    | Library    MongoDBKeywords    connection_manager=${connection_manager}

    | *** Variables ***
    | ${connection_manager}    Evaluate    .ConnectionManager()

    | *** Test Cases ***
    | Insert Document Example
    |     [Documentation]    Example of inserting a document into a MongoDB collection
    |     Connect To Database    my_database    db_user=my_user    db_password=my_password    db_host=localhost    db_port=27017
    |     ${doc_id}    Insert Document    my_collection    {"name": "example", "value": 42}
    |     Log    Inserted document ID: ${doc_id}

    = AWS Authentication =

    MongoDB Library supports AWS authentication using the MONGODB-AWS mechanism.
    To enable this feature, ensure the following steps are completed:

    1. Install the required `pymongo-auth-aws` package:
       ```
       python -m pip install 'pymongo[aws]'
       ```

    2. Ensure that your AWS credentials are properly set up in your environment.
       The library will automatically use the credentials from the environment variables
       `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and optionally `AWS_SESSION_TOKEN`.

    For more details, refer to the [MongoDB documentation](https://www.mongodb.com/docs/manual/core/security-aws/).

    """
    ROBOT_LIBRARY_SCOPE = 'GLOBAL'

    def __init__(self):
        self.connection_manager = ConnectionManager()
        libraries = [MongoDBKeywords(self.connection_manager)]
        DynamicCore.__init__(self, libraries)
