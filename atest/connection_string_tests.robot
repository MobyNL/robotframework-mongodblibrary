*** Settings ***
Library     MongoDBLibrary
Resource    local.resource


*** Test Cases ***
Verify Connect To Database Using Connection String
    [Documentation]    Test connecting to a MongoDB database using connection string.
    Connect To Database Using Connection String
    ...     db_conn_string=${DB_CONNECT_STRING}
    ...     db_name=test_db
    ...     alias=test_alias
    Log     Connected to database successfully
    Disconnect From Database    alias=test_alias

Verify Insert Document Using Connection String
    [Documentation]    Test inserting a document into a MongoDB collection using connection string.
    Connect To Database Using Connection String
    ...             db_conn_string=${DB_CONNECT_STRING}
    ...             db_name=test_db2
    ...             alias=test_alias
    ${doc_id}       Insert Document     collection_name=test_collection         document={"key": "value"}               alias=test_alias
    Log             Inserted document with ID: ${doc_id}
    Disconnect From Database            alias=test_alias

Verify Find Document Using Connection String
    [Documentation]    Test finding a document in a MongoDB collection using connection string.
    Connect To Database Using Connection String
    ...                 db_conn_string=${DB_CONNECT_STRING}
    ...                 db_name=test_db2
    ...                 alias=test_alias
    ${document}         Find Document       collection_name=test_collection         key=value           alias=test_alias
    Should Be True      ${document}         Found document should not be None
    Log                 Found document: ${document}
    Disconnect From Database                alias=test_alias

Verify Update Document Using Connection String
    [Documentation]    Test updating a document in a MongoDB collection using connection string.
    Connect To Database Using Connection String
    ...                 db_conn_string=${DB_CONNECT_STRING}
    ...                 db_name=test_db2
    ...                 alias=test_alias
    ${updated_doc}      Update Document
    ...                 collection_name=test_collection
    ...                 query={"key": "value"}
    ...                 update={"key": "new_value"}
    ...                 alias=test_alias
    Should Be True      ${updated_doc}      Updated document should not be None
    Log                 Updated document: ${updated_doc}
    Disconnect From Database                alias=test_alias

Verify Delete Document Using Connection String
    [Documentation]    Test deleting a document from a MongoDB collection using connection string.
    Connect To Database Using Connection String
    ...                 db_conn_string=${DB_CONNECT_STRING}
    ...                 db_name=test_db2
    ...                 alias=test_alias
    ${deleted_count}    Delete Document     collection_name=test_collection         key=new_value       alias=test_alias
    Should Be Equal As Integers             ${deleted_count}    1
    Log                 Deleted document count: ${deleted_count}
    Disconnect From Database                alias=test_alias
