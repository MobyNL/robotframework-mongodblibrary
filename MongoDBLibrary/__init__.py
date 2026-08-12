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
    - Hosted Clusters
    - Credentials
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
    |     Connect To Database    db_name=my_database    db_user=${DB_USER}    db_password=${DB_PASSWORD}    db_host=localhost    db_port=27017
    |     ${doc_id}    Insert Document    collection_name=my_collection    document={"name": "example", "value": 42}
    |     Log    Inserted document ID: ${doc_id}

    Connections are held in a pool and identified by an alias. Keywords called without
    an ``alias`` use the active connection, which is the one most recently connected
    under the default alias or selected with `Switch Database`.

    == Hosted Clusters ==

    A hosted cluster such as MongoDB Atlas publishes a DNS seed list rather than a
    single host, and requires TLS. Use `Connect To Database Using Connection String`
    with the provider's ``mongodb+srv://`` URI, or enable ``srv`` on
    `Connect To Database`:

    | Connect To Database    db_name=mydb    db_user=${DB_USER}    db_password=${DB_PASSWORD}    db_host=mycluster.abcde.mongodb.net    srv=${True}

    ``db_port`` is ignored when ``srv`` is enabled. ``tls`` forces TLS on or off; left
    unset it follows the connection type, which means on for ``srv``.

    == Credentials ==

    Robot Framework writes each keyword argument into the log as it appears in the
    suite source, so a password written literally in a suite ends up in ``log.html``
    and ``output.xml``. Pass credentials as variables, supplied from a resource file
    that is not committed, from the command line, or from the environment:

    | Connect To Database    db_name=mydb    db_user=${DB_USER}    db_password=${DB_PASSWORD}    db_host=localhost

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

    The operators provided by the AssertionEngine are accepted, including:

    - ``==``: Equal to
    - ``!=``: Not equal to
    - ``>``: Greater than
    - ``<``: Less than
    - ``contains``: Contains

    === Retrying ===

    `Check Query Result` and `Check Document Count` retry a failing assertion until
    ``retry_timeout`` elapses, pausing ``retry_pause`` between attempts. The default
    ``retry_timeout`` of zero means the assertion is checked once. A ``retry_pause`` of
    zero polls as fast as the database answers, which is rarely what you want against a
    shared server.

    === Usage ===

    An assertion is made by an assertion keyword, which takes:

    - ``query``: The query selecting the documents to check.
    - ``assertion_operator``: The operator defining how validation is performed.
    - the expected value, plus ``field`` for `Check Query Result`.

    Optionally, a custom error message can be provided as ``assertion_message``.

    Example:

    | Assertion Example
    |     [Documentation]    Example of using assertions in MongoDB Library
    |     Check Query Result    collection_name=mycollection    query={"key": "value"}    assertion_operator= ==    expected_value=${42}    field=count
    |     Check Document Count    collection_name=mycollection    query={"key": "value"}    assertion_operator= ==    expected_count=${1}

    """
    ROBOT_LIBRARY_SCOPE = 'GLOBAL'

    def __init__(self) -> None:
        """Initializes the MongoDB Library.

        Arguments:
        - None

        * Sets up the connection manager.
        * Initializes the MongoDBKeywords library.

        """
        self.connection_manager = ConnectionManager()
        libraries = [MongoDBKeywords(self.connection_manager)]
        DynamicCore.__init__(self, libraries)
