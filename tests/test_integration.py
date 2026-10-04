"""Exercise the real CLI against isolated, disposable Papis libraries."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "papis-logger" / "scripts" / "run.py"
PAPIS = shutil.which("papis")


@unittest.skipUnless(PAPIS, "Papis must be installed to run integration tests")
class PapisIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="papis-logger-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.lib = self.root / "library"
        self.lib.mkdir()
        self.config = self.root / "config"
        self.config.write_text(
            f"[settings]\ndefault-library = test\ncache-dir = {self.root}/cache\n"
            "notes-name = notes.md\ninfo-name = info.yaml\n"
            f"\n[test]\ndir = {self.lib}\n", encoding="utf-8")
        self.env = os.environ.copy()
        self.env.update(PAPIS_CONFIG_DIR=str(self.root),
                        XDG_CACHE_HOME=str(self.root / "xdg-cache"),
                        XDG_CONFIG_HOME=str(self.root / "xdg-config"))
        self.a = self.document("alpha", title="Alpha decoding", tags=["qec"],
                               extra={"nested": [1, 2]})
        self.b = self.document("beta", title="Beta decoding", tags=["decoding"])

    def document(self, name, **data):
        folder = self.lib / name
        folder.mkdir(exist_ok=True)
        metadata = {"author": "A. Author", "year": 2026, **data}
        (folder / "info.yaml").write_text(json.dumps(metadata), encoding="utf-8")
        return folder

    def cli(self, *args, success=True):
        result = subprocess.run(
            [PAPIS, "--config", str(self.config), "--lib", "test", *map(str, args)],
            cwd=self.root, env=self.env, text=True, capture_output=True, timeout=30)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def helper(self, *args, success=True):
        result = self.cli("exec", RUNNER, *args, success=success)
        return json.loads(result.stdout)

    def metadata(self, folder):
        return self.helper("show", "--folder", folder)["metadata"]

    def note(self, folder=None, reason="Compare its decoder with my implementation.",
             event=None, kind="interest", query=None, success=True):
        reason_file = self.root / "reason.txt"
        reason_file.write_text(reason, encoding="utf-8")
        args = ["note", "--folder", folder or self.a, "--kind", kind,
                "--reason-file", reason_file, "--event-id", event or str(uuid.uuid4())]
        if query is not None:
            query_file = self.root / "query.txt"
            query_file.write_text(query, encoding="utf-8")
            args.extend(["--query-file", query_file])
        return self.helper(*args, success=success)

    def test_catalog_pagination_and_search(self):
        first = self.helper("catalog", "--limit", 1)
        self.assertEqual(first["total"], 2)
        self.assertEqual(first["next_offset"], 1)
        self.assertEqual(first["tag_counts"], {"decoding": 1, "qec": 1})
        second = self.helper("catalog", "--limit", 1, "--offset", 1)
        self.assertEqual(second["documents"][0]["folder"], str(self.b))
        self.assertIsNone(second["next_offset"])
        found = self.helper("search", "title:Alpha")
        self.assertEqual([d["folder"] for d in found["documents"]], [str(self.a)])
        self.assertEqual(self.helper("search", "zzzznonexistent")["total"], 0)
        self.assertFalse((self.a / "notes.md").exists())

    def test_tags_are_additive_idempotent_and_cached(self):
        result = self.helper("tag", "--folder", self.a, "--tag", "decoding", "--tag", "qec")
        self.assertEqual(result["added_tags"], ["decoding"])
        again = self.helper("tag", "--folder", self.a, "--tag", "decoding")
        self.assertEqual(again["added_tags"], [])
        self.assertEqual(self.metadata(self.a)["extra"], {"nested": [1, 2]})
        self.assertEqual(self.helper("search", "tags:decoding")["total"], 2)

    def test_unknown_tags_need_explicit_override_and_are_literal(self):
        tag = "{doc[title]}"
        error = self.helper("tag", "--folder", self.a, "--tag", tag, success=False)
        self.assertIn("New tags require", error["error"])
        self.assertEqual(self.metadata(self.a)["tags"], ["qec"])
        result = self.helper("tag", "--folder", self.a, "--tag", tag, "--allow-new")
        self.assertEqual(result["tags"], ["qec", tag])

    def test_existing_notes_preserved_and_event_retries_deduplicated(self):
        self.document("alpha", title="Alpha decoding", tags=["qec"], notes="research.md")
        note_path = self.a / "research.md"
        old = b"# Prior notes\r\nKeep all these bytes."
        note_path.write_bytes(old)
        event = str(uuid.uuid4())
        reason = "Test Δ and correlated noise.\nKeep `$(touch never-created)` literally."
        first = self.note(reason=reason, event=event)
        content = note_path.read_bytes()
        self.assertTrue(content.startswith(old))
        self.assertIn(reason.encode(), content)
        self.assertTrue(first["appended"])
        self.assertFalse(self.note(reason=reason, event=event)["appended"])
        self.assertEqual(content, note_path.read_bytes())
        self.assertFalse((self.root / "never-created").exists())
        self.note(reason=reason)  # A distinct occasion must survive even if its reason is identical.
        self.assertEqual(note_path.read_text().count("Why saved"), 2)

    def test_retrieval_includes_context_and_only_updates_selected_paper(self):
        self.note(kind="retrieval", query="Find correlated-noise decoding papers.")
        text = (self.a / "notes.md").read_text()
        self.assertIn("Why retrieved", text)
        self.assertIn("Find correlated-noise decoding papers.", text)
        self.assertIn("Compare its decoder", text)
        self.assertEqual(self.metadata(self.a)["notes"], "notes.md")
        self.assertFalse((self.b / "notes.md").exists())
        self.assertNotIn("notes", self.metadata(self.b))

    def test_blank_reason_or_missing_query_is_rejected(self):
        self.note(reason=" \n ", success=False)
        self.note(kind="retrieval", success=False)
        self.assertFalse((self.a / "notes.md").exists())
        self.assertNotIn("notes", self.metadata(self.a))

    def test_reused_event_with_different_content_is_rejected(self):
        event = str(uuid.uuid4())
        self.note(event=event)
        before = (self.a / "notes.md").read_bytes()
        result = self.note(event=event, reason="A different purpose.", success=False)
        self.assertIn("different content", result["error"])
        self.assertEqual(before, (self.a / "notes.md").read_bytes())

    def test_configured_filename_and_template(self):
        template = self.root / "template.md"
        template.write_text("# {doc[title]}\n\nExisting template text.\n")
        config = self.config.read_text().replace("notes-name = notes.md",
                    f"notes-name = journal.md\nnotes-template = {template}")
        self.config.write_text(config)
        result = self.note()
        self.assertEqual(result["notes"], str(self.a / "journal.md"))
        content = (self.a / "journal.md").read_text()
        self.assertTrue(content.startswith("# Alpha decoding\n\nExisting template text."))
        self.assertEqual(self.metadata(self.a)["notes"], "journal.md")

    def test_tex_prose_is_commented(self):
        self.document("alpha", title="Alpha decoding", notes="notes.tex")
        original = "\\section{Existing}\n"
        (self.a / "notes.tex").write_text(original)
        self.note(reason="A 50% gain in a_b.\n\\end{document}")
        appended = (self.a / "notes.tex").read_text()[len(original):]
        self.assertTrue(all(not line or line.startswith("% ") for line in appended.splitlines()))
        self.assertIn("% A 50% gain in a_b.", appended)

    def test_ambiguous_notes_and_legacy_tags_are_not_rewritten(self):
        self.document("alpha", title="Alpha decoding", notes=["a.md", "b.md"], tags="qec decoding")
        catalog = self.helper("catalog")
        self.assertEqual(len(catalog["warnings"]), 1)
        self.note(success=False)
        self.helper("tag", "--folder", self.a, "--tag", "decoding", success=False)
        metadata = self.metadata(self.a)
        self.assertEqual(metadata["notes"], ["a.md", "b.md"])
        self.assertEqual(metadata["tags"], "qec decoding")

    def test_notes_outside_document_and_symlinks_are_rejected(self):
        outside = self.root / "outside.md"
        outside.write_text("Do not alter.")
        self.document("alpha", title="Alpha decoding", notes="../../outside.md")
        self.note(success=False)
        self.document("alpha", title="Alpha decoding", notes="linked.md")
        (self.a / "linked.md").symlink_to(outside)
        self.note(success=False)
        self.assertEqual(outside.read_text(), "Do not alter.")

    def test_unrelated_folder_cannot_be_annotated(self):
        outside = self.root / "unrelated"
        outside.mkdir()
        (outside / "info.yaml").write_text('title: Other library\n')
        self.note(folder=outside, success=False)
        self.assertFalse((outside / "notes.md").exists())

    def test_custom_info_filename(self):
        for folder in (self.a, self.b):
            (folder / "info.yaml").rename(folder / "metadata.yaml")
        self.config.write_text(self.config.read_text().replace(
            "info-name = info.yaml", "info-name = metadata.yaml"))
        self.note()
        self.helper("tag", "--folder", self.a, "--tag", "decoding")
        self.assertEqual(self.metadata(self.a)["notes"], "notes.md")
        self.assertFalse((self.a / "info.yaml").exists())

    def test_offline_native_import_then_tag_and_note(self):
        metadata = self.root / "import.yaml"
        metadata.write_text('title: Gamma decoder\nauthor: B. Author\nyear: 2025\n')
        self.cli("add", "--batch", "--no-confirm", "--no-edit", "--no-open", "--no-git",
                 "--no-move", "--no-link", "--no-auto-doctor", "--no-fetch-citations",
                 "--no-download-files", "--from", "yaml", metadata)
        results = self.helper("search", "title:Gamma")["documents"]
        self.assertEqual(len(results), 1)
        folder = Path(results[0]["folder"])
        self.helper("tag", "--folder", folder, "--tag", "decoding")
        self.note(folder=folder)
        self.assertEqual(self.metadata(folder)["tags"], ["decoding"])
        self.assertTrue((folder / "notes.md").is_file())
        self.assertEqual(self.helper("catalog")["total"], 3)


class InstallerTests(unittest.TestCase):
    def test_both_hosts_conflict_and_backup(self):
        with tempfile.TemporaryDirectory(prefix="papis-logger-install-test-") as tmp:
            project = Path(tmp)
            command = [sys.executable, str(ROOT / "install.py"), "both", "--project", tmp]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            for host in (".agents", ".claude"):
                destination = project / host / "skills" / "papis-logger"
                self.assertEqual((destination / "SKILL.md").read_bytes(),
                                 (ROOT / "papis-logger" / "SKILL.md").read_bytes())
                (destination / "local-change.txt").write_text("Keep in backup.")
            conflict = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(conflict.returncode, 0)
            update = subprocess.run(command + ["--replace"], capture_output=True, text=True)
            self.assertEqual(update.returncode, 0, update.stderr)
            for host in (".agents", ".claude"):
                backups = list((project / host / "skill-backups").iterdir())
                self.assertEqual(len(backups), 1)
                self.assertEqual((backups[0] / "local-change.txt").read_text(), "Keep in backup.")
                self.assertFalse((project / host / "skills" / "papis-logger" / "local-change.txt").exists())


if __name__ == "__main__":
    unittest.main()
