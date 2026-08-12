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
    ],
)
def test_missing_alias_raises_the_same_error_everywhere(mongo_keywords, keyword_name, args, kwargs):
    with pytest.raises(KeyError, match="Alias 'missing_alias' not found in connection pool."):
        getattr(mongo_keywords, keyword_name)(*args, alias="missing_alias", **kwargs)
