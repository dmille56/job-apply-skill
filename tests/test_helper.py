"""Behavior checks using isolated configuration/history; no external submissions."""
import concurrent.futures
import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SOURCE = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "skill-source/job-apply"
HELPER = SOURCE / "scripts/job_apply.py"


class EmailTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("job_apply", HELPER)
        self.helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.helper)

    def test_reads_pin_account_and_guards_without_shell_or_persistence(self):
        query = '-in:trash to:candidate@example.com $(touch /tmp/should-not-exist) --readonly=false'
        for args, tail in (
            (argparse.Namespace(command="email-search", query=query),
             ["gmail", "messages", "search", "--max=5", "--include-recipients", "--", query]),
            (argparse.Namespace(command="email-get", message_id="18abcdef01234567"),
             ["gmail", "get", "--format=full", "--", "18abcdef01234567"]),
        ):
            with self.subTest(command=args.command), mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch.object(self.helper.shutil, "which", return_value="/bin/gog"), \
                    mock.patch.object(self.helper.subprocess, "run") as run, \
                    contextlib.redirect_stdout(io.StringIO()) as stdout:
                run.return_value = subprocess.CompletedProcess([], 0, '{"messages": []}\n', "")
                self.helper.email(args)
                command = run.call_args.args[0]
                self.assertEqual(command, ["gog", "--account=job-apply", "--readonly", "--gmail-no-send",
                                          "--enable-commands-exact=gmail.messages.search,gmail.get",
                                          "--no-input", "--wrap-untrusted", "--json", *tail])
                self.assertNotIn("shell", run.call_args.kwargs)
                self.assertEqual(stdout.getvalue(), '{"messages": []}\n')

    def test_missing_gog_invalid_inputs_and_auth_overrides_never_run(self):
        cases = [({}, None, {"query": "subject:verification"}),
                 ({}, "/bin/gog", {"query": "  "}),
                 ({}, "/bin/gog", {"message_id": "--readonly=false"}),
                 ({"GOG_ACCESS_TOKEN": "secret"}, "/bin/gog", {"query": "test"}),
                 ({"GOG_AUTH_MODE": "adc"}, "/bin/gog", {"query": "test"})]
        for env, executable, fields in cases:
            args = argparse.Namespace(command="email-search" if "query" in fields else "email-get", **fields)
            with self.subTest(fields=fields, env=env), mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(self.helper.shutil, "which", return_value=executable), \
                    mock.patch.object(self.helper.subprocess, "run") as run:
                with self.assertRaises(ValueError):
                    self.helper.email(args)
                run.assert_not_called()

    def test_failed_reads_do_not_retry_or_expose_mail(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(self.helper.shutil, "which", return_value="/bin/gog"), \
                mock.patch.object(self.helper.subprocess, "run") as run, \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            run.return_value = subprocess.CompletedProcess([], 4, "private body", "private diagnostic")
            with self.assertRaisesRegex(ValueError, "exit 4"):
                self.helper.email(argparse.Namespace(command="email-search", query="test"))
            self.assertEqual(stdout.getvalue(), "")
            run.assert_called_once()


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="job apply test ")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.config = self.home / "config/profile.json"
        self.config.parent.mkdir()
        self.resume = self.config.parent / "resume.txt"
        self.resume.write_text("Candidate Name\nBuilt tools in Python.\n", encoding="utf-8")
        self.cfg = json.loads((SOURCE / "config.example.json").read_text())
        self.cfg.update(resume_path="resume.txt", history_path="history.json", accounts_path="accounts/accounts.json")
        self.save_config()

    def save_config(self):
        self.config.write_text(json.dumps(self.cfg), encoding="utf-8")

    def run_cli(self, *args, ok=True, data=None, config=None):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", JOB_APPLY_CONFIG="/nonexistent/config.json")
        result = subprocess.run([sys.executable, str(HELPER), "--config", str(config or self.config), *args],
                                input=data, text=True, capture_output=True, env=env)
        self.assertEqual(result.returncode, 0 if ok else 1, result.stderr or result.stdout)
        return result.stdout if ok else result.stderr

    def queue(self, *urls):
        return json.loads(self.run_cli("queue", *(urls or ("https://example.com/jobs?id=1",))))["jobs"]

    def update(self, identity, status, **metadata):
        return json.loads(self.run_cli("update", "--id", identity, "--status", status,
                                       "--data", "-", data=json.dumps(metadata)))

    def test_config_and_resume_paths(self):
        value = json.loads(self.run_cli("validate"))
        self.assertEqual(value["resume_path"], str(self.resume))
        self.assertIn("Built tools", self.run_cli("resume-text"))
        self.cfg["resume_path"] = "missing.pdf"
        self.save_config()
        self.run_cli("validate", ok=False)
        self.cfg["resume_path"] = "resume.txt"
        self.cfg["history_path"] = "resume.txt"
        self.save_config()
        self.run_cli("validate", ok=False)
        self.assertIn("Built tools", self.resume.read_text())

    def test_browser_selection(self):
        self.assertEqual(self.cfg["browser"], "playwright")
        self.cfg.pop("browser")
        self.save_config()
        self.assertEqual(json.loads(self.run_cli("validate"))["browser"], "playwright")
        for browser in ("playwright", "terminal", "auto"):
            with self.subTest(browser=browser):
                self.cfg["browser"] = browser
                self.save_config()
                self.assertEqual(json.loads(self.run_cli("validate"))["browser"], browser)
        for browser in ("vessel", "unknown"):
            with self.subTest(browser=browser):
                self.cfg["browser"] = browser
                self.save_config()
                self.assertIn("browser must be", self.run_cli("validate", ok=False))

    def test_account_config_compatibility_and_path_guards(self):
        self.cfg.pop("password_pass_entry")
        self.cfg.pop("accounts_path")
        self.save_config()
        self.run_cli("validate")
        for entry in ("", "../secret", "/secret", "-secret", "a/../b", "a//b", "a\nsecret", None):
            with self.subTest(entry=entry):
                self.cfg["password_pass_entry"] = entry
                self.save_config()
                self.run_cli("validate", ok=False)
        self.cfg["password_pass_entry"] = "job apply/shared $(literal)"
        for path in ("profile.json", "resume.txt", "history.json", "", None):
            with self.subTest(path=path):
                self.cfg["accounts_path"] = path
                self.save_config()
                self.run_cli("validate", ok=False)

    def test_account_registry_identity_progress_permissions_and_corruption(self):
        identity = ("--origin", "https://CAREERS.example.com:443/", "--tenant", "employer/site",
                    "--email", "candidate@example.com")
        self.assertIsNone(json.loads(self.run_cli("account-lookup", *identity))["account"])
        for stage in ("signup_started", "verification_pending", "ready"):
            extra = ("--password-source", "shared_pass") if stage == "signup_started" else ()
            record = json.loads(self.run_cli("account-record", *identity, "--stage", stage, *extra))["account"]
            self.assertEqual(record["stage"], stage)
            self.assertEqual(record["password_source"], "shared_pass")
        self.assertEqual(record["origin"], "https://careers.example.com")
        other = list(identity)
        other[3] = "other-employer/site"
        self.assertIsNone(json.loads(self.run_cli("account-lookup", *other))["account"])
        other[3] = "employer/site"
        other[5] = "other@example.com"
        self.assertIsNone(json.loads(self.run_cli("account-lookup", *other))["account"])
        other[5] = "CANDIDATE@example.com"
        self.assertEqual(json.loads(self.run_cli("account-lookup", *other))["account"], record)
        self.run_cli("account-record", *identity, "--stage", "ready", "--password-source", "external")
        path = self.config.parent / "accounts/accounts.json"
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertFalse((self.config.parent / "history.json").exists())
        saved = path.read_text()
        for origin in ("http://careers.example.com", "https://careers.example.com/job",
                       "https://careers.example.com?token=secret", "https://careers.example.com#secret"):
            bad = list(identity)
            bad[1] = origin
            self.run_cli("account-record", *bad, "--stage", "ready", ok=False)
            self.assertEqual(path.read_text(), saved)
        path.write_text('{"version":1,"accounts":[{"password":"not allowed"}]}')
        corrupt = path.read_text()
        self.run_cli("account-record", *identity, "--stage", "ready", ok=False)
        self.assertEqual(path.read_text(), corrupt)

    def password_module(self):
        spec = importlib.util.spec_from_file_location("job_apply_password", HELPER)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        return helper

    def test_pass_reads_only_selected_entry_and_first_line_without_writes(self):
        helper = self.password_module()
        self.cfg["password_pass_entry"] = "custom/shared $(literal)"
        self.save_config()
        before = {p: p.read_bytes() for p in self.config.parent.rglob("*") if p.is_file()}
        with mock.patch.object(helper.shutil, "which", return_value="/bin/pass"), \
                mock.patch.object(helper.subprocess, "run") as run, \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            run.return_value = subprocess.CompletedProcess([], 0, "fictional-password\nprivate notes\n", "")
            helper.password_get(argparse.Namespace(config=str(self.config)))
            self.assertEqual(stdout.getvalue(), "fictional-password\n")
            self.assertEqual(run.call_args.args[0], ["pass", "show", "custom/shared $(literal)"])
            self.assertNotIn("shell", run.call_args.kwargs)
        self.assertEqual(before, {p: p.read_bytes() for p in self.config.parent.rglob("*") if p.is_file()})

    def test_pass_failures_never_echo_secrets_or_retry(self):
        helper = self.password_module()
        for failure in (subprocess.CompletedProcess([], 1, "private body", "private diagnostic"),
                        subprocess.CompletedProcess([], 0, "\nprivate notes", ""),
                        subprocess.TimeoutExpired(["pass"], 45, output="private body", stderr="private diagnostic"),
                        OSError("private diagnostic")):
            with self.subTest(failure=type(failure).__name__), \
                    mock.patch.object(helper.shutil, "which", return_value="/bin/pass"), \
                    mock.patch.object(helper.subprocess, "run") as run, \
                    contextlib.redirect_stdout(io.StringIO()) as stdout:
                if isinstance(failure, Exception):
                    run.side_effect = failure
                else:
                    run.return_value = failure
                with self.assertRaises(ValueError) as error:
                    helper.password_get(argparse.Namespace(config=str(self.config)))
                self.assertNotIn("private", str(error.exception))
                self.assertEqual(stdout.getvalue(), "")
                run.assert_called_once()
        with mock.patch.object(helper.shutil, "which", return_value=None), \
                mock.patch.object(helper.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "requires pass"):
                helper.password_get(argparse.Namespace(config=str(self.config)))
            run.assert_not_called()

    def test_default_pass_entry_without_resume_and_cli_secret_output(self):
        self.cfg.pop("password_pass_entry")
        self.cfg["resume_path"] = None
        self.save_config()
        executable = self.home / "bin/pass"
        executable.parent.mkdir()
        executable.write_text('#!' + sys.executable + '\nimport sys\n'
                              'assert sys.argv[1:] == ["show", "job-apply/shared-password"]\n'
                              'print("fixture-password\\nprivate notes")\n')
        executable.chmod(0o700)
        with mock.patch.dict(os.environ, {"PATH": str(executable.parent)}):
            self.assertEqual(self.run_cli("password-get"), "fixture-password\n")

    def test_invalid_config_and_answers(self):
        self.config.write_text("{broken")
        self.run_cli("validate", ok=False)
        self.cfg["answers"] = [{"questions": [], "answer": "yes"}]
        self.save_config()
        self.run_cli("validate", ok=False)
        self.cfg["answers"] = [{"questions": ["Why this job?"], "answer": "I build tools.", "role": "Engineer"}]
        self.save_config()
        self.run_cli("validate")

    @unittest.skipUnless(__import__("shutil").which("pdftotext"), "Poppler is not installed")
    def test_pdf_resume_extraction(self):
        stream = b"BT /F1 12 Tf 72 720 Td (Test Candidate built Python tools.) Tj ET"
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        ]
        pdf, offsets = b"%PDF-1.4\n", [0]
        for index, obj in enumerate(objects, 1):
            offsets.append(len(pdf))
            pdf += str(index).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
        xref = len(pdf)
        pdf += b"xref\n0 6\n0000000000 65535 f \n"
        pdf += b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:])
        pdf += f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        path = self.config.parent / "resume with spaces.pdf"
        path.write_bytes(pdf)
        self.cfg["resume_path"] = path.name
        self.save_config()
        self.assertIn("Test Candidate built Python tools.", self.run_cli("resume-text"))
        path.write_bytes(b"invalid PDF")
        self.run_cli("resume-text", ok=False)

    def test_order_deduplication_aliases_and_job_queries(self):
        first, second = self.queue("https://EXAMPLE.com/jobs?id=1#form", "https://example.com/jobs?id=1",
                                   "https://example.com/jobs?id=2")
        self.assertNotEqual(first["id"], second["id"])
        self.update(first["id"], "in_progress", application_url="https://ats.example/apply/123")
        selected = self.queue("https://ats.example/apply/123", "https://example.com/jobs?id=1")
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["id"], first["id"])
        self.run_cli("update", "--id", second["id"], "--data", "-", ok=False,
                     data=json.dumps({"aliases": ["https://ats.example/apply/123"]}))
        self.assertEqual(len(json.loads(self.run_cli("history"))["jobs"]), 2)

    def test_input_file_and_bad_urls_are_atomic(self):
        path = self.home / "jobs.txt"
        path.write_text("# jobs\nhttps://example.com/1\n\nhttps://example.com/2\n")
        self.assertEqual(len(json.loads(self.run_cli("queue", "--input", str(path)))["jobs"]), 2)
        self.run_cli("queue", "https://example.com/3", "file:///private", ok=False)
        self.assertEqual(len(json.loads(self.run_cli("history"))["jobs"]), 2)

    def test_review_submission_recovery_and_reapplication(self):
        identity = self.queue()[0]["id"]
        self.run_cli("update", "--id", identity, "--status", "submitted", ok=False)
        self.update(identity, "in_progress")
        self.update(identity, "blocked", blocker="Login needed")
        self.assertEqual(self.update(identity, "in_progress").get("blocker"), None)
        self.update(identity, "awaiting_review")
        self.update(identity, "submitting")
        self.run_cli("update", "--id", identity, "--status", "in_progress", ok=False)
        recovered = json.loads(self.run_cli("recover", "--id", identity))
        self.assertEqual(recovered["status"], "uncertain")
        self.run_cli("update", "--id", identity, "--status", "in_progress", "--retry-confirmed", ok=False)
        self.run_cli("update", "--id", identity, "--status", "in_progress", "--retry-confirmed",
                     "--data", "-", data=json.dumps({"evidence": "Portal has no application; user confirmed"}))
        self.update(identity, "submitting")
        self.update(identity, "submitted", evidence="Application received: ABC123")
        self.assertEqual(self.queue()[0]["status"], "submitted")
        self.run_cli("update", "--id", identity, "--status", "pending", ok=False)
        reapplied = json.loads(self.run_cli("update", "--id", identity, "--status", "pending", "--reapply"))
        self.assertEqual(reapplied["attempt"], 2)
        self.assertEqual(reapplied["previous_attempts"][0]["evidence"], "Application received: ABC123")
        self.assertNotIn("evidence", reapplied)

    def test_concurrent_writes_and_corrupt_history(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda n: self.queue("https://example.com/jobs/" + str(n)), range(12)))
        history = self.config.parent / "history.json"
        self.assertEqual(len(json.loads(history.read_text())["jobs"]), 12)
        self.assertEqual(history.stat().st_mode & 0o777, 0o600)
        history.write_text("{partial")
        self.run_cli("queue", "https://example.com/jobs/next", ok=False)
        self.assertEqual(history.read_text(), "{partial")

    def test_install_preserves_config_history_and_unrelated_files(self):
        identity = self.queue()[0]["id"]
        self.cfg["profile"] = {"full_name": "Private Candidate"}
        self.save_config()
        previous = self.config.read_bytes()
        self.run_cli("install", "--home", str(self.home))
        dest = self.home / ".agents/skills/job-apply"
        note = dest / "personal-note.txt"
        note.write_text("preserve")
        self.run_cli("install", "--home", str(self.home))
        self.assertEqual(self.config.read_bytes(), previous)
        self.assertEqual(note.read_text(), "preserve")
        self.assertEqual(json.loads(self.run_cli("history"))["jobs"][0]["id"], identity)
        self.assertTrue((self.home / ".claude/skills/job-apply/SKILL.md").is_file())
        self.assertTrue((dest / "references/playwright-mcp.md").is_file())
        self.assertTrue((dest / "references/accounts.md").is_file())
        self.assertTrue((dest / "scripts/job_apply.py").is_file())
        self.assertTrue(os.access(dest / "scripts/run-helper.sh", os.X_OK))
        # A retired external seed must not break reinstall of existing user config.
        self.run_cli("install", "--home", str(self.home), "--seed", str(self.home / "missing-seed.json"))

    def test_seed_and_install_conflicts(self):
        new_config = self.home / "new/config.json"
        self.run_cli("init", "--seed", str(self.config), config=new_config)
        self.assertEqual(json.loads(new_config.read_text())["profile"], self.cfg["profile"])
        self.run_cli("init", config=new_config)
        dest = self.home / "unrelated"
        dest.mkdir()
        (dest / "SKILL.md").write_text("different skill")
        self.run_cli("install", "--home", str(self.home), "--skill-dir", str(dest), ok=False)
        self.assertEqual((dest / "SKILL.md").read_text(), "different skill")


if __name__ == "__main__":
    unittest.main()
