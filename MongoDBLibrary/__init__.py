from importlib.metadata import PackageNotFoundError, version

from robotlibcore import DynamicCore

from .connection_pool import ConnectionManager
from .keywords import MongoDBKeywords

try:
    __version__ = version("robotframework-mongodb")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "unknown"


class MongoDBLibrary(DynamicCore):
    """MongoDB Library for Robot Framework.

    MongoDB Library provides keywords for interacting with MongoDB databases.
    It supports operations such as connecting to a database, inserting,
    updating, deleting, and querying documents.

    = Table of Contents =

    - Introduction
    - Usage
    - Object Ids
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

    == Object Ids ==

    *This library rewrites part of your query. Read this section to know when.*

    MongoDB gives each document an ``_id``, by default a 12-byte BSON ``ObjectId``
    rather than a string. The two are different values and never match each other:

    | ObjectId("6a7ccdea6abf6a4ebbc3514f")    # what MongoDB stores
    |          "6a7ccdea6abf6a4ebbc3514f"     # a string that looks the same

    Robot Framework stores variables as text, so a document id that has been through a
    variable, a file, a CSV or an API response arrives as a string. Querying with it
    matches nothing, and MongoDB reports no error: `Find Document` simply returns
    ``None`` and `Count Documents` simply returns ``0``. The test then fails somewhere
    later, or passes while checking nothing.

    === What is rewritten ===

    Before a query is sent, if its ``_id`` is a string that is a *valid* ObjectId — 24
    hexadecimal characters — it is converted:

    | _id="6a7ccdea6abf6a4ebbc3514f"    ->    _id=ObjectId("6a7ccdea6abf6a4ebbc3514f")

    Values inside ``$in`` and comparison operators are converted the same way, so
    ``query={"_id": {"$in": ["6a7c...", "6a7d..."]}}`` works too.

    Every keyword that takes a query or free query parameters does this: the `Find`,
    `Count`, `Update`, `Delete` and `Check` keywords.

    === What is never rewritten ===

    - Any ``_id`` that is not a valid ObjectId. ``user-42`` and ``order_991`` are passed
      through untouched, so a collection keyed by ordinary strings keeps working.
    - Any field other than ``_id``.
    - The documents you insert or the values you set in an update. Only queries.
    - Aggregation pipelines given to `Execute Query`, because a stage can nest to any
      depth and guessing inside one would be reckless. Use `Convert To Object Id` there.

    === When to turn it off ===

    There is exactly one case where this behaviour is wrong: a collection whose ``_id``
    values are genuinely *strings* that happen to be 24 hexadecimal characters, such as
    a truncated hash or commit SHA. The conversion would then look for an ObjectId that
    does not exist, and you are back to a silent no-match.

    If that describes your data, turn it off at import and convert explicitly instead:

    | Library    MongoDBLibrary    coerce_object_ids=${False}

    | ${oid}    Convert To Object Id    ${doc_id}
    | Find Document    collection_name=orders    _id=${oid}

    With the option off, nothing about your queries is altered and passing a string
    ``_id`` against an ObjectId-keyed collection will silently match nothing again.

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
    # Read from the installed package so the version lives in pyproject.toml only.
    ROBOT_LIBRARY_VERSION = __version__

    def __init__(self, coerce_object_ids: bool = True) -> None:
        """Initializes the MongoDB Library.

        Arguments:
        - ``coerce_object_ids``: Whether a string ``_id`` in a query is converted to a
          BSON ObjectId, on by default. See `Object Ids` for exactly what this rewrites,
          why it is on, and the one case in which you want it off.

        | Library    MongoDBLibrary
        | Library    MongoDBLibrary    coerce_object_ids=${False}

        """
        self.connection_manager = ConnectionManager()
        libraries = [MongoDBKeywords(self.connection_manager, coerce_object_ids=coerce_object_ids)]
        DynamicCore.__init__(self, libraries)
