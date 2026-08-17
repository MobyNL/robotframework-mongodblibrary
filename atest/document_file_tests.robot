*** Settings ***
Documentation       Acceptance tests for reading documents from files: Load Document and
...                 Insert Document From File.
...
...                 What needs a real server here is what the types do once they are
...                 stored. A document read from a file holds an ObjectId, a datetime, an
...                 int and a double, and the point of reading them as BSON types rather
...                 than as text is that MongoDB then matches and compares them as such.
...                 Only a real server can be asked that: it is the server that answers a
...                 query for a date range or an id, and mongomock reimplements those
...                 answers rather than giving them.
...
...                 Substitution runs here for a different reason. A variable written in a
...                 file is read from the ones the calling suite can see, and that scope
...                 exists only while Robot Framework is running a suite: the unit tests
...                 substitute against a variable scope they build themselves, and this is
...                 where the real one is. The same goes for filling a template's
...                 placeholders from named arguments, and from a dictionary expanded into
...                 them.

Library             Collections
Library             DateTime
Library             MongoDBLibrary    document_path=${CURDIR}/documents
Resource            local.resource

Suite Setup         Connect To Test Database
Suite Teardown      Cleanup Test Data
Test Setup          Delete All Documents From Collection    collection_name=${COLLECTION}


*** Variables ***
${COLLECTION}       test_collection_document_file
${CUSTOMER_ID}      6a7ccdea6abf6a4ebbc3514f
${ORDER_REFERENCE}    REF-1


*** Test Cases ***
Verify A Document Read From A File Is Stored With Its Extended JSON Types
    [Documentation]    The reason the file is Extended JSON: the id is queried as an id
    ...    and the date compares as a date, neither of which text does.
    Insert Document From File    collection_name=${COLLECTION}    path=order.json

    ${customer_id}    Convert To Object Id    ${CUSTOMER_ID}
    ${found}    Find Document    collection_name=${COLLECTION}    customerId=${customer_id}
    Should Be Equal    ${found.unique_id}    test_document_file

    ${from_date}    Evaluate    {"placedAt": {"$gte": datetime.datetime(2026, 2, 1)}}
    ${in_range}    Count Documents With Query    collection_name=${COLLECTION}    query=${from_date}
    Should Be Equal As Integers    ${in_range}    1

    # The same date as text matches nothing, which is what a file that stored it as text
    # would have produced.
    ${as_text}    Count Documents With Query
    ...    collection_name=${COLLECTION}
    ...    query={"placedAt": "2026-03-01T09:30:00Z"}
    Should Be Equal As Integers    ${as_text}    0

Verify A Variable In A File Is Read From The Calling Suite
    [Documentation]    ${ORDER_REFERENCE} in the file resolves to what this suite defines.
    ${document}    Load Document    order.json
    Should Be Equal    ${document.reference}    REF-1

    ${overridden}    Load Document    order.json    reference=REF-2
    Should Be Equal    ${overridden.reference}    REF-2

Verify Overrides Reach A Nested Field And A List Position
    [Documentation]    The one thing a suite cannot do for itself: dictionary expansion
    ...    merges one level deep, so a nested field means rebuilding every level above it.
    ${document}    Load Document    order.json
    ...    status=shipped
    ...    customer.address.city=Amsterdam
    ...    lines.0.quantity=5
    Should Be Equal    ${document.status}                    shipped
    Should Be Equal    ${document.customer.address.city}     Amsterdam
    Should Be Equal    ${document.customer.name}             A
    Should Be Equal As Integers    ${document.lines}[0][quantity]    5
    Should Be Equal As Integers    ${document.lines}[1][quantity]    1

Verify An Override Is Stored As The Type It Looks Like
    [Documentation]    A number written literally is stored as a number, so it compares as one.
    Insert Document From File    collection_name=${COLLECTION}    path=order.json    total=99.95

    ${count}    Count Documents With Query
    ...    collection_name=${COLLECTION}
    ...    query={"total": {"$gt": 99}}
    Should Be Equal As Integers    ${count}    1

Verify An Update Document Can Be Read From A File
    [Documentation]    Update operators are $-prefixed too, and are passed through as they are.
    Insert Document From File    collection_name=${COLLECTION}    path=order.json

    ${update}    Load Document    ship.json    $set.status=shipped
    Update Document With Operators
    ...    collection_name=${COLLECTION}
    ...    query={"unique_id": "test_document_file"}
    ...    update=${update}

    ${found}    Find Document    collection_name=${COLLECTION}    unique_id=test_document_file
    Should Be Equal    ${found.status}    shipped
    Should Contain     ${found.events}    shipped
    ${shipped}    Count Documents With Query
    ...    collection_name=${COLLECTION}
    ...    query={"shippedAt": {"$type": "date"}}
    Should Be Equal As Integers    ${shipped}    1

