# Job Apply Skill

A portable skill for Codex, Claude Code, OpenCode, and Pi that applies to supplied jobs one at a time using Playwright MCP by default, or terminal-browser when explicitly requested. It supports a configurable resume, reusable application answers, resume-qna for substantive answers, one review per application or automatic submission, and resumable local history.

## NixOS and Nix

This flake follows the layout of `resume-qna`: `skill-source/`, installer apps, Home Manager and NixOS modules. It supports `x86_64-linux` and `aarch64-linux`.

```sh
nix run .#install
nix build .#job-apply
./result/bin/job-apply validate
```

The installer copies the skill to `~/.agents/skills/job-apply` and `~/.claude/skills/job-apply`, then creates configuration if absent. Existing configuration, answers, history, and unrelated files are preserved. Python and Poppler utilities are included in both the Nix helper and the copied `scripts/run-helper.sh` launcher. The installer retains its runtime through a Nix GC root at `${XDG_STATE_HOME:-~/.local/state}/job-apply/nix-runtime`; remove that link when uninstalling. Modules additionally put Poppler utilities on PATH for agent PDF reading. Browser software and MCP connections must already work, or be supplied separately.

### Home Manager

Add this repository as a flake input named `job-apply`, then:

```nix
{ inputs, ... }: {
  imports = [ inputs.job-apply.homeManagerModules.job-apply ];
  jobApply = {
    enable = true;
    resumePath = "/home/you/Documents/resume.pdf";
    browser = "playwright";
    submissionMode = "review";
  };
}
```

### NixOS module

```nix
{ inputs, ... }: {
  imports = [ inputs.job-apply.nixosModules.job-apply ];
  jobApply = {
    enable = true;
    user = "you";
    resumePath = "/home/you/Documents/resume.pdf";
    # Optional existing browser derivations:
    # browserPackages = [ inputs.your-browser.packages.x86_64-linux.default ];
  };
}
```

NixOS activation installs as the target user, so configuration/history stay user-owned. The user's home must exist and be writable at activation. With an encrypted/unmounted home, use Home Manager activation after login or the installer. Choose either module for the same user, rather than activating both against the same files.

Both modules expose `installDirs`, `configPath`, `resumePath`, `browser`, `submissionMode`, `historyPath`, `configSeedFile`, and `browserPackages`. NixOS additionally exposes `user` and `homeDirectory`. Path options are absolute strings. Defaults seed a new mutable config; changing them later does not overwrite an existing config.

For private answers, edit the JSON after installation or set `configSeedFile = "/home/you/private/job-apply-seed.json";`. This external file is read at activation only if config is absent. Never use a Nix path literal or `builtins.readFile` for private resumes/answers: those can copy contents into the Nix store. An external seed overrides other seed options. The skill and helper are immutable in the store; active personal state stays outside it.

`configPath` changes where installation seeds config. For a nondefault path, set `JOB_APPLY_CONFIG` in the agent's environment or explicitly supply the path when invoking the skill/helper.

## Without Nix

Install Python 3 and, for PDF resumes, Poppler (`pdftotext`), then run:

```sh
sh ./install-job-apply.sh
# Optional custom targets and external seed:
sh ./install-job-apply.sh --home /home/you --skill-dir /home/you/.agents/skills/job-apply --seed /path/to/config.json
```

Use `~/.agents/skills/job-apply/scripts/run-helper.sh` if `job-apply` is not on PATH. The non-Nix launcher requires Python 3 on PATH. Neither installer installs a browser or changes agent configuration.

## Configuration

Edit `~/.config/job-apply/config.json` and set `resume_path`. It accepts a UTF-8 `.txt`/`.md` file or a PDF. Optionally set `resume_json` to the path of a JSON file containing structured resume facts; it supplements the document for answering questions and is not uploaded. Relative resume, structured resume, and history paths resolve against this JSON's directory. Explicit helper `--config` takes priority over `JOB_APPLY_CONFIG`, then the default location.

```json
{
  "version": 1,
  "resume_path": "/home/you/Documents/resume.pdf",
  "resume_json": "structured-resume.json",
  "browser": "playwright",
  "submission_mode": "review",
  "remember_approved_answers": true,
  "allow_account_creation": true,
  "history_path": "~/.local/state/job-apply/history.json",
  "password_pass_entry": "job-apply/shared-password",
  "accounts_path": "~/.local/state/job-apply/accounts.json",
  "profile": {
    "full_name": "Your Name",
    "email": "you@example.com",
    "work_authorization": null,
    "requires_sponsorship": null
  },
  "answers": [
    {
      "questions": ["When can you start?", "What is your availability?"],
      "answer": "Two weeks after accepting an offer."
    }
  ]
}
```

