"""Tests for the document, query and index keywords."""

import pytest
from bson import ObjectId
from pytest import param
from robot.utils import DotDict

# --------------------------------------------------------------------------- #
# ObjectId round-tripping
# --------------------------------------------------------------------------- #

def test_a_document_is_found_by_its_id_as_a_string(mongo):
    """Regression: Robot Framework hands back a document id as text.

    Insert Document returns an ObjectId. Once that value has been through a Robot
    variable, a CSV or a JSON fixture it is a string, and an uncoerced query for it
    matched nothing while reporting success.
    """
    doc_id = mongo.insert_document("mycollection", {"key": "value"})

    assert mongo.find_document("mycollection", _id=str(doc_id)) is not None
    assert mongo.find_document("mycollection", _id=doc_id) is not None


@pytest.mark.parametrize(
    "keyword_name, extra_args, expected",
    [
        param("count_documents", (), 1, id="count_documents"),
        param("delete_document", (), 1, id="delete_document"),
        param("delete_many", (), 1, id="delete_many"),
    ],
)
def test_id_as_a_string_works_for_free_argument_keywords(mongo, keyword_name, extra_args, expected):
    doc_id = mongo.insert_document("mycollection", {"key": "value"})

    result = getattr(mongo, keyword_name)("mycollection", *extra_args, _id=str(doc_id))

    assert result == expected


@pytest.mark.parametrize(
    "keyword_name",
    ["count_documents_with_query", "delete_documents_with_query", "find_document_with_query"],
)
def test_id_as_a_string_works_for_query_keywords(mongo, keyword_name):
    doc_id = mongo.insert_document("mycollection", {"key": "value"})

    assert getattr(mongo, keyword_name)("mycollection", {"_id": str(doc_id)})


def test_id_as_a_string_works_inside_an_in_operator(mongo):
    first = mongo.insert_document("mycollection", {"key": "a"})
    second = mongo.insert_document("mycollection", {"key": "b"})

    found = mongo.find_documents_with_query("mycollection", {"_id": {"$in": [str(first), str(second)]}})

    assert len(found) == 2


def test_a_string_that_is_not_an_object_id_is_left_alone(mongo):
    """A collection whose ids are ordinary strings must still be queryable."""
    mongo.insert_document("mycollection", {"_id": "not-an-object-id", "key": "value"})

    found = mongo.find_document("mycollection", _id="not-an-object-id")

    assert found["key"] == "value"


def test_update_document_finds_its_target_by_string_id(mongo):
    doc_id = mongo.insert_document("mycollection", {"key": "value"})

    updated = mongo.update_document("mycollection", {"_id": str(doc_id)}, {"key": "new_value"})

    assert updated["key"] == "new_value"


def test_coercion_is_on_by_default(mongo_keywords):
    assert mongo_keywords.coerce_object_ids is True


def test_coercion_can_be_switched_off(no_coercion):
    """With the option off, a string _id is passed through exactly as given."""
    doc_id = no_coercion.insert_document("mycollection", {"key": "value"})

    assert no_coercion.find_document("mycollection", _id=str(doc_id)) is None
    assert no_coercion.find_document("mycollection", _id=doc_id) is not None


def test_convert_to_object_id_is_the_route_when_coercion_is_off(no_coercion):
    """The documented workaround has to actually work."""
    doc_id = no_coercion.insert_document("mycollection", {"key": "value"})

    oid = no_coercion.convert_to_object_id(str(doc_id))

    assert no_coercion.find_document("mycollection", _id=oid) is not None


@pytest.mark.parametrize(
    "keyword_name, args",
    [
        param("count_documents_with_query", ("mycollection", {"_id": "6a7ccdea6abf6a4ebbc3514f"}), id="count_with_query"),
        param("find_documents_with_query", ("mycollection", {"_id": "6a7ccdea6abf6a4ebbc3514f"}), id="find_with_query"),
    ],
)
def test_coercion_off_applies_to_every_query_keyword(no_coercion, keyword_name, args):
    no_coercion.insert_document("mycollection", {"key": "value"})

    assert not getattr(no_coercion, keyword_name)(*args)


