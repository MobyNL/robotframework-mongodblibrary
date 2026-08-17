"""Unit tests for `Explain Query`.

These run against the ``mock_db`` MagicMock rather than mongomock, which implements no
``explain`` at all. That is the right tool here anyway: what the keyword contributes is
reading a plan tree whose shape differs by server version and topology, and the only way
to cover those shapes at once is to feed it the documents each of them produces. The
acceptance suite covers a real server answering a real query.
"""

import pytest
from bson import ObjectId

BOUNDS = {"_id.date": ["[new Date(1702996077710), new Date(1702996077710)]"]}


def classic_explain():
    """A pre-SBE plan: the winning plan's stage sits at the top of the tree."""
    return {
        "queryPlanner": {
            "winningPlan": {
                "stage": "FETCH",
                "inputStage": {
                    "stage": "IXSCAN",
                    "indexName": "_id.deviceId_1__id.date_1",
                    "indexBounds": BOUNDS,
                },
            }
        },
        "executionStats": {
            "totalKeysExamined": 1,
            "totalDocsExamined": 1,
            "nReturned": 1,
            "executionTimeMillis": 0,
        },
    }


def sbe_explain():
    """A slot-based-engine plan, which nests what the classic one puts at the top."""
    return {
        "queryPlanner": {
            "winningPlan": {
                "queryPlan": {
                    "stage": "FETCH",
                    "inputStage": {
                        "stage": "IXSCAN",
                        "indexName": "_id.deviceId_1__id.date_1",
                        "indexBounds": BOUNDS,
                    },
                },
                "slotBasedPlan": {"slots": "$$RESULT=s11"},
            }
        },
        "executionStats": {
            "totalKeysExamined": 1,
            "totalDocsExamined": 1,
            "nReturned": 1,
            "executionTimeMillis": 3,
        },
    }


def collection_scan_explain():
    return {
        "queryPlanner": {"winningPlan": {"stage": "COLLSCAN", "direction": "forward"}},
        "executionStats": {
            "totalKeysExamined": 0,
            "totalDocsExamined": 3639,
            "nReturned": 1,
            "executionTimeMillis": 3,
        },
    }


def sharded_explain():
    return {
        "queryPlanner": {
            "winningPlan": {
                "stage": "SHARD_MERGE",
                "shards": [
                    {
                        "shardName": "shard-a",
                        "winningPlan": {
                            "stage": "FETCH",
                            "inputStage": {"stage": "IXSCAN", "indexName": "deviceId_1", "indexBounds": BOUNDS},
                        },
                    },
                    {
                        "shardName": "shard-b",
                        "winningPlan": {"stage": "COLLSCAN", "direction": "forward"},
                    },
                ],
            }
        },
        "executionStats": {
            "totalKeysExamined": 1,
            "totalDocsExamined": 2048,
            "nReturned": 1,
            "executionTimeMillis": 11,
            "executionStages": {
                "stage": "SHARD_MERGE",
                "shards": [
                    {
                        "shardName": "shard-a",
                        "totalKeysExamined": 1,
                        "totalDocsExamined": 1,
                        "nReturned": 1,
                        # The root stage counts what it alone read, which for a FETCH over
                        # an IXSCAN is not the shard's total. The totals are what to report.
                        "executionStages": {"stage": "FETCH", "docsExamined": 1, "nReturned": 1},
                    },
                    {
                        "shardName": "shard-b",
                        "totalKeysExamined": 0,
                        "totalDocsExamined": 2047,
                        "nReturned": 0,
                        "executionStages": {"stage": "COLLSCAN", "docsExamined": 2047, "nReturned": 0},
                    },
                ],
            },
        },
    }


@pytest.fixture
def explains(mongo_keywords, mock_db):
    """Keywords whose explain command returns whatever the test sets as ``returns``."""

    def set_return(explain):
        mock_db.command.return_value = explain
        return mongo_keywords

    set_return.command = mock_db.command  # type: ignore[attr-defined]
    return set_return


def test_explain_query_summarises_a_classic_plan(explains):
    mongo = explains(classic_explain())

    plan = mongo.explain_query("readings", **{"_id.deviceId": "device-1"})

    assert plan["stage"] == "FETCH"
    assert plan["index_name"] == "_id.deviceId_1__id.date_1"
    assert plan["collection_scan"] is False
    assert plan["keys_examined"] == 1
    assert plan["docs_examined"] == 1
    assert plan["returned"] == 1
    assert plan["duration_ms"] == 0


def test_explain_query_keeps_the_index_bounds(explains):
    """The field the keyword exists for: what the server actually searched for.

    A query that matches nothing and errors on nothing is answered here and nowhere else,
    so this is the one field the summary must never drop while flattening.
    """
    mongo = explains(classic_explain())

    plan = mongo.explain_query("readings", **{"_id.deviceId": "device-1"})

    assert plan["index_bounds"] == BOUNDS


def test_explain_query_reads_a_slot_based_plan(explains):
    """The stage moved under ``queryPlan`` in the newer engine, and must still be found."""
    mongo = explains(sbe_explain())

    plan = mongo.explain_query("readings", **{"_id.deviceId": "device-1"})

    assert plan["stage"] == "FETCH"
    assert plan["index_name"] == "_id.deviceId_1__id.date_1"
    assert plan["index_bounds"] == BOUNDS
    assert plan["collection_scan"] is False


