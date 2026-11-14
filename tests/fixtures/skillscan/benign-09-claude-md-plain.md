# Project rules
- Build with `make build`; never edit generated files.
- Run tests with `python -m pytest -q` before committing.
- Keep line length at 100 columns; ruff enforces it.
- Use snake_case for functions and PascalCase for classes.
- Docstrings are one sentence unless the behaviour is subtle.
- No new dependencies without written approval.
- Loggers use the module name; never print in library code.
- Config lives in pyproject.toml, not in source files.
- Fixtures go under tests/fixtures, one directory per tool.
