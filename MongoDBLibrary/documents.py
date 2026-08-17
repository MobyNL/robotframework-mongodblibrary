"""Reading seed documents from files.

Kept out of ``keywords.py`` because none of it touches a connection: resolving a file
name, substituting Robot Framework variables, filling template placeholders, reading
Extended JSON and applying dotted overrides are all functions of a file and its arguments.

A document file has two kinds of hole, and they are deliberately written differently
because they are filled from different places. ``${name}`` is a Robot Framework variable,
so it comes from the suite; ``{name}`` is a placeholder, so it comes from the arguments of
the call that loads the document. Reading the file tells you which.
"""

import copy
import json
import re
from pathlib import Path
from typing import Any, NamedTuple, Optional

from bson import json_util
from robot.libraries.BuiltIn import BuiltIn, RobotNotRunningError

# What makes text worth handing to Robot Framework for substitution. ``${...}`` is the
# form documents are written with; ``%{...}`` is the environment variable form, accepted
# because a fixture that reads a value from the environment is written the same way.
VARIABLE_MARKERS = ("${", "%{")

# A placeholder, and the same thing with the quotes that make it a whole JSON string. The
# name is restricted to an identifier so that JSON's own braces can never match: ``{}``,
# ``{"sku": "A-1"}`` and ``{"$set": ...}`` all fail the pattern on their first character.
PLACEHOLDER = re.compile(r"\{([A-Za-z_]\w*)\}")
QUOTED_PLACEHOLDER = re.compile(r'"\{([A-Za-z_]\w*)\}"')

# Distinguishes "no value was given for this placeholder" from a value of None, which is a
# legitimate thing to fill a field with.
_MISSING = object()


class FilledDocument(NamedTuple):
    """The result of filling a template: the text, and what was found while filling it."""

    text: str
    used: set[str]
    declared: list[str]


def resolve_document_file(path: str, document_path: Optional[Path]) -> Path:
    """
    Return the file ``path`` names, looking in ``document_path`` first.

    A bare file name is resolved against ``document_path``, which is the only thing that
    argument does. A path given to the keyword is still tried as written, so a suite that
    imports without ``document_path`` keeps working, and so does one that gives a path
    reaching outside the directory.

    :param path: File name or path as given to the keyword
    :param document_path: Directory from the library import, or None
    :return: The file that was found
    """
    candidates = [Path(path)]
    if document_path is not None and not Path(path).is_absolute():
        candidates.insert(0, document_path / path)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    searched = ", ".join(str(candidate) for candidate in candidates)
    raise ValueError(f"Document file '{path}' was not found. Looked in: {searched}.")


def substitute_variables(text: str, name: str) -> Any:
    """
    Replace the ``${...}`` placeholders in ``text`` from the calling suite's variables.

    Substitution is Robot Framework's own, so the variable scope is the one the suite
    sees at the moment the keyword runs, and a placeholder that resolves to nothing is an
    error rather than a literal ``${user_id}`` written into the database. That distinction
    is the reason this is not left to `Replace Variables` in the suite: a document seeded
    with the placeholder text still inserts, and the test then fails somewhere later
    against data that looks almost right.

    :param text: File contents
    :param name: File name, for the failure message
    :return: The text with placeholders replaced, or the object a whole-file placeholder
        resolved to
    """
    if not any(marker in text for marker in VARIABLE_MARKERS):
        return text
    try:
        return BuiltIn().replace_variables(text)
    except RobotNotRunningError as error:
        raise ValueError(
            f"Document '{name}' uses ${{...}} variables, which can only be resolved while a "
            f"Robot Framework test is running."
        ) from error
    except Exception as error:
        raise ValueError(f"Document '{name}' has a variable that could not be resolved: {error}") from error


