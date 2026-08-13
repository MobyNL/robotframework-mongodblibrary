*** Settings ***
Documentation       Acceptance tests for the optional arguments of Connect To Database.
...
...                 Each of these becomes a pymongo client option under a different name
...                 from the keyword argument, so the only thing that proves the mapping
...                 is a server accepting the connection. A unit test can check the name
...                 the option was given; it cannot check that MongoDB agrees.
...
...                 Coverage here depends on where the suite runs. ``srv`` and ``tls``
...                 need a hosted cluster and are exercised only when ${DB_SRV} is true;
...                 ``direct_connection`` is invalid against a seed list and is exercised
...                 only when it is false. ``replica_set`` needs a replica set and is not
...                 covered by either profile.

Library             MongoDBLibrary
Resource            local.resource

Test Teardown       Disconnect From All Databases


*** Test Cases ***
Verify Connecting With The Password As A Secret
    [Documentation]    A Robot Framework Secret keeps the password out of the log while
    ...    still authenticating. Needs Robot Framework 7.4, which introduced the type.
    ...
    ...    The Secret is built here rather than declared as ${VAR: Secret} %{ENV}, so the
    ...    suite needs no environment variable to run. What is under test is the library
    ...    accepting a Secret and authenticating with it; where the object came from makes
    ...    no difference to that.
    ${secret_password}    Make A Secret    ${DB_PASSWORD}
    Connect With Options    db_password=${secret_password}
    Check If Database Connection Exists
    ${count}    Count Documents    collection_name=test_collection_secret
    Should Be Equal As Integers    ${count}    0

Verify A Secret Password Is Not Written To The Log
    [Documentation]    The reason to use one at all.
    ${secret_password}    Make A Secret    ${DB_PASSWORD}
    Should Be Equal    ${secret_password.__str__()}    <secret>

Verify Connecting With An Explicit Auth Source
    [Documentation]    Needed whenever the user was not created in the database being used.
    ...    Both a hosted cluster and the CI container keep their users in ``admin``.
    Connect With Options    auth_source=admin
    Check If Database Connection Exists

Verify Connecting With An Explicit Auth Mechanism
    [Documentation]    The mechanism the server and driver would otherwise negotiate.
    ...
    ...    Which mechanism works is a property of how the *user* was created, not of the
    ...    server version: a user holding only SCRAM-SHA-1 credentials rejects
    ...    SCRAM-SHA-256 with "bad auth", and Atlas users created some time ago are often
    ...    exactly that. So the mechanism is configured per environment rather than
    ...    assumed, and the test skips where none is given.
    ${mechanism}    Get Variable Value    ${DB_AUTH_MECHANISM}    ${EMPTY}
    Skip If    '${mechanism}' == ''    No auth mechanism configured for this server
    Connect With Options    auth_mechanism=${mechanism}
    Check If Database Connection Exists

Verify Connecting With A Read Preference
    [Documentation]    Accepted against a single server as well as a set, where it decides
    ...    which member reads go to.
    Connect With Options    read_preference=primaryPreferred
    Check If Database Connection Exists

Verify Connecting With TLS Forced On
    [Documentation]    A hosted cluster already requires TLS, so forcing it on changes
    ...    nothing there — but it is the only place the argument can be exercised, since
    ...    forcing TLS against a server that does not offer it simply fails.
    Skip If    not ${DB_SRV}    TLS is only offered by a hosted cluster
    Connect With Options    tls=${True}
    Check If Database Connection Exists

Verify A Port Is Ignored And Reported When Resolving A Seed List
    [Documentation]    A seed list supplies its own ports, so a port given alongside it
    ...    cannot be honoured. Saying so is better than silently ignoring it.
    Skip If    not ${DB_SRV}    A seed list is only resolved for a hosted cluster
    Connect To Database
    ...    db_name=${DB_NAME}
    ...    db_user=${DB_USER}
    ...    db_password=${DB_PASSWORD}
    ...    db_host=${DB_HOST}
    ...    db_port=${27017}
    ...    srv=${True}
    Check If Database Connection Exists

