# Configuration and local helper

`job-apply` is the Nix-installed helper. If it is not on PATH, substitute `<skill-dir>/scripts/run-helper.sh`. Without Nix that launcher requires Python 3 on PATH. Put global `--config PATH` before the subcommand.

```sh
job-apply init
job-apply --config /path/to/config.json validate
job-apply resume-text
job-apply queue 'https://example.com/jobs/123' 'https://example.com/jobs/456'
job-apply queue --input /path/to/jobs.txt
job-apply history
job-apply update --id JOB_ID --status in_progress --data /path/to/metadata.json
job-apply update --id JOB_ID --status awaiting_review
job-apply update --id JOB_ID --status submitting
job-apply update --id JOB_ID --status submitted --data /path/to/confirmation.json
job-apply recover --id JOB_ID
```

Commands output JSON except `resume-text`, which outputs extracted text. Errors go to stderr and return nonzero. `init` creates an example only when no configuration exists; edit it before validation. It does not create a resume.

## Settings

Copy `config.example.json` and replace the null resume path. The default history location is `~/.local/state/job-apply/history.json`. `~` expands to the current target user's home; relative resume/history paths resolve against the config file. `JOB_APPLY_CONFIG` is a file path; an explicit `--config` takes priority. An explicit run override controls the agent's browser/submission choice without rewriting config.

- `version`: `1`.
- `resume_path`: path to a UTF-8 text or PDF resume. The file is uploaded unchanged.
- `browser`: `playwright` (default, Playwright MCP), `terminal` (explicit terminal-browser selection), or legacy `auto` (also Playwright MCP). Missing Playwright MCP does not trigger automatic fallback. For existing configs, replace `vessel` with `playwright`; Vessel is no longer supported.
- `submission_mode`: `review` or `auto`.
- `history_path`: path to the writable JSON history.
- `profile`: candidate facts keyed by descriptive field names. `null` means unknown. Country-specific authorization questions should include country context.
- `answers`: list of `{ "questions": ["Question", "Equivalent wording"], "answer": "Candidate answer", "employer": "Optional scope", "role": "Optional scope" }`. Omit scopes for general answers. The agent matches meaning; the helper validates structure, not semantic suitability.

Do not put secrets or private answers in a flake or Nix seed expression. Edit the mutable JSON or use a module's external `configSeedFile` option. Resume module options are strings naming existing files, not Nix path literals that copy resumes to the store.

## History interface

History contains `version: 1` and `jobs`, an ordered list. Every record includes `id`, `url`, `aliases`, `status`, `created_at`, `updated_at`, and `attempt`. Metadata may include `employer`, `role`, `application_url`, `blocker`, `evidence`, and `note` (short operational text only).

`queue` accepts HTTP(S) URLs, ignores blank/comment lines in files, removes repeated normalized URLs, and returns `selected_ids` in input order plus their current records. Existing records retain position and status. URL normalization lowercases scheme/host and removes fragments; it preserves path and all query parameters. Redirect aliases allow later inputs to find the same record. Duplicate aliases across records are errors requiring inspection.

`update --data FILE` reads a JSON metadata object (`-` reads stdin). Allowed keys are the metadata above and `aliases` (a URL list). Unknown keys are rejected. For example, confirmation data is `{ "evidence": "Application received; receipt ABC123" }`. Submitted records require evidence and a prior `submitting` or `uncertain` state. Ordinary progress can move between `in_progress`, `awaiting_review`, and `blocked`; an explicit skip is recorded with `skipped`. A failed submission stays `uncertain` until inspected. Reset it to `in_progress` with `--retry-confirmed` only when non-submission was confirmed. Use `--reapply` to reset a submitted job to `pending`, incrementing the attempt and retaining prior confirmation in `previous_attempts`.

`recover --id ID` converts a stranded `submitting` record to `uncertain`; other statuses are unchanged. It does not open a site or infer success. History uses a lock and atomic replacement. One agent/browser workflow must own a batch at a time: the file lock protects individual writes, not simultaneous browser sessions.