def fill_placeholders(text: str, values: dict[str, Any], name: str) -> FilledDocument:
    """
    Fill the ``{name}`` placeholders of a template document from ``values``.

    A placeholder is written quoted, as ``"quantity": "{quantity}"``, which keeps the
    template valid JSON — an editor, ``jq`` and a formatter all still read it — and it is
    filled in one of two ways depending on where it sits:

    - A string that is *exactly* one placeholder is replaced whole, its quotes included, by
      the value's own Extended JSON form. This is what lets a valid-JSON template carry a
      value JSON has no syntax for: ``"quantity": "{quantity}"`` given ``3`` becomes a real
      int, and an ObjectId or a datetime becomes ``{"$oid": ...}`` or ``{"$date": ...}`` and
      parses back to what it was.
    - A placeholder inside a longer string, as in ``"REF-{n}"``, is interpolated as text.

    An unquoted ``{name}`` in a value position is filled like the first case. It makes the
    template invalid JSON before it is filled, which is why the quoted form is the one
    documented, but nothing here needs the file to parse yet, so it works.

    Inside a string ``{{`` and ``}}`` are literal braces, as in ``str.format``, which is how
    a document that genuinely holds ``{word}`` in a string says so. Outside a string they
    are JSON's own braces and are left alone — unescaping there would rewrite the ``}}``
    that closes every nested object in the file.

    :param text: File contents, ``${...}`` variables already substituted
    :param values: Candidate values, which are the loading keyword's named arguments
    :param name: File name, for the failure message
    :return: The filled text, the keys of ``values`` it used, and the placeholders the
        file declares
    """
    filled: list[str] = []
    used: set[str] = set()
    declared: list[str] = []
    missing: list[str] = []

    def take(key: str) -> Any:
        """Record a placeholder as declared, and return its value if there is one."""
        if key not in declared:
            declared.append(key)
        if key in values:
            used.add(key)
            return values[key]
        if key not in missing:
            missing.append(key)
        return _MISSING

    index = 0
    in_string = False
    while index < len(text):
        character = text[index]
        if not in_string:
            quoted = QUOTED_PLACEHOLDER.match(text, index)
            if quoted is not None:  # a whole string, so the value keeps its own type
                value = take(quoted.group(1))
                filled.append(quoted.group(0) if value is _MISSING else _as_json(value))
                index = quoted.end()
                continue
            if character == '"':
                in_string = True
                filled.append(character)
                index += 1
                continue
            bare = PLACEHOLDER.match(text, index)
            if bare is not None:  # unquoted, so it is a value position too
                value = take(bare.group(1))
                filled.append(bare.group(0) if value is _MISSING else _as_json(value))
                index = bare.end()
                continue
            filled.append(character)
            index += 1
            continue
        if character == "\\":  # an escape, whose second character is never a brace or quote
            filled.append(text[index:index + 2])
            index += 2
            continue
        if character == '"':
            in_string = False
            filled.append(character)
            index += 1
            continue
        if text.startswith("{{", index) or text.startswith("}}", index):
            filled.append(character)
            index += 2
            continue
        inside = PLACEHOLDER.match(text, index)
        if inside is not None:  # part of a longer string, so the value is text here
            value = take(inside.group(1))
            filled.append(inside.group(0) if value is _MISSING else _as_json_string_body(value))
            index = inside.end()
            continue
        filled.append(character)
        index += 1

    if missing:
        _reject_unfilled(missing, values, name)
    return FilledDocument("".join(filled), used, declared)


def _as_json(value: Any) -> str:
    """Render a value as the Extended JSON that parses back to it."""
    return json_util.dumps(coerce_override(value))


def _as_json_string_body(value: Any) -> str:
    """Render a value as text to sit inside a JSON string, escaped for one."""
    return json_util.dumps(str(value))[1:-1]


def _reject_unfilled(missing: list[str], values: dict[str, Any], name: str) -> None:
    """
    Fail on a placeholder the file declares that no argument filled.

    Loud rather than left as it is, for the same reason an unresolved ``${...}`` fails: the
    literal text ``{unique_id}`` is a perfectly insertable string, so leaving it would put a
    document in the database that looks almost right and fail a test somewhere later.
    """
    holes = ", ".join(f"{{{key}}}" for key in missing)
    given = ", ".join(sorted(values)) or "nothing"
    was = "were" if len(missing) > 1 else "was"
    raise ValueError(
        f"Document '{name}' declares {holes}, which {was} not filled. Pass a value as a "
        f"named argument for each. Given: {given}."
    )


