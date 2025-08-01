*** Settings ***
Library     MongoDBLibrary
Resource    local.resource


*** Test Cases ***
Verify Connect To Database Using User Password
    [Documentation]    Test connecting to a MongoDB database using user and password.
    Connect To Database
    ...                     db_name=${DB_NAME}
    ...                     db_user=${DB_USER}
    ...                     db_password=${DB_PASSWORD}
    ...                     db_host=${DB_HOST}
    ...                     db_port=${DB_PORT}
    ...                     alias=test_alias
    Log                     Connected to database successfully
    Disconnect From Database                        alias=test_alias

Verify Insert Document Using User Password
    [Documentation]    Test inserting a document into a MongoDB collection using user and password.
    Connect To Database
    ...                     db_name=${DB_NAME}
    ...                     db_user=${DB_USER}
    ...                     db_password=${DB_PASSWORD}
    ...                     db_host=${DB_HOST}
    ...                     db_port=${DB_PORT}
    ...                     alias=test_alias
    ${doc_id}               Insert Document
    ...                     collection_name=test_collection
    ...                     document={"key": "value"}
    ...                     alias=test_alias
    Log                     Inserted document with ID: ${doc_id}
    Disconnect From Database                        alias=test_alias

Verify Find Document Using User Password
    [Documentation]    Test finding a document in a MongoDB collection using user and password.
    Connect To Database
    ...                     db_name=${DB_NAME}
    ...                     db_user=${DB_USER}
    ...                     db_password=${DB_PASSWORD}
    ...                     db_host=${DB_HOST}
    ...                     db_port=${DB_PORT}
    ...                     alias=test_alias
    ${document}             Find Document
    ...                     collection_name=test_collection
    ...                     key=value
    ...                     alias=test_alias
    Should Be True          ${document}             Found document should not be None
    Log                     Found document: ${document}
    Disconnect From Database                        alias=test_alias

Verify Update Document Using User Password
    [Documentation]    Test updating a document in a MongoDB collection using user and password.
    Connect To Database
    ...                     db_name=${DB_NAME}
    ...                     db_user=${DB_USER}
    ...                     db_password=${DB_PASSWORD}
    ...                     db_host=${DB_HOST}
    ...                     db_port=${DB_PORT}
    ...                     alias=test_alias
    ${updated_doc}          Update Document
    ...                     collection_name=test_collection
    ...                     query={"key": "value"}
    ...                     update={"key": "new_value"}
    ...                     alias=test_alias
    Should Be True          ${updated_doc}          Updated document should not be None
    Log                     Updated document: ${updated_doc}
    Disconnect From Database                        alias=test_alias

Verify Delete Document Using User Password
    [Documentation]    Test deleting a document from a MongoDB collection using user and password.
    Connect To Database
    ...                     db_name=${DB_NAME}
    ...                     db_user=${DB_USER}
    ...                     db_password=${DB_PASSWORD}
    ...                     db_host=${DB_HOST}
    ...                     db_port=${DB_PORT}
    ...                     alias=test_alias
    ${deleted_count}        Delete Document
    ...                     collection_name=test_collection
    ...                     key=new_value
    ...                     alias=test_alias
    Should Be Equal As Integers                     ${deleted_count}        1
    Log                     Deleted document count: ${deleted_count}
    Disconnect From Database                        alias=test_alias

Verify Delete Many Documents Using User Password
    [Documentation]    Test deleting multiple documents from a MongoDB collection using user and password.
    Connect To Database
    ...                     db_name=${DB_NAME}
    ...                     db_user=${DB_USER}
    ...                     db_password=${DB_PASSWORD}
    ...                     db_host=${DB_HOST}
    ...                     db_port=${DB_PORT}
    ...                     alias=test_alias
    ${deleted_count}        Delete Many
    ...                     collection_name=test_collection
    ...                     key=value
    ...                     alias=test_alias
    Should Be True          ${deleted_count} > 0
    Log                     Deleted document count: ${deleted_count}
    Disconnect From Database                        alias=test_alias

Verify Execute Query Using User Password
    [Documentation]    Test executing an aggregation pipeline query on a MongoDB collection using user and password.
    Connect To Database
    ...                     db_name=${DB_NAME}
    ...                     db_user=${DB_USER}
    ...                     db_password=${DB_PASSWORD}
    ...                     db_host=${DB_HOST}
    ...                     db_port=${DB_PORT}
    ...                     alias=test_alias
    ${results}              Execute Query
    ...                     collection_name=test_collection
    ...                     pipeline=[{"$match": {"key": "value"}}]
    ...                     alias=test_alias
    Should Be True          ${results}              Query results should not be empty
    Log                     Query results: ${results}
    Disconnect From Database                        alias=test_alias

Verify Count Documents Using User Password
    [Documentation]    Test counting documents in a MongoDB collection using user and password.
    Connect To Database
    ...                     db_name=${DB_NAME}
    ...                     db_user=${DB_USER}
    ...                     db_password=${DB_PASSWORD}
    ...                     db_host=${DB_HOST}
    ...                     db_port=${DB_PORT}
    ...                     alias=test_alias
    ${count}                Count Documents
    ...                     collection_name=test_collection
    ...                     query={"key": "value"}
    ...                     alias=test_alias
    Should Be True          ${count} > 0
    Log                     Document count: ${count}
    Disconnect From Database                        alias=test_alias

Verify Delete All Documents From Collection Using User Password
    [Documentation]    Test deleting all documents from a MongoDB collection using user and password.
    Connect To Database
    ...                     db_name=${DB_NAME}
    ...                     db_user=${DB_USER}
    ...                     db_password=${DB_PASSWORD}
    ...                     db_host=${DB_HOST}
    ...                     db_port=${DB_PORT}
    ...                     alias=test_alias
    ${deleted_count}        Delete All Documents From Collection
    ...                     collection_name=test_collection
    ...                     alias=test_alias
    Should Be True          ${deleted_count} > 0
    Log                     Deleted document count: ${deleted_count}
    Disconnect From Database                        alias=test_alias
