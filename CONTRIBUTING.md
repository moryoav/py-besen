# Contributing to the Besen Python library

Thanks for your interest in improving `besen`, the async Python client for Besen
EV chargers over Bluetooth Low Energy.

I maintain the library in this repository. The Home Assistant custom integration
that uses it lives in [moryoav/besen](https://github.com/moryoav/besen), and the
built-in integration lives in Home Assistant Core. Please report problems with
Home Assistant entities, setup, or HACS there.

## Development and releases

I use `main` for ongoing development. `vX.Y.Z` tags publish the package to PyPI
and create a GitHub release. The tag must match the version in `pyproject.toml`
and `src/besen/__init__.py`, and the release notes come from the matching
`CHANGELOG.md` section.

Versions up to 0.4.8 were released from
[moryoav/besen](https://github.com/moryoav/besen) with `library-vX.Y.Z` tags, or
with shared `vX.Y.Z` tags before 0.4.4. This repository carries over that history
with the tags renamed to `vX.Y.Z`.

Contributions are welcome, including bug reports, compatibility reports, protocol
fixes, BLE reliability fixes, security hardening, and focused feature ideas.

## Before You Start

Please open an issue before starting large or risky changes. This helps avoid
duplicated work and gives me a chance to discuss the approach first.

Small fixes, documentation updates, and clearly scoped bug fixes can usually go
straight to a pull request.

## Reporting Bugs

When reporting a bug, please include:

- The `besen` version and Python version you are using.
- Your operating system and Bluetooth adapter or proxy, if known.
- Your charger model or advertised BLE name, if known.
- Clear steps to reproduce the issue, ideally as a short script.
- Relevant debug logs from the `besen` logger with sensitive information removed.
- What you expected to happen.
- What actually happened.

Please remove charger PINs, private BLE addresses, private logs, Wi-Fi details,
and personal paths before sharing logs or screenshots.

## Development Setup

Clone the repository and install the development dependencies:

```bash
git clone https://github.com/moryoav/py-besen.git
cd py-besen
python -m pip install -e ".[dev]"
```

The repository layout is:

```text
src/besen/          Python Bluetooth library
tests/              Library tests
.github/workflows/  CI and release workflows
```

## Testing

Before opening a pull request, run the same checks as CI:

```bash
ruff check .
mypy
pytest --cov
python -m build
twine check dist/*
```

CI runs these checks on Python 3.12, 3.13, and 3.14. Coverage must stay at or
above 95%.

Changes to BLE handling, protocol parsing, or charging commands should include
regression tests. If you tested with real hardware, describe the charger model,
phase count, and what you exercised in the pull request.

## Pull Request Guidelines

Please keep pull requests focused. A good pull request should:

- Explain what changed and why.
- Mention any related issue.
- Keep unrelated formatting or refactoring out of the change.
- Update `README.md` when the public API or behavior changes.
- Add a `CHANGELOG.md` entry under `Unreleased`.
- Avoid committing secrets, charger PINs, private BLE addresses, private logs, or
  Wi-Fi details.

## Releases

1. Move the `Unreleased` changelog entries to a new `## [X.Y.Z] - YYYY-MM-DD`
   section.
2. Update the version in `pyproject.toml` and `src/besen/__init__.py`.
3. Commit the release and push an annotated `vX.Y.Z` tag on `main`.

The release workflow validates the version, publishes to PyPI with trusted
publishing, and then creates the GitHub release. Bump the Home Assistant
integrations only after the new version is available on PyPI.

## Security Notes

Please be especially careful with changes involving:

- Charger PIN handling and login.
- BLE command construction, parsing, notification handling, and reconnects.
- Logs that may include BLE addresses or charger identifiers.
- Charging controls such as start, stop, and charge current.

If you believe you found a security vulnerability, please do not open a public
issue with exploit details. Follow `SECURITY.md` instead.

## Safety Notes

This library is not a safety controller. It must not be relied on as the only
protection for electrical limits, overheating, grid constraints, vehicle safety,
or local code requirements.

Do not use issues or pull requests to request advice about unsafe wiring,
breaker sizing, bypassing charger protections, or electrical work that should be
handled by a qualified professional.

## Code of Conduct

Please be respectful, constructive, and patient. See `CODE_OF_CONDUCT.md`.