def parse_document(text: str, name: str) -> dict:
    """
    Read MongoDB Extended JSON, so the document holds the types MongoDB stores.

    ``bson.json_util`` turns ``$oid``, ``$date``, ``$numberInt`` and ``$numberDouble``
    into ``ObjectId``, ``datetime``, ``int`` and ``float``, and leaves plain JSON values
    as the types they already are. MongoDB's update operators are ``$``-prefixed too and
    are not extended types, so ``{"$set": ..., "$push": ...}`` passes through untouched —
    including a ``$date`` nested inside one — which is what makes this usable for update
    documents as well as for documents to insert.

    :param text: JSON text, variables and placeholders already replaced
    :param name: File name, for the failure message
    :return: The document
    """
    try:
        document = json_util.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Document '{name}' is not valid JSON: {error.msg}, at line {error.lineno} column {error.colno}."
        ) from error
    except Exception as error:
        # A converter rejected a value: a literal ``$date`` holding something that is not
        # a date, an ``$oid`` that is not an object id. Its own message names the value,
        # which is what identifies the field, so it is reported rather than replaced.
        raise ValueError(f"Document '{name}' has a value Extended JSON could not read: {error}") from error
    if not isinstance(document, dict):
        raise ValueError(
            f"Document '{name}' has to hold a JSON object, but it holds a {type(document).__name__}."
        )
    return document


def as_document(value: Any, name: str) -> dict:
    """
    Return the document ``value`` describes, parsing it when it is still text.

    Text is the normal case. An object turns up when the whole file is a single variable,
    such as a file holding nothing but ``${ORDER}``: Robot Framework resolves that to the
    variable itself rather than to its printed form. It is copied, because overrides are
    applied in place and the suite's variable is not this keyword's to change.

    :param value: Result of substitution
    :param name: File name, for the failure message
    :return: The document
    """
    if isinstance(value, dict):
        return copy.deepcopy(value)
    return parse_document(str(value), name)


def build_document(substituted: Any, arguments: dict[str, Any], name: str) -> dict:
    """
    Turn a substituted file into the finished document, using ``arguments`` for both jobs.

    An argument is one of two things and the file decides which: a key the file declares as
    a placeholder fills that placeholder, and any other key is a dotted override path into
    the parsed document. So a value that changes on every call is a hole in the template,
    while a value that changes occasionally overrides what the file already says, and
    neither needs the other to have been thought of first.

    :param substituted: Result of `substitute_variables`
    :param arguments: The loading keyword's named arguments
    :param name: File name, for the failure messages
    :return: The document
    """
    declared: list[str] = []
    remaining = arguments
    if isinstance(substituted, str):
        filled = fill_placeholders(substituted, arguments, name)
        substituted, declared = filled.text, filled.declared
        remaining = {key: value for key, value in arguments.items() if key not in filled.used}
    document = as_document(substituted, name)
    _reject_unknown_arguments(remaining, document, declared, name)
    return apply_overrides(document, remaining, name)


def _reject_unknown_arguments(arguments: dict[str, Any], document: dict, declared: list[str],
                              name: str) -> None:
    """
    Fail on a bare argument that is neither a placeholder in the file nor a field to override.

    A dotted argument can only ever have been a path, and reports itself as one while it is
    walked. A bare name could have been meant as either, and which was meant decides whether
    the fix belongs in the file or in the call, so the failure names both.
    """
    for key in arguments:
        if "." in key or key in document:
            continue
        placeholders = ", ".join(f"{{{item}}}" for item in declared) or "none"
        fields = ", ".join(document) or "nothing"
        raise ValueError(
            f"Document '{name}': '{key}' is neither a placeholder the file declares nor a "
            f"field of the document. Placeholders: {placeholders}. Fields: {fields}."
        )


