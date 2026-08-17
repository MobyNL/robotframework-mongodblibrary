"""Tests for reading documents from files: Load Document and Insert Document From File."""

import datetime

import pytest
from bson import ObjectId
from pytest import param
from robot.errors import VariableError
from robot.libraries.BuiltIn import RobotNotRunningError
from robot.utils import DotDict
from robot.variables import Variables

from MongoDBLibrary.keywords import MongoDBKeywords

OID = "6a7ccdea6abf6a4ebbc3514f"


@pytest.fixture
def documents(tmp_path):
    """A directory to write document files into."""
    directory = tmp_path / "documents"
    directory.mkdir()
    return directory


@pytest.fixture
def write(documents):
    """Write a document file and return its bare name."""

    def write_document(name, text):
        (documents / name).write_text(text, encoding="utf-8")
        return name

    return write_document


@pytest.fixture
def suite_variables(mocker):
    """Robot Framework's own variable scope, standing in for a running suite.

    Substitution is exercised against `robot.variables.Variables` rather than a stub, so
    the tests see Robot Framework's real behaviour: how it renders a value inside a larger
    string, and what it raises for a name that is not there.
    """
    variables = Variables()
    builtin = mocker.patch("MongoDBLibrary.documents.BuiltIn").return_value
    builtin.replace_variables.side_effect = variables.replace_scalar
    return variables


@pytest.fixture
def loader(connection_manager, documents):
    """Keywords that look documents up in the document directory."""
    return MongoDBKeywords(connection_manager, document_path=str(documents))


# --------------------------------------------------------------------------- #
# Finding the file
# --------------------------------------------------------------------------- #

def test_a_bare_file_name_is_resolved_against_the_document_path(loader, write):
    write("order.json", '{"status": "new"}')

    assert loader.load_document("order.json") == {"status": "new"}


def test_a_path_still_works_without_a_document_path(connection_manager, documents, write):
    write("order.json", '{"status": "new"}')
    keywords = MongoDBKeywords(connection_manager)

    assert keywords.load_document(str(documents / "order.json")) == {"status": "new"}


def test_a_path_is_used_as_written_even_when_a_document_path_is_set(loader, tmp_path):
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_text('{"status": "elsewhere"}', encoding="utf-8")

    assert loader.load_document(str(elsewhere)) == {"status": "elsewhere"}


def test_a_missing_file_reports_where_it_looked(loader, documents):
    with pytest.raises(ValueError) as error:
        loader.load_document("missing.json")

    assert "missing.json" in str(error.value)
    assert str(documents / "missing.json") in str(error.value)


# --------------------------------------------------------------------------- #
# Extended JSON
# --------------------------------------------------------------------------- #

def test_extended_json_types_become_the_types_mongodb_stores(loader, write):
    write(
        "order.json",
        """
        {
            "_id": {"$oid": "%s"},
            "placedAt": {"$date": "2026-03-01T09:30:00Z"},
            "quantity": {"$numberInt": "3"},
            "total": {"$numberDouble": "42.50"}
        }
        """ % OID,
    )

    document = loader.load_document("order.json")

    assert document["_id"] == ObjectId(OID)
    assert document["placedAt"] == datetime.datetime(2026, 3, 1, 9, 30)
    assert isinstance(document["quantity"], int) and document["quantity"] == 3
    assert isinstance(document["total"], float) and document["total"] == 42.50


def test_plain_json_values_keep_their_natural_types(loader, write):
    write("order.json", '{"status": "new", "lines": 2, "total": 1.5, "paid": true, "note": null}')

    document = loader.load_document("order.json")

    assert document == {"status": "new", "lines": 2, "total": 1.5, "paid": True, "note": None}
    assert isinstance(document["lines"], int)
    assert isinstance(document["total"], float)


def test_update_operators_are_passed_through(loader, write):
    """A ``$``-prefixed operator is not an extended type, so an update file works too."""
    write(
        "ship.json",
        '{"$set": {"status": "shipped", "shippedAt": {"$date": "2026-03-02T00:00:00Z"}},'
        ' "$push": {"events": "shipped"}, "$inc": {"revision": 1}}',
    )

    document = loader.load_document("ship.json")

    assert set(document) == {"$set", "$push", "$inc"}
    assert document["$set"]["status"] == "shipped"
    assert document["$set"]["shippedAt"] == datetime.datetime(2026, 3, 2, 0, 0)
    assert document["$push"] == {"events": "shipped"}
    assert document["$inc"] == {"revision": 1}


