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

1. **Run one in Docker** (quickest):
   ```bash
   docker run -d --name rf-mongodb-atest -p 27017:27017 \
     -e MONGO_INITDB_ROOT_USERNAME=root -e MONGO_INITDB_ROOT_PASSWORD=testpass mongo:8
   ```
   Then set `${DB_HOST}` to `localhost`, `${DB_PORT}` to `27017`, `${DB_USER}` to
   `root`, `${DB_PASSWORD}` to `testpass`, `${DB_SRV}` to `${False}`, and
   `${DB_CONNECT_STRING}` to `mongodb://root:testpass@localhost:27017/?authSource=admin`.

2. **Set Up a Local MongoDB Instance**:
   - Install MongoDB on your local machine and start the server.
   - Update the `local.resource` file with your MongoDB connection details.

3. **Use Your Own Hosted Cluster**:
   - Add your IP to the provider's access list. Atlas rejects a non-allowlisted IP
     during the TLS handshake, which surfaces as `TLSV1_ALERT_INTERNAL_ERROR` rather
     than as an access error.
   - Update the `local.resource` file, including `${DB_SRV}`.

The acceptance tests empty the collections they use, so point them at a database you
do not mind losing data from.

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
