*** Settings ***
Documentation       ObjectId coercion with the behaviour switched off at import.
...
...                 The library is imported here with coerce_object_ids=${False}, which
...                 is why this suite connects on its own rather than through
...                 resources/crud.resource: that resource imports the library with its
...                 defaults, and two instances would make every keyword ambiguous.
...
...                 Coercion in its default on state is covered by
...                 multi_connection_tests.robot.

Library             MongoDBLibrary    coerce_object_ids=${False}
Resource            local.resource

Suite Setup         Connect Without Coercion
Suite Teardown      Cleanup Test Data


*** Variables ***
${COLLECTION}       test_collection_object_id


*** Test Cases ***
Verify A String Id Is Not Converted When Coercion Is Off
    [Documentation]    With the option off the query is passed through exactly as given,
    ...    so a string id does not match an ObjectId stored in the database.
    ${doc_id}           Insert Document
    ...                 collection_name=${COLLECTION}
    ...                 document={"unique_id": "test_no_coercion"}
    ${as_string}        Convert To String    ${doc_id}
    ${found}            Find Document    collection_name=${COLLECTION}    _id=${as_string}
    Should Be Equal     ${found}    ${None}    A string id must not match while coercion is off

Verify Convert To Object Id Is The Route When Coercion Is Off
    [Documentation]    The documented workaround must actually work.
    ${doc_id}           Insert Document
    ...                 collection_name=${COLLECTION}
    ...                 document={"unique_id": "test_explicit_conversion"}
    ${as_string}        Convert To String    ${doc_id}
    ${oid}              Convert To Object Id    ${as_string}
    ${found}            Find Document    collection_name=${COLLECTION}    _id=${oid}
    Should Be Equal     ${found.unique_id}    test_explicit_conversion


*** Keywords ***
Connect Without Coercion
    [Documentation]    Connect the non-coercing library instance.
    Connect To Database
    ...                 db_name=${DB_NAME}
    ...                 db_user=${DB_USER}
    ...                 db_password=${DB_PASSWORD}
    ...                 db_host=${DB_HOST}
    ...                 db_port=${DB_PORT}
    ...                 srv=${DB_SRV}

Cleanup Test Data
    [Documentation]    Empty the collection and release the connection.
    Delete All Documents From Collection    collection_name=${COLLECTION}
    Disconnect From All Databases