@pytest.mark.parametrize("stage", ["EXPRESS_IXSCAN", "IDHACK"], ids=["mongodb_8", "older"])
def test_explain_query_treats_every_id_fast_path_as_an_index(explains, stage):
    """The ``_id`` fast path is named differently by server version.

    Detecting a scan by the presence of a COLLSCAN rather than by an allowlist of index
    stage names is what makes this hold without a version check.
    """
    mongo = explains(
        {
            "queryPlanner": {"winningPlan": {"stage": stage, "indexName": "_id_"}},
            "executionStats": {
                "totalKeysExamined": 1,
                "totalDocsExamined": 1,
                "nReturned": 1,
                "executionTimeMillis": 0,
            },
        }
    )

    plan = mongo.explain_query("readings", query={"_id": {"deviceId": "d-1"}})

    assert plan["stage"] == stage
    assert plan["collection_scan"] is False
    assert plan["index_name"] == "_id_"


def test_explain_query_flags_a_collection_scan(explains):
    mongo = explains(collection_scan_explain())

    plan = mongo.explain_query("readings", status="new")

    assert plan["collection_scan"] is True
    assert plan["index_name"] is None
    assert plan["index_bounds"] is None
    assert plan["docs_examined"] == 3639


def test_explain_query_ignores_a_rejected_collection_scan(explains):
    """A candidate plan the server threw away describes work that never happened.

    Sorting by a field the index does not cover is enough to put a COLLSCAN among the
    rejected plans of a query the server answered with an index, so reporting one would
    send a suite hunting for a scan that is not there.
    """
    explain = classic_explain()
    explain["queryPlanner"]["rejectedPlans"] = [{"stage": "SORT", "inputStage": {"stage": "COLLSCAN"}}]
    mongo = explains(explain)

    plan = mongo.explain_query("readings", **{"_id.deviceId": "device-1"})

    assert plan["collection_scan"] is False
    assert plan["index_name"] == "_id.deviceId_1__id.date_1"


def test_explain_query_does_not_borrow_an_index_from_a_rejected_plan(explains):
    """The mirror case, and the worse one: an index reported for a query that scanned."""
    explain = collection_scan_explain()
    explain["queryPlanner"]["rejectedPlans"] = [
        {"stage": "FETCH", "inputStage": {"stage": "IXSCAN", "indexName": "status_1", "indexBounds": BOUNDS}}
    ]
    mongo = explains(explain)

    plan = mongo.explain_query("readings", status="new")

    assert plan["collection_scan"] is True
    assert plan["index_name"] is None
    assert plan["index_bounds"] is None


def test_explain_query_ignores_the_trial_runs_of_the_plans_it_did_not_pick(explains):
    """``allPlansExecution`` verbosity carries every candidate's trial run as well."""
    explain = classic_explain()
    explain["executionStats"]["allPlansExecution"] = [
        {"executionStages": {"stage": "COLLSCAN", "docsExamined": 3639}}
    ]
    mongo = explains(explain)

    assert mongo.explain_query("readings", status="new")["collection_scan"] is False


def test_explain_query_ignores_a_shards_rejected_plans(explains):
    """Each shard chooses its own plan, and keeps its own rejects alongside it."""
    explain = sharded_explain()
    shard = explain["queryPlanner"]["winningPlan"]["shards"][0]
    shard["rejectedPlans"] = [{"stage": "COLLSCAN", "direction": "forward"}]
    mongo = explains(explain)

    summaries = {summary["shard"]: summary for summary in mongo.explain_query("readings", status="new")["shards"]}

    assert summaries["shard-a"]["collection_scan"] is False
    assert summaries["shard-b"]["collection_scan"] is True


def test_explain_query_summarises_each_shard(explains):
    mongo = explains(sharded_explain())

    plan = mongo.explain_query("readings", status="new")

    assert plan["stage"] == "SHARD_MERGE"
    assert plan["docs_examined"] == 2048
    assert plan["shards"] == [
        {
            "shard": "shard-a",
            "stage": "FETCH",
            "index_name": "deviceId_1",
            "index_bounds": BOUNDS,
            "collection_scan": False,
            "keys_examined": 1,
            "docs_examined": 1,
            "returned": 1,
        },
        {
            "shard": "shard-b",
            "stage": "COLLSCAN",
            "index_name": None,
            "index_bounds": None,
            "collection_scan": True,
            "keys_examined": 0,
            "docs_examined": 2047,
            "returned": 0,
        },
    ]


def test_explain_query_leaves_out_shards_when_the_plan_is_not_sharded(explains):
    mongo = explains(classic_explain())

    assert "shards" not in mongo.explain_query("readings", status="new")


def test_explain_query_returns_the_raw_explain(explains):
    """The escape hatch: a field the summary omits is still reachable."""
    explain = classic_explain()
    mongo = explains(explain)

    assert mongo.explain_query("readings", status="new")["raw"] == explain


