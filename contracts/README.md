# contracts — Shared contract between web and worker

A plain file directory with no build tooling. It is not an npm package.

## Source of truth

`supabase/migrations/*.sql` is the source of truth. The two files below mirror it.

| File | Consumer |
|---|---|
| `db.types.ts` | web (`@supabase/supabase-js` generics) |
| `worker/src/m3d/models.py` | worker (Pydantic validation) |

When the schema changes, update **all three together**. `worker/tests/test_migration_sql.py` guards against
constraints disappearing on the SQL side.

## Type generation status

This section records the results of trying to generate the types automatically with `supabase gen types`.

- First attempt (at design time): `npx --yes supabase@latest gen types typescript --db-url
  $env:SUPABASE_DB_URL` failed (exit code 1). At that time `SUPABASE_DB_URL` was not set (the project owner had not
  yet created the Supabase project), so `$env:SUPABASE_DB_URL` expanded to an empty value and no value reached the
  `--db-url` flag. The Supabase CLI (`supabase@latest`, downloaded and run on the spot through npx) exited with this
  error:

  ```json
  {"_tag":"Error","error":{"code":"InvalidValue","message":"Missing value for flag --db-url. Expected: string"}}
  ```

  (Just before that, the flag parser, having failed to recognize the flags, first dumped the `--help` text of the
  whole command to stderr — this is the CLI's own behavior, not a problem with our configuration.)
- Current status (2026-08-29): `SUPABASE_DB_URL` is now set, so the cause of the failure above no longer applies.
  However, the command was not rerun to update this section — the `--db-url` value is expanded on the command line
  as it is and contains the password, which would leave the secret in the shell history and the process list (for
  handling secrets, see `CLAUDE.md` §3).
- Origin of `db.types.ts`: written by hand (transcribed by hand from `supabase/migrations/0001_init.sql`). The M0
  final review compared it with `0001_init.sql` column by column and confirmed there is no drift — since no reason
  to switch to automatic generation has been established, this state is kept for now as **a deliberate keep in M0**.

Regeneration through `supabase gen types` is an optional task in M1 — it is not required. If the types are
regenerated, replace the hand-written file with the generated one and update this section.
