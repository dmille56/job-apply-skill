# Configuration and local helper

`job-apply` is the Nix-installed helper. Prefer `<skill-dir>/scripts/run-helper.sh` when following the loaded skill so instructions and helper versions match, even if PATH still contains an older package. The examples below use `job-apply` for brevity. Without Nix that launcher requires Python 3 on PATH. Put global `--config PATH` before the subcommand.

```sh
job-apply init
job-apply --config /path/to/config.json validate
job-apply resume-text
job-apply remember-answers --data /path/to/approved-answers.json
job-apply password-get  # Secret output; only when needed for the current account gate
job-apply account-lookup --origin https://careers.example.com --tenant employer-careers --email you@example.com
job-apply account-record --origin https://careers.example.com --tenant employer-careers --email you@example.com --stage ready --password-source shared_pass
job-apply email-search 'to:you@gmail.com from:accounts.example.com newer_than:1d subject:verification'
job-apply email-get 18abcdef01234567
job-apply queue 'https://example.com/jobs/123' 'https://example.com/jobs/456'
job-apply queue --input /path/to/jobs.txt
job-apply history
job-apply export-csv
job-apply update --id JOB_ID --status in_progress --data /path/to/metadata.json
job-apply update --id JOB_ID --status awaiting_review
job-apply update --id JOB_ID --status submitting
job-apply update --id JOB_ID --status submitted --data /path/to/confirmation.json
job-apply recover --id JOB_ID
```

Commands output JSON except `resume-text`, which outputs extracted text. Errors go to stderr and return nonzero. `init` creates an example only when no configuration exists; edit it before validation. It does not create a resume.

`password-get` is also plain text: it outputs only the configured pass entry's first line, a secret. It requires no readable resume and performs no password-store writes. Failure diagnostics omit pass output. See [accounts.md](accounts.md) for setup and account authorization.

## Settings

`email-search` and `email-get` require separately configured gogcli with the fixed `job-apply` account alias. They enforce read-only/no-send access and do not need or change JSON configuration. Read [email.md](email.md) for user setup, verification matching, and email restrictions.

Copy `config.example.json` and replace the null resume path. Optionally set `resume_json` to the path of a JSON file containing the structured resume (for example, contact details, summary, skills, and experience/education records). The file must contain a JSON object and is used as factual source material by the agent; it does not create an uploadable resume file. `resume_path` remains required for validation and uploading the original PDF/text resume. The default history location is `~/.local/state/job-apply/history.json`. `~` expands to the current target user's home; relative resume/history paths resolve against the config file. `JOB_APPLY_CONFIG` is a file path; an explicit `--config` takes priority. An explicit run override controls the agent's browser/submission choice without rewriting config.

- `version`: `1`.
- `resume_path`: path to a UTF-8 text or PDF resume. The file is uploaded unchanged.
- `resume_json`: optional path to a UTF-8 JSON file containing a structured resume object. It supplements `resume_path` and is not uploaded or converted to another file. Relative paths resolve against the config file. The helper checks that it is readable JSON containing an object.
- `browser`: `playwright` (default, Playwright MCP), `terminal` (explicit terminal-browser selection), or legacy `auto` (also Playwright MCP). Missing Playwright MCP does not trigger automatic fallback. For existing configs, replace `vessel` with `playwright`; Vessel is no longer supported.
- `submission_mode`: `review` or `auto`. Review collects one complete application review before submission; ordinary filling/navigation does not need approval.
- `remember_approved_answers`: Boolean, default `false`. When true, present generalized reusable defaults with the final application review and save them after approval. Automatic submission does not approve unreviewed defaults. Explicit requests to remember answers also authorize saving when this setting is false.
- `allow_account_creation`: Boolean, default `false`. When true, authorizes required candidate accounts and standard signup terms for requested jobs. Explicit run restrictions override this setting; it does not authorize unrelated accounts or unusual commitments.
- `history_path`: path to the writable JSON history.
- `csv_path`: optional path to the generated submitted applications CSV. Defaults to `applications.csv` beside the history file. Relative paths resolve against the config file. It must differ from config, resume, structured resume, history, and accounts paths.
- `password_pass_entry`: relative `pass` entry name, default `job-apply/shared-password`; never the password itself. Absolute paths, traversal, leading option prefixes, and control characters are rejected. Retrieval uses the user's existing pass/GPG environment.
- `accounts_path`: private non-secret account registry, default `~/.local/state/job-apply/accounts.json`. Relative paths resolve against the config file. It must differ from config, resume, and history paths. New directories use `0700`; writes use atomic replacement with mode `0600` and a file lock. Use a private parent directory.
- `profile`: candidate facts keyed by descriptive field names. `null` means unknown. Country-specific authorization questions should include country context.
- `answers`: list of `{ "questions": ["Question", "Equivalent wording"], "answer": "Candidate answer", "employer": "Optional scope", "role": "Optional scope" }`. Omit scopes for general answers. The agent matches meaning; the helper validates structure, not semantic suitability.

