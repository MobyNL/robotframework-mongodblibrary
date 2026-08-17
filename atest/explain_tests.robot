*** Settings ***
Documentation       Acceptance tests for `Explain Query` and `Collection Should Have Index`.
...
...                 These need a real server more than any other suite here. What the
...                 explain keyword contributes is reading a plan document that only
...                 MongoDB produces — mongomock has no ``explain`` at all — and the
...                 collection this suite builds is the shape that motivated both
...                 keywords: an ``_id`` that is a compound subdocument, queried by
...                 dotted path.

Library             Collections
Library             MongoDBLibrary
Resource            local.resource

Suite Setup         Connect And Seed The Readings Collection
Suite Teardown      Cleanup Test Data


*** Variables ***
${COLLECTION}       test_collection_explain
${INDEX_NAME}       _id.deviceId_1__id.date_1


*** Test Cases ***
Verify Explain Query Reports The Index A Dotted Query Uses
    [Documentation]    The motivating query. A dotted path cannot use the automatic
    ...    ``_id_`` index, which stores the subdocument as one opaque value, so this is
    ...    answered by the secondary index the setup creates and by nothing else.
    ${plan}             Explain The Dotted Query
    Should Be Equal     ${plan.collection_scan}                     ${False}
    Should Be Equal     ${plan.index_name}      ${INDEX_NAME}
    Should Be Equal As Integers                 ${plan.returned}    1
    Should Be Equal As Integers                 ${plan.docs_examined}                   1

Verify Explain Query Reports The Values It Searched For
    [Documentation]    The field the keyword exists for: what the server looked for, as it
    ...    understood it. A query matching nothing without erroring is diagnosed here.
    ${plan}                 Explain The Dotted Query
    Dictionary Should Contain Key                   ${plan.index_bounds}    _id.date
    Should Not Be Empty     ${plan.index_bounds}[_id.date]

Verify Explain Query Flags A Collection Scan
    [Documentation]    A field no index covers is read by scanning the collection. Reported
    ...    as information only — the library deliberately has no assertion for it, because
    ...    MongoDB rightly chooses a scan on small collections.
    ${plan}             Explain Query           collection_name=${COLLECTION}       reading=${3}
    Should Be Equal     ${plan.collection_scan}             ${True}
    Should Be Equal     ${plan.index_name}      ${None}
    Should Be True      ${plan.docs_examined} > 1

Verify Explain Query Shows Why A Reversed Id Matches Nothing
    [Documentation]    Subdocument equality compares the BSON as stored, so the field order
    ...    is part of the value. Reversed, the query matches nothing and reports no error;
    ...    the explain says it searched and returned none, which is the visible difference.
    ${date}             Get The Seeded Date
    ${matching}         Explain Query
    ...                 collection_name=${COLLECTION}
    ...                 query=${{ {"_id": {"deviceId": "device-1", "date": $date}} }}
    ${reversed}         Explain Query
    ...                 collection_name=${COLLECTION}
    ...                 query=${{ {"_id": {"date": $date, "deviceId": "device-1"}} }}
    Should Be Equal As Integers                 ${matching.returned}    1
    Should Be Equal As Integers                 ${reversed.returned}    0
    ${document}         Find Document With Query
    ...                 collection_name=${COLLECTION}
    ...                 query=${{ {"_id": {"date": $date, "deviceId": "device-1"}} }}
    Should Be Equal     ${document}             ${None}

Verify Explain Query Takes The Query Either Way
    [Documentation]    Both find keywords' argument shapes explain the same query, so an
    ...    explain can be dropped in beside either without rewriting the call.
    ${date}             Get The Seeded Date
    ${by_params}        Explain Query
    ...                 collection_name=${COLLECTION}
    ...                 _id.deviceId=device-1
    ...                 _id.date=${date}
    ${by_query}         Explain Query
    ...                 collection_name=${COLLECTION}
    ...                 query=${{ {"_id.deviceId": "device-1", "_id.date": $date} }}
    Should Be Equal     ${by_params.index_name}                         ${by_query.index_name}
    Should Be Equal As Integers                 ${by_params.returned}                           ${by_query.returned}