def test_the_library_passes_the_option_through():
    """The flag is set at import time, so it has to reach the keyword class."""
    from MongoDBLibrary import MongoDBLibrary

    assert MongoDBLibrary().keywords["find_document"].__self__.coerce_object_ids is True
    assert MongoDBLibrary(coerce_object_ids=False).keywords["find_document"].__self__.coerce_object_ids is False


def test_the_library_converts_the_option_from_a_robot_argument():
    """`Library  MongoDBLibrary  coerce_object_ids=${False}` must arrive as a boolean."""
    from robot.running.arguments import PythonArgumentParser

    from MongoDBLibrary import MongoDBLibrary

    spec = PythonArgumentParser("MongoDBLibrary").parse(MongoDBLibrary.__init__)

    _, named = spec.convert([], [("coerce_object_ids", "False")])

    assert named == [("coerce_object_ids", False)]


def test_convert_to_object_id(mongo):
    doc_id = mongo.insert_document("mycollection", {"key": "value"})

    converted = mongo.convert_to_object_id(str(doc_id))

    assert converted == doc_id
    assert isinstance(converted, ObjectId)


def test_convert_to_object_id_rejects_a_bad_value(mongo):
    with pytest.raises(Exception, match="24-character hex string|not a valid ObjectId"):
        mongo.convert_to_object_id("nonsense")


# --------------------------------------------------------------------------- #
# Return type consistency
# --------------------------------------------------------------------------- #

def test_every_document_returning_keyword_returns_a_dot_dict(mongo):
    """Regression: only find_document used to wrap its result.

    ``${doc.field}`` worked after a find and broke after an update or an aggregation.
    """
    mongo.insert_document("mycollection", {"key": "value", "items": ["a"]})

    results = {
        "find_document": mongo.find_document("mycollection", key="value"),
        "find_document_with_query": mongo.find_document_with_query("mycollection", {"key": "value"}),
        "find_documents": mongo.find_documents("mycollection", key="value")[0],
        "find_documents_with_query": mongo.find_documents_with_query("mycollection", {"key": "value"})[0],
        "execute_query": mongo.execute_query("mycollection", [{"$match": {"key": "value"}}])[0],
        "update_document": mongo.update_document("mycollection", {"key": "value"}, {"key": "value"}),
        "update_document_with_operators": mongo.update_document_with_operators(
            "mycollection", {"key": "value"}, {"$set": {"key": "value"}}
        ),
        "list_indexes": mongo.list_indexes("mycollection")[0],
    }

    not_wrapped = [name for name, value in results.items() if not isinstance(value, DotDict)]
    assert not_wrapped == []


def test_nested_documents_support_dot_access(mongo):
    mongo.insert_document("mycollection", {"key": "value", "nested": {"deep": 1}})

    found = mongo.find_document("mycollection", key="value")

    assert isinstance(found["nested"], DotDict)


def test_a_missing_document_is_still_none(mongo):
    assert mongo.find_document("mycollection", key="absent") is None
    assert mongo.find_document_with_query("mycollection", {"key": "absent"}) is None
    assert mongo.update_document("mycollection", {"key": "absent"}, {"key": "x"}) is None


# --------------------------------------------------------------------------- #
# Reading many documents
# --------------------------------------------------------------------------- #

@pytest.fixture
def scored(mongo):
    """Three documents with scores 1, 5 and 10."""
    mongo.insert_documents(
        "mycollection",
        [{"key": "a", "score": 1}, {"key": "b", "score": 5}, {"key": "c", "score": 10}],
    )
    return mongo


def test_find_documents_returns_everything_when_given_no_parameters(scored):
    assert len(scored.find_documents("mycollection")) == 3


def test_find_documents_filters(scored):
    assert [d["score"] for d in scored.find_documents("mycollection", key="b")] == [5]


def test_find_documents_returns_an_empty_list_when_nothing_matches(scored):
    assert scored.find_documents("mycollection", key="absent") == []


def test_find_documents_sorts(scored):
    assert [d["score"] for d in scored.find_documents("mycollection", sort={"score": -1})] == [10, 5, 1]


def test_find_documents_limits(scored):
    assert len(scored.find_documents("mycollection", sort={"score": 1}, limit=2)) == 2


