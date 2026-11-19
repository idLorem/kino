import os
import sys
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


if __name__ == "__main__":
    unittest.main()
