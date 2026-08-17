import time

import mongomock
import pytest
from pytest import param
from robot.running.arguments import PythonArgumentParser
from robot.utils import DotDict

from MongoDBLibrary.keywords import AssertionOperator, MongoDBKeywords

# --------------------------------------------------------------------------- #
# Connecting
# --------------------------------------------------------------------------- #

def test_connect_to_database(mongo_keywords, mocker):
    client = mocker.MagicMock(name="MockMongoClient")
    client.__getitem__.return_value.name = "test_db"
    mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=client)

    mongo_keywords.connect_to_database(
        db_name="test_db",
        alias="default",
        db_user="user",
        db_password="pass",
        db_host="localhost",
        db_port=27017,
    )

    assert mongo_keywords.connection_manager.db_connection_pool["default"].name == "test_db"


def test_connect_to_database_using_connection_string(mongo_keywords, mocker):
    client = mocker.MagicMock(name="MockMongoClient")
    client.__getitem__.return_value.name = "test_db"
    mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=client)

    mongo_keywords.connect_to_database_using_connection_string(
        db_conn_string="mongodb://localhost:27017", db_name="test_db", alias="test_alias"
    )

    assert mongo_keywords.connection_manager.db_connection_pool["test_alias"].name == "test_db"


def test_connect_to_database_uses_default_alias(mongo_keywords, mocker):
    mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=mocker.MagicMock())

    mongo_keywords.connect_to_database(db_name="test_db", db_host="localhost")

    assert mongo_keywords.connection_manager.list_connection_pool() == ["default"]


def test_connect_to_database_failure(mongo_keywords, mocker):
    mocker.patch("MongoDBLibrary.keywords.MongoClient", side_effect=Exception("Connection failed"))

    with pytest.raises(Exception, match="Connection failed"):
        mongo_keywords.connect_to_database(db_name="test_db", db_host="localhost", db_port=27017)
    assert mongo_keywords.connection_manager.db_connection_pool == {}


def test_connect_to_database_using_connection_string_failure(mongo_keywords, mocker):
    mocker.patch("MongoDBLibrary.keywords.MongoClient", side_effect=Exception("Invalid connection string"))

    with pytest.raises(Exception, match="Invalid connection string"):
        mongo_keywords.connect_to_database_using_connection_string(db_conn_string="invalid", db_name="test_db")
    assert mongo_keywords.connection_manager.db_connection_pool == {}


@pytest.mark.parametrize(
    "keyword_name, kwargs",
    [
        param("connect_to_database", {"db_name": "test_db", "db_host": "unreachable"}, id="host_and_credentials"),
        param(
            "connect_to_database_using_connection_string",
            {"db_conn_string": "mongodb://unreachable:27017", "db_name": "test_db"},
            id="connection_string",
        ),
    ],
)
def test_connect_verifies_the_server_is_reachable(mongo_keywords, mocker, keyword_name, kwargs):
    """Regression: pymongo connects lazily, so connecting must be verified here.

    Without the verification the keyword passes against an unreachable server and the
    failure surfaces later, at an unrelated keyword.
    """
    client = mocker.MagicMock(name="MockMongoClient")
    client.admin.command.side_effect = Exception("No servers found yet")
    mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=client)

    with pytest.raises(Exception, match="No servers found yet"):
        getattr(mongo_keywords, keyword_name)(**kwargs)

    client.admin.command.assert_called_once_with("ping")
    client.close.assert_called_once()
    assert mongo_keywords.connection_manager.db_connection_pool == {}


def test_connect_to_database_defaults_to_a_single_host_without_tls(mongo_keywords, mocker):
    client_class = mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=mocker.MagicMock())

    mongo_keywords.connect_to_database(db_name="test_db", db_host="localhost", db_port=27017)

    assert client_class.call_args.kwargs == {
        "host": "localhost", "port": 27017, "username": None, "password": None
    }


def test_connect_to_database_with_srv_resolves_a_seed_list(mongo_keywords, mocker):
    """Atlas cluster names have no address record, so they need mongodb+srv."""
    client_class = mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=mocker.MagicMock())

    mongo_keywords.connect_to_database(
        db_name="test_db", db_host="mycluster.abcde.mongodb.net", db_user="user", db_password="pass", srv=True
    )

    assert client_class.call_args.kwargs == {
        "host": "mongodb+srv://mycluster.abcde.mongodb.net",
        "port": None,
        "username": "user",
        "password": "pass",
    }


def test_connect_to_database_with_srv_ignores_db_port(mongo_keywords, mocker, caplog):
    client_class = mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=mocker.MagicMock())

    mongo_keywords.connect_to_database(
        db_name="test_db", db_host="mycluster.abcde.mongodb.net", db_port=27017, srv=True
    )

    assert client_class.call_args.kwargs["port"] is None
    assert "'db_port' is ignored when 'srv' is enabled" in caplog.text


@pytest.mark.parametrize("tls", [True, False], ids=["tls_on", "tls_off"])
def test_connect_to_database_forces_tls(mongo_keywords, mocker, tls):
    client_class = mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=mocker.MagicMock())

    mongo_keywords.connect_to_database(db_name="test_db", db_host="localhost", tls=tls)

    assert client_class.call_args.kwargs["tls"] is tls


