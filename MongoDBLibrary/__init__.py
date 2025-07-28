from robotlibcore import DynamicCore

from .connection_pool import ConnectionManager
from .keywords import MongoDBKeywords


class MongoDBLibrary(DynamicCore):
    """MongoDB Library for Robot Framework.

    MongoDB Library provides keywords for interacting with MongoDB databases.
    It supports operations such as connecting to a database, inserting,
    updating, deleting, and querying documents.

    = Table of Contents =

    - Introduction
    - Usage
    - AWS Authentication
    - Assertions

    == Introduction ==

    MongoDB Library is a Robot Framework library for MongoDB database operations.
    It supports various database operations such as connecting to a database,
    inserting, updating, deleting, and querying documents.

    == Usage ==

    Example:

    | Insert Document Example
    |     [Documentation]    Example of inserting a document into a MongoDB collection
    |     Connect To Database    my_database    db_user=my_user    db_password=my_password    db_host=localhost    db_port=27017
    |     ${doc_id}    Insert Document    my_collection    {"name": "example", "value": 42}
    |     Log    Inserted document ID: ${doc_id}

    == AWS Authentication ==

    MongoDB Library supports AWS authentication using the MONGODB-AWS mechanism.
    To enable this feature, ensure the following steps are completed:

    1. Install the required `pymongo-auth-aws` package:
       | python -m pip install 'pymongo[aws]'

    2. Ensure that your AWS credentials are properly set up in your environment.
       The library will automatically use the credentials from the environment variables
       `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and optionally `AWS_SESSION_TOKEN`.

    For more details, refer to the [https://www.mongodb.com/docs/manual/core/security-aws/|MongoDB documentation].

    == Assertions ==

    MongoDB Library supports meaningful and easy-to-use assertions for validating data.
    Assertions are performed using the `verify_assertion` method from the [https://github.com/MarketSquare/AssertionEngine/|AssertionEngine].

    === Supported Assertions ===

    Currently supported assertion operators are:

    - ``==``: Equal to
    - ``!=``: Not equal to
    - ``>``: Greater than
    - ``<``: Less than
    - ``contains``: Contains

    === Supported Formatters ===

    Formatters can be applied to both the actual and expected values:

    - ``normalize spaces``: Substitutes multiple spaces with a single space.
    - ``strip``: Removes spaces from the beginning and end of the value.
    - ``apply to expected``: Applies rules also to the expected value.
    - ``case insensitive``: Converts value to lowercase.

    === Usage ===

    Assertions can be performed inline within keyword calls. The `verify_assertion` method requires:

    - ``value``: The actual value from the system.
    - ``assertion_operator``: The operator defining how validation is performed.
    - ``assertion_expected``: The expected value.

    Optionally, a custom error message and prefix can be provided.

    Example:

    | Assertion Example
    |     [Documentation]    Example of using assertions in MongoDB Library
    |     ${actual_value}=    Get Document Field    collection_name=mycollection    query={"key": "value"}    field=key
    |     Check Query Result    collection_name=mycollection    query={"key": "value"}    assertion_operator==    expected_value=42    field=key


    """
    ROBOT_LIBRARY_SCOPE = 'GLOBAL'

    def __init__(self):
        """Initializes the MongoDB Library.

        Arguments:
        - None

        * Sets up the connection manager.
        * Initializes the MongoDBKeywords library.

        """
        self.connection_manager = ConnectionManager()
        libraries = [MongoDBKeywords(self.connection_manager)]
        DynamicCore.__init__(self, libraries)
