#!/usr/bin/env python3
"""Job application bookkeeping, shared passwords via pass, and read-only email via gog."""

import argparse
import contextlib
import csv
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parent.parent
STATUSES = {"pending", "in_progress", "awaiting_review", "blocked", "submitting",
            "submitted", "uncertain", "skipped"}
METADATA = {"employer", "role", "application_url", "blocker", "evidence", "note", "aliases",
            "contact_name", "contact_email_phone", "location", "type", "mode", "pay"}
CSV_COLUMNS = ["Company", "Position", "Link", "Name of Contact", "Email/Phone",
               "Location", "Type", "Mode", "Pay", "Sent", "Date (applied)"]
ACCOUNT_STAGES = {"signup_started", "verification_pending", "ready"}
PASSWORD_SOURCES = {"unknown", "shared_pass", "external"}


def fail(message):
    raise ValueError(message)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def output(value):
    print(json.dumps(value, indent=2, ensure_ascii=False))


def read_json(path):
    if str(path) == "-":
        return json.load(sys.stdin)
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix=".job-apply-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextlib.contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def config_path(args):
    return Path(args.config or os.environ.get("JOB_APPLY_CONFIG") or
                "~/.config/job-apply/config.json").expanduser().absolute()


def resolve_path(value, base):
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


def validate_config(cfg, path, require_resume=True):
    if not isinstance(cfg, dict) or type(cfg.get("version")) is not int or cfg["version"] != 1:
        fail("Configuration must be an object with version 1")
    allowed = {"version", "resume_path", "resume_json", "browser", "submission_mode", "history_path", "profile", "answers",
               "password_pass_entry", "accounts_path", "csv_path",
               "remember_approved_answers", "allow_account_creation"}
    if set(cfg) - allowed:
        fail("Unknown configuration keys: " + ", ".join(sorted(set(cfg) - allowed)))
    if cfg.get("browser", "playwright") not in {"auto", "playwright", "terminal"}:
        fail("browser must be playwright, terminal, or auto (Playwright MCP); replace legacy vessel with playwright")
    if cfg.get("submission_mode", "review") not in {"review", "auto"}:
        fail("submission_mode must be review or auto")
    for setting in ("remember_approved_answers", "allow_account_creation"):
        if type(cfg.get(setting, False)) is not bool:
            fail(setting + " must be a boolean")
    resume = cfg.get("resume_path")
    resume_json = cfg.get("resume_json")
    if resume_json is not None and (not isinstance(resume_json, str) or not resume_json.strip()):
        fail("resume_json must be a nonempty path string or null")
    if resume is not None and (not isinstance(resume, str) or not resume.strip()):
        fail("resume_path must be a nonempty string or null")
    if require_resume:
        if not resume:
            fail("Set resume_path in " + str(path))
        resolved = resolve_path(resume, path.parent)
        if not resolved.is_file() or not os.access(resolved, os.R_OK):
            fail("Resume is not a readable file: " + str(resolved))
        if resolved.suffix.lower() not in {".pdf", ".txt", ".md"}:
            fail("Resume must be a PDF or UTF-8 .txt/.md file")
    history = cfg.get("history_path", "~/.local/state/job-apply/history.json")
    if not isinstance(history, str) or not history.strip():
        fail("history_path must be a nonempty string")
    history_path = resolve_path(history, path.parent).resolve()
    protected = {path.resolve()}
    if resume:
        protected.add(resolve_path(resume, path.parent).resolve())
    resume_json_path = None
    if resume_json:
        resume_json_path = resolve_path(resume_json, path.parent).resolve()
        if resume_json_path in protected:
            fail("resume_json must differ from the config and resume paths")
        if require_resume and (not resume_json_path.is_file() or not os.access(resume_json_path, os.R_OK)):
            fail("Structured resume is not a readable file: " + str(resume_json_path))
        if require_resume:
            try:
                structured_resume = read_json(resume_json_path)
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                fail("Structured resume is not valid UTF-8 JSON: " + str(error))
            if not isinstance(structured_resume, dict):
                fail("Structured resume JSON must contain an object")
        protected.add(resume_json_path)
    if history_path in protected:
        fail("history_path must differ from the config and resume paths")
    entry = cfg.get("password_pass_entry", "job-apply/shared-password")
    if (not isinstance(entry, str) or not entry or entry.startswith(("/", "-")) or
            any(part in {"", ".", ".."} for part in entry.split("/")) or
            any(ord(c) < 32 or ord(c) == 127 for c in entry)):
        fail("password_pass_entry must be a relative pass entry without traversal or control characters")
    accounts = cfg.get("accounts_path", "~/.local/state/job-apply/accounts.json")
    if not isinstance(accounts, str) or not accounts.strip():
        fail("accounts_path must be a nonempty string")
    if resolve_path(accounts, path.parent).resolve() in protected | {history_path}:
        fail("accounts_path must differ from the config, resume, and history paths")
    csv_value = cfg.get("csv_path", str(history_path.with_name("applications.csv")))
    if not isinstance(csv_value, str) or not csv_value.strip():
        fail("csv_path must be a nonempty string")
    if resolve_path(csv_value, path.parent).resolve() in protected | {
            history_path, resolve_path(accounts, path.parent).resolve()}:
        fail("csv_path must differ from the config, resume, history, and accounts paths")
    profile = cfg.get("profile", {})
    if not isinstance(profile, dict):
        fail("profile must be an object")
    validate_answers(cfg.get("answers", []))
    return cfg


