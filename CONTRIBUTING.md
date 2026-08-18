# How to Contribute

Thank you for considering contributing to the `robotframework-mongodblibrary` project! Contributions are welcome and greatly appreciated. Please follow the guidelines below to get started.

## Getting Started

1. **Fork the Repository**: Create a fork of this repository to your GitHub account.
2. **Clone the Repository**: Clone your forked repository to your local machine.
   ```bash
   git clone https://github.com/<your-username>/robotframework-mongodblibrary.git
   ```
3. **Set Up the Environment**: Install dependencies using Poetry.
   ```bash
   poetry install
   ```

## Setting Up `local.resource`

Before running the acceptance tests, you need to create your own copy of the
`local.resource` file. Use `atest/local.resource.copy` as an example:

1. Copy `atest/local.resource.copy` to `atest/local.resource`.
2. Update the variables with your MongoDB connection details.

The name matters: `.gitignore` ignores exactly `local.resource`, so any other name
(`local.resource copy.copy`, `local.resource.mine`) is **not** ignored and your
credentials can be committed by accident.

For a hosted cluster such as MongoDB Atlas, set `${DB_SRV}` to `${True}` and put the
cluster name in `${DB_HOST}` — a cluster name is a DNS seed list and has no address
record of its own, so a plain host and port cannot reach it. Also make sure the
`<db_password>` placeholder in the connection string you copied from the provider has
been replaced with the real password.

## Testing

Unit tests need nothing installed: they run against an in-memory MongoDB provided by
`mongomock`. The acceptance tests need a real MongoDB instance. You can either:

1. **Run one in Docker** (quickest, and what CI uses):
   ```bash
   docker run -d --name rf-mongodb-atest --hostname localhost -p 27017:27017 \
     -e MONGODB_INITDB_ROOT_USERNAME=root -e MONGODB_INITDB_ROOT_PASSWORD=testpass \
     mongodb/mongodb-atlas-local:latest
   ```
   Then set `${DB_HOST}` to `localhost`, `${DB_PORT}` to `27017`, `${DB_USER}` to
   `root`, `${DB_PASSWORD}` to `testpass`, `${DB_SRV}` to `${False}`,
   `${DB_REPLICA_SET}` to `rs-localdev`, and `${DB_CONNECT_STRING}` to
   `mongodb://root:testpass@localhost:27017/?authSource=admin`.

   This image is a single-node replica set, which is what a hosted cluster is, so read
   preferences and the replica set name are exercised against a topology that has them.
   Plain `mongo:8` also works — leave `${DB_REPLICA_SET}` empty and the one test that
   needs a set skips itself.

   `--hostname localhost` is not optional. A replica set advertises its members by
   hostname, and left as the container id that name does not resolve from your machine,
   so every connection that is not `directConnection` fails server selection.

2. **Set Up a Local MongoDB Instance**:
   - Install MongoDB on your local machine and start the server.
   - Update the `local.resource` file with your MongoDB connection details.

3. **Use Your Own Hosted Cluster**:
   - Add your IP to the provider's access list. Atlas rejects a non-allowlisted IP
     during the TLS handshake, which surfaces as `TLSV1_ALERT_INTERNAL_ERROR` rather
     than as an access error.
   - Update the `local.resource` file, including `${DB_SRV}` and `${DB_AUTH_MECHANISM}`.

The acceptance tests empty the collections they use, so point them at a database you
do not mind losing data from.

### What Needs A Hosted Cluster

Almost everything runs against the container. Two connect arguments cannot: `srv`
resolves a DNS seed list, and `tls` is the handshake a hosted cluster requires and a
local one does not offer. The tests for those skip themselves unless `${DB_SRV}` is true.

`${DB_AUTH_MECHANISM}` is worth setting deliberately. Which mechanism works is a property
of how the *user* was created, not of the server version — a user holding only
SCRAM-SHA-1 credentials rejects `SCRAM-SHA-256` with `bad auth`, and Atlas users created
some time ago are often exactly that. The container's user is SCRAM-SHA-256. Leave the
variable empty and the test that pins a mechanism skips.

### Supporting Older Robot Framework Versions

