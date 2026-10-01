# Changelog

All notable changes to the `besen` Python library are documented in this file.

This project follows semantic versioning where practical. Release tags use a `v` prefix, for example `v0.4.8`.

Up to version 0.4.8, the library was developed in [moryoav/besen](https://github.com/moryoav/besen) together with the Home Assistant custom integration, and versions 0.2.0 to 0.2.2 were published as `besen-bs20`. Some earlier entries also describe integration changes. The integration's changelog continues in that repository.

## [Unreleased]

### Fixed

- A start request without `amps` no longer falls back to the charger's maximum current when the charger has not reported its charging current. The client asks the charger for it and raises `CommandFailed` if no answer arrives within 5 seconds. A start request also stores its current on the charger, so the old fallback could raise the configured current to the maximum.
- `ChargeStatus.current_state` was one state ahead: a disconnected plug read `Ready to charge`, an active session read `Completed`, and a scheduled start read `Unknown 10`. It now matches the state the charger reports. `CURRENT_STATE` gained a leading `Unknown 0` entry so that list positions match the charger's codes.
- An immediate start after a finished session no longer fails with "Unknown reason". When `current_state` is `Completed` or `Completed Full Charge`, a start without a start time first sends the stop the charger requires and waits up to 5 seconds for it to leave that state. Scheduled starts, which the charger accepts in that state, send no stop.

### Changed

- While the charging current is unknown, the client asks for it again on every charger heartbeat, because the reply to the request sent at login can get lost.

## [0.4.9] - 2026-10-01

### Added

- Scheduled and time-limited charging. `async_start_charging()` accepts two new keyword arguments: a timezone-aware `start` up to 24 hours ahead makes the charger wait until then before charging, and `duration_minutes` (1 to 65534) makes it end the session after that many minutes of charging. The firmware calls a scheduled start a reservation. The charger reports an accepted schedule back as the `ChargeStatus` fields `scheduled_start` and `charging_time_limit`.
- An invalid start time or duration raises `ValueError` before anything is sent to the charger. The limits are available as `besen.const.MAX_START_DELAY` and `besen.const.MAX_CHARGE_DURATION_MINUTES`.
- `timestamp_bytes()` and `shanghai_adjusted_timestamp()` accept an optional timezone-aware `datetime` and still default to the current time.

### Changed

- The charger's "reservation successful" reply to a start request counts as acceptance. It was previously unmapped and would have raised `CommandFailed`.
- A start request without the new arguments is unchanged: it starts now, with no time limit. Stopping, clock synchronization, and the state model are unchanged.

## [0.4.8.post1] - 2026-10-01

### Changed

- Move the library, with its history, to its own repository at [moryoav/py-besen](https://github.com/moryoav/py-besen). Release tags now use `vX.Y.Z` instead of `library-vX.Y.Z`. The package name, import name, and public API are unchanged.
- Point the PyPI project links to the new repository and use the library guide as the PyPI description.
- Test on Python 3.12, 3.13, and 3.14.

### Updating

- This post-release changes only packaging metadata and documentation. The library code is identical to 0.4.8, so Home Assistant keeps requiring `besen==0.4.8`.

## [0.4.8] - 2026-09-30

### Added

- Decode the session start, elapsed session time, session current limit, scheduled start, and charging time limit from the live and completed session reports. They are exposed as the `ChargeStatus` fields `session_start`, `session_duration` (seconds), `session_current_limit` (amperes), `scheduled_start`, and `charging_time_limit` (minutes). The firmware calls a scheduled start a reservation.
- Timestamps are timezone-aware UTC datetimes, decoded in the same Unix epoch format the library writes when it syncs the charger clock and requests charging. Unset timestamps and limits and an unlimited time limit are `None`, while a zero duration stays `0`.

### Changed

- The new fields default to `None` until the first session report, and a later report without them clears previous values. Session energy decoding, charging commands, clock synchronization, and the existing public API are unchanged.

### Validation

- Cover both report types, extended and truncated payloads, sentinel values, clearing previous values, and a round trip of a timestamp written by the library.
- Passed 276 tests and 92 snapshots with 96.98% combined coverage, plus Ruff, mypy, Core alignment, and package validation. No physical charger was operated for this change.

## [0.4.7] - 2026-09-18

### Added

- Add the typed `BesenData.auth_failed` state for an explicit PIN rejection. A Bluetooth outage, an incomplete login, or error-message text cannot be mistaken for rejected credentials.

### Changed

- Stop watchdog and reconnect retries after the charger rejects the PIN, and ignore queued packets from the rejected login. A new login attempt clears the failure state.
- Charging commands, response correlation, outage logging, and the existing public API are unchanged.

### Validation

- Cover explicit and unsolicited rejections, rejected-login packet ordering, watchdog and reconnect suppression, recovery with a replacement PIN, and startup rejection.
- Passed 227 tests and 66 snapshots with 96.92% combined coverage, plus Ruff, mypy, Core alignment, and package validation. No physical charger was operated for this change.

## [0.4.6] - 2026-09-17

### Changed

- Log one `INFO` message when a previously usable charger becomes unavailable, including the device name and reason, and one `INFO` message when it is available again. This replaces the warning repeated every ten minutes and addresses Home Assistant's `log-when-unavailable` quality rule.
- Report recovery only after Bluetooth availability and authentication are both restored. Initial setup, intentional shutdown, and restart do not log outage or recovery messages.
- Report a PIN rejected while reconnecting with one `WARNING` per outage instead of an error on every watchdog cycle. The charger stays unavailable until the PIN is corrected.
- Move routine watchdog, login-retry, and connection-release details to `DEBUG`, and remove the duplicate reconnect success message. Unexpected packet-handling failures remain warnings.
- Charging commands, response correlation, retry behavior, timing, and public APIs are unchanged.

### Validation

- Cover each availability and authentication loss combination, long watchdog outages, duplicate disconnect callbacks, silent reconnect retries, rejected PINs across two outages, shutdown during an outage, and initial setup failures.
- Passed 196 tests and 66 snapshots with 96.39% combined coverage, plus Ruff, mypy, Core alignment, and package validation. No physical charger was operated for this logging-only change.

## [0.4.5] - 2026-09-14

### Fixed

- Match charge-start replies to the connector ID reported by telemetry instead of the single-phase or three-phase request selector. This fixes valid three-phase replies being ignored, followed by a false timeout and unnecessary Bluetooth disconnection.
- Correlate replies with the authenticated charger and serialized pending request when connector telemetry is not available yet, without guessing a connector ID from the phase count.
- Preserve the existing single-phase and three-phase start packets and supported Bluetooth write modes. Add debug logging of the response and expected connector ID.

### Validation

- Cover accepted and rejected responses for both phase counts, before and after connector telemetry, and preserve rejection of replies from another charger or a known different connector.
- Exercise single-phase charging with acknowledged-only, unacknowledged-only, and dual-mode GATT characteristics.
- Validate a physical three-phase BS20 stop/start at 6 A: connector 1 acknowledged the unchanged three-phase request in 0.092 seconds, without a forced disconnect.
- Passed 181 tests and 66 snapshots with 96.09% combined coverage, plus Ruff, mypy, Core alignment, and package validation.

## [0.4.4] - 2026-09-14

### Fixed

- Wait for the charger response before completing a Python library start-charging request, and raise `CommandFailed` for reported rejection codes, disconnection, or a missing response.
- Serialize start-charging requests and retire the Bluetooth session after a timeout or cancellation so a late response cannot complete the next request. Do not retry the charging action automatically.

### Validation

- Add coverage for accepted and rejected requests, unknown error codes, unrelated responses, concurrent requests, transport failures, disconnection, cancellation, and late replies from a retired connection.
- Passed 169 tests and 66 snapshots with 96.09% combined coverage, plus Ruff, mypy, Core alignment, and package validation. Physical charger validation of response timing remains pending.

### Packaging

- Publish Python library releases with `library-vX.Y.Z` tags independently of the HACS integration version.

## [0.4.3] - Withdrawn 2026-09-11

- Withdrawn the September 9 release following a report that initial connection no longer succeeds. A regression is suspected but has not been confirmed.
- Reverted the automatic service-cache clearing and discovery retry changes. Restored 0.4.2 as the latest supported release.
- Kept the remaining connection instability under investigation pending testing with improved Bluetooth reception.

## [0.4.2] - 2026-09-08

### Fixed

- Use acknowledged Bluetooth writes when the charger only advertises that write mode, including the single-phase BS20 variant reported in [moryoav/besen#1](https://github.com/moryoav/besen/issues/1). Preserve unacknowledged writes on boards that support them.
- Select a complete, usable notification/write characteristic pair from discovered GATT characteristics instead of relying on service prefixes or assuming the old-board UUIDs exist.
- Report discovered service UUIDs and characteristic properties in debug logs when no supported pair is found.

### Validation

- Added regression coverage for single-phase login and commands, all supported write modes, reconnects, and missing or unusable characteristics.
- Full connection and charging validation on the reporter's single-phase hardware remains pending.

### Documentation

- Clarified the shared library and full-feature HACS release workflow on `main`, independent of selective Home Assistant Core submissions.
- Corrected the custom integration's sensor names and enabled defaults, and documented upgrades from the legacy `besen_bs20` domain.

## [0.4.1] - 2026-08-30

### Fixed

- Keep LCD brightness, language, and temperature unit state in sync after successful configuration commands.

## [0.4.0] - 2026-08-29

### Added

- Added session energy parsing for charging status commands 5 and 6.

### Changed

- Replaced the misleading `current_energy` and `current_amount` fields with `power`, `total_energy`, and `session_energy` fields that match the charger protocol.
- Return `None` for invalid temperature values and reject incomplete status payloads.
- Parse three-phase data from the protocol's exact 33-byte payload length.
- Updated the bundled Home Assistant custom integration to use the corrected telemetry fields and entity names.

## [0.3.4] - 2026-08-21

### Fixed

- Fixed reconnect handling when a charger keeps its previous application session after the Bluetooth connection is interrupted.
- Prevented duplicate login packets, stale callbacks, and incomplete cleanup from causing reconnect loops.

## [0.3.3] - 2026-07-30

### Fixed

- Updated project, documentation, badge, and contribution links after renaming the GitHub repository to `moryoav/besen`.

## [0.3.2] - 2026-07-06

### Fixed

- Replaced relative README links with absolute GitHub links so the PyPI project description does not point to missing `pypi.org/project/besen/...` pages.

## [0.3.1] - 2026-07-06

### Changed

- Replaced the PyPI-facing README with Python library usage and API documentation.
- Moved the Home Assistant custom integration README content to `docs/home-assistant-custom-integration.md`.

## [0.3.0] - 2026-07-06

### Changed

- Renamed the published Python distribution and import package from `besen-bs20` / `besen_bs20` to `besen`.
- Renamed the public Python client/data/error API to `BesenClient`, `BesenData`, and `BesenError`.
- Renamed the bundled Home Assistant custom integration domain from `besen_bs20` to `besen` and updated it to depend on `besen==0.3.0`.

## [0.2.2] - 2026-07-02

### Changed

- Corrected the displayed Celsius temperature-unit spelling while keeping the legacy `Celcius` command input as an alias.

## [0.2.1] - 2026-07-02

### Changed

- Limited repeated BLE unavailable watchdog warnings so Home Assistant logs are not flooded while the charger is unreachable.

## [0.2.0] - 2026-07-02

### Added

- Added a `besen-bs20` Python package containing the async BLE client, protocol parser, data models, and exceptions.
- Added package build validation to CI and PyPI trusted publishing to the tag release workflow.

### Changed

- Updated the Home Assistant integration to depend on `besen-bs20==0.2.0` instead of carrying protocol/client code inside `custom_components`.