def validate_answers(answers):
    if not isinstance(answers, list):
        fail("answers must be an array")
    for item in answers:
        if not isinstance(item, dict) or set(item) - {"questions", "answer", "employer", "role"}:
            fail("Each answer must contain questions, answer, and optional employer/role")
        questions = item.get("questions")
        if not isinstance(questions, list) or not questions or any(
                not isinstance(q, str) or not q.strip() for q in questions):
            fail("Each answer needs a nonempty array of question strings")
        if not isinstance(item.get("answer"), str) or not item["answer"].strip():
            fail("Each answer needs nonempty answer text")
        for scope in ("employer", "role"):
            if scope in item and (not isinstance(item[scope], str) or not item[scope].strip()):
                fail(scope + " must be a nonempty string when supplied")


def remember_answers(args):
    """Persist reviewed records; semantic generalization belongs to the agent."""
    incoming = read_json(args.data)
    validate_answers(incoming)
    path = config_path(args)
    with locked(path):
        _, cfg = load_config(args)
        answers = cfg.setdefault("answers", [])

        def normalized(text):
            return " ".join(text.split()).casefold()

        def scope(record):
            return tuple(normalized(record.get(key, "")) for key in ("employer", "role"))

        for record in incoming:
            questions = {normalized(q) for q in record["questions"]}
            matches = [item for item in answers if scope(item) == scope(record)
                       and questions & {normalized(q) for q in item["questions"]}]
            if any(item["answer"].strip() != record["answer"].strip() for item in matches):
                fail("Conflicting saved answer; review and explicitly correct the existing record before saving")
            if matches:
                target = matches[0]
                known = {normalized(q) for q in target["questions"]}
                for item in [*matches[1:], record]:
                    for question in item["questions"]:
                        if normalized(question) not in known:
                            target["questions"].append(question)
                            known.add(normalized(question))
                for duplicate in matches[1:]:
                    answers.remove(duplicate)
            else:
                cleaned = dict(record, questions=list(dict.fromkeys(record["questions"])))
                answers.append(cleaned)
        validate_config(cfg, path, require_resume=False)
        atomic_json(path, cfg)
    output({"saved": True, "records_received": len(incoming)})


def load_config(args, require_resume=False):
    path = config_path(args)
    if not path.is_file():
        fail("Configuration missing: " + str(path) + "; run init first")
    cfg = validate_config(read_json(path), path, require_resume)
    return path, cfg


def normalize(url):
    if not isinstance(url, str) or any(c.isspace() for c in url):
        fail("Expected an HTTP(S) URL without whitespace")
    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        fail("Expected an HTTP(S) URL without embedded credentials: " + url)
    _ = parts.port  # Validate invalid/out-of-range ports.
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))


def validate_history(data):
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("jobs"), list):
        fail("Invalid history: expected version 1 and jobs array; refusing to overwrite")
    ids, urls = set(), set()
    for job in data["jobs"]:
        if not isinstance(job, dict) or not isinstance(job.get("id"), str) or job["id"] in ids:
            fail("Invalid history: missing or duplicate job ID")
        ids.add(job["id"])
        if job.get("status") not in STATUSES or not isinstance(job.get("aliases"), list):
            fail("Invalid history status or aliases")
        owned = {normalize(job["url"])} | {normalize(x) for x in job["aliases"]}
        if owned & urls:
            fail("History contains aliases shared by different jobs; inspect it manually")
        urls.update(owned)
    return data


