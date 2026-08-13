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
    - Resetting Between Tests
    - Writing A Fixture That Can Run Twice
    - Hosted Clusters
    - Credentials
    - AWS Authentication
    - Assertions
    - Beyond These Keywords

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

    == Resetting Between Tests ==

    There are two ways to clear a collection and they are not interchangeable.

    `Delete All Documents From Collection` removes the documents. Everything *defined*
    on the collection stays: its indexes, and any options it was created with. So a
    unique index created by one test still rejects the next test's fixtures, long after
    the documents that justified it are gone.

    `Drop Collection` removes the collection itself, indexes and options included. That
    is what actually returns a collection to its original state. Dropping one that does
    not exist succeeds and does nothing, so it is safe in a teardown that runs after a
    setup failed:

    | [Teardown]    Drop Collection    collection_name=orders

    Use `Delete All Documents From Collection` when the indexes are part of what the
    suite is testing against, and `Drop Collection` otherwise.

    For a suite that wants a database to itself, `Drop Database` removes the whole thing.
    It always names its target, so the connected database cannot be dropped by leaving an
    argument out — but it is still deletion, and pointing it at a shared database
    destroys whatever else was using it.

    == Writing A Fixture That Can Run Twice ==

    A setup step that inserts a document fails the second time it runs, which makes a
    suite depend on the state it started from. The ``upsert`` argument writes the
    document if it is not there and updates it if it is:

    | Update Document    collection_name=users    query={"email": "a@example.test"}    update={"active": ${True}}    upsert=${True}

    `Update Document` merges: fields already on the document and not mentioned are left
    alone, so it can never remove one. When the fixture has to be exactly a given
    document, `Replace Document` swaps the whole thing instead:

    | Replace Document    collection_name=users    query={"email": "a@example.test"}    replacement={"email": "a@example.test", "active": ${True}}    upsert=${True}

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
    and ``output.xml``.

    === Secrets ===

    On Robot Framework 7.4 and later, ``db_password`` and ``db_conn_string`` accept a
    ``Secret``. A secret variable is declared with a type and takes its value from the
    environment:

    | *** Variables ***
    | ${DB_PASSWORD: Secret}    %{MONGO_PASSWORD}
    |
    | *** Test Cases ***
    | Connect With A Secret
    |     Connect To Database    db_name=mydb    db_user=${DB_USER}    db_password=${DB_PASSWORD}    db_host=localhost

    The value never appears in the log: Robot Framework writes ``<secret>`` wherever the
    variable is resolved. A connection string embeds its password, so giving that as a
    ``Secret`` hides the whole string.

    Note that a secret can only come from the environment. Robot Framework refuses to
    build one from a literal, which is what makes this stronger than a plain variable —
    there is no way to write the value into the suite by accident.

    A ``Secret`` is not encryption. The value is plain text in memory, it is sent to
    MongoDB as typed, and a keyword that returns or logs it discloses it. What it
    prevents is the accident of Robot Framework itself recording the argument.

    === Without secrets ===

    On Robot Framework 7.3, and anywhere a ``Secret`` is inconvenient, pass credentials
    as ordinary variables supplied from a resource file that is not committed, from the
    command line, or from the environment. The argument is still written to the log as
    the variable name rather than its value, as long as the value is not written
    literally in the suite:

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

    === The assertion keywords ===

    - `Check Query Result` — a field of every matching document against a value.
    - `Check Document Count` — how many documents match.
    - `Check Distinct Values` — the set of values a field takes across the collection.
      This is how to assert that *nothing* is in a given state, which counting cannot
      express as directly.
    - `Document Should Exist` and `Document Should Not Exist` — the plain question,
      taking the same free query parameters as `Find Document`.
    - `Check Collection Exists` and `Check Index Exists` — for asserting that a migration
      or an application's start-up created what it was supposed to.

    === Retrying ===

    Every assertion keyword retries a failing assertion until ``retry_timeout`` elapses,
    pausing ``retry_pause`` between attempts. The default ``retry_timeout`` of zero means
    the assertion is checked once. A ``retry_pause`` of zero polls as fast as the
    database answers, which is rarely what you want against a shared server.

    Give ``retry_timeout`` a value whenever the thing being asserted is written by
    something the test has just triggered and does not otherwise wait for:

    | Document Should Exist    collection_name=orders    order_id=A-1    retry_timeout=10 seconds

    This is the reason to prefer these keywords over a hand-written
    ``Wait Until Keyword Succeeds`` around `Find Document`: the wait is the part that is
    easy to get wrong.

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

    == Beyond These Keywords ==

    The keywords cover what a test suite normally needs, which is a small part of what
    MongoDB can do. `Run Database Command` reaches the rest — server statistics, storage
    sizes, query plans and the administrative commands are all database commands, and
    there are far too many to give each a keyword:

    | ${stats}    Run Database Command    command={"collStats": "orders"}
    | ${plan}     Run Database Command    command={"explain": {"find": "orders", "filter": {"status": "new"}}}
    | ${info}     Run Database Command    command={"listCollections": 1}

    A command written as a document is read as one; anything else is sent as a bare
    command name, so ``command=ping`` works too.

    Deliberately not wrapped, because none of them fit a synchronous keyword taken one at
    a time: transactions and sessions, change streams, GridFS, and client-side field
    level encryption. Use pymongo directly if a suite needs those.

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