def test_find_documents_skips(scored):
    found = scored.find_documents("mycollection", sort={"score": 1}, skip=1)

    assert [d["score"] for d in found] == [5, 10]


def test_find_documents_projects(scored):
    found = scored.find_documents("mycollection", key="a", projection={"score": 1})

    assert sorted(found[0].keys()) == ["_id", "score"]


def test_find_documents_with_query_uses_operators(scored):
    found = scored.find_documents_with_query("mycollection", {"score": {"$gte": 5}}, sort={"score": 1})

    assert [d["score"] for d in found] == [5, 10]


def test_find_document_with_query_returns_the_first_match_in_sort_order(scored):
    assert scored.find_document_with_query("mycollection", {}, sort={"score": -1})["score"] == 10


def test_count_documents_with_query_uses_operators(scored):
    assert scored.count_documents_with_query("mycollection", {"score": {"$gte": 5}}) == 2


def test_count_documents_with_query_counts_everything_for_an_empty_query(scored):
    assert scored.count_documents_with_query("mycollection", {}) == 3


def test_execute_query_rejects_a_non_list_pipeline(mongo):
    with pytest.raises(TypeError, match="Invalid pipeline"):
        mongo.execute_query("mycollection", pipeline="not-a-pipeline")


def test_execute_query_allowing_disk_use(scored):
    found = scored.execute_query("mycollection", [{"$match": {"score": 10}}], allow_disk_use=True)

    assert [d["key"] for d in found] == ["c"]


def test_allow_disk_use_is_left_out_of_the_call_when_off(mongo_keywords, mock_db):
    """The option is only meaningful on a real server, so an old one is never sent it."""
    mock_db.__getitem__.return_value.aggregate.return_value = []

    mongo_keywords.execute_query("mycollection", [])

    assert mock_db.__getitem__.return_value.aggregate.call_args.kwargs == {}


def test_count_documents_limits(scored):
    """A limit answers 'are there at least N' without counting the whole collection."""
    assert scored.count_documents("mycollection", limit=2) == 2


def test_count_documents_skips(scored):
    assert scored.count_documents("mycollection", skip=1) == 2


def test_count_documents_with_query_limits(scored):
    assert scored.count_documents_with_query("mycollection", {"score": {"$gte": 1}}, limit=1) == 1


def test_a_zero_limit_counts_everything(scored):
    """Regression guard: count_documents rejects limit=0, so the default must be omitted."""
    assert scored.count_documents("mycollection", limit=0, skip=0) == 3
    assert scored.count_documents_with_query("mycollection", {}, limit=0, skip=0) == 3


def test_get_estimated_document_count(scored):
    assert scored.get_estimated_document_count("mycollection") == 3


# --------------------------------------------------------------------------- #
# Distinct values
# --------------------------------------------------------------------------- #

def test_get_distinct_values_returns_each_value_once(mongo):
    mongo.insert_documents(
        "mycollection",
        [{"status": "new"}, {"status": "new"}, {"status": "shipped"}],
    )

    assert sorted(mongo.get_distinct_values("mycollection", "status")) == ["new", "shipped"]


def test_get_distinct_values_narrowed_by_a_query(mongo):
    mongo.insert_documents(
        "mycollection",
        [{"status": "new", "region": "eu"}, {"status": "shipped", "region": "us"}],
    )

    found = mongo.get_distinct_values("mycollection", "status", query={"region": "eu"})

    assert found == ["new"]


def test_get_distinct_values_of_an_absent_field_is_empty(mongo):
    mongo.insert_document("mycollection", {"key": "value"})

    assert mongo.get_distinct_values("mycollection", "absent") == []


def test_get_distinct_values_coerces_an_id_in_its_query(mongo):
    doc_id = mongo.insert_document("mycollection", {"status": "new"})

    assert mongo.get_distinct_values("mycollection", "status", query={"_id": str(doc_id)}) == ["new"]


# --------------------------------------------------------------------------- #
# Writing many documents
# --------------------------------------------------------------------------- #

