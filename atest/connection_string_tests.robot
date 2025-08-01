*** Settings ***
Library             MongoDBLibrary
Resource            local.resource

Suite Setup         Prepare Test Data
Suite Teardown      Cleanup Test Data


*** Test Cases ***
Verify Connect To Database Using Connection String
    [Documentation]    Test connecting to a MongoDB database using connection string.
    Connect To Database Using Connection String
    ...     db_conn_string=${DB_CONNECT_STRING}
    ...     db_name=${DB_NAME}
    ...     alias=test_alias_connect
    Disconnect From Database        alias=test_alias_connect

Verify Insert Document Using Connection String
    [Documentation]    Test inserting a document into a MongoDB collection using connection string.
    Connect To Database Using Connection String
    ...             db_conn_string=${DB_CONNECT_STRING}
    ...             db_name=${DB_NAME}
    ...             alias=test_alias_insert
    ${doc_id}       Insert Document
    ...             collection_name=test_collection_string
    ...             document={"key": "value", "testcase": "Verify Insert Document Using Connection String"}
    ...             alias=test_alias_insert
    Disconnect From Database                alias=test_alias_insert

Verify Find Document Using Connection String
    [Documentation]    Test finding a document in a MongoDB collection using connection string.
    Connect To Database Using Connection String
    ...                 db_conn_string=${DB_CONNECT_STRING}
    ...                 db_name=${DB_NAME}
    ...                 alias=test_alias_find
    ${document}         Find Document
    ...                 collection_name=test_collection_string
    ...                 key=value
    ...                 alias=test_alias_find
    Should Be True      ${document}             Found document should not be None
    Disconnect From Database                    alias=test_alias_find

Verify Delete Many Documents Using Connection String
    [Documentation]    Test deleting multiple documents from a MongoDB collection using connection string.
    Connect To Database Using Connection String
    ...                 db_conn_string=${DB_CONNECT_STRING}
    ...                 db_name=${DB_NAME}
    ...                 alias=test_alias_delete_many
    ${deleted_count}    Delete Many
    ...                 collection_name=test_collection_string
    ...                 unique_id=test_delete_many
    ...                 alias=test_alias_delete_many
    Should Be True      ${deleted_count} > 0
    Disconnect From Database                    alias=test_alias_delete_many

Verify Execute Query Using Connection String
    [Documentation]    Test executing an aggregation pipeline query on a MongoDB collection using connection string.
    Connect To Database Using Connection String
    ...                 db_conn_string=${DB_CONNECT_STRING}
    ...                 db_name=${DB_NAME}
    ...                 alias=test_alias_query
    ${results}          Execute Query
    ...                 collection_name=test_collection_string
    ...                 pipeline=[{"$match": {"unique_id": "test_query"}}]
    ...                 alias=test_alias_query
    Should Be True      ${results}              Query results should not be empty
    Disconnect From Database                    alias=test_alias_query

Verify Count Documents Using Connection String
    [Documentation]    Test counting documents in a MongoDB collection using connection string.
    Connect To Database Using Connection String
    ...                 db_conn_string=${DB_CONNECT_STRING}
    ...                 db_name=${DB_NAME}
    ...                 alias=test_alias_count
    ${count}            Count Documents
    ...                 collection_name=test_collection_string
    ...                 alias=test_alias_count
    ...                 unique_id=test_count
    Should Be True      ${count} > 0
    Disconnect From Database                    alias=test_alias_count

Verify Delete All Documents From Collection Using Connection String
    [Documentation]    Test deleting all documents from a MongoDB collection using connection string.
    Connect To Database Using Connection String
    ...                 db_conn_string=${DB_CONNECT_STRING}
    ...                 db_name=${DB_NAME}
    ...                 alias=test_alias_delete_all
    ${deleted_count}    Delete All Documents From Collection
    ...                 collection_name=test_collection_string_delete_all
    ...                 alias=test_alias_delete_all
    Should Be True      ${deleted_count} > 0
    Disconnect From Database                    alias=test_alias_delete_all


*** Keywords ***
Cleanup Test Data
    [Documentation]    Cleanup all test data from the database.
    Connect To Database Using Connection String
    ...     db_conn_string=${DB_CONNECT_STRING}
    ...     db_name=${DB_NAME}
    ...     alias=teardown_alias
    Delete All Documents From Collection
    ...     collection_name=test_collection_string
    ...     alias=teardown_alias
    Delete All Documents From Collection
    ...     collection_name=test_collection_string_delete_all
    ...     alias=teardown_alias
    Disconnect From Database        alias=teardown_alias

Prepare Test Data
    [Documentation]    Prepare unique test data for each test case.
    Connect To Database Using Connection String
    ...                 db_conn_string=${DB_CONNECT_STRING}
    ...                 db_name=${DB_NAME}
    ...                 alias=setup_alias
    Insert Document
    ...                 collection_name=test_collection_string
    ...                 document={"unique_id": "test_insert"}
    ...                 alias=setup_alias
    Insert Document
    ...                 collection_name=test_collection_string
    ...                 document={"unique_id": "test_find"}
    ...                 alias=setup_alias
    Insert Document
    ...                 collection_name=test_collection_string
    ...                 document={"unique_id": "test_count"}
    ...                 alias=setup_alias
    Insert Document
    ...                 collection_name=test_collection_string
    ...                 document={"unique_id": "test_query"}
    ...                 alias=setup_alias
    VAR    &{delete_all_doc}
    ...    unique_id=test_delete_all
    Insert Document
    ...                 collection_name=test_collection_string
    ...                 document=${delete_all_doc}
    ...                 alias=setup_alias
    Insert Document
    ...                 collection_name=test_collection_string
    ...                 document={"unique_id": "test_delete"}
    ...                 alias=setup_alias
    Insert Document
    ...                 collection_name=test_collection_string
    ...                 document={"unique_id": "test_delete_many"}
    ...                 alias=setup_alias
    Insert Document
    ...                 collection_name=test_collection_string
    ...                 document={"unique_id": "test_delete_many"}
    ...                 alias=setup_alias

    Insert Document
    ...                 collection_name=test_collection_string_delete_all
    ...                 document={"unique_id": "test_delete_all"}
    ...                 alias=setup_alias
    Insert Document
    ...                 collection_name=test_collection_string_delete_all
    ...                 document={"unique_id": "test_delete_all"}
    ...                 alias=setup_alias
    Disconnect From Database                    alias=setup_alias