def test_connect_to_database_omits_tls_when_unset(mongo_keywords, mocker):
    """Leaving tls unset must let the connection type decide, not force it off."""
    client_class = mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=mocker.MagicMock())

    mongo_keywords.connect_to_database(db_name="test_db", db_host="localhost")

    assert "tls" not in client_class.call_args.kwargs


def test_connect_to_database_passes_auth_source(mongo_keywords, mocker):
    """A user created outside db_name cannot authenticate without this."""
    client_class = mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=mocker.MagicMock())

    mongo_keywords.connect_to_database(db_name="test_db", db_host="localhost", auth_source="admin")

    assert client_class.call_args.kwargs["authSource"] == "admin"


def test_connect_to_database_converts_the_server_selection_timeout(mongo_keywords, mocker):
    client_class = mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=mocker.MagicMock())

    mongo_keywords.connect_to_database(db_name="test_db", db_host="localhost", server_selection_timeout="5 seconds")

    assert client_class.call_args.kwargs["serverSelectionTimeoutMS"] == 5000


def test_connection_string_converts_the_server_selection_timeout(mongo_keywords, mocker):
    client_class = mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=mocker.MagicMock())

    mongo_keywords.connect_to_database_using_connection_string(
        db_conn_string="mongodb://localhost:27017", db_name="test_db", server_selection_timeout="1500 milliseconds"
    )

    assert client_class.call_args.kwargs["serverSelectionTimeoutMS"] == 1500


def test_optional_connection_arguments_are_omitted_when_unset(mongo_keywords, mocker):
    client_class = mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=mocker.MagicMock())

    mongo_keywords.connect_to_database(db_name="test_db", db_host="localhost")

    assert set(client_class.call_args.kwargs) == {"host", "port", "username", "password"}


def test_srv_and_tls_are_converted_from_robot_arguments():
    """RF must convert srv/tls from strings, so `srv=True` in a suite is a boolean."""
    spec = PythonArgumentParser("connect_to_database").parse(MongoDBKeywords.connect_to_database)

    _, named = spec.convert(["mydb"], [("srv", "True"), ("tls", "False")])

    assert named == [("srv", True), ("tls", False)]


# --------------------------------------------------------------------------- #
# Robot Framework Secret credentials
# --------------------------------------------------------------------------- #

# Imported rather than `importorskip`ed: that raises Skipped at module level on Robot
# Framework 7.3 and older, which skips the whole file — every test in it, not just the
# ones below — and reports it as one skip. The floor of the supported range is tested in
# CI, so the file has to keep running there.
try:  # Robot Framework 7.4 and later
    from robot.api.types import Secret as secret
except ImportError:
    secret = None

needs_secret = pytest.mark.skipif(secret is None, reason="Secret needs Robot Framework 7.4")


@needs_secret
def test_a_secret_password_reaches_the_driver_as_text(mongo_keywords, mocker):
    """The point of Secret is hiding the value from the log, not from pymongo."""
    client_class = mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=mocker.MagicMock())

    mongo_keywords.connect_to_database(db_name="test_db", db_host="localhost", db_password=secret("hunter2"))

    assert client_class.call_args.kwargs["password"] == "hunter2"


def test_a_plain_password_still_works(mongo_keywords, mocker):
    client_class = mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=mocker.MagicMock())

    mongo_keywords.connect_to_database(db_name="test_db", db_host="localhost", db_password="hunter2")

    assert client_class.call_args.kwargs["password"] == "hunter2"


@needs_secret
def test_a_secret_connection_string_reaches_the_driver_as_text(mongo_keywords, mocker):
    client_class = mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=mocker.MagicMock())

    mongo_keywords.connect_to_database_using_connection_string(
        db_conn_string=secret("mongodb://localhost:27017"), db_name="test_db"
    )

    assert client_class.call_args.args == ("mongodb://localhost:27017",)


@needs_secret
def test_two_aliases_with_equal_secrets_share_one_client(mongo_keywords, two_clients):
    """Regression guard: two Secret objects holding the same password are still two
    objects. Keying the client cache on the wrapper rather than the value would make
    every alias miss the cache and open its own connection pool."""
    factory, _ = two_clients

    mongo_keywords.connect_to_database(db_name="db", db_host="localhost", db_password=secret("pw"), alias="a")
    mongo_keywords.connect_to_database(db_name="db", db_host="localhost", db_password=secret("pw"), alias="b")

    assert factory.call_count == 1
    pool = mongo_keywords.connection_manager.db_connection_pool
    assert pool["a"].client is pool["b"].client


@needs_secret
def test_a_secret_and_an_equal_plain_password_share_one_client(mongo_keywords, two_clients):
    """The same credential is the same connection however the suite chose to write it."""
    factory, _ = two_clients

    mongo_keywords.connect_to_database(db_name="db", db_host="localhost", db_password="pw", alias="a")
    mongo_keywords.connect_to_database(db_name="db", db_host="localhost", db_password=secret("pw"), alias="b")

    assert factory.call_count == 1


@needs_secret
def test_different_secrets_do_not_share_a_client(mongo_keywords, two_clients):
    factory, _ = two_clients

    mongo_keywords.connect_to_database(db_name="db", db_host="localhost", db_password=secret("one"), alias="a")
    mongo_keywords.connect_to_database(db_name="db", db_host="localhost", db_password=secret("two"), alias="b")

    assert factory.call_count == 2


