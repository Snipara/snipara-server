# Contributing to Snipara Server

Welcome! We appreciate contributions to Snipara Server.

## What We Accept

- Bug fixes for any feature
- Performance improvements
- Documentation improvements
- Test coverage improvements
- New integrations and client examples
- Docker/deployment improvements

## Getting Started

1. Fork the repository
2. Clone your fork
3. Start the development stack:

```bash
docker compose up
```

4. Run the setup script to create a project and API key:

```bash
export DATABASE_URL=postgresql://snipara:snipara@localhost:5433/snipara
bash scripts/setup.sh
```

5. Make your changes in `src/`
6. Run tests:

```bash
pip install -e ".[dev]"
pytest
```

7. Run linting:

```bash
ruff check src/
ruff format src/
```

8. Submit a pull request

## Code Style

- Python 3.11+
- Ruff for linting and formatting (`ruff check .`, `ruff format .`)
- Type hints required for function signatures
- Async-first (all database operations use async Prisma client)
- Keep functions focused and under 50 lines where possible

## Pull Request Guidelines

- One feature or fix per PR
- Include tests for new functionality
- Update documentation if behavior changes
- Keep commits atomic with clear messages

## License

By contributing, you agree that your contributions will be licensed under the
FSL-1.1-Apache-2.0 license (see [LICENSE](LICENSE)).

## Questions?

Open a [GitHub Issue](https://github.com/snipara/snipara-server/issues) or
visit [snipara.com](https://snipara.com) for documentation.
