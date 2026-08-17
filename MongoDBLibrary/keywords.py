import json
import time
from ast import literal_eval
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Callable, cast, Optional, TYPE_CHECKING, Union

from assertionengine import AssertionOperator, verify_assertion
from bson import ObjectId
from pymongo import MongoClient, ReturnDocument
from pymongo.collection import Collection
from pymongo.database import Database
from robot.api import logger
from robot.api.deco import keyword
from robot.libraries.BuiltIn import BuiltIn
from robot.utils import DotDict, timestr_to_secs

from MongoDBLibrary.connection_pool import ConnectionManager
from MongoDBLibrary.documents import (
    build_document,
    declared_placeholders,
    resolve_document_file,
    substitute_variables,
)

try:  # Robot Framework 7.4 and later
    from robot.api.types import Secret
except ImportError:  # pragma: no cover - Robot Framework 7.3, which has no Secret type
    Secret = None

if TYPE_CHECKING:
    from robot.api.types import Secret as _Secret

    # A credential, given either as plain text or as a Robot Framework ``Secret``.
    Credential = Union[str, _Secret]
    OptionalCredential = Optional[Credential]
else:
    # Built at import so the annotation names a type Robot Framework can convert to.
    # On 7.3 there is no Secret to accept, and no way for a suite to produce one, so the
    # argument is a plain string exactly as it was before.
    Credential = Union[str, Secret] if Secret is not None else str
    OptionalCredential = Optional[Credential]

# Parts of an explain document that describe plans the server did not run: the candidates
# it rejected, and, at ``allPlansExecution`` verbosity, the trial runs it used to choose
# between them. Both are written in the same shape as the plan that did run, so a summary
# that walks the whole document reports work that never happened.
NOT_EXECUTED = ("rejectedPlans", "allPlansExecution")