def test_insert_documents(mongo):
    ids = mongo.insert_documents("mycollection", [{"key": "a"}, {"key": "b"}])

    assert len(ids) == 2
    assert mongo.count_documents("mycollection") == 2


def test_update_documents_changes_every_match(mongo):
    mongo.insert_documents("mycollection", [{"key": "v"}, {"key": "v"}, {"key": "other"}])

    changed = mongo.update_documents("mycollection", {"key": "v"}, {"checked": True})

    assert changed == 2
    assert mongo.count_documents("mycollection", checked=True) == 2


def test_update_documents_reports_zero_when_nothing_matches(mongo):
    assert mongo.update_documents("mycollection", {"key": "absent"}, {"checked": True}) == 0


def test_update_documents_with_operators(mongo):
    mongo.insert_documents("mycollection", [{"key": "v", "n": 1}, {"key": "v", "n": 2}])

    changed = mongo.update_documents_with_operators("mycollection", {"key": "v"}, {"$inc": {"n": 10}})

    assert changed == 2
    assert sorted(d["n"] for d in mongo.find_documents("mycollection")) == [11, 12]


def test_insert_documents_unordered_still_returns_every_id(mongo):
    ids = mongo.insert_documents("mycollection", [{"key": "a"}, {"key": "b"}], ordered=False)

    assert len(ids) == 2


def test_an_unordered_insert_keeps_going_past_a_failure(mongo):
    """The point of ordered=False: one bad document does not discard the rest."""
    mongo.create_index("mycollection", {"key": 1}, unique=True)
    mongo.insert_document("mycollection", {"key": "b"})

    with pytest.raises(Exception, match="duplicate|E11000"):
        mongo.insert_documents(
            "mycollection",
            [{"key": "a"}, {"key": "b"}, {"key": "c"}],
            ordered=False,
        )

    assert sorted(d["key"] for d in mongo.find_documents("mycollection")) == ["a", "b", "c"]


def test_an_ordered_insert_stops_at_the_failure(mongo):
    mongo.create_index("mycollection", {"key": 1}, unique=True)
    mongo.insert_document("mycollection", {"key": "b"})

    with pytest.raises(Exception, match="duplicate|E11000"):
        mongo.insert_documents("mycollection", [{"key": "a"}, {"key": "b"}, {"key": "c"}])

    assert sorted(d["key"] for d in mongo.find_documents("mycollection")) == ["a", "b"]


# --------------------------------------------------------------------------- #
# Upserting
# --------------------------------------------------------------------------- #

def test_update_document_inserts_when_nothing_matches_and_upsert_is_on(mongo):
    document = mongo.update_document(
        "mycollection", {"email": "a@example.test"}, {"active": True}, upsert=True
    )

    assert document["email"] == "a@example.test"
    assert document["active"] is True


def test_update_document_without_upsert_still_returns_none(mongo):
    assert mongo.update_document("mycollection", {"email": "a@example.test"}, {"active": True}) is None


def test_upserting_twice_updates_rather_than_duplicating(mongo):
    """The point of upsert: a fixture step that does not care whether it has run."""
    for _ in range(2):
        mongo.update_document("mycollection", {"email": "a@example.test"}, {"active": True}, upsert=True)

    assert mongo.count_documents("mycollection", email="a@example.test") == 1


def test_update_document_with_operators_upserts(mongo):
    document = mongo.update_document_with_operators(
        "mycollection", {"key": "v"}, {"$inc": {"n": 5}}, upsert=True
    )

    assert document["n"] == 5


def test_update_documents_upserts_and_reports_no_change(mongo):
    """An upserted document was inserted, not modified, so modified_count is 0."""
    changed = mongo.update_documents("mycollection", {"key": "v"}, {"checked": True}, upsert=True)

    assert changed == 0
    assert mongo.count_documents("mycollection", key="v") == 1


def test_update_documents_with_operators_upserts(mongo):
    changed = mongo.update_documents_with_operators(
        "mycollection", {"key": "v"}, {"$inc": {"n": 1}}, upsert=True
    )

    assert changed == 0
    assert mongo.find_document("mycollection", key="v")["n"] == 1


# --------------------------------------------------------------------------- #
# Replacing
# --------------------------------------------------------------------------- #