def test_invalid_json_reports_the_file_with_the_line_and_column(loader, write):
    write("order.json", '{\n    "status": "new",\n}')

    with pytest.raises(ValueError) as error:
        loader.load_document("order.json")

    assert "order.json" in str(error.value)
    assert "line 3" in str(error.value)
    assert "column 1" in str(error.value)


def test_a_value_extended_json_cannot_read_surfaces_its_own_error(loader, write):
    """A literal ``$date`` holding something that is not a date is json_util's failure."""
    write("order.json", '{"placedAt": {"$date": "yesterday"}}')

    with pytest.raises(ValueError) as error:
        loader.load_document("order.json")

    assert "order.json" in str(error.value)
    assert "yesterday" in str(error.value)


def test_a_file_that_does_not_hold_an_object_is_reported(loader, write):
    write("orders.json", '[{"status": "new"}]')

    with pytest.raises(ValueError, match="orders.json"):
        loader.load_document("orders.json")


# --------------------------------------------------------------------------- #
# Suite variables, written ${...}
# --------------------------------------------------------------------------- #

def test_variables_are_replaced_from_the_suite_scope(loader, write, suite_variables):
    suite_variables["${EMAIL}"] = "a@example.test"
    suite_variables["${QUANTITY}"] = 3
    write("order.json", '{"email": "${EMAIL}", "quantity": ${QUANTITY}}')

    assert loader.load_document("order.json") == {"email": "a@example.test", "quantity": 3}


def test_a_variable_can_carry_an_extended_json_value(loader, write, suite_variables):
    suite_variables["${CUSTOMER_ID}"] = OID
    write("order.json", '{"customerId": {"$oid": "${CUSTOMER_ID}"}}')

    assert loader.load_document("order.json") == {"customerId": ObjectId(OID)}


def test_an_undefined_variable_fails_with_the_file_and_the_variable(loader, write, suite_variables):
    write("order.json", '{"email": "${EMAIL}"}')

    with pytest.raises(ValueError) as error:
        loader.load_document("order.json")

    assert "order.json" in str(error.value)
    assert "EMAIL" in str(error.value)
    assert isinstance(error.value.__cause__, VariableError)


def test_a_file_without_variables_needs_no_running_suite(loader, write):
    """Nothing to substitute, so nothing asks Robot Framework for a variable scope."""
    write("order.json", '{"status": "new"}')

    assert loader.load_document("order.json") == {"status": "new"}


def test_a_variable_outside_a_running_suite_is_reported_as_such(loader, write):
    write("order.json", '{"email": "${EMAIL}"}')

    with pytest.raises(ValueError) as error:
        loader.load_document("order.json")

    assert "order.json" in str(error.value)
    assert isinstance(error.value.__cause__, RobotNotRunningError)


def test_a_whole_file_variable_resolves_to_the_variable_itself(loader, write, suite_variables):
    suite_variables["${ORDER}"] = {"status": "new", "lines": [{"quantity": 1}]}
    write("order.json", "${ORDER}")

    assert loader.load_document("order.json") == {"status": "new", "lines": [{"quantity": 1}]}


def test_overriding_a_whole_file_variable_leaves_the_variable_alone(loader, write, suite_variables):
    original = {"status": "new", "lines": [{"quantity": 1}]}
    suite_variables["${ORDER}"] = original
    write("order.json", "${ORDER}")

    loader.load_document("order.json", **{"lines.0.quantity": "5"})

    assert original == {"status": "new", "lines": [{"quantity": 1}]}