@contextlib.contextmanager
def history(args, write=True):
    path, cfg = load_config(args)
    target = resolve_path(cfg.get("history_path", "~/.local/state/job-apply/history.json"), path.parent)
    with locked(target):
        data = validate_history(read_json(target)) if target.exists() else {"version": 1, "jobs": []}
        yield data
        if write:
            validate_history(data)
            atomic_json(target, data)


def csv_path(cfg, base):
    default = resolve_path(cfg.get("history_path", "~/.local/state/job-apply/history.json"), base).with_name("applications.csv")
    return resolve_path(cfg.get("csv_path", str(default)), base)


def write_csv(target, data):
    """Rebuild the generated report from confirmed attempts; replace it atomically."""
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix=".job-apply-", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(CSV_COLUMNS)
            for job in data["jobs"]:
                for attempt in [*job.get("previous_attempts", []), job]:
                    if attempt["status"] != "submitted":
                        continue
                    stamp = attempt.get("submitted_at", attempt["updated_at"])
                    date = datetime.datetime.fromisoformat(stamp).date().isoformat()
                    writer.writerow([attempt.get(key, "") for key in (
                        "employer", "role", "url", "contact_name", "contact_email_phone",
                        "location", "type", "mode", "pay")] + ["Yes", date])
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def export_csv(args, report=True):
    path, cfg = load_config(args)
    target = csv_path(cfg, path.parent)
    # Use the history lock for both automatic and explicit exports, so an older
    # snapshot cannot overwrite a newer report.
    with history(args, write=False) as data:
        write_csv(target, data)
    if report:
        output({"csv_path": str(target)})


def init(args):
    path = config_path(args)
    with locked(path):
        if path.exists():
            output({"config_path": str(path), "created": False})
            return
        cfg = read_json(args.seed) if args.seed else read_json(ROOT / "config.example.json")
        validate_config(cfg, path, False)
        atomic_json(path, cfg)
    output({"config_path": str(path), "created": True})


def queue(args):
    urls = list(args.urls)
    if args.input:
        source = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
        urls.extend(line.strip() for line in source.splitlines() if line.strip() and not line.lstrip().startswith("#"))
    urls = list(dict.fromkeys(normalize(url) for url in urls))
    if not urls:
        fail("Supply at least one job URL")
    with history(args) as data:
        lookup = {url: job for job in data["jobs"] for url in {job["url"], *job["aliases"]}}
        selected = []
        for url in urls:
            job = lookup.get(url)
            if job is None:
                stamp = now()
                job = {"id": hashlib.sha256(url.encode()).hexdigest()[:16], "url": url,
                       "aliases": [], "status": "pending", "created_at": stamp,
                       "updated_at": stamp, "attempt": 1}
                data["jobs"].append(job)
                lookup[url] = job
            if job["id"] not in selected:
                selected.append(job["id"])
        result = {"selected_ids": selected, "jobs": [lookup[url] for url in urls
                  if lookup[url]["id"] in selected]}
        result["jobs"] = list({j["id"]: j for j in result["jobs"]}.values())
    output(result)


def find_job(data, identity):
    for job in data["jobs"]:
        if job["id"] == identity:
            return job
    fail("Unknown job ID: " + identity)


