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
# robocop: off=unused-variable
# Read by the shared steps in resources/crud.resource. The rule checks one file at a
# time, so it cannot see a variable that is defined here and used there.
${CONNECT_METHOD}           connection string
${COLLECTION}               test_collection_string
${DELETE_ALL_COLLECTION}    test_collection_string_delete_all
# robocop: on=unused-variable


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

Verify Get Distinct Values Using Connection String
    [Documentation]    Test collecting the distinct values of a field.
    [Setup]    Connect To Test Database    test_alias_distinct
    Get Distinct Values Should Return Each Value Once    test_alias_distinct
    [Teardown]    Disconnect From Database    alias=test_alias_distinct

Verify Replace Document Using Connection String
    [Documentation]    Test replacing a whole document rather than merging into it.
    [Setup]    Connect To Test Database    test_alias_replace
    Replace Document Should Remove The Fields It Does Not Mention    test_alias_replace
    [Teardown]    Disconnect From Database    alias=test_alias_replace

Verify Upsert Using Connection String
    [Documentation]    Test that upserting is idempotent.
    [Setup]    Connect To Test Database    test_alias_upsert
    Update Document Should Insert When Upserting Against No Match    test_alias_upsert
    [Teardown]    Disconnect From Database    alias=test_alias_upsert

Verify Delete Document And Return It Using Connection String
    [Documentation]    Test deleting a document and reading it in one operation.
    [Setup]    Connect To Test Database    test_alias_delete_return
    Delete Document And Return It Should Give Back What It Deleted    test_alias_delete_return
    [Teardown]    Disconnect From Database    alias=test_alias_delete_return

Verify Document Existence Assertions Using Connection String
    [Documentation]    Test the existence assertions against real data.
    [Setup]    Connect To Test Database    test_alias_exists
    Document Existence Assertions Should Agree With The Data    test_alias_exists
    [Teardown]    Disconnect From Database    alias=test_alias_exists

Verify Delete All Documents From Collection Using Connection String
    [Documentation]    Test deleting all documents from a MongoDB collection.
    [Setup]    Connect To Test Database    test_alias_delete_all
    Delete All Documents Should Empty The Collection    test_alias_delete_all
    [Teardown]    Disconnect From Database    alias=test_alias_delete_all
