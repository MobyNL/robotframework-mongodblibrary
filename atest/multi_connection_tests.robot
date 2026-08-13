*** Settings ***
Documentation       Acceptance tests for behaviour the other suites do not reach: switching
...                 between connections, query values that are not strings, the retry
...                 timeout, and releasing the whole connection pool.

Library             MongoDBLibrary
Resource            local.resource

Suite Setup         Connect Both Databases
Suite Teardown      Cleanup Test Data


*** Variables ***
${COLLECTION}       test_collection_multi_connection


*** Test Cases ***
Verify Switch Database Changes The Connection Used By Later Keywords
    [Documentation]    Switching must affect keywords called without an explicit alias.
    Switch Database             alias=second_alias
    Insert Document             collection_name=${COLLECTION}    document={"unique_id": "test_switch"}
    ${in_second}                Count Documents
    ...                         collection_name=${COLLECTION}
    ...                         alias=second_alias
    ...                         unique_id=test_switch
    ${in_first}                 Count Documents
    ...                         collection_name=${COLLECTION}
    ...                         alias=first_alias
    ...                         unique_id=test_switch
    Should Be Equal As Integers                      ${in_second}    1
    Should Be Equal As Integers                      ${in_first}     0
    [Teardown]    Switch Database                    alias=first_alias

Verify A Document Is Found By Its Id As A String
    [Documentation]    Coercion is on by default, so an id that has been through a Robot
    ...    variable still matches the ObjectId stored in the database.
    ${doc_id}                   Insert Document
    ...                         collection_name=${COLLECTION}
    ...                         document={"unique_id": "test_object_id"}
    ...                         alias=first_alias
    ${as_string}                Convert To String    ${doc_id}
    ${found}                    Find Document
    ...                         collection_name=${COLLECTION}
    ...                         _id=${as_string}
    ...                         alias=first_alias
    Should Be Equal             ${found.unique_id}    test_object_id

Verify Query Values Keep Their Type
    [Documentation]    An integer query argument must not be matched as a string.
    Insert Document
    ...                         collection_name=${COLLECTION}
    ...                         document={"unique_id": "test_types", "count": 5}
    ...                         alias=first_alias
    ${count}                    Count Documents
    ...                         collection_name=${COLLECTION}
    ...                         alias=first_alias
    ...                         count=${5}
    Should Be Equal As Integers                      ${count}    1
    ${deleted}                  Delete Many
    ...                         collection_name=${COLLECTION}
    ...                         alias=first_alias
    ...                         count=${5}
    Should Be Equal As Integers                      ${deleted}    1

Verify Check Document Count Honours Retry Timeout With A Zero Pause
    [Documentation]    A zero retry pause must still reach the timeout instead of looping forever.
    [Timeout]    60 seconds
    Run Keyword And Expect Error                     *Wrong document count:*
    ...    Check Document Count
    ...    collection_name=${COLLECTION}
    ...    query={"unique_id": "absent"}
    ...    assertion_operator===
    ...    expected_count=${5}
    ...    retry_timeout=1 second
    ...    retry_pause=0 seconds
    ...    alias=first_alias

Verify Check Document Count And Check Query Result Pass Against Real Data
    [Documentation]    Happy path for the two assertion keywords, which no other suite calls.
    Insert Document
    ...                         collection_name=${COLLECTION}
    ...                         document={"unique_id": "test_assert", "score": 42}
    ...                         alias=first_alias
    Check Document Count
    ...                         collection_name=${COLLECTION}
    ...                         query={"unique_id": "test_assert"}
    ...                         assertion_operator===
    ...                         expected_count=${1}
    ...                         alias=first_alias
    Check Query Result
    ...                         collection_name=${COLLECTION}
    ...                         query={"unique_id": "test_assert"}
    ...                         assertion_operator===
    ...                         expected_value=${42}
    ...                         field=score
    ...                         alias=first_alias

Verify Check Query Result Honours Retry Timeout
    [Documentation]    The retry loop must give up at the timeout when no document appears.
    [Timeout]    60 seconds
    Run Keyword And Expect Error                     *Query returned no results.*
    ...    Check Query Result
    ...    collection_name=${COLLECTION}
    ...    query={"unique_id": "never_inserted"}
    ...    assertion_operator===
    ...    expected_value=${1}
    ...    field=score
    ...    retry_timeout=1 second
    ...    retry_pause=200 milliseconds
    ...    alias=first_alias

Verify Disconnect From All Databases Releases The Whole Pool
    [Documentation]    Closing every pooled connection must not fail on the Database API.
    ${aliases}                  List Database Connections
    Should Contain              ${aliases}          first_alias
    Should Contain              ${aliases}          second_alias
    Disconnect From All Databases
    ${aliases}                  List Database Connections
    Should Be Empty             ${aliases}
    [Teardown]    Connect Both Databases


*** Keywords ***
Connect Both Databases
    [Documentation]    Connect two aliases pointing at two different databases.
    Connect To Database
    ...                 db_name=${DB_NAME}
    ...                 db_user=${DB_USER}
    ...                 db_password=${DB_PASSWORD}
    ...                 db_host=${DB_HOST}
    ...                 db_port=${DB_PORT}
    ...                 srv=${DB_SRV}
    ...                 alias=first_alias
    # Suffix kept to two characters: Atlas caps database names at 38 bytes.
    Connect To Database
    ...                 db_name=${DB_NAME}_2
    ...                 db_user=${DB_USER}
    ...                 db_password=${DB_PASSWORD}
    ...                 db_host=${DB_HOST}
    ...                 db_port=${DB_PORT}
    ...                 srv=${DB_SRV}
    ...                 alias=second_alias
    Switch Database     alias=first_alias

Cleanup Test Data
    [Documentation]    Remove everything this suite created, then release all connections.
    Delete All Documents From Collection             collection_name=${COLLECTION}    alias=first_alias
    Delete All Documents From Collection             collection_name=${COLLECTION}    alias=second_alias
    Disconnect From All Databases
