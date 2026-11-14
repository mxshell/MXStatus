# Server configuration and API

Open **`/admin/`** on your MXStatus server to manage the fleet. Sign in with
`MXSTATUS_ADMIN_TOKEN`. The responsive panel is bundled with FastAPI and needs no
Node.js server, frontend build step, or external assets.

The panel provides:

- Searchable client health, CPU/RAM/GPU telemetry, storage, and last-report times.
- Client display names, notes, reporting-interval overrides, blocking and forgetting.
- Reporting-key creation, renaming, copying, revocation, and client config downloads.
- View-group creation, membership editing, enabling/disabling, expiration and deletion.
- Server name, console refresh frequency, offline threshold, enrollment and capacity.

Admin tokens stay in tab memory and are cleared on sign-out or reload. Every
management API requires bearer authentication. Destructive actions require an
in-panel confirmation. Configuration downloads contain a reporting secret; keep
them private.

## Storage and restarts

Management state is stored in `data/mxstatus.sqlite3` by default. Set
`MXSTATUS_DATA_PATH` to move it, or `:memory:` for a temporary/test instance. Docker
Compose mounts a named `mxstatus-data` volume. Back up the database securely: it
contains reporting and view keys. Its file permissions are restricted to the owner.

Settings, client registrations, blocked clients, keys and views survive restarts.
Live telemetry is held in memory; clients show as waiting until they report again.
Run **one worker and one replica**: the in-memory state is not coordinated between
processes. Management changes are saved atomically and rolled back on disk errors.

Environment bootstrap settings are applied **only when initializing a new state
database**. This prevents deleted keys or disabled access from being restored on
restart. To change existing keys or views, use the panel. Changing the bootstrap
variables later does not overwrite saved management state. The admin token and
CORS origins remain environment settings and require a restart when changed.

## Configure access

Set these variables in your environment (or a root-level `.env` for Docker Compose):

| Variable | Purpose |
| --- | --- |
| `MXSTATUS_ADMIN_TOKEN` | Required for admin access; random, at least 32 characters. |
| `MXSTATUS_ADMIN_USER_ID` | Bootstrap user ID; defaults to `1000`. |
| `MXSTATUS_REPORT_KEY` | Optional bootstrap reporting key. |
| `MXSTATUS_VIEW_KEY` | Optional bootstrap view key; requires a reporting key. |
| `MXSTATUS_MACHINE_IDS` | Comma-separated machine IDs reserved for the bootstrap reporting key and view. Requires a reporting key. |
| `MXSTATUS_DATA_PATH` | Management database path; defaults to `data/mxstatus.sqlite3`. |
| `MXSTATUS_CORS_ORIGINS` | Comma-separated permitted browser origins. Browser cross-origin access is disabled by default. |

Generate **separate** secrets for the admin token, reporting key and view key using
`python3 -c 'import secrets; print(secrets.token_hex(32))'`. Report and view keys
must be 16–64 ASCII letters or digits, are case insensitive, and are stored in
uppercase. Admin tokens are case sensitive. Keep `.env` private and out of Git.

The old built-in email reporting key and default view key have been removed.
Existing deployments must configure new keys and update each client's
`client/config.json` before upgrading. Treat the old published keys as compromised.

For direct development use, export these variables before starting Uvicorn; it
does not automatically load `.env`. If the admin token is missing or too short,
admin endpoints return 503. An invalid or missing bearer token returns 401 when
admin access is configured.

Expose the service through HTTPS. Report and view keys are bearer credentials;
anyone holding a key has its permissions. The current API uses query parameters
for view keys and some admin operations, so disable or redact query-string access
logs in reverse proxies. The Docker command disables Uvicorn access logs.

## API

All of these admin routes require `Authorization: Bearer <MXSTATUS_ADMIN_TOKEN>`:

- `GET /get`: inspect all reports, with reporting credentials omitted.
- `POST /create_report_key?user_id=1000`: create a reporting key. Optional
  `report_key` and `report_key_desc` query parameters customize it.
- `POST /delete_report_key?user_id=1000&report_key=...`: revoke a key; remove
  reports and view memberships no longer owned through another key.
- `POST /create_view_group?user_id=1000`: JSON body such as
  `{"view_machines":["machine-id"],"view_name":"Workstations"}`. A secure view key
  is generated if omitted. `view_machines` defaults to an empty list.
- `POST /add_machines_to_view_group`, `/remove_machines_from_view_group`, or
  `/set_machines_in_view_group`: `user_id` and `view_key` query parameters, and a
  JSON array of machine IDs. Repeated IDs are deduplicated; setting `[]` clears a view.

The admin token grants server-wide administrative access. `user_id` selects the
owner and is not an authentication credential. A machine must first report using
one of that owner's reporting keys before it can be added to a view. Bootstrap
machine IDs can be reserved before the first report. A reporting key cannot
replace a machine registered to another owner.

Client and viewer routes:

- `POST /report`: JSON status with `machine_id` and `report_key`. The server
  records its UTC receipt time, regardless of the client timestamp.
- `GET /view?view_key=...`: latest reports in an active view.
- `GET /view_machine?view_key=...&machine_id=...`: 200 for a fresh report with a
  GPU, 404 for an unavailable machine/view, 417 for an expired report, or 418 for
  a report without a GPU. `seconds_to_expire` is a positive integer; when omitted, the configured offline
  threshold is used (initially 300 seconds).
- `GET /check_view_group?view_key=...`: metadata for an active view.

Disabled or expired views cannot expose reports or metadata. `view_timer` accepts
an ISO 8601 timestamp; timestamps without an offset are interpreted as UTC.
Reporting keys are never returned in status responses. Invalid payloads return
422; unexpected failures return a generic 500 and are logged server-side.

Requests are limited to 1 MiB. Client capacity is configurable up to 10,000
registrations, including clients waiting for a report. Updates to existing machines
still work at capacity. Use a reverse proxy to enforce request
rates and connection limits for an Internet-facing deployment.

## Panel API

`GET /admin/api/state` returns settings, runtime information, registered clients,
reporting keys and view groups to authenticated administrators. Mutations use JSON
bodies so the panel does not put access keys in request URLs:

| POST route | Body |
| --- | --- |
| `/admin/api/settings` | Server settings shown in the panel. |
| `/admin/api/clients/update` | `machine_id`, `display_name`, `notes`, `enabled`, nullable `report_interval`. |
| `/admin/api/clients/delete` | `machine_id`. |
| `/admin/api/keys` | `report_key_desc`, optional `report_key` and `user_id`. |
| `/admin/api/keys/update` | `report_key`, `report_key_desc`. |
| `/admin/api/keys/delete` | `report_key`. |
| `/admin/api/views` | ViewGroup JSON; optional `user_id` query parameter. |
| `/admin/api/views/update` | ViewGroup JSON including the existing `view_key`. |
| `/admin/api/views/delete` | `view_key`. |

Blocking a client rejects its incoming reports without stopping the client process.
Forgetting a client removes its settings, cached report and memberships; a running
client can re-register if enrollment is enabled. Use blocking to prevent that.

`POST /report` now includes `config.report_interval` in successful acknowledgements.
Updated clients apply a valid interval on their next report. A null interval restores
their local configuration. Older clients continue reporting but must be upgraded to
support remote interval changes. Names and notes are server-side metadata. Changing
the default reporting interval affects newly downloaded configs, not existing clients.
