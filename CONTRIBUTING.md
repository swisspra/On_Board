# Contributing

## Automated tests

```bash
uv sync --locked --extra test
uv run python -m pytest -W error
```

All automated offline tests live in `tests/`. The default pytest command and CI
collect the same suite; add new regression tests there rather than at the
repository root. Test source is intentionally tracked in Git.

## Optional scratch-board checks

These developer programs are not collected by pytest:

```bash
uv run python tools/live/check_a2a.py
uv run python tools/live/check_a2a_multiprocess.py
```

They create their own temporary projects. Do not use an existing project board
as test data.

## Generated files

Pytest and Ruff caches go under `.work/`. Bytecode, legacy cache directories,
coverage reports, build output, virtual environments and project memory are
ignored. Keep those local; do not ignore `tests/` or new test source files.

Maintainer: @swisspra