The library supports Robot Framework 5.0 through 7.x, so a change has to keep working on
all of them. Two things follow from that when writing code here:

- **Anything from `robot` that arrived after 5.0 must be imported conditionally**, the way
  `Secret` is in `MongoDBLibrary/keywords.py` — imported in a `try`, with the keyword's
  behaviour on the older version staying what it was. A plain import of a newer API breaks
  the library at import time for everyone below that version.
- **Keyword annotations must be ones 5.0 converts.** Built-in generics (`list[str]`,
  `dict[str, Any]`), `Optional` and `Union` are all fine; a newer conversion feature is
  not, and libdoc in the version matrix is what catches it.

The `unit-test-robot-framework-range` job runs the unit tests and libdoc against 5.0.1,
6.1.1, 7.3.2 and 7.4.0. It installs with pip from explicit pins rather than
`poetry install`, because the lock file exists to pin one development environment and would
defeat the point.

`unit-test-robot-framework-latest` covers the opposite end: it upgrades past the upper
bounds in `pyproject.toml` to whatever is newest on PyPI, so an upstream release that
breaks the library is found nightly instead of by a user. It is `continue-on-error` and
skipped on pull requests, since it can go red for a reason unrelated to the change under
test. When it does go red, read its "Report the resolved versions" step first — it names
the version that broke — and fix the library or lower the upper bound.

Unit tests that need a newer Robot Framework should skip rather than fail — see
`needs_secret` in `utest/test_keywords.py`. Use `pytest.mark.skipif` on the tests, not a
module-level `pytest.importorskip`: that raises at import and silently skips the entire
file, which is how the Secret tests once took 126 unrelated tests out of the floor job.

The acceptance suites are exempt. They use `VAR` (7.0 syntax), and the robocop formatter
configured in `pyproject.toml` rewrites assignments into it, so they run only on the
newest version. They cover the driver against a real server, which does not vary by
Robot Framework version.

### Continuous Integration

CI runs the acceptance suite twice, against two different things:

- **`acceptance-test`** runs everything against the Atlas Local container, on every push
  and pull request. No credentials, no network beyond the runner.
- **`acceptance-test-atlas`** runs `connection_option_tests.robot` alone against a real
  hosted cluster, on pushes to `main`, nightly, and on demand. Only the connect keywords
  need a cluster, so running the whole suite there would spend runner minutes and write
  traffic to prove things the container already proved.

The hosted job skips itself unless these repository secrets exist:

| Secret | Purpose |
| --- | --- |
| `ATLAS_DB_HOST` | Cluster hostname, without the `mongodb+srv://` prefix |
| `ATLAS_DB_USER` | Database user |
| `ATLAS_DB_PASSWORD` | That user's password |
| `ATLAS_API_PUBLIC_KEY` | Atlas Admin API public key, for the access list |
| `ATLAS_API_PRIVATE_KEY` | Atlas Admin API private key |
| `ATLAS_PROJECT_ID` | Atlas project holding the cluster |

The job adds the runner's address to the access list, runs, and removes it again; the
entry also carries a `deleteAfterDate` an hour out, so a job that dies before its cleanup
step still leaves nothing behind.

