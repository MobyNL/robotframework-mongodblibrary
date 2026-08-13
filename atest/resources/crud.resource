*** Settings ***
Documentation       Shared steps for the CRUD suites.
...
...                 The importing suite selects how to connect and which collections to
...                 use by defining ${CONNECT_METHOD}, ${COLLECTION} and
...                 ${DELETE_ALL_COLLECTION}. Everything else is identical between them,
...                 so it lives here rather than being duplicated per suite.

Library             Collections
Library             MongoDBLibrary
Resource            ../local.resource


*** Keywords ***
Connect To Test Database
    [Documentation]    Connect under ${alias} using the method the suite selected.
    [Arguments]    ${alias}
    IF    '${CONNECT_METHOD}' == 'connection string'
        Connect To Database Using Connection String
        ...    db_conn_string=${DB_CONNECT_STRING}
        ...    db_name=${DB_NAME}
        ...    alias=${alias}
    ELSE
        Connect To Database
        ...    db_name=${DB_NAME}
        ...    db_user=${DB_USER}
        ...    db_password=${DB_PASSWORD}
        ...    db_host=${DB_HOST}
        ...    db_port=${DB_PORT}
        ...    srv=${DB_SRV}
        ...    alias=${alias}
    END

Prepare Test Data
    [Documentation]    Insert the fixture documents the tests in the suite rely on.
    Connect To Test Database    setup_alias
    FOR    ${unique_id}    IN
    ...        test_find
    ...        test_count
    ...        test_query
    ...        test_delete_many
    ...        test_delete_many
        Insert Document
        ...    collection_name=${COLLECTION}
        ...    document={"unique_id": "${unique_id}"}
        ...    alias=setup_alias
    END

    # Inserted as a dictionary rather than a JSON string, to cover both argument forms.
    VAR    &{dict_document}    unique_id=test_dict_document
    Insert Document
    ...    collection_name=${COLLECTION}
    ...    document=${dict_document}
    ...    alias=setup_alias

    Repeat Keyword    2 times
    ...    Insert Document
    ...    collection_name=${DELETE_ALL_COLLECTION}
    ...    document={"unique_id": "test_delete_all"}
    ...    alias=setup_alias
    Disconnect From Database    alias=setup_alias

Cleanup Test Data
    [Documentation]    Empty every collection the suite touched.
    Connect To Test Database    teardown_alias
    Delete All Documents From Collection    collection_name=${COLLECTION}    alias=teardown_alias
    Delete All Documents From Collection    collection_name=${DELETE_ALL_COLLECTION}    alias=teardown_alias
    Disconnect From Database    alias=teardown_alias

Insert Document Should Return An Id
    [Documentation]    Inserting returns the id of the new document.
    [Arguments]    ${alias}
    ${doc_id}    Insert Document
    ...    collection_name=${COLLECTION}
    ...    document={"key": "value", "testcase": "${TEST NAME}"}
    ...    alias=${alias}
    Should Be True    $doc_id is not None    Insert should return the new document id

Find Document Should Return The Fixture Document
    [Documentation]    Finding returns a document whose fields are dot-accessible.
    [Arguments]    ${alias}
    ${document}    Find Document
    ...    collection_name=${COLLECTION}
    ...    unique_id=test_find
    ...    alias=${alias}
    Should Be Equal    ${document.unique_id}    test_find

Find Documents Should Return Every Match
    [Documentation]    Finding many returns a sorted, limited list.
    [Arguments]    ${alias}
    ${documents}    Find Documents
    ...    collection_name=${COLLECTION}
    ...    unique_id=test_delete_many
    ...    alias=${alias}
    Length Should Be    ${documents}    2

Delete Many Should Delete Every Matching Document
    [Documentation]    Deleting many reports how many documents went.
    [Arguments]    ${alias}
    ${deleted_count}    Delete Many
    ...    collection_name=${COLLECTION}
    ...    unique_id=test_delete_many
    ...    alias=${alias}
    Should Be Equal As Integers    ${deleted_count}    2

