# Robot Framework MongoDBLibrary

[![PyPI](https://img.shields.io/pypi/v/robotframework-mongodb.svg)](https://pypi.org/project/robotframework-mongodb/)
[![Python versions](https://img.shields.io/pypi/pyversions/robotframework-mongodb.svg)](https://pypi.org/project/robotframework-mongodb/)
[![CI](https://github.com/MobyNl/robotframework-mongodblibrary/actions/workflows/ci.yml/badge.svg)](https://github.com/MobyNl/robotframework-mongodblibrary/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

MongoDBLibrary is a test library for [Robot Framework](https://robotframework.org/) that provides keywords for interacting with MongoDB databases.

📖 **[Keyword documentation](https://mobynl.github.io/robotframework-mongodblibrary/)** —
every keyword, its arguments and examples.

- [Features](#features)
- [Installation](#installation)
- [Requirements](#requirements)
- [Importing](#importing)
- [Usage Example](#usage-example)
- [Resetting Between Tests](#resetting-between-tests)
- [Waiting For Data](#waiting-for-data)
- [Document Ids](#document-ids)
- [Connecting To A Hosted Cluster (MongoDB Atlas)](#connecting-to-a-hosted-cluster-mongodb-atlas)
- [Using With AWS](#using-with-aws)
- [Beyond These Keywords](#beyond-these-keywords)
- [Older Robot Framework Versions](#older-robot-framework-versions)

## Features
- Connect to a single host, a connection string, or a hosted cluster such as MongoDB Atlas
- Named connections with a connection pool, and clients shared between aliases
- CRUD on one or many documents, with MongoDB query and update operators
- Queries with projection, sorting, limiting, skipping and distinct values
- Upserting and whole-document replacement, so a fixture step can run twice
- Collection and database management: create, drop, list
- Index creation, listing and dropping, including unique, sparse and TTL indexes
- Retrying assertions on a query result, a document count, a set of values, or the
  existence of a document, a collection or an index
- `Run Database Command` for everything the keywords do not wrap
- Runs on Robot Framework 5.0 through 7.x, from one code path

## Installation

```bash
pip install robotframework-mongodb
```

Or with Poetry:

```bash
poetry add robotframework-mongodb
```

## Requirements

| | Supported |
|---|---|
| Robot Framework | 5.0 – 7.x |
| Python | 3.10 – 3.14 |
| MongoDB | any version pymongo 4 speaks to (3.6 and later) |

Everything in the supported range is exercised in CI, not merely allowed by the version
constraint. If you are on an older Robot Framework, read
[Older Robot Framework Versions](#older-robot-framework-versions) — one keyword argument
behaves differently and the rest is identical.

Three names differ and are easy to mix up: the package you install is
`robotframework-mongodb`, the library you import is `MongoDBLibrary`, and the repository
is `robotframework-mongodblibrary`.

## Importing

```robotframework
*** Settings ***
Library    MongoDBLibrary    coerce_object_ids=${True}
```

`coerce_object_ids` (default `${True}`) is the library's only import-time argument. It
controls whether a string `_id` in a query is rewritten to a BSON `ObjectId`; see
[Document Ids](#document-ids) for what that means and when to turn it off. Everything
else — hosts, credentials, TLS, auth mechanism — is configured per connection, on the
connect keywords.

The library's scope is `GLOBAL`, so one instance is shared by every suite in a run and a
connection opened in one suite is still open in the next. One consequence is worth
knowing: Robot Framework creates a separate instance per set of import arguments, so two
suites that import with *different* `coerce_object_ids` values get separate instances,
and therefore separate connection pools rather than shared connections.

## Usage Example

Keywords take named arguments:

```robotframework
*** Settings ***
Library    MongoDBLibrary

*** Test Cases ***
Connect With A Host And Credentials
    Connect To Database    db_name=mydb    db_user=${DB_USER}    db_password=${DB_PASSWORD}
    ...                    db_host=localhost    db_port=27017
    ${doc_id}              Insert Document    collection_name=mycollection    document={"key": "value"}
    ${document}            Find Document      collection_name=mycollection    key=value
    [Teardown]             Disconnect From Database

Connect With A Connection String
    Connect To Database Using Connection String    db_conn_string=${DB_CONNECT_STRING}    db_name=mydb
    ${count}               Count Documents    collection_name=mycollection    key=value
    [Teardown]             Disconnect From Database
```

### Several Databases At Once

Give each connection an `alias` and the connections stay open side by side. Keywords use
the active connection unless passed an `alias` of their own, and `Switch Connection`
changes which one that is:

```robotframework
*** Test Cases ***
Copy A Document Between Two Databases
    Connect To Database    db_name=source    db_host=localhost    alias=source
    Connect To Database    db_name=target    db_host=localhost    alias=target
    ${document}    Find Document    collection_name=orders    order_id=A-1    alias=source
    Switch Connection    alias=target
    Insert Document      collection_name=orders    document=${document}
    [Teardown]           Disconnect From All Databases
```

### Keeping Credentials Out Of The Log

Pass credentials as variables rather than writing them into the suite, because Robot
Framework copies the argument as written into the log.

On Robot Framework 7.4 and later, `db_password` and `db_conn_string` accept a
[`Secret`](https://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html#secret-type),
which keeps the value out of `log.html` and `output.xml`:

```robotframework
*** Variables ***
${DB_PASSWORD: Secret}    %{MONGO_PASSWORD}

*** Test Cases ***
Connect With A Secret
    Connect To Database    db_name=mydb    db_user=${DB_USER}    db_password=${DB_PASSWORD}
    ...                    db_host=localhost
```

A secret can only come from the environment — Robot Framework refuses to build one from
a literal, so the value cannot be written into the suite by accident. It is not
encryption: the value is plain text in memory and is sent to MongoDB as typed. What it
prevents is Robot Framework recording the argument.

On Robot Framework 5.0 through 7.3 there is no `Secret` type, so both arguments take a
plain string and nothing above applies. Nothing else differs; see
[Older Robot Framework Versions](#older-robot-framework-versions).

## Resetting Between Tests

`Delete All Documents From Collection` removes the documents but leaves everything
*defined* on the collection — its indexes and options. So a unique index created by one
test still rejects the next test's fixtures. `Drop Collection` removes the collection
itself, which is what actually resets it, and succeeds when the collection is not there:

```robotframework
*** Test Cases ***
Reset The Collection Completely
    [Teardown]    Drop Collection    collection_name=orders
```

To write a setup step that can run twice, upsert rather than insert:

```robotframework
*** Keywords ***
Ensure The Test User Exists
    Update Document    collection_name=users    query={"email": "a@example.test"}
    ...                update={"active": ${True}}    upsert=${True}
```

## Waiting For Data

The assertion keywords retry, which is the part a suite gets wrong when it hand-rolls
the wait around `Find Document`:

```robotframework
*** Test Cases ***
Wait For The Order To Be Written
    Document Should Exist    collection_name=orders    order_id=A-1    retry_timeout=10 seconds
    Check Distinct Values    collection_name=orders    field=status
    ...                      assertion_operator=not contains    expected_value=pending
```

## Document Ids

**This library rewrites the `_id` in your queries.** MongoDB stores `_id` as a BSON
`ObjectId`, not a string, and the two never match each other. Robot Framework stores
variables as text, so an id that has been through a variable, a file or an API response
arrives as a string and would silently match nothing — no error, just an empty result.

So before a query is sent, an `_id` that is a string of 24 hexadecimal characters is
converted to an `ObjectId`:

```
_id="6a7ccdea6abf6a4ebbc3514f"   ->   _id=ObjectId("6a7ccdea6abf6a4ebbc3514f")
```

Values inside `$in` and comparison operators are converted too. Anything that is *not* a
valid ObjectId (`user-42`, `order_991`) is passed through untouched, as is every field
other than `_id`, every document you insert, and every aggregation pipeline.

Turn it off if your collections use string `_id`s that happen to be 24 hex characters,
such as a truncated hash — the conversion would look for an ObjectId that does not exist:

```robotframework
*** Settings ***
Library    MongoDBLibrary    coerce_object_ids=${False}

*** Test Cases ***
Query An Id Explicitly
    ${oid}    Convert To Object Id    ${doc_id}
    Find Document    collection_name=orders    _id=${oid}
```

Full details, including exactly what is and is not rewritten, are in the `Object Ids`
section of the [keyword documentation](https://mobynl.github.io/robotframework-mongodblibrary/).

## Connecting To A Hosted Cluster (MongoDB Atlas)

A hosted cluster's name is a DNS seed list rather than a single host, so it needs
`mongodb+srv` resolution and TLS. Either use the connection string keyword with the
`mongodb+srv://` URI from your provider, or set `srv=${True}`:

```robotframework
*** Test Cases ***
Connect To Atlas With A Connection String
    Connect To Database Using Connection String
    ...    db_conn_string=${DB_CONNECT_STRING}    db_name=mydb

Connect To Atlas With A Cluster Name
    Connect To Database    db_name=mydb    db_user=${DB_USER}    db_password=${DB_PASSWORD}
    ...                    db_host=mycluster.abcde.mongodb.net    srv=${True}
```

`db_port` is ignored when `srv` is enabled, because the seed list supplies its own
ports. Use `tls=${False}` to force TLS off, or `tls=${True}` to force it on for a
plain host.

## Using With AWS

Two separate things are often confused here. Amazon DocumentDB is a MongoDB-compatible
service whose *transport* needs particular settings; AWS IAM authentication is a
*credential* mechanism, usable against DocumentDB 5.0 and later and against Atlas
clusters hosted on AWS. They are configured independently, and you may want one, the
other, or both.

Neither path is exercised in CI, unlike the Robot Framework range — they need AWS
infrastructure. The library passes these options straight to pymongo and contains no
AWS-specific code.

### Amazon DocumentDB

DocumentDB requires TLS against Amazon's own certificate authority, and it does not
implement retryable writes, which pymongo enables by default. Leaving `retryWrites` on
is the usual first failure. `tlsCAFile` has no keyword argument, so DocumentDB is the one
case where the connection string is the only route:

```robotframework
*** Variables ***
${DB_CONNECT_STRING}    mongodb://${DB_USER}:${DB_PASSWORD}@mycluster.cluster-abc123.eu-west-1.docdb.amazonaws.com:27017/?tls=true&tlsCAFile=global-bundle.pem&replicaSet=rs0&readPreference=secondaryPreferred&retryWrites=false

*** Test Cases ***
Connect To DocumentDB
    Connect To Database Using Connection String
    ...    db_conn_string=${DB_CONNECT_STRING}    db_name=mydb
    [Teardown]    Disconnect From Database
```

- `tls=true&tlsCAFile=global-bundle.pem` — download the bundle from
  [Amazon's CA page](https://docs.aws.amazon.com/documentdb/latest/developerguide/ca_cert_rotation.html)
  and give the path to it.
- `retryWrites=false` — required; without it every write fails.
- `replicaSet=rs0&readPreference=secondaryPreferred` — for a cluster endpoint. Drop both
  when connecting to a single instance endpoint.

`Connect To Database` reaches `tls`, `replica_set` and `read_preference` as named
arguments, but not `tlsCAFile`, so it only suits a DocumentDB cluster whose CA is already
trusted by the system store.

### AWS IAM Authentication (MONGODB-AWS)

IAM authentication needs two options set together — the mechanism, and an auth source of
`$external`. Install the mechanism's dependency with the `aws` extra:

```bash
pip install "robotframework-mongodb[aws]"
```

```bash
poetry add robotframework-mongodb --extras aws
```

That adds one dependency, `pymongo-auth-aws`. Then set the mechanism, either with named
arguments:

```robotframework
*** Test Cases ***
Connect With An IAM Role
    Connect To Database    db_name=mydb    db_host=mycluster.abcde.mongodb.net
    ...                    srv=${True}    auth_mechanism=MONGODB-AWS    auth_source=$external
    [Teardown]             Disconnect From Database
```

or as URI parameters, which is how you combine IAM with the DocumentDB settings above —
append `&authMechanism=MONGODB-AWS&authSource=$external` to the connection string.

Credentials are resolved by `pymongo-auth-aws`, not by this library. Running on EC2, ECS,
EKS or Lambda, the instance or task role is picked up with no credentials given at all —
which is the point of using IAM. Otherwise `pymongo-auth-aws` reads
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and optionally `AWS_SESSION_TOKEN` from the
environment. For an IAM user you can instead pass the access key as `db_user` and the
secret key as `db_password`.

DocumentDB supports IAM only on version 5.0 and later. See
[pymongo's authentication examples](https://pymongo.readthedocs.io/en/stable/examples/authentication.html),
[Atlas AWS IAM authentication](https://www.mongodb.com/docs/atlas/security/aws-iam-authentication/),
and AWS's
[IAM authentication guide](https://docs.aws.amazon.com/documentdb/latest/developerguide/iam-identity-auth.html).

## Beyond These Keywords

The keywords cover what a suite normally needs. `Run Database Command` reaches
everything else — server statistics, storage sizes, query plans and administrative
commands are all database commands:

```robotframework
*** Test Cases ***
Read A Query Plan
    ${plan}    Run Database Command
    ...        command={"explain": {"find": "orders", "filter": {"status": "new"}}}
```

Transactions and sessions, change streams, GridFS and client-side field level encryption
are deliberately not wrapped, because none of them fit a synchronous keyword taken one at
a time. Use pymongo directly if a suite needs those.

## Older Robot Framework Versions

The library supports Robot Framework 5.0 and later from a single code path — there is no
separate release or compatibility shim to install. Installing it alongside an older Robot
Framework is enough:

```bash
pip install robotframework-mongodb "robotframework==6.1.1"
```

The one dependency that needs pairing is the assertion engine, which backs the retrying
assertion keywords. Its 3.x line requires Robot Framework 6.1.1, so on 5.0 through 6.0
pip needs to be told to take 2.x:

```bash
pip install robotframework-mongodb "robotframework==5.0.1" "robotframework-assertion-engine==2.0.0"
```

`verify_assertion` and `AssertionOperator` are the same in both lines, so every assertion
keyword — the operators it accepts, the retrying, the failure messages — behaves the same
either way.

### What differs on an older version

Only one thing: `Secret`. On 7.4 and later, `db_password` and `db_conn_string` accept
one, and the value is logged as `<secret>`. Below 7.4 the type does not exist, Robot
Framework has no syntax to build one, and both arguments take a plain string — which is
how they worked before 7.4 anyway. The library imports `Secret` conditionally and builds
the argument's type from what is available, so nothing raises and nothing needs a
version check in your suite.

Everything else is unaffected. The rest of what the library imports from `robot`
(`logger`, the `@keyword` decorator, `BuiltIn`, `DotDict`, `timestr_to_secs`) long
predates 5.0, and the keyword signatures use annotations 5.0 already converts.

### Robot Framework 4 and older

Not supported: the assertion engine will not install below 5.0, and 4.x does not convert
the built-in generic annotations the keywords use (`list[str]`, `dict[str, Any]`), so
arguments would arrive as strings.

### How the range is tested

CI runs the unit tests and generates the keyword documentation against Robot Framework
5.0.1, 6.1.1, 7.3.2 and 7.4.0 — the floor, the version where the assertion engine changes
line, and both sides of the `Secret` branch. Libdoc runs too, because it reads every
signature and docstring and so catches an annotation an older version cannot convert,
which the unit tests would not notice. A nightly job additionally installs whatever Robot
Framework and assertion engine are newest on PyPI, ignoring the upper bounds in
`pyproject.toml`, so a release that breaks the library shows up here rather than in your
suite.

## License

[MIT](LICENSE)
