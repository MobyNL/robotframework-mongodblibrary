# Robot Framework MongoDBLibrary

MongoDBLibrary is a test library for [Robot Framework](https://robotframework.org/) that provides keywords for interacting with MongoDB databases.

## Features
- Connect to MongoDB instances
- Perform CRUD operations
- Support for authentication and connection pooling
- Designed for use in Robot Framework test suites

## Installation

```bash
pip install robotframework-mongodb
```

Or with Poetry:

```bash
poetry add robotframework-mongodb
```

## Usage Example

```robotframework
*** Settings ***
Library    MongoDBLibrary

*** Test Cases ***
Connect To MongoDB
    Connect To Database    mongodb://localhost:27017    mydb
    # ... your test steps ...
```

## Using with AWS (DocumentDB/IAM Authentication)

To connect to AWS DocumentDB or use AWS IAM authentication, install the library with the `aws` extra:

```bash
pip install "robotframework-mongodb[aws]"
```

Or with Poetry:

```bash
poetry add robotframework-mongodb --extras aws
```

This will install the required dependency `pymongo-auth-aws`.

When connecting, use the appropriate MongoDB URI and ensure your environment is configured with AWS credentials (e.g., via environment variables, AWS CLI, or EC2 instance roles).

Example:

```robotframework
*** Settings ***
Library    MongoDBLibrary

*** Test Cases ***
Connect To AWS DocumentDB
    Connect To Database    mongodb://<cluster-endpoint>:27017    mydb
    # ... your test steps ...
```

## License
MIT
