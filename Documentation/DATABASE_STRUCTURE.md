# Database Structure

The backend now uses a modular relational schema (SQLAlchemy) with SQLite default fallback at `.ctf-agent.db`.

## Tables

### `ctf_sources`
Stores each imported CTF source.

- `id` (PK, int)
- `name` (string)
- `slug` (string, unique)
- `base_url` (string)
- `auth_mode` (`token` | `credentials` | `none`)
- `challenges_root` (string)
- `last_import_at` (timestamp)
- `last_import_status` (`never` | `running` | `success` | `failed`)
- `last_import_error` (text)
- `created_at`, `updated_at` (timestamps)

### `challenges`
Stores challenge metadata for each source.

- `id` (PK, string)
- `ctf_id` (FK -> `ctf_sources.id`)
- `external_id` (CTFd challenge id)
- `name`, `slug`
- `path` (local challenge directory)
- `category`, `value`
- `description`, `connection_info`
- `has_distfiles`, `distfile_count`
- `solves`
- `imported_at`, `started_at`, `updated_at`

Constraints:

- unique (`ctf_id`, `external_id`)
- unique (`ctf_id`, `slug`)

### `challenge_files`
Stores downloaded distfiles per challenge.

- `id` (PK, int)
- `challenge_id` (FK -> `challenges.id`)
- `filename`
- `source_url`
- `local_path`
- `size_bytes`
- `created_at`

Constraint:

- unique (`challenge_id`, `filename`)

### `solver_runs`
Stores run metadata for process tracking and auditability.

- `id` (PK, string)
- `challenge_id` (FK -> `challenges.id`, nullable)
- `mode`
- `status`
- `command_json`
- `workdir`
- `pid`
- `output_log_path`
- `trace_ids_json`
- `exit_code`
- `created_at`, `started_at`, `finished_at`, `updated_at`

## Relationships

- One `ctf_sources` -> many `challenges`
- One `challenges` -> many `challenge_files`
- One `challenges` -> many `solver_runs`

## Default Database URL Resolution

1. `DATABASE_URL` from environment
2. `POSTGRES_URL` from environment
3. SQLite fallback: `sqlite+pysqlite:///<repo>/.ctf-agent.db`
