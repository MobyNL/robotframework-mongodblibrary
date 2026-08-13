*** Settings ***
Documentation       Acceptance tests for the keywords whose purpose is MongoDB query and
...                 update operators, and for sorting.
...
...                 These need a real server. Their only other coverage is the unit suite,
...                 which runs against mongomock — a reimplementation of the query
...                 language rather than the query language itself. Somewhere for
...                 ``$gte``, ``$in``, ``$regex``, ``$inc`` and ``$push`` to be answered
...                 by MongoDB is exactly what these keywords need and had nowhere else.

Library             Collections
Library             MongoDBLibrary
Resource            local.resource

Suite Setup         Connect And Prepare Test Data
Suite Teardown      Cleanup Test Data
Test Setup          Reset The Scored Documents


*** Variables ***
${COLLECTION}       test_collection_operators


*** Test Cases ***
Verify Find Documents With Query Uses Comparison Operators
    [Documentation]    The reason this keyword exists: a query key=value cannot express.
    ${documents}    Find Documents With Query
    ...    collection_name=${COLLECTION}
    ...    query={"score": {"$gte": 5}}
    ...    sort={"score": 1}
    ${scores}       Get Scores    ${documents}
    Should Be Equal    ${scores}    ${{ [5, 10] }}

Verify Find Documents With Query Uses An In Operator
    [Documentation]    $in over a list of values.
    ${documents}    Find Documents With Query
    ...    collection_name=${COLLECTION}
    ...    query={"name": {"$in": ["alpha", "gamma"]}}
    ...    sort={"score": 1}
    ${scores}       Get Scores    ${documents}
    Should Be Equal    ${scores}    ${{ [1, 10] }}

Verify Find Documents With Query Uses A Regular Expression
    [Documentation]    $regex is matched by the server, not by Python.
    ${documents}    Find Documents With Query
    ...    collection_name=${COLLECTION}
    ...    query={"name": {"$regex": "^a"}}
    ${scores}       Get Scores    ${documents}
    Should Be Equal    ${scores}    ${{ [1] }}

Verify Find Document With Query Returns The First In Sort Order
    [Documentation]    Sorting decides which single document comes back.
    ${highest}      Find Document With Query
    ...    collection_name=${COLLECTION}
    ...    query={}
    ...    sort={"score": -1}
    Should Be Equal As Integers    ${highest.score}    10
    ${lowest}       Find Document With Query
    ...    collection_name=${COLLECTION}
    ...    query={}
    ...    sort={"score": 1}
    Should Be Equal As Integers    ${lowest.score}    1

Verify Find Documents Sorts And Projects
    [Documentation]    Sorting and projection over the free-argument find keyword.
    ${documents}    Find Documents
    ...    collection_name=${COLLECTION}
    ...    sort={"score": -1}
    ...    projection={"score": 1}
    ${scores}       Get Scores    ${documents}
    Should Be Equal    ${scores}    ${{ [10, 5, 1] }}
    Dictionary Should Not Contain Key    ${documents}[0]    name

Verify Find Documents Limits And Skips
    [Documentation]    Paging over a sorted result.
    ${documents}    Find Documents
    ...    collection_name=${COLLECTION}
    ...    sort={"score": 1}
    ...    limit=${1}
    ...    skip=${1}
    ${scores}       Get Scores    ${documents}
    Should Be Equal    ${scores}    ${{ [5] }}

Verify Count Documents With Query Uses Operators
    [Documentation]    Counting with an operator the free arguments cannot express.
    ${count}        Count Documents With Query
    ...    collection_name=${COLLECTION}
    ...    query={"score": {"$gte": 5}}
    Should Be Equal As Integers    ${count}    2

Verify Count Documents Limits And Skips
    [Documentation]    A limit answers "are there at least N" without counting everything.
    ${count}        Count Documents    collection_name=${COLLECTION}    limit=${2}
    Should Be Equal As Integers    ${count}    2
    ${count}        Count Documents    collection_name=${COLLECTION}    skip=${1}
    Should Be Equal As Integers    ${count}    2

Verify Get Estimated Document Count Sees The Whole Collection
    [Documentation]    Metadata rather than a query, so it takes no filter.
    ${count}        Get Estimated Document Count    collection_name=${COLLECTION}
    Should Be Equal As Integers    ${count}    3

