import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from digest.cli import main

HERE = os.path.dirname(__file__)
FIXTURES = os.path.join(HERE, "fixtures")


def run_cli(argv):
    out, err, code = io.StringIO(), io.StringIO(), None
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
    except SystemExit as exc:  # argparse --version exits with None; errors exit with 2
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    return out.getvalue(), err.getvalue(), code


class TestCli(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="digest-cli-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write_sources(self, lines):
        path = os.path.join(self.dir, "sources.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines).strip() + "\n")
        return path

    def test_markdown_end_to_end(self):
        sources = self.write_sources([
            "# fixtures",
            "file://" + os.path.join(FIXTURES, "rss_basic.xml"),
            "file://" + os.path.join(FIXTURES, "atom_sample.xml") + " | Harbor Notes",
        ])
        out_path = os.path.join(self.dir, "digest.md")
        args = [
            "--sources", sources,
            "--format", "markdown",
            "--out", out_path,
            "--cache-dir", os.path.join(self.dir, "cache"),
        ]
        stdout, stderr, code = run_cli(args)
        self.assertEqual(code, 0, stderr)
        with open(out_path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertTrue(text.startswith("# Morning Digest"))
        self.assertIn("Arcadia Tech Stream", text)  # feed credited
        self.assertIn("Harbor Notes", text)
        self.assertIn("Gaming", text)
        # deduped: the runner story appears in both fixtures
        self.assertEqual(text.count("Local LLM Runner"), 1)
        stdout_out, err_out, code2 = run_cli(args)  # second run, cache hit
        self.assertEqual(code2, 0)
        with open(out_path, encoding="utf-8") as fh:
            self.assertIn("# Morning Digest", fh.read())

    def test_plain_format(self):
        sources = self.write_sources(["file://" + os.path.join(FIXTURES, "rdf_sample.xml")])
        stdout, stderr, code = run_cli([
            "--sources", sources, "--format", "plain",
            "--cache-dir", os.path.join(self.dir, "cache"),
        ])
        self.assertEqual(code, 0, stderr)
        self.assertIn("Morning Digest", stdout)
        self.assertIn("Vorg Science Desk", stdout)

    def test_unreachable_feed_exit_partial(self):
        sources = self.write_sources([
            "file://" + os.path.join(FIXTURES, "rss_basic.xml"),
            "https://127.0.0.1:9/feed.xml",
        ])
        stdout, stderr, code = run_cli([
            "--sources", sources, "--cache-dir", os.path.join(self.dir, "cache"),
        ])
        self.assertEqual(code, 1, stderr)
        self.assertIn("feed unreachable", stdout)

    def test_no_sources_error(self):
        stdout, stderr, code = run_cli([])
        self.assertEqual(code, 2)
        self.assertIn("no feed URLs", stderr)

    def test_offline_with_seeded_cache(self):
        # prime the cache with a real run, then go offline
        url = "file://" + os.path.join(FIXTURES, "rss_basic.xml")
        sources = self.write_sources([url])
        run_cli(["--sources", sources, "--cache-dir", os.path.join(self.dir, "cache")])
        stdout, stderr, code = run_cli([
            "--sources", sources, "--offline",
            "--cache-dir", os.path.join(self.dir, "cache"),
        ])
        self.assertEqual(code, 0, stderr)
        self.assertIn("Arcadia", stdout)

    def test_summarize_skips_gracefully(self):
        sources = self.write_sources(["file://" + os.path.join(FIXTURES, "rss_basic.xml")])
        stdout, stderr, code = run_cli([
            "--sources", sources,
            "--summarize",  # nothing listens on 11434-free port? default endpoint likely down
            "--cache-dir", os.path.join(self.dir, "cache"),
        ])
        self.assertEqual(code, 0, stderr)  # summaries failing must not break the digest

    def test_version_flag(self):
        stdout, stderr, code = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("digest", stdout + stderr)

    def test_single_url_argument(self):
        stdout, stderr, code = run_cli([
            "file://" + os.path.join(FIXTURES, "rdf_sample.xml"),
            "--cache-dir", os.path.join(self.dir, "cache"),
        ])
        self.assertEqual(code, 0, stderr)
        self.assertIn("Vorg Science Desk", stdout)


if __name__ == "__main__":
    unittest.main()