def test_replace_document_removes_the_fields_it_does_not_mention(mongo):
    """The difference from Update Document, which can only ever add or overwrite."""
    mongo.insert_document("mycollection", {"key": "v", "stale": "gone"})

    replaced = mongo.replace_document("mycollection", {"key": "v"}, {"key": "v"})

    assert "stale" not in replaced


def test_replace_document_keeps_the_id(mongo):
    doc_id = mongo.insert_document("mycollection", {"key": "v"})

    replaced = mongo.replace_document("mycollection", {"key": "v"}, {"key": "other"})

    assert replaced["_id"] == doc_id


def test_replace_document_returns_none_when_nothing_matches(mongo):
    assert mongo.replace_document("mycollection", {"key": "absent"}, {"key": "new"}) is None


def test_replace_document_upserts(mongo):
    replaced = mongo.replace_document("mycollection", {"key": "absent"}, {"key": "new"}, upsert=True)

    assert replaced["key"] == "new"


def test_replace_document_finds_its_target_by_string_id(mongo):
    doc_id = mongo.insert_document("mycollection", {"key": "v"})

    replaced = mongo.replace_document("mycollection", {"_id": str(doc_id)}, {"key": "other"})

    assert replaced["key"] == "other"


def test_replace_document_returns_a_dot_accessible_document(mongo):
    mongo.insert_document("mycollection", {"key": "v"})

    replaced = mongo.replace_document("mycollection", {"key": "v"}, {"key": "other"})

    assert isinstance(replaced, DotDict)


# --------------------------------------------------------------------------- #
# Deleting and returning
# --------------------------------------------------------------------------- #

def test_delete_document_and_return_it_gives_back_what_it_deleted(mongo):
    mongo.insert_document("mycollection", {"key": "v", "payload": 42})

    deleted = mongo.delete_document_and_return_it("mycollection", key="v")

    assert deleted["payload"] == 42
    assert mongo.count_documents("mycollection") == 0


def test_delete_document_and_return_it_returns_none_when_nothing_matches(mongo):
    assert mongo.delete_document_and_return_it("mycollection", key="absent") is None


def test_delete_document_and_return_it_takes_only_one(mongo):
    mongo.insert_documents("mycollection", [{"key": "v"}, {"key": "v"}])

    mongo.delete_document_and_return_it("mycollection", key="v")

    assert mongo.count_documents("mycollection", key="v") == 1


def test_delete_document_and_return_it_finds_its_target_by_string_id(mongo):
    doc_id = mongo.insert_document("mycollection", {"key": "v"})

    assert mongo.delete_document_and_return_it("mycollection", _id=str(doc_id))["key"] == "v"


def test_delete_document_and_return_it_returns_a_dot_accessible_document(mongo):
    mongo.insert_document("mycollection", {"key": "v"})

    assert isinstance(mongo.delete_document_and_return_it("mycollection", key="v"), DotDict)


# --------------------------------------------------------------------------- #
# Indexes
# --------------------------------------------------------------------------- #

def test_every_collection_starts_with_only_the_id_index(mongo):
    mongo.insert_document("mycollection", {"key": "value"})

    assert [index["name"] for index in mongo.list_indexes("mycollection")] == ["_id_"]


def test_create_index_returns_its_name(mongo):
    mongo.insert_document("mycollection", {"email": "a@example.test"})

    name = mongo.create_index("mycollection", {"email": 1})

    assert name in [index["name"] for index in mongo.list_indexes("mycollection")]


def test_create_index_with_an_explicit_name(mongo):
    mongo.insert_document("mycollection", {"email": "a@example.test"})

    assert mongo.create_index("mycollection", {"email": 1}, index_name="by_email") == "by_email"


def test_a_unique_index_rejects_a_duplicate(mongo):
    mongo.insert_document("mycollection", {"email": "a@example.test"})
    mongo.create_index("mycollection", {"email": 1}, unique=True)

    with pytest.raises(Exception, match="duplicate|E11000"):
        mongo.insert_document("mycollection", {"email": "a@example.test"})


