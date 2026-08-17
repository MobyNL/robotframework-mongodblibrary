# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `Explain Query` reports how MongoDB answered a query: the winning plan's stage, the
  index it used, whether it read the collection rather than an index, how many keys and
  documents it examined, and — the field it exists for — `index_bounds`, the values the
  server actually searched for. A query that matches nothing and reports no error is
  nearly always a query that asked for something other than what the suite meant, and
  comparing the bounds with what was passed is the whole diagnosis:

  ```robotframework
  ${plan}    Explain Query    collection_name=readings    _id.deviceId=${device_id}    _id.date=${date}
  Log    ${plan.index_bounds}
  ```

  It takes the query either way the find keywords take it, as free arguments like
  `Find Document` or as a `query` document like `Find Document With Query`, so it can be
  dropped in beside a failing call without rewriting it. The summary is returned, and
  logged at INFO a field to a line, with each indexed field's bounds on a line of its own:
  Robot Framework keeps newlines and indentation in `log.html`, and a summary on one line
  is readable by nobody. The whole explain document is logged at DEBUG, indented, and
  returned under `raw` for anything the summary leaves out.
  `verbosity` selects `executionStats`, which is the default and runs the winning plan,
  `queryPlanner`, which picks a plan without running it, or `allPlansExecution`, which
  adds the rejected plans.

  The summary is derived rather than copied, because the explain document's shape differs
  by server version and topology while the questions do not: a slot-based plan nests its
  stages under `queryPlan`, a sharded cluster reports per shard, and the `_id` fast path
  is `EXPRESS_IXSCAN` on MongoDB 8 and `IDHACK` before it. A collection scan is detected
  by the presence of a `COLLSCAN` rather than by an allowlist of index stage names, so no
  version check is involved.

  The keyword is a diagnostic and asserts nothing, `collection_scan` included. MongoDB
  rightly chooses a scan on a small collection, where reading it beats an index lookup
  plus a fetch, so an assertion that no scan happens passes against production-sized data
  and fails against a freshly seeded test collection with nothing wrong.

- `Collection Should Have Index` fails unless an index on exactly the given fields exists,
  reading the collection's index definitions rather than a query plan, so it cannot flake:

  ```robotframework
  Collection Should Have Index    collection_name=readings    keys={"_id.deviceId": 1, "_id.date": 1}
  ```

  Asks by fields rather than by name, which `Check Index Exists` does. The name is derived
  from the fields — `_id.deviceId_1__id.date_1` — so naming it means writing out a string
  nobody should have to spell and that changes if the index is ever recreated slightly
  differently; the fields are what the queries depend on. The order of the fields is
  compared, because a compound index serves its fields left to right and the same fields
  in the other order are a different index. Failure lists every index the collection does
  have, with its keys.

  This is the guard for an index a suite quietly depends on. Dropping it breaks nothing
  visibly: the queries still return the right documents, by reading the whole collection
  to do it, and the suite gets slower until something times out somewhere unrelated.

- Documentation for the empty result a collection keyed by a compound `_id` produces three
  ways, none of which errors: the automatic `_id_` index cannot serve a query on part of
  the id, since it stores the subdocument as one opaque value; matching the whole `_id`
  compares the stored BSON and is therefore field-order sensitive; and a date compares
  exactly, so a `datetime` at midnight never matches a document stored with milliseconds.

