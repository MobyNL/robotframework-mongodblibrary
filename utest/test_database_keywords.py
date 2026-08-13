"""Tests for the collection, database and server keywords.

These act on the database or the client behind an alias rather than on one
collection, so they exercise a resolution path the document keywords do not.
"""

import pytest
from pymongo.errors import CollectionInvalid
from pytest import param

# --------------------------------------------------------------------------- #
# Collections
# --------------------------------------------------------------------------- #

def test_list_collections_is_empty_for_an_untouched_database(mongo):
    """MongoDB does not create a database until something is written to it."""
    assert mongo.list_collections() == []


def test_list_collections_reports_what_has_been_written_to(mongo):
    mongo.insert_document("orders", {"key": "value"})
    mongo.insert_document("users", {"key": "value"})

    assert sorted(mongo.list_collections()) == ["orders", "users"]


def test_create_collection_makes_it_appear_before_anything_is_written(mongo):
    mongo.create_collection("events")

    assert mongo.list_collections() == ["events"]
    assert mongo.count_documents("events") == 0


def test_create_collection_rejects_one_that_already_exists(mongo):
    mongo.create_collection("events")

    with pytest.raises(CollectionInvalid, match="events"):
        mongo.create_collection("events")


def test_create_collection_passes_its_options_through(mongo_keywords, mock_db):
    """mongomock refuses capped collections, so the call itself is what is checked."""
    mongo_keywords.create_collection("recent", capped=True, size=1048576)

    assert mock_db.create_collection.call_args.kwargs == {"capped": True, "size": 1048576}


def test_drop_collection_removes_it(mongo):
    mongo.insert_document("orders", {"key": "value"})

    mongo.drop_collection("orders")

    assert mongo.list_collections() == []


def test_drop_collection_takes_the_indexes_with_it(mongo):
    """The reason to drop rather than empty: a unique index outlives its documents."""
    mongo.insert_document("orders", {"email": "a@example.test"})
    mongo.create_index("orders", {"email": 1}, unique=True)

    mongo.drop_collection("orders")
    mongo.insert_document("orders", {"email": "a@example.test"})
    mongo.insert_document("orders", {"email": "a@example.test"})

    assert mongo.count_documents("orders") == 2


def test_delete_all_documents_leaves_the_indexes_behind(mongo):
    """The contrast that makes Drop Collection worth having."""
    mongo.insert_document("orders", {"email": "a@example.test"})
    mongo.create_index("orders", {"email": 1}, unique=True)

    mongo.delete_all_documents_from_collection("orders")

    assert [index["name"] for index in mongo.list_indexes("orders")] == ["_id_", "email_1"]


def test_dropping_a_collection_that_is_not_there_is_not_an_error(mongo):
    """So a teardown after a failed setup does not fail in turn."""
    mongo.drop_collection("never_existed")


# --------------------------------------------------------------------------- #
# Databases and server
# --------------------------------------------------------------------------- #

def test_list_databases(mongo):
    mongo.insert_document("mycollection", {"key": "value"})

    assert "test_db" in mongo.list_databases()


def test_drop_database_removes_its_data(mongo):
    mongo.insert_document("mycollection", {"key": "value"})

    mongo.drop_database("test_db")

    assert mongo.count_documents("mycollection") == 0


def test_drop_database_leaves_the_connection_usable(mongo):
    """MongoDB recreates a database on the next write, so the alias keeps working."""
    mongo.insert_document("mycollection", {"key": "value"})

    mongo.drop_database("test_db")
    mongo.insert_document("mycollection", {"key": "again"})

    assert mongo.count_documents("mycollection") == 1


def test_dropping_a_database_that_is_not_there_is_not_an_error(mongo):
    mongo.drop_database("never_existed")


def test_drop_database_names_its_target_explicitly():
    """There is no default, so the connected database cannot be dropped by accident."""
    from robot.running.arguments import PythonArgumentParser

    from MongoDBLibrary.keywords import MongoDBKeywords

    spec = PythonArgumentParser("drop_database").parse(MongoDBKeywords.drop_database)

    assert "db_name" not in spec.defaults, "db_name must stay required"
    assert "db_name" in spec.positional


def test_get_server_info_reports_a_version(mongo):
    info = mongo.get_server_info()

    assert "version" in info


def test_get_server_info_is_dot_accessible(mongo):
    """So a suite can write ${info.version} without Get From Dictionary."""
    assert mongo.get_server_info().version


def test_run_database_command_returns_the_reply(mongo):
    assert mongo.run_database_command("ping")["ok"] == 1.0


def test_run_database_command_is_dot_accessible(mongo):
    assert mongo.run_database_command("ping").ok == 1.0


def test_run_database_command_passes_a_command_document_through(mongo_keywords, mock_db):
    mock_db.command.return_value = {"ok": 1.0}

    mongo_keywords.run_database_command({"collStats": "orders"})

    assert mock_db.command.call_args.args == ({"collStats": "orders"},)


def test_run_database_command_reads_a_command_written_as_a_document(mongo_keywords, mock_db):
    """Regression: a command document reached the server as a command name.

    Robot Framework does not convert an argument that also accepts ``str``, so
    ``command={"dbStats": 1}`` arrived here as text, was sent as a bare command name and
    was rejected with "no such command". Only a real server showed this: a MagicMock
    accepts anything, and mongomock implements ``ping`` alone.
    """
    mock_db.command.return_value = {"ok": 1.0}

    mongo_keywords.run_database_command('{"dbStats": 1}')

    assert mock_db.command.call_args.args == ({"dbStats": 1},)


def test_run_database_command_still_takes_a_bare_name(mongo_keywords, mock_db):
    mock_db.command.return_value = {"ok": 1.0}

    mongo_keywords.run_database_command("ping")

    assert mock_db.command.call_args.args == ("ping",)


@pytest.mark.parametrize(
    "command",
    ['{"unbalanced": 1', '{"not", "a", "document"}'],
    ids=["unparseable", "not_a_dict"],
)
def test_run_database_command_rejects_a_broken_document(mongo_keywords, mock_db, command):
    """A value that opens like a document but is not one must not be sent as a name."""
    with pytest.raises(ValueError, match="looks like a document"):
        mongo_keywords.run_database_command(command)


def test_run_database_command_forwards_further_options(mongo_keywords, mock_db):
    mock_db.command.return_value = {"ok": 1.0}

    mongo_keywords.run_database_command("dbStats", scale=1024)

    assert mock_db.command.call_args.kwargs == {"scale": 1024}


# --------------------------------------------------------------------------- #
# Alias handling
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "keyword_name, args, kwargs",
    [
        param("list_collections", (), {}, id="list_collections"),
        param("create_collection", ("mycollection",), {}, id="create_collection"),
        param("drop_collection", ("mycollection",), {}, id="drop_collection"),
        param("list_databases", (), {}, id="list_databases"),
        param("drop_database", ("test_db",), {}, id="drop_database"),
        param("get_server_info", (), {}, id="get_server_info"),
        param("run_database_command", ("ping",), {}, id="run_database_command"),
    ],
)
def test_missing_alias_raises_the_same_error_everywhere(mongo_keywords, keyword_name, args, kwargs):
    """Server-wide keywords resolve through an alias too, so they fail the same way."""
    with pytest.raises(KeyError, match="Alias 'missing_alias' not found in connection pool."):
        getattr(mongo_keywords, keyword_name)(*args, alias="missing_alias", **kwargs)