Verify Explain Query Refuses Both Query Forms At Once
    [Documentation]    Merging them would hide a typo, and which was meant decides the fix.
    Run Keyword And Expect Error                    *not both*
    ...     Explain Query       collection_name=${COLLECTION}           query={"reading": 3}                    reading=${3}

Verify Explain Query Can Plan Without Running The Query
    [Documentation]    ``queryPlanner`` verbosity picks a plan and stops, so the counters
    ...    are empty rather than zero. Not an error: nothing was executed to count.
    ${plan}             Explain Query
    ...                 collection_name=${COLLECTION}
    ...                 reading=${3}
    ...                 verbosity=queryPlanner
    Should Be Equal     ${plan.collection_scan}         ${True}
    Should Be Equal     ${plan.keys_examined}           ${None}
    Should Be Equal     ${plan.docs_examined}           ${None}
    Should Be Equal     ${plan.returned}    ${None}

Verify Explain Query Returns The Server's Own Explain
    [Documentation]    The escape hatch: anything the summary leaves out is still reachable.
    ${plan}     Explain The Dotted Query
    Dictionary Should Contain Key       ${plan.raw}             queryPlanner
    Dictionary Should Contain Key       ${plan.raw}             executionStats

Verify Collection Should Have Index Passes For The Index That Exists
    [Documentation]    Asked by fields, so the derived name never has to be written out.
    Collection Should Have Index
    ...     collection_name=${COLLECTION}
    ...     keys={"_id.deviceId": 1, "_id.date": 1}

Verify Collection Should Have Index Reports Which Indexes Are There
    [Documentation]    The failure has to say what the collection does have, or the next
    ...    step is another round of looking.
    Run Keyword And Expect Error    *No index on '${COLLECTION}' has keys*It has:*${INDEX_NAME}*
    ...     Collection Should Have Index    collection_name=${COLLECTION}           keys={"status": 1}

Verify Collection Should Have Index Is Field Order Sensitive
    [Documentation]    A compound index serves its fields left to right, so the same fields
    ...    in the other order are a different index and cannot answer the same queries.
    Run Keyword And Expect Error    *No index on '${COLLECTION}' has keys*
    ...     Collection Should Have Index    collection_name=${COLLECTION}           keys={"_id.date": 1, "_id.deviceId": 1}


*** Keywords ***
Cleanup Test Data
    [Documentation]    Remove the collection this suite created, then release the connection.
    Drop Collection     collection_name=${COLLECTION}
    Disconnect From All Databases

Connect And Seed The Readings Collection
    [Documentation]    Connect, then build a collection keyed by a compound ``_id``.
    ...
    ...    Two hundred documents, which is enough for a collection scan to read visibly
    ...    more than an index lookup does. The secondary index is the load-bearing one:
    ...    without it every dotted query below scans.
    Connect To Database
    ...                     db_name=${DB_NAME}
    ...                     db_user=${DB_USER}
    ...                     db_password=${DB_PASSWORD}
    ...                     db_host=${DB_HOST}
    ...                     db_port=${DB_PORT}
    ...                     srv=${DB_SRV}
    Drop Collection         collection_name=${COLLECTION}
    ${start}                Evaluate                datetime.datetime(2026, 1, 1)                   modules=datetime
    ${day}                  Evaluate                datetime.timedelta(days=1)                      modules=datetime
    ${documents}    Evaluate
    ...    [{"_id": {"deviceId": f"device-{u}", "date": $start + $day * d}, "reading": u + d} for u in range(20) for d in range(10)]
    Insert Documents        collection_name=${COLLECTION}                   documents=${documents}
    Create Index            collection_name=${COLLECTION}                   keys={"_id.deviceId": 1, "_id.date": 1}

Explain The Dotted Query
    [Documentation]    The query that motivated these keywords, explained.
    ${date}     Get The Seeded Date
    ${plan}     Explain Query
    ...         collection_name=${COLLECTION}
    ...         _id.deviceId=device-1
    ...         _id.date=${date}
    RETURN      ${plan}

Get The Seeded Date
    [Documentation]    The date every ``device-1`` assertion below matches on.
    ${date}     Evaluate    datetime.datetime(2026, 1, 8)       modules=datetime
    RETURN      ${date}