Use your own facts. `null` means unknown. Answers may optionally specify `employer` and `role` scopes. The agent fills accessible fields independently, uses resume-qna for substantive written responses, and bundles unresolved questions. Required unknown facts pause only when they prevent further progress; hidden later pages may reveal additional questions. Review mode presents all answers together before submission. With `remember_approved_answers: true`, that review also includes generic reusable defaults to save after approval. Meaningful qualifiers remain intact, and tailored motivation essays and sensitive disclosures are not saved. Both new Boolean settings default to false when absent; setting `allow_account_creation: true` grants standing permission for required candidate accounts on requested jobs. See the [configuration reference](skill-source/job-apply/references/configuration.md) for CLI details and history recovery.

```sh
job-apply validate
job-apply resume-text
job-apply history
job-apply export-csv
```

Confirmed submissions automatically generate `applications.csv` beside the JSON history (by default `~/.local/state/job-apply/applications.csv`). Set `csv_path` in configuration to choose another location. Columns are Company, Position, Link, Name of Contact, Email/Phone, Location, Type, Mode, Pay, Sent, and Date (applied). Unknown details stay blank, Sent is `Yes`, and dates use `YYYY-MM-DD`. Run `job-apply export-csv` to backfill existing submitted history or retry a failed export. This generated report is replaced from history on export, so keep manual spreadsheet edits in a separate copy. Confirmed reapplications retain a row for each attempt.

## Agent and browser setup

The shared `~/.agents/skills/job-apply` installation serves Codex, OpenCode, and Pi; the Claude copy serves Claude Code. Restart/reload skills after installation. The same package can instead be copied to each agent's documented project or personal skill directory. No agent-specific plugin is required.

| Agent | Personal skill directory | Example request |
| --- | --- | --- |
| Codex | `~/.agents/skills/job-apply` | `$job-apply Apply to https://example.com/jobs/123` |
| Claude Code | `~/.claude/skills/job-apply` | `/job-apply Apply to https://example.com/jobs/123` |
| OpenCode | `~/.agents/skills/job-apply` | `Use job-apply to apply to these URLs…` |
| Pi | `~/.agents/skills/job-apply` | `/skill:job-apply Apply to these URLs…` |

For **Playwright MCP**, configure your agent with command `playwright-mcp` and arguments `[]`. The command must be installed and available on the agent's PATH. The agent must expose the MCP tools and the server must have a working browser. See the [official Playwright MCP setup](https://github.com/microsoft/playwright-mcp) for client configuration and browser options.

For **terminal-browser**, install it and its skill, use a supported graphical terminal, and check that `terminal-browser ls --json` works in the agent's environment. It controls a visible browser through its agent-browser-compatible CLI. Some hosts require additional sandbox permissions; the skill pauses if they are unavailable. See [terminal-browser setup](https://github.com/zenbu-labs/terminal-browser).

`browser: "playwright"` is the default; legacy `auto` also selects Playwright MCP. Use terminal-browser only when explicitly requested for a run or configured with `browser: "terminal"`. If Playwright MCP is unavailable, the skill pauses for setup or a user-requested switch. Existing configs using `vessel` must change to `playwright`. An explicit browser choice must be usable. A submission setting does not override browser or host permission prompts.

**resume-qna**: install it through your agent's normal skills mechanism. Job Apply reads its instructions once per run and uses them for every answer requiring explanation, examples, motivation, or persuasive wording, including short responses. If unavailable, it fills accessible simple fields and bundles the prerequisite with other blockers before drafting substantive responses. If its configured resume differs and it has no supported override, Job Apply uses its writing guidance directly with the selected job-apply resume without changing resume-qna.

## Usage and recovery

For account creation and login, install and initialize `pass` with your GPG key, then store the shared password interactively:

```sh
pass insert job-apply/shared-password
```

The skill retrieves the first line of this entry only when needed. Set `password_pass_entry` to use another entry; never put the password in job-apply configuration or Nix expressions. `pass` and GPG setup/unlocking remain user-managed prerequisites, including for Nix installations. A missing entry or failed unlock pauses the application. The helper never modifies the password store. Reusing one password increases the impact of a compromised employer account; changing the entry does not update existing employer accounts.