def test_drop_index(mongo):
    mongo.insert_document("mycollection", {"email": "a@example.test"})
    mongo.create_index("mycollection", {"email": 1}, index_name="by_email")

    mongo.drop_index("mycollection", "by_email")

    assert [index["name"] for index in mongo.list_indexes("mycollection")] == ["_id_"]


def test_a_sparse_unique_index_allows_many_documents_without_the_field(mongo):
    """Without sparse, a second document missing the field is a duplicate null."""
    mongo.create_index("mycollection", {"email": 1}, unique=True, sparse=True)

    mongo.insert_documents("mycollection", [{"key": "a"}, {"key": "b"}])

    assert mongo.count_documents("mycollection") == 2


@pytest.mark.parametrize(
    "kwargs, expected_option, expected_value",
    [
        param({"expire_after_seconds": 3600}, "expireAfterSeconds", 3600, id="ttl"),
        param(
            {"partial_filter_expression": {"status": "active"}},
            "partialFilterExpression",
            {"status": "active"},
            id="partial",
        ),
    ],
)
def test_create_index_passes_its_options_through(mongo_keywords, mock_db, kwargs, expected_option, expected_value):
    """mongomock accepts these options but does not record them, so check the call."""
    mongo_keywords.create_index("mycollection", {"created": 1}, **kwargs)

    passed = mock_db.__getitem__.return_value.create_index.call_args.kwargs

    assert passed[expected_option] == expected_value


def test_create_index_omits_a_ttl_it_was_not_given(mongo_keywords, mock_db):
    mongo_keywords.create_index("mycollection", {"created": 1})

    assert "expireAfterSeconds" not in mock_db.__getitem__.return_value.create_index.call_args.kwargs


def test_get_index_information_is_keyed_by_index_name(mongo):
    mongo.create_index("mycollection", {"email": 1}, index_name="by_email")

    information = mongo.get_index_information("mycollection")

    assert sorted(information) == ["_id_", "by_email"]


def test_drop_all_indexes_leaves_only_the_id_index(mongo):
    mongo.insert_document("mycollection", {"email": "a@example.test"})
    mongo.create_index("mycollection", {"email": 1})
    mongo.create_index("mycollection", {"name": 1})

    mongo.drop_all_indexes("mycollection")

    assert [index["name"] for index in mongo.list_indexes("mycollection")] == ["_id_"]


# --------------------------------------------------------------------------- #
# Alias handling for the new keywords
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "keyword_name, args, kwargs",
    [
        param("insert_documents", ("mycollection", [{"key": "value"}]), {}, id="insert_documents"),
        param("find_documents", ("mycollection",), {"key": "value"}, id="find_documents"),
        param("find_document_with_query", ("mycollection", {}), {}, id="find_document_with_query"),
        param("find_documents_with_query", ("mycollection", {}), {}, id="find_documents_with_query"),
        param("count_documents_with_query", ("mycollection", {}), {}, id="count_documents_with_query"),
        param("update_documents", ("mycollection", {}, {}), {}, id="update_documents"),
        param("update_documents_with_operators", ("mycollection", {}, {}), {}, id="update_with_operators"),
        param("create_index", ("mycollection", {"key": 1}), {}, id="create_index"),
        param("list_indexes", ("mycollection",), {}, id="list_indexes"),
        param("drop_index", ("mycollection", "key_1"), {}, id="drop_index"),
        param("get_index_information", ("mycollection",), {}, id="get_index_information"),
        param("drop_all_indexes", ("mycollection",), {}, id="drop_all_indexes"),
        param("get_distinct_values", ("mycollection", "key"), {}, id="get_distinct_values"),
        param("get_estimated_document_count", ("mycollection",), {}, id="estimated_count"),
        param("replace_document", ("mycollection", {}, {}), {}, id="replace_document"),
        param("delete_document_and_return_it", ("mycollection",), {"key": "v"}, id="delete_and_return"),
    ],
)
def test_missing_alias_raises_the_same_error_everywhere(mongo_keywords, keyword_name, args, kwargs):
    with pytest.raises(KeyError, match="Alias 'missing_alias' not found in connection pool."):
        getattr(mongo_keywords, keyword_name)(*args, alias="missing_alias", **kwargs)