@needs_secret
@pytest.mark.parametrize(
    "keyword_name, argument",
    [
        param("connect_to_database", "db_password", id="password"),
        param("connect_to_database_using_connection_string", "db_conn_string", id="connection_string"),
    ],
)
def test_robot_framework_accepts_a_secret_for_the_credential(keyword_name, argument):
    """A str annotation makes Robot Framework reject a Secret outright, which is how
    this was found: 'got value <secret> (Secret) that cannot be converted to string'."""
    spec = PythonArgumentParser(keyword_name).parse(getattr(MongoDBKeywords, keyword_name))
    value = secret("hunter2")

    _, named = spec.convert(["mydb"], [(argument, value)])

    assert dict(named)[argument] is value


@needs_secret
def test_a_secret_does_not_disclose_itself_when_logged():
    """Robot Framework logs the object, so its string form is what a suite would leak."""
    assert str(secret("hunter2")) == "<secret>"
    assert "hunter2" not in repr(secret("hunter2"))


@pytest.mark.parametrize(
    "argument, value, option",
    [
        param("auth_mechanism", "MONGODB-AWS", "authMechanism", id="auth_mechanism"),
        param("replica_set", "rs0", "replicaSet", id="replica_set"),
        param("read_preference", "secondaryPreferred", "readPreference", id="read_preference"),
        param("direct_connection", True, "directConnection", id="direct_connection"),
    ],
)
def test_connect_to_database_passes_its_topology_options(mongo_keywords, mocker, argument, value, option):
    """Each is spelled as pymongo's URI option name, not the keyword's argument name."""
    client_class = mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=mocker.MagicMock())

    mongo_keywords.connect_to_database(db_name="test_db", db_host="localhost", **{argument: value})

    assert client_class.call_args.kwargs[option] == value


def test_direct_connection_can_be_forced_off(mongo_keywords, mocker):
    """False is a real setting here, so it must not be dropped as though it were unset."""
    client_class = mocker.patch("MongoDBLibrary.keywords.MongoClient", return_value=mocker.MagicMock())

    mongo_keywords.connect_to_database(db_name="test_db", db_host="localhost", direct_connection=False)

    assert client_class.call_args.kwargs["directConnection"] is False


def test_topology_options_take_part_in_the_client_cache_key(mongo_keywords, two_clients):
    """Two aliases wanting different read preferences must not share one client."""
    factory, _ = two_clients

    mongo_keywords.connect_to_database(db_name="db", db_host="localhost", alias="a")
    mongo_keywords.connect_to_database(
        db_name="db", db_host="localhost", alias="b", read_preference="secondaryPreferred"
    )

    assert factory.call_count == 2


# --------------------------------------------------------------------------- #
# Client reuse
# --------------------------------------------------------------------------- #

@pytest.fixture
def two_clients(mocker):
    """Patch MongoClient to hand out two distinct in-memory clients in turn."""
    clients = [mongomock.MongoClient(), mongomock.MongoClient()]
    factory = mocker.patch("MongoDBLibrary.keywords.MongoClient", side_effect=clients)
    return factory, clients


def test_the_same_connection_parameters_reuse_one_client(mongo_keywords, two_clients):
    """Five aliases against one server should not open five socket pools."""
    factory, _ = two_clients

    mongo_keywords.connect_to_database(db_name="db", db_host="localhost", alias="a")
    mongo_keywords.connect_to_database(db_name="db", db_host="localhost", alias="b")

    assert factory.call_count == 1
    pool = mongo_keywords.connection_manager.db_connection_pool
    assert pool["a"].client is pool["b"].client


def test_different_connection_parameters_get_different_clients(mongo_keywords, two_clients):
    factory, _ = two_clients

    mongo_keywords.connect_to_database(db_name="db", db_host="localhost", alias="a")
    mongo_keywords.connect_to_database(db_name="db", db_host="elsewhere", alias="b")

    assert factory.call_count == 2


def test_different_credentials_to_one_host_get_different_clients(mongo_keywords, two_clients):
    factory, _ = two_clients

    mongo_keywords.connect_to_database(db_name="db", db_host="localhost", db_user="alice", alias="a")
    mongo_keywords.connect_to_database(db_name="db", db_host="localhost", db_user="bob", alias="b")

    assert factory.call_count == 2


def test_a_shared_client_survives_disconnecting_one_alias(mongo_keywords, two_clients, mocker):
    """Closing a shared client would break every other alias using it."""
    _, clients = two_clients
    close = mocker.spy(clients[0], "close")
    mongo_keywords.connect_to_database(db_name="db", db_host="localhost", alias="a")
    mongo_keywords.connect_to_database(db_name="db", db_host="localhost", alias="b")

    mongo_keywords.disconnect_from_database(alias="a")
    assert close.call_count == 0

    mongo_keywords.disconnect_from_database(alias="b")
    assert close.call_count == 1


def test_disconnecting_the_last_alias_lets_a_new_connection_build_a_fresh_client(mongo_keywords, two_clients):
    """A closed client must not be handed out again from the cache."""
    factory, _ = two_clients

    mongo_keywords.connect_to_database(db_name="db", db_host="localhost", alias="a")
    mongo_keywords.disconnect_from_database(alias="a")
    mongo_keywords.connect_to_database(db_name="db", db_host="localhost", alias="a")

    assert factory.call_count == 2


