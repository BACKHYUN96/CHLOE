import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from server import App, Server, UserError, protect_secret
import os

class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = App(self.temp.name)
        self.app.key = "sk-test-only"
        self.session = self.app.mutate("/api/sessions", {})["id"]

    def body(self, ident="request1"):
        return {"session": self.session, "message": "누가 만들었지?", "request_id": ident}

    @staticmethod
    def complete(key, payload):
        yield {"type": "response.output_text.delta", "delta": "네가 만든 "}
        yield {"type": "response.output_text.delta", "delta": "앱이라고 했어."}
        yield {"type": "response.completed", "response": {"status": "completed",
            "usage": {"input_tokens": 100, "output_tokens": 20, "input_tokens_details": {"cached_tokens": 10}}}}

    def test_memory_subjects_and_corrections_persist(self):
        one = self.app.mutate("/api/memories", {"subject": "새아라", "detail": "사용자가 만든 앱."})
        self.app.mutate("/api/memories", {"subject": "아라", "detail": "제작자 정보 미상."})
        self.app.mutate("/api/memories", {"id": one["id"], "subject": "새아라", "detail": "민지가 만들었다고 사용자가 정정함."})
        restarted = App(self.temp.name)
        prompt = restarted.payload("아라 제작자는?", [])["input"][1]["content"]
        self.assertIn("민지가", prompt)
        self.assertNotIn("사용자가 만든 앱.", prompt)
        self.assertIn("제작자 정보 미상", prompt)
        restarted.mutate("/api/memories/remove", one)
        self.assertNotIn("민지가", restarted.payload("누구?", [])["input"][1]["content"])

    def test_style_examples_and_settings_applied(self):
        self.app.mutate("/api/lessons", {"instruction": "과한 칭찬 줄이기", "example_user": "힘들어", "example_reply": "오늘 많이 지쳤구나."})
        self.app.mutate("/api/settings", {"model": "gpt-6.2-sol", "register": "polite", "nickname": "백현"})
        payload = self.app.payload("안녕", [])
        self.assertEqual(payload["reasoning"]["effort"], "low")
        self.assertFalse(payload["store"])
        self.assertIn("과한 칭찬 줄이기", payload["input"][1]["content"])
        self.assertIn("존댓말", payload["input"][1]["content"])
        self.assertEqual(payload["input"][-1]["content"], "안녕")
        with self.assertRaises(UserError):
            self.app.mutate("/api/lessons", {"instruction": "예시", "example_user": "질문만"})

    def test_complete_stream_is_atomic_and_retry_does_not_duplicate(self):
        emitted = []
        self.app.generate(self.body(), lambda e,d: emitted.append((e,d)), self.complete)
        self.assertEqual([r["role"] for r in self.app.messages(self.session)], ["user","assistant"])
        self.assertEqual(emitted[-1][0], "done")
        self.assertAlmostEqual(emitted[-1][1]["cost"], .0001905)
        with self.assertRaises(UserError):
            self.app.generate(self.body(), lambda *_: None, self.complete)
        self.assertEqual(len(self.app.messages(self.session)), 2)

    def test_incomplete_and_dropped_stream_do_not_poison_history(self):
        for kind in ("response.incomplete", "response.failed", "eof"):
            def incomplete(key, payload):
                yield {"type": "response.output_text.delta", "delta": "잘린 문장"}
                if kind != "eof":
                    yield {"type": kind}
            with self.assertRaises(UserError):
                self.app.generate(self.body(kind), lambda *_: None, incomplete)
        self.assertEqual(self.app.messages(self.session), [])
        self.assertFalse(self.app.lock.locked())

    def test_missing_key_does_not_make_a_request(self):
        self.app.key = ""
        with self.assertRaisesRegex(UserError, "API 키"):
            self.app.generate(self.body(), lambda *_: None, self.complete)

    def test_history_budget_keeps_complete_turns(self):
        history = [{"role": role, "content": str(i) + "가" * 1000} for i in range(30) for role in ("user","assistant")]
        messages = self.app.payload("마지막", history)["input"][2:-1]
        self.assertEqual(len(messages) % 2, 0)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[-1]["role"], "assistant")
        self.assertLessEqual(sum(len(r["content"]) for r in messages), 24000)

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI only")
    def test_encrypted_key_roundtrip(self):
        data = b"sk-unit-test-secret"
        sealed = protect_secret(data)
        self.assertNotIn(data, sealed)
        self.assertEqual(protect_secret(sealed, decrypt=True), data)
        self.app.mutate("/api/key", {"key": data.decode(), "persist": True})
        old = os.environ.pop("OPENAI_API_KEY", None)
        try:
            self.assertEqual(App(self.temp.name).key, data.decode())
        finally:
            if old is not None:
                os.environ["OPENAI_API_KEY"] = old
        self.app.mutate("/api/key/remove", {})
        self.assertFalse(self.app.key_path.exists())

    def test_invalid_mutations_preserve_state(self):
        with self.assertRaises(UserError):
            self.app.mutate("/api/settings", {"model": "unknown"})
        with self.assertRaises(UserError):
            self.app.mutate("/api/memories", {"id": "missing", "subject": "x", "detail": "y"})
        self.assertEqual(self.app.state()["settings"]["model"], "gpt-6.1-terra")

    def test_http_origin_token_and_key_redaction(self):
        server = Server(0, self.app)
        self.addCleanup(server.server_close)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.shutdown)
        base = "http://127.0.0.1:" + str(server.server_port)
        with urllib.request.urlopen(base + "/api/state") as result:
            raw = result.read()
            self.assertNotIn(b"sk-test-only", raw)
            state = json.loads(raw)
        for headers in ({}, {"X-Chloe-Token": state["token"], "Origin": "https://evil.example"}):
            req = urllib.request.Request(base + "/api/sessions", data=b"{}", headers=headers)
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(req)
            self.assertEqual(error.exception.code, 403)
        req = urllib.request.Request(base + "/api/sessions", data=b"{}", headers={"X-Chloe-Token": state["token"]})
        with urllib.request.urlopen(req) as result:
            self.assertIn("id", json.load(result))
        for route in ("/", "/app.js", "/style.css"):
            with urllib.request.urlopen(base + route) as result:
                self.assertEqual(result.status, 200)
                self.assertIn("frame-ancestors 'none'", result.headers["Content-Security-Policy"])

if __name__ == "__main__":
    unittest.main()
