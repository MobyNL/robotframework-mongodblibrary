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

Before running tests, you need to create your own copy of the `local.resource` file. Use the `local.resource.copy` file as an example:

1. Duplicate the `local.resource.copy` file and rename it to `local.resource`.
2. Update the variables in `local.resource` with your MongoDB connection details.

## Configuring Python Path

To ensure the tests run correctly, you need to configure the Python path:

1. Use the `robotcode` extension for Robot Framework in your IDE.
2. Alternatively, add the `./atest/resources` directory to your Python path manually.
   ```bash
   export PYTHONPATH=./atest/resources:$PYTHONPATH
   ```

## Testing

To run tests, you need access to a MongoDB instance. You can either:

1. **Set Up a Local MongoDB Instance**:
   - Install MongoDB on your local machine.
   - Start the MongoDB server.
   - Update the `local.resource` file with your MongoDB connection details.

2. **Use the Preconfigured MongoDB Instance**:
   - Contact the project maintainer to get access to the preconfigured MongoDB instance.
   - Update the `local.resource` file with the provided connection details.

### Running Unit Tests

Unit tests are located in the `utest` directory. To run them, use the following command:
```bash
pytest utest
```

### Running Acceptance Tests

Acceptance tests are located in the `atest` directory. To run them, use the following command:
```bash
robotcode run atest
```

Ensure that the `local.resource` file is properly configured before running the tests.

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

## Code of Conduct

Please adhere to the [Code of Conduct](CODE_OF_CONDUCT.md) when contributing.

## Questions

If you have any questions, feel free to open an issue or contact the project maintainer directly.

Happy coding!
