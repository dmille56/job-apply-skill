"""Behavior checks using isolated configuration/history; no external submissions."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "skill-source/job-apply"
HELPER = SOURCE / "scripts/job_apply.py"


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
        self.cfg.update(resume_path="resume.txt", history_path="history.json")
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
