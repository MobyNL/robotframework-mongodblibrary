# Robot Framework MongoDBLibrary

MongoDBLibrary is a test library for [Robot Framework](https://robotframework.org/) that provides keywords for interacting with MongoDB databases.

## Features
- Connect to a single host, a connection string, or a hosted cluster such as MongoDB Atlas
- Named connections with a connection pool, and clients shared between aliases
- CRUD on one or many documents, with MongoDB query and update operators
- Queries with projection, sorting, limiting and skipping
- Index creation, listing and dropping
- Retrying assertions on a query result or a document count
- Designed for use in Robot Framework test suites

## Installation

```bash
pip install robotframework-mongodb
```

Or with Poetry:

```bash
poetry add robotframework-mongodb
```

## Usage Example

Keywords take named arguments. Pass credentials as variables rather than writing them
into the suite, because Robot Framework copies the argument as written into the log.

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
section of the [keyword documentation](MongoDBLibraryKeywords.html).

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

## Using with AWS (DocumentDB/IAM Authentication)

To connect to AWS DocumentDB or use AWS IAM authentication, install the library with the `aws` extra:

```bash
pip install "robotframework-mongodb[aws]"
```

Or with Poetry:

```bash
poetry add robotframework-mongodb --extras aws
```

This will install the required dependency `pymongo-auth-aws`.

When connecting, use the appropriate MongoDB URI and ensure your environment is configured with AWS credentials (e.g., via environment variables, AWS CLI, or EC2 instance roles).

Example:

```robotframework
*** Settings ***
Library    MongoDBLibrary

*** Test Cases ***
Connect To AWS DocumentDB
    Connect To Database Using Connection String
    ...    db_conn_string=${DB_CONNECT_STRING}    db_name=mydb
```

## License
MIT