def update(args):
    meta = read_json(args.data) if args.data else {}
    if not isinstance(meta, dict) or set(meta) - METADATA:
        fail("Unsupported metadata keys; allowed: " + ", ".join(sorted(METADATA)))
    for key, value in meta.items():
        if key == "aliases":
            if not isinstance(value, list):
                fail("aliases must be a URL array")
            meta[key] = list(dict.fromkeys(normalize(url) for url in value))
        elif not isinstance(value, str) or len(value) > 2000:
            fail(key + " must be a string of at most 2000 characters")
    if meta.get("application_url"):
        meta["application_url"] = normalize(meta["application_url"])
        meta.setdefault("aliases", []).append(meta["application_url"])
    with history(args) as data:
        job = find_job(data, args.id)
        old, new = job["status"], args.status or job["status"]
        if args.reapply:
            if old != "submitted" or new != "pending":
                fail("--reapply requires a submitted job and --status pending")
            job.setdefault("previous_attempts", []).append({k: v for k, v in job.items()
                                                          if k != "previous_attempts"})
            job["attempt"] += 1
            for key in ("evidence", "blocker", "note", "submitted_at"):
                job.pop(key, None)
        elif old == "submitted":
            fail("Submitted records are immutable; use --reapply for an explicitly requested reapplication")
        elif old == "submitting" and new not in {"submitting", "submitted", "uncertain"}:
            fail("Submission may have happened; mark uncertain and inspect before retrying")
        elif old == "uncertain" and new not in {"uncertain", "submitted"}:
            if new != "in_progress" or not args.retry_confirmed or not meta.get("evidence", "").strip():
                fail("Uncertain outcome: supply --retry-confirmed, evidence of non-submission, and --status in_progress")
        elif old == "skipped" and new not in {"skipped", "pending"}:
            fail("Reset skipped jobs to pending before resuming")
        if new == "submitted" and (old not in {"submitting", "uncertain"} or
                                   not meta.get("evidence", "").strip()):
            fail("Confirmed submission requires submitting/uncertain state and new evidence")
        if new == "submitting" and old not in {"in_progress", "awaiting_review", "submitting"}:
            fail("Fill/review the application before recording submission intent")
        aliases = list(dict.fromkeys(job["aliases"] + meta.pop("aliases", [])))
        for other in data["jobs"]:
            if other["id"] != job["id"] and set(aliases) & {other["url"], *other["aliases"]}:
                fail("Alias belongs to job " + other["id"] + "; inspect duplicate before applying")
        job.update(meta)
        job.update(status=new, aliases=aliases, updated_at=now())
        if new == "submitted":
            job["submitted_at"] = job["updated_at"]
        if new != "blocked":
            job.pop("blocker", None)
        result = dict(job)
    if new == "submitted":
        try:
            export_csv(args, report=False)
        except (ValueError, OSError, KeyError, TypeError) as error:
            fail("Submission saved in history, but CSV export failed: " + str(error) +
                 "; run export-csv to retry the report without resubmitting the application")
    output(result)


def recover(args):
    with history(args) as data:
        job = find_job(data, args.id)
        if job["status"] == "submitting":
            job.update(status="uncertain", updated_at=now(),
                       note="Interrupted submission; inspect site before retrying")
        result = dict(job)
    output(result)


def password_get(args):
    """Read just the configured entry; never persist it or echo pass diagnostics."""
    _, cfg = load_config(args)
    if not shutil.which("pass"):
        fail("Shared password requires pass; see references/accounts.md")
    try:
        result = subprocess.run(["pass", "show", cfg.get("password_pass_entry", "job-apply/shared-password")],
                                capture_output=True, text=True, timeout=45)
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        fail("Unable to read shared password from pass; check the entry and GPG unlock. No fallback attempted.")
    if result.returncode:
        fail("Unable to read shared password from pass; check the entry and GPG unlock. No fallback attempted.")
    password = result.stdout.split("\n", 1)[0].removesuffix("\r")
    if not password.strip() or any(ord(c) < 32 or ord(c) == 127 for c in password):
        fail("The pass entry must have a nonempty password on its first line without control characters")
    print(password)