def test_a_failed_connection_is_not_cached(mongo_keywords, mocker):
    failing = mocker.MagicMock(name="FailingClient")
    failing.admin.command.side_effect = Exception("No servers found yet")
    working = mongomock.MongoClient()
    factory = mocker.patch("MongoDBLibrary.keywords.MongoClient", side_effect=[failing, working])

    with pytest.raises(Exception, match="No servers found yet"):
        mongo_keywords.connect_to_database(db_name="db", db_host="localhost", alias="a")
    mongo_keywords.connect_to_database(db_name="db", db_host="localhost", alias="a")

    assert factory.call_count == 2
    assert mongo_keywords.connection_manager.list_connection_pool() == ["a"]


def test_overwriting_an_alias_closes_the_replaced_client(mongo_keywords, two_clients, mocker):
    _, clients = two_clients
    close = mocker.spy(clients[0], "close")
    mongo_keywords.connect_to_database(db_name="db", db_host="localhost", alias="a")

    mongo_keywords.connect_to_database(db_name="db", db_host="elsewhere", alias="a")

    assert close.call_count == 1
    assert mongo_keywords.connection_manager.db_connection_pool["a"].client is clients[1]


# --------------------------------------------------------------------------- #
# Active connection
# --------------------------------------------------------------------------- #

def test_get_active_alias_defaults_to_default(mongo_keywords):
    assert mongo_keywords.get_active_alias() == "default"


def test_switch_connection_changes_the_active_alias(mongo_keywords, mocker):
    mongo_keywords.connection_manager.add_to_connection_pool(mocker.MagicMock(), "other")

    mongo_keywords.switch_connection(alias="other")

    assert mongo_keywords.get_active_alias() == "other"


def test_switch_connection_to_nonexistent_alias(mongo_keywords):
    with pytest.raises(ValueError, match="Connection with alias 'missing' is not connected."):
        mongo_keywords.switch_connection(alias="missing")


def test_switch_database_still_works_while_deprecated(mongo_keywords, mocker):
    """The old name must keep working for suites already using it."""
    mongo_keywords.connection_manager.add_to_connection_pool(mocker.MagicMock(), "other")

    mongo_keywords.switch_database(alias="other")

    assert mongo_keywords.get_active_alias() == "other"


def test_switch_database_is_marked_deprecated():
    """Robot Framework warns on a keyword whose documentation starts with *DEPRECATED*."""
    assert MongoDBKeywords.switch_database.__doc__.strip().startswith("*DEPRECATED*")


# --------------------------------------------------------------------------- #
# Disconnecting
# --------------------------------------------------------------------------- #

def test_disconnect_from_database(mongo_keywords, mocker):
    mongo_keywords.connection_manager.add_to_connection_pool(mocker.MagicMock(), "test_alias")

    mongo_keywords.disconnect_from_database(alias="test_alias")

    assert "test_alias" not in mongo_keywords.connection_manager.db_connection_pool


def test_disconnect_from_database_no_alias(mongo_keywords, mocker):
    mongo_keywords.connection_manager.add_to_connection_pool(mocker.MagicMock(), "default")

    mongo_keywords.disconnect_from_database()

    assert "default" not in mongo_keywords.connection_manager.db_connection_pool


def test_disconnect_from_nonexistent_database(mongo_keywords):
    with pytest.raises(ValueError, match="Connection with alias 'nonexistent_alias' is not connected."):
        mongo_keywords.disconnect_from_database(alias="nonexistent_alias")


def test_disconnect_from_all_databases(mongo_keywords, mocker):
    mongo_keywords.connection_manager.add_to_connection_pool(mocker.MagicMock(), "alias1")
    mongo_keywords.connection_manager.add_to_connection_pool(mocker.MagicMock(), "alias2")

    mongo_keywords.disconnect_from_all_databases()

    assert mongo_keywords.list_database_connections() == []


def test_list_database_connections(mongo, mocker):
    mongo.connection_manager.add_to_connection_pool(mocker.MagicMock(), "extra")

    assert mongo.list_database_connections() == ["default", "extra"]


def test_check_if_database_connection_exists(mongo):
    mongo.check_if_database_connection_exists()


def test_check_if_database_connection_exists_failure(mongo_keywords):
    with pytest.raises(ValueError, match="No database connection exists for alias 'missing'."):
        mongo_keywords.check_if_database_connection_exists(alias="missing")


# --------------------------------------------------------------------------- #
# CRUD, against a real in-memory MongoDB
# --------------------------------------------------------------------------- #

def test_insert_and_find_document(mongo):
    doc_id = mongo.insert_document("mycollection", {"key": "value"})

    found = mongo.find_document("mycollection", key="value")

    assert isinstance(found, DotDict)
    assert found["key"] == "value"
    assert found["_id"] == doc_id


def test_find_document_no_results(mongo):
    assert mongo.find_document("mycollection", key="absent") is None


