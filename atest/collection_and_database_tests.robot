*** Settings ***
Documentation       Acceptance tests for the keywords that act on a collection, a database
...                 or the server rather than on documents. These need a real server:
...                 collection options, index metadata and database commands are all
...                 things an in-memory stand-in either refuses or invents.

Library             Collections
Library             MongoDBLibrary
Resource            local.resource

Suite Setup         Connect To Test Database
Suite Teardown      Cleanup Test Data


*** Variables ***
${COLLECTION}           test_collection_admin
# Created and dropped by this suite alone, so dropping it takes nothing else with it.
# Suffix kept short: Atlas caps database names at 38 bytes.
${SCRATCH_DB}           ${DB_NAME}_d


*** Test Cases ***
Verify List Collections Reports What Has Been Written To
    [Documentation]    A collection appears once something is written to it.
    Insert Document             collection_name=${COLLECTION}    document={"unique_id": "test_list"}
    ${collections}              List Collections
    Should Contain              ${collections}    ${COLLECTION}

Verify Create Collection Makes It Exist Before Anything Is Written
    [Documentation]    Explicit creation, which is the only way to get a collection with no documents.
    Drop Collection             collection_name=test_collection_created
    Create Collection           collection_name=test_collection_created
    Check Collection Exists     collection_name=test_collection_created
    ${count}                    Count Documents    collection_name=test_collection_created
    Should Be Equal As Integers                    ${count}    0
    [Teardown]    Drop Collection                  collection_name=test_collection_created

Verify Create Collection Refuses One That Already Exists
    [Documentation]    Which makes it a check as well as a setup step.
    Create Collection           collection_name=test_collection_twice
    Run Keyword And Expect Error                   *already exists*
    ...    Create Collection    collection_name=test_collection_twice
    [Teardown]    Drop Collection                  collection_name=test_collection_twice

Verify Create Collection Applies A Capped Size
    [Documentation]    A collection option no implicit creation can give, so it proves the options reach the server.
    Drop Collection             collection_name=test_collection_capped
    Create Collection           collection_name=test_collection_capped    capped=${True}    size=${4096}
    ${options}                  Run Database Command
    ...    command={"listCollections": 1, "filter": {"name": "test_collection_capped"}}
    VAR    ${first}             ${options}[cursor][firstBatch][0]
    Should Be True              ${first}[options][capped]
    [Teardown]    Drop Collection                  collection_name=test_collection_capped

Verify Drop Collection Takes The Indexes With It
    [Documentation]    The difference from emptying a collection, which leaves a unique index in place.
    Drop Collection             collection_name=test_collection_dropped
    Insert Document             collection_name=test_collection_dropped    document={"email": "a@example.test"}
    Create Index                collection_name=test_collection_dropped    keys={"email": 1}    unique=${True}
    Drop Collection             collection_name=test_collection_dropped
    Insert Document             collection_name=test_collection_dropped    document={"email": "a@example.test"}
    Insert Document             collection_name=test_collection_dropped    document={"email": "a@example.test"}
    ${count}                    Count Documents    collection_name=test_collection_dropped
    Should Be Equal As Integers                    ${count}    2
    [Teardown]    Drop Collection                  collection_name=test_collection_dropped

Verify Dropping A Collection That Is Not There Succeeds
    [Documentation]    So a teardown after a failed setup does not fail in turn.
    Drop Collection             collection_name=test_collection_never_created

Verify Index Information And Dropping Every Index
    [Documentation]    Index metadata as a dictionary, and resetting a collection's indexes.
    Insert Document             collection_name=${COLLECTION}    document={"email": "a@example.test"}
    Create Index                collection_name=${COLLECTION}    keys={"email": 1}    index_name=by_email
    Check Index Exists          collection_name=${COLLECTION}    index_name=by_email
    ${indexes}                  Get Index Information             collection_name=${COLLECTION}
    Dictionary Should Contain Key                  ${indexes}    by_email
    Drop All Indexes            collection_name=${COLLECTION}
    ${indexes}                  Get Index Information             collection_name=${COLLECTION}
    Should Be Equal             ${{ sorted($indexes) }}           ${{ ['_id_'] }}

Verify A Sparse Unique Index Allows Documents Without The Field
    [Documentation]    Without sparse, a second document missing the field is a duplicate null.
    Drop Collection             collection_name=test_collection_sparse
    Create Index
    ...    collection_name=test_collection_sparse
    ...    keys={"email": 1}
    ...    unique=${True}
    ...    sparse=${True}
    Insert Documents            collection_name=test_collection_sparse    documents=[{"a": 1}, {"a": 2}]
    ${count}                    Count Documents    collection_name=test_collection_sparse
    Should Be Equal As Integers                    ${count}    2
    [Teardown]    Drop Collection                  collection_name=test_collection_sparse