Do not put secrets or private answers in a flake or Nix seed expression. Edit the mutable JSON or use a module's external `configSeedFile` option. Resume module options are strings naming existing files, not Nix path literals that copy resumes to the store.

`account-lookup` returns `{ "account": null }` when absent, otherwise the matching non-secret record. `account-record` upserts by HTTPS origin, tenant, and case-insensitive email. Origins exclude paths, queries, and fragments; default HTTPS port 443 is normalized away. Tenant names remain case-sensitive. Required `--stage` is `signup_started`, `verification_pending`, or `ready`. Optional `--password-source` is `unknown`, `shared_pass`, or `external`; omission preserves the prior source. Records include `updated_at` and no free-form metadata. Stages describe observed account progress, not an enforced transition or application submission state. Registry corruption fails without overwriting it. One browser workflow must own the batch, as with history.

## History interface

History contains `version: 1` and `jobs`, an ordered list. Every record includes `id`, `url`, `aliases`, `status`, `created_at`, `updated_at`, and `attempt`. Metadata may include `employer`, `role`, `application_url`, `blocker`, `evidence`, and `note` (short operational text only), plus `contact_name`, `contact_email_phone`, `location`, `type`, `mode`, and `pay`. Confirmed submissions also have a helper-generated `submitted_at` timestamp.

`queue` accepts HTTP(S) URLs, ignores blank/comment lines in files, removes repeated normalized URLs, and returns `selected_ids` in input order plus their current records. Existing records retain position and status. URL normalization lowercases scheme/host and removes fragments; it preserves path and all query parameters. Redirect aliases allow later inputs to find the same record. Duplicate aliases across records are errors requiring inspection.

`update --data FILE` reads a JSON metadata object (`-` reads stdin). Allowed keys are the metadata above and `aliases` (a URL list). Unknown keys are rejected. For example, confirmation data is `{ "evidence": "Application received; receipt ABC123" }`. Submitted records require evidence and a prior `submitting` or `uncertain` state. Ordinary progress can move between `in_progress`, `awaiting_review`, and `blocked`; an explicit skip is recorded with `skipped`. A failed submission stays `uncertain` until inspected. Reset it to `in_progress` with `--retry-confirmed` only when non-submission was confirmed. Use `--reapply` to reset a submitted job to `pending`, incrementing the attempt and retaining prior confirmation in `previous_attempts`.

`recover --id ID` converts a stranded `submitting` record to `uncertain`; other statuses are unchanged. It does not open a site or infer success. History uses a lock and atomic replacement. One agent/browser workflow must own a batch at a time: the file lock protects individual writes, not simultaneous browser sessions.

## Submitted applications CSV

Recording `submitted` automatically generates a UTF-8 CSV with these columns in order:

`Company, Position, Link, Name of Contact, Email/Phone, Location, Type, Mode, Pay, Sent, Date (applied)`

Company and Position use `employer` and `role`; Link uses the original posting URL. The contact columns describe the hiring contact. Type describes employment type, Mode describes remote/hybrid/on-site work, and Pay is the advertised compensation including currency and period when known. Unknown details are empty. Sent is `Yes`; Date (applied) is `YYYY-MM-DD`, using the UTC submission date. Legacy submitted records use `updated_at` when `submitted_at` is absent.

The CSV is a generated report: each export atomically replaces it from JSON history, including confirmed previous reapplication attempts. Repeated exports do not duplicate rows. Keep manual spreadsheet edits in a separate copy. `export-csv` backfills existing submitted history or rebuilds a missing report; it creates a header-only file when there are no submissions. Pending, blocked, skipped, and uncertain attempts are excluded. A report failure leaves the confirmed submission in history; retry `export-csv` without applying again. New files use mode `0600`.

## Saving approved reusable answers

`remember-answers --data FILE` accepts a JSON array using the existing `answers` record schema (`--data -` reads stdin). The agent must generalize and obtain approval before calling it. It does not infer approval from submission mode or enforce the automatic-memory preference; an explicit request to remember answers is also sufficient authorization.

```json
[
  {
    "questions": ["When can you start?", "What is your availability?"],
    "answer": "Two weeks after accepting an offer."
  }
]
```

Prefer generic facts/preferences to employer-specific wording. Preserve meaningful qualifiers, including country and compensation currency/period. Scope to employer or role only when necessary; do not save tailored motivation essays or sensitive disclosures. The agent matches semantic equivalents before calling the helper.

The helper locks the selected configuration, rereads and validates it, and atomically saves with private file permissions. Matching uses overlapping question strings and equal employer/role scopes, normalized for whitespace and case. Equal answers (ignoring outer whitespace) merge question variants; differing answers reject the entire incoming batch without changing configuration. Other scopes remain separate. Semantic conflicts and sensitive-content filtering remain the agent's responsibility. Successful output contains counts, not answer values. Existing settings/profile/answers are retained; explicitly approved corrections to existing conflicting records require a separate validated edit under the same config lock, never an automatic replacement.