def test_update_document(mongo):
    mongo.insert_document("mycollection", {"key": "value", "other": 1})

    updated = mongo.update_document("mycollection", {"key": "value"}, {"key": "new_value"})

    assert updated["key"] == "new_value"
    assert updated["other"] == 1, "$set must not replace the whole document"


def test_update_document_no_match(mongo):
    assert mongo.update_document("mycollection", {"key": "absent"}, {"key": "x"}) is None


def test_update_document_with_operators(mongo):
    mongo.insert_document("mycollection", {"key": "value", "items": ["a"]})

    updated = mongo.update_document_with_operators(
        "mycollection", {"key": "value"}, {"$push": {"items": "b"}}
    )

    assert updated["items"] == ["a", "b"]


def test_delete_document_deletes_only_one(mongo):
    mongo.insert_document("mycollection", {"key": "value"})
    mongo.insert_document("mycollection", {"key": "value"})

    assert mongo.delete_document("mycollection", key="value") == 1
    assert mongo.count_documents("mycollection", key="value") == 1


def test_delete_many(mongo):
    mongo.insert_document("mycollection", {"key": "value"})
    mongo.insert_document("mycollection", {"key": "value"})
    mongo.insert_document("mycollection", {"key": "other"})

    assert mongo.delete_many("mycollection", key="value") == 2
    assert mongo.count_documents("mycollection") == 1


def test_delete_documents_with_query(mongo):
    for score in (1, 5, 10):
        mongo.insert_document("mycollection", {"score": score})

    assert mongo.delete_documents_with_query("mycollection", {"score": {"$gte": 5}}) == 2
    assert mongo.count_documents("mycollection") == 1


def test_delete_all_documents_from_collection(mongo):
    mongo.insert_document("mycollection", {"key": "value"})
    mongo.insert_document("mycollection", {"key": "other"})

    assert mongo.delete_all_documents_from_collection("mycollection") == 2
    assert mongo.count_documents("mycollection") == 0


def test_count_documents(mongo):
    mongo.insert_document("mycollection", {"key": "value"})
    mongo.insert_document("mycollection", {"key": "other"})

    assert mongo.count_documents("mycollection", key="value") == 1
    assert mongo.count_documents("mycollection") == 2


def test_execute_query(mongo):
    mongo.insert_document("mycollection", {"key": "value", "n": 1})
    mongo.insert_document("mycollection", {"key": "value", "n": 2})
    mongo.insert_document("mycollection", {"key": "other", "n": 3})

    results = mongo.execute_query(
        "mycollection", [{"$match": {"key": "value"}}, {"$group": {"_id": "$key", "total": {"$sum": "$n"}}}]
    )

    assert results == [{"_id": "value", "total": 3}]


def test_execute_query_invalid_pipeline(mongo):
    with pytest.raises(Exception, match="Invalid pipeline"):
        mongo.execute_query("mycollection", pipeline="invalid_pipeline")


def test_count_documents_propagates_driver_errors(mongo_keywords, mock_db, mocker):
    mock_db.__getitem__.return_value.count_documents.side_effect = Exception("Invalid query")

    with pytest.raises(Exception, match="Invalid query"):
        mongo_keywords.count_documents("mycollection", key="value")


# --------------------------------------------------------------------------- #
# Alias handling
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "keyword_name, args, kwargs",
    [
        param("insert_document", ("mycollection", {"key": "value"}), {}, id="insert_document"),
        param("find_document", ("mycollection",), {"key": "value"}, id="find_document"),
        param("update_document", ("mycollection", {}, {}), {}, id="update_document"),
        param("update_document_with_operators", ("mycollection", {}, {}), {}, id="update_with_operators"),
        param("delete_document", ("mycollection",), {"key": "value"}, id="delete_document"),
        param("delete_many", ("mycollection",), {"key": "value"}, id="delete_many"),
        param("delete_documents_with_query", ("mycollection", {}), {}, id="delete_with_query"),
        param("delete_all_documents_from_collection", ("mycollection",), {}, id="delete_all"),
        param("count_documents", ("mycollection",), {"key": "value"}, id="count_documents"),
        param("execute_query", ("mycollection", []), {}, id="execute_query"),
    ],
)
def test_missing_alias_raises_the_same_error_everywhere(mongo_keywords, keyword_name, args, kwargs):
    """Every collection keyword must report an unknown alias the same actionable way."""
    with pytest.raises(KeyError, match="Alias 'missing_alias' not found in connection pool."):
        getattr(mongo_keywords, keyword_name)(*args, alias="missing_alias", **kwargs)


def test_switch_database_to_nonexistent_alias(mongo_keywords):
    with pytest.raises(ValueError, match="Connection with alias 'nonexistent_alias' is not connected."):
        mongo_keywords.switch_database(alias="nonexistent_alias")


def test_switch_database_changes_the_alias_used_by_later_keywords(mongo_keywords):
    """Regression: Switch Database used to write an attribute no other keyword read."""
    client = mongomock.MongoClient()
    manager = mongo_keywords.connection_manager
    manager.add_to_connection_pool(client["first_db"], "first")
    manager.add_to_connection_pool(client["second_db"], "second")

    mongo_keywords.switch_database(alias="second")
    mongo_keywords.insert_document("mycollection", {"key": "value"})

    assert mongo_keywords.count_documents("mycollection", alias="second", key="value") == 1
    assert mongo_keywords.count_documents("mycollection", alias="first", key="value") == 0