# --------------------------------------------------------------------------- #
# Placeholders, written {...} and filled from the keyword's arguments
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "given, expected",
    [
        param("Mark", "Mark", id="text"),
        param("3", 3, id="a whole number written as text"),
        param("0.8", 0.8, id="a number written as text"),
        param(3, 3, id="an int"),
        param(True, True, id="a boolean"),
        param(None, None, id="none"),
        param(ObjectId(OID), ObjectId(OID), id="an object id"),
        param(datetime.datetime(2026, 3, 1, 9, 30), datetime.datetime(2026, 3, 1, 9, 30), id="a datetime"),
        param('a "quoted" \\ mess', 'a "quoted" \\ mess', id="text needing json escaping"),
    ],
)
def test_a_whole_string_placeholder_takes_the_values_own_type(loader, write, given, expected):
    """The rule that lets a template stay valid JSON and still carry a non-string."""
    write("order.json", '{"field": "{field}"}')

    document = loader.load_document("order.json", field=given)

    assert document["field"] == expected
    assert type(document["field"]) is type(expected)


def test_a_placeholder_inside_a_longer_string_is_interpolated_as_text(loader, write):
    write("order.json", '{"reference": "REF-{n}/{suffix}"}')

    assert loader.load_document("order.json", n=7, suffix="a")["reference"] == "REF-7/a"


def test_text_interpolated_into_a_string_is_escaped_for_one(loader, write):
    write("order.json", '{"reference": "REF-{n}"}')

    assert loader.load_document("order.json", n='a "quoted" \\ mess')["reference"] == 'REF-a "quoted" \\ mess'


def test_an_unquoted_placeholder_is_filled_too(loader, write):
    """Not valid JSON before it is filled, which is why the quoted form is documented."""
    write("order.json", '{"quantity": {quantity}}')

    assert loader.load_document("order.json", quantity="3")["quantity"] == 3


def test_one_placeholder_can_appear_more_than_once(loader, write):
    write("order.json", '{"unique_id": "{name}", "slug": "order-{name}", "nested": {"also": "{name}"}}')

    document = loader.load_document("order.json", name="a1")

    assert document == {"unique_id": "a1", "slug": "order-a1", "nested": {"also": "a1"}}


def test_a_placeholder_can_fill_an_extended_json_wrapper(loader, write):
    """Filling the text inside ``$date``, for a value that arrives as a string."""
    write("order.json", '{"placedAt": {"$date": "{placed_at}"}}')

    document = loader.load_document("order.json", placed_at="2026-03-01T09:30:00Z")

    assert document["placedAt"] == datetime.datetime(2026, 3, 1, 9, 30)


def test_a_placeholder_can_stand_in_for_a_field_name(loader, write):
    write("order.json", '{"{field}": "new"}')

    assert loader.load_document("order.json", field="status") == {"status": "new"}


def test_double_braces_inside_a_string_are_a_literal_brace(loader, write):
    """How a document that genuinely holds ``{word}`` in a string says so."""
    write("order.json", '{"template": "{{unfilled}}", "filled": "{filled}"}')

    document = loader.load_document("order.json", filled="yes")

    assert document == {"template": "{unfilled}", "filled": "yes"}


def test_the_braces_json_itself_uses_are_left_alone(loader, write):
    """Regression: unescaping ``}}`` outside a string would close nothing correctly.

    A nested object ends in ``}}`` and an empty one is ``{}``. Neither is a placeholder,
    and neither may be rewritten by the escape handling.
    """
    write("order.json", '{"a": {"b": {"c": 1}}, "empty": {}, "list": [{"sku": "A-1"}]}')

    document = loader.load_document("order.json")

    assert document == {"a": {"b": {"c": 1}}, "empty": {}, "list": [{"sku": "A-1"}]}


def test_a_file_with_no_placeholders_and_no_arguments_is_unchanged(loader, write):
    write("order.json", '{"status": "new", "lines": [{"sku": "A-1"}]}')

    assert loader.load_document("order.json") == {"status": "new", "lines": [{"sku": "A-1"}]}


def test_an_unfilled_placeholder_fails_with_the_file_and_the_holes(loader, write):
    """The literal text ``{unique_id}`` is insertable, so leaving it would seed bad data."""
    write("order.json", '{"unique_id": "{unique_id}", "customerId": "{customerId}", "status": "new"}')

    with pytest.raises(ValueError) as error:
        loader.load_document("order.json", customerId=OID)

    assert "order.json" in str(error.value)
    assert "{unique_id}" in str(error.value)
    assert "{customerId}" not in str(error.value)
    assert "Given: customerId" in str(error.value)