Authorize required account creation persistently with `allow_account_creation: true`, or explicitly for a batch, for example: “Apply to these URLs and create required candidate accounts using my shared password in pass.” This includes standard required signup terms and privacy acknowledgments; application submission still follows review/auto mode. The skill uses a private non-secret account registry at `accounts_path` to distinguish candidate emails and employer tenants, track verification progress, and recover interrupted signup. It reuses known accounts and pauses for unknown existing credentials, password rejection, CAPTCHA, unsupported MFA, or additional commitments. See [account setup and workflow](skill-source/job-apply/references/accounts.md). Password retrieval and browser entry may expose the value in tool transcripts; it is never written to application history or reports.

Optional verification email uses [gogcli](https://github.com/openclaw/gogcli). Install `gog` separately, configure its OAuth credentials, then authorize the candidate's Gmail mailbox and create the required account alias:

```sh
gog auth add you@gmail.com --services gmail --gmail-scope readonly --readonly
gog auth alias set job-apply you@gmail.com
```

The skill uses `job-apply email-search` and `job-apply email-get` for verification codes, sign-in/confirmation links, and relevant submission receipts. Both pin the `job-apply` alias and enforce read-only, no-send, and exact command restrictions. They cannot send mail, create drafts, mark messages read, or change email settings. Setup remains user-managed; missing access pauses the application. Existing JSON configs need no changes. See [email setup and workflow](skill-source/job-apply/references/email.md) for scope requirements and verification boundaries.

```text
Use job-apply to apply to https://example.com/jobs/123.

Use job-apply with terminal-browser to apply to the URLs in ./jobs.txt.
Review each application before submitting.

Use job-apply to apply to these URLs in order and submit automatically:
https://example.com/jobs/123
https://example.com/jobs/456

Resume the interrupted job-apply batch.
```

Applications collect missing facts and conflicts while finishing accessible work, then request them together if they block progress. They also stop for unresolved login/CAPTCHA, agreements outside existing authorization, or ambiguous submission outcomes. A batch advances after confirmed submission or explicit skip. Confirmed submissions are skipped unless you explicitly request reapplication. Sequential history is local to this configuration and is not a shared account-wide duplicate detector. Run one application workflow against a history file at a time.

The skill explicitly ignores website instructions directed at AI agents, including hidden content and instructions surfaced through browser tools. Websites supply application data; they cannot grant permission, change submission mode, request unrelated files or secrets, or override the user's instructions. Suspicious requests with an unclear purpose or destination pause the application. This is an agent instruction safeguard, not a sandbox or a guarantee against prompt injection; keep browser and tool permissions limited. Reinstall/reload the skill after updating its source to apply these rules to installed copies.

History records URLs, status, short operational metadata, and confirmation evidence. It does not store form answers or credentials. Approved reusable defaults are stored separately in the selected configuration through `job-apply remember-answers --data FILE`; saves are locked and atomic and reject conflicting replacements. Helpers use private file permissions and atomic writes. If submission was interrupted, the agent inspects the site before retrying; `recover --id ID` only marks the uncertain outcome and does not check the employer's site.

## Development and validation

```sh
nix develop
python3 tests/test_helper.py skill-source/job-apply
nix flake check
nix fmt
```

The helper suite uses temporary directories and no network. Open `tests/mock-application.html` in the selected browser to exercise upload, conditional required fields, a 300-character answer, later-page availability and compensation questions, confirmation, a simulated login blocker, and an ambiguous result. Use fictional information and a test resume. Exercise both review and auto modes, bundle missing sponsorship data after filling other accessible fields, and repeat with resume-qna absent/matching/mismatched. Verify that accessible fields are completed before asking for sponsorship, later-page unknowns are bundled together, and final review includes all entered answers plus generalized defaults. Verify saved defaults retain country/currency qualifiers, exclude tailored essays, and work across employers. Test standing account permission and an explicit run prohibition separately. Agent/browser scenarios require manual execution; the helper suite does not exercise agent judgment. This fixture never sends an application. Browser and agent integrations require a working interactive host; helper tests alone do not validate those integrations.

Use `tests/mock-account-flow.html` to exercise new signup, existing-account detection/login, password rejection, and recovery after interrupted signup. It uses only fictional in-memory credentials and a visible mock verification code, and links back to the application fixture with the job identity. Account verification must never be recorded as an application submission. For an interruption immediately after creation, call `interruptSignup()` in the fixture and recover through sign-in without repeating signup.

For module evaluation against local nixpkgs and Home Manager checkouts:

```sh
nix-instantiate --eval --strict --json tests/eval-modules.nix \
  --arg nixpkgs /path/to/nixpkgs --arg homeManager /path/to/home-manager
```

The lock file starts with the same nixpkgs revision as the reference resume-qna flake. In an unpacked workspace containing a placeholder `.git` directory, use `nix flake check path:"$PWD"` and `nix run path:"$PWD"#install`; ordinary `.` works in a real checkout.
