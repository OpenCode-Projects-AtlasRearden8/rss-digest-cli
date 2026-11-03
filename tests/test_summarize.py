import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from digest.stories import Story
from digest.summarize import DEFAULT_SNIPPET_CHARS, SummaryError, snippet_for, summarize_story

CAPTURED = []


class FakeHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"data":[{"id":"llama3.2:3b"}]}')

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        CAPTURED.append(body)
        if "/fail" in self.path:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error":"boom"}')
            return
        if body.get("messages") and "no content" in body["messages"][-1]["content"]:
            payload = {"choices": [{"message": {"content": "  UNKNOWN  "}}]}
        else:
            payload = {"choices": [{"message": {"content": "  A calm summary sentence.  "}}]}
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start_server():
    server = HTTPServer(("127.0.0.1", 0), FakeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def endpoint(server):
    host, port = server.server_address
    return f"http://{host}:{port}/v1"


def long_story(summary_size=1000):
    return Story(
        title="Local LLM Runner Lands",
        link="https://example.org/paid-article",
        summary="Paywalled site. " + "Detailed paragraph%s." % (" x" * summary_size),
        feed="Paid Feed",
    )


class TestSnippetPrivacy(unittest.TestCase):
    def test_snippet_capped(self):
        snippet = snippet_for(long_story(), DEFAULT_SNIPPET_CHARS)
        self.assertLessEqual(len(snippet), DEFAULT_SNIPPET_CHARS + 1)
        self.assertNotIn("Local LLM Runner Lands", snippet)
        self.assertNotIn("https://example.org/paid-article", snippet)

    def test_snippet_never_includes_link(self):
        snippet = snippet_for(long_story())
        self.assertNotIn("example.org", snippet)


class TestSummarize(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = start_server()
        CAPTURED.clear()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_success(self):
        story = Story(title="Quiet morning budgeting", link="https://e.com/1",
                      summary="Budgeting without apps works well.", published="2026-11-03T08:00:00+00:00")
        text = summarize_story(story, endpoint(self.server), model="test-model")
        self.assertEqual(text, "A calm summary sentence.")
        self.assertEqual(CAPTURED[-1]["model"], "test-model")
        sent = CAPTURED[-1]["messages"][-1]["content"]
        self.assertIn("Quiet morning budgeting", sent)
        self.assertNotIn("https://e.com/1", sent)

    def test_unknown_means_no_summary(self):
        story = Story(title="no content", link="https://e.com/2", summary="")
        with self.assertRaises(SummaryError):
            summarize_story(story, endpoint(self.server))

    def test_http_error(self):
        story = Story(title="x", link="x", summary="y")
        with self.assertRaises(SummaryError):
            summarize_story(story, endpoint(self.server) + "/fail")

    def test_unreachable(self):
        story = Story(title="x", link="x", summary="y")
        with self.assertRaises(SummaryError):
            summarize_story(story, "http://127.0.0.1:9/v1")


if __name__ == "__main__":
    unittest.main()