Verify Create Index Sets A Time To Live
    [Documentation]    The TTL must reach the server, where it shows up in the index metadata.
    Drop Collection             collection_name=test_collection_ttl
    Create Index
    ...    collection_name=test_collection_ttl
    ...    keys={"created": 1}
    ...    index_name=by_created
    ...    expire_after_seconds=${3600}
    ${indexes}                  Get Index Information             collection_name=test_collection_ttl
    Should Be Equal As Integers                    ${indexes}[by_created][expireAfterSeconds]    3600
    [Teardown]    Drop Collection                  collection_name=test_collection_ttl

Verify Check Collection Exists Fails For A Collection That Is Not There
    [Documentation]    The failure names the collection and lists what the database does hold.
    Run Keyword And Expect Error                   *Collection 'absent_collection' does not exist*
    ...    Check Collection Exists                 collection_name=absent_collection

Verify Check Index Exists Fails For An Index That Is Not There
    [Documentation]    The failure lists the indexes the collection does have.
    Insert Document             collection_name=${COLLECTION}    document={"unique_id": "test_index_missing"}
    Run Keyword And Expect Error                   *Index 'absent_index' does not exist*
    ...    Check Index Exists    collection_name=${COLLECTION}    index_name=absent_index

Verify List Databases Includes The Connected One
    [Documentation]    The connection selects the server, so the list covers every database on it.
    Insert Document             collection_name=${COLLECTION}    document={"unique_id": "test_list_db"}
    ${databases}                List Databases
    Should Contain              ${databases}    ${DB_NAME}

Verify Drop Database Removes Its Data And Leaves The Connection Usable
    [Documentation]    MongoDB recreates the database on the next write, so the alias keeps working.
    Connect To Test Database    alias=scratch_alias    db_name=${SCRATCH_DB}
    Insert Document             collection_name=${COLLECTION}    document={"unique_id": "test_drop_db"}    alias=scratch_alias
    Drop Database               db_name=${SCRATCH_DB}    alias=scratch_alias
    ${count}                    Count Documents    collection_name=${COLLECTION}    alias=scratch_alias
    Should Be Equal As Integers                    ${count}    0
    Insert Document             collection_name=${COLLECTION}    document={"unique_id": "test_after_drop"}    alias=scratch_alias
    ${count}                    Count Documents    collection_name=${COLLECTION}    alias=scratch_alias
    Should Be Equal As Integers                    ${count}    1
    [Teardown]    Run Keywords
    ...    Drop Database        db_name=${SCRATCH_DB}    alias=scratch_alias
    ...    AND    Disconnect From Database          alias=scratch_alias

Verify Get Server Info Reports A Version
    [Documentation]    Used to skip a test the server is too old to support.
    ${info}                     Get Server Info
    Should Not Be Empty         ${info.version}
    Should Be True              ${info.versionArray}[0] > 0

Verify Run Database Command Reaches What The Library Does Not Wrap
    [Documentation]    The escape hatch, over a command with no keyword of its own.
    ${reply}                    Run Database Command    command=ping
    Should Be Equal As Numbers                     ${reply.ok}    1
    ${stats}                    Run Database Command    command={"dbStats": 1}
    Should Be Equal             ${stats}[db]    ${DB_NAME}

Verify Run Database Command Reports A Command Document It Cannot Read
    [Documentation]    A value that opens like a document but is not one must be reported
    ...    here, not sent to the server as a command name and rejected as unknown.
    Run Keyword And Expect Error    *looks like a document but could not be read*
    ...    Run Database Command      command={"unbalanced": 1
    Run Keyword And Expect Error    *looks like a document but is not one*
    ...    Run Database Command      command={"not", "a", "document"}

Verify Run Database Command Reports A Command The Server Rejects
    [Documentation]    A rejected command must raise rather than return a quiet failure.
    Run Keyword And Expect Error                   *
    ...    Run Database Command                    command=notARealCommand


*** Keywords ***
Connect To Test Database
    [Documentation]    Connect using a host and credentials, optionally under another alias.
    [Arguments]    ${alias}=default    ${db_name}=${DB_NAME}
    Connect To Database
    ...    db_name=${db_name}
    ...    db_user=${DB_USER}
    ...    db_password=${DB_PASSWORD}
    ...    db_host=${DB_HOST}
    ...    db_port=${DB_PORT}
    ...    srv=${DB_SRV}
    ...    alias=${alias}

Cleanup Test Data
    [Documentation]    Remove the collection this suite wrote to, then release all connections.
    Drop Collection             collection_name=${COLLECTION}
    Disconnect From All Databases
