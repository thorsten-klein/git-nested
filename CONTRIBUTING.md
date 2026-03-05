# Contributing to git-nested

Thank you for your interest in contributing to git-nested! This document provides guidelines and instructions for contributing to the project.

## Code of Conduct

Please be respectful and constructive in all interactions with the community. We aim to maintain a welcoming and inclusive environment for all contributors.

## Getting Started

### Setting Up Your Development Environment

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/git-nested
   cd git-nested
   ```

3. Install development dependencies:
   ```bash
   # Using uv (recommended)
   uv sync --dev

   # Or using pip
   pip install -e ".[dev]"
   ```

4. Verify your setup:
   ```bash
   uv run poe all
   ```

## Development Workflow

### Making Changes

1. Create a feature branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes, following the coding standards below

3. Add or update tests to cover your changes

4. Run all checks before committing:
   ```bash
   uv run poe all
   ```

### Running Tests Individually

```bash
# Run all tests
uv run poe test

# Run specific test file
uv run poe test test/test_clone.py

# Run with verbose output
uv run poe test -vv

# You can also run pytest directly
uv run pytest
```

### Code Quality

We use [Ruff](https://github.com/astral-sh/ruff) for both linting and formatting:

```bash
# Check code quality
uv run poe lint

# Auto-format code
uv run poe format
```

Make sure all checks pass before submitting your PR.

## Coding Standards

- Follow [PEP 8](https://pep8.org/) style guidelines (enforced by Ruff)
- Write clear, descriptive commit messages
- Add docstrings to all public functions and classes
- Keep functions focused and single-purpose
- Use type hints where appropriate
- Write self-documenting code with meaningful variable names

## Testing Guidelines

- Write tests for all new features and bug fixes
- Ensure existing tests still pass
- Aim for high test coverage on modified code
- Use descriptive test names that explain what is being tested
- Group related tests in the same test file

## Commit Message Guidelines

Write clear and descriptive commit messages:

- Use the imperative mood ("Add feature" not "Added feature")
- Keep the first line under 72 characters
- Reference issues and PRs where relevant
- Provide additional context in the body if needed

Example:
```
Add support for shallow clones with --depth option

Implements shallow clone functionality to reduce clone time
and disk space for large repositories.

Fixes #123
```

## Submitting a Pull Request

1. Push your changes to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

2. Open a Pull Request on GitHub against the `main` branch

3. Fill out the PR template with:
   - Clear description of the changes
   - Motivation and context
   - How the changes have been tested
   - Any breaking changes or migration notes
   - Related issue numbers

4. Wait for review and address any feedback

5. Once approved, a maintainer will merge your PR

## Pull Request Review Process

- All PRs require at least one review before merging
- CI checks must pass (tests, linting, formatting)
- Reviewers may request changes or clarifications
- Be responsive to feedback and questions
- Maintainers will merge once all requirements are met

## Reporting Bugs

If you find a bug, please open an issue on GitHub with:

- Clear, descriptive title
- Steps to reproduce the issue
- Expected behavior vs actual behavior
- Your environment (OS, Python version, git version)
- Any relevant error messages or logs
- Minimal reproduction example if possible

## Requesting Features

Feature requests are welcome! Please:

- Check existing issues to avoid duplicates
- Clearly describe the feature and its use case
- Explain why it would be useful to other users
- Consider submitting a PR if you can implement it

## Documentation

- Update documentation for any user-facing changes
- Add docstrings to new functions and classes
- Update README.md if adding new commands or features
- Include code examples where helpful

## Questions?

- Check existing documentation and issues first
- Open a GitHub issue for questions about contributing
- Be patient and respectful when asking for help

## License

By contributing to git-nested, you agree that your contributions will be licensed under the MIT License.

## Recognition

Contributors will be recognized in the project. Significant contributors may be added to the AUTHORS or CONTRIBUTORS file.

Thank you for contributing to git-nested!
