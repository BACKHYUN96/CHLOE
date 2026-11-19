import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from server import App, Server, UserError, protect_secret, HISTORY_CHAR_BUDGET, ARCHIVE_CHAR_BUDGET, recall_archive
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
        self.assertLessEqual(sum(len(r["content"]) for r in messages), HISTORY_CHAR_BUDGET)
        self.assertIn("이력범위", self.app.payload("마지막", history)["input"][1]["content"])

    def test_short_turns_do_not_drop_early_correction_after_twenty_turns(self):
        history = [{"role": "user", "content": "내 물건이 아니라 수현의 물건이야."},
                   {"role": "assistant", "content": "수현의 물건으로 정정할게."}]
        history += [{"role": role, "content": f"일상 이야기 {i}"}
                    for i in range(35) for role in ("user", "assistant")]
        sent = self.app.payload("누구 물건이었지?", history)["input"]
        self.assertEqual(sent[2:-1], history)
        self.assertNotIn("이력범위", sent[1]["content"])

    def test_archive_preserves_role_order_and_corrections_without_mutating(self):
        history = [{"role":"user","content":"초록 화분은 내 거야."},
                   {"role":"assistant","content":"사용자 물건이구나."},
                   {"role":"user","content":"정정할게. 초록 화분은 친구 유나 거야."},
                   {"role":"assistant","content":"내 물건이야."}]
        history += [{"role":role,"content":"긴 풍경 묘사 " * 400}
                    for _ in range(12) for role in ("user","assistant")]
        original = json.dumps(history)
        payload = self.app.payload("초록 화분 주인은?", history)
        reference = json.loads(payload["input"][1]["content"].split("\n",1)[1])
        archive = reference["이전대화원문발췌"]
        self.assertEqual(archive[0]["발화"][0]["content"], "초록 화분은 내 거야.")
        self.assertEqual(archive[1]["발화"][0]["role"], "user")
        self.assertIn("유나", archive[1]["발화"][0]["content"])
        self.assertEqual(archive[1]["발화"][1]["role"], "assistant")
        self.assertLessEqual(len(json.dumps(archive,ensure_ascii=False)), ARCHIVE_CHAR_BUDGET)
        self.assertEqual(json.dumps(history), original)

    def test_archive_is_session_scoped_and_recomputed_after_new_correction(self):
        first = self.app.mutate("/api/sessions", {})["id"]
        with self.app.connect() as conn:
            for session, owner in ((self.session,"유나"),(first,"정우")):
                conn.executemany("INSERT INTO messages(session,role,content,created) VALUES (?,?,?,?)",
                    [(session,"user",f"가방은 {owner} 거야.",1),(session,"assistant","응",1)] +
                    [(session,r,"풍경 "*2000,2) for _ in range(5) for r in ("user","assistant")])
        source = self.app.messages(self.session)
        sent = json.dumps(self.app.payload("가방 주인은?", source),ensure_ascii=False)
        self.assertIn("유나",sent)
        self.assertNotIn("정우",sent)
        source += [{"role":"user","content":"정정. 가방은 윤호에게 돌려줬어."},{"role":"assistant","content":"응"}]
        updated = json.dumps(self.app.payload("가방은?",source),ensure_ascii=False)
        self.assertIn("윤호에게",updated)
        self.assertEqual(App(self.temp.name).messages(self.session), self.app.messages(self.session))

    def test_archive_does_not_split_oversized_pair_or_claim_complete_recall(self):
        huge = [{"role":"user","content":"정정 " * ARCHIVE_CHAR_BUDGET},{"role":"assistant","content":"응"}]
        self.assertEqual(recall_archive("정정",huge,[]), [])
        sent = self.app.payload("정정 내용은?",huge)["input"][1]["content"]
        self.assertIn("0문답",sent)
        self.assertIn("빈 구간은 알 수 없어",sent)

    def test_long_source_is_retrieved_even_outside_concise_bank(self):
        target = "청록색 망원경은 은수가 빌려줬어. " + "주변 풍경 묘사. " * 100
        older = [{"role":"user","content":target},{"role":"assistant","content":"확인했어."}]
        older += [{"role":role,"content":f"문장 {i}. " + "하늘의 풍경. "*100}
                  for i in range(40) for role in ("user","assistant")]
        found = recall_archive("청록색 망원경을 누구에게 빌렸지?",older,[])
        self.assertTrue(any(r["발화"][0]["content"] == target for r in found))
        self.assertLessEqual(len(json.dumps(found,ensure_ascii=False)),ARCHIVE_CHAR_BUDGET)

    def test_oversized_latest_pair_does_not_include_disconnected_older_history(self):
        history = [{"role": "user", "content": "예전 사실"}, {"role": "assistant", "content": "응"},
                   {"role": "user", "content": "정정"},
                   {"role": "assistant", "content": "가" * HISTORY_CHAR_BUDGET}]
        sent = self.app.payload("지금은?", history)["input"]
        self.assertEqual(len(sent), 3)
        self.assertIn("오래된 메시지 4개", sent[1]["content"])

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