Managing the access list needs an API key with the **Project Owner** role (the
[endpoint](https://www.mongodb.com/docs/api/doc/atlas-admin-api-v2/operation/operation-createprojectipaccesslist)
accepts Project Owner or Project Charts Admin). There is no narrower role that covers
only the access list, so this key can do anything to the project. Two ways to live with
that:

- Keep the key, and give it a project that holds nothing but this test cluster.
- Skip the key. Open the access list yourself and omit `ATLAS_API_PUBLIC_KEY`,
  `ATLAS_API_PRIVATE_KEY` and `ATLAS_PROJECT_ID`; the allowlist step then skips and the
  job connects directly. This trades a broad credential for a cluster reachable from any
  address that has the password, so it suits a throwaway cluster and nothing else.

The job also serialises itself with a `concurrency` group, because the access list
endpoint rejects concurrent writes.

Set `ATLAS_AUTH_MECHANISM` as a repository *variable* if the cluster's user is not
SCRAM-SHA-1.

Each run works in its own database named after the run id and drops it afterwards, so
concurrent runs and your own local testing never collide.

### Running Unit Tests

Unit tests are located in the `utest` directory. To run them, use the following command:
```bash
poetry run pytest utest
```

To check a change against the oldest supported Robot Framework, as CI does, install into a
throwaway virtual environment rather than the Poetry one — the lock file pins the newest
version:

```bash
python -m venv /tmp/rf-floor
/tmp/rf-floor/bin/pip install . pytest pytest-mock mongomock \
  "robotframework==5.0.1" "robotframework-assertion-engine==2.0.0"
/tmp/rf-floor/bin/python -m pytest utest
/tmp/rf-floor/bin/python -m robot.libdoc MongoDBLibrary /tmp/libdoc-check.html
```

Expect the `Secret` tests to skip there and every other test to run.

### Running Acceptance Tests

Acceptance tests are located in the `atest` directory. To run them, use the following command:
```bash
poetry run robot atest
```

These need Robot Framework 7.0 or later — they use `VAR`, and the formatter configured
here rewrites assignments into it. There is no need to run them against an older version;
see [Supporting Older Robot Framework Versions](#supporting-older-robot-framework-versions).

Ensure that the `local.resource` file is properly configured before running the tests.

### Linting And Type Checking

```bash
poetry run ruff check .         # Python
poetry run robocop check atest  # Robot Framework
poetry run mypy                 # types
```

### The Keyword Documentation

`MongoDBLibraryKeywords.html` is not committed. `.github/workflows/docs.yml` generates it
with libdoc and pushes it to the `gh-pages` branch, one directory per version:
`/<version>/` for a `v*` tag, `/dev` for the current main, and `/latest` plus the bare
`MongoDBLibraryKeywords.html` at the site root for the newest release. The bare path is
what the metadata of the already published releases points at, so it stays served.

Nothing needs regenerating by hand, and nothing can drift: a rendered libdoc page carries
its generation time, the absolute path of the machine that produced it and the Robot
Framework and Python versions used, so a committed copy could never be compared against a
freshly generated one anyway. Generating it locally to look at it is still useful, and the
result is gitignored:

```bash
poetry run libdoc MongoDBLibrary MongoDBLibraryKeywords.html
```

`tools/build_docs_index.py` renders the landing page listing the published versions, from
the `versions.json` the workflow keeps on the branch. It decides which release is the
newest, which is what keeps `/latest` from being pointed at an older version when an older
tag is published late, so it has unit tests in `utest/test_docs_index.py` — the workflow
runs once per release, where a mistake is only noticed after the fact.

The workflow writes `.nojekyll` onto the branch itself: the generated documentation
contains 175 `{{ ... }}` sequences in its JavaScript, which Jekyll would read as template
tags and strip, leaving a page that is quietly broken.

A tag released before this workflow existed cannot be dispatched directly, because
`workflow_dispatch` only runs a workflow that exists on the chosen ref. Run the workflow
from `main` with the `ref` input set to the tag — `v1.0.0`, say — and it checks that tag
out, takes `tools/` from `main`, and publishes it under its own version.

## Releasing

A `v*` tag is what publishes to PyPI, and `.github/workflows/release.yml` is the only
thing that uploads — there is no manual `poetry publish`. Two guards stand between the
tag and the upload:

- The workflow compares the tag against `poetry version --short` and fails before
  building if they disagree, so a tag pushed ahead of the version bump cannot ship.
- The `pypi` deployment environment requires a manual approval and admits only `v*`
  tags. The job waits on GitHub until the release is approved, which is the last point
  at which a wrong tag can be deleted instead of yanked — PyPI does not allow reusing a
  version number.

## Submitting Changes

1. **Create a Branch**: Create a new branch for your changes.
   ```bash
   git checkout -b feature/<your-feature-name>
   ```
2. **Make Changes**: Implement your changes and commit them.
   ```bash
   git commit -m "Add <description-of-change>"
   ```
3. **Push Changes**: Push your changes to your forked repository.
   ```bash
   git push origin feature/<your-feature-name>
   ```
4. **Create a Pull Request**: Open a pull request to the main repository.

## Questions

If you have any questions, feel free to open an issue or contact the project maintainer directly.

Happy coding!