Verify Connecting To A Named Replica Set
    [Documentation]    Naming the set makes the driver discover every member from one host
    ...    and follow elections, rather than talking to that host alone. Needs a server
    ...    that is a replica set and advertises a hostname the runner can resolve.
    # Read with a default rather than directly: a local.resource written before this
    # variable existed does not define it, and an undefined variable is an error rather
    # than an empty string.
    ${replica_set}    Get Variable Value    ${DB_REPLICA_SET}    ${EMPTY}
    Skip If    '${replica_set}' == ''    No replica set name configured for this server
    Connect With Options    replica_set=${replica_set}
    Check If Database Connection Exists

Verify Connecting Directly To One Server
    [Documentation]    Skips topology discovery. Invalid against a DNS seed list, which
    ...    names more than one server, so this runs only for a plain host.
    Skip If    ${DB_SRV}    direct_connection cannot be used with a seed list
    Connect With Options    direct_connection=${True}
    Check If Database Connection Exists

Verify A Read Preference Is Not Shared Between Aliases That Disagree
    [Documentation]    Client reuse is keyed on the connection options, so two aliases
    ...    wanting different preferences must not end up on one client.
    Connect With Options    alias=default_preference
    Connect With Options    alias=secondary_preference    read_preference=primaryPreferred
    ${aliases}    List Database Connections
    Should Contain    ${aliases}    default_preference
    Should Contain    ${aliases}    secondary_preference
    Insert Document
    ...    collection_name=test_collection_connection_options
    ...    document={"unique_id": "test_options"}
    ...    alias=secondary_preference
    ${count}    Count Documents
    ...    collection_name=test_collection_connection_options
    ...    unique_id=test_options
    ...    alias=default_preference
    Should Be Equal As Integers    ${count}    1
    [Teardown]    Run Keywords
    ...    Drop Collection    collection_name=test_collection_connection_options    alias=default_preference
    ...    AND    Disconnect From All Databases

Verify Server Selection Timeout Fails Fast Against An Unreachable Server
    [Documentation]    Without it the keyword waits for pymongo's 30 second default. The
    ...    generous upper bound checks the timeout is honoured, not how quick the host is.
    [Timeout]    60 seconds
    ${start}    Get Time    epoch
    Run Keyword And Expect Error    *
    ...    Connect To Database
    ...    db_name=${DB_NAME}
    ...    db_host=unreachable.invalid
    ...    db_port=${27017}
    ...    server_selection_timeout=2 seconds
    ...    alias=unreachable_alias
    ${elapsed}    Evaluate    int(time.time()) - ${start}
    Should Be True    ${elapsed} < 25    Connecting ignored server_selection_timeout

Verify A Connection String Honours The Server Selection Timeout
    [Documentation]    The same option on the other connect keyword, which builds no URI
    ...    of its own and so passes it separately.
    [Timeout]    60 seconds
    Connect To Database Using Connection String
    ...    db_conn_string=${DB_CONNECT_STRING}
    ...    db_name=${DB_NAME}
    ...    server_selection_timeout=20 seconds
    Check If Database Connection Exists

Verify A Failed Connection Leaves No Alias Behind
    [Documentation]    A client that never answered must not be pooled or cached.
    Run Keyword And Expect Error    *
    ...    Connect To Database
    ...    db_name=${DB_NAME}
    ...    db_host=unreachable.invalid
    ...    db_port=${27017}
    ...    server_selection_timeout=2 seconds
    ...    alias=unreachable_alias
    ${aliases}    List Database Connections
    Should Not Contain    ${aliases}    unreachable_alias


*** Keywords ***
Make A Secret
    [Documentation]    Wrap a value as a Robot Framework Secret, skipping below 7.4.
    [Arguments]    ${value}
    ${version}    Evaluate    robot.version.VERSION    modules=robot
    Skip If    ${{ tuple(int(p) for p in "${version}".split(".")[:2]) < (7, 4) }}
    ...    Secret needs Robot Framework 7.4, this is ${version}
    ${secret}    Evaluate    robot.api.types.Secret($value)    modules=robot.api.types
    RETURN    ${secret}

Connect With Options
    [Documentation]    Connect using a host and credentials plus whatever options are given.
    [Arguments]    ${alias}=default    &{options}
    Connect To Database
    ...    db_name=${DB_NAME}
    ...    db_user=${DB_USER}
    ...    db_password=${DB_PASSWORD}
    ...    db_host=${DB_HOST}
    ...    db_port=${DB_PORT}
    ...    srv=${DB_SRV}
    ...    alias=${alias}
    ...    &{options}