def test_every_unfilled_placeholder_is_reported_at_once(loader, write):
    write("order.json", '{"a": "{first}", "b": "{second}"}')

    with pytest.raises(ValueError) as error:
        loader.load_document("order.json")

    assert "{first}, {second}" in str(error.value)
    assert "Given: nothing" in str(error.value)


def test_a_repeated_unfilled_placeholder_is_reported_once(loader, write):
    write("order.json", '{"a": "{name}", "b": "order-{name}"}')

    with pytest.raises(ValueError) as error:
        loader.load_document("order.json")

    assert str(error.value).count("{name}") == 1


def test_an_escape_in_the_files_own_json_survives_filling(loader, write):
    r"""The scan has to step over ``\"`` rather than read it as the end of the string."""
    write("order.json", r'{"note": "a \" quote, a \\ backslash and {n}"}')

    assert loader.load_document("order.json", n=7)["note"] == 'a " quote, a \\ backslash and 7'


def test_a_placeholder_wins_over_a_field_of_the_same_name(loader, write):
    """The file declared the hole, so filling it is what was meant."""
    write("order.json", '{"status": "{status}", "note": "unfilled is impossible"}')

    assert loader.load_document("order.json", status="shipped")["status"] == "shipped"


def test_an_argument_that_is_neither_a_placeholder_nor_a_field_names_both(loader, write):
    write("order.json", '{"status": "{status}", "total": 1.0}')

    with pytest.raises(ValueError) as error:
        loader.load_document("order.json", status="new", totl="2.0")

    assert "order.json" in str(error.value)
    assert "'totl' is neither" in str(error.value)
    assert "Placeholders: {status}" in str(error.value)
    assert "Fields: status, total" in str(error.value)


def test_placeholders_and_dotted_overrides_work_in_one_call(loader, write):
    write("order.json", '{"unique_id": "{unique_id}", "status": "new", "lines": [{"quantity": 1}]}')

    document = loader.load_document("order.json", unique_id="a1", status="shipped",
                                    **{"lines.0.quantity": "3"})

    assert document == {"unique_id": "a1", "status": "shipped", "lines": [{"quantity": 3}]}


def test_suite_variables_are_substituted_before_placeholders_are_filled(loader, write, suite_variables):
    """So an argument's value is inserted last and is never resolved as a variable itself."""
    suite_variables["${EMAIL}"] = "a@example.test"
    write("order.json", '{"email": "${EMAIL}", "note": "{note}"}')

    document = loader.load_document("order.json", note="${NOT_A_VARIABLE}")

    assert document == {"email": "a@example.test", "note": "${NOT_A_VARIABLE}"}


def test_braces_from_a_variables_value_are_data(loader, write, suite_variables):
    """A placeholder is something the file says, so a value that holds braces holds text.

    Substitution runs first, so without this the value would be scanned as a template and
    the keyword would fail on a hole the file never declared.
    """
    suite_variables["${GREETING}"] = "Hi {first_name}"
    write("order.json", '{"note": "${GREETING}"}')

    assert loader.load_document("order.json") == {"note": "Hi {first_name}"}


def test_braces_from_a_variables_value_are_not_filled_by_an_argument(loader, write, suite_variables):
    """Even when an argument happens to be named after them, so the order cannot be used.

    The name is no argument of the file's, so it is read as an override path instead,
    which is what names the mistake.
    """
    suite_variables["${GREETING}"] = "Hi {first_name}"
    write("order.json", '{"note": "${GREETING}"}')

    with pytest.raises(ValueError) as error:
        loader.load_document("order.json", first_name="Ada")

    assert "'first_name' is neither" in str(error.value)


def test_a_placeholder_the_file_declares_is_still_filled_after_substitution(loader, write, suite_variables):
    """The regression the two tests above must not cause."""
    suite_variables["${EMAIL}"] = "a@example.test"
    write("order.json", '{"email": "${EMAIL}", "status": "{status}"}')

    document = loader.load_document("order.json", status="new")

    assert document == {"email": "a@example.test", "status": "new"}


def test_a_whole_file_variable_takes_its_arguments_as_overrides(loader, write, suite_variables):
    """There is no text to fill, so every argument is a path into the object."""
    suite_variables["${ORDER}"] = {"status": "new"}
    write("order.json", "${ORDER}")

    assert loader.load_document("order.json", status="shipped") == {"status": "shipped"}


