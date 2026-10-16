# Job Apply Skill

A portable skill for Codex, Claude Code, OpenCode, and Pi that applies to supplied jobs one at a time using Vessel or terminal-browser. It supports a configurable resume, reusable application answers, optional resume-qna guidance, review or automatic submission, and resumable local history.

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
    browser = "auto";
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

Edit `~/.config/job-apply/config.json` and set `resume_path`. It accepts a UTF-8 `.txt`/`.md` file or a PDF. Relative resume/history paths resolve against this JSON's directory. Explicit helper `--config` takes priority over `JOB_APPLY_CONFIG`, then the default location.

```json
{
  "version": 1,
  "resume_path": "/home/you/Documents/resume.pdf",
  "browser": "auto",
  "submission_mode": "review",
  "history_path": "~/.local/state/job-apply/history.json",
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

Use your own facts. `null` means unknown. Answers may optionally specify `employer` and `role` scopes. Missing required answers pause the current application. The agent saves new reusable answers only when asked. See the [configuration reference](skill-source/job-apply/references/configuration.md) for CLI details and history recovery.

```sh
job-apply validate
job-apply resume-text
job-apply history
```

## Agent and browser setup

The shared `~/.agents/skills/job-apply` installation serves Codex, OpenCode, and Pi; the Claude copy serves Claude Code. Restart/reload skills after installation. The same package can instead be copied to each agent's documented project or personal skill directory. No agent-specific plugin is required.

| Agent | Personal skill directory | Example request |
| --- | --- | --- |
| Codex | `~/.agents/skills/job-apply` | `$job-apply Apply to https://example.com/jobs/123` |
| Claude Code | `~/.claude/skills/job-apply` | `/job-apply Apply to https://example.com/jobs/123` |
| OpenCode | `~/.agents/skills/job-apply` | `Use job-apply to apply to these URLs…` |
| Pi | `~/.agents/skills/job-apply` | `/skill:job-apply Apply to these URLs…` |

For **Vessel**, launch the browser and configure its MCP helper in your agent. The stdio command is `vessel-browser-mcp` with arguments `["--stdio"]`. Codex uses an `mcp_servers` TOML entry; Claude Code and current Pi use `mcpServers` JSON with `command`/`args`; OpenCode uses its local MCP entry with a command array. Use your installed agent's documentation for registration and permissions. Older Pi versions without native MCP need an appropriate extension or terminal-browser instead. The skill discovers actual tool schemas instead of assuming tool names. See [Vessel setup](https://github.com/unmodeled-tyler/vessel-browser).

For **terminal-browser**, install it and its skill, use a supported graphical terminal, and check that `terminal-browser ls --json` works in the agent's environment. It controls a visible browser through its agent-browser-compatible CLI. Some hosts require additional sandbox permissions; the skill pauses if they are unavailable. See [terminal-browser setup](https://github.com/zenbu-labs/terminal-browser).

`browser: "auto"` prefers reachable Vessel MCP tools, then terminal-browser. An explicit browser choice must be usable. A submission setting does not override browser or host permission prompts.

Optional **resume-qna**: install it through your agent's normal skills mechanism. Job Apply reads its instructions for longer answers. If its configured resume differs and it has no supported override, Job Apply uses its writing guidance directly with the selected job-apply resume without changing resume-qna.

## Usage and recovery

```text
Use job-apply to apply to https://example.com/jobs/123.

Use job-apply with terminal-browser to apply to the URLs in ./jobs.txt.
Review each application before submitting.

Use job-apply to apply to these URLs in order and submit automatically:
https://example.com/jobs/123
https://example.com/jobs/456

Resume the interrupted job-apply batch.
```

Applications stop for missing facts, login/CAPTCHA, required agreements, or ambiguous submission outcomes. A batch advances after confirmed submission or explicit skip. Confirmed submissions are skipped unless you explicitly request reapplication. Sequential history is local to this configuration and is not a shared account-wide duplicate detector. Run one application workflow against a history file at a time.

History records URLs, status, short operational metadata, and confirmation evidence. It does not store form answers or credentials. Helpers use private file permissions and atomic writes. If submission was interrupted, the agent inspects the site before retrying; `recover --id ID` only marks the uncertain outcome and does not check the employer's site.

## Development and validation

```sh
nix develop
python3 tests/test_helper.py skill-source/job-apply
nix flake check
nix fmt
```

The helper suite uses temporary directories and no network. Open `tests/mock-application.html` in the selected browser to exercise upload, conditional required fields, a 300-character answer, confirmation, a simulated login blocker, and an ambiguous result. Use fictional information and a test resume. Exercise both review and auto modes, pause on missing sponsorship data, and repeat with resume-qna absent/matching/mismatched. This fixture never sends an application. Browser and agent integrations require a working interactive host; helper tests alone do not validate those integrations.

For module evaluation against local nixpkgs and Home Manager checkouts:

```sh
nix-instantiate --eval --strict --json tests/eval-modules.nix \
  --arg nixpkgs /path/to/nixpkgs --arg homeManager /path/to/home-manager
```

The lock file starts with the same nixpkgs revision as the reference resume-qna flake. In an unpacked workspace containing a placeholder `.git` directory, use `nix flake check path:"$PWD"` and `nix run path:"$PWD"#install`; ordinary `.` works in a real checkout.