Verify A Template Seeds A Different Document On Every Call
    [Documentation]    The reason placeholders exist: one file, a document per call, with no
    ...    dictionary built in the suite and no suite variable per value.
    ${customer_id}    Convert To Object Id    ${CUSTOMER_ID}
    ${placed_at}      Convert Date    2026-03-01 09:30:00    datetime

    FOR    ${unique_id}    IN    dynamic_1    dynamic_2
        Insert Document From File
        ...    collection_name=${COLLECTION}
        ...    path=dynamic_order.json
        ...    unique_id=${unique_id}
        ...    customerId=${customer_id}
        ...    placed_at=${placed_at}
        ...    quantity=3
    END

    ${both}    Count Documents    collection_name=${COLLECTION}    customerId=${customer_id}
    Should Be Equal As Integers    ${both}    2

    ${found}    Find Document    collection_name=${COLLECTION}    unique_id=dynamic_2
    Should Be Equal    ${found.reference}    REF-dynamic_2

Verify A Filled Placeholder Is Stored As The Type Of The Value Given
    [Documentation]    What the whole-string rule buys: the template stays valid JSON and
    ...    still carries an ObjectId, a date and a number rather than text.
    ${customer_id}    Convert To Object Id    ${CUSTOMER_ID}
    ${placed_at}      Convert Date    2026-03-01 09:30:00    datetime
    Insert Document From File
    ...    collection_name=${COLLECTION}
    ...    path=dynamic_order.json
    ...    unique_id=dynamic_types
    ...    customerId=${customer_id}
    ...    placed_at=${placed_at}
    ...    quantity=3

    ${typed}    Evaluate
    ...    {"customerId": {"$type": "objectId"}, "placedAt": {"$type": "date"}, "quantity": {"$type": "int"}}
    ${count}    Count Documents With Query    collection_name=${COLLECTION}    query=${typed}
    Should Be Equal As Integers    ${count}    1

    ${in_range}    Evaluate    {"placedAt": {"$gte": datetime.datetime(2026, 2, 1)}}
    ${matched}     Count Documents With Query    collection_name=${COLLECTION}    query=${in_range}
    Should Be Equal As Integers    ${matched}    1

Verify A Dictionary Can Be Expanded Into The Placeholder Values
    [Documentation]    Robot Framework maps a dictionary into named arguments, so a suite
    ...    that already holds one passes it as it is. An empty one fills nothing.
    VAR    &{placeholders}
    ...    unique_id=dynamic_expanded
    ...    customerId=${CUSTOMER_ID}
    ...    placed_at=2026-03-01T09:30:00Z
    ...    quantity=1
    ${document}    Load Document    dynamic_order.json    &{placeholders}
    Should Be Equal    ${document.unique_id}    dynamic_expanded

    ${unchanged}    Load Document    order.json    &{EMPTY}
    Should Be Equal    ${unchanged.status}    new

Verify Placeholders And Overrides Can Be Given In One Call
    [Documentation]    A hole the file declares is filled; anything else is a path into it.
    ${document}    Load Document    dynamic_order.json
    ...    unique_id=dynamic_mixed
    ...    customerId=${CUSTOMER_ID}
    ...    placed_at=2026-03-01T09:30:00Z
    ...    quantity=1
    ...    status=shipped
    ...    lines.0.quantity=9
    Should Be Equal    ${document.unique_id}    dynamic_mixed
    Should Be Equal    ${document.status}       shipped
    Should Be Equal As Integers    ${document.lines}[0][quantity]    9

Verify An Unfilled Placeholder Fails Instead Of Being Stored As Text
    [Documentation]    The literal text a placeholder is written as inserts perfectly well,
    ...    so leaving it would seed a document that looks almost right.
    Run Keyword And Expect Error    *dynamic_order.json*declares*customerId*quantity*
    ...    Load Document    dynamic_order.json    unique_id=dynamic_unfilled    placed_at=x
    ${count}    Count Documents    collection_name=${COLLECTION}
    Should Be Equal As Integers    ${count}    0

Verify An Argument That Is Neither A Placeholder Nor A Field Names Both
    [Documentation]    Which one was meant decides whether the fix is in the file or the call.
    Run Keyword And Expect Error    *'stauts' is neither*Placeholders*Fields*
    ...    Load Document    dynamic_order.json
    ...    unique_id=dynamic_typo
    ...    customerId=${CUSTOMER_ID}
    ...    placed_at=2026-03-01T09:30:00Z
    ...    quantity=1
    ...    stauts=shipped

Verify An Override Path That Is Not In The Document Fails
    [Documentation]    A path that misses is a typo, so it fails with what was there instead
    ...    of quietly adding a field alongside the one that was meant.
    Run Keyword And Expect Error    *'nmae' is not in 'customer'*Available: name, address*
    ...    Load Document    order.json    customer.nmae=A
    Run Keyword And Expect Error    *'lines' holds 2 items*index 9 is out of range*
    ...    Load Document    order.json    lines.9.quantity=1

Verify A Missing Document File Names Where It Looked
    [Documentation]    Reported here rather than as a failure to parse nothing.
    Run Keyword And Expect Error    *missing.json*${CURDIR}${/}documents*
    ...    Load Document    missing.json


*** Keywords ***
Connect To Test Database
    [Documentation]    Connect using a host and credentials.
    Connect To Database
    ...    db_name=${DB_NAME}
    ...    db_user=${DB_USER}
    ...    db_password=${DB_PASSWORD}
    ...    db_host=${DB_HOST}
    ...    db_port=${DB_PORT}
    ...    srv=${DB_SRV}

Cleanup Test Data
    [Documentation]    Remove the collection this suite wrote to, then release the connection.
    Drop Collection    collection_name=${COLLECTION}
    Disconnect From All Databases
