# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - Unreleased

The fixes in this release change behaviour that previously failed silently, so suites
that appeared to pass may start reporting real failures. That is the point of the
release: read "Fixed" before upgrading.

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
  automatically, including inside `$in` and comparison operators.
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
- `Convert To Object Id`, for building a query document or pipeline stage by hand.

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
