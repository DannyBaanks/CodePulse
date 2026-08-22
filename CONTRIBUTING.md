# Contributing to CodePulse

Thank you for your interest in contributing to CodePulse!

## Development Setup

```bash
# Clone the repo
git clone https://github.com/DannyBaanks/CodePulse
cd CodePulse

# Install in development mode
pip install -e ".[dev]"
```

## Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test class
python -m pytest tests/test_codepulse.py::TestScorer -v

# With coverage
python -m pytest tests/ --cov=codepulse --cov-report=html
```

## Linting

```bash
# Run ruff
ruff check codepulse/ tests/

# Auto-fix
ruff check codepulse/ tests/ --fix
```

## Type Checking

```bash
mypy codepulse/ --ignore-missing-imports
```

## Code Style

- Follow existing code patterns
- Use type hints
- Keep functions small and focused
- Write tests for new features
- Update docstrings for public APIs

## Pull Request Process

1. Fork the repo
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a PR

## Reporting Issues

Please use the GitHub issue tracker for bug reports and feature requests.

## Security

If you find a security vulnerability, please report it via email to the maintainer instead of opening a public issue.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.