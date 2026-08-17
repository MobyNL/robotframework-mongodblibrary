from importlib.metadata import PackageNotFoundError, version
from typing import Optional

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
    - Documents From Files
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

    Robot Framework 5.0 and later are supported, on Python 3.10 and later. The only
    keyword behaviour that differs by version is the ``Secret`` credential described
    under `Credentials`, which needs Robot Framework 7.4. On 5.0 through 6.0, install
    ``robotframework-assertion-engine`` 2.x — its 3.x line requires Robot Framework
    6.1.1, and the assertion keywords behave the same on both.

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

    == Documents From Files ==

    A fixture document written into a suite is fine until a second test needs it. Then it
    is copied, and the two copies drift. `Load Document` reads one from a JSON file
    instead, and `Insert Document From File` reads it and inserts it in one step:

    | Library    MongoDBLibrary    document_path=${CURDIR}/documents

    | ${document}    Load Document    order.json
    | ${doc_id}      Insert Document From File    collection_name=orders    path=order.json

    ``document_path`` only removes the repetition of naming the directory in every call. A
    path given to the keyword is used as written whether it is set or not, so
    ``Load Document    ${CURDIR}/documents/order.json`` works without it.

    === Extended JSON ===

    The file is read as MongoDB Extended JSON, which is how MongoDB itself writes types
    that JSON has no syntax for. So a document id in a file is a real ``ObjectId`` and a
    timestamp is a real ``datetime``:

    | {
    |     "_id": {"$oid": "6a7ccdea6abf6a4ebbc3514f"},
    |     "placedAt": {"$date": "2026-03-01T09:30:00Z"},
    |     "quantity": {"$numberInt": "3"},
    |     "total": {"$numberDouble": "42.50"},
    |     "status": "new",
    |     "lines": [{"sku": "A-1", "quantity": 2}]
    | }

    This matters for exactly the reason `Object Ids` describes: a string that looks like an
    id does not match one, and a date written as text is stored as text and does not
    compare as a date. Plain JSON values are left as the types they already are, so only
    the fields that need a BSON type are written this way.

    MongoDB's update operators start with ``$`` as well, and are not affected — they are
    passed through as they are, nested values included. A file can therefore hold an
    update rather than a document:

    | {"$set": {"status": "shipped", "shippedAt": {"$date": "2026-03-02T00:00:00Z"}}}

    | ${update}    Load Document    ship.json
    | Update Documents With Operators    collection_name=orders    query={"status": "new"}    update=${update}

    === Suite variables ===

    ``${...}`` in the file is replaced from the variables the calling suite can see, so a
    value the whole suite shares is written in one place:

    | {"email": "${EMAIL}", "signedUpAt": {"$date": "${SIGNED_UP_AT}"}}

    A variable that resolves to nothing fails the keyword, naming the file and the
    variable. That is the point of substituting here rather than in the suite: a document
    that kept the literal text ``${EMAIL}`` inserts perfectly well, and the test then fails
    somewhere later against data that looks almost right.

    === Filling a template ===

    A value that differs on *every* call belongs in the call, not in a suite variable. A
    file can declare a hole for one, written ``{name}`` and filled from the keyword's named
    arguments:

    | {
    |     "unique_id": "{unique_id}",
    |     "customerId": "{customerId}",
    |     "placedAt": "{placed_at}",
    |     "quantity": "{quantity}",
    |     "reference": "REF-{unique_id}",
    |     "status": "new"
    | }

    | ${document}    Load Document    order.json    unique_id=order-1    customerId=${oid}
    | ...            placed_at=${now}    quantity=3

    The template stays valid JSON, so an editor, ``jq`` and a formatter still read it. A
    dictionary can be expanded into the arguments with ``&{placeholders}``, and an empty one
    fills nothing.

    Two different holes, then, and the syntax says which is which: ``${name}`` comes from
    the suite, ``{name}`` from the call.

    As for what a filled value becomes: a string that is *exactly* one placeholder is
    replaced whole, quotes included, by the
    value's own Extended JSON form. That is what lets a valid-JSON template carry something
    JSON cannot write, and it means no ``$oid`` or ``$date`` wrapper is needed for a value
    that already is one:

    | "customerId": "{customerId}"    with an ObjectId    ->    a real ObjectId
    | "placedAt": "{placed_at}"       with a datetime     ->    a real datetime
    | "quantity": "{quantity}"        with 3              ->    a real int

    A value written literally is read the way the file's own values are, so ``quantity=3``
    is a number and ``status=shipped`` is text. A placeholder inside a longer string, as in
    ``"REF-{unique_id}"``, is interpolated as text instead. Where a document genuinely
    holds braces in a string, ``{{`` and ``}}`` are literal ones, as in Python's
    ``str.format``; JSON's own braces are never touched.

    A placeholder the file declares and no argument fills is an error, naming the file and
    the holes, for the same reason an unresolved ``${...}`` is: the literal text
    ``{unique_id}`` is a perfectly insertable string.

    === Overriding fields ===

    A field the file already fills can be changed without the file declaring a hole for it,
    which is what a value that varies only *occasionally* wants — the file's own value stays
    as the default for every test that does not mention it. Any field can be overridden by
    its path, and a list position is written as a number:

    | ${document}    Load Document    order.json    status=shipped    lines.0.quantity=3
    | ${document}    Load Document    order.json    customer._id=${customer_id}

    This is the part a suite cannot do for itself. Robot Framework's ``&{dict}`` expansion
    merges one level deep, so overriding a nested field means rebuilding every level above
    it by hand.

    A value written literally is read the way the file's own values are: ``0.8`` is a
    number, ``${True}`` and ``true`` are booleans, ``{"$oid": "..."}`` is an ObjectId, and
    a word such as ``shipped`` is the text it looks like. A value given as a variable is
    used as it is.

    Every step of a path has to exist in the document already. A path that does not fails
    with what the document held at that point, because a path that misses is a typo far
    more often than it is a field meant to be added — and a silent insert would leave the
    document with both the misspelled field and the original one.

    === Which one an argument is ===

    Placeholders and overrides are given the same way, and the file decides which an
    argument is: a name the file declares as a placeholder fills it, and anything else is a
    path into the document.

    | ${document}    Load Document    order.json    unique_id=order-1    status=shipped    lines.0.quantity=3
    | #                                            a hole the file       a field it        a nested field
    | #                                            declares             already fills

    A dotted name can only ever have been a path. A bare one that is neither a placeholder
    nor a field fails naming both, because which was meant decides whether the fix belongs
    in the file or in the call.

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

    On Robot Framework 7.3 and older, where the type does not exist, and anywhere a
    ``Secret`` is inconvenient, pass credentials
    as ordinary variables supplied from a resource file that is not committed, from the
    command line, or from the environment. The argument is still written to the log as
    the variable name rather than its value, as long as the value is not written
    literally in the suite:

    | Connect To Database    db_name=mydb    db_user=${DB_USER}    db_password=${DB_PASSWORD}    db_host=localhost

    == AWS IAM Authentication ==

    AWS IAM authentication uses the ``MONGODB-AWS`` mechanism, which needs two things
    set together — the mechanism itself and an auth source of ``$external``:

    | Connect To Database    db_name=mydb    db_host=mycluster.abcde.mongodb.net    srv=${True}    auth_mechanism=MONGODB-AWS    auth_source=$external

    With `Connect To Database Using Connection String`, put both in the URI instead:
    ``...?authMechanism=MONGODB-AWS&authSource=$external``.

    Install the mechanism's dependency with the ``aws`` extra:

    | python -m pip install 'robotframework-mongodb[aws]'

    Credentials are resolved by ``pymongo-auth-aws``, not by this library, which only
    passes the mechanism through. An EC2, ECS, EKS or Lambda role is picked up with no
    credentials given at all; otherwise ``AWS_ACCESS_KEY_ID``, ``AWS_SECRET_ACCESS_KEY``
    and optionally ``AWS_SESSION_TOKEN`` are read from the environment. For an IAM user
    you may also pass the access key as ``db_user`` and the secret key as ``db_password``.

    See [https://pymongo.readthedocs.io/en/stable/examples/authentication.html|pymongo's
    authentication examples], and the ``Using With AWS`` section of the README for Amazon
    DocumentDB, whose TLS and ``retryWrites`` requirements are separate from IAM.

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

    def __init__(self, coerce_object_ids: bool = True, document_path: Optional[str] = None) -> None:
        """Initializes the MongoDB Library.

        Arguments:
        - ``coerce_object_ids``: Whether a string ``_id`` in a query is converted to a
          BSON ObjectId, on by default. See `Object Ids` for exactly what this rewrites,
          why it is on, and the one case in which you want it off.
        - ``document_path``: Directory that documents given to `Load Document` and
          `Insert Document From File` by file name are looked up in. It saves naming the
          directory in every call and does nothing else: a path given to the keyword is
          used as written whether this is set or not. See `Documents From Files`.

        | Library    MongoDBLibrary
        | Library    MongoDBLibrary    coerce_object_ids=${False}
        | Library    MongoDBLibrary    document_path=${CURDIR}/documents

        """
        self.connection_manager = ConnectionManager()
        libraries = [MongoDBKeywords(self.connection_manager, coerce_object_ids=coerce_object_ids,
                                     document_path=document_path)]
        DynamicCore.__init__(self, libraries)