# --------------------------------------------------------------------------- #
# Robot Framework argument conversion
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "keyword_name",
    ["find_document", "delete_document", "delete_many", "count_documents"],
)
def test_free_query_arguments_keep_their_type(keyword_name):
    """Regression: annotating **params as `str` made RF coerce every query value.

    A `str` annotation turned `Delete Many  coll  count=${5}` into a query for the
    string "5", which matches nothing and reports a successful deletion of 0 documents.
    """
    spec = PythonArgumentParser(keyword_name).parse(getattr(MongoDBKeywords, keyword_name))

    _, named = spec.convert(["mycollection"], [("count", 5), ("active", True)])

    assert named == [("count", 5), ("active", True)]


def test_query_values_of_other_types_match(mongo):
    """The end-to-end consequence of the conversion above."""
    mongo.insert_document("mycollection", {"count": 5})

    assert mongo.count_documents("mycollection", count=5) == 1
    assert mongo.delete_many("mycollection", count=5) == 1


# --------------------------------------------------------------------------- #
# Assertion keywords
# --------------------------------------------------------------------------- #

def test_check_query_result(mongo):
    mongo.insert_document("mycollection", {"key": "value", "field": 42})

    mongo.check_query_result("mycollection", {"key": "value"}, AssertionOperator.equal, 42, "field")


def test_check_query_result_mismatch(mongo):
    mongo.insert_document("mycollection", {"key": "value", "field": 1})

    with pytest.raises(AssertionError, match="Field 'field' value mismatch:"):
        mongo.check_query_result("mycollection", {"key": "value"}, AssertionOperator.equal, 42, "field")


def test_check_query_result_no_results(mongo):
    with pytest.raises(AssertionError, match="Query returned no results."):
        mongo.check_query_result("mycollection", {"key": "value"}, AssertionOperator.equal, 42, "field")


def test_check_query_result_field_not_in_document(mongo):
    mongo.insert_document("mycollection", {"key": "value", "other_field": 42})

    with pytest.raises(AssertionError, match="Field 'field' not found in document."):
        mongo.check_query_result("mycollection", {"key": "value"}, AssertionOperator.equal, 42, "field")


def test_check_query_result_checks_every_matching_document(mongo):
    mongo.insert_document("mycollection", {"key": "value", "field": 42})
    mongo.insert_document("mycollection", {"key": "value", "field": 1})

    with pytest.raises(AssertionError, match="Field 'field' value mismatch:"):
        mongo.check_query_result("mycollection", {"key": "value"}, AssertionOperator.equal, 42, "field")


def test_check_query_result_invalid_operator(mongo):
    mongo.insert_document("mycollection", {"key": "value", "field": 42})

    with pytest.raises(RuntimeError, match="is not a valid assertion operator"):
        mongo.check_query_result("mycollection", {"key": "value"}, "invalid_operator", 42, "field")


def test_check_document_count(mongo):
    mongo.insert_document("mycollection", {"key": "value"})

    mongo.check_document_count("mycollection", {"key": "value"}, AssertionOperator.equal, 1)


def test_check_document_count_mismatch(mongo):
    with pytest.raises(AssertionError, match="Wrong document count:"):
        mongo.check_document_count("mycollection", {"key": "value"}, AssertionOperator.equal, 5)


def test_check_document_count_invalid_operator(mongo):
    with pytest.raises(RuntimeError, match="is not a valid assertion operator"):
        mongo.check_document_count("mycollection", {"key": "value"}, "invalid_operator", 5)


def test_check_document_count_retries_until_the_count_matches(mongo_keywords, mock_db):
    mock_db.__getitem__.return_value.count_documents.side_effect = [0, 0, 5]

    mongo_keywords.check_document_count(
        "mycollection", {}, AssertionOperator.equal, 5,
        retry_timeout="5 seconds", retry_pause="1 millisecond",
    )

    assert mock_db.__getitem__.return_value.count_documents.call_count == 3


@pytest.mark.parametrize("retry_pause", ["0 seconds", "1 millisecond"])
def test_check_document_count_honours_retry_timeout(mongo_keywords, mock_db, retry_pause):
    """Regression: the retry loop used to advance a counter by ``retry_pause``.

    With ``retry_pause=0`` that counter never advanced, so the timeout was never
    reached and the keyword hung forever. The attempt cap is deliberately generous —
    a zero pause polls very fast — and exists only so a regression fails instead of
    hanging the suite.
    """
    attempts = {"n": 0}

    def count_documents(_query):
        attempts["n"] += 1
        if attempts["n"] > 1_000_000:
            raise RuntimeError("retry loop did not honour retry_timeout")
        return 0

    mock_db.__getitem__.return_value.count_documents = count_documents
    started = time.monotonic()

    with pytest.raises(AssertionError, match="Wrong document count:"):
        mongo_keywords.check_document_count(
            "mycollection", {}, AssertionOperator.equal, 5,
            retry_timeout="100 milliseconds", retry_pause=retry_pause,
        )

    assert time.monotonic() - started < 5, "retry loop overran its timeout"


