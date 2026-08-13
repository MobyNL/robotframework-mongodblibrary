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

### Running Acceptance Tests

Acceptance tests are located in the `atest` directory. To run them, use the following command:
```bash
poetry run robot atest
```

Ensure that the `local.resource` file is properly configured before running the tests.

### Linting And Type Checking

```bash
poetry run ruff check .         # Python
poetry run robocop check atest  # Robot Framework
poetry run mypy                 # types
```

### Regenerating The Keyword Documentation

`MongoDBLibraryKeywords.html` is committed, so regenerate it whenever a keyword or its
documentation changes:

```bash
poetry run libdoc MongoDBLibrary MongoDBLibraryKeywords.html
```

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