- `Load Document` reads a seed document from a JSON file, and `Insert Document From File`
  reads one and inserts it in a single step. A new `document_path` import argument names
  the directory that documents given by file name are looked up in; a path given to the
  keyword works with or without it, so the argument only removes the repetition.

  The file is read as MongoDB Extended JSON, so `$oid`, `$date`, `$numberInt` and
  `$numberDouble` become `ObjectId`, `datetime`, `int` and `float`, and the document is
  stored with the types MongoDB compares against rather than with text that silently
  matches nothing. Plain JSON values keep their own types. MongoDB's update operators are
  `$`-prefixed as well and are passed through untouched, nested values included, so a file
  can hold `{"$set": ..., "$push": ...}` for an update as readily as a document to insert.

  A file can hold two kinds of hole, written differently because they are filled from
  different places. `${name}` is a Robot Framework variable and is replaced from the ones
  the calling suite can see, using Robot Framework's own substitution, so a value a whole
  suite shares is written once. `{name}` is a template placeholder and is filled from the
  loading keyword's named arguments, so a value that differs on every call is given at the
  call:

  ```robotframework
  ${document}    Load Document    order.json    unique_id=order-1    customerId=${oid}
  ${document}    Load Document    order.json    &{placeholders}
  ```

  Placeholders are written quoted — `"customerId": "{customerId}"` — which keeps the
  template valid JSON, so editors, `jq` and formatters still read it. A string that is
  exactly one placeholder is replaced whole, its quotes included, by the value's own
  Extended JSON form, so an ObjectId, a datetime or a number arrives as itself with no
  `$oid` or `$date` wrapper needed; a placeholder inside a longer string, as in
  `"REF-{unique_id}"`, is interpolated as text. Inside a string `{{` and `}}` are literal
  braces as in `str.format`, and JSON's own braces are never touched. Either kind of hole
  left unfilled fails the keyword, because the literal text is a perfectly insertable
  string that would seed a document looking almost right.

  Any field the file already fills can be overridden by its dotted path, list positions
  included, as in `lines.0.quantity=3`. This is the part a suite cannot do for itself:
  `&{dict}` expansion merges one level deep, so overriding a nested field otherwise means
  rebuilding every level above it. Overrides written literally are read like the file's own
  values, so a number stays a number. A path that does not exist in the document fails with
  what the document held at that point, because a path that misses is a typo far more often
  than it is a field meant to be added.

  Placeholders and overrides are given the same way and the file decides which an argument
  is: a name it declares as a placeholder fills that placeholder, and anything else is a
  path. So a value that always varies becomes a hole in the template, a value that varies
  occasionally overrides what the file already says, and a bare name that is neither fails
  naming both.

## [1.1.0] - 2026-08-13

### Changed

- Robot Framework 5.0 and later are supported, and Python 3.10 and later, where before the
  constraints allowed only Robot Framework 7.3+ on Python 3.12+. The library needed no
  change for this: everything it imports from `robot` other than `Secret` predates 5.0,
  `Secret` was already imported conditionally, and the keyword annotations are ones 5.0
  converts. The pins were the only thing keeping older versions out.

  On 5.0 through 6.0 the assertion engine has to be 2.x, because its 3.x line requires
  Robot Framework 6.1.1. `verify_assertion` and `AssertionOperator` are identical across
  every line, so the assertion keywords behave the same either way. The dependency now
  allows `>=2.0,<6` and pip resolves the pairing.

  The upper end of that range matters as much as the lower: the previous `^3.0.3` excluded
  the assertion engine's current 4.x and 5.x lines, which work, and which other Robot
  Framework libraries depend on — installing this library alongside Browser would have
  been an unsatisfiable conflict.

  Robot Framework 4 and older remain unsupported: the assertion engine will not install
  below 5, and 4 does not convert built-in generic annotations such as `list[str]`.

  The only behavioural difference below 7.4 is that `db_password` and `db_conn_string`
  take a plain string, since `Secret` does not exist there. See "Older Robot Framework
  Versions" in README.md.

### Fixed

- The unit test file covering the keywords ran no tests at all on Robot Framework 7.3 and
  older. A module-level `pytest.importorskip` for the `Secret` type raised at import, so
  the whole file — 126 tests, of which 8 concern `Secret` — was skipped and reported as a
  single skip. The `Secret` tests now skip individually.

### Added

- `db_password` and `db_conn_string` accept a Robot Framework `Secret`, so the value is
  written to `log.html` and `output.xml` as `<secret>` rather than as itself. A secret
  can only be built from an environment variable, which is what makes it stronger than
  passing an ordinary variable: there is no way to write the value into the suite by
  accident. A connection string embeds its password, so giving that as a `Secret` hides
  the whole string.

  This needs Robot Framework 7.4, which introduced the type. On every older supported
  version there is no `Secret` to accept and no way for a suite to produce one, so the
  arguments behave exactly as before.

  Passing a `Secret` previously failed with `got value '<secret>' (Secret) that cannot be
  converted to string or None` — a clear error rather than a silent one, since Robot
  Framework refused the conversion instead of sending the literal text `<secret>` as the
  password.

### Documentation