def test_check_query_result_honours_retry_timeout(mongo):
    with pytest.raises(AssertionError, match="Query returned no results."):
        mongo.check_query_result(
            "mycollection", {"key": "value"}, AssertionOperator.equal, 42, "field",
            retry_timeout="100 milliseconds", retry_pause="0 seconds",
        )


# --------------------------------------------------------------------------- #
# Distinct value assertions
# --------------------------------------------------------------------------- #

@pytest.fixture
def orders(mongo):
    """Three orders, two of them new."""
    mongo.insert_documents(
        "orders",
        [
            {"status": "new", "region": "eu"},
            {"status": "new", "region": "us"},
            {"status": "shipped", "region": "eu"},
        ],
    )
    return mongo


def test_check_distinct_values(orders):
    orders.check_distinct_values("orders", "status", AssertionOperator.equal, ["new", "shipped"])


def test_check_distinct_values_sorts_before_comparing(mongo_keywords, mock_db):
    """MongoDB does not define the order, so an expected list has to mean a set."""
    mock_db.__getitem__.return_value.distinct.return_value = ["shipped", "new"]

    mongo_keywords.check_distinct_values("orders", "status", AssertionOperator.equal, ["new", "shipped"])


def test_check_distinct_values_mismatch(orders):
    with pytest.raises(AssertionError, match="Wrong distinct values for field 'status':"):
        orders.check_distinct_values("orders", "status", AssertionOperator.equal, ["new"])


def test_check_distinct_values_narrowed_by_a_query(orders):
    orders.check_distinct_values(
        "orders", "status", AssertionOperator.equal, ["new"], query={"region": "us"}
    )


def test_check_distinct_values_can_assert_a_value_is_absent(orders):
    """The question counting cannot express: nothing is left in this state."""
    orders.check_distinct_values("orders", "status", AssertionOperator.contains, "new")

    with pytest.raises(AssertionError):
        orders.check_distinct_values("orders", "status", AssertionOperator.contains, "pending")


def test_check_distinct_values_honours_retry_timeout(mongo):
    with pytest.raises(AssertionError, match="Wrong distinct values"):
        mongo.check_distinct_values(
            "orders", "status", AssertionOperator.equal, ["new"],
            retry_timeout="100 milliseconds", retry_pause="0 seconds",
        )


# --------------------------------------------------------------------------- #
# Existence assertions
# --------------------------------------------------------------------------- #

def test_check_collection_exists(mongo):
    mongo.insert_document("orders", {"key": "value"})

    mongo.check_collection_exists("orders")


def test_check_collection_exists_reports_what_is_there(mongo):
    mongo.insert_document("orders", {"key": "value"})

    with pytest.raises(AssertionError, match=r"Collection 'absent' does not exist.*\['orders'\]"):
        mongo.check_collection_exists("absent")


def test_check_collection_exists_takes_a_custom_message(mongo):
    with pytest.raises(AssertionError, match="the migration did not run"):
        mongo.check_collection_exists("absent", assertion_message="the migration did not run")


def test_check_collection_exists_retries(mongo_keywords, mock_db):
    mock_db.list_collection_names.side_effect = [[], [], ["orders"]]

    mongo_keywords.check_collection_exists(
        "orders", retry_timeout="5 seconds", retry_pause="1 millisecond"
    )

    assert mock_db.list_collection_names.call_count == 3


def test_check_collection_exists_honours_retry_timeout(mongo):
    with pytest.raises(AssertionError, match="Collection 'absent' does not exist"):
        mongo.check_collection_exists(
            "absent", retry_timeout="100 milliseconds", retry_pause="0 seconds"
        )


def test_check_index_exists(mongo):
    mongo.insert_document("users", {"email": "a@example.test"})
    mongo.create_index("users", {"email": 1}, index_name="by_email")

    mongo.check_index_exists("users", "by_email")


def test_check_index_exists_reports_what_is_there(mongo):
    mongo.insert_document("users", {"email": "a@example.test"})

    with pytest.raises(AssertionError, match=r"Index 'by_email' does not exist.*\['_id_'\]"):
        mongo.check_index_exists("users", "by_email")


def test_check_index_exists_honours_retry_timeout(mongo):
    mongo.insert_document("users", {"email": "a@example.test"})

    with pytest.raises(AssertionError, match="Index 'by_email' does not exist"):
        mongo.check_index_exists(
            "users", "by_email", retry_timeout="100 milliseconds", retry_pause="0 seconds"
        )


def test_collection_should_have_index(mongo):
    mongo.insert_document("readings", {"_id": {"deviceId": "d", "date": 1}})
    mongo.create_index("readings", {"_id.deviceId": 1, "_id.date": 1})

    mongo.collection_should_have_index("readings", {"_id.deviceId": 1, "_id.date": 1})


def test_collection_should_have_index_ignores_the_derived_name(mongo):
    """The point of asking by fields: the same index under a name of someone's choosing."""
    mongo.insert_document("users", {"email": "a@example.test"})
    mongo.create_index("users", {"email": 1}, index_name="by_email")

    mongo.collection_should_have_index("users", {"email": 1})


def test_collection_should_have_index_reports_what_is_there(mongo):
    mongo.insert_document("users", {"email": "a@example.test"})

    with pytest.raises(AssertionError, match=r"No index on 'users' has keys.*It has: _id_ \{'_id': 1\}"):
        mongo.collection_should_have_index("users", {"email": 1})