def test_explain_query_logs_the_summary(explains, mocker):
    """Logged at INFO, never at WARN: a warning on correct use trains people to ignore them."""
    info = mocker.patch("MongoDBLibrary.keywords.logger.info")
    warn = mocker.patch("MongoDBLibrary.keywords.logger.warn", create=True)
    mongo = explains(classic_explain())

    mongo.explain_query("readings", status="new")

    assert "_id.deviceId_1__id.date_1" in info.call_args.args[0]
    warn.assert_not_called()


def test_explain_query_logs_one_field_per_line(explains, mocker):
    """Robot Framework keeps newlines and indentation in the log, so the summary uses them.

    On one line it is unreadable, and ``index_bounds`` — a dictionary inside the summary,
    and the field the keyword exists for — suffers most.
    """
    info = mocker.patch("MongoDBLibrary.keywords.logger.info")
    mongo = explains(classic_explain())

    mongo.explain_query("readings", status="new")

    logged = info.call_args.args[0].splitlines()
    assert logged[0] == "Explain of {'status': 'new'} on 'readings':"
    assert "  stage            FETCH" in logged
    assert "  index_bounds" in logged
    assert "    _id.date  [new Date(1702996077710), new Date(1702996077710)]" in logged


def test_explain_query_logs_the_whole_explain_at_debug(explains, mocker):
    """Indented, and at DEBUG: too long to read every time, wanted on the occasion it is."""
    debug = mocker.patch("MongoDBLibrary.keywords.logger.debug")
    mongo = explains(classic_explain())

    mongo.explain_query("readings", status="new")

    logged = debug.call_args.args[0]
    assert '\n  "queryPlanner": {' in logged


def test_explain_query_debug_log_survives_a_value_json_cannot_write(explains, mocker):
    """An explain holds BSON types, and failing to log must not fail the keyword."""
    debug = mocker.patch("MongoDBLibrary.keywords.logger.debug")
    explain = classic_explain()
    explain["queryPlanner"]["parsedQuery"] = {"_id": ObjectId("6a7ccdea6abf6a4ebbc3514f")}
    mongo = explains(explain)

    mongo.explain_query("readings", status="new")

    assert "6a7ccdea6abf6a4ebbc3514f" in debug.call_args.args[0]


def test_explain_query_without_execution_stats_leaves_the_counters_empty(explains):
    """``queryPlanner`` verbosity picks a plan without running it, which is not an error."""
    mongo = explains({"queryPlanner": {"winningPlan": {"stage": "COLLSCAN"}}})

    plan = mongo.explain_query("readings", status="new", verbosity="queryPlanner")

    assert plan["stage"] == "COLLSCAN"
    assert plan["keys_examined"] is None
    assert plan["docs_examined"] is None
    assert plan["returned"] is None
    assert plan["duration_ms"] is None


def test_explain_query_sends_the_query_as_a_find_command(explains):
    mongo = explains(classic_explain())

    mongo.explain_query("readings", **{"_id.deviceId": "device-1"})

    assert explains.command.call_args.args == (
        {"explain": {"find": "readings", "filter": {"_id.deviceId": "device-1"}}, "verbosity": "executionStats"},
    )


def test_explain_query_sends_the_rest_of_the_find(explains):
    mongo = explains(classic_explain())

    mongo.explain_query(
        "readings",
        query={"status": "new"},
        projection={"total": 1},
        sort={"placedAt": -1},
        limit=5,
        skip=2,
        verbosity="allPlansExecution",
    )

    assert explains.command.call_args.args == (
        {
            "explain": {
                "find": "readings",
                "filter": {"status": "new"},
                "projection": {"total": 1},
                "sort": {"placedAt": -1},
                "limit": 5,
                "skip": 2,
            },
            "verbosity": "allPlansExecution",
        },
    )


def test_explain_query_leaves_out_the_options_it_was_not_given(explains):
    """A `limit` of zero means no limit, and the find command must not be told otherwise."""
    mongo = explains(classic_explain())

    mongo.explain_query("readings", status="new")

    assert explains.command.call_args.args[0]["explain"] == {"find": "readings", "filter": {"status": "new"}}


def test_explain_query_explains_the_query_that_would_really_be_sent(explains):
    """A string ``_id`` is rewritten for the find keywords, so it is rewritten here too."""
    mongo = explains(classic_explain())

    mongo.explain_query("orders", _id="6a7ccdea6abf6a4ebbc3514f")

    assert explains.command.call_args.args[0]["explain"]["filter"] == {
        "_id": ObjectId("6a7ccdea6abf6a4ebbc3514f")
    }


def test_explain_query_refuses_both_ways_of_giving_the_query(explains):
    """Merging them would hide a typo, and which one was meant decides what to fix."""
    mongo = explains(classic_explain())

    with pytest.raises(ValueError, match="not both"):
        mongo.explain_query("readings", query={"status": "new"}, status="new")


def test_explain_query_reports_a_missing_alias_like_every_other_keyword(mongo_keywords):
    with pytest.raises(KeyError, match="Alias 'missing_alias' not found in connection pool."):
        mongo_keywords.explain_query("readings", alias="missing_alias", status="new")