Verify Update Documents Changes Every Match
    [Documentation]    The bulk update keyword, reporting how many documents changed.
    ${changed}      Update Documents
    ...    collection_name=${COLLECTION}
    ...    query={"score": {"$gte": 5}}
    ...    update={"checked": True}
    Should Be Equal As Integers    ${changed}    2
    ${count}        Count Documents    collection_name=${COLLECTION}    checked=${True}
    Should Be Equal As Integers    ${count}    2

Verify Update Documents With Operators Increments Every Match
    [Documentation]    $inc against a real server, over every matching document.
    ${changed}      Update Documents With Operators
    ...    collection_name=${COLLECTION}
    ...    query={"score": {"$gte": 5}}
    ...    update={"$inc": {"score": 100}}
    Should Be Equal As Integers    ${changed}    2
    ${documents}    Find Documents    collection_name=${COLLECTION}    sort={"score": 1}
    ${scores}       Get Scores    ${documents}
    Should Be Equal    ${scores}    ${{ [1, 105, 110] }}

Verify Update Document With Operators Pushes Onto An Array
    [Documentation]    $push, which no amount of $set can express.
    ${updated}      Update Document With Operators
    ...    collection_name=${COLLECTION}
    ...    query={"name": "alpha"}
    ...    update={"$push": {"tags": "added"}}
    Should Be Equal    ${updated.tags}    ${{ ['first', 'added'] }}

Verify Update Documents Upserts When Nothing Matches
    [Documentation]    The bulk keywords report 0, because an upsert inserts rather than changes.
    ${changed}      Update Documents
    ...    collection_name=${COLLECTION}
    ...    query={"name": "absent"}
    ...    update={"score": ${99}}
    ...    upsert=${True}
    Should Be Equal As Integers    ${changed}    0
    ${count}        Count Documents    collection_name=${COLLECTION}    name=absent
    Should Be Equal As Integers    ${count}    1

Verify Delete Document Deletes Only One
    [Documentation]    The singular delete, against a query matching more than one document.
    ${deleted}      Delete Document    collection_name=${COLLECTION}    tags=first
    Should Be Equal As Integers    ${deleted}    1
    ${count}        Count Documents    collection_name=${COLLECTION}
    Should Be Equal As Integers    ${count}    2

Verify Delete Documents With Query Uses Operators
    [Documentation]    Deleting a range, which the free arguments cannot express.
    ${deleted}      Delete Documents With Query
    ...    collection_name=${COLLECTION}
    ...    query={"score": {"$gte": 5}}
    Should Be Equal As Integers    ${deleted}    2
    ${count}        Count Documents    collection_name=${COLLECTION}
    Should Be Equal As Integers    ${count}    1

Verify A Document Is Found By Its Id Inside An In Operator
    [Documentation]    Ids that have been through a Robot variable are strings, and the
    ...    coercion has to reach inside $in as well as a bare _id.
    ${documents}    Find Documents    collection_name=${COLLECTION}    sort={"score": 1}
    ${low}          Convert To String    ${documents}[0][_id]
    ${high}         Convert To String    ${documents}[2][_id]
    ${found}        Find Documents With Query
    ...    collection_name=${COLLECTION}
    ...    query={"_id": {"$in": ["${low}", "${high}"]}}
    ...    sort={"score": 1}
    ${scores}       Get Scores    ${found}
    Should Be Equal    ${scores}    ${{ [1, 10] }}

Verify Check Distinct Values Asserts The Whole Collection At Once
    [Documentation]    Including the question counting cannot express: nothing is in this state.
    Check Distinct Values
    ...    collection_name=${COLLECTION}
    ...    field=name
    ...    assertion_operator= ==
    ...    expected_value=${{ ['alpha', 'beta', 'gamma'] }}
    Check Distinct Values
    ...    collection_name=${COLLECTION}
    ...    field=name
    ...    assertion_operator=not contains
    ...    expected_value=delta

Verify Check Distinct Values Narrows With A Query
    [Documentation]    The query restricts which documents contribute a value.
    Check Distinct Values
    ...    collection_name=${COLLECTION}
    ...    field=name
    ...    assertion_operator= ==
    ...    expected_value=${{ ['gamma'] }}
    ...    query={"score": {"$gte": 10}}

Verify Check Distinct Values Honours Retry Timeout
    [Documentation]    The retry loop must give up at the timeout rather than hang.
    [Timeout]    60 seconds
    Run Keyword And Expect Error    *Wrong distinct values for field 'name':*
    ...    Check Distinct Values
    ...    collection_name=${COLLECTION}
    ...    field=name
    ...    assertion_operator= ==
    ...    expected_value=${{ ['never'] }}
    ...    retry_timeout=1 second
    ...    retry_pause=200 milliseconds