def account_identity(origin, tenant, email):
    parts = urlsplit(normalize(origin))
    if parts.scheme != "https" or parts.path != "/" or parts.query or parts.fragment:
        fail("Account origin must be an HTTPS origin without a path, query, or fragment")
    if "#" in origin:
        fail("Account origin must not contain a fragment")
    for name, value in (("tenant", tenant), ("email", email)):
        if (not isinstance(value, str) or not value.strip() or value != value.strip() or
                len(value) > 254 or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            fail("Account " + name + " must be a nonempty string of at most 254 characters without control characters")
    if "@" not in email or any(c.isspace() for c in email):
        fail("Account email must be a candidate email address")
    return (urlunsplit((parts.scheme, parts.netloc.removesuffix(":443"), "", "", "")),
            tenant, email)


def account_key(record):
    return record["origin"], record["tenant"], record["email"].casefold()


def validate_accounts(data):
    if (not isinstance(data, dict) or set(data) != {"version", "accounts"} or
            type(data["version"]) is not int or data["version"] != 1 or not isinstance(data["accounts"], list)):
        fail("Invalid account registry; refusing to overwrite")
    seen = set()
    for record in data["accounts"]:
        if not isinstance(record, dict) or set(record) != {
                "origin", "tenant", "email", "stage", "password_source", "updated_at"}:
            fail("Invalid account record; only non-secret account metadata is supported")
        identity = account_identity(record["origin"], record["tenant"], record["email"])
        if (identity != (record["origin"], record["tenant"], record["email"]) or
                record["stage"] not in ACCOUNT_STAGES or record["password_source"] not in PASSWORD_SOURCES or
                not isinstance(record["updated_at"], str)):
            fail("Invalid account record")
        key = account_key(record)
        if key in seen:
            fail("Duplicate account identity; inspect registry before continuing")
        seen.add(key)
    return data


def account(args):
    path, cfg = load_config(args)
    origin, tenant, email_address = account_identity(args.origin, args.tenant, args.email)
    key = (origin, tenant, email_address.casefold())
    target = resolve_path(cfg.get("accounts_path", "~/.local/state/job-apply/accounts.json"), path.parent)
    with locked(target):
        data = validate_accounts(read_json(target)) if target.exists() else {"version": 1, "accounts": []}
        record = next((r for r in data["accounts"] if account_key(r) == key), None)
        if args.command == "account-record":
            if record is None:
                record = {"origin": origin, "tenant": tenant, "email": email_address,
                          "password_source": "unknown"}
                data["accounts"].append(record)
            record.update(stage=args.stage, updated_at=now())
            if args.password_source:
                record["password_source"] = args.password_source
            validate_accounts(data)
            atomic_json(target, data)
        output({"account": record})


def email(args):
    """Expose only two reads; never accept gog flags or a different account."""
    if not shutil.which("gog"):
        fail("Email verification requires gogcli (gog) and its job-apply account alias; see references/email.md")
    if os.environ.get("GOG_ACCESS_TOKEN") or os.environ.get("GOG_AUTH_MODE", "oauth") != "oauth":
        fail("Email verification requires stored OAuth for the job-apply alias; remove direct-token/ADC overrides")
    command = ["gog", "--account=job-apply", "--readonly", "--gmail-no-send",
               "--enable-commands-exact=gmail.messages.search,gmail.get",
               "--no-input", "--wrap-untrusted", "--json"]
    if args.command == "email-search":
        if not args.query.strip():
            fail("Email search query must not be empty")
        command += ["gmail", "messages", "search", "--max=5", "--include-recipients", "--", args.query]
    else:
        if not args.message_id or not all(c in "0123456789abcdefABCDEF" for c in args.message_id):
            fail("Expected a Gmail message ID from email-search (hexadecimal)")
        command += ["gmail", "get", "--format=full", "--", args.message_id]
    # No shell, passthrough options, persistence, or retries. Old gog versions fail closed.
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode:
        fail("gog email read failed; check the job-apply alias, read-only authorization, and gog version "
             "(exit " + str(result.returncode) + "). No fallback or settings changes attempted.")
    print(result.stdout, end="")


def install(args):
    home = Path(args.home).expanduser().absolute() if args.home else Path.home()
    destinations = [Path(x).expanduser().absolute() for x in args.skill_dir] if args.skill_dir else [
        home / ".agents/skills/job-apply", home / ".claude/skills/job-apply"]
    for dest in destinations:
        if dest.resolve() == ROOT:
            fail("Installation destination must differ from source")
        existing = dest / "SKILL.md"
        if dest.is_symlink() or (dest.exists() and not existing.is_file()):
            fail("Refusing to overwrite unrelated destination: " + str(dest))
        if existing.exists() and "\nname: job-apply\n" not in existing.read_text(encoding="utf-8"):
            fail("Destination contains a different skill: " + str(dest))
        # Preflight every file before copying; never follow a preexisting destination symlink.
        sources = [p for p in ROOT.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
        for source in sources:
            target = dest / source.relative_to(ROOT)
            for component in [target, *list(target.parents)]:
                if component.is_symlink():
                    fail("Refusing symlink destination: " + str(component))
                if component == dest:
                    break
        dest.mkdir(parents=True, exist_ok=True)
        for source in sources:
            target = dest / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            # Replace known package files rather than writing into an old read-only inode.
            fd, temp = tempfile.mkstemp(prefix=".job-apply-", dir=target.parent)
            os.close(fd)
            try:
                shutil.copyfile(source, temp)
                os.chmod(temp, 0o644 | (source.stat().st_mode & 0o111))
                os.replace(temp, target)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
    if not args.config and not os.environ.get("JOB_APPLY_CONFIG"):
        args.config = str(home / ".config/job-apply/config.json")
    init(args)
    output({"installed": [str(d) for d in destinations]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="Configuration JSON; overrides JOB_APPLY_CONFIG")
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "install"):
        sub = subs.add_parser(name)
        sub.add_argument("--seed", help="External JSON used only when config is absent")
        if name == "install":
            sub.add_argument("--home", help="Target home (no privilege/ownership changes)")
            sub.add_argument("--skill-dir", action="append", default=[], help="Repeat for multiple destinations")
    subs.add_parser("validate")
    subs.add_parser("resume-text")
    subs.add_parser("history")
    subs.add_parser("export-csv", help="Rebuild the submitted applications CSV from history")
    subs.add_parser("password-get", help="Print the shared password's first line from the configured pass entry (secret output)")
    sub = subs.add_parser("remember-answers", help="Save reviewed reusable answer records without overwriting conflicts")
    sub.add_argument("--data", required=True, help="JSON answer array; - for stdin")
    for name in ("account-lookup", "account-record"):
        sub = subs.add_parser(name, help="Look up or record non-secret portal account progress")
        sub.add_argument("--origin", required=True, help="HTTPS portal origin only")
        sub.add_argument("--tenant", required=True, help="Observed employer tenant/site identifier, not a job URL")
        sub.add_argument("--email", required=True)
        if name == "account-record":
            sub.add_argument("--stage", required=True, choices=sorted(ACCOUNT_STAGES))
            sub.add_argument("--password-source", choices=sorted(PASSWORD_SOURCES))
    sub = subs.add_parser("email-search", help="Search verification email through the job-apply gog alias (read-only)")
    sub.add_argument("query", help="Narrow Gmail query for the current application")
    sub = subs.add_parser("email-get", help="Read one Gmail message through the job-apply gog alias (read-only)")
    sub.add_argument("message_id")
    sub = subs.add_parser("queue")
    sub.add_argument("urls", nargs="*")
    sub.add_argument("--input", help="One URL per line; - for stdin")
    sub = subs.add_parser("update")
    sub.add_argument("--id", required=True)
    sub.add_argument("--status", choices=sorted(STATUSES))
    sub.add_argument("--data", help="Metadata JSON file; - for stdin")
    sub.add_argument("--reapply", action="store_true")
    sub.add_argument("--retry-confirmed", action="store_true")
    sub = subs.add_parser("recover")
    sub.add_argument("--id", required=True)
    args = parser.parse_args()
    try:
        if args.command in {"init", "install", "queue", "update", "recover"}:
            globals()[args.command](args)
        elif args.command in {"email-search", "email-get"}:
            email(args)
        elif args.command == "password-get":
            password_get(args)
        elif args.command == "remember-answers":
            remember_answers(args)
        elif args.command == "export-csv":
            export_csv(args)
        elif args.command in {"account-lookup", "account-record"}:
            account(args)
        elif args.command == "history":
            with history(args, write=False) as data:
                output(data)
        else:
            path, cfg = load_config(args, require_resume=True)
            resume = resolve_path(cfg["resume_path"], path.parent)
            if args.command == "validate":
                output({"valid": True, "config_path": str(path), "resume_path": str(resume),
                        "resume_json_path": str(resolve_path(cfg["resume_json"], path.parent)) if cfg.get("resume_json") else None,
                        "history_path": str(resolve_path(cfg.get("history_path",
                        "~/.local/state/job-apply/history.json"), path.parent)),
                        "csv_path": str(csv_path(cfg, path.parent)),
                        "browser": cfg.get("browser", "playwright"), "submission_mode": cfg.get("submission_mode", "review"),
                        "remember_approved_answers": cfg.get("remember_approved_answers", False),
                        "allow_account_creation": cfg.get("allow_account_creation", False)})
            elif resume.suffix.lower() == ".pdf":
                if not shutil.which("pdftotext"):
                    fail("PDF extraction requires pdftotext (Poppler); use the Nix package or install Poppler")
                result = subprocess.run(["pdftotext", "-layout", str(resume), "-"],
                                        check=True, capture_output=True, text=True)
                if not result.stdout.strip():
                    fail("PDF contains no extractable text; provide a text resume or OCR it explicitly")
                print(result.stdout, end="")
            else:
                content = resume.read_text(encoding="utf-8")
                if not content.strip():
                    fail("Resume is empty")
                print(content, end="")
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print("job-apply: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
