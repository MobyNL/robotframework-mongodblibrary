*** Settings ***
Documentation       The CRUD keywords over a connection-string connection.
...
...                 The steps live in resources/crud.resource, shared with the
...                 user/password suite, which runs the same tests over a connection
...                 built from a host and credentials.

Resource            resources/crud.resource

Suite Setup         Prepare Test Data
Suite Teardown      Cleanup Test Data


*** Variables ***
${CONNECT_METHOD}           connection string
${COLLECTION}               test_collection_string
${DELETE_ALL_COLLECTION}    test_collection_string_delete_all


*** Test Cases ***
Verify Connect Using Connection String
    [Documentation]    Test connecting to a MongoDB database using connection string.
    Connect To Test Database               test_alias_connect
    Check If Database Connection Exists    alias=test_alias_connect
    [Teardown]    Disconnect From Database    alias=test_alias_connect

Verify Insert Document Using Connection String
    [Documentation]    Test inserting a document into a MongoDB collection.
    [Setup]    Connect To Test Database    test_alias_insert
    Insert Document Should Return An Id    test_alias_insert
    [Teardown]    Disconnect From Database    alias=test_alias_insert

Verify Find Document Using Connection String
    [Documentation]    Test finding a document in a MongoDB collection.
    [Setup]    Connect To Test Database    test_alias_find
    Find Document Should Return The Fixture Document    test_alias_find
    [Teardown]    Disconnect From Database    alias=test_alias_find

Verify Find Documents Using Connection String
    [Documentation]    Test finding every matching document in a MongoDB collection.
    [Setup]    Connect To Test Database    test_alias_find_many
    Find Documents Should Return Every Match    test_alias_find_many
    [Teardown]    Disconnect From Database    alias=test_alias_find_many

Verify Execute Query Using Connection String
    [Documentation]    Test executing an aggregation pipeline query.
    [Setup]    Connect To Test Database    test_alias_query
    Execute Query Should Return The Matching Documents    test_alias_query
    [Teardown]    Disconnect From Database    alias=test_alias_query

Verify Count Documents Using Connection String
    [Documentation]    Test counting documents in a MongoDB collection.
    [Setup]    Connect To Test Database    test_alias_count
    Count Documents Should Count The Matching Documents    test_alias_count
    [Teardown]    Disconnect From Database    alias=test_alias_count

Verify Delete Many Documents Using Connection String
    [Documentation]    Test deleting multiple documents from a MongoDB collection.
    [Setup]    Connect To Test Database    test_alias_delete_many
    Delete Many Should Delete Every Matching Document    test_alias_delete_many
    [Teardown]    Disconnect From Database    alias=test_alias_delete_many

Verify Delete All Documents From Collection Using Connection String
    [Documentation]    Test deleting all documents from a MongoDB collection.
    [Setup]    Connect To Test Database    test_alias_delete_all
    Delete All Documents Should Empty The Collection    test_alias_delete_all
    [Teardown]    Disconnect From Database    alias=test_alias_delete_all