Execute Query Should Return The Matching Documents
    [Documentation]    An aggregation pipeline returns the documents it matched.
    [Arguments]    ${alias}
    ${results}    Execute Query
    ...    collection_name=${COLLECTION}
    ...    pipeline=[{"$match": {"unique_id": "test_query"}}]
    ...    alias=${alias}
    Length Should Be    ${results}    1

Count Documents Should Count The Matching Documents
    [Documentation]    Counting matches exactly the fixture document.
    [Arguments]    ${alias}
    ${count}    Count Documents
    ...    collection_name=${COLLECTION}
    ...    unique_id=test_count
    ...    alias=${alias}
    Should Be Equal As Integers    ${count}    1

Get Distinct Values Should Return Each Value Once
    [Documentation]    Distinct collapses repeated values across the matching documents.
    [Arguments]    ${alias}
    FOR    ${status}    IN    new    new    shipped
        Insert Document
        ...    collection_name=${COLLECTION}
        ...    document={"unique_id": "test_distinct", "status": "${status}"}
        ...    alias=${alias}
    END
    ${statuses}    Get Distinct Values
    ...    collection_name=${COLLECTION}
    ...    field=status
    ...    query={"unique_id": "test_distinct"}
    ...    alias=${alias}
    ${statuses}    Evaluate    sorted($statuses)
    Should Be Equal    ${statuses}    ${{ ['new', 'shipped'] }}

Replace Document Should Remove The Fields It Does Not Mention
    [Documentation]    Replacing swaps the whole document, unlike an update that merges.
    [Arguments]    ${alias}
    Insert Document
    ...    collection_name=${COLLECTION}
    ...    document={"unique_id": "test_replace", "stale": "gone"}
    ...    alias=${alias}
    ${replaced}    Replace Document
    ...    collection_name=${COLLECTION}
    ...    query={"unique_id": "test_replace"}
    ...    replacement={"unique_id": "test_replace"}
    ...    alias=${alias}
    Dictionary Should Not Contain Key    ${replaced}    stale

Update Document Should Insert When Upserting Against No Match
    [Documentation]    Upserting twice must leave one document, not two.
    [Arguments]    ${alias}
    FOR    ${_}    IN RANGE    2
        Update Document
        ...    collection_name=${COLLECTION}
        ...    query={"unique_id": "test_upsert"}
        ...    update={"checked": True}
        ...    upsert=${True}
        ...    alias=${alias}
    END
    ${count}    Count Documents
    ...    collection_name=${COLLECTION}
    ...    unique_id=test_upsert
    ...    alias=${alias}
    Should Be Equal As Integers    ${count}    1

Delete Document And Return It Should Give Back What It Deleted
    [Documentation]    One operation, so nothing can change between reading and deleting.
    [Arguments]    ${alias}
    Insert Document
    ...    collection_name=${COLLECTION}
    ...    document={"unique_id": "test_delete_return", "payload": 42}
    ...    alias=${alias}
    ${deleted}    Delete Document And Return It
    ...    collection_name=${COLLECTION}
    ...    unique_id=test_delete_return
    ...    alias=${alias}
    Should Be Equal As Integers    ${deleted.payload}    42
    Document Should Not Exist
    ...    collection_name=${COLLECTION}
    ...    unique_id=test_delete_return
    ...    alias=${alias}

Document Existence Assertions Should Agree With The Data
    [Documentation]    The two existence assertions over a document that is there and one that is not.
    [Arguments]    ${alias}
    Document Should Exist
    ...    collection_name=${COLLECTION}
    ...    unique_id=test_find
    ...    alias=${alias}
    Document Should Not Exist
    ...    collection_name=${COLLECTION}
    ...    unique_id=never_inserted
    ...    alias=${alias}

Delete All Documents Should Empty The Collection
    [Documentation]    Deleting everything leaves the collection empty.
    [Arguments]    ${alias}
    ${deleted_count}    Delete All Documents From Collection
    ...    collection_name=${DELETE_ALL_COLLECTION}
    ...    alias=${alias}
    Should Be Equal As Integers    ${deleted_count}    2
    ${remaining}    Count Documents    collection_name=${DELETE_ALL_COLLECTION}    alias=${alias}
    Should Be Equal As Integers    ${remaining}    0