Verify A String Id That Is Not An Object Id Is Left Alone
    [Documentation]    Coercion is on, but a collection keyed by ordinary strings has to
    ...    keep working. Only a value that is a valid ObjectId is ever rewritten.
    Insert Document
    ...    collection_name=${COLLECTION}
    ...    document={"_id": "order-991", "name": "delta", "score": 0}
    ${found}        Find Document    collection_name=${COLLECTION}    _id=order-991
    Should Be Equal    ${found.name}    delta

Verify Create Index With A Partial Filter Expression
    [Documentation]    The index covers only the documents matching the expression, which
    ...    shows up in the index metadata the server reports back.
    Create Index
    ...    collection_name=${COLLECTION}
    ...    keys={"name": 1}
    ...    index_name=by_name_partial
    ...    partial_filter_expression={"score": {"$gte": 5}}
    ${indexes}      Get Index Information    collection_name=${COLLECTION}
    Should Be Equal    ${indexes}[by_name_partial][partialFilterExpression]    ${{ {'score': {'$gte': 5}} }}

Verify Document Should Exist Reports The Query It Could Not Match
    [Documentation]    The failure message has to say what was looked for.
    Run Keyword And Expect Error    *No document in '${COLLECTION}' matches*
    ...    Document Should Exist    collection_name=${COLLECTION}    name=never_inserted

Verify Document Should Not Exist Reports How Many It Found
    [Documentation]    Knowing the count is what makes the failure actionable.
    Run Keyword And Expect Error    *but found 1*
    ...    Document Should Not Exist    collection_name=${COLLECTION}    name=alpha

Verify Check Query Result Reports A Field The Document Does Not Have
    [Documentation]    A missing field is a different failure from a wrong value.
    Run Keyword And Expect Error    *Field 'absent_field' not found in document.*
    ...    Check Query Result
    ...    collection_name=${COLLECTION}
    ...    query={"name": "alpha"}
    ...    assertion_operator= ==
    ...    expected_value=${1}
    ...    field=absent_field

Verify Execute Query Rejects A Pipeline That Is Not A List
    [Documentation]    An aggregation pipeline is a list of stages. From a suite it is
    ...    Robot Framework's own argument conversion that rejects a document, before the
    ...    keyword runs at all; the library's matching check catches a caller in Python.
    ...    The pattern is loose because either layer may be the one to answer.
    Run Keyword And Expect Error    *pipeline*list*
    ...    Execute Query    collection_name=${COLLECTION}    pipeline={"$match": {}}

Verify List Indexes And Drop Index
    [Documentation]    The index keywords that report raw definitions and remove one by name.
    Create Index    collection_name=${COLLECTION}    keys={"name": 1}    index_name=by_name
    ${indexes}      List Indexes    collection_name=${COLLECTION}
    ${names}        Evaluate    [index["name"] for index in $indexes]
    Should Contain    ${names}    by_name
    Drop Index      collection_name=${COLLECTION}    index_name=by_name
    ${indexes}      List Indexes    collection_name=${COLLECTION}
    ${names}        Evaluate    [index["name"] for index in $indexes]
    Should Not Contain    ${names}    by_name


*** Keywords ***
Connect And Prepare Test Data
    [Documentation]    Connect using a host and credentials, then create the collection.
    Connect To Database
    ...    db_name=${DB_NAME}
    ...    db_user=${DB_USER}
    ...    db_password=${DB_PASSWORD}
    ...    db_host=${DB_HOST}
    ...    db_port=${DB_PORT}
    ...    srv=${DB_SRV}

Reset The Scored Documents
    [Documentation]    Three documents with scores 1, 5 and 10, rebuilt before every test.
    ...
    ...    Rebuilding rather than sharing means a test that updates or deletes cannot
    ...    change what the next one sees, so the tests can be read in any order.
    Drop Collection    collection_name=${COLLECTION}
    Insert Documents
    ...    collection_name=${COLLECTION}
    ...    documents=[{"name": "alpha", "score": 1, "tags": ["first"]}, {"name": "beta", "score": 5}, {"name": "gamma", "score": 10}]

Get Scores
    [Documentation]    The score of every document, in the order given.
    [Arguments]    ${documents}
    ${scores}    Evaluate    [document["score"] for document in $documents]
    RETURN    ${scores}

Cleanup Test Data
    [Documentation]    Remove the collection this suite created, then release the connection.
    Drop Collection    collection_name=${COLLECTION}
    Disconnect From All Databases