# --------------------------------------------------------------------------- #
# Overrides
# --------------------------------------------------------------------------- #

def test_a_top_level_field_is_overridden(loader, write):
    write("order.json", '{"status": "new", "total": 1.0}')

    assert loader.load_document("order.json", status="shipped") == {"status": "shipped", "total": 1.0}


def test_a_nested_field_is_overridden_without_rebuilding_the_document(loader, write):
    write("order.json", '{"customer": {"name": "A", "address": {"city": "Utrecht"}}}')

    document = loader.load_document("order.json", **{"customer.address.city": "Amsterdam"})

    assert document == {"customer": {"name": "A", "address": {"city": "Amsterdam"}}}


def test_a_list_position_is_written_as_a_number(loader, write):
    write("recipe.json", '{"components": [{"evaporationFactor": 1.0}, {"evaporationFactor": 1.0}]}')

    document = loader.load_document("recipe.json", **{"components.0.evaporationFactor": "0.8"})

    assert document["components"][0]["evaporationFactor"] == 0.8
    assert document["components"][1]["evaporationFactor"] == 1.0


def test_a_whole_list_item_can_be_replaced(loader, write):
    write("recipe.json", '{"components": [{"sku": "A"}, {"sku": "B"}]}')

    document = loader.load_document("recipe.json", **{"components.1": '{"sku": "C"}'})

    assert document["components"] == [{"sku": "A"}, {"sku": "C"}]


@pytest.mark.parametrize(
    "given, expected",
    [
        param("0.8", 0.8, id="a number is a number"),
        param("3", 3, id="a whole number is an int"),
        param("true", True, id="a boolean"),
        param("null", None, id="null"),
        param("shipped", "shipped", id="a word stays text"),
        param("2026-03-01", "2026-03-01", id="a date-looking string stays text"),
        param('{"$oid": "%s"}' % OID, ObjectId(OID), id="extended json"),
        param('{"nested": 1}', {"nested": 1}, id="an object"),
    ],
)
def test_an_override_written_as_text_is_read_like_the_files_own_values(loader, write, given, expected):
    write("order.json", '{"field": "original"}')

    assert loader.load_document("order.json", field=given)["field"] == expected


def test_an_override_given_as_an_object_is_used_unchanged(loader, write):
    """Robot Framework hands ``${oid}`` over as the object it is, not as text."""
    write("order.json", '{"_id": "original"}')
    object_id = ObjectId(OID)

    assert loader.load_document("order.json", _id=object_id)["_id"] is object_id


def test_an_override_can_target_an_update_operator(loader, write):
    write("ship.json", '{"$set": {"status": "new"}}')

    document = loader.load_document("ship.json", **{"$set.status": "shipped"})

    assert document == {"$set": {"status": "shipped"}}


@pytest.mark.parametrize(
    "path, expected_in_message",
    [
        param("customer.name", "Available: status, lines", id="a field that is not there at all"),
        param("lines.0.qty", "Available: sku", id="a misspelled field inside a list item"),
        param("lines.5.sku", "holds 1 items", id="a list index out of range"),
        param("lines.first.sku", "has to be a number", id="a list step that is not a number"),
        param("status.upper", "is a str", id="a step into a plain value"),
        param("lines.5", "holds 1 items", id="a list index out of range at the end"),
    ],
)
def test_an_override_path_that_does_not_exist_fails_with_what_was_there(loader, write, path, expected_in_message):
    write("order.json", '{"status": "new", "lines": [{"sku": "A-1"}]}')

    with pytest.raises(ValueError) as error:
        loader.load_document("order.json", **{path: "x"})

    assert "order.json" in str(error.value)
    assert path in str(error.value)
    assert expected_in_message in str(error.value)


def test_an_override_path_through_a_null_field_is_reported(loader, write):
    write("order.json", '{"customer": null}')

    with pytest.raises(ValueError, match="is null"):
        loader.load_document("order.json", **{"customer.name": "A"})