- The AWS documentation never said how to enable AWS authentication. Doing so requires
  `authMechanism=MONGODB-AWS` together with `authSource=$external`, and neither appeared in
  README.md or in the class docstring, so the documented example — a connection string with
  nothing AWS-specific in it — quietly authenticated with SCRAM instead. Both are now
  documented, including that `auth_mechanism` and `auth_source` already reach them as
  keyword arguments, so no connection string is needed for IAM.

  The one section is now two, because Amazon DocumentDB and AWS IAM authentication are
  independent choices rather than one path. DocumentDB's own requirements are documented
  for the first time: TLS against Amazon's CA bundle, and `retryWrites=false`, which is
  required and without which every write fails. `tlsCAFile` has no keyword argument, so
  that is the one case where the connection string is the only route.

- The docstring claimed the library reads `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and
  `AWS_SESSION_TOKEN`. It reads none of them: there is no AWS-specific code in the library,
  `pymongo-auth-aws` resolves credentials, and an EC2, ECS, EKS or Lambda role is used with
  no credentials given at all. It also told the reader to install `pymongo[aws]`, which
  installs pymongo's extra and leaves this package's alone; the extra it meant is
  `robotframework-mongodb[aws]`. The MongoDB URL both files linked to now returns 404.

- `coerce_object_ids` is the library's only import-time argument but had no section of its
  own. A new "Importing" section covers it and the `GLOBAL` scope, including the
  consequence that two suites importing with different values get separate instances, and
  therefore separate connection pools rather than shared connections.

- README.md now opens with a runnable example before the `Secret` discussion rather than
  after it, and gains the multi-connection `alias` example the feature list promised but
  never showed, badges and a table of contents. The contributor-facing CI detail is
  compressed.

## [1.0.0] - 2026-08-13

The first release the version number claims is stable. It collects the work previously
staged as 0.3.0, which was never published, and completes the keyword surface: the
library now covers the parts of pymongo a test suite actually reaches for, rather than
documents alone.

The fixes in this release change behaviour that previously failed silently, so suites
that appeared to pass may start reporting real failures. That is the point of the
release: read "Fixed" before upgrading.

Nothing that worked before has been removed or renamed, and every new argument defaults
to the previous behaviour, so upgrading from 0.2.2 needs no changes to a suite beyond
those the fixes force.

### Fixed

- `Switch Database` had no effect. It set an attribute that no other keyword read, so
  every later keyword kept using the previous connection — writing to the wrong
  database, or failing with `KeyError: 'default'`.
- `Delete Document` and `Delete Many` coerced every query value to a string. Robot
  Framework converts free named arguments using their annotation, and these were
  annotated `str`, so `Delete Many  coll  count=${5}` searched for `"5"`, deleted
  nothing and reported success.
- A document could not be found by its id in string form. `Insert Document` returns an
  `ObjectId`; once that value passed through a Robot variable, a CSV or a JSON fixture
  it became text and no longer matched. A string `_id` in a query is now converted
  automatically, including inside `$in` and comparison operators. This rewrites part of
  your query, so it is documented in full under `Object Ids` in the library
  documentation and can be turned off with `coerce_object_ids=${False}` at import.
  Only `_id` is affected, only in queries, and only when the value is a valid ObjectId.
- `Check Query Result` and `Check Document Count` could loop forever. The retry
  deadline was tracked by adding `retry_pause` to a counter, so `retry_pause=0 seconds`
  never advanced it and the timeout was never reached. The deadline now uses a real
  clock, which also stops a slow query from overrunning `retry_timeout`.
- Closing the connection pool raised `TypeError`. `Database` has no `close()`, and
  pymongo's attribute lookup returned a `Collection` named "close" instead. Clients are
  now closed through `database.client`.
- `Connect To Database` and `Connect To Database Using Connection String` reported
  success against an unreachable server, because pymongo connects lazily. Both now
  verify the connection before passing, so the failure is reported by the keyword that
  caused it.
- `Find Document`, `Count Documents`, `Update Document With Operators` and
  `Delete Documents With Query` raised a bare `KeyError: 'myalias'` for an unknown
  alias instead of the actionable message the other keywords produced.
- `Update Document`, `Update Document With Operators` and `Execute Query` returned
  plain dictionaries, so `${doc.field}` worked after a find and broke after an update.
  Every document-returning keyword now returns a dot-accessible document.
- `Insert Document` was annotated as returning `str` but returns an `ObjectId`.

### Added

- `srv` and `tls` arguments on `Connect To Database`, so hosted clusters such as
  MongoDB Atlas can be reached. A cluster name is a DNS seed list with no address
  record of its own, which no combination of the previous arguments could resolve.
- `auth_source` argument on `Connect To Database`, required whenever the user was not
  created in the database being connected to.
- `server_selection_timeout` argument on both connect keywords, so an unreachable
  server fails faster than pymongo's 30 second default.
- `Find Documents` and `Find Documents With Query`, with `projection`, `sort`, `limit`
  and `skip`. Previously there was no way to retrieve more than one document other than
  by writing an aggregation pipeline.
- `Find Document With Query` and `Count Documents With Query`, so reads can use
  operators such as `$gte`, `$in` and `$regex`. Only deletes could do this before.
- `Insert Documents`, `Update Documents` and `Update Documents With Operators` for
  bulk writes.
- `Create Index`, `List Indexes` and `Drop Index`.
- `Switch Connection`, which is named for what it does, and `Get Active Alias` to read
  back the current selection.
- `Disconnect From All Databases` and `List Database Connections`. A `GLOBAL` scope
  library previously had no way to release its connections at the end of a run.
- `Convert To Object Id`, for building a query document or pipeline stage by hand, and
  the supported route for querying by id when `coerce_object_ids` is off.
- `coerce_object_ids` import argument, for collections whose `_id` values are genuinely
  strings that happen to be 24 hexadecimal characters, such as a truncated hash. With
  it off, queries are passed through exactly as written.
- `Get Distinct Values`, returning each value a field takes across the matching
  documents. Asking which statuses a collection contains previously meant writing an
  aggregation pipeline.
- `Replace Document`, which swaps a whole document rather than merging fields into it.
  `Update Document` can only add or overwrite, so until now there was no way to make a
  field disappear.
- `upsert` argument on `Update Document`, `Update Document With Operators`,
  `Update Documents` and `Update Documents With Operators`. "Ensure this document exists
  with these values" was previously impossible to express, so fixture setup could not be
  written to run twice. Note that an upserted document is inserted rather than changed,
  so the two bulk keywords still report 0 and log the new id.
- `Delete Document And Return It`, which deletes and reads in one operation. Doing it as
  a find followed by a delete leaves a window in which the document can change, and
  cannot safely drain a queue collection.
- `Drop Collection`, `Create Collection` and `List Collections`.
  `Delete All Documents From Collection` empties a collection but leaves its indexes and
  options behind, so a unique index created by one test still rejected the next one's
  fixtures. `Create Collection` takes the options an implicit creation cannot supply:
  `capped`, `validator`, `timeseries`.
- `List Databases`, `Drop Database` and `Get Server Info`, the last of these for skipping
  a test the server is too old to support.
- `Run Database Command`, which reaches every command the library does not wrap:
  `collStats`, `dbStats`, `explain`, `listCollections` and the administrative commands.
- `Get Index Information` and `Drop All Indexes`, and `sparse`, `expire_after_seconds`
  and `partial_filter_expression` arguments on `Create Index`.
- `Check Distinct Values`, `Check Collection Exists`, `Check Index Exists`,
  `Document Should Exist` and `Document Should Not Exist`. All retry like the existing
  assertion keywords, which is the part a suite gets wrong when it hand-rolls the wait.
- `limit` and `skip` arguments on `Count Documents` and `Count Documents With Query`,
  `ordered` on `Insert Documents`, `allow_disk_use` on `Execute Query`, and
  `Get Estimated Document Count`.
- `replica_set`, `direct_connection`, `read_preference` and `auth_mechanism` arguments on
  `Connect To Database`. These were previously reachable only by writing a connection
  string, which meant a suite could not use a host and credentials and still read from a
  secondary. `auth_mechanism` is what the documented AWS path needs.

### Changed

- Connecting several aliases to the same server with the same credentials now reuses
  one client instead of opening a connection pool per alias. A client is closed only
  once no alias still uses it.
- `Execute Query` raises `TypeError` rather than a bare `Exception` for a pipeline that
  is not a list.
- Documentation: the README's two usage examples passed positional arguments that bound
  to the wrong parameters and could never have worked. The library documentation
  described four assertion formatters that were never wired up, and referenced a
  `Get Document Field` keyword that has never existed.
- `CONTRIBUTING.md` documented `robotcode run atest`, but `robotcode` was not a
  dependency of the project. The documented command is now `poetry run robot atest`.

### Deprecated

- `Switch Database`. It switches the active connection, not the database within a
  connection. Use `Switch Connection`; the old name still works and warns.

### Removed

- `ConnectionManager.get_current_connection` and `ConnectionManager.current_alias`,
  which had no callers and no keyword exposing them.
- The unused `db_name` parameter of `ConnectionManager.add_to_connection_pool`.
- The duplicate `atest/resources/local.resource.copy` template, and the
  `extend-python-path` setting that pointed at the directory holding it.
- The `[tool.isort]` configuration, for a tool that was not a dependency, and the
  unused `robotstatuschecker` dependency.

### Internal

- Unit tests run against an in-memory MongoDB (`mongomock`) instead of `MagicMock`.
  Three of the bugs above were invisible to the previous suite because a mock answers
  any call and accepts any argument type; the acceptance suites passed 14/14 against
  the broken code.
- New acceptance suite `atest/multi_connection_tests.robot` covering switching
  connections, non-string query values, the retry timeout and releasing the pool.
- New acceptance suite `atest/collection_and_database_tests.robot` for the keywords that
  act on a collection, a database or the server. These need a real server: collection
  options, index metadata and database commands are all things an in-memory stand-in
  either refuses or invents. It caught `Run Database Command` sending a command document
  as a command name, which every mock-based test had accepted.
- New acceptance suite `atest/query_operator_tests.robot`. The keywords whose whole
  purpose is MongoDB query and update operators — the `*With Query` family, the bulk
  updates, sorting, and ObjectId coercion inside `$in` — had no acceptance coverage at
  all, so `$gte`, `$in`, `$regex`, `$inc` and `$push` were only ever answered by
  mongomock's reimplementation of the query language rather than by MongoDB.
- New acceptance suite `atest/connection_option_tests.robot` covering `auth_source`,
  `auth_mechanism`, `read_preference`, `direct_connection` and `server_selection_timeout`
  against a real server. Each becomes a pymongo option under a different name from the
  keyword argument, and only a server accepting the connection proves the mapping.
- CI's acceptance job now runs against `mongodb/mongodb-atlas-local` rather than plain
  `mongo:8`. It is a single-node replica set, which is what a hosted cluster is, so read
  preferences and `replica_set` are exercised against a topology that has them instead of
  a standalone that ignores them. It needs `--hostname localhost`: a replica set
  advertises its members by hostname, and left as the container id that name does not
  resolve from the runner, so every connection that is not `directConnection` fails
  server selection.
- A second CI job runs the connection suite against a real hosted cluster, on pushes to
  `main`, nightly and on demand, covering `srv` and `tls` — a DNS seed list and a TLS
  handshake being the two things no container offers. It works in a database named after
  the run and drops it afterwards, and admits itself to the Atlas access list for the
  length of the job rather than leaving the cluster open. It skips cleanly where the
  secrets are absent, so a fork is unaffected.
- `${DB_REPLICA_SET}` and `${DB_AUTH_MECHANISM}` in `local.resource`. Both are properties
  of the server and of how its user was created rather than of the library, and the tests
  that need them skip when they are not set. A user holding only SCRAM-SHA-1 credentials
  rejects `SCRAM-SHA-256` with `bad auth`, which is what a hosted cluster's user often is.
- Acceptance coverage of `MongoDBLibrary/keywords.py` rose from 80% to 97% against the
  container, and 99% counting the hosted-cluster job. The one remaining statement is a
  guard in `Execute Query` that Robot Framework's own argument conversion reaches first,
  leaving it reachable only from Python, where the unit tests cover it.
- CI runs `ruff`, `robocop`, `mypy` and the unit tests on Python 3.12, 3.13 and 3.14,
  plus the acceptance tests against a MongoDB service container.
- A tag-triggered release workflow publishes to PyPI and refuses to run if the tag does
  not match the project version.

## [0.2.2] - 2026-01-06

### Changed

- Allow Python 3.14.

## [0.2.1] - 2026-01-06

### Added

- `robotframework-robocop` as a development dependency.

## [0.2.0] - 2025-12-22

### Added

- `Update Document With Operators` and `Delete Documents With Query`.

### Changed

- Expanded README and package metadata.

## [0.1.0] - 2025-07-25

### Added

- Initial release: connection management and keywords for connecting, inserting,
  finding, updating, deleting, counting and aggregating.