def coerce_override(value: Any) -> Any:
    """
    Read an override value that was written in a suite as text.

    Robot Framework passes ``evaporationFactor=0.8`` as the string ``"0.8"``, and a
    string where the document held a number changes what MongoDB stores and how it
    compares. Each value is read as Extended JSON, which gives numbers, booleans, null
    and ``{"$oid": ...}`` what they mean, and leaves anything that is not JSON — an
    ordinary word such as ``abc`` — as the text it already is. A value given as
    ``${variable}`` arrives as an object and is used unchanged.

    :param value: Override value as given to the keyword
    :return: The value to write into the document
    """
    if not isinstance(value, str):
        return value
    try:
        return json_util.loads(value)
    except Exception:
        return value


def apply_overrides(document: dict, overrides: dict[str, Any], name: str) -> dict:
    """
    Write each override into ``document`` at its dotted path.

    :param document: Document to modify in place
    :param overrides: Dotted path to value, as given to the keyword
    :param name: File name, for the failure messages
    :return: The same document
    """
    for path, value in overrides.items():
        _write_path(document, path, coerce_override(value), name)
    return document


def _location(walked: list[str]) -> str:
    """Name the place a path had reached, for a failure message."""
    return f"'{'.'.join(walked)}'" if walked else "the document"


def _prefix(path: str, name: str) -> str:
    """Open a failure message with the override and the file it was applied to."""
    return f"Override '{path}' for document '{name}': "


def _write_path(document: dict, path: str, value: Any, name: str) -> None:
    """
    Follow a dotted ``path`` into ``document`` and write ``value`` at the end of it.

    List positions are written as numbers, as in ``components.0.evaporationFactor``, so
    one syntax covers both objects and lists. Every step has to exist, the last one
    included: a step that does not is reported with what was available at that point,
    because a path that misses usually means a typo rather than a field meant to be
    added.
    """
    steps = path.split(".")
    current: Any = document
    walked: list[str] = []
    for step in steps[:-1]:
        current = _read_step(current, step, walked, path, name)
        walked.append(step)
    _write_step(current, steps[-1], value, walked, path, name)


def _read_step(current: Any, step: str, walked: list[str], path: str, name: str) -> Any:
    """Take one step into a document, failing with what was there instead."""
    prefix = _prefix(path, name)
    if isinstance(current, dict):
        if step not in current:
            available = ", ".join(current) or "nothing"
            raise ValueError(f"{prefix}'{step}' is not in {_location(walked)}. Available: {available}.")
        return current[step]
    if isinstance(current, list):
        return current[_index(current, step, walked, prefix)]
    if current is None:
        raise ValueError(f"{prefix}{_location(walked)} is null, so '{step}' cannot be read from it.")
    raise ValueError(
        f"{prefix}{_location(walked)} is a {type(current).__name__}, so '{step}' cannot be read from it."
    )


def _write_step(current: Any, step: str, value: Any, walked: list[str], path: str, name: str) -> None:
    """Write the last step of a path, which has to be a field the document already has."""
    prefix = _prefix(path, name)
    if isinstance(current, dict):
        if step not in current:
            available = ", ".join(current) or "nothing"
            raise ValueError(f"{prefix}'{step}' is not in {_location(walked)}. Available: {available}.")
        current[step] = value
        return
    if isinstance(current, list):
        current[_index(current, step, walked, prefix)] = value
        return
    if current is None:
        raise ValueError(f"{prefix}{_location(walked)} is null, so '{step}' cannot be set on it.")
    raise ValueError(
        f"{prefix}{_location(walked)} is a {type(current).__name__}, so '{step}' cannot be set on it."
    )


def _index(current: list, step: str, walked: list[str], prefix: str) -> int:
    """Read a path step as a list position, checking it against the list's length."""
    try:
        index = int(step)
    except ValueError:
        raise ValueError(f"{prefix}{_location(walked)} is a list, so '{step}' has to be a number.") from None
    if not -len(current) <= index < len(current):
        raise ValueError(
            f"{prefix}{_location(walked)} holds {len(current)} items, so index {step} is out of range."
        )
    return index