@pytest.mark.parametrize(
    "path, expected_in_message",
    [
        param("address.city.postcode", "'address' is null", id="through a null field"),
        param("name.first.initial", "'name' is a str", id="through a plain value"),
    ],
)
def test_a_path_that_keeps_going_past_a_value_it_cannot_enter_is_reported(loader, write, path,
                                                                         expected_in_message):
    write("order.json", '{"name": "A", "address": null}')

    with pytest.raises(ValueError) as error:
        loader.load_document("order.json", **{path: "x"})

    assert expected_in_message in str(error.value)


def test_a_null_field_can_itself_be_overridden(loader, write):
    write("order.json", '{"note": null}')

    assert loader.load_document("order.json", note="late")["note"] == "late"


def test_the_file_on_disk_is_not_changed_by_overrides(loader, write, documents):
    name = write("order.json", '{"status": "new"}')
    loader.load_document(name, status="shipped")

    assert loader.load_document(name) == {"status": "new"}
    assert (documents / name).read_text(encoding="utf-8") == '{"status": "new"}'


# --------------------------------------------------------------------------- #
# What the keyword hands back
# --------------------------------------------------------------------------- #

def test_the_document_is_returned_for_dotted_access_in_a_suite(loader, write):
    write("order.json", '{"customer": {"name": "A"}, "lines": [{"sku": "A-1"}]}')

    document = loader.load_document("order.json")

    assert isinstance(document, DotDict)
    assert document.customer.name == "A"
    assert document.lines[0].sku == "A-1"


# --------------------------------------------------------------------------- #
# Insert Document From File
# --------------------------------------------------------------------------- #

@pytest.fixture
def mongo_loader(mongo, documents):
    """Keywords backed by an in-memory MongoDB that also read from the document directory."""
    mongo.document_path = documents
    return mongo


def test_a_document_is_read_and_inserted_in_one_step(mongo_loader, write):
    write("order.json", '{"_id": {"$oid": "%s"}, "status": "new"}' % OID)

    doc_id = mongo_loader.insert_document_from_file("orders", "order.json")

    assert doc_id == ObjectId(OID)
    assert mongo_loader.find_document("orders", _id=OID)["status"] == "new"


def test_inserting_from_a_file_applies_the_overrides(mongo_loader, write):
    write("order.json", '{"status": "new", "lines": [{"quantity": 1}]}')

    mongo_loader.insert_document_from_file("orders", "order.json", status="shipped",
                                          **{"lines.0.quantity": "3"})

    stored = mongo_loader.find_document("orders", status="shipped")
    assert stored["lines"][0]["quantity"] == 3


def test_inserting_from_a_file_fills_its_placeholders(mongo_loader, write):
    """The dominant shape: one template, a different document inserted per call."""
    write("order.json", '{"unique_id": "{unique_id}", "customerId": "{customerId}", "status": "new"}')

    for unique_id in ("order-1", "order-2"):
        mongo_loader.insert_document_from_file("orders", "order.json", unique_id=unique_id,
                                              customerId=ObjectId(OID))

    # Queried as an ObjectId, since only ``_id`` is coerced from a string. That it matches
    # at all is the point: the placeholder stored a real ObjectId, not its text.
    assert mongo_loader.count_documents("orders", customerId=ObjectId(OID)) == 2
    assert mongo_loader.find_document("orders", unique_id="order-2")["status"] == "new"


def test_inserting_from_a_file_fails_on_an_unfilled_placeholder(mongo_loader, write):
    write("order.json", '{"unique_id": "{unique_id}"}')

    with pytest.raises(ValueError, match="{unique_id}"):
        mongo_loader.insert_document_from_file("orders", "order.json")

    assert mongo_loader.count_documents("orders") == 0


def test_inserting_from_a_file_uses_the_given_alias(mongo_loader, write, database):
    write("order.json", '{"status": "new"}')
    mongo_loader.connection_manager.add_to_connection_pool(database, "other")

    mongo_loader.insert_document_from_file("orders", "order.json", alias="other")

    assert mongo_loader.count_documents("orders", alias="other", status="new") == 1
    assert mongo_loader.count_documents("orders", status="new") == 0


def test_a_missing_file_fails_before_anything_is_inserted(mongo_loader):
    with pytest.raises(ValueError, match="missing.json"):
        mongo_loader.insert_document_from_file("orders", "missing.json")

    assert mongo_loader.count_documents("orders") == 0