class MongoDBKeywords:
    """
    Provides keywords for interacting with MongoDB.

    This class contains Robot Framework keywords for MongoDB operations.
    """

    def __init__(self, connection_manager: ConnectionManager, coerce_object_ids: bool = True,
                 document_path: Optional[str] = None):
        """
        Initializes the MongoDBKeywords library.

        Arguments:
        - ``connection_manager``: Manages connections to MongoDB.
        - ``coerce_object_ids``: Whether a string ``_id`` in a query is converted to an
          ObjectId.
        - ``document_path``: Directory that documents given by file name are looked up in.
        """
        self.connection_manager = connection_manager
        self.coerce_object_ids = coerce_object_ids
        self.document_path = Path(document_path) if document_path else None

    # ----------------------------------------------------------------- #
    # Internals
    # ----------------------------------------------------------------- #

    def _resolve_alias(self, alias: Optional[str] = None) -> str:
        """Return ``alias``, or the currently active alias when None."""
        return self.connection_manager.default_alias if alias is None else alias

    def _get_database(self, alias: Optional[str] = None) -> Database:
        """Return the pooled database for ``alias``, raising if it is not connected."""
        alias = self._resolve_alias(alias)
        if alias not in self.connection_manager.db_connection_pool:
            raise KeyError(f"Alias '{alias}' not found in connection pool.")
        return self.connection_manager.db_connection_pool[alias]

    def _get_collection(self, collection_name: str, alias: Optional[str] = None) -> Collection:
        """Return a collection from the pooled database for ``alias``."""
        return self._get_database(alias)[collection_name]

    def _get_client(self, alias: Optional[str] = None) -> MongoClient:
        """Return the client behind the pooled database for ``alias``.

        Server-wide keywords act on the client rather than one database, but they are
        still addressed by an alias so that they resolve and fail exactly like every
        other keyword.
        """
        return self._get_database(alias).client

    @staticmethod
    def _reveal(credential: OptionalCredential) -> Optional[str]:
        """Return the text of a credential, unwrapping a Robot Framework ``Secret``.

        Everything downstream needs the plain value: pymongo has to authenticate with
        it, and the client cache has to key on it. Two ``Secret`` objects holding the
        same password are still different objects, so leaving one wrapped would make
        every alias miss the cache and open its own connection pool.
        """
        if Secret is not None and isinstance(credential, Secret):
            return cast(str, credential.value)
        return credential

    @staticmethod
    def _coerce_object_id(value: Any) -> Any:
        """Turn a string that is a valid ObjectId into one, leaving anything else alone."""
        if isinstance(value, str) and ObjectId.is_valid(value):
            return ObjectId(value)
        return value

    def _normalise_query(self, query: Any) -> Any:
        """
        Convert a string ``_id`` in a query into an ObjectId.

        Robot Framework turns every value it stores in a variable into a string when it
        is written back out, so a document id obtained from `Insert Document` arrives
        here as text and would otherwise never match. Disabled by importing the library
        with ``coerce_object_ids=${False}``, after which queries are passed through
        exactly as given.
        """
        if not self.coerce_object_ids:
            return query
        if not isinstance(query, dict) or "_id" not in query:
            return query
        normalised = dict(query)
        value = normalised["_id"]
        if isinstance(value, dict):
            normalised["_id"] = {
                operator: [self._coerce_object_id(item) for item in operand]
                if isinstance(operand, list)
                else self._coerce_object_id(operand)
                for operator, operand in value.items()
            }
        else:
            normalised["_id"] = self._coerce_object_id(value)
        if normalised["_id"] != value:
            logger.debug(f"Converted the query '_id' to an ObjectId: {normalised['_id']!r}")
        return normalised

    @staticmethod
    def _as_dot_dict(value: Any) -> Any:
        """Wrap documents so Robot Framework's ``${doc.field}`` access works."""
        if isinstance(value, list):
            return [DotDict(item) if isinstance(item, dict) else item for item in value]
        return DotDict(value) if isinstance(value, dict) else value

    @staticmethod
    def _as_sort_list(sort: Optional[dict]) -> Optional[list]:
        """Turn ``{"name": 1}`` into pymongo's ``[("name", 1)]``."""
        return list(sort.items()) if sort else None

    @staticmethod
    def _count_options(limit: int, skip: int) -> dict[str, Any]:
        """Build the count options, omitting the ones left at zero.

        ``count_documents`` rejects ``limit=0`` rather than reading it as "no limit",
        so a default of zero has to be left out of the call entirely.
        """
        options: dict[str, Any] = {}
        if limit:
            options["limit"] = limit
        if skip:
            options["skip"] = skip
        return options

    @staticmethod
    def _as_command(command: Union[dict, str]) -> Union[dict, str]:
        """Read a command written as a document, which Robot Framework leaves as text.

        Every other complex argument in this library is annotated ``dict`` or ``list``,
        so Robot Framework converts ``query={"a": 1}`` from the suite into a real
        dictionary. A command is either a document or a bare name, and an argument that
        also accepts ``str`` is one Robot Framework stops converting — the text arrives
        here unchanged and would be sent as a command *name*, which the server rejects
        with "no such command". There is no ambiguity to resolve: no command is named
        ``{...}``.
        """
        if isinstance(command, str) and command.startswith("{"):
            try:
                parsed = literal_eval(command)
            except (ValueError, SyntaxError) as error:
                raise ValueError(f"Command {command!r} looks like a document but could not be read: {error}") from error
            if not isinstance(parsed, dict):
                raise ValueError(f"Command {command!r} looks like a document but is not one.")
            return parsed
        return command

    @staticmethod
    def _modified_count(result: Any) -> int:
        """Report how many documents changed, logging an upsert that changed none.

        ``modified_count`` counts changes, and an upserted document was inserted rather
        than changed, so a successful upsert returns 0. Logging the new id keeps that
        from reading as "nothing happened".
        """
        if result.upserted_id is not None:
            logger.info(f"No document matched, so one was inserted with _id {result.upserted_id!r}.")
        return result.modified_count

    def _find(self, collection_name: str, query: Any, alias: Optional[str], projection: Optional[dict],
              sort: Optional[dict], limit: int, skip: int) -> list:
        collection = self._get_collection(collection_name, alias)
        cursor = collection.find(self._normalise_query(query), projection, skip=skip, limit=limit)
        sort_list = self._as_sort_list(sort)
        if sort_list:
            cursor = cursor.sort(sort_list)
        return self._as_dot_dict(list(cursor))

    @staticmethod
    def _explain_stages(node: Any) -> Iterator[dict]:
        """Yield every stage in an explain document, wherever the server put it.

        The plan is a tree whose links are named differently depending on what produced
        it: ``inputStage`` and ``inputStages`` for a classic plan, ``queryPlan`` for the
        slot-based engine, ``executionStages`` for the executed side, and ``shards`` for a
        sharded cluster. Walking every nested dictionary and list instead of following
        those names by hand means a shape this library has not seen still reports its
        stages, which is the whole reason the summary can stay version-agnostic.

        The walk stays agnostic about the names of the *links*, but deliberately not about
        ``NOT_EXECUTED``: those two hold plans the server considered and did not use, and a
        stage from one of them describes work that never happened. Yielding them would let
        a rejected COLLSCAN report a collection scan for a query answered by an index, and
        a rejected index plan lend its ``indexName`` to a query that scanned the collection.
        """
        if isinstance(node, dict):
            if "stage" in node:
                yield node
            for key, value in node.items():
                if key not in NOT_EXECUTED:
                    yield from MongoDBKeywords._explain_stages(value)
        elif isinstance(node, list):
            for item in node:
                yield from MongoDBKeywords._explain_stages(item)

    @staticmethod
    def _first_stage_value(stages: list[dict], field: str) -> Any:
        """Return ``field`` from the first stage that has it, or None."""
        return next((stage[field] for stage in stages if field in stage), None)

    @staticmethod
    def _format_explain(collection_name: str, query: Any, summary: dict[str, Any]) -> str:
        """Lay the summary out over several lines, aligned, for the log.

        Robot Framework renders a logged message with ``white-space: pre-wrap``, so
        newlines and indentation survive into ``log.html``. A summary on one line is
        readable by nobody, and the field this keyword exists for — ``index_bounds`` —
        is the one that suffers most, since it is a dictionary inside it. Here each
        indexed field gets a line of its own, which is what makes comparing the bounds
        with what the suite passed a matter of reading rather than of parsing.
        """
        lines = [f"Explain of {query!r} on '{collection_name}':"]
        scalars = [(name, value) for name, value in summary.items() if name not in ("index_bounds", "shards")]
        width = max(len(name) for name, _ in scalars)
        lines += [f"  {name:<{width}}  {value}" for name, value in scalars]
        bounds = summary.get("index_bounds")
        if bounds:
            lines.append("  index_bounds")
            field_width = max(len(field) for field in bounds)
            for field, values in bounds.items():
                shown = values if isinstance(values, list) else [values]
                lines += [f"    {field:<{field_width}}  {value}" for value in shown]
        for shard in summary.get("shards") or []:
            lines.append(f"  shard {shard.get('shard')}")
            lines += [
                f"    {name:<{width}}  {value}" for name, value in shard.items() if name not in ("shard", "index_bounds")
            ]
        return "\n".join(lines)

    @classmethod
    def _summarise_explain(cls, raw: dict) -> dict[str, Any]:
        """Flatten an explain document into the handful of fields a test author reads.

        Everything here is derived rather than copied, because the shapes differ by
        server version and topology while the questions do not: which plan won, what it
        searched for, and how much it had to look at to answer.
        """
        winning = raw.get("queryPlanner", {}).get("winningPlan", {})
        # The slot-based engine nests the plan the classic one puts at the top.
        root = winning.get("queryPlan", winning)
        stages = list(cls._explain_stages(raw))
        execution = raw.get("executionStats", {})
        summary: dict[str, Any] = {
            "stage": root.get("stage"),
            "index_name": cls._first_stage_value(stages, "indexName"),
            "index_bounds": cls._first_stage_value(stages, "indexBounds"),
            # Presence of a COLLSCAN, rather than a list of index stage names: the fast
            # path for `_id` is reported as EXPRESS_IXSCAN on MongoDB 8 and IDHACK before
            # it, and an allowlist would have to grow with every server release.
            "collection_scan": any(stage.get("stage") == "COLLSCAN" for stage in stages),
            "keys_examined": execution.get("totalKeysExamined"),
            "docs_examined": execution.get("totalDocsExamined"),
            "returned": execution.get("nReturned"),
            "duration_ms": execution.get("executionTimeMillis"),
        }
        shards = cls._shard_summaries(raw)
        if shards is not None:
            summary["shards"] = shards
        return summary

    @classmethod
    def _shard_summaries(cls, raw: dict) -> Optional[list[dict[str, Any]]]:
        """Summarise each shard of a sharded plan, or None when the plan is not sharded.

        A shard that reads nothing is as interesting as one that reads everything, so
        each is reported separately rather than only as part of the total.
        """
        planner_shards = raw.get("queryPlanner", {}).get("winningPlan", {}).get("shards")
        execution_shards = raw.get("executionStats", {}).get("executionStages", {}).get("shards")
        if planner_shards is None and execution_shards is None:
            return None
        by_name: dict[str, dict[str, Any]] = {}
        for shard in planner_shards or []:
            name = shard.get("shardName")
            plan = shard.get("winningPlan", {})
            plan = plan.get("queryPlan", plan)
            stages = list(cls._explain_stages(shard))
            by_name[name] = {
                "shard": name,
                "stage": plan.get("stage"),
                "index_name": cls._first_stage_value(stages, "indexName"),
                "index_bounds": cls._first_stage_value(stages, "indexBounds"),
                "collection_scan": any(stage.get("stage") == "COLLSCAN" for stage in stages),
            }
        for shard in execution_shards or []:
            name = shard.get("shardName")
            summary = by_name.setdefault(name, {"shard": name})
            # The shard's own totals where it reports them, and its root stage's counts
            # otherwise. The totals are what the unsharded summary counts, so a shard
            # whose plan has several stages is reported the same way the whole query is.
            stage = shard.get("executionStages", {})
            for key, total, per_stage in (
                ("keys_examined", "totalKeysExamined", "keysExamined"),
                ("docs_examined", "totalDocsExamined", "docsExamined"),
                ("returned", "nReturned", "nReturned"),
            ):
                summary[key] = shard.get(total, stage.get(per_stage))
        return list(by_name.values())

    def _retry_until_no_assertion_error(self, check: Callable[[], None], retry_timeout: str, retry_pause: str) -> None:
        """
        Run ``check`` until it stops raising AssertionError or ``retry_timeout`` elapses.

        The deadline is measured against a real clock, so the loop terminates even
        when ``retry_pause`` is zero and regardless of how long ``check`` itself takes.
        """
        deadline = time.monotonic() + timestr_to_secs(retry_timeout)
        pause = timestr_to_secs(retry_pause)
        while True:
            try:
                check()
                return
            except AssertionError:
                if time.monotonic() >= deadline:
                    logger.info(f"Timeout '{retry_timeout}' reached")
                    raise
                BuiltIn().sleep(pause)

    # ----------------------------------------------------------------- #
    # Connecting
    # ----------------------------------------------------------------- #

    @keyword
    def connect_to_database(self, db_name: str, db_user: Optional[str] = None, db_password: OptionalCredential = None, db_host: Optional[str] = None, db_port: Optional[int] = None, alias: Optional[str] = None, srv: bool = False, tls: Optional[bool] = None, auth_source: Optional[str] = None, auth_mechanism: Optional[str] = None, replica_set: Optional[str] = None, direct_connection: Optional[bool] = None, read_preference: Optional[str] = None, server_selection_timeout: Optional[str] = None) -> None:
        """
        Connects to MongoDB and adds the database object to the connection pool.

        The connection is verified before the keyword passes, so a failure to reach
        the server or to authenticate is reported here rather than by a later keyword.
        Connecting several aliases to the same server reuses one client.

        Arguments:
        - ``db_name``: Name of the database to connect to.
        - ``db_user``: Username for authentication (optional).
        - ``db_password``: Password for authentication (optional). Accepts a Robot
          Framework ``Secret``, which keeps the value out of the log. See `Credentials`.
        - ``db_host``: Hostname or IP address of the MongoDB server (optional).
        - ``db_port``: Port number of the MongoDB server (optional, defaults to 27017). Ignored when ``srv`` is true.
        - ``alias``: Alias for the connection (optional).
        - ``srv``: Resolve ``db_host`` as a DNS seed list (``mongodb+srv``) instead of a
          single host. Required for hosted clusters such as MongoDB Atlas, whose
          cluster names have no address record of their own. Enables TLS by default.
        - ``tls``: Force TLS on or off (optional). Leave unset to use the default for
          the connection type, which is on for ``srv`` and off otherwise.
        - ``auth_source``: Database holding the user's credentials (optional). Needed
          whenever the user was not created in ``db_name`` itself.
        - ``auth_mechanism``: Authentication mechanism, e.g. ``SCRAM-SHA-256`` or
          ``MONGODB-AWS`` (optional). Left unset, the server and driver negotiate one.
          See `AWS Authentication`.
        - ``replica_set``: Name of the replica set to connect to (optional). Setting it
          makes the driver discover the whole set from ``db_host`` and follow elections,
          rather than talking to that one host.
        - ``direct_connection``: Connect to ``db_host`` itself and skip topology
          discovery (optional). Use it to read from one specific member of a set.
        - ``read_preference``: Which member to read from, e.g. ``primary``,
          ``primaryPreferred``, ``secondary``, ``secondaryPreferred`` or ``nearest``
          (optional, defaults to ``primary``). Reading from a secondary can return data
          that has not yet caught up with the last write, which makes a test flaky in a
          way that looks like a product bug.
        - ``server_selection_timeout``: How long to wait for a reachable server before
          failing, as a Robot Framework time string (optional, pymongo defaults to 30
          seconds).

        Credentials should come from variables rather than being written literally in a
        suite, because Robot Framework writes the argument as it appears in the source
        into the log.

        Example:
        | Connect To Database    db_name=mydb    db_user=user    db_password=pass    db_host=localhost    db_port=27017
        | Connect To Database    db_name=mydb    db_user=user    db_password=pass    db_host=mycluster.abcde.mongodb.net    srv=${True}
        | Connect To Database    db_name=mydb    db_user=user    db_password=pass    db_host=localhost    auth_source=admin    server_selection_timeout=5 seconds
        | Connect To Database    db_name=mydb    db_host=node1.example.test    replica_set=rs0    read_preference=secondaryPreferred

        """
        options: dict[str, Any] = {}
        host: Optional[str]
        port: Optional[int]
        if srv:
            host = f"mongodb+srv://{db_host}"
            port = None
            if db_port:
                logger.warn("'db_port' is ignored when 'srv' is enabled, because a seed list supplies its own ports.")
        else:
            host = db_host
            port = int(db_port) if db_port else 27017
        if tls is not None:
            options["tls"] = tls
        if auth_source:
            options["authSource"] = auth_source
        if auth_mechanism:
            options["authMechanism"] = auth_mechanism
        if replica_set:
            options["replicaSet"] = replica_set
        if direct_connection is not None:
            options["directConnection"] = direct_connection
        if read_preference:
            options["readPreference"] = read_preference
        if server_selection_timeout:
            options["serverSelectionTimeoutMS"] = int(timestr_to_secs(server_selection_timeout) * 1000)

        password = self._reveal(db_password)
        cache_key = ("host", host, port, db_user, password, tuple(sorted(options.items())))
        self._connect(cache_key, lambda: MongoClient(host=host, port=port, username=db_user, password=password, **options), db_name, alias)
        logger.info(f"Connected to MongoDB with alias '{self._resolve_alias(alias)}' at {db_host}")

    @keyword
    def connect_to_database_using_connection_string(self, db_conn_string: Credential, db_name: str, alias: Optional[str] = None, server_selection_timeout: Optional[str] = None) -> None:
        """
        Connects to MongoDB using a connection string and adds the database object to the connection pool.

        The connection is verified before the keyword passes, so a failure to reach
        the server or to authenticate is reported here rather than by a later keyword.
        Connecting several aliases with the same connection string reuses one client.

        Arguments:
        - ``db_conn_string``: MongoDB connection string. Both ``mongodb://`` and
          ``mongodb+srv://`` are accepted. A connection string embeds the password, so
          this accepts a Robot Framework ``Secret`` and the whole string is then kept out
          of the log. See `Credentials`.
        - ``db_name``: Name of the database to connect to.
        - ``alias``: Alias for the connection (optional).
        - ``server_selection_timeout``: How long to wait for a reachable server before
          failing, as a Robot Framework time string (optional, pymongo defaults to 30
          seconds).

        The connection string should come from a variable rather than being written
        literally in a suite, because Robot Framework writes the argument as it appears
        in the source into the log.

        Example:
        | Connect To Database Using Connection String    db_conn_string=mongodb://localhost:27017    db_name=mydb

        """
        options: dict[str, Any] = {}
        if server_selection_timeout:
            options["serverSelectionTimeoutMS"] = int(timestr_to_secs(server_selection_timeout) * 1000)

        connection_string = self._reveal(db_conn_string)
        cache_key = ("uri", connection_string, tuple(sorted(options.items())))
        self._connect(cache_key, lambda: MongoClient(connection_string, **options), db_name, alias)
        logger.info(f"Connected to MongoDB with alias '{self._resolve_alias(alias)}' using connection string.")

    def _connect(self, cache_key: Any, create_client: Callable[[], MongoClient], db_name: str, alias: Optional[str]) -> None:
        """Create or reuse a client, verify it, and pool its database under ``alias``."""
        alias = self._resolve_alias(alias)
        client = self.connection_manager.get_or_create_client(cache_key, create_client)
        try:
            client.admin.command("ping")
        except Exception:
            self.connection_manager.discard_client(client)
            raise
        self.connection_manager.add_to_connection_pool(client[db_name], alias)

    @keyword
    def disconnect_from_database(self, alias: Optional[str] = None) -> None:
        """
        Disconnect a specific database connection using its alias.

        The underlying client stays open if another alias still shares it.

        Arguments:
        - ``alias``: Alias of the connection to disconnect (optional, defaults to the active alias).

        Example:
        | Disconnect From Database    alias=myalias

        """
        alias = self._resolve_alias(alias)
        if alias not in self.connection_manager.db_connection_pool:
            logger.error(f"Attempted to disconnect non-existent alias: {alias}")
            raise ValueError(f"Connection with alias '{alias}' is not connected.")
        self.connection_manager.remove_from_connection_pool(alias)
        logger.info(f"Disconnected alias: {alias}")

    @keyword
    def disconnect_from_all_databases(self) -> None:
        """
        Disconnect every connection in the connection pool.

        Useful as a suite teardown, since the library has ``GLOBAL`` scope and
        otherwise keeps its connections open for the whole run.

        Example:
        | Disconnect From All Databases

        """
        self.connection_manager.clear_connection_pool()

    @keyword
    def list_database_connections(self) -> list[str]:
        """
        List the aliases of all currently connected databases.

        Returns:
        - A list of connection aliases.

        Example:
        | ${aliases}    List Database Connections

        """
        return self.connection_manager.list_connection_pool()

    @keyword
    def switch_connection(self, alias: str) -> None:
        """
        Make the connection stored under ``alias`` the active one.

        Keywords called afterwards without an explicit ``alias`` use this connection.

        Arguments:
        - ``alias``: Alias of the connection to switch to.

        Example:
        | Switch Connection    alias=myalias

        """
        if alias not in self.connection_manager.db_connection_pool:
            raise ValueError(f"Connection with alias '{alias}' is not connected.")
        self.connection_manager.default_alias = alias

    @keyword
    def switch_database(self, alias: str) -> None:
        """
        *DEPRECATED* Use `Switch Connection` instead, which is named for what it does.

        Switches the active connection, not the database within a connection.

        Arguments:
        - ``alias``: Alias of the connection to switch to.

        """
        self.switch_connection(alias)

    @keyword
    def get_active_alias(self) -> str:
        """
        Return the alias used by keywords called without an explicit ``alias``.

        Returns:
        - The active connection alias.

        Example:
        | ${alias}    Get Active Alias

        """
        return self.connection_manager.default_alias

    @keyword
    def check_if_database_connection_exists(self, alias: Optional[str] = None) -> None:
        """
        Check if a database connection exists for the given alias.

        Arguments:
        - ``alias``: Alias of the connection to check (optional, defaults to the active alias).

        Raises:
        - ValueError: If the connection does not exist.

        Example:
        | Check If Database Connection Exists    alias=myalias

        """
        alias = self._resolve_alias(alias)
        if alias not in self.connection_manager.db_connection_pool:
            raise ValueError(f"No database connection exists for alias '{alias}'.")

    # ----------------------------------------------------------------- #
    # Conversion helpers
    # ----------------------------------------------------------------- #

    @keyword
    def convert_to_object_id(self, value: str) -> ObjectId:
        """
        Convert a document id in string form into a BSON ObjectId.

        Query keywords convert a string ``_id`` automatically, so this is only needed
        when building a query document yourself or when nesting an id inside an
        aggregation pipeline.

        Arguments:
        - ``value``: The 24-character hexadecimal id.

        Returns:
        - The value as an ObjectId.

        Example:
        | ${oid}    Convert To Object Id    ${doc_id}

        """
        return ObjectId(value)

    # ----------------------------------------------------------------- #
    # Documents from files
    # ----------------------------------------------------------------- #

    @keyword
    def load_document(self, path: str, **arguments: Any) -> dict:
        """
        Read a document from a JSON file, ready to insert or to update with.

        The file is MongoDB Extended JSON, so it can hold the types MongoDB stores rather
        than only what plain JSON can express. See `Documents From Files` for the whole
        picture; the short version is that the file is read in four steps:

        1. ``${...}`` variables are replaced from the ones the calling suite can see, so a
           value shared by a whole suite is written once. One that resolves to nothing
           fails the keyword.
        2. ``{...}`` placeholders are filled from this keyword's named arguments, so a
           value that differs on every call is given at the call. One that is left
           unfilled fails the keyword. A placeholder is one the file itself is written
           with: braces that arrive in step 1, as part of a variable's value, are data and
           are inserted as they are.
        3. ``$oid``, ``$date``, ``$numberInt`` and ``$numberDouble`` become ``ObjectId``,
           ``datetime``, ``int`` and ``float``. Plain JSON values keep their own types,
           and MongoDB's ``$``-prefixed update operators are left alone, so an update
           document works here as well as a document to insert.
        4. Any argument that is not a placeholder is written in as a dotted override path.

        Arguments:
        - ``path``: File name, resolved against the ``document_path`` given at import, or
          a path, used as written.
        - ``arguments``: A value for each ``{placeholder}`` the file declares, and a dotted
          path to a value for each field to override. Which one an argument is depends on
          the file: a name it declares as a placeholder fills that placeholder, and
          anything else is a path. ``ingredients.0`` is the first item of a list, so one
          syntax covers objects and lists both. Every step of an override path has to exist
          in the document: a path that does not is a typo far more often than it is a field
          meant to be added, and it fails with what the document did hold at that point.

        Returns:
        - The document, as a dictionary whose fields Robot Framework can reach with
          ``${document.field}``.

        Example:
        | ${document}    Load Document    order.json
        | ${document}    Load Document    order.json    unique_id=order-1    customerId=${customer_id}
        | ${document}    Load Document    order.json    &{placeholders}
        | ${document}    Load Document    order.json    status=shipped    lines.0.quantity=3
        | ${doc_id}      Insert Document    collection_name=orders    document=${document}

        A dictionary given as ``&{placeholders}`` is expanded into named arguments by Robot
        Framework, so an empty one fills nothing and the file's own values stand.

        See `Insert Document From File` for the last two lines written as one keyword.

        """
        document_file = resolve_document_file(path, self.document_path)
        text = document_file.read_text(encoding="utf-8")
        substituted = substitute_variables(text, document_file.name)
        # From the file as it was read, so a variable whose value contains braces is data.
        allowed = declared_placeholders(text)
        document = build_document(substituted, arguments, document_file.name, allowed)
        logger.debug(f"Loaded document from '{document_file}': {document!r}")
        return cast(dict, self._as_dot_dict(document))

    # ----------------------------------------------------------------- #
    # Inserting
    # ----------------------------------------------------------------- #

    @keyword
    def insert_document(self, collection_name: str, document: dict, alias: Optional[str] = None) -> Any:
        """
        Insert a document into a collection.

        Arguments:
        - ``collection_name``: Name of the collection where the document will be inserted.
        - ``document``: Document to insert as a dictionary.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - The ID of the inserted document. This is a BSON ``ObjectId`` unless the
          document supplied its own ``_id``, so it has no length and keywords such as
          `Should Not Be Empty` do not apply to it.

        Example:
        | ${doc_id}    Insert Document    collection_name=mycollection    document={"key": "value"}

        """
        collection = self._get_collection(collection_name, alias)
        return collection.insert_one(document).inserted_id

    @keyword
    def insert_documents(self, collection_name: str, documents: list, alias: Optional[str] = None, ordered: bool = True) -> list:
        """
        Insert several documents into a collection in one round trip.

        Arguments:
        - ``collection_name``: Name of the collection where the documents will be inserted.
        - ``documents``: List of documents to insert.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``ordered``: Whether to stop at the first document that fails (optional,
          on by default). Turn it off to insert every document that can be inserted and
          report the failures at the end, which is what you want when seeding fixtures
          into a collection that may already hold some of them. The keyword still fails
          either way; ``ordered`` decides only how much was written before it did.

        Returns:
        - The IDs of the inserted documents, in the order given.

        Example:
        | ${ids}    Insert Documents    collection_name=mycollection    documents=[{"key": "a"}, {"key": "b"}]
        | ${ids}    Insert Documents    collection_name=mycollection    documents=${docs}    ordered=${False}

        """
        collection = self._get_collection(collection_name, alias)
        return collection.insert_many(documents, ordered=ordered).inserted_ids

    @keyword
    def insert_document_from_file(self, collection_name: str, path: str, alias: Optional[str] = None,
                                  **arguments: Any) -> Any:
        """
        Insert a document read from a JSON file, which is `Load Document` and
        `Insert Document` in one step.

        Seeding from a file and inserting it is the shape a fixture almost always wants,
        and the document itself is rarely worth a variable. Take it in two keywords
        instead when the same document is inserted more than once, or when the test needs
        the document as well as what was stored.

        Arguments:
        - ``collection_name``: Name of the collection where the document will be inserted.
        - ``path``: File name or path, resolved exactly as `Load Document` resolves it.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``arguments``: Placeholder values and dotted override paths, as `Load Document`
          takes them. A placeholder or field genuinely named ``collection_name``, ``path``
          or ``alias`` cannot be given here, since those name this keyword's own arguments;
          use `Load Document` and `Insert Document` for that document.

        Returns:
        - The ID of the inserted document, as `Insert Document` returns it.

        Example:
        | ${doc_id}    Insert Document From File    collection_name=orders    path=order.json
        | ${doc_id}    Insert Document From File    collection_name=orders    path=order.json    unique_id=order-1
        | ${doc_id}    Insert Document From File    collection_name=orders    path=order.json    status=shipped

        """
        document = self.load_document(path, **arguments)
        return self.insert_document(collection_name, document, alias)

    # ----------------------------------------------------------------- #
    # Reading
    # ----------------------------------------------------------------- #

    @keyword
    def find_document(self, collection_name: str, alias: Optional[str] = None, **params: Any) -> Optional[dict]:
        """
        Find a single document in a collection.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection to search.
        - ``params``: Query parameters to locate the document.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - The found document, or None if no document matches the query.

        Example:
        | ${document}    Find Document    collection_name=mycollection    key=value

        """
        collection = self._get_collection(collection_name, alias)
        return self._as_dot_dict(collection.find_one(self._normalise_query(params)))

    @keyword
    def find_document_with_query(self, collection_name: str, query: dict, alias: Optional[str] = None, projection: Optional[dict] = None, sort: Optional[dict] = None) -> Optional[dict]:
        """
        Find a single document using a MongoDB query document.

        Use this when the query needs operators such as ``$gte``, ``$in`` or ``$regex``,
        which simple key=value parameters cannot express.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection to search.
        - ``query``: MongoDB query document.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``projection``: Fields to include or exclude, e.g. ``{"name": 1}`` (optional).
        - ``sort``: Fields to sort by before taking the first match, where 1 is
          ascending and -1 descending, e.g. ``{"created": -1}`` (optional).

        Returns:
        - The found document, or None if no document matches the query.

        Example:
        | ${document}    Find Document With Query    collection_name=mycollection    query={"score": {"$gte": 10}}    sort={"score": -1}

        """
        documents = self._find(collection_name, query, alias, projection, sort, limit=1, skip=0)
        return documents[0] if documents else None

    @keyword
    def find_documents(self, collection_name: str, alias: Optional[str] = None, projection: Optional[dict] = None, sort: Optional[dict] = None, limit: int = 0, skip: int = 0, **params: Any) -> list:
        """
        Find every document in a collection matching the given parameters.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection to search.
        - ``params``: Query parameters to locate the documents. Omit them to return the
          whole collection.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``projection``: Fields to include or exclude, e.g. ``{"name": 1}`` (optional).
        - ``sort``: Fields to sort by, where 1 is ascending and -1 descending (optional).
        - ``limit``: Maximum number of documents to return, 0 for no limit (optional).
        - ``skip``: Number of matching documents to skip (optional).

        Returns:
        - A list of documents, empty when nothing matches.

        Example:
        | ${documents}    Find Documents    collection_name=mycollection    key=value    sort={"created": -1}    limit=10

        """
        return self._find(collection_name, params, alias, projection, sort, limit, skip)

    @keyword
    def find_documents_with_query(self, collection_name: str, query: dict, alias: Optional[str] = None, projection: Optional[dict] = None, sort: Optional[dict] = None, limit: int = 0, skip: int = 0) -> list:
        """
        Find every document matching a MongoDB query document.

        Use this when the query needs operators such as ``$gte``, ``$in`` or ``$regex``,
        which simple key=value parameters cannot express.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection to search.
        - ``query``: MongoDB query document.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``projection``: Fields to include or exclude, e.g. ``{"name": 1}`` (optional).
        - ``sort``: Fields to sort by, where 1 is ascending and -1 descending (optional).
        - ``limit``: Maximum number of documents to return, 0 for no limit (optional).
        - ``skip``: Number of matching documents to skip (optional).

        Returns:
        - A list of documents, empty when nothing matches.

        Example:
        | ${documents}    Find Documents With Query    collection_name=mycollection    query={"score": {"$gte": 10}}    limit=5

        """
        return self._find(collection_name, query, alias, projection, sort, limit, skip)

    @keyword
    def count_documents(self, collection_name: str, alias: Optional[str] = None, limit: int = 0, skip: int = 0, **params: Any) -> int:
        """
        Count the number of documents in a collection matching a query.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``limit``: Stop counting after this many matches, 0 for no limit (optional).
          Use it to answer "are there at least N?" without counting a large collection.
        - ``skip``: Number of matching documents to ignore before counting (optional).
        - ``params``: key-value pairs to count matching documents.

        Returns:
        - The count of matching documents.

        Example:
        | ${count}    Count Documents    collection_name=mycollection    key=value

        """
        collection = self._get_collection(collection_name, alias)
        return collection.count_documents(self._normalise_query(params), **self._count_options(limit, skip))

    @keyword
    def count_documents_with_query(self, collection_name: str, query: dict, alias: Optional[str] = None, limit: int = 0, skip: int = 0) -> int:
        """
        Count the documents matching a MongoDB query document.

        Use this when the query needs operators such as ``$gte``, ``$in`` or ``$regex``,
        which simple key=value parameters cannot express.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``query``: MongoDB query document.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``limit``: Stop counting after this many matches, 0 for no limit (optional).
        - ``skip``: Number of matching documents to ignore before counting (optional).

        Returns:
        - The count of matching documents.

        Example:
        | ${count}    Count Documents With Query    collection_name=mycollection    query={"score": {"$gte": 10}}

        """
        collection = self._get_collection(collection_name, alias)
        return collection.count_documents(self._normalise_query(query), **self._count_options(limit, skip))

    @keyword
    def get_estimated_document_count(self, collection_name: str, alias: Optional[str] = None) -> int:
        """
        Return roughly how many documents a collection holds, without counting them.

        The number comes from collection metadata rather than a query, so it answers
        immediately on a collection of any size. The cost is accuracy: after an unclean
        shutdown, and briefly during a write, it can be wrong. Use `Count Documents`
        whenever the exact number is what the test is asserting.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - The estimated number of documents in the collection.

        Example:
        | ${count}    Get Estimated Document Count    collection_name=mycollection

        """
        collection = self._get_collection(collection_name, alias)
        return collection.estimated_document_count()

    @keyword
    def get_distinct_values(self, collection_name: str, field: str, query: Optional[dict] = None, alias: Optional[str] = None) -> list:
        """
        Return each value a field takes, once, across the matching documents.

        Answers "which statuses appear in this collection?" without an aggregation
        pipeline. Where the field holds an array, every element counts as a value.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``field``: Field whose values to collect, e.g. ``status`` or ``address.city``.
        - ``query``: MongoDB query narrowing which documents are considered (optional,
          defaults to the whole collection).
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - A list of the distinct values. The order is not defined, so sort it before
          comparing against an expected list.

        Example:
        | ${statuses}    Get Distinct Values    collection_name=orders    field=status
        | ${statuses}    Get Distinct Values    collection_name=orders    field=status    query={"total": {"$gte": 100}}

        """
        collection = self._get_collection(collection_name, alias)
        return collection.distinct(field, self._normalise_query(query) if query else None)

    @keyword
    def execute_query(self, collection_name: str, pipeline: list, alias: Optional[str] = None, allow_disk_use: bool = False) -> list:
        """
        Execute an aggregation pipeline query on a collection.

        A string ``_id`` inside a pipeline is not converted automatically; use
        `Convert To Object Id` when a stage needs to match one.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``pipeline``: Aggregation pipeline as a list of stages.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``allow_disk_use``: Let a stage spill to temporary files when it exceeds the
          server's 100 MB memory limit (optional). Turn it on if a large ``$group`` or
          ``$sort`` fails with an exceeded-memory-limit error.

        Returns:
        - A list of query results.

        Example:
        | ${results}    Execute Query    collection_name=mycollection    pipeline=[{"$match": {"key": "value"}}]

        """
        # Robot Framework's own conversion rejects a non-list before this runs, so from a
        # suite this guard is unreachable. It answers a caller in Python, where nothing
        # else would check before the driver failed further in.
        if not isinstance(pipeline, list):
            raise TypeError("Invalid pipeline: must be a list of stages.")

        collection = self._get_collection(collection_name, alias)
        options: dict[str, Any] = {"allowDiskUse": True} if allow_disk_use else {}
        return self._as_dot_dict(list(collection.aggregate(pipeline, **options)))

    @keyword
    def explain_query(self, collection_name: str, query: Optional[dict] = None, alias: Optional[str] = None,
                      projection: Optional[dict] = None, sort: Optional[dict] = None, limit: int = 0, skip: int = 0,
                      verbosity: str = "executionStats", **params: Any) -> dict:
        """
        Report how MongoDB answers a query: which plan it chose and what it searched for.

        *This keyword is a diagnostic and asserts nothing.* It is for the moment a find
        keyword returns nothing and gives no reason, and it is not meant to stay in a
        passing test. Nothing here should be asserted on — see ``collection_scan`` below
        for why the obvious assertion is the wrong one.

        The field to read first is ``index_bounds``: the values the server actually
        searched for, as it understood them.

        | '_id.date': ['[new Date(1702996077710), new Date(1702996077710)]']

        A query that matches nothing and errors on nothing is nearly always a query that
        asked for something other than what the caller meant, and this is where that
        becomes visible — a ``datetime`` at midnight against documents stored with
        millisecond precision, or a string where the collection holds an ObjectId. Compare
        the bounds with what the suite passed.

        Takes the query either way the find keywords take it: as free arguments like
        `Find Document`, or as a ``query`` document like `Find Document With Query`.
        Giving both fails, so an explain can be dropped in beside a failing call unchanged.

        Arguments:
        - ``collection_name``: Name of the collection to explain the query against.
        - ``query``: MongoDB query document, as `Find Document With Query` takes it
          (optional). Mutually exclusive with ``params``.
        - ``params``: Query parameters, as `Find Document` takes them. Mutually exclusive
          with ``query``.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``projection``, ``sort``, ``limit``, ``skip``: The rest of the find, so that
          what is explained is the query the suite actually runs (optional).
        - ``verbosity``: How much the server reports (optional). ``executionStats``, the
          default, runs the winning plan and counts what it read. ``queryPlanner`` picks a
          plan without running it, leaving the four counters below empty.
          ``allPlansExecution`` adds the plans that were rejected.

        Returns:
        - A dictionary summarising the plan, with the server's own explain document under
          ``raw``. The summary is also logged at INFO, a field to a line, and the whole
          explain document at DEBUG, indented:

        | ``stage``           | The winning plan's stage, e.g. ``IXSCAN`` or ``COLLSCAN``.        |
        | ``index_name``      | Name of the index used, or None if none was.                     |
        | ``index_bounds``    | The values searched for, per indexed field.                      |
        | ``collection_scan`` | Whether the plan reads the collection rather than an index.      |
        | ``keys_examined``   | ``totalKeysExamined``: index entries read.                       |
        | ``docs_examined``   | ``totalDocsExamined``: documents read.                           |
        | ``returned``        | ``nReturned``: documents matched.                                |
        | ``duration_ms``     | ``executionTimeMillis``.                                         |
        | ``shards``          | The same per shard, on a sharded cluster only.                   |

        ``collection_scan`` is reported as information for a person to read, and is not
        something to assert on. MongoDB legitimately chooses a collection scan on a small
        collection, where reading it beats an index lookup plus a fetch, so an assertion
        that no scan happens passes against production-sized data and fails against a
        freshly seeded test collection with nothing wrong. To require that an index
        exists, assert that directly with `Collection Should Have Index`.

        The query is rewritten as every find keyword rewrites it, so a string ``_id`` is
        explained as the ObjectId that would really be sent. See `Object Ids`.

        Aggregation pipelines are not covered; explain one with `Run Database Command`.

        Example:
        | ${plan}    Explain Query    collection_name=readings    _id.deviceId=${device_id}    _id.date=${date}
        | Log    ${plan.index_bounds}
        | ${plan}    Explain Query    collection_name=orders    query={"status": "new"}    sort={"placedAt": -1}

        """
        if query is not None and params:
            raise ValueError(
                f"Give the query either as 'query' or as free arguments, not both. "
                f"Got query={query!r} and {sorted(params)}."
            )
        database = self._get_database(alias)
        find: dict[str, Any] = {
            "find": collection_name,
            "filter": self._normalise_query(query if query is not None else params),
        }
        if projection:
            find["projection"] = projection
        if sort:
            find["sort"] = sort
        if limit:
            find["limit"] = limit
        if skip:
            find["skip"] = skip
        raw = dict(database.command({"explain": find, "verbosity": verbosity}))
        summary = self._summarise_explain(raw)
        logger.info(self._format_explain(collection_name, find["filter"], summary))
        # The whole explain at DEBUG, indented. It is far too long to read every time and
        # exactly what is wanted on the occasion the summary leaves out the answer.
        logger.debug(json.dumps(raw, indent=2, default=str))
        summary["raw"] = raw
        return self._as_dot_dict(summary)

    # ----------------------------------------------------------------- #
    # Updating
    # ----------------------------------------------------------------- #

    @keyword
    def update_document(self, collection_name: str, query: dict, update: dict, alias: Optional[str] = None, upsert: bool = False) -> Optional[dict]:
        """
        Update a single document in a collection.

        The fields in ``update`` are merged into the document; fields already on it and
        not mentioned are left as they are. Use `Replace Document` to replace the whole
        document instead.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``query``: Query to find the document to update.
        - ``update``: Fields to set on the document.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``upsert``: Insert a document when the query matches nothing (optional). The
          new document is built from the query and the update together, which makes this
          the way to write a fixture step that does not care whether it has run before.

        Returns:
        - The updated document, or None if no document matches and ``upsert`` is off.
          With ``upsert`` on, the newly inserted document is returned.

        Example:
        | ${updated_doc}    Update Document    collection_name=mycollection    query={"key": "value"}    update={"key": "new_value"}
        | ${document}       Update Document    collection_name=users    query={"email": "a@example.test"}    update={"active": ${True}}    upsert=${True}

        """
        collection = self._get_collection(collection_name, alias)
        return self._as_dot_dict(
            collection.find_one_and_update(self._normalise_query(query), {'$set': update}, return_document=ReturnDocument.AFTER, upsert=upsert)
        )

    @keyword
    def update_document_with_operators(self, collection_name: str, query: dict, update: dict, alias: Optional[str] = None, upsert: bool = False) -> Optional[dict]:
        """
        Update a single document in a collection using raw MongoDB update operators.

        This keyword allows you to use MongoDB update operators like $set, $push, $pull, etc.
        directly without automatic wrapping. Use this when you need operations other than $set.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``query``: Query to find the document to update.
        - ``update``: Raw MongoDB update document with operators (e.g., {"$push": {...}, "$set": {...}}).
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``upsert``: Insert a document when the query matches nothing (optional). The
          new document is built from the query and the update together.

        Returns:
        - The updated document, or None if no document matches and ``upsert`` is off.
          With ``upsert`` on, the newly inserted document is returned.

        Example:
        | ${updated_doc}    Update Document With Operators    collection_name=mycollection    query={"key": "value"}    update={"$push": {"items": "new_item"}, "$set": {"modified": "2025-01-01"}}

        """
        collection = self._get_collection(collection_name, alias)
        return self._as_dot_dict(
            collection.find_one_and_update(self._normalise_query(query), update, return_document=ReturnDocument.AFTER, upsert=upsert)
        )

    @keyword
    def update_documents(self, collection_name: str, query: dict, update: dict, alias: Optional[str] = None, upsert: bool = False) -> int:
        """
        Update every document in a collection matching a query.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``query``: Query to find the documents to update.
        - ``update``: Fields to set on each matching document.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``upsert``: Insert a document when the query matches nothing (optional). At
          most one document is ever inserted, however many the query would have matched.

        Returns:
        - The count of documents that were *changed*. An upserted document was inserted
          rather than changed, so it is not counted and the keyword returns 0; the id of
          the inserted document is written to the log instead.

        Example:
        | ${updated_count}    Update Documents    collection_name=mycollection    query={"key": "value"}    update={"checked": ${True}}

        """
        collection = self._get_collection(collection_name, alias)
        return self._modified_count(collection.update_many(self._normalise_query(query), {'$set': update}, upsert=upsert))

    @keyword
    def update_documents_with_operators(self, collection_name: str, query: dict, update: dict, alias: Optional[str] = None, upsert: bool = False) -> int:
        """
        Update every matching document using raw MongoDB update operators.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``query``: Query to find the documents to update.
        - ``update``: Raw MongoDB update document with operators.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``upsert``: Insert a document when the query matches nothing (optional). At
          most one document is ever inserted, however many the query would have matched.

        Returns:
        - The count of documents that were *changed*. An upserted document was inserted
          rather than changed, so it is not counted and the keyword returns 0; the id of
          the inserted document is written to the log instead.

        Example:
        | ${updated_count}    Update Documents With Operators    collection_name=mycollection    query={"key": "value"}    update={"$inc": {"attempts": 1}}

        """
        collection = self._get_collection(collection_name, alias)
        return self._modified_count(collection.update_many(self._normalise_query(query), update, upsert=upsert))

    @keyword
    def replace_document(self, collection_name: str, query: dict, replacement: dict, alias: Optional[str] = None, upsert: bool = False) -> Optional[dict]:
        """
        Replace a whole document with a new one.

        `Update Document` merges its fields into the document and leaves the rest
        alone, so it can never remove a field. This keyword swaps the entire document
        for ``replacement``, which is what to use when a field has to disappear or when
        the expected document is easier to state in full than as a set of changes. The
        ``_id`` is the one thing that survives, because MongoDB does not allow it to
        change.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``query``: Query to find the document to replace.
        - ``replacement``: The new document. It holds plain fields, not update
          operators — pass those to `Update Document With Operators` instead.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``upsert``: Insert ``replacement`` when the query matches nothing (optional).

        Returns:
        - The document as it now stands, or None if nothing matched and ``upsert`` is off.

        Example:
        | ${document}    Replace Document    collection_name=orders    query={"order_id": "A-1"}    replacement={"order_id": "A-1", "status": "shipped"}

        """
        collection = self._get_collection(collection_name, alias)
        return self._as_dot_dict(
            collection.find_one_and_replace(self._normalise_query(query), replacement, return_document=ReturnDocument.AFTER, upsert=upsert)
        )

    # ----------------------------------------------------------------- #
    # Deleting
    # ----------------------------------------------------------------- #

    @keyword
    def delete_document(self, collection_name: str, alias: Optional[str] = None, **params: Any) -> int:
        """
        Delete a single document from a collection.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``params``: Query parameters to locate the document to delete.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - The count of deleted documents (0 or 1).

        Example:
        | ${deleted_count}    Delete Document    collection_name=mycollection    key=value

        """
        collection = self._get_collection(collection_name, alias)
        return collection.delete_one(self._normalise_query(params)).deleted_count

    @keyword
    def delete_many(self, collection_name: str, alias: Optional[str] = None, **params: Any) -> int:
        """
        Delete multiple documents from a collection.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``params``: Query parameters to find the documents to delete.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - Count of deleted documents.

        Example:
        | ${deleted_count}    Delete Many    collection_name=mycollection    key=value

        """
        collection = self._get_collection(collection_name, alias)
        return collection.delete_many(self._normalise_query(params)).deleted_count

    @keyword
    def delete_documents_with_query(self, collection_name: str, query: dict, alias: Optional[str] = None) -> int:
        """
        Delete multiple documents from a collection using a complex MongoDB query.

        This keyword allows you to use MongoDB query operators like $gte, $lt, $in, $regex, etc.
        directly without limitations. Use this when you need operations beyond simple key=value matching.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``query``: MongoDB query document with operators (e.g., {"date": {"$gte": start, "$lt": end}}).
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - Count of deleted documents.

        Example:
        | ${start_date}    Get Current Date    result_format=datetime
        | ${end_date}      Evaluate    $start_date + timedelta(days=1)    modules=datetime
        | ${query}         Create Dictionary    userId=user123
        | ${date_range}    Create Dictionary    $gte=${start_date}    $lt=${end_date}
        | Set To Dictionary    ${query}    date=${date_range}
        | ${deleted_count}    Delete Documents With Query    collection_name=activity    query=${query}

        """
        collection = self._get_collection(collection_name, alias)
        return collection.delete_many(self._normalise_query(query)).deleted_count

    @keyword
    def delete_all_documents_from_collection(self, collection_name: str, alias: Optional[str] = None) -> int:
        """
        Delete all documents from a collection.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - The count of deleted documents.

        Example:
        | ${deleted_count}    Delete All Documents From Collection    collection_name=mycollection

        """
        collection = self._get_collection(collection_name, alias)
        return collection.delete_many({}).deleted_count

    @keyword
    def delete_document_and_return_it(self, collection_name: str, alias: Optional[str] = None, **params: Any) -> Optional[dict]:
        """
        Delete a single document and return what was deleted.

        The other delete keywords report only a count, so asserting on the document
        that went means reading it first and deleting it afterwards — two operations,
        between which anything else touching the collection can change the answer. This
        does both in one, which is also how to drain a queue collection: take a
        document, and be sure no other worker takes the same one.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``params``: Query parameters to locate the document to delete.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - The document as it was just before deletion, or None if nothing matched.

        Example:
        | ${document}    Delete Document And Return It    collection_name=queue    status=pending

        """
        collection = self._get_collection(collection_name, alias)
        return self._as_dot_dict(collection.find_one_and_delete(self._normalise_query(params)))

    # ----------------------------------------------------------------- #
    # Collections
    # ----------------------------------------------------------------- #

    @keyword
    def list_collections(self, alias: Optional[str] = None) -> list[str]:
        """
        List the names of every collection in the database.

        Arguments:
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - A list of collection names. Empty for a database that holds nothing, since
          MongoDB does not create a database until something is written to it.

        Example:
        | ${collections}    List Collections
        | Should Contain    ${collections}    orders

        """
        database = self._get_database(alias)
        return database.list_collection_names()

    @keyword
    def create_collection(self, collection_name: str, alias: Optional[str] = None, **options: Any) -> None:
        """
        Create a collection explicitly.

        MongoDB creates a collection on its own the first time something is written to
        it, so this is only needed when the collection has to exist *before* that, or
        when it needs options an implicit creation cannot give it: a capped size, a
        document validator, or a time series configuration.

        Fails if the collection already exists, which makes it a check as well as a
        setup step.

        Arguments:
        - ``collection_name``: Name of the collection to create.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``options``: Any collection option MongoDB accepts, passed through under the
          name the server uses: ``capped``, ``size``, ``max``, ``validator``,
          ``expireAfterSeconds``, ``timeseries``.

        Example:
        | Create Collection    collection_name=events
        | Create Collection    collection_name=recent    capped=${True}    size=${1048576}
        | Create Collection    collection_name=readings    timeseries={"timeField": "ts", "metaField": "sensor"}

        """
        database = self._get_database(alias)
        database.create_collection(collection_name, **options)
        logger.info(f"Created collection '{collection_name}'.")

    @keyword
    def drop_collection(self, collection_name: str, alias: Optional[str] = None) -> None:
        """
        Drop a collection, with its documents, its indexes and its options.

        `Delete All Documents From Collection` empties a collection but leaves
        everything defined on it in place, so a unique index created by an earlier test
        still rejects the next one's fixtures. Dropping is what actually resets it.

        Dropping a collection that does not exist succeeds and does nothing, so this is
        safe in a teardown that runs after a failed setup.

        Arguments:
        - ``collection_name``: Name of the collection to drop.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Example:
        | Drop Collection    collection_name=mycollection

        """
        database = self._get_database(alias)
        database.drop_collection(collection_name)
        logger.info(f"Dropped collection '{collection_name}'.")

    # ----------------------------------------------------------------- #
    # Databases and server
    # ----------------------------------------------------------------- #

    @keyword
    def list_databases(self, alias: Optional[str] = None) -> list[str]:
        """
        List the names of every database on the server.

        Arguments:
        - ``alias``: Alias of the connection whose server to ask (optional, defaults to
          the active alias). The connection selects the server, not the database, so the
          list covers every database that connection can see.

        Returns:
        - A list of database names.

        Example:
        | ${databases}    List Databases

        """
        client = self._get_client(alias)
        return client.list_database_names()

    @keyword
    def drop_database(self, db_name: str, alias: Optional[str] = None) -> None:
        """
        Drop a database and everything in it.

        *This deletes data and cannot be undone.* It is meant for a test run that
        creates its own throwaway database; pointing it at a shared one destroys
        whatever else was using it. The name is always explicit, never the connected
        database by default, so this cannot happen by leaving an argument out.

        Dropping a database that does not exist succeeds and does nothing.

        Note that connections stay in the pool afterwards and keep working — MongoDB
        recreates the database the next time something is written to it.

        Arguments:
        - ``db_name``: Name of the database to drop.
        - ``alias``: Alias of the connection whose server to act on (optional, defaults
          to the active alias).

        Example:
        | Drop Database    db_name=test_run_1234

        """
        client = self._get_client(alias)
        client.drop_database(db_name)
        logger.info(f"Dropped database '{db_name}'.")

    @keyword
    def get_server_info(self, alias: Optional[str] = None) -> dict:
        """
        Return the server's build information.

        Chiefly useful for skipping a test that needs a feature the server is too old
        to have, rather than watching it fail with an obscure error.

        Arguments:
        - ``alias``: Alias of the connection whose server to ask (optional, defaults to
          the active alias).

        Returns:
        - The server's build information. ``version`` holds the version as a string and
          ``versionArray`` holds it as numbers, which is what to compare against.

        Example:
        | ${info}    Get Server Info
        | Skip If    ${info.versionArray}[0] < 7    Time series collections need MongoDB 7

        """
        client = self._get_client(alias)
        return self._as_dot_dict(dict(client.server_info()))

    @keyword
    def run_database_command(self, command: Union[dict, str], alias: Optional[str] = None, **kwargs: Any) -> dict:
        """
        Run a raw database command and return its reply.

        This is the way through to everything the library does not wrap. Server
        statistics, storage sizes, query plans and administrative commands are all
        database commands, and there are far too many to give each a keyword.

        Arguments:
        - ``command``: The command, either as a name on its own (``ping``) or as a
          document when it takes arguments (``{"collStats": "orders"}``). A document is
          tried first, so a value that is not one is sent as a bare command name.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
          The command runs against that connection's database.
        - ``kwargs``: Further command options, for the form where ``command`` is a name.

        Returns:
        - The server's reply as a dictionary. A reply that reached the server always
          contains ``ok``; a command the server rejected raises instead.

        Example:
        | ${reply}    Run Database Command    command=ping
        | ${stats}    Run Database Command    command={"collStats": "orders"}
        | ${plan}     Run Database Command    command={"explain": {"find": "orders", "filter": {"status": "new"}}}

        """
        database = self._get_database(alias)
        return self._as_dot_dict(dict(database.command(self._as_command(command), **kwargs)))

    # ----------------------------------------------------------------- #
    # Indexes
    # ----------------------------------------------------------------- #

    @keyword
    def create_index(self, collection_name: str, keys: dict, alias: Optional[str] = None, unique: bool = False, index_name: Optional[str] = None, sparse: bool = False, expire_after_seconds: Optional[int] = None, partial_filter_expression: Optional[dict] = None) -> str:
        """
        Create an index on a collection.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``keys``: Fields to index, where 1 is ascending and -1 descending,
          e.g. ``{"email": 1}``.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``unique``: Whether the index rejects duplicate values (optional).
        - ``index_name``: Name for the index (optional, MongoDB derives one otherwise).
        - ``sparse``: Index only the documents that have the field (optional). Combined
          with ``unique`` this allows many documents to omit the field while those that
          do have it stay unique — without it, a second document missing the field
          counts as a duplicate null.
        - ``expire_after_seconds``: Make this a TTL index, deleting each document this
          many seconds after the indexed date field (optional). The field must hold a
          date. MongoDB removes expired documents on a background sweep that runs about
          once a minute, so a test cannot expect the deletion to be immediate.
        - ``partial_filter_expression``: Index only the documents matching this query
          (optional), e.g. ``{"status": {"$ne": "archived"}}``.

        Returns:
        - The name of the created index.

        Example:
        | ${name}    Create Index    collection_name=mycollection    keys={"email": 1}    unique=${True}
        | ${name}    Create Index    collection_name=sessions    keys={"created": 1}    expire_after_seconds=${3600}

        """
        collection = self._get_collection(collection_name, alias)
        options: dict[str, Any] = {"unique": unique, "sparse": sparse}
        if index_name:
            options["name"] = index_name
        if expire_after_seconds is not None:
            options["expireAfterSeconds"] = expire_after_seconds
        if partial_filter_expression:
            options["partialFilterExpression"] = partial_filter_expression
        return collection.create_index(list(keys.items()), **options)

    @keyword
    def list_indexes(self, collection_name: str, alias: Optional[str] = None) -> list:
        """
        List the indexes defined on a collection.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - A list of index definitions. Every collection has at least the ``_id_`` index.

        Example:
        | ${indexes}    List Indexes    collection_name=mycollection

        """
        collection = self._get_collection(collection_name, alias)
        return self._as_dot_dict(list(collection.list_indexes()))

    @keyword
    def drop_index(self, collection_name: str, index_name: str, alias: Optional[str] = None) -> None:
        """
        Drop an index from a collection.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``index_name``: Name of the index to drop, as reported by `List Indexes`.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Example:
        | Drop Index    collection_name=mycollection    index_name=email_1

        """
        collection = self._get_collection(collection_name, alias)
        collection.drop_index(index_name)

    @keyword
    def get_index_information(self, collection_name: str, alias: Optional[str] = None) -> dict:
        """
        Return the collection's indexes keyed by name.

        `List Indexes` returns the raw index documents as the server stores them. This
        returns the same information as a dictionary of name to definition, which is
        the shape to use when a test asks about one index it knows the name of.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Returns:
        - A dictionary of index name to its definition. Always contains ``_id_``.

        Example:
        | ${indexes}          Get Index Information    collection_name=mycollection
        | Dictionary Should Contain Key    ${indexes}    email_1
        | Should Be True     ${indexes}[email_1][unique]

        """
        collection = self._get_collection(collection_name, alias)
        return self._as_dot_dict(dict(collection.index_information()))

    @keyword
    def drop_all_indexes(self, collection_name: str, alias: Optional[str] = None) -> None:
        """
        Drop every index on a collection except ``_id_``.

        The ``_id_`` index stays because MongoDB does not allow it to be dropped.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Example:
        | Drop All Indexes    collection_name=mycollection

        """
        collection = self._get_collection(collection_name, alias)
        collection.drop_indexes()
        logger.info(f"Dropped every index except '_id_' on '{collection_name}'.")

    # ----------------------------------------------------------------- #
    # Assertions
    # ----------------------------------------------------------------- #

    @keyword
    def check_query_result(
        self,
        collection_name: str,
        query: dict,
        assertion_operator: AssertionOperator,
        expected_value: Any,
        field: str,
        assertion_message: Optional[str] = None,
        retry_timeout: str = "0 seconds",
        retry_pause: str = "0.5 seconds",
        alias: Optional[str] = None
    ) -> None:
        """
        Check the result of a query against an expected value.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``query``: Query to find the document.
        - ``assertion_operator``: Operator for assertion (e.g., ==, !=, >, <).
        - ``expected_value``: Expected value for the assertion.
        - ``field``: Field in the document to check.
        - ``assertion_message``: Custom message for assertion failure (optional).
        - ``retry_timeout``: Timeout for retrying the query (optional).
        - ``retry_pause``: Pause duration between retries (optional).
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Example:
        | Check Query Result    collection_name=mycollection    query={"key": "value"}    assertion_operator= ==    expected_value=42    field=key

        """
        collection = self._get_collection(collection_name, alias)
        normalised = self._normalise_query(query)

        def check() -> None:
            results = list(collection.find(normalised))
            if not results:
                raise AssertionError("Query returned no results.")

            for document in results:
                if field not in document:
                    raise AssertionError(f"Field '{field}' not found in document.")

                verify_assertion(
                    document[field],
                    assertion_operator,
                    expected_value,
                    f"Field '{field}' value mismatch:",
                    assertion_message
                )

        self._retry_until_no_assertion_error(check, retry_timeout, retry_pause)

    @keyword
    def check_document_count(
        self,
        collection_name: str,
        query: dict,
        assertion_operator: AssertionOperator,
        expected_count: int,
        assertion_message: Optional[str] = None,
        retry_timeout: str = "0 seconds",
        retry_pause: str = "0.5 seconds",
        alias: Optional[str] = None
    ) -> None:
        """
        Check the count of documents matching a query against an expected value.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``query``: Query to count matching documents.
        - ``assertion_operator``: Operator for assertion (e.g., ==, !=, >, <).
        - ``expected_count``: Expected count for the assertion.
        - ``assertion_message``: Custom message for assertion failure (optional).
        - ``retry_timeout``: Timeout for retrying the query (optional).
        - ``retry_pause``: Pause duration between retries (optional).
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Example:
        | Check Document Count    collection_name=mycollection    query={"key": "value"}    assertion_operator= ==    expected_count=5

        """
        collection = self._get_collection(collection_name, alias)
        normalised = self._normalise_query(query)

        def check() -> None:
            verify_assertion(
                collection.count_documents(normalised),
                assertion_operator,
                expected_count,
                "Wrong document count:",
                assertion_message
            )

        self._retry_until_no_assertion_error(check, retry_timeout, retry_pause)

    @keyword
    def check_distinct_values(
        self,
        collection_name: str,
        field: str,
        assertion_operator: AssertionOperator,
        expected_value: Any,
        query: Optional[dict] = None,
        assertion_message: Optional[str] = None,
        retry_timeout: str = "0 seconds",
        retry_pause: str = "0.5 seconds",
        alias: Optional[str] = None
    ) -> None:
        """
        Check the set of values a field takes against an expected value.

        Answers questions about a whole collection at once — "no order is left in the
        ``pending`` state", "these are the only currencies in use" — which counting
        cannot express. The values are sorted before the assertion, so an expected list
        should be sorted too; MongoDB does not define the order they come back in.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``field``: Field whose distinct values to check.
        - ``assertion_operator``: Operator for assertion (e.g., ==, !=, contains).
        - ``expected_value``: Expected value for the assertion.
        - ``query``: MongoDB query narrowing which documents are considered (optional).
        - ``assertion_message``: Custom message for assertion failure (optional).
        - ``retry_timeout``: Timeout for retrying the query (optional).
        - ``retry_pause``: Pause duration between retries (optional).
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Example:
        | Check Distinct Values    collection_name=orders    field=status    assertion_operator= ==    expected_value=['new', 'shipped']
        | Check Distinct Values    collection_name=orders    field=status    assertion_operator=not contains    expected_value=pending

        """
        collection = self._get_collection(collection_name, alias)
        normalised = self._normalise_query(query) if query else None

        def check() -> None:
            verify_assertion(
                sorted(collection.distinct(field, normalised)),
                assertion_operator,
                expected_value,
                f"Wrong distinct values for field '{field}':",
                assertion_message
            )

        self._retry_until_no_assertion_error(check, retry_timeout, retry_pause)

    @keyword
    def check_collection_exists(
        self,
        collection_name: str,
        assertion_message: Optional[str] = None,
        retry_timeout: str = "0 seconds",
        retry_pause: str = "0.5 seconds",
        alias: Optional[str] = None
    ) -> None:
        """
        Fail unless the collection exists in the database.

        Arguments:
        - ``collection_name``: Name of the collection that should exist.
        - ``assertion_message``: Custom message for assertion failure (optional).
        - ``retry_timeout``: How long to keep checking before failing (optional). Give
          it a value when something else is expected to create the collection.
        - ``retry_pause``: Pause duration between retries (optional).
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Example:
        | Check Collection Exists    collection_name=orders
        | Check Collection Exists    collection_name=orders    retry_timeout=10 seconds

        """
        database = self._get_database(alias)

        def check() -> None:
            existing = database.list_collection_names()
            if collection_name not in existing:
                raise AssertionError(
                    assertion_message
                    or f"Collection '{collection_name}' does not exist. The database holds: {sorted(existing)}."
                )

        self._retry_until_no_assertion_error(check, retry_timeout, retry_pause)

    @keyword
    def check_index_exists(
        self,
        collection_name: str,
        index_name: str,
        assertion_message: Optional[str] = None,
        retry_timeout: str = "0 seconds",
        retry_pause: str = "0.5 seconds",
        alias: Optional[str] = None
    ) -> None:
        """
        Fail unless the named index exists on the collection.

        Useful for asserting that a migration or an application's start-up actually
        created the index it is supposed to, which is otherwise invisible until a query
        is unexpectedly slow.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``index_name``: Name of the index that should exist, as reported by
          `List Indexes` or `Get Index Information`.
        - ``assertion_message``: Custom message for assertion failure (optional).
        - ``retry_timeout``: How long to keep checking before failing (optional).
        - ``retry_pause``: Pause duration between retries (optional).
        - ``alias``: Alias of the connection (optional, defaults to the active alias).

        Example:
        | Check Index Exists    collection_name=users    index_name=email_1

        """
        collection = self._get_collection(collection_name, alias)

        def check() -> None:
            existing = list(collection.index_information())
            if index_name not in existing:
                raise AssertionError(
                    assertion_message
                    or f"Index '{index_name}' does not exist on '{collection_name}'. It has: {sorted(existing)}."
                )

        self._retry_until_no_assertion_error(check, retry_timeout, retry_pause)

    @keyword
    def collection_should_have_index(
        self,
        collection_name: str,
        keys: dict,
        alias: Optional[str] = None,
        assertion_message: Optional[str] = None,
        retry_timeout: str = "0 seconds",
        retry_pause: str = "0.5 seconds"
    ) -> None:
        """
        Fail unless an index on exactly these fields exists on the collection.

        The guard for an index a suite's queries quietly depend on. Dropping it does not
        break anything visibly: the queries still return the right documents, by reading
        the whole collection to do it, and the suite gets slower until something times
        out somewhere unrelated. This turns that into one failing assertion naming the
        index.

        Asks by fields rather than by name, which `Check Index Exists` does. A name is
        derived from the fields — an index on ``{"_id.deviceId": 1, "_id.date": 1}`` is
        called ``_id.deviceId_1__id.date_1`` — so naming it means writing out a string
        nobody should have to spell, that changes if the index is ever recreated slightly
        differently. The fields are what the queries actually depend on.

        The order of the fields matters and is compared: a compound index serves a query
        on its first field, or its first two, and so on, so an index on
        ``{"deviceId": 1, "date": 1}`` is a different index from one on
        ``{"date": 1, "deviceId": 1}``.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``keys``: Fields the index is on, in order, exactly as `Create Index` takes
          them, e.g. ``{"_id.deviceId": 1, "_id.date": 1}``.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``assertion_message``: Custom message for assertion failure (optional).
        - ``retry_timeout``: How long to keep checking before failing (optional). Give it
          a value when a migration or an application's start-up creates the index.
        - ``retry_pause``: Pause duration between retries (optional).

        Example:
        | Collection Should Have Index    collection_name=readings    keys={"_id.deviceId": 1, "_id.date": 1}
        | Collection Should Have Index    collection_name=users    keys={"email": 1}    retry_timeout=10 seconds

        """
        collection = self._get_collection(collection_name, alias)
        expected = [(field, direction) for field, direction in keys.items()]

        def check() -> None:
            existing = dict(collection.index_information())
            if any(list(definition.get("key", [])) == expected for definition in existing.values()):
                return
            # Every collection that exists has at least ``_id_``, so nothing at all means
            # the collection does not, which is a likelier explanation of the failure than
            # a missing index and is worth saying rather than leaving the sentence empty.
            present = ", ".join(
                f"{name} {dict(definition.get('key', []))}" for name, definition in sorted(existing.items())
            ) or "no indexes at all, so the collection may not exist"
            raise AssertionError(
                assertion_message
                or f"No index on '{collection_name}' has keys {dict(expected)}. It has: {present}."
            )

        self._retry_until_no_assertion_error(check, retry_timeout, retry_pause)

    @keyword
    def document_should_exist(
        self,
        collection_name: str,
        alias: Optional[str] = None,
        assertion_message: Optional[str] = None,
        retry_timeout: str = "0 seconds",
        retry_pause: str = "0.5 seconds",
        **params: Any
    ) -> None:
        """
        Fail unless at least one document matches the given parameters.

        The plain form of the question suites ask most often. Give it a
        ``retry_timeout`` when the document is written by something the test has just
        triggered and does not otherwise wait for.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``params``: Query parameters the document should match.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``assertion_message``: Custom message for assertion failure (optional).
        - ``retry_timeout``: How long to keep looking before failing (optional).
        - ``retry_pause``: Pause duration between retries (optional).

        Example:
        | Document Should Exist    collection_name=orders    order_id=A-1
        | Document Should Exist    collection_name=orders    order_id=A-1    retry_timeout=10 seconds

        """
        collection = self._get_collection(collection_name, alias)
        normalised = self._normalise_query(params)

        def check() -> None:
            if collection.count_documents(normalised, limit=1) == 0:
                raise AssertionError(
                    assertion_message or f"No document in '{collection_name}' matches {normalised}."
                )

        self._retry_until_no_assertion_error(check, retry_timeout, retry_pause)

    @keyword
    def document_should_not_exist(
        self,
        collection_name: str,
        alias: Optional[str] = None,
        assertion_message: Optional[str] = None,
        retry_timeout: str = "0 seconds",
        retry_pause: str = "0.5 seconds",
        **params: Any
    ) -> None:
        """
        Fail if any document matches the given parameters.

        Give it a ``retry_timeout`` when waiting for something to be deleted or to stop
        matching.

        A string ``_id`` in the query is converted to an ObjectId, unless the library
        was imported with ``coerce_object_ids=${False}``. See `Object Ids`.

        Arguments:
        - ``collection_name``: Name of the collection.
        - ``params``: Query parameters no document should match.
        - ``alias``: Alias of the connection (optional, defaults to the active alias).
        - ``assertion_message``: Custom message for assertion failure (optional).
        - ``retry_timeout``: How long to keep checking before failing (optional).
        - ``retry_pause``: Pause duration between retries (optional).

        Example:
        | Document Should Not Exist    collection_name=orders    status=pending

        """
        collection = self._get_collection(collection_name, alias)
        normalised = self._normalise_query(params)

        def check() -> None:
            found = collection.count_documents(normalised)
            if found:
                raise AssertionError(
                    assertion_message
                    or f"Expected no document in '{collection_name}' matching {normalised}, but found {found}."
                )

        self._retry_until_no_assertion_error(check, retry_timeout, retry_pause)
