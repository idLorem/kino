import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import main


def info():
    return {"information": {"category": {
        "Stream 0": {"Type": "Video"},
        "Stream 1": {"Type": "Audio", "Description": "Дубляж", "Language": "Russian", "Codec": "AC3"},
        "Stream 2": {"Type": "Audio", "Language": "English"},
        "Stream 4": {"Type": "Subtitle", "Description": "Субтитры", "Language": "Russian"},
        "meta": {"filename": "x.mkv"},
    }}}


class VlcTracks(unittest.TestCase):
    def pc(self):
        p = main.PcPlayer.__new__(main.PcPlayer)
        p.vsel, p.vlog = {}, False
        return p

    def test_split_and_default(self):
        a, s = self.pc()._vtracks(info())
        self.assertEqual([t["id"] for t in a], [1, 2])
        self.assertEqual([t["id"] for t in s], [4])
        self.assertTrue(a[0]["sel"] and not a[1]["sel"])
        self.assertEqual(a[0]["title"], "Дубляж · Russian · AC3")

    def test_selection_follows_commands(self):
        p = self.pc()
        p.vsel = {"audio": 2, "sub": 4}
        a, s = p._vtracks(info())
        self.assertEqual([t["sel"] for t in a], [False, True])
        self.assertTrue(s[0]["sel"])

    def test_localized_keys(self):
        d = {"information": {"category": {"Поток 3": {"Тип": "Аудио"}, "Поток 5": {"Тип": "Субтитры"}}}}
        a, s = self.pc()._vtracks(d)
        self.assertEqual([t["id"] for t in a], [3])
        self.assertEqual([t["id"] for t in s], [5])


class Relay(unittest.TestCase):
    def test_cmd_only_reaches_live_target_once(self):
        r = main.TvRelay()
        r.cmd({"op": "pause", "dev": "a"})
        r.report("a", {"active": True})
        r.cmd({"op": "seek", "dev": "a"})
        r.cmd({"op": "stop", "dev": "b"})
        self.assertEqual(r.report("a", {"active": True})["cmds"], [{"op": "seek", "dev": "a"}])
        self.assertEqual(r.report("a", {"active": True})["cmds"], [])

    def test_state_and_watch(self):
        r = main.TvRelay()
        self.assertFalse(r.state()["active"])
        r.report("a", {"active": True, "pos": 5})
        self.assertEqual(r.state()["dev"], "a")
        self.assertFalse(r.report("a", {"active": True})["watch"])
        r.state(True)
        self.assertTrue(r.report("a", {"active": True})["watch"])
        r.report("a", {"active": False})
        self.assertFalse(r.state()["active"])

    def test_stale_state_expires(self):
        r = main.TvRelay()
        r.report("a", {"active": True})
        r.devs["a"]["ts"] -= 7
        self.assertFalse(r.state()["active"])


class FakeApi:
    def __init__(self, root, path):
        self.lock = threading.Lock()
        self._lock = self.lock
        self._cfg = {"srv_nopin": "", "srv_tokens": {}, "root_folders": [root]}
        self._items = {"x": {"id": "x"}}
        self.path = path

    def _view(self, it):
        return {"files": [{"path": self.path}]}

    def _srv_pin(self):
        return "123456"

    def _tv_token_ok(self, t):
        return t == "tok"

    def _tv_add_token(self, name):
        return "new"


class Server(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.root = os.path.join(self.dir, "Films")
        os.mkdir(self.root)
        self.file = os.path.join(self.root, "a.mp4")
        with open(self.file, "wb") as f:
            f.write(bytes(range(100)))
        self.srv = main.TvServer(FakeApi(self.root, self.file), 0)
        self.srv._udp_loop = lambda: None
        self.assertEqual(self.srv.start(), "")
        self.port = self.srv.httpd.server_address[1]

    def tearDown(self):
        self.srv.httpd.shutdown()
        self.srv.httpd.server_close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def get(self, path, rng=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", path, headers={"X-Kino-Token": "tok", **({"Range": rng} if rng else {})})
        r = c.getresponse()
        body = r.read()
        c.close()
        return r, body

    def post(self, path, d):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("POST", path, body=json.dumps(d))
        r = c.getresponse()
        r.read()
        c.close()
        return r

    def test_inside_rejects_escape_and_sibling(self):
        self.assertTrue(main._is_inside(self.root, self.file))
        self.assertFalse(main._is_inside(self.root, os.path.join(self.root, "..", "x.mp4")))
        self.assertFalse(main._is_inside(self.root, self.root + "2" + os.sep + "x.mp4"))
        self.assertFalse(main._is_inside(self.root, self.root))

    def test_stream_outside_root_is_404(self):
        self.srv.api.path = os.path.join(self.dir, "b.mp4")
        with open(self.srv.api.path, "wb") as f:
            f.write(b"x")
        self.assertEqual(self.get("/api/stream/x/0")[0].status, 404)

    def test_ranges(self):
        r, b = self.get("/api/stream/x/0", "bytes=10-19")
        self.assertEqual((r.status, b, r.getheader("Content-Range")), (206, bytes(range(10, 20)), "bytes 10-19/100"))
        r, b = self.get("/api/stream/x/0", "bytes=95-")
        self.assertEqual(b, bytes(range(95, 100)))
        r, b = self.get("/api/stream/x/0", "bytes=-3")
        self.assertEqual(b, bytes(range(97, 100)))
        self.assertEqual(self.get("/api/stream/x/0", "bytes=-0")[0].status, 416)
        self.assertEqual(self.get("/api/stream/x/0", "bytes=200-")[0].status, 416)
        self.assertIsNone(self.get("/api/stream/x/0")[0].getheader("Access-Control-Allow-Origin"))

    def test_pair_attempts_are_limited(self):
        codes = [self.post("/api/pair", {"pin": "000000"}).status for _ in range(5)]
        self.assertEqual(codes, [403] * 5)
        self.assertEqual(self.post("/api/pair", {"pin": "123456"}).status, 429)


class Tokens(unittest.TestCase):
    def test_kept_to_twenty_newest(self):
        a = main.Api.__new__(main.Api)
        a._lock = threading.RLock()
        a._cfg = {"srv_tokens": {"t%d" % i: {"name": "x", "ts": i} for i in range(25)}}
        a._save_cfg = lambda: None
        tok = main.Api._tv_add_token(a, "new")
        self.assertEqual(len(a._cfg["srv_tokens"]), 20)
        self.assertIn(tok, a._cfg["srv_tokens"])
        self.assertNotIn("t5", a._cfg["srv_tokens"])


class LongPoll(unittest.TestCase):
    def test_report_returns_early_on_cmd_and_pos_moves(self):
        r = main.TvRelay()
        r.state(True)
        threading.Timer(0.2, lambda: r.cmd({"op": "pause", "dev": "a"})).start()
        r.report("a", {"active": True, "pos": 1000, "dur": 9000})
        t = time.time()
        out = r.report("a", {"active": True, "pos": 1000, "dur": 9000}, 3)
        self.assertLess(time.time() - t, 1.5)
        self.assertEqual(out["cmds"][0]["op"], "pause")
        time.sleep(0.3)
        self.assertGreaterEqual(r.state()["pos"], 1250)
        r.report("a", {"active": True, "pos": 1000, "dur": 9000, "pause": True})
        time.sleep(0.2)
        self.assertEqual(r.state()["pos"], 1000)

    def test_no_hold_when_not_watched(self):
        r = main.TvRelay()
        t = time.time()
        r.report("a", {"active": True}, 3)
        self.assertLess(time.time() - t, 0.5)


if __name__ == "__main__":
    unittest.main()
