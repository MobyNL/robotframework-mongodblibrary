# Copilot Instructions

## General Guidelines

- **Focus on Python Development**: Prioritize writing clean, idiomatic Python code.
- **Unit Testing**: Always write unit tests for new features or changes. Use `pytest` as the testing framework.
- **Minimize Comments**: Write self-explanatory code that minimizes the need for comments. Use comments only when necessary to clarify complex logic.
- **Package Management**: Use `poetry` for dependency management and packaging. Ensure the `pyproject.toml` file is updated with any new dependencies.
- **Code Quality**: Adhere to `ruff` linting rules to maintain high-quality Python code.

## Unit Testing

- Write tests for all public methods and functions.
- Use `pytest` fixtures to set up reusable test data or mocks.
- Mock external dependencies using `pytest-mock` or `unittest.mock`.
- Ensure tests are isolated and do not depend on external systems or shared state.
- Aim for high test coverage without compromising test quality.

## Poetry Usage

- Add new dependencies using `poetry add <package>`.
- Use `poetry.lock` to ensure consistent dependency versions.
- Run `poetry install` to set up the development environment.
- Use `poetry run` to execute scripts or commands within the virtual environment.

## Ruff Configuration

- Follow the `ruff` configuration specified in the project (e.g., `.ruff.toml` or `pyproject.toml`).
- Fix linting issues reported by `ruff` before committing code.
- Use `ruff --fix` to automatically resolve simple issues.

## Commit Messages

- Write clear and concise commit messages.
- Use the imperative mood (e.g., "Add feature X" or "Fix bug Y").
- Reference related issues or pull requests when applicable.

## Collaboration

- Follow the repository's contribution guidelines.
- Review pull requests thoroughly before approval.
- Provide constructive feedback during code reviews.

## Additional Tools

- Use `black` for code formatting if specified in the project.
- Use `mypy` for type checking if type annotations are used.
- Use `pytest-cov` for measuring test coverage.

By following these instructions, Copilot can assist in maintaining a high standard of Python development and testing within this project.