def test_collection_should_have_index_is_field_order_sensitive(mongo):
    """A compound index serves its fields left to right, so the order is the index."""
    mongo.insert_document("readings", {"_id": {"deviceId": "d", "date": 1}})
    mongo.create_index("readings", {"_id.deviceId": 1, "_id.date": 1})

    with pytest.raises(AssertionError, match="No index on 'readings' has keys"):
        mongo.collection_should_have_index("readings", {"_id.date": 1, "_id.deviceId": 1})


def test_collection_should_have_index_takes_a_custom_message(mongo):
    mongo.insert_document("users", {"email": "a@example.test"})

    with pytest.raises(AssertionError, match="the login query needs this"):
        mongo.collection_should_have_index(
            "users", {"email": 1}, assertion_message="the login query needs this"
        )


def test_collection_should_have_index_honours_retry_timeout(mongo):
    mongo.insert_document("users", {"email": "a@example.test"})

    with pytest.raises(AssertionError, match="No index on 'users' has keys"):
        mongo.collection_should_have_index(
            "users", {"email": 1}, retry_timeout="100 milliseconds", retry_pause="0 seconds"
        )


def test_document_should_exist(mongo):
    mongo.insert_document("orders", {"order_id": "A-1"})

    mongo.document_should_exist("orders", order_id="A-1")


def test_document_should_exist_fails_with_the_query_in_the_message(mongo):
    with pytest.raises(AssertionError, match="No document in 'orders' matches"):
        mongo.document_should_exist("orders", order_id="A-1")


def test_document_should_exist_takes_a_custom_message(mongo):
    with pytest.raises(AssertionError, match="the order was never placed"):
        mongo.document_should_exist(
            "orders", assertion_message="the order was never placed", order_id="A-1"
        )


def test_document_should_exist_finds_its_target_by_string_id(mongo):
    doc_id = mongo.insert_document("orders", {"order_id": "A-1"})

    mongo.document_should_exist("orders", _id=str(doc_id))


def test_document_should_exist_retries(mongo_keywords, mock_db):
    mock_db.__getitem__.return_value.count_documents.side_effect = [0, 0, 1]

    mongo_keywords.document_should_exist(
        "orders", retry_timeout="5 seconds", retry_pause="1 millisecond", order_id="A-1"
    )

    assert mock_db.__getitem__.return_value.count_documents.call_count == 3


def test_document_should_exist_honours_retry_timeout(mongo):
    with pytest.raises(AssertionError, match="No document in 'orders' matches"):
        mongo.document_should_exist(
            "orders", retry_timeout="100 milliseconds", retry_pause="0 seconds", order_id="A-1"
        )


def test_document_should_not_exist(mongo):
    mongo.document_should_not_exist("orders", order_id="A-1")


def test_document_should_not_exist_reports_how_many_it_found(mongo):
    mongo.insert_documents("orders", [{"status": "pending"}, {"status": "pending"}])

    with pytest.raises(AssertionError, match="but found 2"):
        mongo.document_should_not_exist("orders", status="pending")


def test_document_should_not_exist_retries_until_the_document_goes(mongo_keywords, mock_db):
    mock_db.__getitem__.return_value.count_documents.side_effect = [1, 1, 0]

    mongo_keywords.document_should_not_exist(
        "orders", retry_timeout="5 seconds", retry_pause="1 millisecond", status="pending"
    )

    assert mock_db.__getitem__.return_value.count_documents.call_count == 3


def test_document_should_not_exist_honours_retry_timeout(mongo):
    mongo.insert_document("orders", {"status": "pending"})

    with pytest.raises(AssertionError, match="Expected no document"):
        mongo.document_should_not_exist(
            "orders", retry_timeout="100 milliseconds", retry_pause="0 seconds", status="pending"
        )


@pytest.mark.parametrize(
    "keyword_name",
    ["document_should_exist", "document_should_not_exist"],
)
def test_existence_assertions_keep_their_query_argument_types(keyword_name):
    """Free query arguments must not be coerced to strings, as the delete ones once were."""
    spec = PythonArgumentParser(keyword_name).parse(getattr(MongoDBKeywords, keyword_name))

    _, named = spec.convert(["mycollection"], [("count", 5), ("active", True)])

    assert named == [("count", 5), ("active", True)]


@pytest.mark.parametrize(
    "keyword_name, args, kwargs",
    [
        param("check_distinct_values", ("orders", "status", AssertionOperator.equal, []), {}, id="check_distinct"),
        param("check_collection_exists", ("orders",), {}, id="check_collection_exists"),
        param("check_index_exists", ("orders", "by_email"), {}, id="check_index_exists"),
        param("collection_should_have_index", ("orders", {"email": 1}), {}, id="collection_should_have_index"),
        param("document_should_exist", ("orders",), {"key": "value"}, id="document_should_exist"),
        param("document_should_not_exist", ("orders",), {"key": "value"}, id="document_should_not_exist"),
    ],
)
def test_missing_alias_raises_the_same_error_for_assertions(mongo_keywords, keyword_name, args, kwargs):
    with pytest.raises(KeyError, match="Alias 'missing_alias' not found in connection pool."):
        getattr(mongo_keywords, keyword_name)(*args, alias="missing_alias", **kwargs)
