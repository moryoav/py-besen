## Summary

Describe what this pull request changes and why.

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Device compatibility improvement
- [ ] Documentation update
- [ ] Security hardening
- [ ] Maintenance or refactoring
- [ ] Other

## Affected Area

- [ ] BLE connection handling
- [ ] Charger login or PIN
- [ ] Protocol parsing or state models
- [ ] Charger commands
- [ ] CI, packaging, or release process
- [ ] Documentation

## Testing

Describe the testing you performed.

- [ ] Ruff passes.
- [ ] Mypy passes.
- [ ] Tests pass with at least 95% coverage.
- [ ] The package builds and passes `twine check`.
- [ ] Tested with a physical charger (describe the model and what was exercised).
- [ ] Documentation-only change; no runtime testing needed.

## Security and Safety

- [ ] This change does not add charger PINs, private BLE addresses, private logs,
      or Wi-Fi details.
- [ ] I considered whether this affects charger PIN handling, logging, BLE
      command handling, or charging controls.
- [ ] I updated `SECURITY.md` or documentation if this changes
      security-sensitive behavior.
- [ ] I considered the safety impact of changes that affect charging controls.

## Documentation

- [ ] I updated `README.md` for public API or behavior changes.
- [ ] I added a `CHANGELOG.md` entry under `Unreleased`.
- [ ] Documentation is not needed for this change.

## Related Issues

Link any related issues here.
