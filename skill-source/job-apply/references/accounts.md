# Candidate accounts and shared passwords

Read this when the current requested application requires signup or login, including Workday-style multi-step portals. Keep the original job identity and application URL available while completing authentication.

## Setup managed by the user

Install `pass`, initialize the password store with the user's existing GPG key, and insert the shared password:

```sh
pass insert job-apply/shared-password
```

The user runs this interactive command; do not request a password in command arguments, conversation, or config. `password_pass_entry` selects a different entry if needed. Use the existing password store and GPG environment, including an explicitly configured `PASSWORD_STORE_DIR`. The first line of the decrypted entry is the password; later lines are ignored. The user must be able to unlock the key through their existing GPG agent/pinentry setup. See [pass documentation](https://www.passwordstore.org/).

Do not install software, initialize stores, generate keys, change GPG configuration, modify entries, or fall back to plaintext during an application. Missing `pass`, an unavailable entry, or failed/timed-out decryption blocks the step. Ask the user to fix setup or complete authentication. Never retry decryption in a loop.

One entry supplies the same password for new accounts. Reusing a password increases the impact of an employer account compromise. Changing this entry does not change passwords on employer sites; do not assume previously created accounts now use the new value. Password resets and rotation remain user-managed.

## Authorization

Resolve explicit run instructions first, then `allow_account_creation` (false when absent). An explicit instruction to create required accounts for the current supplied batch, or `allow_account_creation: true`, authorizes signup for those requested jobs. An explicit prohibition for the run overrides the setting. Otherwise ask once at the first account gate; the user can authorize the batch or only that portal. Do not ask again within existing authorization. Enabling the setting is standing permission for future requested jobs, not permission to add jobs or create unrelated accounts. This permission includes required standard candidate account terms and privacy acknowledgments. Inspect their actual purpose: ask about additional commitments or unusual agreements, and leave optional marketing/talent-pool consents unchecked. Submission still follows review/auto mode independently.

## Account identity and progress

Use the HTTPS portal origin, observed employer tenant/site identifier, and candidate email as the account identity. On portals with path-based tenants, use the stable tenant path/site identifier, not the job-specific path. For a portal with its own dedicated origin and no tenant identifier, use `default`. Do not merge tenants merely because they share an ATS or hostname; if the account boundary is unclear, ask rather than guessing. Do not put query strings, verification links, codes, or tokens in these fields.

```sh
job-apply account-lookup --origin https://careers.example.com --tenant employer-careers --email you@example.com
job-apply account-record --origin https://careers.example.com --tenant employer-careers --email you@example.com --stage signup_started --password-source shared_pass
job-apply account-record --origin https://careers.example.com --tenant employer-careers --email you@example.com --stage verification_pending
job-apply account-record --origin https://careers.example.com --tenant employer-careers --email you@example.com --stage ready
```

Substitute `HELPER` as described in SKILL.md. The registry stores only identity, stage, password source (`unknown`, `shared_pass`, or `external`), and update time. Omitted password source preserves the existing value; a new record defaults to `unknown`. `ready` means an account was visibly usable, not that an application was submitted. These records support recovery; they do not prove the current browser is authenticated or that credentials remain valid.

## Complete the gate

1. Inspect the browser and verify that any authenticated profile is the configured candidate. Reuse that session. Otherwise look up the portal identity before signup or login.
2. For an established `shared_pass` account, retrieve the password only when required with `HELPER password-get`, then enter it through the selected browser's normal password-field capability. A `signup_started` record alone does not establish which password an existing account uses; inspect the portal and resolve that uncertainty first. The command deliberately outputs a secret. Never pipe it into a file, copy it to the clipboard, include it in a report, or use it as shell code. Tool retrieval and browser entry may expose the value to tool transcripts; encryption at rest does not conceal those calls.
3. For a required new account, obtain signup authorization if needed and check password availability before starting. Record `signup_started` with `shared_pass` immediately before the create-account action. Fill the candidate email and same shared password, respecting required confirmation fields. Inspect validation. If rejected, pause for the user; do not generate an alternative or repeatedly try passwords.
4. If the portal says an account already exists, stop signup. Inspect the login route. If the current signup attempt first created the registry record, set its password source back to `unknown`: the attempted password was not established. Use the shared password only when prior successful creation/login or explicit user information establishes that account uses it. Otherwise ask the user to sign in or provide a supported credential route; record `external` only once established. Do not automatically reset passwords or infer the shared password works for unrelated existing accounts. After a failed login, pause instead of retrying credentials.
5. When verification is requested, record `verification_pending` and read [email.md](email.md). Match the actual challenge time, recipient, and portal; use the existing bounded email search and link checks. Confirm verification and account usability in the browser before recording `ready`.
6. Return to the saved job application, verify its employer and role, inspect each step and resume-parsed fields, then continue the main skill. Account creation and verification are never application submission evidence.

For interrupted or ambiguous signup, inspect the portal before another create-account action. A `signup_started` record means the account may exist. Prefer the login/account-status route; a fresh verification challenge may be necessary after expiration. Do not repeat signup blindly, automatically reset credentials, repeatedly request email challenges, or reuse stored verification tokens. Persist no tokens. Pause on unresolved outcomes, CAPTCHA, unsupported MFA, additional required facts, or missing browser/email capabilities. Mark the job `blocked` with a non-secret reason and retain queue order.
