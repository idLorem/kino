import os
import sys
import re
import json
import time
import base64
import hashlib
import threading
import difflib
import functools
import subprocess
import webbrowser
import traceback
import shutil
import tempfile
import socket
import hmac
import secrets
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

import requests
from html import escape as html_escape, unescape
from urllib.parse import quote, urlparse, parse_qs

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

webview = None

APP_NAME = "Kino"
WINDOW_TITLE = "Kino"
APP_VERSION = "1.0.3"
MATCH_V = 2
UPDATE_REPO = "idLorem/kino"


def _writable(d):
    try:
        os.makedirs(d, exist_ok=True)
        t = os.path.join(d, ".w_test")
        with open(t, "w") as f:
            f.write("1")
        os.remove(t)
        return True
    except Exception:
        return False


def _app_dir():
    base = os.environ.get("KINO_DATA_DIR") or (os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__)))
    if _writable(base):
        return base
    alt = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
    os.makedirs(alt, exist_ok=True)
    return alt


APP_DIR = _app_dir()
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
CACHE_PATH = os.path.join(APP_DIR, "metadata_cache.json")
WATCHLIST_PATH = os.path.join(APP_DIR, "watchlist.json")
WATCHED_PATH = os.path.join(APP_DIR, "watched.json")
PROGRESS_PATH = os.path.join(APP_DIR, "progress.json")
POSTER_DIR = os.path.join(APP_DIR, "poster_cache")
PALETTE_PATH = os.path.join(APP_DIR, "palettes.json")
BG_PATH = os.path.join(APP_DIR, "background.jpg")
LOG_PATH = os.path.join(APP_DIR, "kino.log")

DEFAULT_CONFIG = {
    "root_folders": [],
    "player_mode": "system",
    "player_path": "",
    "kp_api_key": "",
    "tmdb_api_key": "",
    "omdb_api_key": "",
    "lb_user": "",
    "fallback_source": "none",
    "bg_mode": "default",
    "bg_color": "#0a0a0a",
    "bg_dim": "55",
    "bg_blur": "0",
    "bg_ver": "0",
    "auto_update": "1",
    "tray_close": "1",
    "autostart": "0",
    "card_rating": "imdb",
    "sort": "added",
    "shortcut_done": "",
    "lang": "ru",
    "lang_set": "",
    "poster_size": "176",
    "watched": {},
    "hidden": {},
    "pinned": {},
    "srv_on": "",
    "srv_port": "8765",
    "srv_pin": "",
    "srv_nopin": "",
    "srv_tokens": {},
}


def _log(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except Exception:
        pass


def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except Exception:
        return default


def _save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts"}
SKIP_DIRS = {"$recycle.bin", "system volume information", "sample", "samples", "@eadir", ".git", "$windows.~bt"}
SAMPLE_RE = re.compile(r"(?i)(?:^|[\W_])samples?(?:[\W_]|$)")
POSTER_NAMES = ["poster.jpg", "folder.jpg", "cover.jpg", "poster.jpeg", "folder.jpeg", "cover.jpeg",
                "poster.png", "folder.png", "cover.png"]

QUALITY_RE = re.compile(
    r"(?i)(?<![^\W_])(?:2160p|1080[pi]|720p|576p|480p|360p|4k|uhd|fhd|hdr10\+?|hdr|dolby\s?vision|sdr|"
    r"web[\s-]?dl|web[\s-]?rip|webrip|webdl|bd[\s-]?rip|bdrip|bd[\s-]?remux|bdremux|brrip|blu[\s-]?ray|remux|"
    r"dvd[\s-]?rip|dvdrip|dvd[\s-]?scr|dvd[\s-]?[59]|dvd|hd[\s-]?dvd|bd[\s-]?(?:25|50)|custom|hdtv|hdtvrip|tvrip|satrip|hdrip|camrip|telesync|"
    r"ntsc|pal|uncut|criterion|theatrical|director'?s[\s-]?cut|"
    r"x264|x265|h[\s.]?264|h[\s.]?265|hevc|avc|xvid|divx|aac|ac3|eac3|dts|truehd|atmos|ddp?\d?|"
    r"10[\s-]?bit|8[\s-]?bit|cd\s?\d|"
    r"lostfilm|hdrezka|rezka|newstudio|kubik|alexfilm|baibako|jaskier|amedia|coldfilm|kerob|ideafilm|rutracker|"
    r"rus|eng|ukr|multi|dub|dubbed|mvo|dvo|avo|nf|amzn|dsnp|hmax|atvp|repack|proper|extended|unrated|"
    r"remastered|imax|internal|"
    r"дубляж\w*|озвучк\w*|многоголос\w*|одноголос\w*|двухголос\w*|закадров\w*|субтитры|лицензия|пифагор|гоблин)"
    r"(?![^\W_])"
)
YEAR_RE = re.compile(r"(?<![^\W_])(?:19[2-9]\d|20[0-4]\d)(?![^\W_])")

RE_SE = re.compile(r"(?i)(?<![^\W_])s(\d{1,2})[\s\-]?e(\d{1,3})(?!\d)")
RE_NXM = re.compile(r"(?<!\d)(\d{1,2})x(\d{2,3})(?![\dxp])")
RE_SEASON_A = re.compile(r"(?i)(?<![^\W_])(?:season|сезон)\s*(\d{1,2})(?!\d)")
RE_SEASON_B = re.compile(r"(?i)(?<![^\W_])(\d{1,2})\s*(?:сезон|season)")
RE_EP_A = re.compile(r"(?i)(?<![^\W_])(?:серия|серии|эпизод|episode|ep|эп)\s*(\d{1,3})(?!\d)")
RE_EP_B = re.compile(r"(?i)(?<![^\W_])(\d{1,3})\s*(?:серия|серии|эпизод|episode|эп)(?![^\W_])")
RE_DASH_EP = re.compile(r"\s-\s+(\d{2,3})(?:v\d)?(?=\s|$)")
RE_LEAD_NUM = re.compile(r"^\s*(\d{1,3})\s*(?:[-–)]|\.\s)\s*\S")
SEASON_DIR_RE = re.compile(r"(?i)^\s*(?:(?:season|сезон)[\s._-]*(\d{1,2})\b|s(\d{1,2})\b|(\d{1,2})[\s._-]*(?:сезон|season)\b)")


def norm(s):
    return re.sub(r"[^0-9a-zа-я]+", "", (s or "").lower().replace("ё", "е"))


def season_from_dirname(name):
    m = SEASON_DIR_RE.match(name or "")
    if not m:
        return None
    for g in m.groups():
        if g:
            return int(g)
    return None


def find_episode(s):
    m = RE_SE.search(s)
    if m:
        return int(m.group(1)), int(m.group(2)), m.start()
    m = RE_NXM.search(s)
    if m:
        return int(m.group(1)), int(m.group(2)), m.start()
    sm = RE_SEASON_A.search(s) or RE_SEASON_B.search(s)
    em = RE_EP_A.search(s) or RE_EP_B.search(s)
    if sm or em:
        starts = [x.start() for x in (sm, em) if x]
        return (int(sm.group(1)) if sm else None), (int(em.group(1)) if em else None), min(starts)
    m = RE_DASH_EP.search(s)
    if m:
        return None, int(m.group(1)), m.start()
    return None


def _strip_brackets(m):
    txt = m.group(0)
    if re.fullmatch(r"\(\s*\d{1,3}\s*\)", txt):
        return txt
    return " "


def parse_name(text):
    s = text or ""
    year_paren = None
    m = re.search(r"[\(\[]\s*((?:19|20)\d{2})\s*[\)\]]", s)
    if m:
        year_paren = int(m.group(1))
    s = re.sub(r"\[[^\]]*\]|\([^)]*\)|\{[^}]*\}", _strip_brackets, s)
    s = re.sub(r"[._]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    ep = find_episode(s)
    cuts = []
    if ep:
        cuts.append(ep[2])
    qm = QUALITY_RE.search(s)
    if qm and qm.start() > 0:
        cuts.append(qm.start())
    cut = min(cuts) if cuts else len(s)

    year = year_paren
    title_end = cut
    if year is None:
        cands = [mm for mm in YEAR_RE.finditer(s) if 0 < mm.start() < cut]
        if cands:
            mm = cands[-1]
            year = int(mm.group(0))
            title_end = mm.start()
        else:
            later = [mm for mm in YEAR_RE.finditer(s) if mm.start() >= cut and mm.start() > 0]
            if later:
                year = int(later[0].group(0))
    title = s[:title_end]
    title = re.sub(r"\s+", " ", title).strip(" -–—,.:;|/+~")
    parts = [p.strip(" -–—,.:;") for p in re.split(r"\s+[/|]\s+", title)]
    parts = [p for p in parts if p]
    return {
        "title": parts[0] if parts else "",
        "alts": parts[1:3],
        "year": year,
        "season": ep[0] if ep else None,
        "episode": ep[1] if ep else None,
        "has_ep": bool(ep),
    }


def _same(a, b):
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def _folder_chain(d, root):
    out = []
    cur = d
    while cur and not _same(cur, root):
        out.append(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return out


def folder_title(d, root):
    for cur in _folder_chain(d, root):
        name = os.path.basename(cur)
        if season_from_dirname(name) is not None:
            continue
        info = parse_name(name)
        if info["title"]:
            return info
    return None


def season_from_folders(d, root):
    for cur in _folder_chain(d, root):
        s = season_from_dirname(os.path.basename(cur))
        if s is not None:
            return s
    return None


def _disc_kind(dp):
    b = os.path.basename(dp).upper()
    return "DVD" if b == "VIDEO_TS" else ("Blu-ray" if b == "BDMV" else None)


def _disc_record(dp, kind, root):
    files = []
    for d2, _dn, fn2 in os.walk(dp):
        for f in fn2:
            p = os.path.join(d2, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            files.append((p, st.st_size, st.st_mtime))
    if not files:
        return None
    if kind == "DVD":
        up = [(p, sz) for p, sz, _ in files if p.upper().endswith(".VOB")]
        if sum(sz for _, sz in up) < 50 * 1024 * 1024:
            return None
        ifo = [p for p, _, _ in files if os.path.basename(p).upper() == "VIDEO_TS.IFO"]
        titles = sorted(p for p, _ in up if re.search(r"VTS_\d\d_[1-9]\.VOB$", p.upper()))
        main = ifo[0] if ifo else (titles[0] if titles else up[0][0])
    else:
        m2 = [(p, sz) for p, sz, _ in files if p.lower().endswith(".m2ts")]
        if not m2 or max(sz for _, sz in m2) < 200 * 1024 * 1024:
            return None
        main = max(m2, key=lambda x: x[1])[0]
    parent = os.path.dirname(dp)
    stem = os.path.basename(parent.rstrip("\\/")) or os.path.basename(root.rstrip("\\/")) or kind
    return {"path": main, "dir": parent, "root": root, "name": "%s [%s]" % (stem, kind), "stem": stem,
            "size": sum(sz for _, sz, _ in files), "mtime": max(m for _, _, m in files),
            "info": parse_name(stem), "num_ep": None, "fmt": kind,
            "extra": [p for p, _, _ in files if p != main]}


def _walk_root(root, recs, seen):
    root = os.path.normpath(root)
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d.lower() not in SKIP_DIRS and not d.startswith(".")]
        kind = _disc_kind(dp)
        if kind:
            dns[:] = []
            sk = os.path.normcase(os.path.normpath(dp))
            if sk not in seen:
                seen.add(sk)
                rec = _disc_record(dp, kind, root)
                if rec:
                    recs.append(rec)
            continue
        for fn in fns:
            if fn.startswith("."):
                continue
            stem, ext = os.path.splitext(fn)
            if ext.lower() not in VIDEO_EXT:
                continue
            if SAMPLE_RE.search(stem):
                continue
            path = os.path.join(dp, fn)
            sk = os.path.normcase(os.path.normpath(path))
            if sk in seen:
                continue
            seen.add(sk)
            try:
                st = os.stat(path)
            except OSError:
                continue
            if getattr(st, "st_file_attributes", 0) & 0x6:
                continue
            info = parse_name(stem)
            num_ep = None
            if not info["has_ep"]:
                if re.fullmatch(r"\d{1,3}", info["title"] or ""):
                    num_ep = int(info["title"])
                else:
                    lm = RE_LEAD_NUM.match(stem)
                    if lm:
                        num_ep = int(lm.group(1))
            recs.append({"path": path, "dir": dp, "root": root, "name": fn, "stem": stem, "size": st.st_size,
                         "mtime": st.st_mtime, "info": info, "num_ep": num_ep})

def scan_library(roots):
    if isinstance(roots, str):
        roots = [roots]
    recs, seen = [], set()
    for rt in roots:
        _walk_root(rt, recs, seen)

    num_count = {}
    for r in recs:
        if r["num_ep"] is not None:
            num_count[r["dir"]] = num_count.get(r["dir"], 0) + 1

    groups = {}
    for r in recs:
        info = r["info"]
        d = r["dir"]
        root = r["root"]
        title, year, alts = info["title"], info["year"], info["alts"]
        season, episode = info["season"], info["episode"]
        is_ep = info["has_ep"]
        numeric_ep = (not is_ep) and r["num_ep"] is not None and num_count.get(d, 0) >= 2
        if numeric_ep:
            is_ep = True
            episode = r["num_ep"]
            title = ""
        if not title or len(norm(title)) < 2:
            fi = folder_title(d, root)
            if fi:
                title, alts = fi["title"], fi["alts"]
                year = year or fi["year"]
        elif year is None:
            fi = folder_title(d, root)
            if fi and fi["year"] and norm(fi["title"]) == norm(title):
                year = fi["year"]
        if not title:
            title = re.sub(r"[._]+", " ", r["stem"]).strip() or r["stem"]
        if is_ep and season is None:
            season = season_from_folders(d, root) or 1
        kind = "series" if is_ep else "movie"
        key = ("s|" + norm(title)) if is_ep else ("m|%s|%s" % (norm(title), year or ""))
        g = groups.get(key)
        if g is None:
            g = {"id": hashlib.md5(key.encode("utf-8")).hexdigest()[:12], "kind": kind, "title": title,
                 "alts": alts, "year": year, "files": [], "added": 0, "poster": None, "dirs": set()}
            groups[key] = g
        if g["year"] is None and year:
            g["year"] = year
        fr = {"path": r["path"], "name": r["name"], "size": r["size"],
              "season": season if is_ep else None, "episode": episode if is_ep else None}
        if r.get("fmt"):
            fr["fmt"] = r["fmt"]
            fr["extra"] = r.get("extra") or []
        g["files"].append(fr)
        g["added"] = max(g["added"], r["mtime"])
        g["dirs"].add((d, root))

    listing_cache = {}

    def find_poster(d):
        if d not in listing_cache:
            try:
                listing_cache[d] = {n.lower(): n for n in os.listdir(d)}
            except OSError:
                listing_cache[d] = {}
        names = listing_cache[d]
        for p in POSTER_NAMES:
            if p in names:
                return os.path.join(d, names[p])
        return None

    items = []
    for g in groups.values():
        for d, root in sorted(g["dirs"]):
            cands = []
            if not _same(d, root):
                cands.append(d)
                parent = os.path.dirname(d)
                if g["kind"] == "series" and not _same(parent, root) and parent != d:
                    cands.append(parent)
            for c in cands:
                p = find_poster(c)
                if p:
                    g["poster"] = p
                    break
            if g["poster"]:
                break
        g.pop("dirs", None)
        items.append(g)
    items.sort(key=lambda x: x["title"].lower())
    return items, {f["path"] for it in items for f in it["files"]}


KP_BASE = "https://kinopoiskapiunofficial.tech"
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG = "https://image.tmdb.org/t/p/"

COUNTRIES = {
    "US": "США", "RU": "Россия", "GB": "Великобритания", "FR": "Франция", "DE": "Германия", "JP": "Япония",
    "KR": "Южная Корея", "CN": "Китай", "IT": "Италия", "ES": "Испания", "CA": "Канада", "AU": "Австралия",
    "IN": "Индия", "SE": "Швеция", "DK": "Дания", "NO": "Норвегия", "PL": "Польша", "UA": "Украина",
    "BY": "Беларусь", "TR": "Турция", "MX": "Мексика", "BR": "Бразилия", "SU": "СССР", "HK": "Гонконг",
    "IE": "Ирландия", "NL": "Нидерланды", "BE": "Бельгия", "FI": "Финляндия", "CZ": "Чехия", "AT": "Австрия",
    "CH": "Швейцария", "NZ": "Новая Зеландия", "AR": "Аргентина", "TH": "Таиланд", "TW": "Тайвань",
}


WEB_GAPS = {"omdbapi.com": 0.3, "letterboxd.com": 2.0, "media-imdb.com": 0.8, "imdb.com": 1.2}

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/131.0.0.0 Safari/537.36")
LB_BASE = "https://letterboxd.com"
IMDB_DS_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"
IMDB_DS_MAX_AGE = 14 * 86400
_IMDB_DS_LOCK = threading.Lock()
IMDB_SUGGEST = "https://v3.sg.media-imdb.com/suggestion/x/"

GENRES_EN = {
    "action": "боевик", "adventure": "приключения", "animation": "мультфильм", "comedy": "комедия",
    "crime": "криминал", "documentary": "документальный", "drama": "драма", "family": "семейный",
    "fantasy": "фэнтези", "history": "история", "horror": "ужасы", "music": "музыка", "mystery": "детектив",
    "romance": "мелодрама", "science fiction": "фантастика", "thriller": "триллер", "tv movie": "телефильм",
    "war": "военный", "western": "вестерн",
}
COUNTRIES_EN = {
    "russia": "Россия", "usa": "США", "united states": "США", "uk": "Великобритания",
    "united kingdom": "Великобритания", "france": "Франция", "germany": "Германия", "japan": "Япония",
    "south korea": "Южная Корея", "china": "Китай", "italy": "Италия", "spain": "Испания", "canada": "Канада",
    "australia": "Австралия", "india": "Индия", "sweden": "Швеция", "denmark": "Дания", "norway": "Норвегия",
    "poland": "Польша", "ukraine": "Украина", "belarus": "Беларусь", "turkey": "Турция", "mexico": "Мексика",
    "brazil": "Бразилия", "ussr": "СССР", "soviet union": "СССР", "hong kong": "Гонконг", "ireland": "Ирландия",
    "netherlands": "Нидерланды", "belgium": "Бельгия", "finland": "Финляндия", "czech republic": "Чехия",
    "austria": "Австрия", "switzerland": "Швейцария", "new zealand": "Новая Зеландия", "argentina": "Аргентина",
    "georgia": "Грузия", "kazakhstan": "Казахстан", "latvia": "Латвия", "lithuania": "Литва", "estonia": "Эстония",
}


def tr_genre(g):
    return GENRES_EN.get((g or "").strip().lower(), g)


def tr_country(c):
    return COUNTRIES_EN.get((c or "").strip().lower(), c)


_TR_MULTI = [
    ("shch", "щ"), ("sch", "щ"), ("dzh", "дж"),
    ("zh", "ж"), ("kh", "х"), ("ts", "ц"), ("ch", "ч"), ("sh", "ш"),
    ("yu", "ю"), ("ya", "я"), ("yo", "е"), ("ye", "е"),
    ("ju", "ю"), ("ja", "я"), ("jo", "е"),
    ("yy", "ый"), ("iy", "ий"), ("ey", "ей"), ("ay", "ай"), ("oy", "ой"), ("uy", "уй"),
]
_TR_SINGLE = {
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "х", "i": "и", "j": "й",
    "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "q": "к", "r": "р", "s": "с", "t": "т",
    "u": "у", "v": "в", "w": "в", "x": "кс", "y": "ы", "z": "з",
}
_EN_STOP = {"the", "of", "and", "with", "for", "from", "you", "your", "an", "to", "in", "on", "my",
            "is", "are", "it", "by", "at", "or", "his", "her", "dead", "love", "man", "night", "day"}


def _is_lat(ch):
    return "a" <= ch <= "z"


def translit_to_cyr(text, alt=False):
    s_ = (text or "").lower()
    out = []
    i, n = 0, len(s_)
    while i < n:
        ch = s_[i]
        if ch == "'":
            if out and "а" <= out[-1][-1:] <= "я":
                out.append("ь")
            i += 1
            continue
        if not _is_lat(ch):
            out.append(ch)
            i += 1
            continue
        word_start = i == 0 or not _is_lat(s_[i - 1])
        done = False
        for lat, cyr in _TR_MULTI:
            if s_.startswith(lat, i):
                out.append("тс" if (alt and lat == "ts") else cyr)
                i += len(lat)
                done = True
                break
        if done:
            continue
        if ch == "c":
            nxt = s_[i + 1] if i + 1 < n else ""
            out.append("ц" if nxt in ("e", "i", "y") else "к")
        elif ch == "e" and alt and word_start and i + 1 < n and _is_lat(s_[i + 1]):
            out.append("э")
        elif ch == "y":
            nxt_lat = i + 1 < n and _is_lat(s_[i + 1])
            prev = s_[i - 1] if i > 0 else ""
            if alt and not nxt_lat and prev and _is_lat(prev) and prev not in "aeiouy":
                out.append("ый")
            else:
                out.append("ы")
        else:
            out.append(_TR_SINGLE.get(ch, ch))
        i += 1
    res = "".join(out)
    return res[:1].upper() + res[1:] if res else res


def translit_variants(text):
    a, b = translit_to_cyr(text), translit_to_cyr(text, alt=True)
    return [a] if a == b else [a, b]


def looks_translit(t):
    if not t or re.search(r"[А-Яа-яЁё]", t) or not re.search(r"[A-Za-z]", t):
        return False
    low = t.lower()
    if re.search(r"[wq]", low):
        return False
    return not any(w in _EN_STOP for w in re.findall(r"[a-z']+", low))


def title_sim(names, qs):
    best = 0.0
    for n_ in names:
        n_ = norm(n_)
        if not n_:
            continue
        for q in qs:
            q = norm(q)
            if not q:
                continue
            if n_ == q:
                sc = 1.0
            elif q in n_ or n_ in q:
                sc = 0.6 + 0.4 * min(len(q), len(n_)) / max(len(q), len(n_))
            else:
                sc = difflib.SequenceMatcher(None, n_, q).ratio()
            best = max(best, sc)
    return best


def _upscale_imdb(url, width):
    if not url:
        return None
    m = re.match(r"^(.*?)\._V1_.*?(\.[A-Za-z]+)$", url)
    return "%s._V1_UX%d_%s" % (m.group(1), width, m.group(2)) if m else url


_IMDB_SKIP = {"tvepisode", "videogame", "podcastseries", "podcastepisode", "musicvideo"}


def parse_imdb_suggest(data):
    res = []
    for d in ((data or {}).get("d") or []):
        iid = d.get("id") or ""
        if not iid.startswith("tt"):
            continue
        qid = (d.get("qid") or "").lower()
        if qid in _IMDB_SKIP:
            continue
        img = (d.get("i") or {}).get("imageUrl")
        y = d.get("y")
        res.append({
            "source": "imdb", "ext_id": iid, "titleRu": d.get("l"), "titleOrig": d.get("l"),
            "year": y if isinstance(y, int) else None, "duration": None,
            "ratingKp": None, "ratingImdb": None, "ratingTmdb": None,
            "genres": [], "countries": [], "description": "",
            "type": "series" if qid in ("tvseries", "tvminiseries") else "movie", "qid": qid,
            "poster": _upscale_imdb(img, 500), "posterPreview": img, "stars": d.get("s") or "",
            "url": "https://www.imdb.com/title/%s/" % iid, "imdbId": iid,
        })
    return res


def _html_meta(html, key):
    for m in re.finditer(r"<meta\b[^>]*>", html, re.I):
        tag = m.group(0)
        if re.search(r"""(?:property|name)\s*=\s*["']%s["']""" % re.escape(key), tag, re.I):
            cm = re.search(r'content\s*=\s*"([^"]*)"|content\s*=\s*\'([^\']*)\'', tag, re.I)
            if cm:
                return unescape(cm.group(1) if cm.group(1) is not None else cm.group(2))
    return None


def _jsonld(html):
    blocks = re.findall(r"""<script[^>]+type=["']application/ld\+json["'][^>]*>(.*?)</script>""", html, re.S | re.I)
    for b in blocks:
        b = re.sub(r"^\s*/\*.*?\*/", "", b, count=1, flags=re.S)
        b = re.sub(r"/\*.*?\*/\s*$", "", b, count=1, flags=re.S)
        try:
            d = json.loads(b.strip())
        except ValueError:
            continue
        if isinstance(d, list):
            d = next((x for x in d if isinstance(x, dict) and x.get("@type") in ("Movie", "TVSeries")), None) or {}
        if isinstance(d, dict) and d:
            return d
    return {}


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def parse_lb_film(html, url=""):
    if not html:
        return None
    ld = _jsonld(html)
    og_title = _html_meta(html, "og:title") or ""
    name = ld.get("name") if isinstance(ld.get("name"), str) else ""
    name = (name or re.sub(r"\s*\((?:19|20)\d{2}\)\s*$", "", og_title)).strip()
    if not name:
        return None
    year = None
    rel = ld.get("releasedEvent")
    if isinstance(rel, list) and rel:
        rel = rel[0]
    cand = (rel.get("startDate") if isinstance(rel, dict) else None) or ld.get("datePublished")
    m = re.search(r"((?:19|20)\d{2})", str(cand or ""))
    if not m:
        m = re.search(r"\(((?:19|20)\d{2})\)", og_title)
    if m:
        year = int(m.group(1))
    rating = None
    ag = ld.get("aggregateRating")
    if isinstance(ag, dict):
        try:
            rating = round(float(ag.get("ratingValue")), 1)
        except (TypeError, ValueError):
            rating = None
    if rating is None:
        mm = re.search(r"([0-5](?:\.\d+)?)\s+out of\s+5", _html_meta(html, "twitter:data2") or "")
        if mm:
            rating = round(float(mm.group(1)), 1)
    if rating is not None and not (0 < rating <= 5):
        rating = None
    genres = [g for g in _as_list(ld.get("genre")) if isinstance(g, str)]
    countries = []
    for c in _as_list(ld.get("countryOfOrigin")):
        nm = c.get("name") if isinstance(c, dict) else c
        if isinstance(nm, str) and nm:
            countries.append(nm)
    img = next((x for x in _as_list(ld.get("image")) if isinstance(x, str)), None) or _html_meta(html, "og:image")
    desc = (_html_meta(html, "og:description") or "").strip()
    tm = re.search(r"""<div[^>]+class=["'][^"']*\btruncate\b[^"']*["'][^>]*>(.*?)</div>""", html, re.S | re.I)
    if tm:
        full = unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", tm.group(1)))).strip()
        if len(full) >= len(desc.rstrip("…. ")):
            desc = full or desc
    directors = []
    for d in _as_list(ld.get("director")):
        nm = d.get("name") if isinstance(d, dict) else d
        if isinstance(nm, str) and nm.strip():
            directors.append(nm.strip())
    om = re.search(r"""class=["'][^"']*\boriginalname\b[^"']*["'][^>]*>\s*(?:<[^>]+>\s*)*([^<]+)""", html, re.I)
    orig = unescape(om.group(1)).strip() if om else None
    cm = re.search(r"""<link[^>]+rel=["']canonical["'][^>]*href=["']([^"']+)""", html, re.I)
    page_url = (cm.group(1) if cm else None) or _html_meta(html, "og:url") or url
    sm = re.search(r"/film/([^/]+)/", page_url or url or "")
    if not sm:
        return None
    rt = re.search(r"text-footer[^>]*>[^<]*?(\d{2,3})(?:&nbsp;|\s| )*mins?", html, re.S)
    im = re.search(r"imdb\.com/title/(tt\d+)", html)
    return {"slug": sm.group(1), "name": name, "year": year, "rating": rating, "genres": genres,
            "countries": countries, "poster": img, "description": desc,
            "runtime": int(rt.group(1)) if rt else None, "imdbId": im.group(1) if im else None,
            "directors": directors, "origTitle": orig,
            "url": "%s/film/%s/" % (LB_BASE, sm.group(1))}


def parse_lb_search(html):
    res, seen = [], set()

    def add(slug, title, year):
        if slug and slug not in seen:
            seen.add(slug)
            res.append({"slug": slug, "title": title or slug.replace("-", " ").title(), "year": year})

    if BeautifulSoup is not None:
        try:
            soup = BeautifulSoup(html, "html.parser")
            lis = soup.select("ul.results > li") or soup.select("li.search-result") or soup.select("li[class*=search-result]")
            for li in lis:
                raw = str(li)
                sm = re.search(r"/film/([a-z0-9\-_.]+)/", raw)
                if not sm:
                    continue
                tnode = li.select_one("h2 a, .film-title-wrapper a, .headline-2 a")
                title = tnode.get_text(" ", strip=True) if tnode else None
                if not title:
                    img = li.find("img", alt=True)
                    title = img["alt"].strip() if img else None
                ym = re.search(r"/films/year/((?:19|20)\d{2})/", raw)
                if not ym:
                    mnode = li.select_one(".metadata, small")
                    ym = re.search(r"((?:19|20)\d{2})", mnode.get_text(" ", strip=True)) if mnode else None
                add(sm.group(1), title, int(ym.group(1)) if ym else None)
        except Exception:
            res, seen = [], set()
    if not res:
        for slug in re.findall(r"""href=["']/film/([a-z0-9\-_.]+)/["']""", html or ""):
            add(slug, None, None)
    return res


def lb_nick(v):
    v = str(v or "").strip()
    m = re.search(r"letterboxd\.com/([^/?#\s]+)", v, re.I)
    if m:
        v = m.group(1)
    v = v.strip("/@ ")
    return v if re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", v) else ""


def parse_lb_profile(html, nick):
    html = html or ""
    img = None
    for cand in re.findall(r"""<img[^>]+src=["']([^"']+)["']""", html, re.I):
        if "/avatar/" in cand or "avatar" in cand.lower():
            img = unescape(cand)
            break
    if not img:
        og = _html_meta(html, "og:image") or ""
        img = og if "avatar" in og.lower() else None
    films = None
    m = re.search(r"href=[\"']/%s/films/[\"'][^>]*>.*?class=[\"'][^\"']*\bvalue\b[^\"']*[\"'][^>]*>\s*([\d,.\s\u00a0]+?)\s*<" % re.escape(nick), html, re.I | re.S)
    if not m:
        m = re.search(r"href=[\"']/%s/films/[\"'][^>]*>\s*(?:<[^>]+>\s*)*([\d][\d,.\s\u00a0]*)" % re.escape(nick), html, re.I)
    if m:
        digits = re.sub(r"\D", "", m.group(1))
        films = int(digits) if digits else None
    name = None
    m = re.search(r"""class=["'][^"']*\bdisplayname\b[^"']*["'][^>]*>\s*([^<]+?)\s*<""", html, re.I)
    if m:
        name = unescape(m.group(1)).strip()
    if not name:
        og = _html_meta(html, "og:title") or ""
        og = re.sub(r"\s*[•\-–|]\s*Letterboxd\s*$", "", og).strip()
        og = re.sub(r"(?:[\u2019']s)?\s+(?:profile|watchlist|films|diary|lists|reviews|likes|network|stats|activity)$", "", og, flags=re.I).strip()
        name = og or None
    return {"avatar": img, "films": films, "name": name}


def parse_lb_watchlist(html):
    films, seen = [], set()

    def add(slug, name, year):
        if not slug or slug in seen:
            return
        seen.add(slug)
        name = unescape(name or "").strip()
        m = re.match(r"^(.*?)\s*\(((?:18|19|20)\d{2})\)\s*$", name)
        if m:
            name, year = m.group(1).strip(), year or int(m.group(2))
        films.append({"slug": slug, "title": name or slug.replace("-", " ").title(), "year": year})

    for tag in re.findall(r"<(?:div|li|a)\b[^>]*\bdata-(?:item|film)-slug=[^>]*>", html or "", re.I):
        sm = re.search(r"data-(?:item|film)-slug=[\"']/?(?:film/)?([a-z0-9\-_.]+?)/?[\"']", tag, re.I)
        nm = re.search(r"data-(?:item|film)-name=[\"']([^\"']*)[\"']", tag, re.I)
        ym = re.search(r"data-film-release-year=[\"'](\d{4})[\"']", tag, re.I)
        if sm:
            add(sm.group(1), nm.group(1) if nm else "", int(ym.group(1)) if ym else None)
    if not films:
        for m in re.finditer(r"<a[^>]+href=[\"']/film/([a-z0-9\-_.]+)/[\"'][^>]*>(.*?)</a>", html or "", re.I | re.S):
            alt = re.search(r"alt=[\"']([^\"']+)[\"']", m.group(2))
            add(m.group(1), alt.group(1) if alt else "", None)
    nxt = bool(re.search(r"""class=["'][^"']*\bnext\b[^"']*["'][^>]*href=["'][^"']*/page/\d+/|href=["'][^"']*/watchlist/page/\d+/["'][^>]*class=["'][^"']*\bnext\b""", html or "", re.I))
    return films, nxt


class ApiError(Exception):
    def __init__(self, code, message=""):
        super().__init__(message or code)
        self.code = code


POSTER_SOURCES = ("kp", "imdb", "lb")


def _descs_of(meta):
    d = meta.get("descs")
    if not isinstance(d, dict):
        d = {}
        meta["descs"] = d
        own = {"kp": "kp", "imdb": "imdb", "lb": "lb"}.get(meta.get("source"))
        if own and meta.get("description"):
            d[own] = meta["description"]
    return d


def parse_imdb_plot(html):
    if not html:
        return None
    for blob in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            ld = json.loads(blob)
        except ValueError:
            continue
        if isinstance(ld, dict) and ld.get("description"):
            return unescape(re.sub(r"<[^>]+>", "", str(ld["description"]))).strip() or None
    return None


def split_mixed(title):
    words = re.findall(r"[^\s]+", title or "")
    cyr = [w for w in words if re.search(r"[А-Яа-яЁё]", w)]
    lat = [w for w in words if re.search(r"[A-Za-z]", w) and not re.search(r"[А-Яа-яЁё]", w)]
    if cyr and lat and len(cyr) + len(lat) <= len(words):
        return [" ".join(cyr), " ".join(lat)]
    return []


_OMDB_EN_RU = None


def _omdb_ru(values, kind):
    global _OMDB_EN_RU
    if _OMDB_EN_RU is None:
        _OMDB_EN_RU = {}
        m = re.search(r"const EN_DICT=(\{.*?\});\nconst CYR", HTML, re.S)
        if m:
            for ru, en in json.loads(m.group(1)).items():
                _OMDB_EN_RU.setdefault(en.lower(), ru)
    out = []
    for v in values:
        v = v.strip()
        if v and v.lower() not in ("n/a",):
            out.append(_OMDB_EN_RU.get(v.lower(), v))
    return out


def _omdb_minutes(s):
    m = re.search(r"(\d+)", s or "")
    return int(m.group(1)) if m else None


def _posters_of(meta):
    p = meta.get("posters")
    if not isinstance(p, dict):
        p = {}
        meta["posters"] = p
        own = {"kp": "kp", "imdb": "imdb", "lb": "lb"}.get(meta.get("source"))
        if own and meta.get("poster"):
            p[own] = {"poster": meta["poster"], "preview": meta.get("posterPreview") or meta["poster"]}
    return p


def _clip_get():
    import ctypes
    from ctypes import wintypes
    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    u32.OpenClipboard.argtypes = [wintypes.HWND]
    u32.OpenClipboard.restype = wintypes.BOOL
    u32.GetClipboardData.argtypes = [wintypes.UINT]
    u32.GetClipboardData.restype = wintypes.HANDLE
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    for _ in range(15):
        if u32.OpenClipboard(None):
            break
        time.sleep(0.02)
    else:
        return ""
    try:
        h = u32.GetClipboardData(13)
        if not h:
            return ""
        p = k32.GlobalLock(h)
        if not p:
            return ""
        try:
            return ctypes.wstring_at(p)
        finally:
            k32.GlobalUnlock(h)
    finally:
        u32.CloseClipboard()


def _clip_set(text):
    import ctypes
    from ctypes import wintypes
    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    u32.OpenClipboard.argtypes = [wintypes.HWND]
    u32.OpenClipboard.restype = wintypes.BOOL
    u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    u32.SetClipboardData.restype = wintypes.HANDLE
    k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k32.GlobalAlloc.restype = wintypes.HGLOBAL
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    raw = (text + "\0").encode("utf-16-le")
    h = k32.GlobalAlloc(0x0002, len(raw))
    if not h:
        return
    p = k32.GlobalLock(h)
    ctypes.memmove(p, raw, len(raw))
    k32.GlobalUnlock(h)
    for _ in range(15):
        if u32.OpenClipboard(None):
            break
        time.sleep(0.02)
    else:
        return
    try:
        u32.EmptyClipboard()
        u32.SetClipboardData(13, h)
    finally:
        u32.CloseClipboard()


def safe(fn):
    @functools.wraps(fn)
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except Exception as e:
            _log("ERROR in %s: %s\n%s" % (fn.__name__, e, traceback.format_exc()))
            return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
    return wrapper


def _num(v):
    try:
        if v is None:
            return None
        if isinstance(v, str):
            if not re.fullmatch(r"\d+(\.\d+)?", v.strip()):
                return None
        f = float(v)
        return round(f, 1) if f > 0 else None
    except Exception:
        return None


def _minutes(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v) or None
    m = re.fullmatch(r"\s*(\d+):(\d{2})\s*", str(v))
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


def _kp_type(t):
    return "series" if t in ("TV_SERIES", "MINI_SERIES", "TV_SHOW") else "movie"


def pick_best(cands, title, alts, year, kind):
    qs = [norm(t) for t in [title] + list(alts or []) if t]
    best = None
    best_key = None
    for c in cands:
        names = [norm(c.get("titleRu")), norm(c.get("titleOrig"))]
        sim = 0.0
        for n in names:
            if not n:
                continue
            for q in qs:
                if not q:
                    continue
                if n == q:
                    s = 1.0
                elif (q in n or n in q) and min(len(q), len(n)) / max(len(q), len(n)) >= 0.5:
                    s = 0.6 + 0.4 * min(len(q), len(n)) / max(len(q), len(n))
                else:
                    s = difflib.SequenceMatcher(None, n, q).ratio()
                sim = max(sim, s)
        score = sim
        cy = c.get("year")
        if year and cy:
            d = abs(year - cy)
            if d > 1 and sim < 0.9:
                continue
            score += 0.3 if d == 0 else (0.12 if d == 1 else -0.25)
        elif year and not cy and sim < 0.9:
            continue
        if c.get("type") == kind:
            score += 0.1
        if best_key is None or score > best_key[0]:
            best_key = (score, sim)
            best = c
    if best is not None and best_key[1] >= 0.55:
        return best
    return None


def _recycle(path):
    if os.name != "nt":
        raise NotImplementedError("Корзина доступна только в Windows")
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

    op = SHFILEOPSTRUCTW()
    op.wFunc = 3
    op.pFrom = os.path.abspath(path) + "\0"
    op.fFlags = 0x40 | 0x10 | 0x4 | 0x400
    res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if res != 0 or op.fAnyOperationsAborted:
        raise OSError("не удалось переместить в Корзину (код %s)" % res)


def _is_inside(root, path):
    try:
        r = os.path.normcase(os.path.realpath(root))
        p = os.path.normcase(os.path.realpath(path))
        return os.path.commonpath([r, p]) == r and p != r
    except ValueError:
        return False


class Api:
    _srv = None
    _srv_err = ""

    def _srv_pin(self):
        with self._lock:
            p = str(self._cfg.get("srv_pin") or "")
            new = not re.fullmatch(r"\d{6}", p)
            if new:
                p = "%06d" % secrets.randbelow(10 ** 6)
                self._cfg["srv_pin"] = p
        if new:
            self._save_cfg()
        return p

    def _tv_token_ok(self, t):
        if not t:
            return False
        with self._lock:
            keys = list(self._cfg["srv_tokens"])
        hit = None
        for k in keys:
            if hmac.compare_digest(str(t), k):
                hit = k
        if hit is None:
            return False
        now = int(time.time())
        with self._lock:
            v = self._cfg["srv_tokens"].get(hit)
            fresh = isinstance(v, dict) and now - int(v.get("last") or 0) >= 60
            if fresh:
                v["last"] = now
        if fresh:
            self._save_cfg()
        return True

    def _tv_add_token(self, name):
        tok = secrets.token_urlsafe(24)
        with self._lock:
            self._cfg["srv_tokens"][tok] = {"name": name, "ts": int(time.time())}
        self._save_cfg()
        return tok

    def _srv_ensure_scan(self):
        if not self._items and self._cfg.get("root_folders"):
            self.scan()

    def _srv_firewall(self, port):
        if os.name != "nt":
            return
        flags = 0x08000000
        try:
            for name, proto, p in (("Kino server %d" % port, "TCP", port), ("Kino discovery", "UDP", TV_UDP_PORT)):
                r = subprocess.run(["netsh", "advfirewall", "firewall", "show", "rule", "name=" + name],
                                   capture_output=True, creationflags=flags, timeout=15)
                if r.returncode != 0:
                    subprocess.run(["netsh", "advfirewall", "firewall", "add", "rule", "name=" + name, "dir=in",
                                    "action=allow", "protocol=" + proto, "localport=%d" % p, "profile=private"],
                                   capture_output=True, creationflags=flags, timeout=15)
        except Exception:
            pass

    def _srv_apply(self):
        old = self._srv
        if old:
            old.stop()
            self._srv = None
        self._srv_err = ""
        if self._cfg.get("srv_on") != "1":
            return
        port = self._srv_port()
        s = TvServer(self, port)
        self._srv_err = s.start()
        if self._srv_err:
            return
        self._srv = s
        threading.Thread(target=self._srv_firewall, args=(port,), daemon=True).start()
        threading.Thread(target=self._srv_ensure_scan, daemon=True).start()

    def _srv_port(self):
        try:
            p = int(self._cfg.get("srv_port"))
        except (TypeError, ValueError):
            p = 8765
        return p if 1024 <= p <= 65535 else 8765

    @safe
    def srv_info(self):
        with self._lock:
            devs = [{"name": v.get("name") or "TV", "ts": v.get("ts") or 0, "last": v.get("last") or 0}
                    for v in self._cfg["srv_tokens"].values() if isinstance(v, dict)]
        port = self._srv_port()
        return {"ok": True, "on": self._cfg.get("srv_on") == "1", "running": bool(self._srv), "error": self._srv_err,
                "port": port, "addr": "http://%s:%d" % (_local_ip(), port), "pin": self._srv_pin(),
                "pinRequired": self._cfg.get("srv_nopin") != "1", "devices": devs}

    def _progress_all(self):
        with self._lock:
            if not hasattr(self, "_prog"):
                self._prog = _load_json(PROGRESS_PATH, {})
            return dict(self._prog)

    def tv_progress(self, item_id, fid, pos, dur):
        it = self._items.get(item_id)
        if not it:
            return {"ok": False}
        paths = _flat_paths(self._view(it))
        try:
            fid = int(fid)
            pos = max(0, int(pos))
            dur = max(0, int(dur))
        except (TypeError, ValueError):
            return {"ok": False}
        if not 0 <= fid < len(paths):
            return {"ok": False}
        done = dur > 0 and pos >= dur * 0.9
        self._progress_all()
        with self._lock:
            self._prog["%s|%d" % (item_id, fid)] = {"pos": 0 if done else pos, "dur": dur, "ts": int(time.time()), "done": done}
            snap = dict(self._prog)
            if done:
                self._cfg["watched"][paths[fid]] = 1
            _save_json(PROGRESS_PATH, snap)
        if done:
            self._save_cfg()
            w = self._cfg["watched"]
            if all(x in w for x in paths) and item_id not in self._wd:
                self.set_watched(item_id, True)
        return {"ok": True, "done": done}

    def tv_progress_clear(self, item_id):
        self._progress_all()
        pre = "%s|" % item_id
        with self._lock:
            for k in [k for k in self._prog if k.startswith(pre)]:
                del self._prog[k]
            snap = dict(self._prog)
            _save_json(PROGRESS_PATH, snap)
        return {"ok": True}

    @safe
    def srv_set(self, on, port=None):
        if port is not None:
            try:
                p = int(port)
            except (TypeError, ValueError):
                p = 0
            if not 1024 <= p <= 65535:
                return {"ok": False, "error": "Порт должен быть от 1024 до 65535"}
            self._cfg["srv_port"] = str(p)
        self._cfg["srv_on"] = "1" if on else ""
        self._save_cfg()
        self._srv_apply()
        return self.srv_info()

    @safe
    def srv_pin_required(self, flag):
        self._cfg["srv_nopin"] = "" if flag else "1"
        self._save_cfg()
        return self.srv_info()

    @safe
    def srv_new_pin(self):
        self._cfg["srv_pin"] = ""
        self._srv_pin()
        return self.srv_info()

    @safe
    def srv_forget(self):
        with self._lock:
            self._cfg["srv_tokens"] = {}
        self._save_cfg()
        return self.srv_info()

    def _rem(self):
        return getattr(self, "_remote", None)

    def _rem_http(self, method, path, body=None, timeout=20, stream=False):
        r = self._rem()
        if not r:
            raise ApiError("net", "not connected")
        sess = requests.Session()
        sess.trust_env = False
        try:
            resp = sess.request(method, "http://%s:%d%s" % (r["host"], r["port"], path),
                                headers={"X-Kino-Token": r["token"]}, json=body, timeout=timeout)
        except requests.exceptions.RequestException as e:
            raise ApiError("net", str(e))
        if resp.status_code == 401:
            raise ApiError("auth", "unauthorized")
        if resp.status_code != 200:
            raise ApiError("http", "HTTP %s" % resp.status_code)
        return resp

    def _rem_post(self, path, body):
        try:
            return self._rem_http("POST", path, body).json()
        except ApiError as e:
            return {"ok": False, "error": self._rem_err(e)}

    @staticmethod
    def _rem_err(e):
        return {"net": "Не удаётся связаться с удалённым компьютером",
                "auth": "Доступ отклонён, подключитесь заново"}.get(e.code, "Ошибка удалённой медиатеки")

    @staticmethod
    def _rem_norm(host, port):
        host = (host or "").strip()
        host = re.sub(r"^https?://", "", host).split("/")[0]
        if host.count(":") == 1:
            h, p = host.split(":")
            host = h
            if p.isdigit():
                port = int(p)
        try:
            port = int(port or 8765)
        except (TypeError, ValueError):
            port = 8765
        return host, port

    @staticmethod
    def _local_ips():
        ips = {_local_ip()}
        try:
            ips.update(r[4][0] for r in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
        except OSError:
            pass
        return sorted(i for i in ips if not i.startswith(("127.", "169.254.", "0.")))

    @staticmethod
    def _probe_kino(host):
        try:
            with socket.create_connection((host, 8765), timeout=0.35) as c:
                c.settimeout(0.8)
                c.sendall(b"GET /api/ping HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
                buf = b""
                while b"\r\n\r\n" not in buf and len(buf) < 4096:
                    chunk = c.recv(1024)
                    if not chunk:
                        break
                    buf += chunk
                head, _, body = buf.partition(b"\r\n\r\n")
                m = re.search(rb"(?i)content-length:\s*(\d+)", head)
                n = min(int(m.group(1)), 4096) if m else 0
                while len(body) < n:
                    chunk = c.recv(1024)
                    if not chunk:
                        break
                    body += chunk
            d = json.loads(body.decode("utf-8"))
        except (OSError, ValueError):
            return None
        return (host, 8765, d.get("name") or host) if d.get("app") == "kino" else None

    @safe
    def remote_discover(self):
        import select
        found = {}
        ips = self._local_ips()
        mine = set(ips) | {"127.0.0.1"}
        sweep = [("%s.%d" % (ip.rsplit(".", 1)[0], n)) for ip in ips[:4] for n in range(1, 255)]
        sweep = [h for h in dict.fromkeys(sweep) if h not in mine]
        pool = ThreadPoolExecutor(max_workers=64)
        futs = [pool.submit(self._probe_kino, h) for h in sweep]
        socks = []
        for ip in ips + [""]:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.bind((ip, 0))
                socks.append((s, ip))
            except OSError:
                pass
        for _ in range(2):
            for s, ip in socks:
                for dst in ("255.255.255.255", ip.rsplit(".", 1)[0] + ".255" if ip else None):
                    if dst:
                        try:
                            s.sendto(b"KINO?", (dst, TV_UDP_PORT))
                        except OSError:
                            pass
            end = time.time() + 0.9
            while time.time() < end and socks:
                try:
                    ready = select.select([s for s, _ in socks], [], [], 0.2)[0]
                except (OSError, ValueError):
                    break
                for s in ready:
                    try:
                        data, addr = s.recvfrom(512)
                        d = json.loads(data.decode("utf-8"))
                    except (OSError, ValueError):
                        continue
                    if d.get("app") == "kino":
                        found[(addr[0], int(d.get("port") or 8765))] = d.get("name") or addr[0]
        for s, _ in socks:
            s.close()
        for f in futs:
            try:
                r = f.result(timeout=3)
            except Exception:
                r = None
            if r:
                found.setdefault((r[0], r[1]), r[2])
        pool.shutdown(wait=False, cancel_futures=True)
        out = [{"host": h, "port": p, "name": n, "self": h in mine} for (h, p), n in found.items()]
        return {"ok": True, "servers": out}

    @safe
    def remote_connect(self, host, port=8765, pin=""):
        host, port = self._rem_norm(host, port)
        if not host:
            return {"ok": False, "error": "Укажите адрес"}
        sess = requests.Session()
        sess.trust_env = False
        try:
            r = sess.post("http://%s:%d/api/pair" % (host, port),
                          json={"pin": str(pin or ""), "device": "Kino PC %s" % socket.gethostname()}, timeout=10)
        except requests.exceptions.RequestException:
            return {"ok": False, "error": "Нет ответа. Проверьте адрес, порт и что сервер включён на том компьютере."}
        if r.status_code == 403:
            return {"ok": False, "error": "Неверный PIN"}
        if r.status_code == 429:
            return {"ok": False, "error": "Слишком много попыток, подождите несколько минут"}
        try:
            d = r.json()
        except ValueError:
            d = {}
        if r.status_code != 200 or not d.get("token"):
            return {"ok": False, "error": "Не удалось подключиться"}
        self._remote = {"host": host, "port": port, "token": d["token"], "name": d.get("name") or host}
        with self._lock:
            self._cfg["remote_last"] = dict(self._remote)
        self._save_cfg()
        return {"ok": True, "name": self._remote["name"]}

    @safe
    def remote_reconnect(self):
        last = self._cfg.get("remote_last")
        if not isinstance(last, dict) or not last.get("token"):
            return {"ok": False, "error": "Нет сохранённого подключения"}
        self._remote = dict(last)
        try:
            self._rem_http("GET", "/api/library", timeout=30)
        except ApiError as e:
            self._remote = None
            if e.code == "auth":
                with self._lock:
                    self._cfg.pop("remote_last", None)
                self._save_cfg()
            return {"ok": False, "error": self._rem_err(e)}
        return {"ok": True, "name": last.get("name")}

    @safe
    def remote_disconnect(self):
        self._remote = None
        self._remote_posters = {}
        return {"ok": True}

    @safe
    def remote_state(self):
        r = self._rem()
        last = self._cfg.get("remote_last")
        return {"ok": True, "connected": bool(r), "name": r["name"] if r else None,
                "player": self._cfg.get("remote_player") or "", "custom": self._cfg.get("player_mode") == "custom" and bool(self._cfg.get("player_path")),
                "addr": ("%s:%d" % (r["host"], r["port"])) if r else None,
                "last": ({"host": last["host"], "port": last["port"], "name": last.get("name")} if isinstance(last, dict) and last.get("token") else None)}

    def _remote_scan(self):
        try:
            d = self._rem_http("GET", "/api/library", timeout=60).json()
        except ApiError as e:
            return {"ok": False, "error": self._rem_err(e), "items": []}
        rid = [0]

        def fix(v):
            v["hasLocalPoster"] = bool(v.pop("localPoster", False))
            for f in v.get("files") or []:
                f["path"] = "kino-remote://%s/%d" % (v["id"], f["fid"])
            for sn in v.get("seasons") or []:
                for f in sn.get("episodes") or []:
                    f["path"] = "kino-remote://%s/%d" % (v["id"], f["fid"])
            return v

        items = [fix(v) for v in d.get("items") or []]
        ghosts = [fix(v) for v in d.get("ghosts") or []]
        return {"ok": True, "roots": [], "missing": [], "items": items, "ghosts": ghosts,
                "remote": self._remote["name"]}

    def _remote_play(self, path, override=""):
        m = re.fullmatch(r"kino-remote://([^/]+)/(\d+)", path)
        r = self._rem()
        if not m or not r:
            return {"ok": False, "error": "Нет подключения к удалённой медиатеке"}
        url = "http://%s:%d/api/stream/%s/%s?t=%s" % (r["host"], r["port"], m.group(1), m.group(2), r["token"])
        mode = self._cfg.get("player_mode")
        player = self._cfg.get("player_path")
        if override:
            if override == "browser":
                player = None
            elif os.path.isfile(override) and override.lower().endswith(".exe"):
                player = override
            else:
                return {"ok": False, "error": "Файл плеера не найден"}
        elif not (mode == "custom" and player and os.path.isfile(player)):
            player = None
            choice = self._cfg.get("remote_player") or ""
            if choice == "browser":
                player = None
            elif choice and os.path.isfile(choice):
                player = choice
            else:
                return {"ok": False, "needPlayer": True, "players": self._find_players()}
        try:
            if player:
                flags = (0x00000008 | 0x00000200) if os.name == "nt" else 0
                subprocess.Popen([player, url], creationflags=flags, close_fds=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif os.name == "nt":
                os.startfile(url)
            else:
                subprocess.Popen(["xdg-open", url])
        except Exception as e:
            return {"ok": False, "error": "Не удалось запустить: %s" % e}
        return {"ok": True}

    def _find_players(self):
        if os.name != "nt":
            return []
        bases = [os.environ.get(k) for k in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")]
        bases.append(os.path.join(os.environ.get("LOCALAPPDATA") or "", "Programs"))
        known = (("VLC", r"VideoLAN\VLC\vlc.exe"), ("PotPlayer", r"DAUM\PotPlayer\PotPlayerMini64.exe"),
                 ("PotPlayer", r"PotPlayer\PotPlayerMini64.exe"), ("PotPlayer", r"PotPlayer64\PotPlayerMini64.exe"),
                 ("MPC-HC", r"MPC-HC\mpc-hc64.exe"), ("MPC-BE", r"MPC-BE x64\mpc-be64.exe"),
                 ("MPC-BE", r"MPC-BE\mpc-be64.exe"), ("mpv", r"mpv\mpv.exe"), ("SMPlayer", r"SMPlayer\smplayer.exe"),
                 ("KMPlayer", r"The KMPlayer\KMPlayer64.exe"))
        found, seen = [], set()

        def add(name, path):
            key = os.path.normcase(os.path.normpath(path))
            if key not in seen and os.path.isfile(path):
                seen.add(key)
                found.append({"name": name, "path": os.path.normpath(path)})
        for name, rel in known:
            for b in bases:
                if b:
                    add(name, os.path.join(b, rel))
        mine = self._cfg.get("player_path")
        if mine:
            add(os.path.splitext(os.path.basename(mine))[0], mine)
        return found

    @safe
    def remote_set_player(self, kind, path=""):
        if kind == "browser":
            val = "browser"
        elif kind == "exe" and path and os.path.isfile(path) and path.lower().endswith(".exe"):
            val = path
        elif kind == "reset":
            val = ""
        else:
            return {"ok": False, "error": "Укажите .exe файл плеера"}
        with self._lock:
            self._cfg["remote_player"] = val
        self._save_cfg()
        return {"ok": True, "player": val}

    def _remote_poster(self, item_id):
        cache = getattr(self, "_remote_posters", None)
        if cache is None:
            cache = self._remote_posters = {}
        if item_id in cache:
            return cache[item_id]
        try:
            resp = self._rem_http("GET", "/api/poster/%s" % quote(item_id, safe=""), timeout=20)
        except ApiError:
            return ""
        mime = resp.headers.get("Content-Type") or "image/jpeg"
        uri = "data:%s;base64,%s" % (mime, base64.b64encode(resp.content).decode("ascii"))
        cache[item_id] = uri
        return uri


    def __init__(self):
        self._window = None
        self._lock = threading.RLock()
        cfg = dict(DEFAULT_CONFIG)
        raw = _load_json(CONFIG_PATH, {})
        cfg.update({k: v for k, v in raw.items() if k in DEFAULT_CONFIG})
        if not isinstance(cfg.get("root_folders"), list):
            cfg["root_folders"] = []
        if not cfg["root_folders"] and isinstance(raw.get("root_folder"), str) and raw["root_folder"]:
            cfg["root_folders"] = [raw["root_folder"]]
        cfg["root_folders"] = self._norm_roots(cfg["root_folders"])
        if not isinstance(cfg.get("watched"), dict):
            cfg["watched"] = {}
        if not isinstance(cfg.get("hidden"), dict):
            cfg["hidden"] = {}
        if not isinstance(cfg.get("pinned"), dict):
            cfg["pinned"] = {}
        if not isinstance(cfg.get("srv_tokens"), dict):
            cfg["srv_tokens"] = {}
        self._cfg = cfg
        cache = _load_json(CACHE_PATH, {})
        if not isinstance(cache.get("items"), dict):
            cache = {"version": 1, "items": {}}
        self._cache = cache
        self._items = {}
        self._paths = set()
        self._local_cache = {}
        self._remote = None
        self._remote_posters = {}
        wl = _load_json(WATCHLIST_PATH, {"items": []})
        if not isinstance(wl.get("items"), list):
            wl = {"items": []}
        self._wl = wl
        self._wl_cache = {}
        wd = _load_json(WATCHED_PATH, {})
        self._wd = wd if isinstance(wd, dict) else {}
        self._http = requests.Session()
        self._http.headers["User-Agent"] = "Kino/1.5.0"
        self._kp_dead = (None, 0)
        self._gate_lock = threading.Lock()
        self._gate_next = {}
        self._gate_cool = {}
        self._gate_dead = {}
        self._omdb_dead = (None, 0.0)
        self._pal = {}
        self._poster_sem = threading.Semaphore(8)
        self._poster_base = ""
        self._start_poster_server()

    @staticmethod
    def _norm_roots(lst):
        out, seen = [], set()
        for x in lst or []:
            if not isinstance(x, str) or not x.strip():
                continue
            p = os.path.normpath(x.strip())
            k = os.path.normcase(p)
            if k not in seen:
                seen.add(k)
                out.append(p)
        return out

    def _roots(self):
        return [r for r in self._cfg.get("root_folders", []) if os.path.isdir(r)]

    def _save_cfg(self):
        with self._lock:
            _save_json(CONFIG_PATH, self._cfg)

    def _save_cache(self):
        with self._lock:
            self._cache_dirty = True
            if getattr(self, "_cache_timer", None):
                return
            self._cache_timer = threading.Timer(3, self._flush_cache)
            self._cache_timer.daemon = True
            self._cache_timer.start()

    def _flush_cache(self):
        with self._lock:
            self._cache_timer = None
            if getattr(self, "_cache_dirty", False):
                self._cache_dirty = False
                _save_json(CACHE_PATH, self._cache)

    def _dialog(self, kind, **kw):
        FD = getattr(webview, "FileDialog", None)
        names = {"folder": "FOLDER", "open": "OPEN", "save": "SAVE"}
        if FD is not None:
            t = getattr(FD, names[kind])
        else:
            t = getattr(webview, names[kind] + "_DIALOG")
        return self._window.create_file_dialog(t, **kw)

    def _get(self, url, headers=None, params=None):
        r = None
        for attempt in range(2):
            try:
                r = self._http.get(url, headers=headers, params=params, timeout=15)
            except requests.exceptions.RequestException as e:
                raise ApiError("net", str(e))
            if r.status_code == 429 and attempt == 0:
                time.sleep(1.2)
                continue
            break
        sc = r.status_code
        if sc == 200:
            try:
                return r.json()
            except ValueError:
                raise ApiError("http", "bad json")
        if sc in (401, 403):
            raise ApiError("auth", "HTTP %s" % sc)
        if sc == 402:
            raise ApiError("limit", "HTTP 402")
        if sc == 404:
            raise ApiError("notfound", "HTTP 404")
        if sc == 429:
            raise ApiError("rate", "HTTP 429")
        raise ApiError("http", "HTTP %s" % sc)

    def _kp_get(self, path, params=None):
        headers = {"X-API-KEY": self._cfg["kp_api_key"], "Content-Type": "application/json"}
        return self._get(KP_BASE + path, headers=headers, params=params)

    def _kp_search(self, query, year=None):
        query = re.sub(r"\s+", " ", query or "").strip()
        if not query:
            return []
        err = None
        for ver in ("v22", "v21"):
            try:
                if ver == "v22":
                    prm = {"keyword": query, "page": 1}
                    if year:
                        prm["yearFrom"] = int(year) - 1
                        prm["yearTo"] = int(year) + 1
                    data = self._kp_get("/api/v2.2/films", prm)
                    return self._kp_rows_v22(data)
                data = self._kp_get("/api/v2.1/films/search-by-keyword", {"keyword": query, "page": 1})
                return self._kp_rows_v21(data)
            except ApiError as e:
                if e.code not in ("http", "net"):
                    raise
                err = e
        raise err

    def _kp_rows_v22(self, data):
        res = []
        for f in (data.get("items") or []):
            kid = f.get("kinopoiskId")
            if not kid:
                continue
            typ = _kp_type(f.get("type"))
            year = f.get("year")
            res.append({
                "source": "kp", "ext_id": kid,
                "titleRu": f.get("nameRu") or f.get("nameEn") or f.get("nameOriginal"),
                "titleOrig": f.get("nameOriginal") or f.get("nameEn"),
                "year": int(year) if str(year or "").isdigit() else None,
                "duration": None,
                "ratingKp": _num(f.get("ratingKinopoisk")), "ratingImdb": _num(f.get("ratingImdb")), "ratingTmdb": None,
                "genres": [g.get("genre") for g in (f.get("genres") or []) if g.get("genre")],
                "countries": [c.get("country") for c in (f.get("countries") or []) if c.get("country")],
                "type": typ, "description": "",
                "poster": f.get("posterUrl"), "posterPreview": f.get("posterUrlPreview"),
                "imdbId": f.get("imdbId") or None,
                "url": "https://www.kinopoisk.ru/%s/%s/" % ("series" if typ == "series" else "film", kid),
            })
        return res

    def _kp_rows_v21(self, data):
        res = []
        for f in (data.get("films") or []):
            if not f.get("filmId"):
                continue
            year = f.get("year")
            res.append({
                "source": "kp", "ext_id": f["filmId"],
                "titleRu": f.get("nameRu") or f.get("nameEn"), "titleOrig": f.get("nameEn"),
                "year": int(year) if str(year or "").isdigit() else None,
                "duration": _minutes(f.get("filmLength")),
                "ratingKp": _num(f.get("rating")), "ratingImdb": None, "ratingTmdb": None,
                "genres": [g.get("genre") for g in (f.get("genres") or []) if g.get("genre")],
                "countries": [c.get("country") for c in (f.get("countries") or []) if c.get("country")],
                "type": _kp_type(f.get("type")),
                "description": f.get("description") or "",
                "poster": f.get("posterUrl"), "posterPreview": f.get("posterUrlPreview"),
                "url": "%s/%s/" % ("https://www.kinopoisk.ru", "series/%s" % f["filmId"] if _kp_type(f.get("type")) == "series" else "film/%s" % f["filmId"]),
            })
        return res

    def _kp_details(self, kp_id):
        d = self._kp_get("/api/v2.2/films/%s" % kp_id)
        typ = _kp_type(d.get("type"))
        if d.get("serial") is True:
            typ = "series"
        ru = d.get("nameRu") or d.get("nameOriginal") or d.get("nameEn")
        orig = d.get("nameOriginal") or d.get("nameEn")
        web = d.get("webUrl") or "https://www.kinopoisk.ru/%s/%s/" % ("series" if typ == "series" else "film", kp_id)
        return {
            "source": "kp", "ext_id": d.get("kinopoiskId") or kp_id,
            "titleRu": ru, "titleOrig": orig if orig and orig != ru else None,
            "year": d.get("year"), "duration": _minutes(d.get("filmLength")),
            "ratingKp": _num(d.get("ratingKinopoisk")), "ratingImdb": _num(d.get("ratingImdb")), "ratingTmdb": None,
            "genres": [g.get("genre") for g in (d.get("genres") or []) if g.get("genre")],
            "countries": [c.get("country") for c in (d.get("countries") or []) if c.get("country")],
            "type": typ,
            "description": d.get("description") or d.get("shortDescription") or "",
            "poster": d.get("posterUrl"), "posterPreview": d.get("posterUrlPreview"),
            "url": web, "imdbId": d.get("imdbId") or None,
        }

    def _tmdb_get(self, path, params=None):
        key = self._cfg["tmdb_api_key"]
        params = dict(params or {})
        headers = {}
        if key.startswith("eyJ"):
            headers["Authorization"] = "Bearer " + key
        else:
            params["api_key"] = key
        return self._get(TMDB_BASE + path, headers=headers, params=params)

    def _tmdb_norm(self, d, mt):
        is_tv = mt == "tv"
        date = d.get("first_air_date") if is_tv else d.get("release_date")
        runtime = None
        if is_tv:
            ert = d.get("episode_run_time") or []
            runtime = ert[0] if ert else None
        else:
            runtime = d.get("runtime") or None
        countries = []
        if d.get("production_countries"):
            for c in d["production_countries"]:
                countries.append(COUNTRIES.get(c.get("iso_3166_1"), c.get("name")))
        elif d.get("origin_country"):
            countries = [COUNTRIES.get(c, c) for c in d["origin_country"]]
        genres = [g.get("name") for g in (d.get("genres") or []) if g.get("name")]
        pp = d.get("poster_path")
        vc = d.get("vote_count") or 0
        return {
            "source": "tmdb", "ext_id": "%s:%s" % (mt, d.get("id")),
            "titleRu": (d.get("name") if is_tv else d.get("title")) or (d.get("original_name") if is_tv else d.get("original_title")),
            "titleOrig": d.get("original_name") if is_tv else d.get("original_title"),
            "year": int(date[:4]) if date and date[:4].isdigit() else None,
            "duration": runtime, "ratingKp": None, "ratingImdb": None,
            "ratingTmdb": _num(d.get("vote_average")) if vc else None,
            "genres": genres, "countries": countries,
            "type": "series" if is_tv else "movie",
            "description": d.get("overview") or "",
            "poster": (TMDB_IMG + "w780" + pp) if pp else None,
            "posterPreview": (TMDB_IMG + "w342" + pp) if pp else None,
            "url": "https://www.themoviedb.org/%s/%s" % (mt, d.get("id")),
        }

    def _tmdb_search(self, query):
        data = self._tmdb_get("/search/multi", {"query": query, "language": "ru-RU", "include_adult": "false"})
        res = []
        for d in (data.get("results") or []):
            mt = d.get("media_type")
            if mt in ("movie", "tv"):
                res.append(self._tmdb_norm(d, mt))
        return res

    def _tmdb_details(self, ext_id):
        mt, _id = str(ext_id).split(":")
        d = self._tmdb_get("/%s/%s" % (mt, _id), {"language": "ru-RU"})
        return self._tmdb_norm(d, mt)

    def _kp_usable(self):
        if not self._cfg["kp_api_key"]:
            return False
        code, until = self._kp_dead
        return not (code and time.time() < until)

    def _block_kp(self, code):
        secs = {"auth": 10 ** 9, "limit": 1800, "rate": 90}.get(code, 60)
        self._kp_dead = (code, time.time() + secs)

    def _kp_warn(self):
        code, until = self._kp_dead
        return code if (code and time.time() < until) else None

    def _kp_full(self, best):
        try:
            return self._kp_details(best["ext_id"])
        except ApiError as e:
            if e.code in ("net", "auth", "limit", "rate"):
                raise
            return dict(best)

    def _web_wait(self, host):
        gap = WEB_GAPS.get(next((k for k in WEB_GAPS if host.endswith(k)), ""), 1.0)
        with self._gate_lock:
            now = time.time()
            slot = max(now, self._gate_next.get(host, 0.0), self._gate_cool.get(host, 0.0))
            self._gate_next[host] = slot + gap
        if slot > now:
            time.sleep(slot - now)

    def _web_get(self, url, params=None, throttle=False, soft=False):
        host = urlparse(url).netloc.lower()
        if time.time() < self._gate_dead.get(host, 0.0):
            raise ApiError("blocked", "cooldown")
        headers = {
            "User-Agent": BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        }
        pauses = (8, 25)
        last_err = None
        for attempt in range(1 if soft else 3):
            self._web_wait(host)
            try:
                r = self._http.get(url, headers=headers, params=params, timeout=15, allow_redirects=True)
            except requests.exceptions.RequestException as e:
                if attempt == 0:
                    time.sleep(2)
                    last_err = ApiError("net", str(e))
                    continue
                raise ApiError("net", str(e))
            if r.status_code == 200:
                r.encoding = "utf-8"
                return r
            if r.status_code == 404:
                raise ApiError("notfound", "HTTP 404")
            if soft and r.status_code in (403, 429, 503):
                raise ApiError("blocked", "HTTP %s" % r.status_code)
            if r.status_code == 403:
                with self._gate_lock:
                    self._gate_dead[host] = time.time() + 600
                raise ApiError("blocked", "HTTP 403")
            if r.status_code in (429, 503):
                wait = pauses[min(attempt, len(pauses) - 1)]
                try:
                    wait = max(wait, min(60, int(r.headers.get("Retry-After", 0))))
                except (TypeError, ValueError):
                    pass
                with self._gate_lock:
                    self._gate_cool[host] = max(self._gate_cool.get(host, 0.0), time.time() + wait)
                last_err = ApiError("blocked", "HTTP %s" % r.status_code)
                continue
            raise ApiError("http", "HTTP %s" % r.status_code)
        if last_err is not None and last_err.code == "blocked":
            with self._gate_lock:
                self._gate_dead[host] = time.time() + 180
        raise last_err or ApiError("blocked", "HTTP 429")

    def _step_kp(self, queries, it):
        title, alts, year, kind = it["title"], it.get("alts") or [], it["year"], it["kind"]
        for q in queries[:2]:
            best = None
            if year:
                best = pick_best(self._kp_search(q, year), title, alts, year, kind)
            if not best:
                best = pick_best(self._kp_search(q), title, alts, year, kind)
            if best:
                m = self._kp_full(best)
                m["via"] = "kp"
                return m
        tries = 0
        for q in queries[:2]:
            if not looks_translit(q):
                continue
            for v in translit_variants(q):
                if tries >= 2:
                    return None
                tries += 1
                best = pick_best(self._kp_search(v), v, [], year, kind)
                if best:
                    m = self._kp_full(best)
                    m["via"] = "translit"
                    return m
        return None

    def _step_tmdb(self, queries, it):
        qs = list(queries[:2])
        if queries and looks_translit(queries[0]):
            qs.append(translit_to_cyr(queries[0]))
        for q in qs:
            best = pick_best(self._tmdb_search(q), q, queries, it["year"], it["kind"])
            if best:
                try:
                    return self._tmdb_details(best["ext_id"])
                except ApiError as e:
                    if e.code == "net":
                        raise
                    return best
        return None

    def _imdb_search(self, q):
        q = re.sub(r"\s+", " ", re.sub(r"[^\w\s'\-.&:]", " ", q or "")).strip().lower()
        if not q:
            return []
        r = self._web_get(IMDB_SUGGEST + quote(q, safe="") + ".json")
        try:
            return parse_imdb_suggest(r.json())
        except ValueError:
            return []

    def _imdb_pick(self, cands, it):
        kind, year = it["kind"], it["year"]
        qs = [it["title"]] + list(it.get("alts") or [])
        best, best_s = None, 0.0
        for idx, c in enumerate(cands):
            cy = c.get("year")
            sim = title_sim([c.get("titleOrig"), c.get("titleRu")], qs)
            sc = 0.0
            if year and cy:
                d = abs(year - cy)
                if d == 0:
                    sc += 1.0
                elif d == 1:
                    sc += 0.5
                else:
                    continue
                if sim < 0.35 and not (idx == 0 and d == 0 and c.get("type") == kind):
                    continue
            elif sim < 0.6:
                continue
            sc += sim * 0.5
            sc += 0.3 if c.get("type") == kind else -0.2
            sc -= idx * 0.02
            if sc > best_s:
                best, best_s = c, sc
        return best if best is not None and best_s >= 0.45 else None

    def _omdb_ready(self):
        if not self._cfg.get("omdb_api_key"):
            return False
        code, until = self._omdb_dead
        return not (code and time.time() < until)

    def _omdb_get(self, params):
        p = dict(params, apikey=self._cfg["omdb_api_key"])
        try:
            r = self._web_get("https://www.omdbapi.com/", params=p)
        except ApiError as e:
            if e.code == "http":
                self._omdb_dead = ("http", time.time() + 3600)
            raise
        try:
            data = r.json()
        except ValueError:
            raise ApiError("http", "bad json")
        if str(data.get("Response")) == "False":
            err = str(data.get("Error") or "")
            if "limit" in err.lower():
                self._omdb_dead = ("limit", time.time() + 6 * 3600)
                raise ApiError("limit", err)
            if "api key" in err.lower():
                self._omdb_dead = ("auth", time.time() + 10 ** 6)
                raise ApiError("auth", err)
            return None
        return data

    def _omdb_search(self, q, year=None, kind=None):
        params = {"s": q}
        if year:
            params["y"] = year
        if kind in ("movie", "series"):
            params["type"] = kind
        data = self._omdb_get(params)
        res = []
        for d in ((data or {}).get("Search") or []):
            iid = d.get("imdbID") or ""
            if not iid.startswith("tt") or d.get("Type") not in ("movie", "series"):
                continue
            y = re.match(r"(\d{4})", d.get("Year") or "")
            img = d.get("Poster") if d.get("Poster") not in (None, "N/A") else None
            res.append({
                "source": "imdb", "ext_id": iid, "titleRu": d.get("Title"), "titleOrig": d.get("Title"),
                "year": int(y.group(1)) if y else None, "duration": None,
                "ratingKp": None, "ratingImdb": None, "ratingTmdb": None,
                "genres": [], "countries": [], "description": "",
                "type": d.get("Type"), "qid": d.get("Type"),
                "poster": _upscale_imdb(img, 500) if img else None, "posterPreview": img, "stars": "",
                "url": "https://www.imdb.com/title/%s/" % iid, "imdbId": iid,
            })
        return res

    def _step_omdb(self, queries, it):
        if not self._omdb_ready():
            return None
        latin = [q for q in queries if re.search(r"[A-Za-z]", q)]
        for q in latin[:2]:
            best = self._imdb_pick(self._omdb_search(q, it["year"], it["kind"]), it)
            if best is None and it["year"]:
                best = self._imdb_pick(self._omdb_search(q, None, it["kind"]), it)
            if best:
                return self._meta_from_omdb(best, it)
        return None

    def _meta_from_omdb(self, c, it):
        iid = c["ext_id"]
        typ = c.get("type") or it["kind"]
        meta = self._kp_from_imdb(iid, c.get("titleOrig"), c.get("year"), typ) if self._lang() == "ru" else None
        if meta is None:
            d = self._omdb_get({"i": iid, "plot": "full"}) or {}
            img = d.get("Poster") if d.get("Poster") not in (None, "N/A") else c.get("posterPreview")
            rating = _num(d.get("imdbRating")) if d.get("imdbRating") not in (None, "N/A") else None
            y = re.match(r"(\d{4})", d.get("Year") or "")
            plot = d.get("Plot") if d.get("Plot") not in (None, "N/A") else ""
            meta = {"source": "imdb", "ext_id": iid, "titleRu": d.get("Title") or c.get("titleRu"), "titleOrig": None,
                    "year": int(y.group(1)) if y else c.get("year"), "duration": _omdb_minutes(d.get("Runtime")),
                    "ratingKp": None, "ratingImdb": rating, "ratingTmdb": None,
                    "genres": _omdb_ru((d.get("Genre") or "").split(","), "g"),
                    "countries": _omdb_ru((d.get("Country") or "").split(","), "c"),
                    "type": typ, "description": plot,
                    "poster": _upscale_imdb(img, 500) if img else c.get("poster"), "posterPreview": img,
                    "url": "https://www.imdb.com/title/%s/" % iid, "imdbId": iid, "via": "omdb"}
            if typ == "movie":
                try:
                    self._merge_lb(meta, self._lb_by_imdb(iid), fill=True)
                except ApiError:
                    pass
        meta["imdbId"] = iid
        return meta

    def _step_imdb(self, queries, it):
        latin = [q for q in queries if re.search(r"[A-Za-z]", q)]
        for q in latin[:2]:
            qq = [q] + (["%s %s" % (q, it["year"])] if it["year"] else [])
            for text in qq:
                best = self._imdb_pick(self._imdb_search(text), it)
                if best:
                    return self._meta_from_imdb(best, it)
        return None

    def _kp_from_imdb(self, imdb_id, title, year, kind):
        if not self._kp_usable():
            return None
        try:
            data = self._kp_get("/api/v2.2/films", {"imdbId": imdb_id})
            kp_id = None
            for f in (data.get("items") or []):
                if f.get("kinopoiskId"):
                    kp_id = f["kinopoiskId"]
                    break
            if kp_id is None and title:
                best = pick_best(self._kp_search(title), title, [], year, kind)
                if best:
                    kp_id = best["ext_id"]
            if kp_id is None:
                return None
            m = self._kp_details(kp_id)
            if not m.get("imdbId"):
                m["imdbId"] = imdb_id
            m["via"] = "imdb"
            return m
        except ApiError as e:
            if e.code in ("auth", "limit", "rate"):
                self._block_kp(e.code)
            return None

    def _meta_from_imdb(self, c, it):
        iid = c["ext_id"]
        typ = c.get("type") or it["kind"]
        meta = self._kp_from_imdb(iid, c.get("titleOrig"), c.get("year"), typ) if self._lang() == "ru" else None
        if meta is None:
            meta = {"source": "imdb", "ext_id": iid, "titleRu": c.get("titleRu"), "titleOrig": None,
                    "year": c.get("year"), "duration": None, "ratingKp": None, "ratingImdb": None,
                    "ratingTmdb": None, "genres": [], "countries": [], "type": typ, "description": "",
                    "poster": c.get("poster"), "posterPreview": c.get("posterPreview"),
                    "url": "https://www.imdb.com/title/%s/" % iid, "imdbId": iid, "via": "imdb"}
            if typ == "movie":
                try:
                    self._merge_lb(meta, self._lb_by_imdb(iid), fill=True)
                except ApiError:
                    pass
        meta["imdbId"] = iid
        return meta

    def _lb_search(self, q):
        q = re.sub(r"\s+", " ", re.sub(r"[()\[\]{}]", " ", q or "")).strip()
        if not q:
            return []
        r = self._web_get(LB_BASE + "/search/films/" + quote(q, safe="") + "/", throttle=True)
        return parse_lb_search(r.text)

    def _lb_film(self, slug):
        r = self._web_get("%s/film/%s/" % (LB_BASE, slug), throttle=True)
        lb = parse_lb_film(r.text, r.url)
        if not lb:
            raise ApiError("notfound", "letterboxd page")
        return lb

    def _lb_by_imdb(self, imdb_id):
        try:
            r = self._web_get("%s/imdb/%s/" % (LB_BASE, imdb_id), throttle=True)
        except ApiError as e:
            if e.code == "notfound":
                return None
            raise
        if "/film/" not in r.url:
            return None
        return parse_lb_film(r.text, r.url)

    def _lb_to_meta(self, lb):
        return {"source": "lb", "ext_id": lb["slug"], "titleRu": lb["name"], "titleOrig": lb.get("origTitle") if lb.get("origTitle") and lb.get("origTitle") != lb["name"] else None,
                "year": lb.get("year"), "duration": lb.get("runtime"), "ratingKp": None, "ratingImdb": None,
                "ratingTmdb": None, "ratingLb": lb.get("rating"),
                "genres": [tr_genre(g) for g in lb.get("genres") or []],
                "countries": [tr_country(c) for c in lb.get("countries") or []], "type": "movie",
                "description": lb.get("description") or "", "poster": lb.get("poster"),
                "posterPreview": lb.get("poster"), "url": lb["url"], "urlLb": lb["url"],
                "directors": lb.get("directors") or [],
                "imdbId": lb.get("imdbId"), "via": "letterboxd"}

    def _merge_lb(self, meta, lb, fill=False):
        if not lb:
            return meta
        if lb.get("rating") is not None:
            meta["ratingLb"] = lb["rating"]
        meta["urlLb"] = lb["url"]
        if not meta.get("imdbId") and lb.get("imdbId"):
            meta["imdbId"] = lb["imdbId"]
        if lb.get("poster"):
            _posters_of(meta)["lb"] = {"poster": lb["poster"], "preview": lb["poster"]}
        if lb.get("description"):
            _descs_of(meta).setdefault("lb", lb["description"])
        if fill:
            if not meta.get("genres") and lb.get("genres"):
                meta["genres"] = [tr_genre(g) for g in lb["genres"]]
            if not meta.get("countries") and lb.get("countries"):
                meta["countries"] = [tr_country(c) for c in lb["countries"]]
            if not meta.get("duration") and lb.get("runtime"):
                meta["duration"] = lb["runtime"]
            if not meta.get("year") and lb.get("year"):
                meta["year"] = lb["year"]
        return meta

    def _lb_finish(self, lb):
        if lb.get("imdbId") and self._lang() == "ru":
            kp = self._kp_from_imdb(lb["imdbId"], lb["name"], lb.get("year"), "movie")
            if kp is not None:
                self._merge_lb(kp, lb)
                return kp
        return self._lb_to_meta(lb)

    def _finalize(self, meta, it):
        iid = meta.get("imdbId")
        if iid and not meta.get("urlImdb"):
            meta["urlImdb"] = "https://www.imdb.com/title/%s/" % iid
        if iid and meta.get("type") != "series" and not meta.get("urlLb"):
            try:
                self._merge_lb(meta, self._lb_by_imdb(iid))
            except ApiError:
                pass
        try:
            self._rate_topup(meta)
        except Exception as e:
            _log("rate topup: %s" % e)
        return meta

    def _kp_flaky(self):
        return time.time() - getattr(self, "_kp_http_ts", 0) < 3600

    def _rate_topup(self, meta):
        iid = meta.get("imdbId")
        if not iid or not str(iid).startswith("tt"):
            return False
        changed = False
        if (meta.get("ratingKp") is None and meta.get("source") != "kp" and self._lang() == "ru"
                and self._kp_usable()):
            km = self._kp_from_imdb(iid, None, None, meta.get("type"))
            if km:
                for k in ("ratingKp", "ratingImdb"):
                    if meta.get(k) is None and km.get(k) is not None:
                        meta[k] = km[k]
                        changed = True
                if km.get("url") and not meta.get("urlKp"):
                    meta["urlKp"] = km["url"]
        if meta.get("ratingImdb") is None and self._omdb_ready():
            try:
                d = self._omdb_get({"i": iid}) or {}
            except ApiError:
                d = {}
            r = d.get("imdbRating")
            if r not in (None, "N/A") and _num(r) is not None:
                meta["ratingImdb"] = _num(r)
                changed = True
        return changed

    def _resolve(self, it):
        cfg = self._cfg
        ru = self._lang() == "ru"
        kp_cfg = bool(cfg["kp_api_key"]) and ru
        tm_ok = ru and cfg["fallback_source"] == "tmdb" and bool(cfg["tmdb_api_key"])
        om_ok = self._omdb_ready()
        parts = [p for p in split_mixed(it["title"]) if len(p) > 1]
        if parts:
            it = dict(it, alts=parts + [a for a in (it.get("alts") or []) if a not in parts])
        queries = []
        for t in parts + [it["title"]] + list(it.get("alts") or []):
            q = re.sub(r"[()\[\]{}]", " ", t or "")
            q = re.sub(r"\s+", " ", q).strip()
            if q and q not in queries:
                queries.append(q)
        if not queries:
            return "notfound", None, {}
        errs = set()
        meta = None
        try:
            if ru and self._kp_usable():
                try:
                    meta = self._step_kp(queries, it)
                except ApiError as e:
                    if e.code == "net":
                        raise
                    if e.code in ("auth", "limit", "rate"):
                        self._block_kp(e.code)
                    if e.code == "http":
                        self._kp_http_ts = time.time()
            if meta is None and tm_ok:
                try:
                    meta = self._step_tmdb(queries, it)
                except ApiError as e:
                    if e.code == "net":
                        raise
        except ApiError:
            return "neterr", None, {}
        if meta is None and not ru and self._kp_usable():
            try:
                meta = self._step_kp(queries, it)
                if meta is not None:
                    meta["via"] = "kp-search"
            except ApiError as e:
                if e.code == "net":
                    errs.add("net")
                elif e.code in ("auth", "limit", "rate"):
                    self._block_kp(e.code)
        if meta is None:
            steps = ([self._step_omdb] if om_ok else []) + [self._step_imdb]
            for step in steps:
                try:
                    meta = step(queries, it)
                except ApiError as e:
                    if e.code in ("net", "blocked"):
                        errs.add(e.code)
                except Exception as e:
                    _log("step %s failed: %s\n%s" % (step.__name__, e, traceback.format_exc()))
                if meta is not None:
                    break
        extra = {}
        if (ru and not kp_cfg) or (not ru and not om_ok):
            extra["hint"] = "nokey"
        warn = self._kp_warn() if kp_cfg else None
        if warn:
            extra["warn"] = warn
        if meta is None:
            if errs and (kp_cfg or tm_ok or om_ok):
                extra["soft"] = True
            elif "net" in errs:
                return "neterr", None, extra
            elif errs:
                return "webrate", None, extra
            if warn:
                return warn, None, extra
            return "notfound", None, extra
        try:
            meta = self._finalize(meta, it)
        except Exception as e:
            _log("finalize failed: %s" % e)
        return "ok", meta, extra

    def _view(self, it):
        with self._lock:
            meta = self._cache["items"].get(it["id"])
            nf = bool(meta and meta.get("miss"))
            meta = None if nf else self._present(meta)
        w = self._cfg.get("watched", {})
        v = {"id": it["id"], "kind": it["kind"], "title": it["title"], "year": it["year"],
             "added": it["added"], "nFiles": len(it["files"]), "hasLocalPoster": bool(it.get("poster")),
             "notFound": nf, "meta": meta, "files": [], "seasons": [],
             "inWatched": it["id"] in self._wd, "ghost": False,
             "hidden": it["id"] in self._cfg["hidden"],
             "pinned": self._cfg["pinned"].get(it["id"], 0)}
        if it["kind"] == "movie":
            v["files"] = [dict({"path": f["path"], "name": f["name"], "size": f["size"], "watched": f["path"] in w},
                               **({"fmt": f["fmt"]} if f.get("fmt") else {}))
                          for f in sorted(it["files"], key=lambda f: f["name"].lower())]
        else:
            by = {}
            for f in it["files"]:
                by.setdefault(f["season"] or 1, []).append(f)
            for s in sorted(by):
                eps = sorted(by[s], key=lambda f: (f["episode"] if f["episode"] is not None else 10 ** 6, f["name"].lower()))
                v["seasons"].append({"season": s, "episodes": [
                    {"episode": f["episode"], "path": f["path"], "name": f["name"], "size": f["size"],
                     "watched": f["path"] in w} for f in eps]})
        return v

    @safe
    def get_settings(self):
        s = {k: v for k, v in self._cfg.items() if k not in ("watched", "hidden", "pinned", "srv_tokens", "srv_pin", "srv_nopin")}
        s["config_path"] = CONFIG_PATH
        s["cache_path"] = CACHE_PATH
        s["poster_base"] = self._poster_base
        s["app_version"] = APP_VERSION
        s["match_v"] = MATCH_V
        if s.get("lang") not in ("ru", "en"):
            s["lang"] = "ru"
        if s.get("card_rating") not in ("kp", "imdb", "lb"):
            s["card_rating"] = "imdb"
        if s.get("sort") not in ("added", "rating", "yearDesc", "yearAsc", "title"):
            s["sort"] = "added"
        s["bg_base"] = self._poster_base.replace("/p?u=", "/bg") if self._poster_base else ""
        return s

    @safe
    def save_settings(self, data):
        allowed = {"player_mode", "player_path", "kp_api_key", "tmdb_api_key", "omdb_api_key", "lb_user", "fallback_source", "poster_size",
                   "bg_mode", "bg_color", "bg_dim", "bg_blur", "auto_update", "lang", "lang_set", "card_rating", "sort", "autostart"}
        flags = {"tray_close"}
        prev_key = self._cfg["kp_api_key"]
        if isinstance((data or {}).get("root_folders"), list):
            self._cfg["root_folders"] = self._norm_roots(data["root_folders"])
        for k, v in (data or {}).items():
            if k in allowed:
                self._cfg[k] = str(v or "").strip()
            elif k in flags:
                self._cfg[k] = "1" if str(v).strip().lower() in ("1", "true", "on") else "0"
        self._cfg["lb_user"] = lb_nick(self._cfg.get("lb_user"))
        if self._cfg["player_mode"] not in ("system", "custom"):
            self._cfg["player_mode"] = "system"
        if self._cfg["fallback_source"] not in ("none", "tmdb"):
            self._cfg["fallback_source"] = "none"
        self._cfg["auto_update"] = "0" if str(self._cfg.get("auto_update")) == "0" else "1"
        if self._cfg.get("lang") not in ("ru", "en"):
            self._cfg["lang"] = "ru"
        self._cfg["lang_set"] = "1" if str(self._cfg.get("lang_set")) == "1" else ""
        if self._cfg.get("card_rating") not in ("kp", "imdb", "lb"):
            self._cfg["card_rating"] = "imdb"
        if self._cfg.get("autostart") not in ("0", "min", "normal"):
            self._cfg["autostart"] = "0"
        if self._cfg.get("sort") not in ("added", "rating", "yearDesc", "yearAsc", "title"):
            self._cfg["sort"] = "added"
        if self._cfg.get("bg_mode") not in ("default", "color", "image"):
            self._cfg["bg_mode"] = "default"
        if not re.match(r"^#[0-9a-fA-F]{6}$", str(self._cfg.get("bg_color", ""))):
            self._cfg["bg_color"] = "#0a0a0a"
        for k, lo, hi, dv in (("bg_dim", 0, 90, 55), ("bg_blur", 0, 30, 0)):
            try:
                self._cfg[k] = str(max(lo, min(hi, int(float(self._cfg.get(k))))))
            except (TypeError, ValueError):
                self._cfg[k] = str(dv)
        try:
            self._cfg["poster_size"] = str(max(110, min(320, int(float(self._cfg.get("poster_size") or 176)))))
        except (TypeError, ValueError):
            self._cfg["poster_size"] = "176"
        if prev_key != self._cfg["kp_api_key"]:
            self._kp_dead = (None, 0)
        self._save_cfg()
        self._autostart_apply()
        return {"ok": True, "settings": self.get_settings()}

    def _autostart_apply(self):
        if os.name != "nt":
            return
        mode = self._cfg.get("autostart")
        try:
            import winreg
            exe = os.environ.get("KINO_EXE")
            if exe and os.path.isfile(exe):
                cmd = '"%s"' % exe
            elif getattr(sys, "frozen", False):
                cmd = '"%s"' % sys.executable
            else:
                pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
                cmd = '"%s" "%s"' % (pyw if os.path.isfile(pyw) else sys.executable, os.path.abspath(__file__))
            if mode == "min":
                cmd += " --minimized"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                                winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
                try:
                    cur = winreg.QueryValueEx(k, "Kino")[0]
                except OSError:
                    cur = None
                if mode in ("min", "normal"):
                    if cur != cmd:
                        winreg.SetValueEx(k, "Kino", 0, winreg.REG_SZ, cmd)
                elif cur is not None:
                    winreg.DeleteValue(k, "Kino")
        except Exception as e:
            _log("autostart: %s" % e)

    @safe
    def clip_get(self):
        return {"ok": True, "text": _clip_get()}

    @safe
    def clip_set(self, text):
        _clip_set(str(text or ""))
        return {"ok": True}

    @safe
    def get_poster_data(self, url):
        data = self._poster_bytes(url)
        if not data:
            raise ApiError("poster", "Не удалось загрузить постер")
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            mime = "image/png"
        elif data[:3] == b"\xff\xd8\xff":
            mime = "image/jpeg"
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            mime = "image/webp"
        elif data[:3] == b"GIF":
            mime = "image/gif"
        else:
            mime = "image/jpeg"
        return {"ok": True, "mime": mime, "b64": base64.b64encode(data).decode("ascii")}

    @safe
    def save_png(self, b64, name):
        try:
            data = base64.b64decode(b64 or "", validate=False)
        except (ValueError, TypeError):
            raise ApiError("poster", "Не удалось сохранить постер")
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            raise ApiError("poster", "Не удалось сохранить постер")
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", str(name or "poster")).strip(" .") or "poster"
        pics = os.path.join(os.path.expanduser("~"), "Pictures")
        res = self._dialog("save", directory=pics if os.path.isdir(pics) else "", save_filename=safe_name + ".png",
                           file_types=("PNG (*.png)",))
        if isinstance(res, (list, tuple)):
            res = res[0] if res else ""
        if not res:
            return {"ok": True, "path": ""}
        path = os.path.normpath(str(res))
        if not path.lower().endswith(".png"):
            path += ".png"
        with open(path, "wb") as f:
            f.write(data)
        return {"ok": True, "path": path}

    def _ensure_shortcut(self):
        if os.name != "nt" or self._cfg.get("shortcut_done") == "1":
            return
        exe = os.environ.get("KINO_EXE")
        args = ""
        icon = ""
        if exe and os.path.isfile(exe):
            target, icon = exe, exe + ",0"
        elif getattr(sys, "frozen", False):
            target, icon = sys.executable, sys.executable + ",0"
        elif not os.environ.get("KINO_BASE"):
            pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            target = pyw if os.path.isfile(pyw) else sys.executable
            args = '"%s"' % os.path.abspath(__file__)
            ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
            icon = ico if os.path.isfile(ico) else ""
        else:
            return
        ok = _make_shortcut("Desktop", target, args, icon)
        if ok:
            self._cfg["shortcut_done"] = "1"
            self._save_cfg()

    @safe
    def pick_folder(self):
        cur = (self._cfg.get("root_folders") or [""])[-1]
        res = self._dialog("folder", directory=cur if os.path.isdir(cur) else "")
        path = res[0] if res else ""
        return {"ok": True, "path": os.path.normpath(path) if path else ""}

    @safe
    def pick_player(self):
        cur = os.path.dirname(self._cfg.get("player_path") or "")
        res = self._dialog("open", directory=cur if os.path.isdir(cur) else "",
                           file_types=("Executable (*.exe)", "All files (*.*)"))
        path = res[0] if res else ""
        return {"ok": True, "path": os.path.normpath(path) if path else ""}

    @safe
    def scan(self):
        if self._rem():
            return self._remote_scan()
        all_roots = self._cfg.get("root_folders") or []
        roots = [r for r in all_roots if os.path.isdir(r)]
        if not all_roots:
            return {"ok": False, "error": "Папка не выбрана", "items": []}
        if not roots:
            return {"ok": False, "error": "Выбранные папки недоступны", "items": []}
        missing = [r for r in all_roots if r not in roots]
        items, paths = scan_library(roots)
        self._items = {it["id"]: it for it in items}
        self._paths = paths
        self._refresh_snaps()
        self._warm_posters()
        ghosts = [self._ghost_view(k, e) for k, e in self._wd.items() if k not in self._items]
        return {"ok": True, "roots": roots, "missing": missing, "items": [self._view(it) for it in items], "ghosts": ghosts}

    @safe
    def fetch_meta(self, item_id, force=False):
        if self._rem():
            return {"ok": False, "error": "Недоступно в режиме удалённой медиатеки"}
        it = self._items.get(item_id)
        if not it:
            return {"ok": False, "status": "error", "error": "Элемент не найден"}
        with self._lock:
            cached = self._cache["items"].get(item_id)
        upgrade = False
        stale = bool(cached and not cached.get("miss") and not cached.get("manual") and (cached.get("mv") or 1) < MATCH_V)
        if stale and cached.get("source") == "kp" and not (self._lang() == "ru" and self._kp_usable()):
            stale = False
        if cached and not force and not stale:
            if cached.get("miss"):
                if time.time() - cached.get("ts", 0) < 7 * 86400:
                    return {"ok": True, "status": "notfound", "item": self._view(it)}
            else:
                upgrade = bool(self._lang() == "ru" and self._cfg["kp_api_key"] and not cached.get("manual") and cached.get("source") != "kp"
                               and time.time() - cached.get("kp_tried", 0) > 7 * 86400 and self._kp_usable())
                if not upgrade:
                    if _rate_missing(cached) and time.time() - cached.get("rt_tried", 0) > 3 * 86400:
                        self._rate_topup(cached)
                        with self._lock:
                            cached["rt_tried"] = int(time.time())
                            self._save_cache()
                    return {"ok": True, "status": "ok", "item": self._view(it)}
        try:
            status, meta, extra = self._resolve(it)
        except Exception as e:
            _log("resolve error: %s\n%s" % (e, traceback.format_exc()))
            status, meta, extra = "error", None, {}
        if stale and (status != "ok" or (cached.get("source") == "kp" and meta.get("source") != "kp")):
            if status in ("ok", "notfound"):
                with self._lock:
                    cached["mv"] = MATCH_V
                    self._save_cache()
            return {"ok": True, "status": "ok", "item": self._view(it)}
        if upgrade and not (status == "ok" and meta.get("source") == "kp"):
            km = None
            if cached.get("imdbId"):
                km = self._kp_from_imdb(cached["imdbId"], None, None, cached.get("type"))
            if km:
                try:
                    meta = self._finalize(km, it)
                except Exception:
                    meta = km
                status = "ok"
            else:
                with self._lock:
                    if not self._kp_flaky():
                        cached["kp_tried"] = int(time.time())
                    if self._rate_topup(cached):
                        cached["rt_tried"] = int(time.time())
                    self._save_cache()
                return {"ok": True, "status": "ok", "item": self._view(it)}
        if status == "ok":
            meta["manual"] = False
            meta["mv"] = MATCH_V
            meta["ts"] = int(time.time())
            if meta.get("source") != "kp":
                meta["kp_tried"] = int(time.time()) if (self._lang() == "ru" and self._cfg["kp_api_key"] and not self._kp_warn() and not self._kp_flaky()) else 0
            with self._lock:
                self._cache["items"][item_id] = meta
                self._save_cache()
        elif status == "notfound":
            with self._lock:
                soft = bool((extra or {}).get("soft"))
                self._cache["items"][item_id] = {"miss": True, "ts": int(time.time()) - (7 * 86400 - 3600 if soft else 0)}
                self._save_cache()
        out = {"ok": True, "status": status, "item": self._view(it)}
        out.update(extra or {})
        return out

    @safe
    def get_local_poster(self, item_id):
        if self._rem():
            return self._remote_poster(item_id)
        if item_id in self._local_cache:
            return self._local_cache[item_id]
        it = self._items.get(item_id)
        p = it.get("poster") if it else None
        if not p or not os.path.isfile(p) or os.path.getsize(p) > 8 * 1024 * 1024:
            return ""
        ext = os.path.splitext(p)[1].lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        with open(p, "rb") as f:
            uri = "data:%s;base64,%s" % (mime, base64.b64encode(f.read()).decode("ascii"))
        self._local_cache[item_id] = uri
        return uri

    @safe
    def search_candidates(self, query, source):
        if self._rem():
            return {"ok": False, "error": "Недоступно в режиме удалённой медиатеки"}
        q = (query or "").strip()
        if not q:
            return {"ok": False, "error": "Введите название, ID или ссылку"}
        km = re.search(r"kinopoisk\.[a-z]+/(?:film|series|level/\d+/film)/(\d+)", q)
        lm = re.search(r"letterboxd\.com/film/([A-Za-z0-9_.\-]+)", q)
        im = re.search(r"imdb\.com/title/(tt\d+)", q) or re.fullmatch(r"(tt\d{6,10})", q)
        tm = re.search(r"themoviedb\.org/(movie|tv)/(\d+)", q)
        need_kp = {"ok": False, "error": "Не указан API-ключ Кинопоиска (Настройки)"}
        need_tm = {"ok": False, "error": "Не указан API-ключ TMDB (Настройки)"}
        try:
            if km or (q.isdigit() and source == "kp"):
                if not self._cfg["kp_api_key"]:
                    return need_kp
                res = [self._kp_details(km.group(1) if km else q)]
            elif lm:
                res = [self._lb_to_meta(self._lb_film(lm.group(1)))]
            elif im:
                iid = im.group(1)
                res = [c for c in self._imdb_search(iid) if c["ext_id"] == iid]
                if not res:
                    lb = self._lb_by_imdb(iid)
                    res = [self._lb_to_meta(lb)] if lb else []
            elif tm or (q.isdigit() and source == "tmdb"):
                if not self._cfg["tmdb_api_key"]:
                    return need_tm
                if tm:
                    res = [self._tmdb_details("%s:%s" % (tm.group(1), tm.group(2)))]
                else:
                    res = []
                    for mt in ("movie", "tv"):
                        try:
                            res.append(self._tmdb_details("%s:%s" % (mt, q)))
                        except ApiError as e:
                            if e.code != "notfound":
                                raise
            elif source == "tmdb":
                if not self._cfg["tmdb_api_key"]:
                    return need_tm
                res = self._tmdb_search(q)
            elif source == "imdb":
                res = self._imdb_search(q)
            elif source == "lb":
                res = [{"source": "lb", "ext_id": c["slug"], "titleRu": c["title"], "titleOrig": None,
                        "year": c["year"], "type": "movie", "genres": [], "countries": [], "poster": None,
                        "posterPreview": None, "description": "", "duration": None,
                        "url": "%s/film/%s/" % (LB_BASE, c["slug"])} for c in self._lb_search(q)]
            else:
                if not self._cfg["kp_api_key"]:
                    return need_kp
                res = self._kp_search(q)
                if not res and looks_translit(q):
                    for v in translit_variants(q):
                        res = self._kp_search(v)
                        if res:
                            break
        except ApiError as e:
            if e.code == "notfound":
                return {"ok": True, "results": []}
            msgs = {"net": "Нет подключения к интернету", "auth": "API-ключ отклонён",
                    "limit": "Суточный лимит запросов исчерпан", "rate": "Слишком много запросов, подождите",
                    "blocked": "Сайт временно блокирует запросы, попробуйте позже",
                    "http": "Сервис временно недоступен, попробуйте позже"}
            return {"ok": False, "error": msgs.get(e.code, "Ошибка запроса: %s" % e)}
        return {"ok": True, "results": res[:15]}

    @safe
    def apply_match(self, item_id, cand):
        if self._rem():
            return {"ok": False, "error": "Недоступно в режиме удалённой медиатеки"}
        it = self._items.get(item_id)
        if not it:
            return {"ok": False, "error": "Элемент не найден"}
        src = cand.get("source")
        meta = None
        try:
            if src == "kp":
                meta = self._kp_details(cand["ext_id"])
            elif src == "tmdb":
                meta = self._tmdb_details(cand["ext_id"])
            elif src == "imdb":
                meta = self._meta_from_imdb(cand, it)
            elif src == "lb":
                meta = self._lb_finish(self._lb_film(cand["ext_id"]))
        except ApiError:
            meta = None
        if not meta:
            meta = dict(cand)
        try:
            meta = self._finalize(meta, it)
        except Exception as e:
            _log("finalize failed: %s" % e)
        meta["manual"] = True
        meta["ts"] = int(time.time())
        with self._lock:
            self._cache["items"][item_id] = meta
            self._save_cache()
        return {"ok": True, "item": self._view(it)}

    @staticmethod
    def _meta_keys(m):
        ks = set()
        if m.get("source") and m.get("ext_id") is not None:
            ks.add(("id", "%s:%s" % (m["source"], m["ext_id"])))
        if m.get("imdbId"):
            ks.add(("imdb", m["imdbId"]))
        lbm = re.search(r"/film/([^/]+)/", str(m.get("urlLb") or ""))
        if lbm:
            ks.add(("id", "lb:%s" % lbm.group(1)))
        for t in (m.get("titleRu"), m.get("titleOrig")):
            n = norm(t)
            if n:
                ks.add(("t", n, m.get("year")))
        return ks

    def _wl_all_keys(self):
        ks = set()
        for e in self._wl["items"]:
            ks |= self._meta_keys(e.get("meta") or {})
        return ks

    def _library_keys(self):
        ks = set()
        for it in self._items.values():
            for t in [it["title"]] + list(it.get("alts") or []):
                n = norm(t)
                if n:
                    ks.add(("t", n, it["year"]))
            m = self._cache["items"].get(it["id"])
            if m and not m.get("miss"):
                ks |= self._meta_keys(m)
        return ks

    def _wl_save(self):
        with self._lock:
            _save_json(WATCHLIST_PATH, self._wl)

    @safe
    def wl_search(self, query):
        q = re.sub(r"\s+", " ", (query or "")).strip()
        year = None
        ym = re.search(r"\s\(?((?:19|20)\d\d)\)?$", q)
        if ym and len(q) - len(ym.group(0)) >= 2:
            year = int(ym.group(1))
            q = q[:ym.start()].strip()
        if len(q) < 2:
            return {"ok": True, "results": [], "notes": []}
        ck = q.lower() + ("|%s" % year if year else "")
        cfg = self._cfg
        notes, results, codes = [], None, set()
        if ck in self._wl_cache:
            results = [dict(c) for c in self._wl_cache[ck]]
        else:
            found = []

            def run(fn, *a):
                try:
                    return fn(*a)
                except ApiError as e:
                    codes.add(e.code)
                    if e.code in ("auth", "limit", "rate"):
                        self._block_kp(e.code)
                    return []

            if cfg["kp_api_key"] and self._kp_usable():
                res = run(self._kp_search, q)
                if not res and looks_translit(q) and not (codes & {"net", "auth", "limit", "rate"}):
                    for v in translit_variants(q):
                        res = run(self._kp_search, v)
                        if res:
                            break
                found += res
            if cfg["fallback_source"] == "tmdb" and cfg["tmdb_api_key"]:
                found += run(self._tmdb_search, q)
            if self._omdb_ready() and re.search(r"[A-Za-z]", q):
                found += run(self._omdb_search, q, year)
                if year:
                    found += run(self._omdb_search, q)
            if re.search(r"[A-Za-z]", q):
                found += run(self._imdb_search, q)
            seen, results = set(), []
            for c in found:
                ks = self._meta_keys(c)
                ks_t = {k for k in ks if k[0] == "t"}
                if ks_t & seen:
                    continue
                seen |= ks_t
                results.append(c)
            if year:
                results.sort(key=lambda c: 0 if c.get("year") == year else 1)
            results = results[:12]
            if results or not codes:
                self._wl_cache[ck] = [dict(c) for c in results]
                if len(self._wl_cache) > 60:
                    self._wl_cache.pop(next(iter(self._wl_cache)))
        if not results:
            if "net" in codes:
                return {"ok": False, "error": "Нет подключения к интернету"}
            if "limit" in codes:
                notes.append("Суточный лимит Кинопоиска исчерпан — продолжим завтра, пока работают IMDb и TMDB.")
            elif "auth" in codes:
                notes.append("API-ключ Кинопоиска отклонён — проверьте его в настройках.")
        if (not cfg["kp_api_key"] and not (cfg["fallback_source"] == "tmdb" and cfg["tmdb_api_key"])
                and re.search(r"[А-Яа-яЁё]", q)):
            notes.append("Русские названия лучше всего находятся с ключом Кинопоиска (Настройки). Без него попробуйте латиницей.")
        have = self._wl_all_keys()
        for c in results:
            ks = self._meta_keys(c)
            c["inList"] = bool(ks & have) or any(("t", k[1], None) in have for k in ks if k[0] == "t")
        return {"ok": True, "results": results, "notes": notes}

    def _wl_meta_from_cand(self, cand):
        meta = {k: v for k, v in cand.items() if k not in ("adding", "inList", "stars", "qid")}
        try:
            if cand["source"] == "kp" and self._kp_usable():
                meta = self._kp_details(cand["ext_id"])
            elif cand["source"] == "tmdb" and self._cfg.get("tmdb_api_key"):
                meta = self._tmdb_details(cand["ext_id"])
            elif cand["source"] == "imdb" and self._lang() == "ru":
                m = self._kp_from_imdb(cand["ext_id"], cand.get("titleOrig"), cand.get("year"), cand.get("type") or "movie")
                if m:
                    meta = m
        except ApiError as e:
            if e.code in ("auth", "limit", "rate"):
                self._block_kp(e.code)
        if meta.get("imdbId") and not meta.get("urlImdb"):
            meta["urlImdb"] = "https://www.imdb.com/title/%s/" % meta["imdbId"]
        return meta

    @safe
    def wl_rematch(self, key, cand):
        if not isinstance(cand, dict) or not cand.get("source") or cand.get("ext_id") is None:
            return {"ok": False, "error": "Некорректный вариант"}
        with self._lock:
            e = next((x for x in self._wl["items"] if x.get("key") == key), None)
        if not e:
            return {"ok": False, "error": "Элемент не найден"}
        meta = self._wl_meta_from_cand(cand)
        old = e.get("meta") or {}
        if old.get("urlLb"):
            meta["urlLb"] = old["urlLb"]
        meta.pop("lb_pending", None)
        meta["wl_manual"] = 1
        meta["wl_rich_t"] = 0
        with self._lock:
            e["meta"] = meta
        self._wl_save()
        return {"ok": True, "items": self.wl_list()["items"]}

    @safe
    def wl_add(self, cand):
        if not isinstance(cand, dict) or not cand.get("source") or cand.get("ext_id") is None:
            return {"ok": False, "error": "Некорректный вариант"}
        if self._meta_keys(cand) & self._wl_all_keys():
            return {"ok": True, "items": self.wl_list()["items"]}
        meta = self._wl_meta_from_cand(cand)
        with self._lock:
            self._wl["items"].insert(0, {"key": "%s:%s" % (meta.get("source"), meta.get("ext_id")),
                                         "added": int(time.time()), "meta": meta})
        self._wl_save()
        return {"ok": True, "items": self.wl_list()["items"]}

    def _wl_enrich_meta(self, m):
        memo = {}
        if not (m.get("description") or any(_descs_of(m).values())):
            order = list(self._desc_order()) + [x for x in ("kp", "imdb") if x not in self._desc_order()]
            for sel in order:
                if sel == "kp" and not self._kp_usable():
                    continue
                try:
                    val = self._desc_fetch(sel, m, memo)
                except Exception:
                    val = None
                if val:
                    _descs_of(m)[sel] = val
                    if not m.get("description"):
                        m["description"] = val
                    break
        if m.get("ratingImdb") is None and m.get("imdbId") and self._omdb_ready():
            try:
                d = self._omdb_get({"i": m["imdbId"]}) or {}
                v = d.get("imdbRating")
                if v and v != "N/A":
                    m["ratingImdb"] = float(v)
            except Exception:
                pass
        m["wl_rich_t"] = int(time.time())

    @safe
    def wl_enrich(self, key):
        with self._lock:
            e = next((x for x in self._wl["items"] if x.get("key") == key), None)
        if not e:
            return {"ok": False}
        m = e.get("meta") or {}
        if int(time.time()) - int(m.get("wl_rich_t") or 0) > 6 * 3600:
            try:
                self._wl_enrich_meta(m)
            except Exception as ex:
                _log("wl_enrich: %s" % ex)
            self._wl_save()
        row = self._present(m) or {}
        return {"ok": True, "meta": row}

    def _lb_slug_of(self, e):
        m = e.get("meta") or {}
        mm = re.search(r"/film/([^/]+)/", str(m.get("urlLb") or ""))
        if mm:
            return mm.group(1)
        if m.get("source") == "lb":
            return str(m.get("ext_id"))
        return None

    def _lb_skip_add(self, e):
        slug = self._lb_slug_of(e)
        if slug:
            skip = self._wl.setdefault("lb_skip", [])
            if slug not in skip:
                skip.append(slug)

    @safe
    def wl_remove(self, key):
        with self._lock:
            for e in self._wl["items"]:
                if e.get("key") == key:
                    self._lb_skip_add(e)
            self._wl["items"] = [e for e in self._wl["items"] if e.get("key") != key]
            self._cfg["pinned"].pop("w|" + str(key), None)
        self._wl_save()
        self._save_cfg()
        return {"ok": True, "items": self.wl_list()["items"]}

    @safe
    def wl_to_watched(self, key):
        with self._lock:
            e = next((x for x in self._wl["items"] if x.get("key") == key), None)
            if not e:
                return {"ok": False, "error": "Элемент не найден"}
            meta = e.get("meta") or {}
            wid = "wl:%s" % key
            self._wd[wid] = {"ts": int(time.time()), "snap": {
                "kind": meta.get("type") or "movie",
                "title": meta.get("titleRu") or meta.get("titleOrig") or "Без названия",
                "year": meta.get("year"), "meta": meta}}
            self._lb_skip_add(e)
            self._wl["items"] = [x for x in self._wl["items"] if x.get("key") != key]
            self._cfg["pinned"].pop("w|" + str(key), None)
        self._wl_save()
        self._save_cfg()
        self._save_wd()
        return {"ok": True, "items": self.wl_list()["items"], "ghost": self._ghost_view(wid, self._wd[wid])}

    @safe
    def wl_lb_sync(self, user=None):
        nick = lb_nick(user if user is not None else self._cfg.get("lb_user"))
        if not nick:
            return {"ok": False, "error": "Укажите ник Letterboxd (например: idlorem)"}
        films, seen = [], set()
        err = None
        first_html = None
        for page in range(1, 41):
            url = "%s/%s/watchlist/%s" % (LB_BASE, nick, "" if page == 1 else "page/%d/" % page)
            try:
                r = self._web_get(url, throttle=True)
            except ApiError as e:
                err = e.code
                break
            if page == 1:
                first_html = r.text
            got, nxt = parse_lb_watchlist(r.text)
            new = [g for g in got if g["slug"] not in seen]
            for g in new:
                seen.add(g["slug"])
                films.append(g)
            if not new or not nxt:
                break
        if err and not films:
            msg = {"notfound": "Профиль или вотчлист не найден. Проверьте ник и что вотчлист открыт для всех.",
                   "net": "Нет подключения к интернету",
                   "blocked": self._lb_wait_msg(),
                   "rate": self._lb_wait_msg()}.get(err, "Не удалось загрузить вотчлист (%s)" % err)
            return {"ok": False, "error": msg}
        if not films:
            return {"ok": False, "error": "Вотчлист пуст или закрыт в настройках приватности Letterboxd."}
        self._cfg["lb_user"] = nick
        self._save_cfg()
        prof = self._lb_fetch_profile(nick, first_html)
        prof["watchlist"] = len(films)
        self._wl["lb_profile"] = prof
        bylug = {g["slug"]: g for g in films}
        with self._lock:
            for e in self._wl["items"]:
                if self._wl_lb_suspect(e):
                    sl = self._lb_slug_of(e)
                    e["meta"] = self._lb_skeleton(sl, bylug.get(sl))
        have = self._wl_all_keys()
        skip = set(self._wl.get("lb_skip") or [])
        watched_keys = set()
        for we in self._wd.values():
            watched_keys |= self._meta_keys((we.get("snap") or {}).get("meta") or {})
        added = 0
        with self._lock:
            for g in reversed(films):
                if g["slug"] in skip:
                    continue
                meta = {"source": "lb", "ext_id": g["slug"], "titleRu": g["title"], "titleOrig": None, "year": g["year"],
                        "type": "movie", "description": "", "genres": [], "countries": [],
                        "urlLb": "%s/film/%s/" % (LB_BASE, g["slug"]), "lb_pending": 1}
                ks = self._meta_keys(meta)
                if ks & have or ks & watched_keys:
                    continue
                have |= ks
                self._wl["items"].insert(0, {"key": "lb:%s" % g["slug"], "added": int(time.time()), "meta": meta})
                added += 1
        self._wl_save()
        pending = sum(1 for e in self._wl["items"] if (e.get("meta") or {}).get("lb_pending"))
        return {"ok": True, "nick": nick, "total": len(films), "added": added, "pending": pending,
                "profile": prof, "items": self.wl_list()["items"]}

    def _lb_fetch_profile(self, nick, seed=None):
        old = self._wl.get("lb_profile") or {}
        prof = {"nick": nick, "name": None, "avatar": None, "films": None, "watchlist": None, "err": None}
        if old.get("nick") == nick:
            prof.update({k: old.get(k) for k in ("name", "avatar", "films", "watchlist")})
        if seed:
            got = parse_lb_profile(seed, nick)
            for k in ("avatar", "films", "name"):
                if got.get(k) not in (None, ""):
                    prof[k] = got[k]
        blocked_recently = old.get("nick") == nick and old.get("err") == "HTTP 403" and time.time() - float(old.get("ts403") or 0) < 86400
        if blocked_recently:
            prof["err"] = old.get("err")
            prof["ts403"] = old.get("ts403")
        if (prof.get("films") is None or not prof.get("avatar")) and not blocked_recently:
            try:
                pr = self._web_get("%s/%s/" % (LB_BASE, nick), throttle=True, soft=True)
                got = parse_lb_profile(pr.text, nick)
                for k in ("avatar", "films", "name"):
                    if got.get(k) not in (None, ""):
                        prof[k] = got[k]
                if got.get("films") is None and not got.get("avatar"):
                    prof["err"] = "страница профиля не содержит ожидаемых данных"
                    _log("lb profile: no data parsed, html len %d" % len(pr.text or ""))
                    try:
                        with open(os.path.join(APP_DIR, "lb_profile_debug.html"), "w", encoding="utf-8") as f:
                            f.write((pr.text or "")[:40000])
                    except OSError:
                        pass
            except ApiError as e:
                prof["err"] = str(e)
                if "403" in str(e):
                    prof["ts403"] = time.time()
                _log("lb profile: %s" % e)
        if not prof.get("name") and not blocked_recently:
            try:
                rr = self._web_get("%s/%s/rss/" % (LB_BASE, nick), throttle=True, soft=True)
                tm = re.search(r"<title>\s*Letterboxd\s*[-–]\s*(.*?)\s*</title>", rr.text or "", re.S)
                if tm:
                    prof["name"] = unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", tm.group(1))).strip() or None
            except ApiError as e:
                _log("lb rss: %s" % e)
        return prof

    @safe
    def lb_profile_refresh(self):
        nick = self._cfg.get("lb_user")
        if not nick:
            return {"ok": True, "profile": None}
        old = self._wl.get("lb_profile") or {}
        if old.get("nick") == nick and old.get("films") is not None and old.get("avatar") and old.get("name"):
            return {"ok": True, "profile": old}
        prof = self._lb_fetch_profile(nick)
        if prof.get("watchlist") is None:
            prof["watchlist"] = sum(1 for e in self._wl["items"] if self._lb_slug_of(e))
        self._wl["lb_profile"] = prof
        self._wl_save()
        return {"ok": True, "profile": prof}

    def _lb_wait_msg(self):
        left = max(self._gate_dead.get("letterboxd.com", 0.0), self._gate_cool.get("letterboxd.com", 0.0)) - time.time()
        if left > 5:
            return "Letterboxd временно ограничил запросы. Повторите через %d мин." % max(1, int(left / 60 + 0.99))
        return "Letterboxd временно ограничил запросы. Попробуйте чуть позже."

    @safe
    def lb_profile(self):
        p = self._wl.get("lb_profile")
        nick = self._cfg.get("lb_user")
        if nick and (not p or p.get("nick") != nick):
            p = {"nick": nick, "avatar": None, "films": None, "watchlist": None}
        return {"ok": True, "profile": p if nick else None}

    @safe
    def lb_unlink(self):
        self._cfg["lb_user"] = ""
        self._save_cfg()
        self._wl.pop("lb_profile", None)
        self._wl_save()
        return {"ok": True}

    def _lb_fill_from_imdb(self, meta, lb):
        iid = lb.get("imdbId")
        if not iid or not self._omdb_ready():
            return
        try:
            d = self._omdb_get({"i": iid, "plot": "full"}) or {}
        except ApiError as ex:
            if ex.code == "net":
                raise
            return
        rating = d.get("imdbRating")
        if rating not in (None, "N/A") and meta.get("ratingImdb") is None:
            try:
                meta["ratingImdb"] = float(rating)
            except ValueError:
                pass
        plot = d.get("Plot")
        if plot not in (None, "N/A") and not meta.get("description"):
            meta["description"] = plot
        if not meta.get("duration"):
            meta["duration"] = _omdb_minutes(d.get("Runtime"))
        if not meta.get("genres") and d.get("Genre") not in (None, "N/A"):
            meta["genres"] = _omdb_ru((d.get("Genre") or "").split(","), "g")
        if not meta.get("countries") and d.get("Country") not in (None, "N/A"):
            meta["countries"] = _omdb_ru((d.get("Country") or "").split(","), "c")
        meta["urlImdb"] = "https://www.imdb.com/title/%s/" % iid

    def _wl_lb_meta(self, e):
        slug = self._lb_slug_of(e)
        lb = self._lb_film(slug)
        meta = None
        if self._lang() == "ru" and lb.get("imdbId"):
            meta = self._kp_from_imdb(lb["imdbId"], None, lb.get("year"), "movie")
        if meta is not None:
            self._merge_lb(meta, lb, fill=True)
            if not meta.get("description") and lb.get("description"):
                meta["description"] = lb["description"]
        else:
            meta = self._lb_to_meta(lb)
            self._lb_fill_from_imdb(meta, lb)
        meta.pop("lb_pending", None)
        meta["lb_v"] = 2
        meta["urlLb"] = lb["url"]
        if lb.get("imdbId") and not meta.get("imdbId"):
            meta["imdbId"] = lb["imdbId"]
        return meta

    def _lb_skeleton(self, slug, g=None):
        ym = re.search(r"-((?:18|19|20)\d{2})$", slug)
        base = re.sub(r"-(?:18|19|20)\d{2}$", "", slug).replace("-", " ").strip().title()
        title = (g or {}).get("title") or base or slug
        year = (g or {}).get("year") or (int(ym.group(1)) if ym else None)
        return {"source": "lb", "ext_id": slug, "titleRu": title, "titleOrig": None, "year": year,
                "type": "movie", "description": "", "genres": [], "countries": [],
                "urlLb": "%s/film/%s/" % (LB_BASE, slug), "lb_pending": 1}

    def _wl_lb_suspect(self, e):
        m = e.get("meta") or {}
        if m.get("lb_pending") or m.get("lb_v") == 2 or m.get("wl_manual") or m.get("source") == "lb":
            return False
        slug = self._lb_slug_of(e)
        if not slug:
            return False
        base = re.sub(r"-(?:18|19|20)\d{2}$", "", slug).replace("-", " ")
        ym = re.search(r"-((?:18|19|20)\d{2})$", slug)
        sim = title_sim([m.get("titleRu"), m.get("titleOrig"), m.get("titleEn")], [base])
        bad_year = bool(ym and m.get("year") and abs(int(ym.group(1)) - int(m["year"])) > 1)
        return sim < 0.6 or bad_year

    @safe
    def wl_lb_fill(self, limit=5):
        with self._lock:
            todo = [e for e in self._wl["items"] if (e.get("meta") or {}).get("lb_pending")]
        out, stop = [], False
        lib = self._library_keys()
        for e in todo[:max(1, min(8, int(limit or 5)))]:
            try:
                newm = self._wl_lb_meta(e)
            except ApiError as ex:
                if ex.code == "notfound":
                    e["meta"]["lb_pending"] = 0
                    continue
                stop = True
                break
            with self._lock:
                e["meta"] = newm
            out.append(self._wl_row(e, lib))
        if todo:
            self._wl_save()
        left = sum(1 for e in self._wl["items"] if (e.get("meta") or {}).get("lb_pending"))
        return {"ok": True, "updates": out, "remaining": left if not stop else 0, "stop": stop}

    def _wl_row(self, e, lib):
        ks = self._meta_keys(e.get("meta") or {})
        inlib = bool(ks & lib) or any(("t", k[1], None) in lib for k in ks if k[0] == "t")
        return {"key": e.get("key"), "added": e.get("added", 0), "meta": self._present(e.get("meta") or {}) or {}, "inLibrary": inlib,
                "pinned": self._cfg["pinned"].get("w|" + str(e.get("key")), 0)}

    def _en_lookup(self, m):
        iid = m.get("imdbId")
        if iid:
            r = self._web_get(IMDB_SUGGEST + quote(iid, safe="") + ".json")
            try:
                for d in (r.json().get("d") or []):
                    if d.get("id") == iid and d.get("l"):
                        return d["l"]
            except ValueError:
                return None
            return None
        q = m.get("titleOrig") or m.get("titleRu")
        if not q or not m.get("year"):
            return None
        for i, c in enumerate(self._imdb_search(q)[:3]):
            if c.get("year") == m.get("year") and c.get("type") == m.get("type", "movie") and i == 0:
                return c.get("titleOrig")
        return None

    @safe
    def fill_en_titles(self, limit=8):
        todo = []
        with self._lock:
            for k, m in self._cache["items"].items():
                if m and not m.get("miss") and not m.get("titleEn") and not m.get("en_tried"):
                    todo.append(("id", k, m))
            for e in self._wl["items"]:
                m = e.get("meta") or {}
                if m and not m.get("titleEn") and not m.get("en_tried"):
                    todo.append(("key", e.get("key"), m))
        out = []
        for kind, k, m in todo[:max(1, min(20, int(limit or 8)))]:
            try:
                t = self._en_lookup(m)
            except Exception:
                t = None
            with self._lock:
                m["en_tried"] = 1
                if t:
                    m["titleEn"] = t
                    out.append({kind: k, "titleEn": t})
        if todo:
            with self._lock:
                self._save_cache()
                self._wl_save()
        return {"ok": True, "updates": out, "remaining": max(0, len(todo) - limit)}

    def _lang(self):
        return "en" if self._cfg.get("lang") == "en" else "ru"

    def _desc_order(self):
        return ("imdb", "lb") if self._lang() == "en" else ("kp", "lb")

    def _present(self, meta):
        if not meta:
            return meta
        out = None
        sel = meta.get("poster_sel")
        posters = meta.get("posters")
        if sel == "none":
            out = dict(meta)
            out["poster"] = ""
            out["posterPreview"] = ""
        elif sel in POSTER_SOURCES and isinstance(posters, dict):
            e = posters.get(sel)
            if e and e.get("poster"):
                out = dict(meta)
                out["poster"] = e["poster"]
                out["posterPreview"] = e.get("preview") or e["poster"]
        descs = meta.get("descs")
        if isinstance(descs, dict):
            for s in self._desc_order():
                if descs.get(s):
                    if out is None:
                        out = dict(meta)
                    out["description"] = descs[s]
                    break
        return out if out is not None else meta

    def _poster_fetch(self, sel, m, memo):
        iid = m.get("imdbId")
        if sel == "imdb":
            if not iid:
                return None
            r = self._web_get(IMDB_SUGGEST + quote(iid, safe="") + ".json")
            for d in (r.json().get("d") or []):
                img = (d.get("i") or {}).get("imageUrl")
                if d.get("id") == iid and img:
                    return {"poster": _upscale_imdb(img, 500), "preview": img}
            return None
        if sel == "lb":
            lb = self._lb_memo(iid, memo)
            if not lb:
                lm = re.search(r"/film/([^/]+)/", str(m.get("urlLb") or ""))
                if lm:
                    lb = self._lb_film(lm.group(1))
            if lb and lb.get("poster"):
                return {"poster": lb["poster"], "preview": lb["poster"]}
            return None
        d = self._kp_meta_for(m)
        if d and d.get("poster"):
            return {"poster": d["poster"], "preview": d.get("posterPreview") or d["poster"]}
        return None

    def _desc_fetch(self, sel, m, memo):
        iid = m.get("imdbId")
        if sel == "imdb":
            if not iid:
                return None
            if self._omdb_ready():
                d = self._omdb_get({"i": iid, "plot": "full"}) or {}
                plot = d.get("Plot")
                if plot and plot != "N/A":
                    return plot
            r = self._web_get("https://www.imdb.com/title/%s/" % quote(iid, safe=""))
            return parse_imdb_plot(r.text)
        if sel == "lb":
            lb = self._lb_memo(iid, memo)
            return (lb or {}).get("description") or None
        d = self._kp_meta_for(m)
        return (d or {}).get("description") or None

    def _lb_memo(self, iid, memo):
        if not iid:
            return None
        if iid not in memo:
            memo[iid] = self._lb_by_imdb(iid)
        return memo[iid]

    def _kp_meta_for(self, m):
        if m.get("source") == "kp" and m.get("ext_id"):
            return self._kp_details(m["ext_id"])
        if m.get("imdbId"):
            return self._kp_from_imdb(m["imdbId"], m.get("titleOrig"), m.get("year"), m.get("type") or "movie")
        return None

    def _wanted(self, m):
        tasks = []
        order = list(self._desc_order())
        descs = _descs_of(m)
        for s in order:
            if descs.get(s):
                break
            tasks.append(("desc", s))
        tried = m.get("z_tried") or []
        return [(k, s) for k, s in tasks if "%s:%s" % (k, s) not in tried]

    def _update_row(self, kind, k, m):
        v = self._present(m)
        return {kind: k, "poster": v.get("poster"), "posterPreview": v.get("posterPreview"),
                "description": v.get("description"), "posterSel": v.get("poster_sel")}

    def _present_updates(self):
        out = []
        with self._lock:
            for k, m in self._cache["items"].items():
                if m and not m.get("miss"):
                    out.append(self._update_row("id", k, m))
            for e in self._wl["items"]:
                m = e.get("meta") or {}
                if m:
                    out.append(self._update_row("key", e.get("key"), m))
            for k, e in self._wd.items():
                m = (e.get("snap") or {}).get("meta")
                if m:
                    out.append(self._update_row("id", k, m))
        return out

    @safe
    def set_item_poster(self, kind, key, src):
        if self._rem():
            return {"ok": False, "error": "Недоступно в режиме удалённой медиатеки"}
        if src not in (None, "", "none") and src not in POSTER_SOURCES:
            return {"ok": False, "error": "Неизвестный источник"}
        with self._lock:
            m = None
            if kind == "key":
                e = next((x for x in self._wl["items"] if x.get("key") == key), None)
                m = (e or {}).get("meta")
            else:
                m = self._cache["items"].get(key)
                if not m or m.get("miss"):
                    m = ((self._wd.get(key) or {}).get("snap") or {}).get("meta")
        if not m:
            return {"ok": False, "error": "Нет данных о фильме"}
        if not src:
            m.pop("poster_sel", None)
        elif src == "none":
            m["poster_sel"] = "none"
        else:
            if src == "kp" and not self._kp_usable():
                return {"ok": False, "error": "Для Кинопоиска нужен API-ключ в настройках"}
            try:
                val = self._poster_fetch(src, m, {})
            except ApiError as e:
                return {"ok": False, "error": "Нет подключения к интернету" if e.code == "net" else "Источник временно недоступен"}
            except Exception:
                val = None
            if not val:
                return {"ok": False, "error": "В этом источнике постер не найден"}
            _posters_of(m)[src] = val
            m["poster_sel"] = src
        with self._lock:
            self._save_cache()
            self._wl_save()
            self._save_wd()
        return {"ok": True, "row": self._update_row(kind, key, m)}

    def _imdb_ds_path(self):
        return os.path.join(APP_DIR, "imdb_ratings.db")

    def _imdb_ds_ok(self, fresh=True):
        p = self._imdb_ds_path()
        try:
            if os.path.getsize(p) < 1000000:
                return False
            return (not fresh) or time.time() - os.path.getmtime(p) < IMDB_DS_MAX_AGE
        except OSError:
            return False

    def _imdb_ds_build(self):
        import gzip
        import sqlite3
        p = self._imdb_ds_path()
        gz, tmp = p + ".gz.part", p + ".part"
        r = self._http.get(IMDB_DS_URL, timeout=60, stream=True, headers={"User-Agent": BROWSER_UA})
        if r.status_code != 200:
            raise ApiError("http", "datasets HTTP %s" % r.status_code)
        with open(gz, "wb") as fh:
            for chunk in r.iter_content(65536):
                fh.write(chunk)
        if os.path.exists(tmp):
            os.remove(tmp)
        db = sqlite3.connect(tmp)
        try:
            db.execute("create table r(id text primary key, v real) without rowid")
            batch = []
            with gzip.open(gz, "rt", encoding="utf-8") as fh:
                next(fh, None)
                for line in fh:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 2 or not parts[0].startswith("tt"):
                        continue
                    try:
                        batch.append((parts[0], float(parts[1])))
                    except ValueError:
                        continue
                    if len(batch) >= 20000:
                        db.executemany("insert or replace into r values(?,?)", batch)
                        batch = []
            if batch:
                db.executemany("insert or replace into r values(?,?)", batch)
            db.commit()
        finally:
            db.close()
        os.replace(tmp, p)
        try:
            os.remove(gz)
        except OSError:
            pass

    def _imdb_ds_lookup(self, ids):
        import sqlite3
        out = {}
        db = sqlite3.connect(self._imdb_ds_path())
        try:
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                for row in db.execute("select id, v from r where id in (%s)" % ",".join("?" * len(chunk)), chunk):
                    out[row[0]] = row[1]
        finally:
            db.close()
        return out

    @safe
    def fill_imdb_ratings(self):
        if self._rem():
            return {"ok": True, "updates": []}
        targets = []
        with self._lock:
            for k, m in self._cache["items"].items():
                if m and not m.get("miss") and m.get("imdbId") and m.get("ratingImdb") is None:
                    targets.append(("id", k, m))
            for e in self._wl["items"]:
                m = e.get("meta") or {}
                if m.get("imdbId") and m.get("ratingImdb") is None:
                    targets.append(("key", e.get("key"), m))
        if not targets:
            return {"ok": True, "updates": []}
        if not self._imdb_ds_ok():
            if time.time() - getattr(self, "_imdb_ds_fail", 0) < 3600 and not self._imdb_ds_ok(False):
                return {"ok": True, "updates": []}
            try:
                with _IMDB_DS_LOCK:
                    if not self._imdb_ds_ok():
                        self._imdb_ds_build()
            except Exception as e:
                self._imdb_ds_fail = time.time()
                _log("imdb dataset: %s" % e)
                if not self._imdb_ds_ok(False):
                    return {"ok": True, "updates": []}
        try:
            found = self._imdb_ds_lookup(sorted({m["imdbId"] for _, _, m in targets}))
        except Exception as e:
            _log("imdb dataset lookup: %s" % e)
            return {"ok": True, "updates": []}
        out = []
        with self._lock:
            for kind, k, m in targets:
                v = found.get(m["imdbId"])
                if v is not None and m.get("ratingImdb") is None:
                    m["ratingImdb"] = v
                    out.append({kind: k, "ratingImdb": v})
            if out:
                self._save_cache()
                self._wl_save()
        return {"ok": True, "updates": out}

    @safe
    def set_source_prefs(self):
        return {"ok": True, "updates": self._present_updates()}

    @safe
    def fill_sources(self, limit=6):
        todo = []
        with self._lock:
            groups = [("id", k, m) for k, m in self._cache["items"].items() if m and not m.get("miss")]
            groups += [("key", e.get("key"), e.get("meta") or {}) for e in self._wl["items"]]
            for kind, k, m in groups:
                if m and self._wanted(m):
                    todo.append((kind, k, m))
        out = []
        memo = {}
        n = max(1, min(12, int(limit or 6)))
        for kind, k, m in todo[:n]:
            changed = False
            got_desc = False
            for what, sel in self._wanted(m):
                if what == "desc" and got_desc:
                    continue
                if sel == "kp" and not self._kp_usable():
                    continue
                try:
                    val = self._poster_fetch(sel, m, memo) if what == "poster" else self._desc_fetch(sel, m, memo)
                except Exception:
                    val = None
                with self._lock:
                    m.setdefault("z_tried", []).append("%s:%s" % (what, sel))
                    if val:
                        changed = True
                        if what == "poster":
                            _posters_of(m)[sel] = val
                        else:
                            _descs_of(m)[sel] = val
                            got_desc = True
            if changed:
                out.append(self._update_row(kind, k, m))
        if todo:
            with self._lock:
                self._save_cache()
                self._wl_save()
        return {"ok": True, "updates": out, "remaining": max(0, len(todo) - n)}

    @safe
    def wl_list(self):
        lib = self._library_keys()
        out = []
        for e in self._wl["items"]:
            out.append(self._wl_row(e, lib))
        return {"ok": True, "items": out}

    @safe
    def poster_data(self, url):
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return ""
        path = os.path.join(POSTER_DIR, hashlib.md5(url.encode("utf-8")).hexdigest() + ".bin")
        data = None
        try:
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    data = f.read()
        except OSError:
            data = None
        if not data:
            try:
                r = self._http.get(url, headers={"User-Agent": BROWSER_UA,
                                                 "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}, timeout=15)
            except requests.exceptions.RequestException:
                return ""
            if r.status_code != 200 or not r.content or len(r.content) > 4 * 1024 * 1024:
                return ""
            data = r.content
            try:
                os.makedirs(POSTER_DIR, exist_ok=True)
                with open(path, "wb") as f:
                    f.write(data)
            except OSError:
                pass
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            mime = "image/png"
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            mime = "image/webp"
        elif data[:2] == b"\xff\xd8":
            mime = "image/jpeg"
        else:
            return ""
        return "data:%s;base64,%s" % (mime, base64.b64encode(data).decode("ascii"))


    @staticmethod
    def _ver_tuple(v):
        m = re.match(r"^v?(\d+)\.(\d+)(?:\.(\d+))?", str(v or "").strip())
        return tuple(int(x or 0) for x in m.groups()) if m else None

    @staticmethod
    def _update_mode():
        if os.environ.get("KINO_BASE"):
            return "launcher"
        if getattr(sys, "frozen", False):
            return "frozen"
        return "source"

    def _download_release_asset(self, url, limit):
        prefix = "https://github.com/%s/releases/download/" % UPDATE_REPO
        if not isinstance(url, str) or not url.startswith(prefix):
            raise ApiError("update", "Недопустимый адрес обновления")
        r = self._http.get(url, headers={"User-Agent": "kino-updater"}, timeout=120, stream=False)
        if r.status_code != 200 or not r.content:
            raise ApiError("update", "Не удалось скачать обновление (HTTP %s)" % r.status_code)
        if len(r.content) > limit:
            raise ApiError("update", "Файл обновления слишком большой")
        return r.content

    @safe
    def check_update(self):
        r = self._http.get("https://api.github.com/repos/%s/releases/latest" % UPDATE_REPO,
                           headers={"Accept": "application/vnd.github+json", "User-Agent": "kino-updater"}, timeout=12)
        if r.status_code == 404:
            return {"ok": True, "available": False, "current": APP_VERSION}
        if r.status_code != 200:
            return {"ok": False, "error": "GitHub вернул HTTP %d" % r.status_code}
        d = r.json()
        latest, cur = self._ver_tuple(d.get("tag_name")), self._ver_tuple(APP_VERSION)
        assets = {a.get("name"): a.get("browser_download_url") for a in (d.get("assets") or []) if isinstance(a, dict)}
        mode = self._update_mode()
        can = bool((assets.get("installer.exe") or assets.get("kino.exe")) if mode == "frozen" else assets.get("main.py"))
        self._upd = {"assets": assets, "mode": mode}
        return {"ok": True, "available": bool(latest and cur and latest > cur), "current": APP_VERSION,
                "latest": str(d.get("tag_name") or "").lstrip("vV"), "notes": (d.get("body") or "")[:1200],
                "page": d.get("html_url") or "https://github.com/%s/releases/latest" % UPDATE_REPO,
                "mode": mode, "canInstall": can}

    def _exit_soon(self):
        self._flush_cache()
        threading.Timer(0.9, lambda: os._exit(0)).start()

    def _spawn_detached(self, args):
        flags = 0
        if os.name == "nt":
            flags = 0x00000008 | 0x08000000
        subprocess.Popen(args, creationflags=flags, close_fds=True, cwd=APP_DIR)

    def _validate_main_py(self, data):
        try:
            text = data.decode("utf-8")
            compile(text, "main.py", "exec")
        except (UnicodeDecodeError, SyntaxError, ValueError):
            raise ApiError("update", "Скачанный файл повреждён")
        if "APP_VERSION" not in text or "class Api" not in text:
            raise ApiError("update", "Скачанный файл не похож на Kino")

    @safe
    def install_update(self):
        try:
            return self._install_update()
        except ApiError as e:
            return {"ok": False, "error": str(e)}

    def _install_update(self):
        info = getattr(self, "_upd", None)
        if not info:
            chk = self.check_update()
            if not chk.get("ok"):
                return chk
            info = self._upd
        mode, assets = info["mode"], info["assets"]
        if mode in ("launcher", "source"):
            data = self._download_release_asset(assets.get("main.py"), 6 * 1024 * 1024)
            self._validate_main_py(data)
            if mode == "launcher":
                appdir = os.environ.get("KINO_APP_DIR") or os.path.join(APP_DIR, "app")
                os.makedirs(appdir, exist_ok=True)
                target = os.path.join(appdir, "main.py")
            else:
                target = os.path.abspath(__file__)
                try:
                    shutil.copy2(target, target + ".bak")
                except OSError:
                    pass
            tmp = target + ".new"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, target)
            if mode == "launcher":
                with open(os.path.join(os.path.dirname(target), "base.txt"), "w", encoding="ascii") as f:
                    f.write(os.environ.get("KINO_BASE", ""))
            exe = sys.executable
            if os.name == "nt" and exe.lower().endswith("python.exe") and os.path.isfile(exe[:-10] + "pythonw.exe"):
                exe = exe[:-10] + "pythonw.exe"
            self._spawn_detached([exe, target, "--after-update"])
        else:
            data = self._download_release_asset(assets.get("installer.exe") or assets.get("kino.exe"), 400 * 1024 * 1024)
            if data[:2] != b"MZ" or len(data) < 1024 * 1024:
                raise ApiError("update", "Скачанный файл не является программой")
            exe_path = sys.executable
            new_path = exe_path + ".new"
            with open(new_path, "wb") as f:
                f.write(data)
            bat = os.path.join(tempfile.gettempdir(), "kino_update.bat")
            with open(bat, "w", encoding="cp866", newline="\r\n") as f:
                f.write('@echo off\nping 127.0.0.1 -n 3 >nul\n:loop\nmove /Y "%s" "%s" >nul 2>nul\n'
                        'if errorlevel 1 (\nping 127.0.0.1 -n 2 >nul\ngoto loop\n)\nstart "" "%s"\ndel "%%~f0"\n'
                        % (new_path, exe_path, exe_path))
            self._spawn_detached(["cmd", "/c", bat])
        self._exit_soon()
        return {"ok": True, "restart": True}

    @staticmethod
    def _sniff(data):
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp"
        if data[:2] == b"\xff\xd8":
            return "image/jpeg"
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        return ""

    @staticmethod
    def _poster_path(url):
        return os.path.join(POSTER_DIR, hashlib.md5(url.encode("utf-8")).hexdigest() + ".bin")

    def _poster_bytes(self, url):
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return None
        path = self._poster_path(url)
        try:
            with open(path, "rb") as f:
                data = f.read()
            if data and self._sniff(data):
                return data
        except OSError:
            pass
        with self._poster_sem:
            try:
                r = self._http.get(url, headers={"User-Agent": BROWSER_UA,
                                                 "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}, timeout=15)
            except requests.exceptions.RequestException:
                return None
        data = r.content if r.status_code == 200 else b""
        if not data or len(data) > 6 * 1024 * 1024 or not self._sniff(data):
            return None
        try:
            os.makedirs(POSTER_DIR, exist_ok=True)
            tmp = path + ".%d.tmp" % threading.get_ident()
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        except OSError:
            pass
        return data

    def _start_poster_server(self):
        api = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_GET(self):
                try:
                    pu = urlparse(self.path)
                    q = parse_qs(pu.query)
                    if pu.path == "/bg":
                        data = None
                        try:
                            with open(BG_PATH, "rb") as f:
                                data = f.read()
                        except OSError:
                            pass
                    else:
                        data = api._poster_bytes((q.get("u") or [""])[0])
                    url = ""
                    if not data:
                        self.send_response(404)
                        self.send_header("Content-Length", "0")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", api._sniff(data))
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "public, max-age=31536000, immutable")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(data)
                except Exception:
                    pass

        try:
            srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
            srv.daemon_threads = True
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self._poster_srv = srv
            self._poster_base = "http://127.0.0.1:%d/p?u=" % srv.server_address[1]
        except Exception as e:
            _log("poster server failed: %s" % e)
            self._poster_base = ""

    def _warm_posters(self):
        urls = []
        for e in list(self._cache["items"].values()):
            if isinstance(e, dict) and not e.get("miss"):
                u = e.get("posterPreview") or e.get("poster")
                if u and not os.path.isfile(self._poster_path(u)):
                    urls.append(u)

        def work():
            with ThreadPoolExecutor(max_workers=6) as ex:
                list(ex.map(lambda u: self._poster_bytes(u), urls))
        if urls:
            threading.Thread(target=work, daemon=True).start()

    @safe
    def save_background(self, data_url):
        if not isinstance(data_url, str) or not data_url.startswith("data:image/jpeg;base64,"):
            return {"ok": False, "error": "Нужен JPEG"}
        if len(data_url) > 16 * 1024 * 1024:
            return {"ok": False, "error": "Файл слишком большой"}
        try:
            raw = base64.b64decode(data_url.split(",", 1)[1], validate=True)
        except Exception:
            return {"ok": False, "error": "Повреждённые данные"}
        if raw[:2] != b"\xff\xd8":
            return {"ok": False, "error": "Не JPEG"}
        tmp = BG_PATH + ".tmp"
        with open(tmp, "wb") as f:
            f.write(raw)
        os.replace(tmp, BG_PATH)
        self._cfg["bg_ver"] = str(int(time.time()))
        self._cfg["bg_mode"] = "image"
        self._save_cfg()
        return {"ok": True, "settings": self.get_settings()}

    @safe
    def clear_background(self):
        try:
            os.remove(BG_PATH)
        except OSError:
            pass
        self._cfg["bg_ver"] = "0"
        if self._cfg.get("bg_mode") == "image":
            self._cfg["bg_mode"] = "default"
        self._save_cfg()
        return {"ok": True, "settings": self.get_settings()}

    @safe
    def get_palettes(self):
        if not self._pal:
            p = _load_json(PALETTE_PATH, {})
            self._pal = p if isinstance(p, dict) else {}
        return {"ok": True, "palettes": self._pal}

    @safe
    def save_palettes(self, data):
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(k, str) and isinstance(v, list) and 1 <= len(v) <= 3 and all(isinstance(x, str) and len(x) < 40 for x in v):
                    self._pal[k] = v
            try:
                tmp = PALETTE_PATH + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._pal, f, ensure_ascii=False)
                os.replace(tmp, PALETTE_PATH)
            except OSError:
                pass
        return {"ok": True}

    def _snap(self, it):
        m = self._cache["items"].get(it["id"])
        return {"kind": it["kind"], "title": it["title"], "year": it["year"],
                "meta": m if (m and not m.get("miss")) else None}

    def _refresh_snaps(self):
        changed = False
        for k, e in self._wd.items():
            it = self._items.get(k)
            if it:
                snap = self._snap(it)
                if e.get("snap") != snap:
                    e["snap"] = snap
                    changed = True
        if changed:
            self._save_wd()

    def _save_wd(self):
        with self._lock:
            _save_json(WATCHED_PATH, self._wd)

    def _ghost_view(self, wid, e):
        snap = e.get("snap") or {}
        return {"id": wid, "kind": snap.get("kind") or "movie", "title": snap.get("title") or "Без названия",
                "year": snap.get("year"), "added": e.get("ts", 0), "nFiles": 0, "hasLocalPoster": False,
                "notFound": False, "meta": self._present(snap.get("meta")), "files": [], "seasons": [],
                "inWatched": True, "ghost": True, "hidden": wid in self._cfg["hidden"],
                "pinned": self._cfg["pinned"].get(wid, 0)}

    @safe
    def set_pin(self, ref, flag):
        if self._rem():
            return self._rem_post("/api/pin", {"ref": ref, "flag": bool(flag)})
        if not isinstance(ref, str) or not ref:
            return {"ok": False}
        with self._lock:
            if flag:
                self._cfg["pinned"][ref] = time.time()
            else:
                self._cfg["pinned"].pop(ref, None)
            val = self._cfg["pinned"].get(ref, 0)
        self._save_cfg()
        return {"ok": True, "pinned": val}

    @safe
    def set_hidden(self, item_id, flag):
        if self._rem():
            return self._rem_post("/api/hidden", {"id": item_id, "flag": bool(flag)})
        if not isinstance(item_id, str) or not item_id:
            return {"ok": False}
        with self._lock:
            if flag:
                self._cfg["hidden"][item_id] = int(time.time())
            else:
                self._cfg["hidden"].pop(item_id, None)
        self._save_cfg()
        return {"ok": True, "hidden": bool(flag)}

    @safe
    def set_watched(self, item_id, flag):
        if self._rem():
            return self._rem_post("/api/watched", {"id": item_id, "flag": bool(flag)})
        if flag:
            it = self._items.get(item_id)
            if not it:
                return {"ok": False, "error": "Элемент не найден"}
            self._wd[item_id] = {"ts": int(time.time()), "snap": self._snap(it)}
        else:
            self._wd.pop(item_id, None)
        self._save_wd()
        return {"ok": True, "inWatched": bool(flag)}

    @staticmethod
    def _rm_empty_dirs(d, root):
        while _is_inside(root, d):
            try:
                os.rmdir(d)
            except OSError:
                break
            d = os.path.dirname(d)

    @safe
    def delete_files(self, item_id, paths, permanent=False, keep=False):
        if self._rem():
            return {"ok": False, "error": "Недоступно в режиме удалённой медиатеки"}
        it = self._items.get(item_id)
        roots = self._roots()
        if not it or not roots:
            return {"ok": False, "error": "Элемент не найден. Обновите каталог."}
        mine = {f["path"] for f in it["files"]}
        todo = [p for p in (paths or []) if p in mine and p in self._paths]
        if not todo:
            return {"ok": False, "error": "Нет файлов для удаления"}
        deleted, failed = [], []
        by_path = {f["path"]: f for f in it["files"]}
        disc_dirs = {}
        for p in todo:
            targets = [p] + list(by_path[p].get("extra") or [])
            if any(not any(_is_inside(r, t) for r in roots) for t in targets):
                failed.append({"path": p, "error": "файл вне выбранной папки"})
                continue
            try:
                for t in targets:
                    if os.path.isfile(t):
                        if permanent:
                            os.remove(t)
                        else:
                            _recycle(t)
                    disc_dirs[os.path.dirname(t)] = 1
                deleted.append(p)
            except Exception as e:
                _log("delete failed %s: %s" % (p, e))
                failed.append({"path": p, "error": str(e)})
        gone = set(deleted)
        it["files"] = [f for f in it["files"] if f["path"] not in gone]
        self._paths -= gone
        for p in gone:
            self._cfg["watched"].pop(p, None)
            rt = next((r for r in roots if _is_inside(r, p)), None)
            if rt:
                for dd in sorted(disc_dirs, key=len, reverse=True):
                    if _is_inside(rt, dd):
                        self._rm_empty_dirs(dd, rt)
                self._rm_empty_dirs(os.path.dirname(p), rt)
        removed = not it["files"]
        ghost = None
        if removed:
            self._items.pop(item_id, None)
            if keep:
                self._wd[item_id] = {"ts": (self._wd.get(item_id) or {}).get("ts") or int(time.time()), "snap": self._snap(it)}
                ghost = self._ghost_view(item_id, self._wd[item_id])
            else:
                self._wd.pop(item_id, None)
            self._save_wd()
        if gone:
            self._save_cfg()
        return {"ok": True, "deleted": len(deleted), "failed": failed,
                "item": None if removed else self._view(it), "ghost": ghost}

    @safe
    def clear_cache(self):
        with self._lock:
            keep = {k: v for k, v in self._cache["items"].items() if not v.get("miss") and v.get("manual")}
            self._cache["items"] = keep
            self._save_cache()
        return {"ok": True, "kept": len(keep)}

    @safe
    def play(self, path, override=""):
        if self._rem() and path.startswith("kino-remote://"):
            return self._remote_play(path, override)
        if path not in self._paths:
            return {"ok": False, "error": "Файл не входит в каталог. Обновите список."}
        if not os.path.isfile(path):
            return {"ok": False, "error": "Файл не найден (возможно, диск отключён)."}
        mode = self._cfg.get("player_mode")
        player = self._cfg.get("player_path")
        try:
            if mode == "custom":
                if not player or not os.path.isfile(player):
                    return {"ok": False, "error": "Файл плеера не найден. Укажите .exe в настройках."}
                flags = (0x00000008 | 0x00000200) if os.name == "nt" else 0
                subprocess.Popen([player, path], creationflags=flags, close_fds=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif os.name == "nt":
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            return {"ok": False, "error": "Не удалось запустить: %s" % e}
        self._cfg["watched"][path] = 1
        self._save_cfg()
        return {"ok": True}

    @safe
    def reveal(self, path):
        if path in self._paths and os.path.exists(path) and os.name == "nt":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        return {"ok": True}

    @safe
    def open_url(self, url):
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            webbrowser.open(url)
        return {"ok": True}


HTML = r'''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Kino</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script async src="https://cdn.tailwindcss.com"></script>
<style>
:root{
  --text:#f2f2f2; --muted:rgba(242,242,242,.52); --accent:#ffffff;
  --stroke:rgba(255,255,255,.10); --good:#9ad4ae; --mid:#c9c9c9; --bad:#e29a9a;
}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{font-family:"Segoe UI Variable Text","Segoe UI",system-ui,sans-serif;color:var(--text);background:#060606;overflow:hidden;-webkit-font-smoothing:antialiased;user-select:none;font-size:14px}
button{font-family:inherit;color:inherit}
.hidden{display:none!important}
.grow{flex:1;min-width:0}

#base,#bgA,#bgB,#shade{position:fixed;pointer-events:none}
#base{inset:0;overflow:hidden;background:
  radial-gradient(1100px 760px at 10% 0%,#1e1e20 0%,transparent 60%),
  radial-gradient(900px 700px at 95% 20%,#171718 0%,transparent 55%),
  radial-gradient(900px 700px at 50% 110%,#1a1a1b 0%,transparent 60%),
  linear-gradient(160deg,#080808,#0c0c0d 50%,#050505)}
#bgA,#bgB{inset:0;background-size:cover;background-position:center;opacity:0;transition:opacity .9s ease}
#bgA.on,#bgB.on{opacity:.8}
#shade{inset:0;background:linear-gradient(180deg,rgba(4,4,4,.35),rgba(4,4,4,.78))}
#updBar{position:fixed;left:50%;bottom:74px;transform:translate(-50%,20px);z-index:60;display:flex;align-items:center;gap:12px;padding:10px 14px 10px 18px;border-radius:16px;font-size:13.5px;opacity:0;pointer-events:none;transition:opacity .3s,transform .3s}
#updBar.on{opacity:1;pointer-events:auto;transform:translate(-50%,0)}
#updBar small{color:var(--muted)}
#userbg{position:fixed;inset:0;pointer-events:none;display:none;background-size:cover;background-position:center}
body.bg-custom #base,body.bg-custom #bgA,body.bg-custom #bgB{display:none}
body.bg-custom #userbg{display:block}
.bgsw{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.bgsw i{width:26px;height:26px;border-radius:50%;cursor:pointer;border:1px solid rgba(255,255,255,.22);transition:transform .15s}
.bgsw i:hover{transform:scale(1.15)}
input[type=color].inp{padding:2px;width:46px;height:34px;cursor:pointer}
.rng{display:flex;align-items:center;gap:12px;margin:6px 0;font-size:13px;color:var(--muted)}
.rng span{width:92px}.rng input{flex:1;accent-color:#f2f2f2}.rng b{width:38px;text-align:right;color:var(--text);font-weight:600}

.glass{position:relative;background:rgba(20,20,22,.94);
  border:1px solid rgba(255,255,255,.08);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.08),0 12px 32px rgba(0,0,0,.4)}
.sheen{position:relative}

.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:8px 16px;border-radius:12px;cursor:pointer;font-size:13.5px;font-weight:600;
  background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);box-shadow:inset 0 1px 0 rgba(255,255,255,.08);transition:background-color .16s cubic-bezier(.22,1,.36,1),border-color .16s cubic-bezier(.22,1,.36,1),transform .16s cubic-bezier(.22,1,.36,1);white-space:nowrap}
.btn:hover{background:rgba(255,255,255,.12);border-color:rgba(255,255,255,.16)}
.btn:active{transform:scale(.98)}
.btn.icon{width:40px;height:40px;padding:0;border-radius:12px}
.btn.sm{padding:6px 12px;font-size:12.5px;border-radius:8px}
.btn.primary{background:#ededed;border-color:#ededed;color:#0a0a0a;box-shadow:inset 0 1px 0 rgba(255,255,255,.6)}
.btn.primary:hover{background:#ffffff;border-color:#ffffff}
.btn.lg{padding:12px 24px;font-size:15px;border-radius:14px}
.btn.lg.icon{padding:0;width:50px;height:50px}
.btn.lbbtn{font-size:13px;font-weight:800;letter-spacing:.2px}
.btn.spin svg{animation:rot 1s linear infinite}
@keyframes rot{to{transform:rotate(360deg)}}
.inp{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);color:var(--text);border-radius:12px;padding:10px 14px;font-size:14px;font-family:inherit;outline:none;transition:background-color .16s cubic-bezier(.22,1,.36,1),border-color .16s cubic-bezier(.22,1,.36,1);user-select:text}
.inp:focus{border-color:rgba(255,255,255,.5);box-shadow:0 0 0 3px rgba(255,255,255,.1);background-color:rgba(255,255,255,.08)}
.inp::placeholder{color:rgba(242,242,242,.38)}
select.inp{cursor:pointer;color-scheme:dark;-webkit-appearance:none;appearance:none;padding-right:38px;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23b8b8b8' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 14px center}
select.inp option{background:#141414;color:#f2f2f2}
.seg{display:inline-flex;padding:4px;border-radius:14px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08)}
.seg button{border:0;background:transparent;padding:8px 16px;border-radius:10px;cursor:pointer;font-weight:600;font-size:13px;color:var(--text);transition:background-color .16s cubic-bezier(.22,1,.36,1),color .16s cubic-bezier(.22,1,.36,1)}
.seg button:hover{background:rgba(255,255,255,.07)}
.seg button.on{background:#ededed;color:#0a0a0a}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-thumb{background:rgba(255,255,255,.16);border-radius:10px;border:2px solid transparent;background-clip:padding-box}
::-webkit-scrollbar-thumb:hover{background:rgba(255,255,255,.28);background-clip:padding-box;border:2px solid transparent}
::-webkit-scrollbar-track{background:transparent}

#app{position:relative;z-index:1;height:100%;display:flex;flex-direction:column}
#top{position:absolute;left:0;right:0;top:0;margin:16px 20px 0;padding:12px 16px;border-radius:18px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;z-index:5}
#top .inp,#top .btn:not(.icon){height:40px;padding-top:0;padding-bottom:0}
.brand{display:flex;align-items:center;gap:10px;font-weight:800;font-size:19px;letter-spacing:.5px;margin-right:8px;white-space:nowrap}
#splash{position:fixed;inset:0;z-index:9999;background:#070707;display:grid;place-items:center;transition:opacity .45s cubic-bezier(.22,1,.36,1)}
#splash img{width:180px;height:auto;pointer-events:none}
#splash.out{opacity:0;pointer-events:none}
@media (prefers-reduced-motion:reduce){#splash{transition:none}}
.brand img{height:40px;width:auto;display:block;pointer-events:none;user-select:none;-webkit-user-drag:none}
.search{position:relative;flex:1 1 150px;min-width:130px;max-width:360px}
.search svg{position:absolute;left:13px;top:50%;transform:translateY(-50%);opacity:.55;pointer-events:none}
.search .inp{padding-left:40px;padding-right:38px;width:100%}
.search .sx{position:absolute;right:8px;top:50%;transform:translateY(-50%);width:26px;height:26px;border-radius:50%;border:0;background:rgba(255,255,255,.08);color:inherit;cursor:pointer;display:none;align-items:center;justify-content:center;padding:0}
.search .sx:hover{background:rgba(255,255,255,.18)}
.search .sx svg{position:static;transform:none;opacity:.85;pointer-events:none}
.search.has .sx{display:flex}
#main{flex:1;overflow-y:auto;overflow-x:hidden;padding:calc(var(--topH,60px) + 24px) 0 calc(var(--botH,48px) + 24px)}
#grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(var(--cw,176px),1fr));gap:32px;padding:24px 32px 56px}
#status{position:absolute;left:0;right:0;bottom:0;z-index:5;margin:0 20px 12px;padding:8px 16px;border-radius:14px;display:flex;align-items:center;gap:14px;font-size:12.5px;color:var(--muted)}
.bar{flex:1;height:3px;border-radius:4px;background:rgba(255,255,255,.08);overflow:hidden;opacity:0;transition:opacity .3s}
.bar.on{opacity:1}
.bar i{display:block;height:100%;width:0;background:#f2f2f2;transition:width .3s}

.banner{margin:8px 26px 0;padding:11px 16px;border-radius:18px;display:flex;align-items:center;gap:12px;font-size:13.5px}
.banner .b-ico{width:24px;height:24px;border-radius:50%;display:grid;place-items:center;background:rgba(255,255,255,.14);color:#fff;font-weight:800}
.banner .b-t{flex:1}

.card{position:relative;border-radius:16px;cursor:pointer;transition:transform .3s cubic-bezier(.22,1,.36,1);animation:rise .5s backwards}
.card:hover{transform:translateY(-4px);z-index:3}
#grid.noanim .card,.wl-grid .card{animation:none}
.roots{display:flex;flex-direction:column;gap:8px;margin-bottom:10px}.roots .row{margin:0}
.halo{display:none;position:absolute;inset:-30px;pointer-events:none;z-index:0;opacity:.8;transition:opacity .35s ease;
  background:radial-gradient(ellipse closest-side,var(--h1,rgba(255,255,255,.12)) 60%,transparent 100%),
  radial-gradient(ellipse 60% 48% at 82% 14%,var(--h2,transparent),transparent),
  radial-gradient(ellipse 60% 48% at 18% 86%,var(--h3,transparent),transparent);
  -webkit-mask-image:radial-gradient(ellipse closest-side,#000 66%,transparent 100%);mask-image:radial-gradient(ellipse closest-side,#000 66%,transparent 100%)}
.card:hover .halo{opacity:1}
.m-wrap{position:relative}
.m-wrap .halo{display:none;inset:-56px;opacity:.85}
@keyframes rise{from{opacity:0;transform:translateY(16px) scale(.97)}}
.cv{position:relative;z-index:1;aspect-ratio:2/3;border-radius:16px;overflow:hidden;border:1px solid rgba(255,255,255,.1);background:#101010;box-shadow:0 8px 24px rgba(0,0,0,.45)}
.cv img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.stub{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;padding:14px;text-align:center;
  background:radial-gradient(120% 90% at 30% 10%,hsla(0,0%,calc(40% + var(--g) * 2%),.32),transparent 60%),linear-gradient(160deg,hsl(0,0%,calc(15% + var(--g) * 1%)),hsl(0,0%,8%))}
.stub-l{font-size:calc(var(--cw,176px) * .32);font-weight:800;line-height:1;color:rgba(255,255,255,.85);text-shadow:0 6px 24px rgba(0,0,0,.5)}
.stub-n{font-size:11px;color:rgba(255,255,255,.45)}
.cap{position:absolute;left:0;right:0;bottom:0;padding:40px 12px 11px;background:linear-gradient(180deg,transparent,rgba(4,4,4,.55) 35%,rgba(4,4,4,.94))}
.cap-t{font-weight:700;font-size:calc(13px + (var(--cw,176px) - 120px) * .034);line-height:1.25;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.cap-s{font-size:calc(11px + (var(--cw,176px) - 120px) * .018);color:var(--muted);margin-top:3px}
.pn{position:absolute;top:9px;right:9px;width:26px;height:26px;border-radius:50%;display:grid;place-items:center;background:rgba(8,8,8,.7);z-index:2}
.card.pinned .rt{right:44px}
@keyframes pinpop{from{opacity:0;transform:scale(0) rotate(-50deg)}60%{transform:scale(1.25) rotate(8deg)}}
.pn.fresh{animation:pinpop .6s .3s cubic-bezier(.3,1.4,.5,1) backwards}
.rt{position:absolute;top:12px;right:12px;padding:3px 8px;border-radius:8px;font-weight:700;font-variant-numeric:tabular-nums;font-size:calc(10.5px + (var(--cw,176px) - 120px) * .02);background:rgba(8,8,8,.7)}
.rg{color:var(--good)}.ry{color:var(--mid)}.rr{color:var(--bad)}
.tp{position:absolute;top:12px;left:12px;padding:3px 8px;border-radius:8px;font-weight:600;font-size:calc(9.5px + (var(--cw,176px) - 120px) * .018);background:rgba(8,8,8,.7)}

.empty{display:flex;height:100%;padding:24px;overflow:auto}
.empty .box{margin:auto}
.empty .box{max-width:520px;padding:38px 40px;border-radius:30px;text-align:center}
.empty h2{margin:14px 0 8px;font-size:22px}
.empty p{margin:0 0 22px;color:var(--muted);line-height:1.55}
.empty .big{width:72px;height:72px;border-radius:24px;margin:0 auto;display:grid;place-items:center;background:#f2f2f2;color:#0a0a0a;box-shadow:0 14px 40px rgba(255,255,255,.1),inset 0 1px 0 #fff}

.empty .box.wel{max-width:560px;width:100%;padding:24px 32px;text-align:left}
.wel .wlogo{height:38px;width:auto;display:block;margin:0 0 12px;pointer-events:none}
.wel h2{margin:0 0 4px;font-size:20px}
.wel .wsub{margin:0 0 6px;color:var(--muted);line-height:1.5;font-size:13px}
.wel .wst{margin:16px 0 8px;font-size:13px;font-weight:600;color:var(--muted)}
.wel .wroots{display:flex;flex-direction:column;gap:5px;margin-top:8px}
.wel .wroots div{padding:7px 12px;border-radius:11px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wel .wlang{display:flex;gap:10px}
.wel .wlang .btn{flex:1;justify-content:center}
.wel .wlang .btn.on{background:linear-gradient(180deg,#fff,#d9d9d9);color:#0a0a0a;border-color:rgba(255,255,255,.7)}
.wel .wins{margin:0 0 10px;padding-left:18px;color:var(--muted);font-size:12.5px;line-height:1.55}
.wel .wwarn{margin-top:10px;padding:10px 13px;border-radius:12px;background:rgba(255,190,70,.1);border:1px solid rgba(255,190,70,.3);color:#f2c27a;font-size:12.5px;line-height:1.5}
.wel .wgo{margin-top:16px;display:flex;justify-content:flex-end}

.overlay{position:fixed;inset:0;z-index:50;display:grid;place-items:center;padding:24px;background:rgba(2,2,2,.74);animation:fade .25s}
@keyframes fade{from{opacity:0}}
.modal{width:min(1080px,96vw);max-height:92vh;overflow:auto;border-radius:30px;padding:30px;animation:pop .38s cubic-bezier(.2,.9,.3,1) backwards}
.modal.sm{width:min(640px,96vw)}
@keyframes pop{from{opacity:0;transform:translateY(24px) scale(.96)}}
.modal .x{position:absolute;top:16px;right:16px;z-index:3}
.m-grid{display:grid;grid-template-columns:290px 1fr;gap:30px}
@media(max-width:860px){.m-grid{grid-template-columns:1fr}.m-left{max-width:260px}}
.m-poster{position:relative;aspect-ratio:2/3;border-radius:22px;overflow:hidden;border:1px solid rgba(255,255,255,.14);box-shadow:0 24px 60px rgba(0,0,0,.6),inset 0 1px 0 rgba(255,255,255,.25)}
.m-poster img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.m-right h2{margin:0 44px 2px 0;font-size:28px;line-height:1.15;font-weight:800;letter-spacing:-.3px}
.orig{color:var(--muted);font-size:15px;margin-bottom:14px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.chip{padding:5px 12px;border-radius:12px;font-size:12.5px;font-weight:600;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.12)}
.chip.t{background:#ededed;color:#0a0a0a;border-color:transparent}
.ratings{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}
.rbadge{display:flex;align-items:baseline;gap:8px;padding:8px 14px;border-radius:15px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.16)}
.rbadge b{font-size:20px}.rbadge small{font-size:12px;color:var(--muted)}
.rbadge.lb{background:rgba(255,255,255,.1);border-style:dashed;transition:background .2s}
.rbadge.lb[data-act]:hover{background:rgba(255,255,255,.18)}
.meta-l{color:var(--muted);font-size:13px;margin:6px 0}
.meta-l b{color:var(--text);font-weight:600}
.desc{line-height:1.65;font-size:14.5px;margin:14px 0 18px;color:rgba(242,242,242,.86);user-select:text;white-space:pre-line}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0 8px}
.links{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:0 0 8px}
.btn.lnk{width:100%;min-width:0;height:42px;padding:0 10px;font-size:13.5px;font-weight:600;white-space:nowrap}
.btn.lnk svg{opacity:.7;flex:none}
.note{padding:12px 16px;border-radius:16px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);font-size:13px;line-height:1.5;color:rgba(242,242,242,.8);margin:10px 0}
.sec-t{font-weight:600;font-size:13px;color:var(--muted);margin:24px 0 12px}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.tab{padding:8px 16px;border-radius:10px;cursor:pointer;font-weight:600;font-size:13px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);transition:background-color .16s cubic-bezier(.22,1,.36,1)}
.tab small{margin-left:7px;opacity:.55}
.tab:hover{background:rgba(255,255,255,.12)}
.tab.on{background:#ededed;color:#0a0a0a;border-color:transparent}
.eps{display:flex;flex-direction:column;gap:6px;max-height:300px;overflow:auto;padding-right:4px}
.ep{display:grid;grid-template-columns:38px 1fr auto 34px;align-items:center;gap:12px;padding:9px 12px;border-radius:14px;cursor:pointer;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07);transition:all .2s}
.ep:hover{background:rgba(255,255,255,.12);transform:translateX(3px)}
.ep.seen{opacity:.55}
.ep-n{font-weight:800;color:#fff;text-align:center}
.ep-t{min-width:0}.ep-t b{display:block;font-size:13.5px}
.ep-t small{display:block;color:var(--muted);font-size:11.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ep-s{font-size:12px;color:var(--muted)}
.ep-p{display:grid;place-items:center;width:30px;height:30px;border-radius:50%;background:rgba(255,255,255,.1)}
.fix{margin-top:14px;padding:16px;border-radius:20px;background:rgba(0,0,0,.28);border:1px solid rgba(255,255,255,.1)}
.row{display:flex;gap:10px;align-items:center;margin-top:10px;flex-wrap:wrap}
.row:first-child{margin-top:0}
.dd{margin-top:10px;max-height:290px;overflow:auto;border-radius:16px;border:1px solid rgba(255,255,255,.12);background:rgba(10,10,10,.82)}
.dd-i{display:flex;gap:12px;align-items:center;padding:9px 12px;cursor:pointer;transition:background .15s;border-bottom:1px solid rgba(255,255,255,.05)}
.dd-i:last-child{border-bottom:0}
.dd-i:hover{background:rgba(255,255,255,.12)}
.dd-i img,.dd-i .ph{width:38px;height:56px;border-radius:8px;object-fit:cover;flex:none;background:rgba(255,255,255,.07)}
.dd-i b{display:block;font-size:13.5px}.dd-i small{color:var(--muted);font-size:12px}
.dd-e{padding:16px;text-align:center;color:var(--muted);font-size:13px}
.path{flex:1;min-width:0;padding:10px 14px;border-radius:14px;background:rgba(255,255,255,.04);border:1px dashed rgba(255,255,255,.16);font-size:13px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;user-select:text}
.radio{display:flex;align-items:center;gap:10px;padding:8px 2px;cursor:pointer}
.radio input{accent-color:#f2f2f2;width:16px;height:16px}
.hint{font-size:12px;color:var(--muted);line-height:1.5}
.modal h2.t{margin:0 0 6px;font-size:24px;font-weight:800}
.rp-list{display:grid;gap:8px;margin:20px 0 18px}
.rp-i{display:flex;align-items:center;justify-content:space-between;gap:16px;width:100%;min-height:48px;padding:0 16px;border-radius:12px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);color:var(--text);font-family:inherit;font-size:14px;text-align:left;cursor:pointer;transition:background-color .16s cubic-bezier(.22,1,.36,1),border-color .16s cubic-bezier(.22,1,.36,1)}
.rp-i b{font-weight:600;white-space:nowrap}
.rp-i span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12.5px;color:var(--muted)}
.rp-i:hover{background:rgba(255,255,255,.1);border-color:rgba(255,255,255,.18)}
.rp-i.pri{background:#ededed;border-color:#ededed;color:#0a0a0a}
.rp-i.pri span{color:rgba(10,10,10,.55)}
.rp-i.pri:hover{background:#fff}
.rp-i:focus-visible{outline:2px solid rgba(255,255,255,.7);outline-offset:2px}
.foot{display:flex;justify-content:flex-end;gap:10px;margin-top:26px}
.sep{height:1px;background:rgba(255,255,255,.08);margin:22px 0 0}

#wl{display:none;padding:24px 20px 40px}
body.v-wl #wl{display:block}
body.v-wl #grid,body.v-wl #empty,body.v-wl #banner{display:none!important}
body.v-wl .libonly{display:none!important}
body:not(.v-wl) .wlonly{display:none}
.seg small{opacity:.6;margin-left:6px;font-size:12px}
.wl-wrap{max-width:none;margin:0}
.wl-head{display:flex;gap:16px 20px;align-items:center;flex-wrap:wrap;padding:0 12px}
#lbBox{flex:0 0 auto;margin-left:auto}
#lbMsg:empty{display:none}
.wl-t{font-size:20px;font-weight:700;white-space:nowrap}.wl-t small{margin-left:8px;font-size:15px;font-weight:600;color:var(--muted)}
.wl-s{flex:0 1 420px;width:auto;max-width:420px}
.wl-dd{max-height:420px}
.wl-r{display:grid;grid-template-columns:44px 1fr auto;gap:14px;align-items:center;padding:10px 12px;border-bottom:1px solid rgba(255,255,255,.05);transition:background .15s}
.wl-r:last-child{border-bottom:0}
.wl-r:hover{background:rgba(255,255,255,.06)}
.wl-r img,.wl-r .ph{width:44px;height:64px;border-radius:8px;object-fit:cover;background:rgba(255,255,255,.07);display:block}
.wl-r b{display:block;font-size:14.5px}
.wl-r small{color:var(--muted);font-size:12px}
.lb-row{display:flex;gap:10px;align-items:center}
.lb-l{font-size:12px;color:var(--muted);white-space:nowrap}
.lb-row .inp{flex:1;min-width:0;width:200px}
.lb-card{display:flex;align-items:center;gap:12px;padding:6px 6px 6px 8px;border-radius:14px;color:var(--text);background:rgba(20,20,22,.62);-webkit-backdrop-filter:blur(24px) saturate(1.5);backdrop-filter:blur(24px) saturate(1.5);box-shadow:inset 0 1px 0 rgba(255,255,255,.1),0 12px 32px rgba(0,0,0,.35)}
.lb-card .btn.icon{width:36px;height:36px}
.lb-av{width:36px;height:36px;border-radius:50%;object-fit:cover;background:rgba(255,255,255,.1);flex:none;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:15px;overflow:hidden}
.lb-av img{width:100%;height:100%;object-fit:cover;display:block}
.lb-i{flex:1;min-width:0}
.lb-i b{display:block;font-size:14px;line-height:1.2}
.lb-i small{color:var(--muted);font-size:12px;display:block;white-space:nowrap}
.lb-i small.lb-e{font-size:11.5px;opacity:.8}
.wl-lang{display:flex;gap:10px;margin-bottom:6px}
.wl-lang .btn{flex:1;flex-direction:column;gap:2px;padding:14px 10px}
.wl-lang small{font-weight:400;opacity:.65;font-size:11.5px}
.chip.cp{cursor:pointer;display:inline-flex;align-items:center;justify-content:center;color:inherit;font-family:inherit}
.chip.cp:hover{background:rgba(255,255,255,.16)}
.wl-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(var(--cw,176px),1fr));gap:32px;padding:24px 12px 40px}
.wl-empty{grid-column:1/-1;padding:34px;text-align:center;color:var(--muted);line-height:1.6}
.zoom{display:flex;align-items:center;gap:10px;margin-left:auto;flex:none}
.zoom .zs,.zoom .zb{display:block;border:1.5px solid rgba(255,255,255,.5);border-radius:3px}
.zoom .zs{width:8px;height:11px}.zoom .zb{width:13px;height:18px}
#zoom{-webkit-appearance:none;appearance:none;width:170px;height:4px;border-radius:4px;background:rgba(255,255,255,.18);outline:none;cursor:pointer}
#zoom::-webkit-slider-thumb{-webkit-appearance:none;width:15px;height:15px;border-radius:50%;background:#f2f2f2;box-shadow:0 2px 8px rgba(0,0,0,.55);cursor:pointer;transition:transform .15s}
#zoom::-webkit-slider-thumb:hover{transform:scale(1.2)}
.ctx{position:fixed;z-index:80;min-width:260px;max-width:330px;padding:6px;border-radius:14px;background:rgba(20,20,22,.98);animation:pop .16s ease backwards;user-select:none}
.ctx-h{padding:8px 12px 6px}.ctx-h b{display:block;font-size:14px;line-height:1.3}.ctx-h small{color:var(--muted);font-size:12.5px}
.ctx-fi{display:flex;align-items:center;gap:6px;padding:0 12px 6px;font-size:12.5px;color:var(--muted)}
.ctx-i{display:flex;justify-content:space-between;gap:18px;padding:5px 10px;font-size:12.5px;color:var(--muted)}.ctx-i b{color:var(--text);font-weight:600;text-align:right}
.ctx-sep{height:1px;background:rgba(255,255,255,.08);margin:6px 8px}
.ctx-b{display:flex;align-items:center;gap:12px;width:100%;min-height:36px;padding:0 12px;border:0;background:transparent;border-radius:8px;cursor:pointer;font-size:13.5px;font-weight:500;text-align:left;transition:background-color .12s cubic-bezier(.22,1,.36,1)}
.ctx-b svg{flex:none;opacity:.7}
.ctx-ic{width:16px;height:16px;flex:none}
.ctx-b.sel{font-weight:600}
.ctx-b.sel svg{opacity:1}
.ctx-b:hover{background:rgba(255,255,255,.1)}
.ctx-b:disabled{opacity:.38;cursor:default;background:transparent}
.ctx-b.danger{color:var(--bad)}.ctx-b.danger:hover{background:rgba(226,154,154,.14)}
.btn.danger{background:rgba(226,154,154,.12);border-color:rgba(226,154,154,.4);color:#f1b4b4}
.btn.danger:hover{background:rgba(226,154,154,.22)}
.overlay.dlg{z-index:70}
.modal.rm{width:min(560px,94vw)}
.modal.dlg-s{width:min(440px,94vw);padding:28px}
.dlg-s h2.t{font-size:22px;margin-bottom:10px}
.dlg-p{font-size:15px;line-height:1.55;color:rgba(242,242,242,.72)}
.dlg-s .foot{margin-top:24px}
.modal.rm-dlg{width:min(520px,94vw);padding:28px}
.rm-dlg h2.t{font-size:22px;margin:0 44px 20px 0}
.rm-h{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}
.rm-h .sec-t{margin:0}
.rm-re{width:36px;height:36px}
.rm-list{display:flex;flex-direction:column;gap:8px}
.rm-srv{display:flex;align-items:center;gap:12px;width:100%;justify-content:flex-start;padding:10px 16px}
.rm-srv .hint{margin-left:auto}
.rm-stat{display:flex;align-items:center;gap:10px;color:var(--muted);font-size:14px;min-height:40px}
.rm-stat .spinner{width:14px;height:14px;border-width:2px}
.rm-form{display:grid;grid-template-columns:minmax(0,1fr) 96px auto;gap:10px;align-items:center}
.rm-form .btn{height:40px}
.rm-last{margin-top:10px}
.rm-msg{margin-top:12px;font-size:13.5px;color:#f2a2a2}
.rm-help{margin-top:24px;padding-top:16px;border-top:1px solid rgba(255,255,255,.08);font-size:13px;line-height:1.55;color:var(--muted)}
.rm-sec{margin-top:28px}
.rm-sec .sec-t{margin:0 0 12px}
.modal.st-modal{width:min(720px,96vw);padding:0;display:flex;flex-direction:column;overflow:hidden;max-height:92vh}
.st-head{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:24px 28px 16px;flex:none}
.st-head h2.t{margin:0;font-size:24px}
.st-head .x{position:static}
.st-body{overflow:auto;padding:0 28px 12px;flex:1;min-height:0}
.st-g{padding:20px 0;border-top:1px solid rgba(255,255,255,.08)}
.st-g:first-child{border-top:0;padding-top:4px}
.st-g>.sec-t,.st-r .sec-t{margin:0 0 12px}
.st-r{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:12px}
.st-r .sec-t{margin:0}
.st-modal .sec-t{font-size:13.5px;font-weight:500;color:var(--text)}
.st-g>.hint:last-child,.st-g>.st-r:last-child{margin-bottom:0}
.st-body select.inp{min-width:220px}
.st-body .hint{font-size:13px;line-height:1.55}
.st-foot{margin:0;padding:16px 28px;border-top:1px solid rgba(255,255,255,.08);flex:none;background:rgba(20,20,22,.98)}
.st-k+.st-k{margin-top:24px}
.st-kh{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px}
.st-kt{font-size:14px;font-weight:600}
.st-body .row{margin-top:10px}
.st-body .row:first-child{margin-top:0}
.radio.sw{flex-direction:row-reverse;justify-content:space-between;gap:16px;padding:10px 0;width:100%}
.radio.sw input[type=checkbox]{-webkit-appearance:none;appearance:none;width:38px;height:22px;border-radius:11px;background:rgba(255,255,255,.14);position:relative;cursor:pointer;flex:none;margin:0;transition:background-color .16s cubic-bezier(.22,1,.36,1)}
.radio.sw input[type=checkbox]::after{content:"";position:absolute;top:3px;left:3px;width:16px;height:16px;border-radius:50%;background:#bdbdbd;transition:transform .16s cubic-bezier(.22,1,.36,1),background-color .16s cubic-bezier(.22,1,.36,1)}
.radio.sw input[type=checkbox]:checked{background:#ededed}
.radio.sw input[type=checkbox]:checked::after{transform:translateX(16px);background:#141415}
.radio.sw input[type=checkbox]:focus-visible{outline:2px solid rgba(255,255,255,.6);outline-offset:2px}
.st-body .radio input[type=radio]{-webkit-appearance:none;appearance:none;width:18px;height:18px;border-radius:50%;border:2px solid rgba(255,255,255,.4);margin:0;flex:none;cursor:pointer;transition:border-color .16s}
.st-body .radio input[type=radio]:checked{border-color:#ededed;background:radial-gradient(circle,#ededed 0 42%,transparent 48%)}
.st-body .radio input[type=radio]:focus-visible{outline:2px solid rgba(255,255,255,.6);outline-offset:2px}
.rm-list{max-height:46vh;overflow:auto;margin-top:10px;display:flex;flex-direction:column;gap:2px}
.del-list{display:flex;flex-direction:column;gap:6px;max-height:190px;overflow:auto;margin-bottom:12px}
.del-f{display:flex;justify-content:space-between;gap:14px;padding:8px 12px;border-radius:12px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.07);font-size:12.5px}
.del-f span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.del-f small{color:var(--muted);flex:none}
.card.ghost .cv{filter:grayscale(.75) brightness(.72)}
@media(max-width:1500px){#btnRefresh .lbl,#btnRemote .lbl{display:none}#btnRefresh,#btnRemote{padding:0 11px}}
#toasts{position:fixed;left:50%;bottom:64px;transform:translateX(-50%);z-index:99;display:flex;flex-direction:column;gap:10px;align-items:center;pointer-events:none}
.toast{padding:11px 20px;border-radius:16px;font-size:13.5px;font-weight:600;animation:rise .35s backwards;transition:all .4s}
.toast.out{opacity:0;transform:translateY(10px)}
.toast.err{border-color:rgba(255,255,255,.4);box-shadow:inset 0 1px 0 rgba(255,255,255,.22),0 0 30px rgba(255,255,255,.1),0 18px 50px rgba(0,0,0,.45)}
.busy{position:fixed;left:50%;top:92px;transform:translateX(-50%);z-index:40;padding:11px 20px;border-radius:18px;display:flex;align-items:center;gap:12px;font-weight:600}
.spinner{width:18px;height:18px;border-radius:50%;border:2.5px solid rgba(255,255,255,.22);border-top-color:#fff;animation:rot .8s linear infinite}
.sheen::after{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;background:radial-gradient(240px circle at var(--mx,50%) var(--my,0%),rgba(255,255,255,.045),transparent 62%);opacity:0;transition:opacity .3s}
.sheen:hover::after{opacity:1}
.btn{transition:background-color .22s ease,border-color .22s ease,transform .22s ease,box-shadow .22s ease}
.btn:hover{background:rgba(255,255,255,.15);border-color:rgba(255,255,255,.18);transform:translateY(-1px);box-shadow:inset 0 1px 0 rgba(255,255,255,.26),0 8px 22px rgba(0,0,0,.4)}
.btn:active{transform:translateY(0) scale(.98)}
.btn.primary:hover{background:#ffffff;border-color:#ffffff;box-shadow:inset 0 1px 0 #fff,0 10px 28px rgba(255,255,255,.18)}
.seg button{transition:background-color .2s ease,color .2s ease,box-shadow .2s ease}
.seg button.on{box-shadow:0 4px 14px rgba(0,0,0,.35)}
.btn.md{padding:0 20px;height:44px;font-size:14px;border-radius:12px}
.btn.md.on{background:rgba(255,255,255,.14);border-color:rgba(255,255,255,.28)}
.btn.lg{height:48px}
.actions.a2{margin:0 0 8px}
.rbadge.lk{cursor:pointer;transition:background-color .16s cubic-bezier(.22,1,.36,1)}
.rbadge.lk:hover{background:rgba(255,255,255,.1)}
.rbadge small{display:inline-flex;align-items:center;gap:5px}
.rbadge small svg{flex:none;color:inherit;opacity:.8}
.rbadge.lk:hover small svg{opacity:1}
.actions{align-items:center}
.seg{position:relative}
.seg button{position:relative;z-index:1}
.seg button.on,.seg button.on:hover{background:transparent;box-shadow:none;color:#0a0a0a}
.seg-pill{position:absolute;top:4px;bottom:4px;left:0;width:0;border-radius:10px;background:#ededed;box-shadow:0 4px 14px rgba(0,0,0,.35);pointer-events:none}
.seg.rdy .seg-pill{transition:transform .32s cubic-bezier(.22,1,.36,1),width .32s cubic-bezier(.22,1,.36,1)}
@keyframes viewin{from{opacity:0}}
.vt-in{animation:viewin 1.5s cubic-bezier(.22,1,.36,1)}
#top select.inp{flex:none;text-overflow:ellipsis;white-space:nowrap;overflow:hidden}
#top select.inp,#top .seg button{font-size:13.5px;font-weight:600}
#top select.inp{padding:0 30px 0 12px;background-position:right 11px center}
#typeSel{width:112px}
#genre{width:140px}
#sort{width:132px}
#top .inp,#top .btn:not(.icon){height:36px}
#top .btn.icon{width:36px;height:36px}
#top .seg button{padding:0 14px;height:28px;display:inline-flex;align-items:center;justify-content:center;line-height:1}
#top .seg button small{margin-left:6px;line-height:1;font-variant-numeric:tabular-nums}
#top.glass,#status.glass{background:rgba(20,20,22,.62);-webkit-backdrop-filter:blur(24px) saturate(1.5);backdrop-filter:blur(24px) saturate(1.5);box-shadow:inset 0 1px 0 rgba(255,255,255,.1),0 12px 32px rgba(0,0,0,.35)}
.overlay.mv{background:rgba(2,2,2,.86)}
.dd-btn{display:inline-flex;align-items:center;justify-content:space-between;gap:10px;cursor:pointer;text-align:left;font-family:inherit}
.dd-btn .dd-t{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dd-btn svg{flex:none;opacity:.7;transition:transform .2s cubic-bezier(.22,1,.36,1)}
.dd-btn.open svg{transform:rotate(180deg)}
#top .dd-btn{flex:none;height:36px;padding:0 12px;font-size:13.5px;font-weight:600}
#typeSel+.dd-btn{width:112px}
#genre+.dd-btn{width:140px}
#sort+.dd-btn{width:132px}
.sp-pop{position:fixed;z-index:90;padding:6px;border-radius:14px;overflow:auto;background:rgba(20,20,22,.62);-webkit-backdrop-filter:blur(24px) saturate(1.5);backdrop-filter:blur(24px) saturate(1.5);border:1px solid rgba(255,255,255,.12);box-shadow:inset 0 1px 0 rgba(255,255,255,.1),0 12px 32px rgba(0,0,0,.35);animation:pop .16s ease backwards;user-select:none}
.sp-i{display:flex;align-items:center;gap:10px;width:100%;min-height:34px;padding:0 12px;border:0;background:transparent;color:var(--text);border-radius:8px;font-size:13.5px;font-weight:500;text-align:left;cursor:pointer;white-space:nowrap;font-family:inherit;transition:background-color .12s cubic-bezier(.22,1,.36,1)}
.sp-pop.st{background:rgba(24,24,27,.98);-webkit-backdrop-filter:none;backdrop-filter:none}
.st-body .dd-btn{min-width:220px;font-size:14px;font-weight:600}
.sp-i:hover,.sp-i.hl{background:rgba(255,255,255,.1)}
.sp-i.sel{font-weight:600}
.sp-i svg{flex:none;opacity:.9}
.sp-ic{width:14px;height:14px;flex:none}
.wel .wlang .btn.on{background:#ededed;border-color:#ededed;color:#0a0a0a;box-shadow:inset 0 1px 0 rgba(255,255,255,.6)}
.wel .wlang .btn.on:hover{background:#fff;border-color:#fff}
.wel h2{font-size:26px;font-weight:700;margin:0 0 6px}
body.is-welcome:not(.v-wl) #top .search,body.is-welcome:not(.v-wl) #typeSel,body.is-welcome:not(.v-wl) #genre,body.is-welcome:not(.v-wl) #sort,body.is-welcome:not(.v-wl) #typeSel+.dd-btn,body.is-welcome:not(.v-wl) #genre+.dd-btn,body.is-welcome:not(.v-wl) #sort+.dd-btn,body.is-welcome:not(.v-wl) #btnRefresh{display:none!important}
.actions.act-grid{display:grid;grid-template-columns:max-content max-content;justify-content:start;align-items:center;gap:12px;margin:24px 0 8px}
.act-grid .btn{width:100%}
.meta-l.src{font-size:12px;color:var(--muted);margin:14px 0 0}
.meta-l.src b{font-weight:500}
.pzoom{position:fixed;inset:0;z-index:120;display:grid;place-items:center;padding:24px;background:rgba(2,2,2,.94);cursor:zoom-out;animation:fade .2s}
.pzoom img{max-width:100%;max-height:100%;object-fit:contain;border-radius:12px;box-shadow:0 24px 80px rgba(0,0,0,.6)}
.modal{border-radius:20px;padding:32px}
.m-grid{grid-template-columns:300px minmax(0,1fr);gap:36px}
.m-left{position:sticky;top:0;align-self:start}
.m-poster{border-radius:16px;border-color:rgba(255,255,255,.1);box-shadow:0 12px 32px rgba(0,0,0,.5)}
.m-right h2{margin:0 48px 4px 0;font-size:30px;line-height:1.15;font-weight:700;letter-spacing:-.01em}
.orig{font-size:15px;margin-bottom:12px}
.chips{gap:8px;margin:12px 0}
.chips.mm{align-items:center;gap:8px;margin:12px 0 16px}
.chips.mm .chip{padding:0;border:0;background:none;border-radius:0;font-size:14px;font-weight:500;color:var(--muted)}
.chips.mm .chip.t{color:var(--text);font-weight:600}
.chips.mm .chip:not(:first-child):not(.cp)::before{content:"\00b7";margin-right:8px;opacity:.7}
.chips.mm .chip.cp{width:30px;height:30px;padding:0;border-radius:8px;margin-left:4px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08)}
.chips.gn .chip{padding:5px 12px;border-radius:8px;font-size:12.5px;font-weight:500;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08)}
.ratings{gap:12px;margin:0 0 16px}
.rbadge{padding:8px 16px;border-radius:12px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1)}
.rbadge.lb{background:rgba(255,255,255,.05);border-style:solid}
.rbadge.lb[data-act]:hover{background:rgba(255,255,255,.1)}
.rbadge b{font-size:22px;font-variant-numeric:tabular-nums}
.meta-l{color:var(--text);font-size:14px;margin:8px 0}
.meta-l b{color:var(--muted);font-weight:500}
.desc{font-size:15px;line-height:1.65;max-width:72ch;margin:16px 0 24px;color:rgba(242,242,242,.82)}
.actions{gap:12px;margin:24px 0 12px}
.links{display:flex;flex-wrap:wrap;gap:12px;margin:0 0 8px}
.btn.lnk{width:auto;height:40px;padding:0 18px}
.ep{border-radius:10px}
</style>
</head>
<body>
<div id="splash"><img alt=""></div>
<div id="updBar" class="glass"></div><div id="base"></div><div id="userbg"></div><div id="bgA"></div><div id="bgB"></div><div id="shade"></div>

<div id="app">
  <header id="top" class="glass sheen">
    <div class="brand"><img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAJkAAABQCAYAAAAKu9fGAAAgAElEQVR42q1dV4xd13Vd574hKXaKdShWsYudIw6pYhVKoootW0osCInj2EHsACmOEeQjTpCv/OcjQADHgIEETtwUxZZiK7IkS7JlSiRNDjnsRSwzrMNhL2Kdeffk4+3DWdw67c74AcQM79zzTttnl7XLMRjAx1pbGGNKa+1qAE8CuAzgx8aYs9ZaY4yxgfefA7AcQBeA7xtjegPfb4wx1lo7HMDXABQAdhlj3vV9v2ozAsA3ANQAHDTGvJLRZhCAvwMwFsBVAP9sjLkcaVczxtSttV8C8AKAawC+a4xZ7+YamP90AP8E4JKs2TVZt07dF7V5AcAaadMj4+sF8L4xZjf3R/MZBuDrAAbLu1bWo9MY81NPX24+nwPwJwDOA7gpfd2UvTrI7Wh8CwB8U/ZokPQzBMAxDJDImuTnd2zjc9VaO8lN1EeU8vNDeb/NWlv43lXvt9q+z79w35E2LdTmFbeIiTYzrLV1aXPUWjskNBf+Pmvtm9TXmlBftF5/Yz/9eczXjsb2S+v/fFmvB43r6UCb1xJ9/SzQ7hHdjub0j4E2/9OEgX3qsgFLANQBbDTGdAe4mBGKvxvAbHn/V/KsSU6a/hQASgAr5ScAfOC+MjAm12a5/LQA3pW/mUAb93yBmxeAd40xN93pDnC/urV2KICF0uYcgB3ySulbL/n5svxelxN/A0CHnhet2QQAK+R9S+M1AA551sP9/QUZR49wlx4ATQA26/VQfT1Cfbn3rgI47OnLzWmtmlMpP98qBsDFHCFNAjBfvnC7/LkW2cj7pE0NwNZUN/KzVYjnFoA9CSJzn1XSxgDYFtl4HtsKaVPzbYQmZjlgawBMlzYXRJyFVAtrrV0E4H7pp0naXRTRpOdVkz6eADBOxtJEYyyFsG+3k33pFdH/OIkv7u9I4HACwEMAxnj6uiD/uC83p5myRzUSlYNkfO3FALiYa7tYFgAANmW8v1ImcDO1+cIpCtl8yOJ0JIjMnaxl8vMkgP2JNpbG5r5jc6qNHLKvESFelA326XAFcZfBNE4IgV2L9PHFwDp1y/yguI47MAvkeaHGcCQytxdUX+6dU8aYa2pu7qA9DmCYzMlQ22MA9g2EyNxk7peftxJEozeyI0YwTj8AMBXAHPl9tzHmljtBEW4xEcBcebxXlPciovTX5eQvkcddRJhlxOCZCeBZeqc7wv3qosu8RO+48ZyU7yuUQl231jYDeEZJCNffCWPMJ3IgrSKkZ+T3Oq2xAXAdwHEP93Oi/0n1Pe5z3PPcHYKn1D5aWvurAyGykkSZIxqfzOZJNBFX2mmMuRHafNqopQBGyO/tgQXQbZi7tmW2mQVgBhHzlcjY3Hf9kZzgW/L/Mz4io+9ZJv+clee++7SnneMSzwAYRVyCPyc8CrzTk58NEPwVEumaMFeL6Gfu5x0j7eloEefwtNkcW/gcfay01t5Fp3+HcJmaZ2PcRKeL0l9l81vp2daECHNtWujZpgxDwYnXIamxyQbWxfL8inrvVGBjC1L4CyUqQWY+tytlHV/2jN39/6DaeEfMC2jd9MZ3OyKjfXL9vqhUDv50BOb0IIDJwnS0WO4/kQVOf0xRNrSRQ9VG2kxOeSVD6bdKhF8lay9lKDxAv8f0MbeRTwOYpxb3bIQoB5O+o9f9TOAQTxFLz6g2RokwvfFPi+LdS+/e5khONKvxNUk7BPrqDqzbsx4drhCLeedAiMy1W+45/TaDK50lgikjnHI4gEV0ko5FdDjWrZzSfzih5PKpXZlJmO7Zn9H43fzORYjyAeEwTJSu3VH13U78fR7ASI+odL93qnZuLl/wHHhL+ib/zY2v1WMo8F4f7Vvq22s9BMBzAY55wB2CgehkTDTnAOyOKP2l2sj9ALpDSDotwDwAU+T3XTKxWqLNDAAz5fftsTaEjE8QrMtZXscCuqVT+OeJruR0K6P0lhyrjdf/TGC9no8ccssHiIyeGSLCQvt7RK2X+/lZ+b2uCNM9O604FURVmqueubG3y1rV+ktkdaX77DfGnE6AsKNoI9vlvVqCU7bQO1syAdUlJJI3pbAu4sjjyCDpDRCme/+rBEMYhjAigO2LnhPvoJyTilicqHzUZ9ERxz3nGdtamX89MO8TAav3uQhhXqKDwGDwcx7CdJ/furUv+gvCWmvHE0LengHCLhAFkXWeFAi7ip61Zyr9q+i9LZltHvUYFyagWw0Xq5I5ihEL83zAalsl+qv1bOInytpzf38yICpZgWfuUirlPXSgmPu5g7RYDpoNEPRpAmLZgn3es1Y1vfbFAPSxRQAmKKpNcaUiA08DgFIm0UJg5d5UG6X0d2e0cSfwEXq2LUCYbkM+KyK5VBtyDQ1nt6/tSx6rzZKovOiZx4sJnfCEWPOmYSiaUg7+QwGOVCiRzsTxlBBHPdDXGQcyS19WUILlAe58mte+GCAIa9Dwh+WAsKtIgTwYA2FlEpNFJ3MKfHciiqKUyIsFBAReyABu7yHs7iotjg0Q8dflbxp4vCJcSYvKIQFRdFsRpw2EzGOcoOjGQyxWwSUFvfM4gLuVMaLHyB4CR1SfC6gVVsEXheK0gxWnLUl/vg2A94fIrFL6j4olEQNhC6L6XeKeSIGwSwSEBIBt8m4KU5tPhsKWBA5XEHQxivCqLo+j2ulJ98lG+r73oqDpvu+fFRFFXfS+Uzc+EyAW/uz3eA4+HzjsLPbOkdvOStjR6sRaMY5Xqr58/dyBMxb90Me0CyaG3BtyDc2tCMKupGdtmQr8/fT7pkxM7Sl61ilcRc/FfeeXPafXvXdBCNFxW0NwQkg5ZhiCieULSs/yrc+RPlq5bVyEDgCLvZvCNZn7DYsYCrqv0lo7NmDBete+6KeovFdOJyvxRaZrKBeEXU3vbcsEVF2b6xQREsPUhhGYyBteqHd75d0/jMy1m91B0mYwfX9orU96iOWpgKj0YWuGkPfpHl0xJPaswtRih7dD9fUIGoGdpTpshQp8GBCR5SL3mitdALArsfnOXbWYWPz+lAIvp3MZEUssWsP5BVfLgekhABERFP1ezyZahfYzcaxAI7TJRhTxTo9LbHqgjXvW4wnX+Vxije5wcgtBjwHwWIT7OWLUaP/znr4s6c9HfxdEtor0kF2RzdSuoY/dydWhyer75wKYRgr8xVTotOhi8wiE7YkAt85v96dqnKcjYvUrCW56yjOPpyOislA6GQh7QkS8usPqiLpXdN41CY4JCmBgfXF8Qvc7R9haD8Wp6b4YhL0DZyz6CcKuIKLpchwowzW0TZTNFAi7Ao2AOcatUm2WCK4U9aPKhpTW2jloxGlZ6uusJyivtNZOE5DTt2bGQ6DO2Hk+YbVdIeJ0FubaiP7JxsIFiutfKJzfBtq5MR9Szz+bgQp0AbioIklCmJ8XAC/6AcLeLSKArb5awjU0NcOJ7tOtWBznxrUhAcI6zvdXhIwXtOm+zfl90Sl9yrHx6FZWuHFLQhHvAnCaDulM0V9De3NbJEkfg4gwBwXGZykk/ZTiSGsz+uqSsTUF4tSgmMCn1KcqnKyg8OnJFUHYmkQEtGeCo25zepwnPwO4fYrATa/znbjYJBF/lkK0HU52h8NZ2rycQeRnPaKyKbLxLiKilzZwDYC7IpaeVuB10GDs8J53OpkQzX0ev6Ovr4/V/58OON+NiNZPAeBFP/SxFtIz2iuAsMc9Aw5FtS4gP9uhSJuaLNjj6HMNnSX3Tigi4mse66iHiIxB4YXCWUOKuPM/dquD8nwG1qiV/rWZVnSHEMstWa8HMzjScRF7NSKWWkL3gwPORcdl4Nqnj+02xpzX+nPRDxC2hQYdi513HGYFDeCTDBB2MRqJDE7pvx5p4559i9rXQ+FDwplGAvhzj/5yMwCmvkSbEeIUl5xvT6y2SYmNhwo67BGI5OFMAHk/PXskAdzeJjK1hs9mYo9H6dmjCX9qm09/LiqCsDWCCYLIPT27R1D4gUbCFiEuZq19iNKxoMSfz/f4sliuGoq4iUagnVbeX8zgEmcBXKK8hIcDm6Hneows3cWiu8bEl4MvOGH2iQhw+6koWtnHiQQrxfoqlbHwTICpmFgiUVFRVHJSR1sGCLsYfS6btkwEvjUz8oK5GCuiTYExuejPv1bfZwnAva6U9xVktcWI7KTkZtaUqEyFfB+kZ2sSngGGL7opsfbRCHDLnz24M11wdAK6cPDFcelrCAUSaJywFvNhVyUy9idurhAJe5kU+BgCP5g45c0QBkdcrFVASLZ+anpehNk8pxI5oEJubnjS12J6i/Y/9gpivybBJVzW0FFFZDHxZUl8XaRImAUR6IJFV4eHI6W43wkKQ1ooYHTIBxsEwKsSGcfb78gAYVfSiT2eQZScM3AsEjrt/v/3KutHRwro97/h+T73+2UhdCPEUiMcKQW5fExib5HMIcX9zjiLVCJzVyb2pKQAUUuE2ZSwRg2LWDnITyT6suTLrVNfPuiiJDjLm0hUVEx/u5+I5oRsSCgSdii5hrYlQqc5QnWQY+8+xztxsRY0/G6l4kqFSr+vSYBeCxrhKSFc75LS3RYS10vpkUeUjmQyuN8xlzMpYnlchvjSIvaJTO53ilD7ueQZSbVjEftkok0QAy0qpL+NIOS+XaCDWOTF7MxMphAIuz0xxm/JKY5xRnYh/UVC9F1Q4uWpBJcIWWBPZ27gXnr2mQy/o2EiE7/jykyOdJAI+sGMeRkmMuG0qwJ91VLqU1FBVOYi9xx206TwtNyMIfiiKCiregmA3wtwGYYwDGVhvxRwT1mF2JfKhxgjFleIpEPGN9mT74hEPBjQF80aO4ROLdhPUNLkhD6mAVXmfjajr8PEaccHgiGN6IjBRKIcItP+xBJ9bpsyI5PpJIB9ifQ3K9GgCwkY3R2pVvO3ETdKr4IzgEaIzpjE6T1NoOOUDJyLlf4zdLBGJcTeHX5ECZleltnXOQJwH89wpN9B0IIR5s7rEkElDwX2ryQ880woiKHoRyRsVwKE1U70PcaYS5H0Nxd2s1BQeGfVdHqc1XVr7b2UVe3TrW5SGSqH7f1xBqfuxJ2JviMSRMm61XWVKxCz2pzyfIhi7cZncqROimx9JIP7afB2ScIo0R6CU4T7xRz9W2JBDDlEVnrCpy8HQFjHlSaRaygVRVEjTAoRpZ/T0YZFUOcrLtKDklaXR4iy8ITqPKHi+JO6lRDzY5lc4hQZCw9mcCTWrcqIe8dH0DdIXD6cgcWVtAe9AtwuT0Sg/DZHFKZqkHFSRyx2njOZxqYUQiGEW6LL/CWbw/x95BK6C3emo/k+FxVR/0FkYdn3yCb+Y5kAJwjKmUHWdIoj7TfGXKqgj2ljoSUDTGXud1QZGCZjXu3Ul4/TWjKkooEPqUXkGmR3VwBhkyn/JP7mAHgPDfeTG+RjwhlK5dh+SDwONiOLJyf8mdt0kYk/P1MRBwHGrQCGZ4rY3WQhLqsg9napuh1lBmHuk4M8grhflb5WBzgtg8OHYsZEkWlZrqTcwu0Zrp5WUm6PJLJ/3kcj7KROhsXDAF6iUp9uHF9UqVwIxcwLxNIiHDgFjB6hInQPZJj4HNrysdJbbMZ6bqfsqsmZYu8WtXuwAvfbQSFaUzP0sUK8EXsUQYf0sR2JEmBJItPI/aFInQh2DS2lMOg7QnEdgCtg7Y/QcFb3EmdwutA3XfwXJWXkJFjs7wcwyij6oxnE4tZlH4CzMqcHKsAQe2hdi0x9rBNAp9QDW5Kxf4VSPVpVSluqryPC/ZYmiGxTaixFBgjLyP32SJ0In2vIl8rm2n5JRAUH7TFivxDAeArrXhoRlZyBs7ci/nR7IyRa9P6MDbxtVVF+wX0VlP79iuPnGBg7xcXTgkbmfsoadUr/HsX9cvraJX0tinDaIkN9Si6km8AcNLJnUgVMuFbpEIWn+QbwcMLU70FfFpF7v0go8KcJfxoWOYVar9pGRfrmZBCmUQu8RCCPmCJeErGcFzVgeQWC3qSCQHO432EAh0W/rdLXZtpLE9DHCvFh7xoIkTEIO1i+JCf9bRXlIe6LKKidgf5d4ba3pMzAYIW7xTaw3RhzkXJD74kQjCOILuJ+S+mAxLhETXSkNqVOlBWIZVaGD9HHMVZW8DW3G2N6ZC3mVDBmtqg1txF14ZQvkagqTtaaSTQ6Pv+AMeacB4R1bf9LlG2OougVJL8TwD846II4aiqL51f0bA6VIY+12WyMuaAWNYdYDpJVtbICsWxQJa7KDLF3HsA24UhLKuzdRkIH7sroy4j3YhuNMaaPbU2UAEsOtK7Cp/cIZzEREHYc6SbeclKuMJoxpgN9YdMl+mLC2gGsNcacUFnVUyMTdokqb9PzGRkEAwDv0O85cEJJ+liPYHcLMvCxQjC8bRRxkhofx85fkDnNyORIJXHNKn1tF3E+gThtv0DYKJGROTqRMKMYcu8rJ7Up4UUwAL4tXMsFGv4YwGNyfw+n0o9EX7CkCYi9bQB20PUvcxNzd4T5PkV+LqgAVm4gPW56ot1tfYzwuGUVYIhNFTiS+9tR8v8uR777cCMFRIwLGBiOiNtzDnIqTmqRoL0potG5jzcJ0ykjGdyD5F0INPJVKW3uspDc9w5Hw5UUW5zXVOWfexP6mNM9nKXXTBWBYhvfpLjEnExRBAC/pYu1FlQQseuVKpIjztuNMVcVOpCjg2+kSNiYU/xELPusCpEx0ezISH9rJaX+UIaRMIXKEWynyEptzdylYA696bcAvEp6HdC4WiclGv6XFNYZQsw2gyN1kH46r0Is2HrKlZiWKWI/IQOjCvfbQPPK7esyifNliajknYkSYEkiKz1E05FxEQRnMt3ITH9zHKrNVfILiLYiYGxYuQjsAHkSRiSQdJf48AY9W5ABDbh1WW+MuapOPBLW6HXawNmZYs+5d44JhlfF3bWJDsHgzL72oi+ubslAQVjELkOQjRpS8SKImSSiNlfklM7KsxmJrb7v+p5a4JHoq4vhI0wjY9xFOtziCgGcv6ZnizL1sT3kqF5aQextkHWZmqH7MV64i9xJ2fAKlaKYO1AQFhnpbLOIaHJA2OX9uAhiJQXI7cwQr/o7anLy3lDfOy5CZO7zE6XDzcrYQMcB15OD+97MyIv1pAYsq2CUfUiHOFecbzPGnCP/aO7h2Uh9TQyUIygEeto5ECIb6EUQ0Zr+xCmHERe4nZgSAfVMYEF/6IwF+tvdVLnQBETXT9GXvV1k6i0QZfcgGQvjMzOxP6B6HHMyneJXaO1nV+BIH5KfeH7m4blFCMIssiC9kR0Z+5WFk+VeBFEfwEUQU0npLxM6og1wlf/wHICxEcvIypXKnST+x2UQmfuudXSd9TS619EklPfNdAByIY9dFJCwKDM2n7nf3ZkE7Q7PYQX/lBGMsEyBsDEi08j9vlD8NoGwo0lx3pZ5EcRyj5IaW/TSgwW9a4zZQ3W6XPtRCdHwI7UpzWgEAeas1S/o2fzMsu87iViaCUvM1cdydD/HtbsJPpqW0VdJ+tgt1VfokwXCeokscBFEDgi7sMJFEJpT1qmPWEkpX0LJvwUWfnQgibcmSvGbqr/JVPshxpHOAfjIQ2QpYvmIiGUeOfpTIvYj2ZehdJVPivu1GWPOk25lEpalUX3ViMiKgYCwSFgO95Hit7lCOameftQgy7lZt07tnFjdA+At0Tt0X8Mj/b4m7jE+NLMzx7xB/LGDCO3P0cfW0bP7MmqCOH3McfjxwgFzdMZ1FebFLrk2ErFTIjXIujL2K0pkvosg2iteBHEgUfPCJZrMJ5/o5QSoV/dcV/wdiTDwwSrDI/Fm3/f87Z5M6+vnjqhFgZ+ZcNo7fWwLPb83N4KCsr6nirWcU/NiAz1bmMlpDxN6P5numQqFKl3NAWGRKDPZmnN7iKec1O4ECuzLGWjLcdbTJJtE5P0gAp4O8bQvxGuxkbifVRwpBab+whhjBYoYkxFK5Nw7J6is1OxMjvRrWsMUUOyI7yxBC8gIJSoJo7xBIrYWudVkU9XadkXgIoilqYsgaNGmZZaT4smuzrzA1FKyLwcw/rtECoRqawwJfM8PxTJ07Upyb6WI5SNjzDESsxMSxoIOP3Ih57MyRSwDvrMyuV+bC1uS6JB7Mh3+H3q4XzlQEBaRG1pn0qQ2ZeBpS0k8Vb2N95NMUM+ouq7f9RV78YgOUHXrawBe4SgQEd0FWWCxzXiVOKkTYTH4wq3P+xQQMCHRlxOxZ0lNyRGxvni6HD3OOfs3erhfKMFk+++CyJahz5+4JeMLuab/zsyLIJaELhYIjG8+wRL7jDGHI3cBhJT2d4wxRwjuYP1tfCJW7Sr6YtVKJWJDpbMKgRPa3eVcou8Mi+hWLL64vuvcjDBy6wDfTA9B6SnLCvjj1fg23hOJA55FZK0eoikzykkdAHAyggJztZ/pGYkpOqTbZEAq1vM3N8f/DHDl0RFczc3jA0eg1MfUDDHfZoy5TOWw5mQWn3uXOC47+00ifmwHEfTUTAxvi9TlNRLq7jNmSoqELQPGVhaRaWjhY/TFb4dqkI1UF0GUGUV1V9Cib8pUgls9lxHEPqMUmz9GEbB11edY9N37FPr8t+dOolkZ4ut9NfeZCcng8j3fIxE7LuG6KilW7ToaERcsYlPE8BvqqzlB0JuAfl6QGrgIIha/XXiu/qtagyyazUSGyF3oi+ysUz8xUTlSvfOqmN18Ag050xHxc15AnwOeQeFJkfm69P33AyI2xlkOA9hDhtVMpHMBtPLOeBwSIdqMqzUHxLm+jbfsD+Jf9Qpno27jrVKDrIXyD2OJKZySN5OA2wMZZUTHKsX2lchcxgXG4Mb7pgCwNcpRiDnUHTEcQF+4TW9GMgyL5h7i9rnc7zdq3NMyRGyHh6B9F3O58KF9VZV+JjJ9hXNvwtXjuwhif0YNsgkEwu4NJaZE7lnaGSnr7vowdA9ATayhNscZPUQ8IbBwrv8fezZrOOF8IWL5UPTNJiLMSRnFA99Sz6dlHKr9QizuCsSmTAzvIxGxgxQeZwMg7OUqICw8d0ez7nM8Eb+ty0ntlnCbFAi7iDjHlkRJKXguu88BAkcSJwOA1xMRA2Mj1uERggXqSo8bG9hE9/9fqv+PiRAZZzOtU5s7N0PEOu7nDuPEBHzhnr2nnk/PvY23EpEFwqd3Z14EMS/zKmbfRRApUM+l5LV68ghjJ2k0gaQlgJ8n9Ijxkc173aPLuTZDA6Z+DY0gzHVqrJMCBK3B1NNygOsZQLGO1DU0vhEJD8ZN9OUc1CPwRe5NyFFOZjzIfc5tvHz1X9WLIK7HSrSTCG0mFp5KiS8ITBxOYmRXIiFiTATM/WFg7pMS8VabjTFdCvKYRNZpKG7+bSqVVYoeeE8Cw7vmOXzTIlElJUFBh4RpuII2msj4Nt7tAyGywnOF8+YK5QiuZBCMrvbTgcTNuiReRxMO15WBw3Ea/7uRy1UtRR1we7cxWwFsVbqcUQ51m8C5CuVJCV1C7yIh3vQYJc2JyOA2Y8xRBZDOyNCn31bowRhSZfT96ocSoHk2TsYXQVQBYQ+Gykl57i2fmXmzrvHoY6loTOshsnUZazAiML9XnZ/T02ZSYL4OunjHs34xwjQSurRPEcu4CFBsVQY8j3NKRvmqd9TzZuLqxgPCxkDzJJH5kPsTCRB2GLmGtmdeBLHCkzOQig54gJ6tz7hgjJ371zPvZhrp8XPeIF+l76BNjsACewHs9Lhepifm+pbnEE2L1POoKcCXM71mJ7LL9xF64BOxCETCGvTjU3iQ+/YIcs93hPf3Nt5odSBVF20pKabtGZjaTBIVB6EqaHvgjoI4GYf/rDPGHPL4OWNArHvvvUCkR0i3csTyMw8o3BypqmPE+t3uCVGfmBCxbxtjblI6IB+cMuc23v6Iy3m0CG0ZWE4LAZ1bK14EEbxZN0LIJxIgrFGln4CGmyvF4od4AhwN+mLVisAmTYgYC2+ocTrsrjnCWQ4H0PTpESKzQtDXCCi2ws1DFmkRGKMPKuEqP/v6g/T7RJljy20VLoLoqnARxAKKojibAcKupI3bngiG9EEkGzI47GD0+fqcEnyOFPC6Zy41D0bmiOUYifWS5jg0wF3cmr0hcXs1leA8PRH69KbnO0cFMDwnnTooT4EDN5tDGVMSEVL0Rx/TGwqk4+21a2iPDCBFMAsJj9qaCcKu9uBjqbIKXJAk57AMJs7HutGZREDk6ED/7zjOotqOojY+DOq1gL44KYLFXSR/ZamA4tGRNXonQNDTApZlv0FYBmOzkHu6I7wZfa6hFGrvgxVSnnwHwrbQsxwdbgT6nMJdCT+bIYIZrBbxFQqX8bUZ5Slj5dq+HmgzIUCYBRqelQ1MCKQHTolwv3XGmG5POmAzGm4iGyDon3vWruaBSnQNMttvIlMg7JZMEHZMJmqvfZzRklJE3JOJkC8ToFomkoUnZ7q53GcYGoVP3EHpRsNFE7tueZTS49gltEGN00Qy2j+lhJPv1aXBjY3hXIG9mhhwcruI2/Wev49S4UScVb59oETWRERjE64DLjxcFzM/B4StoZE4UlYoKbWYLl7YSyCsjcAwi6mIbpsHovH1M5oQ7SYRlZcD5auYUzjwtKDq3S5dji1SBm9LSmjhzX89sB5OxNYVPGGkzw8CBD1J2vQqNacGYKMEJRTktLfSRvdViEHS+bsgsmdYwc7w+K+V909EbtblE7GAKubslVPr20ReqDW0GVvlhDephdOfx/vhZ5shbZxe9pMMP+F05Slx4vb/IoQ9I3Cj8HEPZ3HrNi7i69wJYG/A+zFT9qfmsXz1GNmlONjTz26y0OsDIbJdaNSTOB+7wlko36ARlXBaNr8nwmFYUf6piKWfIC/r5oqY2b2Rk66NkWPy/ZeJyMqMmvrfE052FZ+OyfK1uS5rcIOwtTr6yhf4cLULIt6uyTPHOX9N2WB6rLfQKN7sAGLHdYZKjJuTEnVdbgDAv1KRZ0fcNY/VzFccflt+HyTzGoG+MKcBff4fZY3ugRFsJzAAAAAASUVORK5CYII=" alt="Kino" draggable="false"></div>
    <div class="seg" id="viewSeg"><i class="seg-pill"></i><button data-v="lib" class="on">Not watched<small id="ntCount"></small></button><button data-v="wl">Watchlist<small id="wlCount"></small></button><button data-v="wd">Watched<small id="wdCount"></small></button></div>
    <div class="search"><span data-ico="search"></span><input id="q" class="inp" autocomplete="off" spellcheck="false"><button type="button" class="sx" data-act="sx" data-for="q" title="Очистить"></button></div>
    <div class="grow"></div>
    <button class="btn" id="btnRemote" data-act="remote" title="Медиатека на другом компьютере"><span data-ico="net"></span><span class="lbl">Другой ПК</span></button>
    <select id="typeSel" class="inp"><option value="all">Все типы</option><option value="movie">Фильмы</option><option value="series">Сериалы</option><option value="hidden">Скрытое</option></select>
    <select id="genre" class="inp"><option value="">Все жанры</option></select>
    <select id="sort" class="inp">
      <option value="added">Недавние</option>
      <option value="rating">По рейтингу</option>
      <option value="yearDesc">Год: новые</option>
      <option value="yearAsc">Год: старые</option>
      <option value="title">По названию</option>
    </select>
    <button class="btn" id="btnRefresh" data-act="refresh" title="Пересканировать папки"><span data-ico="refresh"></span><span class="lbl">Сканировать</span></button>
    <button class="btn icon" data-act="folder" title="Добавить папку"><span data-ico="folder"></span></button>
    <button class="btn icon" data-act="settings" title="Настройки"><span data-ico="gear"></span></button>
  </header>

  <main id="main">
    <div id="banner" class="banner glass hidden"></div>
    <div id="grid"></div>
    <div id="empty" class="empty hidden"></div>
    <div id="wl"></div>
  </main>

  <footer id="status" class="glass"><span id="stT">Готово</span><div class="bar" id="stBar"><i></i></div>
    <div class="zoom" title="Размер постеров (двойной клик — сбросить)"><span class="zs"></span><input type="range" id="zoom" min="110" max="320" step="2" value="176"><span class="zb"></span></div></footer>
</div>

<div id="modalRoot"></div>
<div id="dlgRoot"></div>
<div id="toasts"></div>
<div id="busy" class="busy glass hidden"><span class="spinner"></span><span id="busyT"></span></div>

<script>
(function(){
"use strict";
const $=(s,r=document)=>r.querySelector(s);
const esc=s=>String(s==null?"":s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

const ICON={
 search:`<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>`,
 folder:`<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>`,
 gear:`<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>`,
 refresh:`<path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v6h-6"/>`,
 play:`<path d="M7 4.5v15a1 1 0 0 0 1.5.9l12-7.5a1 1 0 0 0 0-1.8l-12-7.5A1 1 0 0 0 7 4.5z" fill="currentColor" stroke="none"/>`,
 close:`<path d="M18 6 6 18M6 6l12 12"/>`,
 plus:`<path d="M12 5v14M5 12h14"/>`,
 film:`<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M7 3v18M17 3v18M3 8h4M3 12h4M3 16h4M17 8h4M17 12h4M17 16h4"/>`,
 pin:`<path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6z"/><path d="M12 14v7"/>`,
 eye:`<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>`,
 ext:`<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>`,
 fix:`<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18v3h3l6.3-6.3a4 4 0 0 0 5.4-5.4l-2.4 2.4-2.6-.6-.6-2.6z"/>`,
 check:`<path d="m5 12 5 5 9-10"/>`,
 copy:`<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>`,
 net:`<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>`,
 disk:`<path d="M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M3 13h18"/>`,
 trash:`<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M6 6l1 14h10l1-14"/><path d="M10 11v5M14 11v5"/>`,
 eyeoff:`<path d="M3 3l18 18"/><path d="M10.6 6.1A9.8 9.8 0 0 1 12 6c6.5 0 10 6 10 6a17 17 0 0 1-3.2 3.9M6.6 7.6A16 16 0 0 0 2 12s3.5 6 10 6a9.8 9.8 0 0 0 4-.9"/>`,
 undo:`<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>`,
 download:`<path d="M12 4v11"/><path d="m7 11 5 5 5-5"/><path d="M5 20h14"/>`,
 image:`<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="1.5"/><path d="m21 16-5-5-8 8"/>`,
 chev:`<path d="m6 9 6 6 6-6"/>`
};
const svg=(n,sz)=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="${sz||18}" height="${sz||18}">${ICON[n]||""}</svg>`;

const S={base:"",settings:{},items:[],byId:new Map(),q:"",type:"all",genre:"",sort:"added",problem:null,hint:null,view:"lib",ctx:null,del:null,pal:{},palSaved:new Set(),blob:new Map(),anim:false,wl:{items:[],results:[],notes:[],busy:false,msg:""},
  local:{},localTried:new Set(),failed:new Set(),current:null,curSeason:null,visCount:0,draft:{},
  fix:{open:false,q:"",src:"kp",results:[],busy:false,msg:""}};
const api=(n,...a)=>{ if(!window.pywebview||!window.pywebview.api) return Promise.reject(new Error("no bridge")); return window.pywebview.api[n](...a); };

function hash(s){let h=0;for(let i=0;i<s.length;i++){h=(h*31+s.charCodeAt(i))|0}return Math.abs(h)}
const pad2=n=>String(n).padStart(2,"0");
function fmtSize(b){ if(!b)return ""; const g=b/1073741824; return g>=1?g.toFixed(2)+" ГБ":(b/1048576).toFixed(0)+" МБ"; }
const rcls=r=>r>=7?"rg":(r>=5?"ry":"rr");
const fmtR=r=>Number(r).toFixed(1);
const effType=it=>(it.meta&&it.meta.type)||it.kind;
function pickRating(m){
  if(!m)return null;
  const o={kp:["ratingKp",1,""],imdb:["ratingImdb",1,""],tmdb:["ratingTmdb",1,""],lb:["ratingLb",2,"★"]};
  const order=[S.settings.card_rating||"imdb","imdb","kp","tmdb","lb"];
  for(const k of order){ const f=o[k], v=m[f[0]]; if(v!=null)return{v:v*f[1],t:fmtR(v)+f[2]}; }
  return null;
}
function primR(it){ return pickRating(it.meta); }
function prim(it){ const r=primR(it); return r?r.v:null; }
function srcLinks(m){
  if(!m)return {};
  return {"Кинопоиск":m.source==="kp"?m.url:(m.urlKp||""),"IMDb":m.urlImdb||(m.imdbId?`https://www.imdb.com/title/${m.imdbId}/`:(m.source==="imdb"?m.url:"")),"TMDB":m.source==="tmdb"?m.url:""};
}
function ratingBadge(name,v,url){
  const link=url?` data-act="open-url" data-url="${esc(url)}" title="Открыть на ${name}"`:"";
  return `<div class="rbadge ${rcls(v)}${url?" lk":""}"${link}><b>${fmtR(v)}</b><small>${name}${url?svg("ext",12):""}</small></div>`;
}
function srcLine(m){
  if(!m||!m.source)return "";
  const names={kp:"Кинопоиск",imdb:"IMDb",tmdb:"TMDB",lb:"Letterboxd"};
  const parts=[names[m.source]||m.source];
  if(m.manual)parts.push("вручную");
  else if(m.via==="omdb")parts.push("через OMDb");
  else if(m.via==="imdb")parts.push(m.source==="kp"?"по IMDb ID":"поиск на IMDb");
  else if(m.via==="translit")parts.push("по транслиту");
  else if(m.via==="kp-search")parts.push("через поиск по Кинопоиску");
  return `<div class="meta-l src"><b>Источник данных:</b> ${parts.join(" · ")}</div>`;
}
function lbBadge(m){
  if(!m||(m.ratingLb==null&&!m.urlLb))return "";
  const r=m.ratingLb, url=m.urlLb||(m.source==="lb"?m.url:""), link=url?` data-act="open-url" data-url="${esc(url)}" title="Открыть на Letterboxd"`:"";
  return `<div class="rbadge lb ${r!=null?rcls(r*2):""}${url?" lk":""}"${link}><b>${r!=null?fmtR(r):"—"}</b><small>Letterboxd${r!=null?" · из 5":""}${url?svg("ext",12):""}</small></div>`;
}
const cap1=s=>{ if(s&&S.lang==="en"&&trRe)s=trText(s); return s?s.charAt(0).toUpperCase()+s.slice(1):s; };
function toast(msg,kind){ const t=document.createElement("div"); t.className="toast glass "+(kind||""); t.textContent=msg; $("#toasts").appendChild(t); setTimeout(()=>{t.classList.add("out");setTimeout(()=>t.remove(),450)},3800); }
function setBusy(on,msg){ $("#busy").classList.toggle("hidden",!on); $("#busyT").textContent=msg||""; }

let bgFlip=false,bgCur="";
function setBg(url){
  if(document.body.classList.contains("bg-custom"))return;
  url=shown(url);
  if(!url||url===bgCur)return; bgCur=url;
  const on=bgFlip?$("#bgB"):$("#bgA"), off=bgFlip?$("#bgA"):$("#bgB"); bgFlip=!bgFlip;
  const img=new Image(); img.referrerPolicy="no-referrer"; if(S.base&&url.startsWith(S.base))img.crossOrigin="anonymous";
  img.onload=()=>{ if(bgCur!==url)return;
    let uri=url; try{ const w=40,h=60,cv=document.createElement("canvas"); cv.width=w; cv.height=h; const cx=cv.getContext("2d"); cx.drawImage(img,0,0,w,h);
      const d=cx.getImageData(0,0,w,h); for(let i=0;i<d.data.length;i+=4){ const g=(d.data[i]*.3+d.data[i+1]*.59+d.data[i+2]*.11)*.5; d.data[i]=d.data[i+1]=d.data[i+2]=g; } cx.putImageData(d,0,0); uri=cv.toDataURL("image/jpeg",.7); }catch(e){ return; }
    on.style.backgroundImage=`url("${uri}")`; on.classList.add("on"); off.classList.remove("on"); };
  img.src=url;
}
function clearBg(){ bgCur=""; $("#bgA").classList.remove("on"); $("#bgB").classList.remove("on"); }
function itemBg(it){ const m=it.meta; return (m&&(m.poster||m.posterPreview))||S.local[it.id]||""; }

function visibleItems(){
  const q=S.q.trim().toLowerCase().replace(/ё/g,"е");
  const a=S.items.filter(it=>{
    if(S.type==="hidden"){ if(!it.hidden)return false; }
    else { if(it.hidden||!inView(it))return false; if(S.type!=="all"&&effType(it)!==S.type)return false; }
    if(S.genre&&!((it.meta&&it.meta.genres)||[]).includes(S.genre))return false;
    if(q){ const m=it.meta||{}; const hay=[it.title,m.titleRu,m.titleOrig,m.titleEn,it.year,m.year].join(" ").toLowerCase().replace(/ё/g,"е"); if(!hay.includes(q))return false; }
    return true;
  });
  const t=it=>String(titleOf(it)||"").toLowerCase();
  const y=it=>(it.meta&&it.meta.year)||it.year||0;
  const cmp={
    added:(a,b)=>b.added-a.added,
    rating:(a,b)=>{const x=prim(a),z=prim(b); return (z==null?-1:z)-(x==null?-1:x);},
    yearDesc:(a,b)=>y(b)-y(a),
    yearAsc:(a,b)=>(y(a)||9999)-(y(b)||9999),
    title:(a,b)=>t(a).localeCompare(t(b),"ru")
  }[S.sort];
  a.sort(cmp);
  const pin=a.filter(i=>i.pinned).sort((x,z)=>z.pinned-x.pinned);
  return pin.length?pin.concat(a.filter(i=>!i.pinned)):a;
}
function refreshGenres(){
  const set=new Set();
  if(S.view==="wl")S.wl.items.forEach(e=>((e.meta&&e.meta.genres)||[]).forEach(g=>set.add(g)));
  else S.items.filter(inView).forEach(i=>((i.meta&&i.meta.genres)||[]).forEach(g=>set.add(g)));
  const arr=[...set].sort((a,b)=>a.localeCompare(b,"ru"));
  if(S.genre&&!set.has(S.genre))S.genre="";
  $("#genre").innerHTML=`<option value="">Все жанры</option>`+arr.map(g=>`<option value="${esc(g)}" ${g===S.genre?"selected":""}>${esc(cap1(g))}</option>`).join("");
}

function posterOf(it,preview){
  const m=it.meta; if(m&&m.poster_sel==="none")return "";
  const remote=(!S.failed.has(it.id)&&m)?(preview?(m.posterPreview||m.poster):(m.poster||m.posterPreview)):"";
  return remote||S.local[it.id]||"";
}
function cardHTML(it,i){
  const m=it.meta, title=metaTitle(m,it.title), year=(m&&m.year)||it.year||"";
  const pr=primR(it), src=posterOf(it,true);
  const type=effType(it)==="series"?"Сериал":"Фильм";
  const sub=(it.kind==="series"&&!it.ghost)?` · ${it.nFiles} эп.`:"";
  const hue=hash(it.title)%360;
  const initial=(it.title||"?").trim().charAt(0).toUpperCase();
  const dur=m&&m.duration?` · ${m.duration} мин`:"";
  const pkey=/^https?:/.test(src)?src:(S.local[it.id]?"local:"+it.id:"");
  return `<div class="card sheen${it.ghost?" ghost":""}${it.pinned?" pinned":""}" data-act="open" data-id="${it.id}" data-pkey="${esc(pkey)}" style="animation-delay:${Math.min(i||0,24)*18}ms;${palStyle(pkey)}"><div class="halo"></div>
    <div class="cv">
      <div class="stub" style="--g:${hue%8}"><div class="stub-l">${esc(initial)}</div><div class="stub-n">${m?"":(it.notFound?"Нет в базе":"Нет метаданных")}</div></div>
      ${src?`<img data-poster="1" src="${esc(shown(src))}" decoding="async" loading="lazy" referrerpolicy="no-referrer" alt="">`:""}
      ${pr?`<div class="rt ${rcls(pr.v)}">${pr.t}</div>`:""}${it.pinned?`<div class="pn${S.freshPin===it.id?" fresh":""}">${svg("pin",14)}</div>`:""}
      ${(it.ghost||effType(it)==="series")?`<div class="tp">${it.ghost?"Нет на диске":type+sub}</div>`:""}
      <div class="cap"><div class="cap-t">${esc(title)}</div><div class="cap-s">${esc(year)}${dur}</div></div>
    </div></div>`;
}
function updateCard(id){
  const el=document.querySelector(`.card[data-id="${id}"]`); if(!el)return;
  const it=S.byId.get(id); if(!it)return;
  const tmp=document.createElement("div"); tmp.innerHTML=cardHTML(it,0);
  const n=tmp.firstElementChild; n.style.animation="none"; el.replaceWith(n); observePalettes();
}
function needLocal(it){ return it.hasLocalPoster&&!S.local[it.id]&&!S.localTried.has(it.id)&&(!posterOf(it,true)); }
async function loadLocal(id){
  if(S.localTried.has(id))return; S.localTried.add(id);
  try{ const uri=await api("get_local_poster",id); if(uri&&typeof uri==="string"){ S.local[id]=await toBlobUrl(uri); updateCard(id); if(S.current===id&&!S.fix.open)renderModal(); } }catch(e){}
}
document.addEventListener("error",e=>{
  const img=e.target; if(!img||img.tagName!=="IMG"||!img.dataset.poster)return;
  if(S.base&&img.src.startsWith(S.base)&&!img.dataset.retry){ img.dataset.retry="1"; try{ img.src=decodeURIComponent(img.src.slice(S.base.length)); return; }catch(_){} }
  const card=img.closest(".card"); const id=card&&card.dataset.id; img.remove();
  if(id){ S.failed.add(id); const it=S.byId.get(id); if(it&&it.hasLocalPoster){ if(S.local[id])updateCard(id); else loadLocal(id); } }
},true);

function welcomeHTML(){
  const roots=S.settings.root_folders||[], set=S.settings.lang_set==="1", en=S.lang==="en";
  const logo=(document.querySelector(".brand img")||{}).src||"";
  const keyName=en?"omdb_api_key":"kp_api_key", keyVal=S.settings[keyName]||"";
  const rootsH=roots.length?`<div class="wroots">${roots.map(r=>`<div title="${esc(r)}">${esc(r)}</div>`).join("")}</div>`:"";
  const api_=!set?"":(en?`<div class="wst">Ключ OMDb</div>
    <ol class="wins"><li>Откройте сайт omdbapi.com/apikey.aspx, выберите бесплатный тариф (FREE) и укажите почту.</li><li>Подтвердите ключ в письме и вставьте его ниже.</li></ol>
    <div class="row"><button class="btn" data-act="open-url" data-url="https://www.omdbapi.com/apikey.aspx">${svg("ext",16)} Получить ключ OMDb</button></div>`
    :`<div class="wst">Ключ Кинопоиска</div>
    <ol class="wins"><li>Откройте сайт kinopoiskapiunofficial.tech и войдите через почту или GitHub.</li><li>Скопируйте API-ключ из личного кабинета и вставьте его ниже.</li></ol>
    <div class="row"><button class="btn" data-act="open-url" data-url="https://kinopoiskapiunofficial.tech">${svg("ext",16)} Получить ключ Кинопоиска</button></div>`)
    +(set?`<div class="row" style="margin-top:10px"><input type="password" id="w-key" class="inp grow" value="${esc(keyVal)}" autocomplete="off" spellcheck="false" data-field="${keyName}"><button class="btn icon" data-act="toggle-key" data-for="w-key" title="Показать/скрыть">${svg("eye",16)}</button></div>
    <div class="wwarn ${keyVal?"hidden":""}" id="w-warn">Без ключа названия, постеры и описания будут находиться неточно и очень медленно. Ключ можно добавить позже в настройках.</div>`:"");
  return `<div class="box glass wel"><img class="wlogo" src="${esc(logo)}" alt="Kino" draggable="false">
    <h2>Kino</h2>
    <p class="wsub">Каталог рекурсивно просканирует все подпапки и найдёт только видеофайлы. Можно добавить несколько папок.</p>
    <div class="wst">Папка с фильмами и сериалами</div>
    <div class="row"><button class="btn ${roots.length?"":"primary"} lg" data-act="folder">${svg("folder")} ${roots.length?"Добавить ещё папку":"Выбрать папку"}</button></div>${rootsH}
    <div class="wst">Язык</div>
    <div class="wlang"><button class="btn lg ${set&&!en?"on":""}" data-act="w-lang" data-v="ru">Русский</button><button class="btn lg ${set&&en?"on":""}" data-act="w-lang" data-v="en">English</button></div>
    <p class="wsub" style="margin-top:8px">${set?(en?"Названия, описания и постеры берутся из OMDb. Постер конкретного фильма можно сменить правой кнопкой мыши по постеру.":"Названия, описания и постеры берутся из Кинопоиска. Постер конкретного фильма можно сменить правой кнопкой мыши по постеру."):"Язык определяет названия, описания и источник постеров: русский — Кинопоиск, English — OMDb."}</p>
    ${api_}
    <div class="wgo"><button class="btn primary lg" data-act="w-start" ${roots.length&&set?"":"disabled"}>Начать</button></div></div>`;
}
async function welcomeLang(v){
  S.settings.lang_set="1"; S.settings.lang=v;
  try{ await api("save_settings",{lang:v,lang_set:"1"}); }catch(e){}
  setLang(v); renderGrid();
}
async function welcomeStart(){
  if(!hasRoots()){ toast("Сначала выберите папку","err"); return; }
  S.welcome=false; renderGrid(); queueMissing(false);
}
let wKeyT=0;
document.addEventListener("input",e=>{
  const t=e.target; if(!t||t.id!=="w-key")return;
  const f=t.dataset.field, v=t.value.trim(); S.settings[f]=v;
  const w=$("#w-warn"); if(w)w.classList.toggle("hidden",!!v);
  clearTimeout(wKeyT); wKeyT=setTimeout(()=>{ api("save_settings",{[f]:v}).catch(()=>{}); },400);
});
function hasRoots(){ return (S.settings.root_folders||[]).length>0; }
function renderGrid(){
  const list=visibleItems(); S.visCount=list.length;
  const grid=$("#grid"), empty=$("#empty");
  const wel=!S.remote&&(S.welcome||!hasRoots());
  document.body.classList.toggle("is-welcome",wel);
  if(wel){
    grid.innerHTML=""; grid.classList.add("hidden"); empty.classList.remove("hidden");
    empty.innerHTML=welcomeHTML();
  } else if(!S.items.length){
    grid.innerHTML=""; grid.classList.add("hidden"); empty.classList.remove("hidden");
    empty.innerHTML=`<div class="box glass"><div class="big">${svg("disk",34)}</div><h2>Видеофайлов не найдено</h2><p>В выбранных папках нет поддерживаемых видео (mp4, mkv, avi, mov, wmv, flv, webm, m4v, ts, DVD и Blu-ray папки). Семплы и прочие файлы игнорируются.</p><div class="row" style="justify-content:center"><button class="btn primary lg" data-act="refresh">${svg("refresh")} Пересканировать</button><button class="btn lg" data-act="folder">${svg("folder")} Добавить папку</button></div></div>`;
  } else if(!list.length){
    grid.innerHTML=""; grid.classList.add("hidden"); empty.classList.remove("hidden");
    empty.innerHTML=emptyMsg();
  } else {
    empty.classList.add("hidden"); grid.classList.remove("hidden");
    grid.classList.toggle("noanim",!S.anim); S.anim=false;
    grid.innerHTML=list.map((it,i)=>cardHTML(it,i)).join("");
    markPinGap(grid);
    list.forEach(it=>{ if(needLocal(it))loadLocal(it.id); });
  }
  renderStatus(); observePalettes(); prefetchPosters();
}

const F={queue:[],queued:new Set(),force:new Set(),total:0,done:0,running:false,abort:false};
function renderStatus(){
  updateCounts();
  let t=S.view==="wl"?`В Watchlist: ${S.wl.items.length}`:(hasRoots()?`${S.visCount} из ${S.items.filter(i=>S.type==="hidden"?i.hidden:(inView(i)&&!i.hidden)).length}`:"Папка не выбрана");
  if(F.running&&F.total)t+=` · метаданные ${F.done}/${F.total}`;
  $("#stT").textContent=t;
  $("#stBar").classList.toggle("on",F.running&&F.total>0);
  $("#stBar i").style.width=(F.total?Math.round(F.done/F.total*100):0)+"%";
}
const PROB={
 nokey:["Нет доступных источников метаданных. Вставьте API-ключ в настройках или включите поиск через IMDb.","settings"],
 hint:["Ключ Кинопоиска не указан: данные ищутся через IMDb, примерно один фильм за несколько секунд, описания на английском. Вставьте ключ в настройках — будет быстрее и по-русски.","settings"],
 hintEn:["Ключ OMDb не указан: данные ищутся через сайт IMDb, это медленнее и менее надёжно. Вставьте ключ OMDb в настройках.","settings"],
 auth:["API-ключ отклонён сервисом. Проверьте ключ в настройках.","settings"],
 neterr:["Нет подключения к интернету или сервис недоступен. Показаны данные из кэша и заглушки.","retry"],
 limit:["Суточный лимит запросов API исчерпан. Уже загруженное сохранено в кэш — продолжим позже.","retry"],
 rate:["Слишком много запросов — сервис просит подождать. Попробуйте чуть позже.","retry"],
 webrate:["IMDb временно ограничил запросы. Всё найденное сохранено, повторите чуть позже. С API-ключом такого не бывает.","retry"]
};
function renderBanner(){
  const b=$("#banner"); const key=S.problem||S.hint; if(!key){b.classList.add("hidden");return;}
  const p=PROB[key]||["Ошибка API.","retry"]; b.classList.remove("hidden");
  b.innerHTML=`<span class="b-ico">!</span><span class="b-t">${esc(p[0])}</span><button class="btn sm" data-act="${p[1]==="settings"?"settings":"retry"}">${p[1]==="settings"?"Настройки":"Повторить"}</button>`;
}

function applyItem(item){
  const old=S.byId.get(item.id); if(!old)return;
  Object.assign(old,item); updateCard(item.id);
  if(S.current===item.id&&!S.fix.open&&!document.querySelector(".modal.sm"))renderModal();
}
function enqueue(ids,force){
  ids.forEach(id=>{ if(F.queued.has(id))return; F.queued.add(id); F.queue.push(id); if(force)F.force.add(id); F.total++; });
  renderStatus(); if(!F.running&&F.queue.length)runWorkers();
}
async function runWorkers(){
  F.running=true; F.abort=false;
  const worker=async()=>{
    while(!F.abort&&F.queue.length){
      const id=F.queue.shift(); let r;
      try{ r=await api("fetch_meta",id,F.force.has(id)); }catch(e){ r={ok:false,status:"error"}; }
      F.done++;
      if(r&&r.item)applyItem(r.item);
      const st=r&&r.status?r.status:"error";
      if(st==="nokey"||st==="neterr"||st==="webrate"){ F.abort=true; S.problem=st; renderBanner(); }
      else if(["auth","limit","rate"].includes(st)||(r&&r.warn)){ S.problem=["auth","limit","rate"].includes(st)?st:r.warn; renderBanner(); }
      else if(r&&r.hint==="nokey"&&!S.hint){ S.hint=S.lang==="en"?"hintEn":"hint"; renderBanner(); }
      renderStatus();
    }
  };
  await Promise.all([worker(),worker(),worker()]);
  if(F.queue.length&&!F.abort){ F.running=false; return runWorkers(); }
  F.running=false; F.queue.length=0; F.queued.clear(); F.force.clear(); F.total=0; F.done=0;
  refreshGenres(); renderGrid(); imdbFill();
}
let imdbBusy=false;
async function imdbFill(){
  if(imdbBusy||S.remote)return; imdbBusy=true;
  try{
    const r=await api("fill_imdb_ratings");
    if(r&&r.ok&&r.updates&&r.updates.length){
      let wlc=false;
      r.updates.forEach(u=>{
        if(u.id){ const it=S.byId.get(u.id); if(it&&it.meta){ it.meta.ratingImdb=u.ratingImdb; updateCard(u.id); if(S.current===u.id&&!S.fix.open&&$("#modalRoot").firstChild&&!document.querySelector(".modal.sm"))renderModal(); } }
        else if(u.key){ const e=S.wl.items.find(x=>x.key===u.key); if(e&&e.meta){ e.meta.ratingImdb=u.ratingImdb; wlc=true; } }
      });
      if(wlc&&S.view==="wl")renderWLGrid();
    }
  }catch(e){}
  imdbBusy=false;
}
function queueMissing(retryMissing){
  if(S.welcome||S.remote)return;
  const en=S.lang==="en", kp=!!S.settings.kp_api_key&&!en, now=Date.now()/1000;
  const todo=S.items.filter(i=>!i.ghost&&!i.meta&&(retryMissing||!i.notFound));
  const upg=S.items.filter(i=>!i.ghost&&i.meta&&((kp&&!i.meta.manual&&i.meta.source!=="kp"&&now-(i.meta.kp_tried||0)>7*86400)||(i.meta.imdbId&&i.meta.ratingImdb==null&&i.meta.ratingKp==null&&now-(i.meta.rt_tried||0)>3*86400)||(!i.meta.manual&&(i.meta.mv||1)<(S.settings.match_v||1))));
  if(!todo.length&&!upg.length)return;
  if(!(en?S.settings.omdb_api_key:kp)&&todo.length&&!S.problem){ S.hint=en?"hintEn":"hint"; renderBanner(); }
  enqueue(todo.filter(i=>!i.notFound).map(i=>i.id),false);
  enqueue(todo.filter(i=>i.notFound).map(i=>i.id),true);
  enqueue(upg.map(i=>i.id),false);
}

async function loadLibrary(retryMissing){
  setBusy(true,"Сканирование папки…");
  let r; try{ r=await api("scan"); }catch(e){ setBusy(false); toast("Ошибка сканирования","err"); return; }
  setBusy(false);
  if(!r||!r.ok){ S.items=[]; S.byId=new Map(); refreshGenres(); renderGrid(); if(r&&r.error&&(hasRoots()||S.remote))toast(r.error,"err"); return; }
  S.items=r.items.concat(r.ghosts||[]); S.byId=new Map(S.items.map(i=>[i.id,i]));
  if(r.missing&&r.missing.length)toast("Папка недоступна: "+r.missing.join(", "),"err");
  S.problem=null; S.hint=null; renderBanner(); refreshGenres(); S.anim=true; renderGrid();
  queueMissing(retryMissing); setTimeout(imdbFill,3000);
}
async function refreshAll(){
  if(!hasRoots()&&!S.remote){ openSettings(); return; }
  const b=$("#btnRefresh"); b.classList.add("spin"); const n0=S.items.filter(i=>!i.ghost).length;
  await loadLibrary(true);
  b.classList.remove("spin"); const dn=S.items.filter(i=>!i.ghost).length-n0;
  toast("Папки пересканированы"+(dn?` · ${dn>0?"+":""}${dn}`:""));
}

function closeModal(){ if(!S.saving&&S.draft&&$("#s-roots")){ saveSettings(true); return; } ddClose(); clearBg(); $("#modalRoot").innerHTML=""; S.current=null; S.fix.open=false; S.fix.results=[]; S.fix.msg=""; }
function nextEpisode(it){
  if(it.kind==="movie"){ const f=it.files[0]; return f?{path:f.path,label:"Смотреть"}:null; }
  const all=[]; it.seasons.forEach(s=>s.episodes.forEach(e=>all.push({e,season:s.season})));
  if(!all.length)return null;
  let idx=all.findIndex(x=>!x.e.watched); const any=all.some(x=>x.e.watched);
  if(idx<0){idx=0;}
  const x=all[idx]; const code=x.e.episode!=null?` · S${pad2(x.season)}E${pad2(x.e.episode)}`:"";
  return {path:x.e.path,label:(any&&idx>0?"Продолжить":"Смотреть")+code};
}
function epRow(e){
  return `<div class="ep ${e.watched?"seen":""}" data-act="play" data-path="${esc(e.path)}">
    <span class="ep-n">${e.episode!=null?e.episode:"•"}</span>
    <span class="ep-t"><b>${e.episode!=null?"Серия "+e.episode:"Файл"}</b><small>${esc(e.name)}</small></span>
    <span class="ep-s">${fmtSize(e.size)}</span><span class="ep-p">${e.watched?svg("check",16):svg("play",14)}</span></div>`;
}
function openModal(id){
  const it=S.byId.get(id); if(!it)return;
  S.current=id; S.fix={open:false,q:(it.meta&&(it.meta.titleRu||it.meta.titleOrig))||it.title,src:S.settings.kp_api_key?"kp":"imdb",results:[],busy:false,msg:""};
  if(it.kind==="series"&&it.seasons.length){
    let pick=it.seasons[0].season;
    for(const s of it.seasons){ if(s.episodes.some(e=>!e.watched)){pick=s.season;break;} }
    S.curSeason=pick;
  } else S.curSeason=null;
  renderModal(); setBg(itemBg(it)); if(needLocal(it))loadLocal(it.id); queuePalette(posterOf(it,true));
}
function fixPanel(it){
  const f=S.fix; if(!f.open)return "";
  const hasKp=!!S.settings.kp_api_key, hasTm=!!S.settings.tmdb_api_key;
  const opts=[["lb","Letterboxd"],["imdb","IMDb"]];
  if(hasTm)opts.unshift(["tmdb","TMDB"]);
  if(hasKp)opts.unshift(["kp","Кинопоиск"]);
  if(!opts.some(o=>o[0]===f.src))f.src=opts[0][0];
  return `<div class="fix">
    <div class="row"><input id="fixQ" class="inp grow" value="${esc(f.q)}" autocomplete="off">
    <select id="fixSrc" class="inp">${opts.map(o=>`<option value="${o[0]}" ${f.src===o[0]?"selected":""}>${o[1]}</option>`).join("")}</select>
    <button class="btn primary" data-act="fix-go">${svg("search",16)} Найти</button></div>
    <div id="fixRes">${fixResults()}</div>
    <div class="row"><button class="btn sm" data-act="fix-auto">Автопоиск заново</button><span class="hint">Можно вставить ссылку: kinopoisk.ru/film/…, letterboxd.com/film/… или imdb.com/title/… Транслит (Izgnanie) понимают IMDb и Letterboxd.</span></div></div>`;
}
function fixResults(){
  const f=S.fix;
  if(f.busy)return `<div class="dd"><div class="dd-e">Поиск…</div></div>`;
  if(f.msg)return `<div class="dd"><div class="dd-e">${esc(f.msg)}</div></div>`;
  if(!f.results.length)return "";
  return `<div class="dd">${f.results.map((c,i)=>{
    const r=c.ratingKp!=null?c.ratingKp:(c.ratingImdb!=null?c.ratingImdb:c.ratingTmdb);
    const SRC={kp:"Кинопоиск",tmdb:"TMDB",imdb:"IMDb",lb:"Letterboxd"};
    const info=[SRC[c.source],c.titleOrig&&c.titleOrig!==c.titleRu?c.titleOrig:null,c.year,c.type==="series"?"Сериал":"Фильм",r!=null?"★ "+fmtR(r):(c.ratingLb!=null?"★ "+fmtR(c.ratingLb)+"/5":null),c.stars||null].filter(Boolean).join(" · ");
    const pv=c.posterPreview||c.poster;
    return `<div class="dd-i" data-act="fix-pick" data-i="${i}">${pv?`<img src="${esc(shown(pv))}" referrerpolicy="no-referrer" alt="">`:`<div class="ph"></div>`}<div><b>${esc(c.titleRu||c.titleOrig||"Без названия")}</b><small>${esc(info)}</small></div></div>`;
  }).join("")}</div>`;
}
function renderModal(){
  const it=S.byId.get(S.current); if(!it){closeModal();return;}
  const m=it.meta;
  const title=metaTitle(m,it.title);
  const orig=origLine(m,title);
  const isSeries=effType(it)==="series";
  const poster=posterOf(it,false);
  const hue=hash(it.title)%360, initial=(it.title||"?").trim().charAt(0).toUpperCase();
  const rb=[]; if(m){ if(m.ratingKp!=null)rb.push(["Кинопоиск",m.ratingKp]); if(m.ratingImdb!=null)rb.push(["IMDb",m.ratingImdb]); if(m.ratingTmdb!=null)rb.push(["TMDB",m.ratingTmdb]); }
  const chips=[`<span class="chip t">${isSeries?"Сериал":"Фильм"}</span>`];
  const yr=(m&&m.year)||it.year; if(yr)chips.push(`<span class="chip">${yr}</span>`);
  if(m&&m.duration)chips.push(`<span class="chip">${m.duration} мин${isSeries?" / серия":""}</span>`);
  if(it.kind==="series")chips.push(`<span class="chip">${it.nFiles} файл(ов) в каталоге</span>`);
  chips.push(`<button class="chip cp" data-act="copy-title" data-id="${it.id}" title="Копировать название и год">${svg("copy",14)}</button>`);
  const genres=(m&&m.genres)||[], countries=(m&&m.countries)||[];
  const ne=nextEpisode(it);
  const noMeta=!m?`<div class="note">${it.notFound?"Фильм не найден в базе по названию файла. Нажмите «Исправить совпадение» и найдите его вручную.":"Метаданные ещё не загружены. Вставьте API-ключ Кинопоиска в настройках или дождитесь загрузки."}<br>Распознано из имени файла: <b>${esc(it.title)}</b>${it.year?" ("+it.year+")":""}</div>`:"";
  let list="";
  if(it.kind==="series"&&it.seasons.length){
    const cs=it.seasons.find(s=>s.season===S.curSeason)||it.seasons[0];
    list=`<div class="sec-t">Сезоны и серии</div><div class="tabs">${it.seasons.map(s=>`<button class="tab ${s===cs?"on":""}" data-act="season" data-s="${s.season}">Сезон ${s.season}<small>${s.episodes.length}</small></button>`).join("")}</div><div class="eps">${cs.episodes.map(epRow).join("")}</div>`;
  } else if(it.files.length>1){
    list=`<div class="sec-t">Файлы</div><div class="eps">${it.files.map(f=>epRow({episode:null,path:f.path,name:f.name,size:f.size,watched:f.watched})).join("")}</div>`;
  }
  $("#modalRoot").innerHTML=`<div class="overlay mv" data-act="overlay"><div class="modal glass">
    <button class="btn icon x" data-act="close" title="Закрыть (Esc)">${svg("close")}</button>
    <div class="m-grid">
      <div class="m-left"><div class="m-wrap" data-purl="${esc((m&&(m.poster||m.posterPreview))||"")}" data-pname="${esc(title+((m&&m.year)||it.year?" ("+((m&&m.year)||it.year)+")":""))}" data-ptype="id" data-pid="${esc(it.id)}" data-pkey="${esc(posterOf(it,true))}" style="${palStyle(posterOf(it,true))}"><div class="halo"></div><div class="m-poster"><div class="stub" style="--g:${hue%8}"><div class="stub-l">${esc(initial)}</div><div class="stub-n">${m?"":"Нет метаданных"}</div></div>${poster?`<img data-mposter="1" src="${esc(shown(poster))}" referrerpolicy="no-referrer" alt="">`:""}</div></div></div>
      <div class="m-right">
        <h2>${esc(title)}</h2>${orig?`<div class="orig">${esc(orig)}</div>`:`<div style="height:10px"></div>`}
        <div class="chips mm">${chips.join("")}</div>
        ${(rb.length||(m&&(m.ratingLb!=null||m.urlLb)))?`<div class="ratings">${rb.map(r=>ratingBadge(r[0],r[1],srcLinks(m)[r[0]])).join("")}${lbBadge(m)}</div>`:""}
        ${genres.length?`<div class="chips gn">${genres.map(g=>`<span class="chip">${esc(cap1(g))}</span>`).join("")}</div>`:""}
        ${countries.length?`<div class="meta-l"><b>Страны:</b> ${esc(countries.join(", "))}</div>`:""}
        ${m&&m.description?`<div class="desc">${esc(m.description)}</div>`:""}
        ${noMeta}
        ${it.ghost?`<div class="note">Файлов на диске нет — осталась только запись в Watched.</div>`:""}
        <div class="actions act-grid">
          ${ne?`<button class="btn primary lg" data-act="play" data-path="${esc(ne.path)}">${svg("play",16)} ${esc(ne.label)}</button>`:""}
          <button class="btn md${(it.ghost||it.inWatched)?" on":""}" data-act="toggle-watched" data-id="${it.id}" title="${it.ghost?"Убрать из Watched":(it.inWatched?"Вернуть в Not watched":"Перенести в Watched")}">${svg("check",16)} ${S.lang==="en"?"Watched":"Просмотрено"}</button>
          ${it.ghost?"":`<button class="btn md" data-act="fix-toggle">${svg("fix",16)} Исправить совпадение</button>`}
          ${(it.ghost||!ne)?"":`<button class="btn md" data-act="reveal" data-path="${esc(ne.path)}">${svg("folder",16)} Показать в папке</button>`}
        </div>
        ${srcLine(m)}
        ${fixPanel(it)}
        ${list}
      </div></div></div></div>`;
  const im=$("[data-mposter]"); if(im)im.addEventListener("error",()=>{const pv=m&&m.posterPreview; if(pv&&im.src!==pv&&!im.dataset.t){im.dataset.t="1";im.src=pv;return;} S.failed.add(it.id); im.remove(); if(it.hasLocalPoster&&!S.local[it.id])loadLocal(it.id); else if(S.local[it.id])renderModal();});
  if(S.fix.open){const q=$("#fixQ"); if(q&&document.activeElement!==q&&!S.fix.results.length&&!S.fix.busy){q.focus();q.select();}}
}

async function fixSearch(){
  const q=($("#fixQ")||{}).value||S.fix.q; S.fix.q=q; const sel=$("#fixSrc"); if(sel)S.fix.src=sel.value;
  S.fix.busy=true; S.fix.msg=""; S.fix.results=[]; $("#fixRes").innerHTML=fixResults();
  let r; try{ r=await api("search_candidates",q,S.fix.src); }catch(e){ r={ok:false,error:"Ошибка связи с приложением"}; }
  S.fix.busy=false;
  if(!r||!r.ok){ S.fix.msg=(r&&r.error)||"Ошибка поиска"; }
  else if(!r.results.length){ S.fix.msg="Ничего не найдено. Попробуйте другое название или ID."; }
  else S.fix.results=r.results;
  const box=$("#fixRes"); if(box)box.innerHTML=fixResults();
}
async function fixPick(i){
  const c=S.fix.results[i]; if(!c)return; const id=S.current;
  S.fix.busy=true; $("#fixRes").innerHTML=fixResults();
  let r; try{ r=await api("apply_match",id,c); }catch(e){ r={ok:false,error:"Ошибка связи"}; }
  S.fix.busy=false;
  if(!r||!r.ok){ toast((r&&r.error)||"Не удалось применить","err"); const box=$("#fixRes"); if(box)box.innerHTML=fixResults(); return; }
  S.failed.delete(id); S.fix.open=false; S.fix.results=[]; S.fix.msg="";
  const old=S.byId.get(id); Object.assign(old,r.item); updateCard(id); refreshGenres(); renderModal(); setBg(itemBg(old)); toast("Совпадение исправлено");
}
async function fixAuto(){
  const id=S.current; S.fix.busy=true; $("#fixRes").innerHTML=fixResults();
  let r; try{ r=await api("fetch_meta",id,true); }catch(e){ r={ok:false,status:"error"}; }
  S.fix.busy=false; if(r&&r.item){ const old=S.byId.get(id); Object.assign(old,r.item); S.failed.delete(id); updateCard(id); refreshGenres(); }
  const st=r&&r.status;
  if(st==="ok"){ S.fix.open=false; renderModal(); toast("Метаданные обновлены"); }
  else { S.fix.msg=({notfound:"Автопоиск ничего не нашёл — введите название вручную.",nokey:"Нет API-ключа (Настройки).",neterr:"Нет подключения к интернету.",auth:"API-ключ отклонён.",limit:"Лимит запросов исчерпан."})[st]||"Не удалось выполнить автопоиск."; const box=$("#fixRes"); if(box)box.innerHTML=fixResults(); }
}

const RM={servers:[],busy:false,msg:"",st:null,host:"",pin:""};
async function openRemote(){
  let st=null; try{ st=await api("remote_state"); }catch(e){}
  RM.st=st&&st.ok?st:{connected:false}; RM.msg=""; RM.servers=[]; renderRemote();
  if(!RM.st.connected)remoteScan();
}
async function remoteScan(){
  RM.busy=true; renderRemoteNet();
  let r=null; try{ r=await api("remote_discover"); }catch(e){}
  RM.busy=false; RM.servers=(r&&r.ok?r.servers:[]).filter(x=>!x.self); renderRemoteNet();
}
function remoteNetHTML(){
  const list=RM.servers.length
    ?`<div class="rm-list">${RM.servers.map((x,i)=>`<button class="btn rm-srv" data-act="remote-pick" data-i="${i}">${svg("film",16)}<b>${esc(x.name)}</b><span class="hint">${esc(x.host)}</span></button>`).join("")}</div>`
    :`<div class="rm-stat">${RM.busy?`<span class="spinner"></span>Ищу компьютеры с Kino в сети…`:"Компьютеры в сети не найдены. Введите адрес вручную."}</div>`;
  return `<div class="rm-h"><div class="sec-t">В вашей сети</div><button class="btn icon rm-re${RM.busy?" spin":""}" data-act="remote-scan" title="Искать снова">${svg("refresh",16)}</button></div>${list}`;
}
function renderRemoteNet(){ const n=document.getElementById("rmNet"); if(n)n.innerHTML=remoteNetHTML(); }
function remoteBodyHTML(){
  const st=RM.st||{};
  if(st.connected){
    return `<div class="row"><span class="hint">Подключено</span><b>${esc(st.name)}</b><span class="hint">${esc(st.addr||"")}</span></div>
      <div class="row"><span class="hint">Плеер для сети:</span><b>${st.custom?"из настроек":st.player==="browser"?"браузер":st.player?esc(st.player.split(/[\\/]/).pop()):"спросить при запуске"}</b>${!st.custom&&st.player?`<button class="btn sm" data-act="rp-reset">Сменить</button>`:""}</div>
      <div class="row"><button class="btn primary" data-act="remote-off">Вернуться к моей медиатеке</button></div>`;
  }
  return `<div id="rmNet">${remoteNetHTML()}</div>
    <div class="rm-sec"><div class="sec-t">Адрес вручную</div>
      <div class="rm-form"><input id="r-host" class="inp" placeholder="192.168.1.10" value="${esc(RM.host)}" autocomplete="off" spellcheck="false"><input id="r-pin" class="inp" placeholder="PIN" value="${esc(RM.pin)}" autocomplete="off" inputmode="numeric" maxlength="6"><button class="btn primary" data-act="remote-go">Подключиться</button></div>
      ${st.last?`<button class="btn rm-last" data-act="remote-last">Продолжить: ${esc(st.last.name||st.last.host)}</button>`:""}
      ${RM.msg?`<div class="rm-msg">${esc(RM.msg)}</div>`:""}</div>
    <div class="rm-help">На другом компьютере в Kino включите «Доступ с телевизора». PIN показан там же. Через VPN введите IP того компьютера в сети VPN: подключение работает так же, если порт 8765 доступен.</div>`;
}
function renderRemote(){
  const h=document.getElementById("r-host"), p=document.getElementById("r-pin");
  if(h)RM.host=h.value; if(p)RM.pin=p.value;
  const ae=document.activeElement, af=ae&&ae.id, ss=ae&&ae.selectionStart;
  const body=document.getElementById("rmBody");
  if(body&&document.querySelector("#dlgRoot .modal[data-rm]")){
    body.innerHTML=remoteBodyHTML();
    if(af==="r-host"||af==="r-pin"){ const el=document.getElementById(af); if(el){ el.focus(); try{ el.setSelectionRange(ss,ss); }catch(e){} } }
    return;
  }
  $("#dlgRoot").innerHTML=`<div class="overlay dlg" data-act="dlg-overlay"><div class="modal sm rm-dlg glass" data-rm="1">
    <button class="btn icon x" data-act="dlg-close">${svg("close")}</button>
    <h2 class="t">Медиатека на другом компьютере</h2><div id="rmBody">${remoteBodyHTML()}</div></div></div>`;
}
async function remoteFinish(r){
  if(!r||!r.ok){ RM.msg=(r&&r.error)||"Не удалось подключиться"; renderRemote(); return; }
  closeDlg(); S.remote=r.name||true; S.welcome=false; updRemoteBtn(); toast("Подключено: "+(r.name||"")); await loadLibrary(false);
}
async function remoteGo(host){
  const h=document.getElementById("r-host"), p=document.getElementById("r-pin");
  const addr=host||(h?h.value:""), pin=p?p.value:RM.pin;
  RM.msg="Подключаюсь…"; renderRemote();
  let r=null; try{ r=await api("remote_connect",addr,8765,pin); }catch(e){}
  await remoteFinish(r);
}
async function remoteLast(){
  RM.msg="Подключаюсь…"; renderRemote();
  let r=null; try{ r=await api("remote_reconnect"); }catch(e){}
  await remoteFinish(r);
}
async function remoteOff(){
  try{ await api("remote_disconnect"); }catch(e){}
  S.remote=null; updRemoteBtn(); closeDlg(); await loadLibrary(false);
}
function updRemoteBtn(){ const b=$("#btnRemote"); if(b){ b.classList.toggle("primary",!!S.remote); b.title=S.remote?("Удалённая медиатека: "+(S.remote===true?"":S.remote)):"Медиатека на другом компьютере"; } }

function playerAsk(path,players){
  const pl=players||[]; RM.askPath=path; RM.askPl=pl;
  $("#dlgRoot").innerHTML=`<div class="overlay dlg" data-act="dlg-overlay"><div class="modal sm glass">
    <button class="btn icon x" data-act="dlg-close">${svg("close")}</button>
    <h2 class="t">Чем открывать фильмы по сети?</h2>
    <div class="rp-list">
      ${pl.map((x,i)=>`<button class="rp-i${i?"":" pri"}" data-act="rp-use" data-i="${i}"><b>${esc(x.name)}</b><span>${esc(x.path)}</span></button>`).join("")}
      <button class="rp-i${pl.length?"":" pri"}" data-act="rp-exe"><b>Выбрать .exe плеера…</b></button>
      <button class="rp-i" data-act="rp-browser"><b>Открывать в браузере</b></button>
    </div>
    <label class="radio sw"><input type="checkbox" id="rp-mem" checked> Запомнить выбор</label>
  </div></div>`;
}
async function rpChoose(kind,p){
  const mem=$("#rp-mem"), keep=!mem||mem.checked;
  if(keep&&!await playerSet(kind,p))return;
  closeDlg();
  if(RM.askPath)play(RM.askPath,keep?"":(kind==="browser"?"browser":p)); else openRemote();
}
async function playerSet(kind,p){
  let r=null; try{ r=await api("remote_set_player",kind,p||""); }catch(e){}
  if(!r||!r.ok){ toast((r&&r.error)||"Не удалось сохранить","err"); return false; }
  if(RM.st)RM.st.player=r.player; return true;
}
async function play(path,override){
  let r; try{ r=await api("play",path,override||""); }catch(e){ r={ok:false,error:"Нет связи с приложением"}; }
  if(r&&r.needPlayer){ playerAsk(path,r.players); return; }
  if(!r||!r.ok){ toast((r&&r.error)||"Не удалось запустить","err"); return; }
  S.items.forEach(it=>{ it.files.forEach(f=>{if(f.path===path)f.watched=true;}); it.seasons.forEach(s=>s.episodes.forEach(e=>{if(e.path===path)e.watched=true;})); });
  toast("Запускаю плеер…"); if(S.current&&!S.fix.open)renderModal();
}

const BG_SW=["#0a0a0a","#141414","#1c1c1f","#0e1620","#13200f","#241216","#1d1530","#2b2418"];
function bgCfg(){ const c=S.settings||{}; return {mode:c.bg_mode||"default",color:c.bg_color||"#0a0a0a",dim:Number(c.bg_dim==null?55:c.bg_dim),blur:Number(c.bg_blur||0),ver:Number(c.bg_ver||0)}; }
function applyBg(){
  const c=bgCfg(), u=$("#userbg"), sh=$("#shade"), b=document.body;
  const img=c.mode==="image"&&S.settings.bg_base&&c.ver;
  if(c.mode==="default"||(c.mode==="image"&&!img)){ b.classList.remove("bg-custom"); sh.style.background=""; u.style.cssText=""; return; }
  b.classList.add("bg-custom");
  if(c.mode==="color"){
    u.style.cssText=`background:radial-gradient(1100px 760px at 10% 0%,rgba(255,255,255,.06),transparent 60%),${c.color}`; sh.style.background="transparent";
  } else {
    u.style.cssText=`background-image:url("${S.settings.bg_base}?v=${c.ver}");`+(c.blur?`filter:blur(${c.blur}px);transform:scale(1.08);`:"");
    sh.style.background=`rgba(0,0,0,${(c.dim/100).toFixed(2)})`;
  }
  clearBg();
}
let bgSaveT=null;
function saveBg(patch){ Object.assign(S.settings,patch); applyBg(); clearTimeout(bgSaveT); bgSaveT=setTimeout(()=>{ api("save_settings",patch).catch(()=>{}); },350); }
function bgHTML(){
  const c=bgCfg();
  return `<div class="st-r"><div class="sec-t">Фон</div>
    <select id="bg-mode" class="inp"><option value="default" ${c.mode==="default"?"selected":""}>Стандартный (тёмный)</option><option value="color" ${c.mode==="color"?"selected":""}>Свой цвет</option><option value="image" ${c.mode==="image"?"selected":""}>Своё фото</option></select></div>
    <div id="bg-color-box" style="margin-top:12px;${c.mode==="color"?"":"display:none"}"><div class="bgsw"><input type="color" id="bg-color" class="inp" value="${esc(c.color)}">${BG_SW.map(x=>`<i data-act="bg-swatch" data-c="${x}" style="background:${x}" title="${x}"></i>`).join("")}</div></div>
    <div id="bg-img-box" style="margin-top:12px;${c.mode==="image"?"":"display:none"}">
      <div class="row"><button class="btn" data-act="bg-pick">${svg("folder",16)} Выбрать фото…</button><button class="btn" data-act="bg-clear">Убрать фото</button><span class="hint" id="bg-hint">${c.ver?"Фото выбрано":"Фото не выбрано"}</span></div>
      <input type="file" id="bg-file" accept="image/*" hidden>
      <div class="rng"><span>Затемнение</span><input type="range" id="bg-dim" min="0" max="90" value="${c.dim}"><b id="bg-dim-v">${c.dim}%</b></div>
      <div class="rng"><span>Размытие</span><input type="range" id="bg-blur" min="0" max="30" value="${c.blur}"><b id="bg-blur-v">${c.blur}px</b></div>
    </div>`;
}
function loadImageFile(file){
  return new Promise((ok,no)=>{ const url=URL.createObjectURL(file); const im=new Image(); im.onload=()=>{ URL.revokeObjectURL(url); ok(im); }; im.onerror=()=>{ URL.revokeObjectURL(url); no(new Error("img")); }; im.src=url; });
}
async function setBgFile(file){
  if(!file)return; const hint=$("#bg-hint"); if(hint)hint.textContent="Обработка…";
  try{
    const im=await loadImageFile(file); const k=Math.min(1,2200/Math.max(im.naturalWidth,im.naturalHeight));
    const cv=document.createElement("canvas"); cv.width=Math.max(1,Math.round(im.naturalWidth*k)); cv.height=Math.max(1,Math.round(im.naturalHeight*k));
    cv.getContext("2d").drawImage(im,0,0,cv.width,cv.height);
    const r=await api("save_background",cv.toDataURL("image/jpeg",.86));
    if(!r||!r.ok)throw new Error((r&&r.error)||"save");
    S.settings=r.settings; if(S.settings.bg_mode!=="image"){ S.settings.bg_mode="image"; api("save_settings",{bg_mode:"image"}).catch(()=>{}); const m=$("#bg-mode"); if(m)m.value="image"; }
    applyBg(); if(hint)hint.textContent="Фото выбрано";
  }catch(e){ if(hint)hint.textContent="Не удалось открыть изображение"; toast("Не удалось загрузить фото","err"); }
}
document.addEventListener("input",e=>{
  const t=e.target; if(!t||!t.id)return;
  if(t.id==="bg-color")saveBg({bg_color:t.value});
  else if(t.id==="bg-dim"){ $("#bg-dim-v").textContent=t.value+"%"; saveBg({bg_dim:t.value}); }
  else if(t.id==="bg-blur"){ $("#bg-blur-v").textContent=t.value+"px"; saveBg({bg_blur:t.value}); }
});
document.addEventListener("change",e=>{
  const t=e.target; if(!t||!t.id)return;
  if(t.id==="bg-mode"){ $("#bg-color-box").style.display=t.value==="color"?"":"none"; $("#bg-img-box").style.display=t.value==="image"?"":"none"; saveBg({bg_mode:t.value}); }
  else if(t.id==="bg-file"){ setBgFile(t.files&&t.files[0]); t.value=""; }
});

let updInfo=null, updHide=false;
function renderUpdBar(){
  const el=$("#updBar"); if(!el)return;
  if(!updInfo||!updInfo.available||updHide){ el.classList.remove("on"); return; }
  el.innerHTML=`<span>Доступна версия <b>${esc(updInfo.latest)}</b> <small>(у вас ${esc(updInfo.current)})</small></span>`+
    (updInfo.canInstall?`<button class="btn sm primary" data-act="upd-install">Обновить</button>`:`<button class="btn sm primary" data-act="open-url" data-url="${esc(updInfo.page)}">Скачать</button>`)+
    `<button class="btn sm" data-act="upd-later">Позже</button>`;
  el.classList.add("on");
}
async function checkUpdate(manual){
  const hint=$("#upd-hint"); if(manual&&hint)hint.textContent="Проверка…";
  let r=null; try{ r=await api("check_update"); }catch(e){}
  if(!r||!r.ok){ if(manual&&hint)hint.textContent="Не удалось проверить: "+((r&&r.error)||"нет связи с GitHub"); return; }
  updInfo=r; updHide=false; renderUpdBar();
  if(manual&&hint)hint.textContent=r.available?`Доступна версия ${r.latest}`:`У вас последняя версия (${r.current})`;
}
async function installUpdate(){
  const el=$("#updBar"); el.innerHTML=`<span>Загрузка обновления…</span>`;
  let r=null; try{ r=await api("install_update"); }catch(e){}
  if(r&&r.ok){ el.innerHTML=`<span>Перезапуск…</span>`; return; }
  toast((r&&r.error)||"Не удалось обновить","err"); renderUpdBar();
}
function tvHTML(){
  return `<div class="sec-t">Доступ с телевизора</div>
    <label class="radio sw"><input type="checkbox" id="tv-on"> Включить сервер для Android TV</label>
    <div id="tvBox"></div>`;
}
async function tvLoad(){ let r=null; try{ r=await api("srv_info"); }catch(e){} if(r&&r.ok)renderTv(r); }
function devWhen(d){
  const en=S.lang==="en", loc=en?"en-GB":"ru-RU", fmt=s=>new Date(s*1000).toLocaleString(loc,{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"});
  if(!d.last)return (en?"Paired ":"Подключено ")+fmt(d.ts||0);
  if(Date.now()/1000-d.last<120)return en?"Online":"В сети";
  return (en?"Last seen ":"Был в сети ")+fmt(d.last);
}
function renderTv(r){
  const box=$("#tvBox"); if(!box)return; const c=$("#tv-on"); if(c)c.checked=!!r.on;
  if(!r.on){ box.innerHTML=`<div class="hint">Телевизор и компьютер должны быть в одной сети. Приложение Kino для ТВ найдёт компьютер само.</div>`; return; }
  box.innerHTML=(r.error?`<div class="hint" style="color:#f2a2a2">${esc(r.error)}</div>`:"")+
    `<div class="row"><span class="hint">Адрес</span><b style="user-select:text">${esc(r.addr)}</b><button class="btn icon" style="width:28px;height:28px;border-radius:8px" data-act="copy-text" data-v="${esc(r.addr)}" title="Копировать">${svg("copy",14)}</button></div>
    <label class="radio sw"><input type="checkbox" id="tv-pinreq" ${r.pinRequired?"checked":""}> Запрашивать PIN при подключении</label>
    ${r.pinRequired?`<div class="row"><span class="hint">PIN</span><b style="font-size:22px;letter-spacing:.2em;user-select:text">${esc(r.pin)}</b><button class="btn icon" style="width:28px;height:28px;border-radius:8px" data-act="copy-text" data-v="${esc(r.pin)}" title="Копировать">${svg("copy",14)}</button><button class="btn sm" data-act="tv-pin">Новый PIN</button></div>`:`<div class="hint">Любое устройство в вашей сети сможет подключиться без PIN.</div>`}
    <div class="row"><span class="hint">Подключено устройств: ${r.devices.length}</span><button class="btn sm" data-act="tv-forget" ${r.devices.length?"":"disabled"}>Отключить все</button></div>
    ${r.devices.length?`<div style="display:grid;gap:8px;margin:6px 0 12px">${r.devices.map(d=>`<div class="row" style="justify-content:space-between"><b>${esc(d.name)}</b><span class="hint">${esc(devWhen(d))}</span></div>`).join("")}</div>`:""}
    <div class="hint">Если ТВ не подключается, разрешите Kino в брандмауэре Windows для частной сети.</div>`;
}
document.addEventListener("change",async e=>{
  const t=e.target; if(t&&t.id==="tv-pinreq"){ let r=null; try{ r=await api("srv_pin_required",t.checked); }catch(x){} if(r&&r.ok)renderTv(r); else tvLoad(); return; }
  if(!t||t.id!=="tv-on")return;
  let r=null; try{ r=await api("srv_set",t.checked); }catch(x){}
  if(r&&r.ok)renderTv(r); else { toast((r&&r.error)||"Не удалось изменить","err"); tvLoad(); }
});
async function tvAct(name){ let r=null; try{ r=await api(name); }catch(e){} if(r&&r.ok)renderTv(r); }
function startHTML(){
  const m=S.settings.autostart||"0";
  return `<div class="st-r"><div class="sec-t">Запуск с системой</div><select id="s-auto" class="inp">${[["0","Выключено"],["min","Свернуто в трей"],["normal","Развернуто"]].map(o=>`<option value="${o[0]}" ${m===o[0]?"selected":""}>${o[1]}</option>`).join("")}</select></div>
    <label class="radio sw"><input type="checkbox" id="tray-close" ${S.settings.tray_close==="1"?"checked":""}> При закрытии сворачивать в трей</label>`;
}
function updHTML(){
  const on=(S.settings.auto_update||"1")!=="0";
  return `<div class="sec-t">Обновления</div>
    <label class="radio sw"><input type="checkbox" id="upd-auto" ${on?"checked":""}> Проверять обновления при запуске</label>
    <div class="row"><button class="btn" data-act="upd-check">Проверить сейчас</button><span class="hint" id="upd-hint">Версия ${esc(S.settings.app_version||"")}</span></div>`;
}
document.addEventListener("change",e=>{ const t=e.target; if(t&&t.id==="upd-auto")saveBg({auto_update:t.checked?"1":"0"}); if(t&&t.id==="tray-close")saveBg({tray_close:t.checked?"1":"0"}); });

const EN_DICT={"Бесплатный план: до 1000 запросов в сутки.":"Free plan: up to 1000 requests per day.","Запомнить выбор":"Remember my choice","Запуск с системой":"Start with Windows","Выключено":"Off","Свернуто в трей":"Minimized to tray","Развернуто":"Normal window","Чем открывать фильмы по сети?":"How to open movies over the network?","Выбрать .exe плеера…":"Choose player .exe…","Открывать в браузере":"Open in the browser","Не удалось сохранить":"Could not save","Плеер для сети:":"Network player:","из настроек":"from settings","браузер":"browser","спросить при запуске":"ask on play","Сменить":"Change","Укажите .exe файл плеера":"Choose the player .exe file","При закрытии сворачивать в трей":"Minimize to tray on close","Открыть Kino":"Open Kino","через поиск по Кинопоиску":"via Kinopoisk search","Источник данных:":"Data source:","вручную":"manual","через OMDb":"via OMDb","по IMDb ID":"by IMDb ID","поиск на IMDb":"IMDb search","по транслиту":"by transliteration","Добавить фильм":"Add movie","Другой ПК":"Other PC","Удалить постер":"Remove poster","Удаляю постер…":"Removing poster…","Постер удалён":"Poster removed","Удалить профиль Letterboxd?":"Remove the Letterboxd profile?","Загрузка вотчлиста с этого профиля остановится. Фильмы, уже добавленные в вотчлист, останутся.":"Watchlist syncing from this profile will stop. Movies already in your watchlist will stay.","Медиатека на другом компьютере":"Library on another computer","Подключено":"Connected","Вернуться к моей медиатеке":"Back to my library","Ищу компьютеры с Kino в сети…":"Looking for computers with Kino on the network…","Компьютеры в сети не найдены. Введите адрес вручную.":"No computers found on the network. Enter the address manually.","В вашей сети":"On your network","Искать снова":"Search again","Адрес вручную":"Address manually","Подключиться":"Connect","Подключаюсь…":"Connecting…","Продолжить:":"Continue:","На другом компьютере в Kino включите «Доступ с телевизора». PIN показан там же. Через VPN введите IP того компьютера в сети VPN: подключение работает так же, если порт 8765 доступен.":"On the other computer, turn on “TV access” in Kino. The PIN is shown there. Over a VPN, enter that computer's IP on the VPN network: it works the same if port 8765 is reachable.","Удалённая медиатека: ":"Remote library: ","Подключено: ":"Connected: ","Не удалось подключиться":"Could not connect","Укажите адрес":"Enter an address","Неверный PIN":"Wrong PIN","Слишком много попыток, подождите несколько минут":"Too many attempts, wait a few minutes","Нет ответа. Проверьте адрес, порт и что сервер включён на том компьютере.":"No response. Check the address, the port and that the server is on at the other computer.","По этому адресу не Kino":"Not a Kino server at this address","Нет сохранённого подключения":"No saved connection","Не удаётся связаться с удалённым компьютером":"Cannot reach the remote computer","Доступ отклонён, подключитесь заново":"Access denied, connect again","Ошибка удалённой медиатеки":"Remote library error","Недоступно в режиме удалённой медиатеки":"Not available for a remote library","Нет подключения к удалённой медиатеке":"Not connected to a remote library","Сервис временно недоступен, попробуйте позже":"Service is temporarily unavailable, try again later","Запрашивать PIN при подключении":"Require PIN to connect","Любое устройство в вашей сети сможет подключиться без PIN.":"Any device on your network will be able to connect without a PIN.","Доступ с телевизора":"TV access","Включить сервер для Android TV":"Enable server for Android TV","Телевизор и компьютер должны быть в одной сети. Приложение Kino для ТВ найдёт компьютер само.":"The TV and this computer must be on the same network. The Kino TV app will find the computer by itself.","Адрес":"Address","Новый PIN":"New PIN","Подключено устройств:":"Connected devices:","Отключить все":"Disconnect all","Если ТВ не подключается, разрешите Kino в брандмауэре Windows для частной сети.":"If the TV cannot connect, allow Kino in Windows Firewall for private networks.","Закрепить":"Pin","Открепить":"Unpin","Закреплено":"Pinned","Откреплено":"Unpinned","Изменить совпадение":"Change match","Если фильмов с одинаковым названием несколько, найдите нужный и выберите его. Можно писать название и год, например: Spring 2014.":"If several movies share a title, find the right one and pick it. You can type the title and year, for example: Spring 2014.","Выбрать":"Select","Совпадение изменено":"Match changed","Не удалось изменить":"Could not change","По умолчанию":"Default","Добро пожаловать в Kino":"Welcome to Kino","Каталог рекурсивно просканирует все подпапки и найдёт только видеофайлы. Можно добавить несколько папок.":"The catalog scans all subfolders recursively and picks up video files only. You can add several folders.","Папка с фильмами и сериалами":"Folder with movies and series","Добавить ещё папку":"Add another folder","Ключ OMDb":"OMDb key","Откройте сайт omdbapi.com/apikey.aspx, выберите бесплатный тариф (FREE) и укажите почту.":"Open omdbapi.com/apikey.aspx, choose the free plan (FREE) and enter your email.","Подтвердите ключ в письме и вставьте его ниже.":"Confirm the key from the email and paste it below.","Получить ключ OMDb":"Get an OMDb key","Откройте сайт kinopoiskapiunofficial.tech и войдите через почту или GitHub.":"Open kinopoiskapiunofficial.tech and sign in with email or GitHub.","Скопируйте API-ключ из личного кабинета и вставьте его ниже.":"Copy the API key from your account and paste it below.","Получить ключ Кинопоиска":"Get a Kinopoisk key","Без ключа названия, постеры и описания будут находиться неточно и очень медленно. Ключ можно добавить позже в настройках.":"Without a key, titles, posters and descriptions will be matched inaccurately and very slowly. You can add the key later in settings.","Названия, описания и постеры берутся из OMDb. Постер конкретного фильма можно сменить правой кнопкой мыши по постеру.":"Titles, descriptions and posters come from OMDb. You can change the poster of a specific movie with a right click on the poster.","Названия, описания и постеры берутся из Кинопоиска. Постер конкретного фильма можно сменить правой кнопкой мыши по постеру.":"Titles, descriptions and posters come from Kinopoisk. You can change the poster of a specific movie with a right click on the poster.","Начать":"Get started","Сначала выберите папку":"Choose a folder first","Нет доступных источников метаданных. Вставьте API-ключ в настройках или включите поиск через IMDb.":"No metadata sources available. Paste an API key in settings or enable IMDb search.","Ключ Кинопоиска не указан: данные ищутся через IMDb, примерно один фильм за несколько секунд, описания на английском. Вставьте ключ в настройках — будет быстрее и по-русски.":"No Kinopoisk key: data is searched via IMDb, roughly one movie per few seconds, with English descriptions. Paste the key in settings for faster results in Russian.","Ключ OMDb не указан: данные ищутся через сайт IMDb, это медленнее и менее надёжно. Вставьте ключ OMDb в настройках.":"No OMDb key: data is searched via the IMDb website, which is slower and less reliable. Paste an OMDb key in settings.","IMDb временно ограничил запросы. Всё найденное сохранено, повторите чуть позже. С API-ключом такого не бывает.":"IMDb has temporarily limited requests. Everything found is saved, try again a bit later. This does not happen with an API key.","Скрыть":"Hide","Вернуть из скрытых":"Unhide","Скрытое":"Hidden","Скрытых фильмов нет":"No hidden movies","Нажмите правой кнопкой мыши по постеру и выберите «Скрыть».":"Right-click a poster and choose “Hide”.","Фильм скрыт":"Movie hidden","Фильм снова виден":"Movie is visible again","Русский":"Russian","Очистить":"Clear","Загрузить постер из источника":"Load poster from source","Как в настройках":"As in settings","В вотчлисте:":"In watchlist:","Просмотрено:":"Watched:","Открыть профиль на Letterboxd":"Open Letterboxd profile","Язык данных о фильмах":"Movie data language","На каком языке загружать названия и описания для вотчлиста?":"Which language should be used for watchlist titles and descriptions?","OMDb, затем Letterboxd":"OMDb, then Letterboxd","Затемнение":"Dimming","Размытие":"Blur","Данные вотчлиста: спросить при загрузке":"Watchlist data: ask on load","Данные вотчлиста: русский (Кинопоиск)":"Watchlist data: Russian (Kinopoisk)","Данные вотчлиста: English (OMDb, затем Letterboxd)":"Watchlist data: English (OMDb, then Letterboxd)","Letterboxd: в списке":"Letterboxd: in list",", добавлено новых:":", new added:","Ищу постер…":"Looking for the poster…","Возвращаю постер по умолчанию…":"Restoring the default poster…","Постер обновлён":"Poster updated","В этом источнике постер не найден":"No poster found in this source","Для Кинопоиска нужен API-ключ в настройках":"Kinopoisk needs an API key in settings","Неизвестный источник":"Unknown source","Нет данных о фильме":"No data about this movie","Источник временно недоступен":"Source temporarily unavailable","Не удалось сменить постер":"Could not change the poster","Укажите ник Letterboxd (например: idlorem)":"Enter your Letterboxd username (e.g. idlorem)","Укажите ник Letterboxd":"Enter your Letterboxd username","Загружаю вотчлист с Letterboxd…":"Loading your watchlist from Letterboxd…","Профиль или вотчлист не найден. Проверьте ник и что вотчлист открыт для всех.":"Profile or watchlist not found. Check the username and that the watchlist is public.","Letterboxd временно ограничил запросы.":"Letterboxd has temporarily limited requests.","Повторите через":"Try again in","мин.":"min.","Попробуйте чуть позже.":"Try again a bit later.","Вотчлист пуст или закрыт в настройках приватности Letterboxd.":"The watchlist is empty or private in Letterboxd privacy settings.","Не удалось загрузить вотчлист":"Could not load the watchlist","Не удалось перенести":"Could not move","Скопировано:":"Copied:","Загрузка…":"Loading…","Просмотрено":"Move to Watched","Удалить профиль":"Remove profile","Обновить вотчлист":"Refresh watchlist","Загрузить вотчлист":"Load watchlist","Копировать название и год":"Copy title and year","Перенести в Watched":"Move to Watched","Ваш ник на Letterboxd, например: idlorem":"Your Letterboxd username, e.g. idlorem","Ник на Letterboxd, например: idlorem":"Letterboxd username, e.g. idlorem","Letterboxd — ваш вотчлист":"Letterboxd — your watchlist","Перенесено в Watched":"Moved to Watched","(у вас":"(you have",", не удалось:":", failed:","/ серия":"/ episode","API-ключ (X-API-KEY)":"API key (X-API-KEY)","API-ключ отклонён сервисом. Проверьте ключ в настройках.":"The API key was rejected by the service. Check the key in settings.","API-ключ отклонён.":"API key rejected.","TMDB API-ключ или Read Access Token":"TMDB API key or Read Access Token","· из 5":"· out of 5","· метаданные":"· metadata","» · файлов:":"» · files:","Автопоиск заново":"Search again","Автопоиск ничего не нашёл — введите название вручную.":"Auto-search found nothing — enter the title manually.","Без названия":"Untitled","Бесплатный план: до 500 запросов в сутки. Каждый новый фильм — 2 запроса.":"Free plan: up to 500 requests per day. Each new movie takes 2 requests.","Библиотека":"Library","В Watched пока пусто":"Watched is empty for now","В Watchlist:":"In Watchlist:","В библиотеке":"In library","В списке":"In the list","Введите название выше и нажмите «Добавить» у нужного варианта.":"Enter a title above and press “Add” on the right match.","Вернуть в Not watched":"Move back to Not watched","Версия":"Version","Видеоплеер":"Video player","Видеофайлов не найдено":"No video files found","Внешний плеер (VLC, PotPlayer, MPC-HC…)":"External player (VLC, PotPlayer, MPC-HC…)","Возвращено в Not watched":"Moved back to Not watched","Все жанры":"All genres","Все типы":"All types","Все фильмы из папки находятся во вкладке Watched.":"All movies from the folder are in the Watched tab.","Всё просмотрено":"All watched","Выберите папку с фильмами и сериалами":"Choose a folder with movies and series","Выбрать .exe…":"Choose .exe…","Выбрать папку":"Choose folder","Выбрать фото…":"Choose photo…","ГБ":"GB","Год: новые":"Year: newest","Год: старые":"Year: oldest","Готово":"Done","Добавить":"Add","Добавить папку":"Add folder","Добавить папку…":"Add folder…","Добавлено в вотчлист":"Added to watchlist","Доступна версия":"Version available:","Есть в библиотеке":"In your library","Загрузка обновления…":"Downloading update…","Закрыть (Esc)":"Close (Esc)","Запускаю плеер…":"Starting player…","Запустите программу через main.py или kino.exe — страница работает только внутри окна приложения.":"Run the program via main.py or kino.exe — the page only works inside the app window.","Измените запрос или фильтры.":"Change the query or filters.","Исправить совпадение":"Fix match","Ищу…":"Searching…","Кинопоиск":"Kinopoisk","Кинопоиск Unofficial — основной источник":"Kinopoisk Unofficial — main source","Ключ Кинопоиска не указан: данные ищутся через IMDb и Letterboxd, примерно один фильм за несколько секунд, описания на английском. Вставьте ключ в настройках — будет быстрее и по-русски.":"No Kinopoisk key: data is searched via IMDb and Letterboxd, roughly one movie every few seconds, descriptions in English. Paste a key in settings — it will be faster and in Russian.","Кэш":"Cache","Кэш сброшен, загружаю заново…":"Cache cleared, reloading…","Лимит запросов исчерпан.":"Request limit reached.","МБ":"MB","Метаданные ещё не загружены. Вставьте API-ключ Кинопоиска в настройках или дождитесь загрузки.":"Metadata is not loaded yet. Paste a Kinopoisk API key in settings or wait for loading.","Метаданные обновлены":"Metadata updated","Можно вставить ссылку: kinopoisk.ru/film/…, letterboxd.com/film/… или imdb.com/title/… Транслит (Izgnanie) понимают IMDb и Letterboxd.":"You can paste a link: kinopoisk.ru/film/…, letterboxd.com/film/… or imdb.com/title/… Transliteration (Izgnanie) is understood by IMDb and Letterboxd.","Можно добавить несколько папок. Каталог рекурсивно просканирует все подпапки и найдёт только видеофайлы. Постеры, описания и рейтинги подтянутся из Кинопоиска.":"You can add several folders. The catalog scans all subfolders and picks up video files only. Posters, descriptions and ratings are loaded from Kinopoisk.","Мой вотчлист":"My watchlist","Нажмите ещё раз для подтверждения":"Click again to confirm","Нажмите правой кнопкой мыши по постеру и выберите «Перенести в Watched».":"Right-click a poster and choose “Move to Watched”.","Название на любом языке, без года — например: битва за битвой":"Title in any language, no year — e.g. one battle after another","Название, ID Кинопоиска или ссылка на фильм":"Title, Kinopoisk ID or movie link","Найти":"Search","Настройки":"Settings","Настройки сохранены":"Settings saved","Не использовать":"Don't use","Не удалось выполнить автопоиск.":"Auto-search failed.","Не удалось добавить":"Could not add","Не удалось запустить":"Could not start","Не удалось изменить":"Could not change","Не удалось обновить":"Could not update","Не удалось применить":"Could not apply","Не удалось проверить:":"Could not check:","Не удалось сохранить настройки":"Could not save settings","Не удалось удалить":"Could not delete","Недавние":"Recent","Нет API-ключа (Настройки).":"No API key (Settings).","Нет в базе":"Not in database","Нет доступных источников метаданных. Включите IMDb/Letterboxd или вставьте API-ключ Кинопоиска в настройках.":"No metadata sources available. Enable IMDb/Letterboxd or paste a Kinopoisk API key in settings.","Нет метаданных":"No metadata","Нет на диске":"Not on disk","Нет подключения к интернету или сервис недоступен. Показаны данные из кэша и заглушки.":"No internet connection or the service is unavailable. Showing cached data and placeholders.","Нет подключения к интернету.":"No internet connection.","Нет связи с Python":"No connection to Python","Нет связи с приложением":"No connection to the app","Ничего не найдено":"Nothing found","Ничего не найдено. Попробуйте другое название или ID.":"Nothing found. Try another title or ID.","Ничего не найдено. Попробуйте другое написание или латиницу.":"Nothing found. Try another spelling or Latin letters.","Обновить":"Update","Обновления":"Updates","Общий размер":"Total size","Оставить запись в Watched":"Keep the entry in Watched","Открыть на":"Open on","Открыть на Letterboxd":"Open on Letterboxd","Отмена":"Cancel","Ошибка API.":"API error.","Ошибка поиска":"Search error","Ошибка связи":"Connection error","Ошибка связи с приложением":"App connection error","Ошибка сканирования":"Scan error","Папка не выбрана":"No folder selected","Папка недоступна:":"Folder unavailable:","Папки не выбраны":"No folders selected","Папки пересканированы":"Folders rescanned","Перезапуск…":"Restarting…","Перенесено в Watched":"Moved to Watched","Перенести в Watched":"Move to Watched","Пересканировать":"Rescan","Пересканировать папки":"Rescan folders","По названию":"By title","По рейтингу":"By rating","Повторить":"Retry","Позже":"Later","Поиск по названию…   ( / )":"Search by title…   ( / )","Поиск по названию…":"Search by title…","Поиск…":"Searching…","Показать в папке":"Show in folder","Показать файл в папке":"Show file in folder","Показать/скрыть":"Show/hide","Показывать рейтинг и ссылку Letterboxd":"Show Letterboxd rating and link","Получить бесплатный ключ":"Get a free key","Получить ключ TMDB":"Get a TMDB key","Проверить сейчас":"Check now","Проверка…":"Checking…","Проверять обновления при запуске":"Check for updates on startup","Продолжить":"Continue","Размер":"Size","Размер постеров (двойной клик — сбросить)":"Poster size (double-click to reset)","Распознано из имени файла:":"Parsed from file name:","Резервный источник":"Fallback source","Ручные привязки сохраняются. После сброса данные загрузятся заново (расходуются запросы API).":"Manual matches are kept. After clearing, data is reloaded (uses API requests).","Сбросить кэш метаданных":"Clear metadata cache","Свой цвет":"Custom color","Своё фото":"Custom photo","Сезон":"Season","Сезоны и серии":"Seasons and episodes","Сериал":"Series","Сериалы":"Series","Серия":"Episode","Системный плеер по умолчанию":"System default player","Сканирование папки…":"Scanning folder…","Сканировать":"Scan","Скачать":"Download","Слишком много запросов — сервис просит подождать. Попробуйте чуть позже.":"Too many requests — the service asks to wait. Try again in a moment.","Смотреть":"Watch","Совпадение исправлено":"Match fixed","Сохранить":"Save","Список пока пуст.":"The list is empty for now.","Стандартный (тёмный)":"Default (dark)","Страны:":"Countries:","Суточный лимит запросов API исчерпан. Уже загруженное сохранено в кэш — продолжим позже.":"Daily API request limit reached. What is already loaded is saved in the cache — we will continue later.","У вас последняя версия (":"You have the latest version (","Убрано из Watched":"Removed from Watched","Убрано из вотчлиста":"Removed from watchlist","Убрать из Watched":"Remove from Watched","Убрать из Watchlist":"Remove from Watchlist","Убрать из вотчлиста":"Remove from watchlist","Убрать из каталога (файлы не удаляются)":"Remove from catalog (files are not deleted)","Убрать фото":"Remove photo","Удалено файлов:":"Files deleted:","Удалено:":"Deleted:","Удалить":"Delete","Удалить навсегда, минуя Корзину":"Delete permanently, skip the Recycle Bin","Удалить с компьютера?":"Delete from computer?","Удалить с компьютера…":"Delete from computer…","Удалить файл с компьютера…":"Delete file from computer…","Удаляю…":"Deleting…","Укажите .exe файл плеера или выберите системный":"Choose the player .exe or select the system player","Файл":"File","Файл .exe не выбран":"No .exe file selected","Файлов":"Files","Файлов на диске нет — осталась только запись в Watched.":"No files on disk — only the Watched entry remains.","Файлы":"Files","Файлы будут перемещены в Корзину Windows, их можно восстановить.":"Files will be moved to the Windows Recycle Bin and can be restored.","Файлы будут удалены безвозвратно.":"Files will be deleted permanently.","Файлы:":"Files:","Фильм":"Movie","Фильм не найден в базе по названию файла. Нажмите «Исправить совпадение» и найдите его вручную.":"The movie was not found by file name. Press “Fix match” and find it manually.","Фильмы":"Movies","Фон":"Background","Формат":"Format","Форматы":"Formats","Фото выбрано":"Photo selected","Фото не выбрано":"No photo selected","Что хотите посмотреть?":"What do you want to watch?","из":"of","мин":"min","нет на диске":"not on disk","нет связи с GitHub":"no connection to GitHub","файл(ов) в каталоге":"file(s) in catalog","эп.":"ep.","— в Корзине":"— in Recycle Bin","…и ещё":"…and more","Язык":"Language","Язык интерфейса":"Interface language","Названия на английском подгружаются с IMDb.":"English titles are loaded from IMDb.","Описания фильмов остаются на языке источника.":"Movie descriptions stay in the source language.","Ключ Кинопоиска":"Kinopoisk key","Выбранные папки недоступны":"Selected folders are unavailable","Элемент не найден":"Item not found","Элемент не найден. Обновите каталог.":"Item not found. Refresh the catalog.","Введите название, ID или ссылку":"Enter a title, ID or link","Не указан API-ключ Кинопоиска (Настройки)":"Kinopoisk API key is not set (Settings)","Не указан API-ключ TMDB (Настройки)":"TMDB API key is not set (Settings)","Нет подключения к интернету":"No internet connection","API-ключ отклонён":"API key rejected","Суточный лимит запросов исчерпан":"Daily request limit reached","Слишком много запросов, подождите":"Too many requests, please wait","Сайт временно блокирует запросы, попробуйте позже":"The site is temporarily blocking requests, try later","Ошибка запроса:":"Request error:","Суточный лимит Кинопоиска исчерпан — продолжим завтра, пока работают IMDb и TMDB.":"Kinopoisk daily limit reached — we will continue tomorrow while IMDb and TMDB are used.","API-ключ Кинопоиска отклонён — проверьте его в настройках.":"The Kinopoisk API key was rejected — check it in settings.","Русские названия лучше всего находятся с ключом Кинопоиска (Настройки). Без него попробуйте латиницей.":"Russian titles are found best with a Kinopoisk key (Settings). Without it, try Latin letters.","Некорректный вариант":"Invalid option","Недопустимый адрес обновления":"Invalid update address","Не удалось скачать обновление (HTTP":"Could not download the update (HTTP","Файл обновления слишком большой":"The update file is too large","Скачанный файл повреждён":"The downloaded file is corrupted","Скачанный файл не похож на Kino":"The downloaded file does not look like kino","Скачанный файл не является программой":"The downloaded file is not a program","Нужен JPEG":"A JPEG is required","Файл слишком большой":"The file is too large","Повреждённые данные":"Corrupted data","Не JPEG":"Not a JPEG","Нет файлов для удаления":"No files to delete","файл вне выбранной папки":"file is outside the selected folder","Файл не входит в каталог. Обновите список.":"The file is not in the catalog. Refresh the list.","Файл не найден (возможно, диск отключён).":"File not found (the drive may be disconnected).","Файл плеера не найден. Укажите .exe в настройках.":"Player file not found. Choose an .exe in settings.","Не удалось запустить:":"Could not start:","GitHub вернул HTTP":"GitHub returned HTTP","не удалось переместить в Корзину (код":"could not move to the Recycle Bin (code","Корзина доступна только в Windows":"The Recycle Bin is only available on Windows","аниме":"anime","биография":"biography","боевик":"action","вестерн":"western","военный":"war","детектив":"mystery","детский":"kids","для взрослых":"adult","документальный":"documentary","драма":"drama","игра":"game show","история":"history","комедия":"comedy","концерт":"concert","короткометражка":"short","криминал":"crime","мелодрама":"romance","музыка":"music","мультфильм":"animation","мюзикл":"musical","новости":"news","приключения":"adventure","реальное ТВ":"reality TV","семейный":"family","спорт":"sport","ток-шоу":"talk show","триллер":"thriller","ужасы":"horror","фантастика":"sci-fi","фильм-нуар":"film noir","нуар":"noir","фэнтези":"fantasy","церемония":"ceremony","телефильм":"TV movie","мини-сериал":"miniseries","США":"USA","Россия":"Russia","СССР":"USSR","Великобритания":"United Kingdom","Франция":"France","Германия":"Germany","Япония":"Japan","Южная Корея":"South Korea","Китай":"China","Италия":"Italy","Испания":"Spain","Канада":"Canada","Австралия":"Australia","Индия":"India","Швеция":"Sweden","Дания":"Denmark","Норвегия":"Norway","Польша":"Poland","Украина":"Ukraine","Беларусь":"Belarus","Турция":"Turkey","Мексика":"Mexico","Бразилия":"Brazil","Гонконг":"Hong Kong","Ирландия":"Ireland","Нидерланды":"Netherlands","Бельгия":"Belgium","Финляндия":"Finland","Чехия":"Czech Republic","Австрия":"Austria","Швейцария":"Switzerland","Новая Зеландия":"New Zealand","Аргентина":"Argentina","Таиланд":"Thailand","Тайвань":"Taiwan","Грузия":"Georgia","Казахстан":"Kazakhstan","Латвия":"Latvia","Литва":"Lithuania","Эстония":"Estonia","Германия (ФРГ)":"West Germany","ГДР":"East Germany","Югославия":"Yugoslavia","Чехословакия":"Czechoslovakia","Венгрия":"Hungary","Румыния":"Romania","Болгария":"Bulgaria","Сербия":"Serbia","Хорватия":"Croatia","Греция":"Greece","Португалия":"Portugal","Израиль":"Israel","Иран":"Iran","Египет":"Egypt","ЮАР":"South Africa","Куба":"Cuba","Чили":"Chile","Колумбия":"Colombia","Перу":"Peru","Исландия":"Iceland","Люксембург":"Luxembourg","Монако":"Monaco","Мальта":"Malta","Филиппины":"Philippines","Индонезия":"Indonesia","Малайзия":"Malaysia","Сингапур":"Singapore","Вьетнам":"Vietnam","Пакистан":"Pakistan","Армения":"Armenia","Азербайджан":"Azerbaijan","Узбекистан":"Uzbekistan","Молдова":"Moldova","Алжир":"Algeria","Марокко":"Morocco","Тунис":"Tunisia","Нигерия":"Nigeria","Ливан":"Lebanon","Саудовская Аравия":"Saudi Arabia","ОАЭ":"UAE","Катар":"Qatar","Словакия":"Slovakia","Словения":"Slovenia","Босния и Герцеговина":"Bosnia and Herzegovina","Македония":"North Macedonia","Албания":"Albania","Кипр":"Cyprus","Бангладеш":"Bangladesh","Непал":"Nepal","Камбоджа":"Cambodia","Монголия":"Mongolia","Кыргызстан":"Kyrgyzstan","Таджикистан":"Tajikistan","Туркменистан":"Turkmenistan","Эфиопия":"Ethiopia","Кения":"Kenya","Венесуэла":"Venezuela","Уругвай":"Uruguay","Боливия":"Bolivia","Парагвай":"Paraguay","Эквадор":"Ecuador","Пуэрто-Рико":"Puerto Rico","Ямайка":"Jamaica","Доминикана":"Dominican Republic","Лихтенштейн":"Liechtenstein","В выбранных папках нет поддерживаемых видео (mp4, mkv, avi, mov, wmv, flv, webm, m4v, ts, DVD и Blu-ray папки). Семплы и прочие файлы игнорируются.":"No supported videos in the selected folders (mp4, mkv, avi, mov, wmv, flv, webm, m4v, ts, DVD and Blu-ray folders). Samples and other files are ignored.","Источник постеров":"Poster source","Авто (как у найденного фильма)":"Auto (from the matched source)","IMDb":"IMDb","Letterboxd":"Letterboxd","Если у фильма нет постера в выбранном источнике, остаётся постер по умолчанию. Недостающие подгружаются в фоне и запоминаются.":"If a movie has no poster in the selected source, the default poster stays. Missing ones are loaded in the background and remembered.","Источник описания":"Description source","Авто (Кинопоиск для русского, IMDb или Letterboxd для английского)":"Auto (Kinopoisk for Russian, IMDb or Letterboxd for English)","Если в выбранном источнике нет описания, остаётся исходное. Недостающие подгружаются в фоне и запоминаются.":"If the selected source has no description, the original one stays. Missing ones are loaded in the background and remembered.","Рейтинг на карточках":"Rating on cards","Сохранить постер как PNG…":"Save poster as PNG…","Постер сохранён":"Poster saved","Не удалось загрузить постер":"Could not load the poster","Не удалось сохранить постер":"Could not save the poster","Отменить":"Undo","Вырезать":"Cut","Копировать":"Copy","Вставить":"Paste","Выделить всё":"Select all","IMDb или Letterboxd временно ограничили запросы. Всё найденное сохранено, повторите чуть позже. С ключом Кинопоиска такого не бывает.":"IMDb or Letterboxd temporarily limited requests. Everything found is saved, try again a bit later. This does not happen with a Kinopoisk key.","OMDb — данные IMDb через API":"OMDb — IMDb data via API","OMDb API-ключ":"OMDb API key","Получить бесплатный ключ OMDb":"Get a free OMDb key",};
const CYR=/[А-Яа-яЁё]/;
let trRe=null, trObs=null, trOrig=new WeakMap(), trDone=new WeakMap(), trAttrOrig=new WeakMap();
const TR_ATTRS=["title","placeholder","aria-label","alt"];
function trBuild(){
  if(trRe)return;
  const keys=Object.keys(EN_DICT).sort((a,b)=>b.length-a.length).map(k=>k.replace(/[.*+?^${}()|[\]\\\/]/g,"\\$&"));
  trRe=new RegExp("(?<![А-Яа-яЁё])(?:"+keys.join("|")+")(?![А-Яа-яЁё])","g");
}
function trText(s){
  if(!CYR.test(s))return s;
  const r=s.replace(trRe,m=>EN_DICT[m]);
  return CYR.test(r)?s:r;
}
function trNode(n){
  const d=n.data; if(trDone.get(n)===d)return;
  const r=trText(d);
  if(r!==d){ trOrig.set(n,d); trDone.set(n,r); n.data=r; }
}
function trAttrs(el){
  for(const a of TR_ATTRS){
    const v=el.getAttribute&&el.getAttribute(a); if(!v||!CYR.test(v))continue;
    const r=trText(v); if(r===v)continue;
    let o=trAttrOrig.get(el); if(!o){ o={}; trAttrOrig.set(el,o); } o[a]=v; el.setAttribute(a,r);
  }
}
function trWalk(root){
  if(!root)return;
  if(root.nodeType===3){ if(root.parentNode&&!/^(SCRIPT|STYLE|TEXTAREA)$/.test(root.parentNode.nodeName))trNode(root); return; }
  if(root.nodeType!==1)return;
  trAttrs(root);
  const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT|NodeFilter.SHOW_ELEMENT);
  let n; while((n=w.nextNode())){
    if(n.nodeType===3){ if(!/^(SCRIPT|STYLE|TEXTAREA)$/.test(n.parentNode.nodeName))trNode(n); }
    else trAttrs(n);
  }
}
let trQ=new Set(), trRaf=0;
function trSchedule(nodes){
  nodes.forEach(n=>trQ.add(n));
  if(trRaf)return;
  trRaf=requestAnimationFrame(()=>{ trRaf=0; const q=[...trQ]; trQ.clear(); q.forEach(n=>{ if(n.isConnected!==false)trWalk(n); }); });
}
function trStart(){
  trBuild(); trWalk(document.body);
  if(trObs)return;
  trObs=new MutationObserver(ms=>{
    const ns=[];
    for(const m of ms){
      if(m.type==="characterData")ns.push(m.target);
      else if(m.type==="attributes")ns.push(m.target);
      else m.addedNodes.forEach(x=>ns.push(x));
    }
    if(ns.length)trSchedule(ns);
  });
  trObs.observe(document.body,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:TR_ATTRS});
}
function trStop(){
  if(trObs){ trObs.disconnect(); trObs=null; }
  const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT|NodeFilter.SHOW_ELEMENT);
  let n; while((n=w.nextNode())){
    if(n.nodeType===3){ const o=trOrig.get(n); if(o!==undefined&&trDone.get(n)===n.data){ n.data=o; } trOrig.delete(n); trDone.delete(n); }
    else { const o=trAttrOrig.get(n); if(o){ for(const a in o)n.setAttribute(a,o[a]); trAttrOrig.delete(n); } }
  }
}
const isLat=s=>!!s&&!CYR.test(s);
function metaTitle(m,fb){
  if(S.lang==="en"&&m){ const e=m.titleEn||(isLat(m.titleOrig)?m.titleOrig:""); if(e)return e; }
  return m?(m.titleRu||m.titleOrig||fb):fb;
}
function origLine(m,title){ const o=m&&m.titleOrig; if(!o||o===title)return ""; return (S.lang==="en"&&!isLat(o))?"":o; }
function rerenderAll(){
  refreshGenres(); renderGrid(); renderBanner(); renderStatus();
  if(S.view==="wl"){ if($("#wlq")){ renderWLShell(); } renderWLGrid(); }
  if(S.current&&S.byId.has(S.current)&&$("#modalRoot")&&$("#modalRoot").querySelector(".m-grid"))renderModal();
  if(S.draft&&$("#modalRoot")&&$("#modalRoot").querySelector("#s-roots"))renderSettings();
}
function setLang(l,first){
  l=l==="en"?"en":"ru"; const changed=S.lang!==l; S.lang=l; S.settings.lang=l;
  document.documentElement.lang=l;
  if(l==="en")trStart(); else trStop();
  if(changed&&!first)rerenderAll();
  if(l==="en")enFill();
}
let enBusy=false;
async function enFill(){
  if(enBusy||S.lang!=="en")return; enBusy=true;
  try{
    for(let i=0;i<60&&S.lang==="en";i++){
      const r=await api("fill_en_titles",8); if(!r||!r.ok)break;
      (r.updates||[]).forEach(u=>{
        if(u.id){ const it=S.byId.get(u.id); if(it&&it.meta)it.meta.titleEn=u.titleEn; }
        else if(u.key&&S.wl&&S.wl.items){ const e=S.wl.items.find(x=>x.key===u.key); if(e&&e.meta)e.meta.titleEn=u.titleEn; }
      });
      if(r.updates&&r.updates.length&&S.lang==="en"){ renderGrid(); if(S.view==="wl")renderWLGrid(); }
      if(!r.remaining&&!(r.updates&&r.updates.length))break;
      if(!r.remaining)break;
    }
  }catch(e){}
  enBusy=false;
}
setInterval(()=>{ if(S.lang==="en")enFill(); },25000);
document.addEventListener("change",e=>{ const t=e.target; if(t&&t.id==="s-lang"){ const v=t.value; if(S.draft)S.draft.lang=v; setLang(v); api("save_settings",{lang:v,lang_set:"1"}).then(()=>api("set_source_prefs")).then(applyPrefs).then(()=>{ queueMissing(false); pzFill(); }).catch(()=>{}); } });

let pzBusy=false;
function pzApply(ups){
  let descCur=false;
  (ups||[]).forEach(u=>{
    let m=null;
    if(u.id){ const it=S.byId.get(u.id); m=it&&it.meta; }
    else if(u.key&&S.wl&&S.wl.items){ const e=S.wl.items.find(x=>x.key===u.key); m=e&&e.meta; }
    if(!m)return;
    if(u.poster!=null){ m.poster=u.poster; m.posterPreview=u.posterPreview!=null?u.posterPreview:u.poster; }
    if(u.posterSel!==undefined)m.poster_sel=u.posterSel;
    if(u.description!=null&&u.description!==m.description){ m.description=u.description; if(u.id&&u.id===S.current)descCur=true; }
  });
  if(S.failed)S.failed.clear();
  renderGrid(); if(S.view==="wl")renderWLGrid();
  if(descCur&&$("#modalRoot")&&$("#modalRoot").firstChild&&S.byId.has(S.current))renderModal();
}
async function pzFill(){
  if(pzBusy)return; pzBusy=true;
  try{
    for(let i=0;i<80;i++){
      const r=await api("fill_sources",6); if(!r||!r.ok)break;
      if(r.updates&&r.updates.length)pzApply(r.updates);
      if(!r.remaining)break;
    }
  }catch(e){}
  pzBusy=false;
}
setInterval(()=>{ pzFill(); },30000);
function saveSet(patch){ Object.assign(S.settings,patch); if(S.draft)Object.assign(S.draft,patch); api("save_settings",patch).catch(()=>{}); }
function applyPrefs(r){ if(r&&r.ok){ pzApply(r.updates); pzFill(); } }
document.addEventListener("change",e=>{
  const t=e.target; if(!t)return;
  if(t.id==="s-crt"){ saveSet({card_rating:t.value}); renderGrid(); if(S.view==="wl")renderWLGrid(); }
  if(t.id==="s-auto")saveSet({autostart:t.value});
});

function rootsHTML(d){
  const L=d.root_folders||[];
  if(!L.length)return `<div class="path">Папки не выбраны</div>`;
  return L.map((p,i)=>`<div class="row"><div class="path">${esc(p)}</div><button class="btn icon" data-act="root-del" data-i="${i}" title="Убрать из каталога (файлы не удаляются)">${svg("close",14)}</button></div>`).join("");
}
function openSettings(){ S.draft={...S.settings,root_folders:[...(S.settings.root_folders||[])]}; S.current=null; renderSettings(); }
function renderSettings(){
  const d=S.draft; const custom=d.player_mode==="custom";
  const keyRow=(id,ph,val)=>`<div class="row"><input type="password" id="${id}" class="inp grow" placeholder="${ph}" value="${esc(val||"")}" autocomplete="off" spellcheck="false"><button class="btn icon" data-act="toggle-key" data-for="${id}" title="Показать/скрыть">${svg("eye",16)}</button></div>`;
  $("#modalRoot").innerHTML=`<div class="overlay" data-act="overlay"><div class="modal sm st-modal glass">
    <div class="st-head"><h2 class="t">Настройки</h2><button class="btn icon x" data-act="close">${svg("close")}</button></div>
    <div class="st-body">
    <div class="st-g">
      <div class="sec-t">Библиотека</div>
      <div class="roots" id="s-roots">${rootsHTML(d)}</div>
      <div class="row"><button class="btn" data-act="pick-folder">${svg("folder",16)} Добавить папку…</button></div>
    </div>
    <div class="st-g">
      <div class="st-r"><div class="sec-t">Язык</div><select id="s-lang" class="inp"><option value="ru" ${S.lang==="en"?"":"selected"}>Русский</option><option value="en" ${S.lang==="en"?"selected":""}>English</option></select></div>
    </div>
    <div class="st-g">
      <div class="st-r"><div class="sec-t">Рейтинг на карточках</div><select id="s-crt" class="inp">${[["imdb","IMDb"],["kp","Кинопоиск"],["lb","Letterboxd"]].map(o=>`<option value="${o[0]}" ${(S.settings.card_rating||"imdb")===o[0]?"selected":""}>${o[1]}</option>`).join("")}</select></div>
    </div>
    <div class="st-g">${bgHTML()}</div>
    <div class="st-g">${startHTML()}</div>
    <div class="st-g">${updHTML()}</div>
    <div class="st-g">${tvHTML()}</div>
    <div class="st-g">
      <div class="sec-t">Видеоплеер</div>
      <label class="radio"><input type="radio" name="pm" value="system" ${custom?"":"checked"}> Системный плеер по умолчанию</label>
      <label class="radio"><input type="radio" name="pm" value="custom" ${custom?"checked":""}> Внешний плеер (VLC, PotPlayer, MPC-HC…)</label>
      <div class="row" id="s-prow" style="${custom?"":"opacity:.45;pointer-events:none"}"><div class="path" id="s-player">${esc(d.player_path||"Файл .exe не выбран")}</div><button class="btn" data-act="pick-player">Выбрать .exe…</button></div>
    </div>
    <div class="st-g">
      <div class="st-k">
        <div class="st-kh"><div class="st-kt">Кинопоиск Unofficial — основной источник</div><button class="btn sm" data-act="open-url" data-url="https://kinopoiskapiunofficial.tech">${svg("ext",14)} Получить бесплатный ключ</button></div>
        ${keyRow("s-kp","API-ключ (X-API-KEY)",d.kp_api_key)}
        <div class="hint" style="margin-top:8px">Бесплатный план: до 500 запросов в сутки. Каждый новый фильм — 2 запроса.</div>
      </div>
      <div class="st-k">
        <div class="st-kh"><div class="st-kt">Резервный источник</div><button class="btn sm" data-act="open-url" data-url="https://www.themoviedb.org/settings/api">${svg("ext",14)} Получить ключ TMDB</button></div>
        <div class="row"><select id="s-fb" class="inp"><option value="none" ${d.fallback_source==="tmdb"?"":"selected"}>Не использовать</option><option value="tmdb" ${d.fallback_source==="tmdb"?"selected":""}>TMDB (language=ru-RU)</option></select>
        <input type="password" id="s-tmdb" class="inp grow" placeholder="TMDB API-ключ или Read Access Token" value="${esc(d.tmdb_api_key||"")}" autocomplete="off" spellcheck="false"><button class="btn icon" data-act="toggle-key" data-for="s-tmdb" title="Показать/скрыть">${svg("eye",16)}</button></div>
      </div>
      <div class="st-k">
        <div class="st-kh"><div class="st-kt">OMDb — данные IMDb через API</div><button class="btn sm" data-act="open-url" data-url="https://www.omdbapi.com/apikey.aspx">${svg("ext",14)} Получить бесплатный ключ OMDb</button></div>
        ${keyRow("s-omdb","OMDb API-ключ",d.omdb_api_key)}
        <div class="hint" style="margin-top:8px">Бесплатный план: до 1000 запросов в сутки.</div>
      </div>
      <div class="st-k">
        <div class="st-kh"><div class="st-kt">Letterboxd — ваш вотчлист</div></div>
        <div class="row"><input id="s-lbu" class="inp grow" value="${esc(d.lb_user||"")}" autocomplete="off" spellcheck="false"></div>
      </div>
    </div>
    <div class="st-g">
      <div class="sec-t">Кэш</div>
      <div class="row"><button class="btn" id="btnClear" data-act="clear-cache">Сбросить кэш метаданных</button><span class="hint">Ручные привязки сохраняются. После сброса данные загрузятся заново (расходуются запросы API).</span></div>
      <div class="hint" style="margin-top:12px;user-select:text">Файлы: ${esc(d.config_path||"config.json")} · ${esc(d.cache_path||"metadata_cache.json")}</div>
    </div>
    </div>
    <div class="foot st-foot"><button class="btn primary" data-act="save-settings">Готово</button></div>
  </div></div>`;
  ddClose(); document.querySelectorAll("#modalRoot select.inp").forEach(ddEnhance);
  tvLoad();
}
async function saveSettings(exit){
  if(S.saving)return; S.saving=true;
  try{
    const pm=document.querySelector("input[name=pm]:checked");
    const d={root_folders:S.draft.root_folders||[],player_mode:pm?pm.value:"system",player_path:S.draft.player_path||"",
      kp_api_key:$("#s-kp").value.trim(),tmdb_api_key:$("#s-tmdb").value.trim(),omdb_api_key:$("#s-omdb").value.trim(),lb_user:$("#s-lbu").value.trim(),fallback_source:$("#s-fb").value};
    if(d.player_mode==="custom"&&!d.player_path){
      if(!exit){ toast("Укажите .exe файл плеера или выберите системный","err"); return; }
      d.player_mode="system";
    }
    const prev=S.settings;
    const def={root_folders:[],player_mode:"system",player_path:"",kp_api_key:"",tmdb_api_key:"",omdb_api_key:"",lb_user:"",fallback_source:"none"};
    const changed=Object.keys(d).some(k=>JSON.stringify(d[k])!==JSON.stringify(prev[k]==null||prev[k]===""?def[k]:prev[k]));
    if(exit&&!changed){ closeModal(); return; }
    let r;
    try{ r=await api("save_settings",d); }catch(e){ r=null; }
    if(!r||!r.ok){ toast("Не удалось сохранить настройки","err"); if(exit)closeModal(); return; }
    S.settings=r.settings; closeModal();
    const keys=prev.kp_api_key!==d.kp_api_key||prev.tmdb_api_key!==d.tmdb_api_key||prev.omdb_api_key!==d.omdb_api_key||prev.fallback_source!==d.fallback_source;
    toast("Настройки сохранены");
    if(prev.lb_user!==S.settings.lb_user){ S.lbProf=null; renderLbBox(); if(S.settings.lb_user)wlSync(false); }
    if(JSON.stringify(S.settings.root_folders||[])!==JSON.stringify(prev.root_folders||[])){ await loadLibrary(false); }
    else if(keys){ S.problem=null; S.hint=null; renderBanner(); queueMissing(true); }
    else renderGrid();
  } finally { S.saving=false; }
}
async function pickFolderTop(){
  let r; try{ r=await api("pick_folder"); }catch(e){ return; }
  if(!r||!r.ok||!r.path)return;
  const s=await api("save_settings",{root_folders:[...(S.settings.root_folders||[]),r.path]}); if(s&&s.ok){ S.settings=s.settings; await loadLibrary(false); }
}

let clearArmed=false;
document.addEventListener("click",async e=>{
  if(!e.target.closest("#ctx"))hideMenu();
  const t=e.target.closest("[data-act]"); if(!t)return;
  const act=t.dataset.act;
  if(act==="overlay"){ if(e.target===t)closeModal(); return; }
  switch(act){
    case "open": openModal(t.dataset.id); break;
    case "close": closeModal(); break;
    case "play": play(t.dataset.path); break;
    case "sx": clearSearch(t.dataset.for); break;
    case "reveal": api("reveal",t.dataset.path); break;
    case "open-url": api("open_url",t.dataset.url); break;
    case "season": S.curSeason=Number(t.dataset.s); renderModal(); break;
    case "fix-toggle": S.fix.open=!S.fix.open; S.fix.results=[]; S.fix.msg=""; renderModal(); break;
    case "fix-go": fixSearch(); break;
    case "fix-pick": fixPick(Number(t.dataset.i)); break;
    case "fix-auto": fixAuto(); break;
    case "ctx-watch": { const c=S.ctx; hideMenu(); if(c)setWatched(c.id,true); break; }
    case "ctx-unwatch": { const c=S.ctx; hideMenu(); if(c)setWatched(c.id,false); break; }
    case "ctx-reveal": { const c=S.ctx; hideMenu(); if(c){ const it=S.byId.get(c.id); const f=it?filesOf(it)[0]:null; const p=c.path||(f&&f.path); if(p)api("reveal",p); } break; }
    case "ctx-play": { const c=S.ctx; hideMenu(); if(c&&c.path)play(c.path); break; }
    case "ctx-delete": { const c=S.ctx; hideMenu(); if(c)openDelete(c); break; }
    case "ed-undo": case "ed-cut": case "ed-copy": case "ed-paste": case "ed-del": case "ed-all": edAct(act); break;
    case "ctx-poster-src": { const c=S.ctx; hideMenu(); if(c&&c.pid)posterFrom(c.ptype,c.pid,t.dataset.src); break; }
    case "ctx-save-poster": { const c=S.ctx; hideMenu(); if(c&&c.url)savePoster(c.url,c.name); break; }
    case "ctx-wl-remove": { const c=S.ctx; hideMenu(); if(c)wlRemove(c.key); break; }
    case "ctx-wl-watch": { const c=S.ctx; hideMenu(); if(c)wlWatch(c.key); break; }
    case "ctx-copy": { const c=S.ctx; hideMenu(); if(!c)break;
      if(c.type==="wl"){ const w=S.wl.items.find(x=>x.key===c.key); if(w)copyText(copyName(w.meta,metaTitle(w.meta,""))); }
      else { const it=S.byId.get(c.id); if(it)copyText(copyName(it.meta,titleOf(it),it.year)); }
      break; }
    case "copy-title": {
      if(t.dataset.key){ const w=S.wl.items.find(x=>x.key===t.dataset.key); if(w)copyText(copyName(w.meta,metaTitle(w.meta,""))); }
      else { const it=S.byId.get(t.dataset.id); if(it)copyText(copyName(it.meta,titleOf(it),it.year)); }
      break; }
    case "wl-watch": wlWatch(t.dataset.key); break;
    case "lb-sync": wlSync(false); break;
    case "w-lang": welcomeLang(t.dataset.v); break;
    case "w-start": welcomeStart(); break;
    case "copy-text": copyText(t.dataset.v); break;
    case "tv-pin": tvAct("srv_new_pin"); break;
    case "tv-forget": tvAct("srv_forget"); break;
    case "ctx-pin": case "ctx-unpin": { const c=S.ctx; hideMenu(); if(c)setPin(c,act==="ctx-pin"); break; }
    case "ctx-hide": { const c=S.ctx; hideMenu(); if(c)setHidden(c.id,true); break; }
    case "ctx-unhide": { const c=S.ctx; hideMenu(); if(c)setHidden(c.id,false); break; }
    case "lb-unlink": openLbUnlink(); break;
    case "lb-unlink-ok": closeDlg(); lbUnlink(); break;
    case "toggle-watched": { const it=S.byId.get(t.dataset.id); if(it)setWatched(it.id,it.ghost?false:!it.inWatched); break; }
    case "dlg-close": closeDlg(); break;
    case "dlg-confirm": confirmDelete(); break;
    case "dlg-overlay": if(e.target===t)closeDlg(); break;
    case "wl-add": wlAdd(Number(t.dataset.i)); break;
    case "wl-rematch": wlRematchOpen(t.dataset.key); break;
    case "rm-pick": wlRematchPick(Number(t.dataset.i)); break;
    case "wl-open": wlOpen(t.dataset.key); break;
    case "wl-remove": wlRemove(t.dataset.key); break;
    case "refresh": refreshAll(); break;
    case "remote": openRemote(); break;
    case "remote-scan": remoteScan(); break;
    case "remote-pick": { const x=RM.servers[Number(t.dataset.i)]; if(x){ RM.host=x.host+":"+x.port; remoteGo(RM.host); } break; }
    case "remote-go": remoteGo(); break;
    case "remote-last": remoteLast(); break;
    case "remote-off": remoteOff(); break;
    case "rp-use": { const x=(RM.askPl||[])[Number(t.dataset.i)]; if(x)rpChoose("exe",x.path); break; }
    case "rp-exe": { const x=await api("pick_player"); if(x&&x.path)rpChoose("exe",x.path); break; }
    case "rp-browser": rpChoose("browser"); break;
    case "rp-reset": if(await playerSet("reset")){ RM.askPath=null; renderRemote(); } break;
    case "retry": S.problem=null; renderBanner(); queueMissing(false); break;
    case "folder": pickFolderTop(); break;
    case "settings": openSettings(); break;
    case "toggle-key": { const i=document.getElementById(t.dataset.for); if(i)i.type=i.type==="password"?"text":"password"; break; }
    case "upd-check": checkUpdate(true); break;
    case "upd-install": installUpdate(); break;
    case "upd-later": updHide=true; renderUpdBar(); break;
    case "bg-swatch": { const c=t.dataset.c; const i=$("#bg-color"); if(i)i.value=c; saveBg({bg_color:c}); break; }
    case "bg-pick": { const f=$("#bg-file"); if(f)f.click(); break; }
    case "bg-clear": { const r=await api("clear_background"); if(r&&r.ok){ S.settings=r.settings; applyBg(); const h=$("#bg-hint"); if(h)h.textContent="Фото не выбрано"; } break; }
    case "pick-folder": { const r=await api("pick_folder"); if(r&&r.path){ const L=S.draft.root_folders; if(!L.some(x=>x.toLowerCase()===r.path.toLowerCase()))L.push(r.path); $("#s-roots").innerHTML=rootsHTML(S.draft); } break; }
    case "root-del": { S.draft.root_folders.splice(Number(t.dataset.i),1); $("#s-roots").innerHTML=rootsHTML(S.draft); break; }
    case "pick-player": { const r=await api("pick_player"); if(r&&r.path){ S.draft.player_path=r.path; $("#s-player").textContent=r.path; } break; }
    case "save-settings": saveSettings(); break;
    case "clear-cache":
      if(!clearArmed){ clearArmed=true; t.textContent="Нажмите ещё раз для подтверждения"; setTimeout(()=>{clearArmed=false; const b=$("#btnClear"); if(b)b.textContent="Сбросить кэш метаданных";},4000); }
      else { clearArmed=false; await api("clear_cache"); closeModal(); toast("Кэш сброшен, загружаю заново…"); await loadLibrary(true); }
      break;
  }
});
document.addEventListener("change",e=>{
  if(e.target.name==="pm"){ S.draft.player_mode=e.target.value; const r=$("#s-prow"); if(r){ r.style.opacity=e.target.value==="custom"?"1":".45"; r.style.pointerEvents=e.target.value==="custom"?"auto":"none"; } }
});
let qT=null;
function syncSx(inp){ const p=inp&&inp.closest(".search"); if(p)p.classList.toggle("has",!!inp.value); }
function clearSearch(id){
  const inp=$("#"+id); if(!inp)return;
  inp.value=""; syncSx(inp);
  if(id==="q"){ clearTimeout(qT); S.q=""; if(S.view==="wl")renderWLGrid(); else renderGrid(); }
  else if(id==="wlq"){ clearTimeout(wlT); wlSearch(""); }
  inp.focus();
}
document.addEventListener("input",e=>{
  if(e.target.id==="q"||e.target.id==="wlq")syncSx(e.target);
  if(e.target.id==="q"){ clearTimeout(qT); qT=setTimeout(()=>{S.q=e.target.value; if(S.view==="wl")renderWLGrid(); else renderGrid();},120); }
  else if(e.target.id==="fixQ"){ S.fix.q=e.target.value; }
  else if(e.target.id==="wlq"){ wlQueue(e.target.value); }
});
document.addEventListener("keydown",e=>{
  if(e.key==="Escape"){ if($("#pzoom")){ closePosterZoom(); return; } if($("#dlgRoot").firstChild){ closeDlg(); return; } if($("#ctx")){ hideMenu(); return; } if($("#modalRoot").firstChild){ closeModal(); return; } }
  if(e.key==="Enter"&&e.target.id==="fixQ"){ e.preventDefault(); fixSearch(); return; }
  if(e.key==="Enter"&&e.target.id==="lbu"){ e.preventDefault(); wlSync(false); return; }
  if(e.key==="Enter"&&e.target.id==="wlq"){ e.preventDefault(); clearTimeout(wlT); wlSearch(e.target.value); return; }
  const typing=/INPUT|SELECT|TEXTAREA/.test((document.activeElement||{}).tagName||"");
  if((e.key==="/"||(e.ctrlKey&&e.key.toLowerCase()==="f"))&&!typing){ e.preventDefault(); const sq=S.view==="wl"?$("#wlq"):$("#q"); if(sq){sq.focus();sq.select();} }
});
const redrawView=()=>{ if(S.view==="wl"){ renderWLGrid(); viewFade(["#wlGrid"]); } else { renderGrid(); viewFade(["#grid","#empty"]); } };
$("#typeSel").addEventListener("change",e=>{ S.type=e.target.value; redrawView(); });
$("#genre").addEventListener("change",e=>{ S.genre=e.target.value; redrawView(); });
$("#sort").addEventListener("change",e=>{ S.sort=e.target.value; saveSet({sort:S.sort}); redrawView(); });
let sheenRaf=0;
document.addEventListener("pointermove",e=>{
  if(sheenRaf)return; const t=e.target.closest&&e.target.closest(".sheen"); if(!t)return; const x=e.clientX,y=e.clientY;
  sheenRaf=requestAnimationFrame(()=>{ sheenRaf=0; const r=t.getBoundingClientRect(); t.style.setProperty("--mx",(x-r.left)+"px"); t.style.setProperty("--my",(y-r.top)+"px"); });
},{passive:true});

const palQ=[], palBusy=new Set(); let palRun=0;
function shown(u){ if(!u)return u; if(S.base&&/^https?:/.test(u))return S.base+encodeURIComponent(u); return S.blob.get(u)||u; }
function toBlobUrl(uri){ return fetch(uri).then(r=>r.blob()).then(b=>URL.createObjectURL(b)).catch(()=>uri); }
function needPal(k){ return !S.pal[k]; }
let pfT=null;
let palSaveT=null, palDirty=new Set();
function savePalLater(){
  clearTimeout(palSaveT);
  palSaveT=setTimeout(()=>{ const o={}; Object.keys(S.pal).forEach(k=>{ if(!k.startsWith("local:")&&!S.palSaved.has(k)){ o[k]=S.pal[k]; S.palSaved.add(k); } }); if(Object.keys(o).length)api("save_palettes",o).catch(()=>{}); },2000);
}
function prefetchPosters(){
  clearTimeout(pfT);
  pfT=setTimeout(()=>{
    S.items.forEach(it=>{ const k=posterOf(it,true); if(/^https?:/.test(k))queuePalette(k); });
    ((S.wl&&S.wl.items)||[]).forEach(e=>{ const m=e.meta||{}; const k=m.posterPreview||m.poster||""; if(/^https?:/.test(k))queuePalette(k); });
  },400);
}
function rgb2hsl(r,g,b){ r/=255;g/=255;b/=255; const mx=Math.max(r,g,b),mn=Math.min(r,g,b); let h=0,s=0; const l=(mx+mn)/2, d=mx-mn;
  if(d){ s=l>.5?d/(2-mx-mn):d/(mx+mn); h=mx===r?(g-b)/d+(g<b?6:0):(mx===g?(b-r)/d+2:(r-g)/d+4); h*=60; } return [h,s,l]; }
function glowCss(c){ let [h,s,l]=rgb2hsl(c[0],c[1],c[2]); s=Math.min(1,s*1.25); l=Math.min(.66,Math.max(.46,l)); return `hsl(${Math.round(h)} ${Math.round(s*100)}% ${Math.round(l*100)}%)`; }
function extractPalette(img){
  const w=24,h=36,cv=document.createElement("canvas"); cv.width=w; cv.height=h;
  const cx=cv.getContext("2d",{willReadFrequently:true}); cx.drawImage(img,0,0,w,h);
  const d=cx.getImageData(0,0,w,h).data, bk=new Map();
  for(let i=0;i<d.length;i+=4){
    if(d[i+3]<200)continue; const r=d[i],g=d[i+1],b=d[i+2], mx=Math.max(r,g,b), mn=Math.min(r,g,b), l=(mx+mn)/510;
    if(l<.1||l>.93)continue; const sat=mx?(mx-mn)/mx:0, key=((r>>5)<<6)|((g>>5)<<3)|(b>>5), wt=.3+sat*1.7;
    const o=bk.get(key)||{w:0,r:0,g:0,b:0}; o.w+=wt; o.r+=r*wt; o.g+=g*wt; o.b+=b*wt; bk.set(key,o);
  }
  const list=[...bk.values()].map(o=>[o.r/o.w,o.g/o.w,o.b/o.w,o.w]).sort((a,b)=>b[3]-a[3]), out=[];
  for(const c of list){ if(out.every(p=>Math.hypot(p[0]-c[0],p[1]-c[1],p[2]-c[2])>70))out.push(c); if(out.length===3)break; }
  return out.length?out.map(glowCss):null;
}
function palStyle(key){ const p=key&&S.pal[key]; return p?`--h1:${p[0]};--h2:${p[1]||p[0]};--h3:${p[2]||p[1]||p[0]}`:""; }
function applyPal(key){
  const p=S.pal[key]; if(!p)return;
  document.querySelectorAll("[data-pkey]").forEach(el=>{ if(el.dataset.pkey!==key)return;
    el.style.setProperty("--h1",p[0]); el.style.setProperty("--h2",p[1]||p[0]); el.style.setProperty("--h3",p[2]||p[1]||p[0]); });
}
function queuePalette(key,prio){ if(!key||!needPal(key)||palBusy.has(key))return; palBusy.add(key); if(prio)palQ.unshift(key); else palQ.push(key); pumpPal(); }
function pumpPal(){ while(palRun<4&&palQ.length){ const key=palQ.shift(); palRun++; palWork(key).finally(()=>{ palBusy.delete(key); palRun--; pumpPal(); }); } }
async function palWork(key){
  try{
    let src="";
    if(key.startsWith("local:"))src=S.local[key.slice(6)]||"";
    else if(S.base){ src=shown(key); }
    else { src=S.blob.get(key)||""; if(!src){ const r=await api("poster_data",key); if(typeof r==="string"&&r){ src=await toBlobUrl(r); if(src.startsWith("blob:"))S.blob.set(key,src); } } }
    if(!src||S.pal[key])return;
    const img=new Image(); if(S.base&&src.startsWith(S.base))img.crossOrigin="anonymous";
    await new Promise((ok,no)=>{ img.onload=ok; img.onerror=no; img.src=src; });
    const p=extractPalette(img); if(p){ S.pal[key]=p; applyPal(key); savePalLater(); }
  }catch(e){}
}
const palIO=("IntersectionObserver" in window)?new IntersectionObserver(es=>es.forEach(e=>{ if(e.isIntersecting){ palIO.unobserve(e.target); queuePalette(e.target.dataset.pkey,true); } }),{rootMargin:"400px"}):null;
function observePalettes(){
  document.querySelectorAll(".card[data-pkey]").forEach(el=>{ const k=el.dataset.pkey; if(!k||!needPal(k))return; if(palIO)palIO.observe(el); else queuePalette(k); });
}

const WL_SRC={kp:"Кинопоиск",tmdb:"TMDB",imdb:"IMDb",lb:"Letterboxd"};
let wlT=null, wlSeq=0;
function updateWlCount(){ const n=S.wl.items.length; const el=$("#wlCount"); if(el)el.textContent=" · "+n; }
let ddCur=null;
function ddClose(){
  if(!ddCur)return; const c=ddCur; ddCur=null;
  c.pop.remove(); c.btn.classList.remove("open");
  document.removeEventListener("keydown",c.key,true); document.removeEventListener("mousedown",c.down,true); window.removeEventListener("resize",ddClose);
}
function ddEnhance(sel){
  if(!sel||sel._dd)return; sel._dd=1;
  const btn=document.createElement("button"); btn.type="button"; btn.className="inp dd-btn";
  btn.innerHTML=`<span class="dd-t"></span>${svg("chev",12)}`;
  sel.after(btn); sel.style.display="none";
  const sync=()=>{ const o=sel.options[sel.selectedIndex]; btn.querySelector(".dd-t").textContent=o?o.text:""; };
  sync();
  new MutationObserver(sync).observe(sel,{childList:true,subtree:true,characterData:true});
  const desc=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,"value");
  Object.defineProperty(sel,"value",{get(){ return desc.get.call(sel); },set(v){ desc.set.call(sel,v); sync(); },configurable:true});
  sel.addEventListener("change",sync);
  btn.addEventListener("click",e=>{ e.stopPropagation(); ddOpen(sel,btn); });
  btn.addEventListener("keydown",e=>{ if(e.key==="ArrowDown"||e.key==="Enter"||e.key===" "){ e.preventDefault(); ddOpen(sel,btn); } });
}
function ddOpen(sel,btn){
  if(ddCur&&ddCur.btn===btn){ ddClose(); return; }
  ddClose();
  const opts=[...sel.options].map((o,i)=>({o:o,i:i})).filter(x=>!x.o.hidden);
  const pop=document.createElement("div"); pop.className="sp-pop"+(btn.closest(".st-modal")?" st":"");
  pop.innerHTML=opts.map(x=>`<button type="button" class="sp-i${x.i===sel.selectedIndex?" sel":""}" data-i="${x.i}">${x.i===sel.selectedIndex?svg("check",14):`<span class="sp-ic"></span>`}<span>${esc(x.o.text)}</span></button>`).join("");
  document.body.appendChild(pop);
  const r=btn.getBoundingClientRect(); pop.style.minWidth=r.width+"px"; pop.style.left=Math.max(8,Math.min(r.left,innerWidth-pop.offsetWidth-8))+"px";
  const below=innerHeight-r.bottom-14, above=r.top-14;
  if(below>=Math.min(pop.scrollHeight+12,220)||below>=above){ pop.style.maxHeight=Math.min(360,below)+"px"; pop.style.top=(r.bottom+6)+"px"; }
  else { const mh=Math.min(360,above); pop.style.maxHeight=mh+"px"; pop.style.top=(r.top-6-Math.min(pop.offsetHeight,mh))+"px"; }
  btn.classList.add("open");
  let hl=opts.findIndex(x=>x.i===sel.selectedIndex); const items=[...pop.querySelectorAll(".sp-i")];
  const mark=()=>{ items.forEach((b,k)=>b.classList.toggle("hl",k===hl)); if(items[hl])items[hl].scrollIntoView({block:"nearest"}); };
  const pick=k=>{ if(!opts[k])return; sel.selectedIndex=opts[k].i; sel.dispatchEvent(new Event("change",{bubbles:true})); ddClose(); btn.focus(); };
  const key=e=>{
    if(e.key==="Escape"){ e.preventDefault(); e.stopPropagation(); ddClose(); btn.focus(); }
    else if(e.key==="ArrowDown"){ e.preventDefault(); hl=Math.min(items.length-1,hl+1); mark(); }
    else if(e.key==="ArrowUp"){ e.preventDefault(); hl=Math.max(0,hl-1); mark(); }
    else if(e.key==="Enter"||e.key===" "){ e.preventDefault(); e.stopPropagation(); pick(hl); }
  };
  const down=e=>{ if(!pop.contains(e.target)&&!btn.contains(e.target))ddClose(); };
  pop.addEventListener("click",e=>{ const b=e.target.closest(".sp-i"); if(b)pick(items.indexOf(b)); });
  document.addEventListener("keydown",key,true); document.addEventListener("mousedown",down,true); window.addEventListener("resize",ddClose);
  ddCur={pop:pop,btn:btn,key:key,down:down}; mark();
}
function segMove(){
  const seg=$("#viewSeg"); if(!seg)return; const on=seg.querySelector("button.on"), pill=seg.querySelector(".seg-pill"); if(!on||!pill)return;
  pill.style.width=on.offsetWidth+"px"; pill.style.transform=`translateX(${on.offsetLeft}px)`;
}
function segInit(){
  const seg=$("#viewSeg"); if(!seg)return; segMove();
  if(window.ResizeObserver){ const ro=new ResizeObserver(segMove); ro.observe(seg); seg.querySelectorAll("button").forEach(b=>ro.observe(b)); }
  setTimeout(()=>seg.classList.add("rdy"),120);
}
function setView(v){
  S.view=v; document.body.classList.toggle("v-wl",v==="wl");
  document.querySelectorAll("#viewSeg button").forEach(b=>b.classList.toggle("on",b.dataset.v===v)); segMove();
  hideMenu();
  const ho=$("#typeSel option[value=hidden]"); if(ho)ho.hidden=(v==="wl");
  if(v==="wl"){ if(S.type==="hidden"){ S.type="all"; $("#typeSel").value="all"; } refreshGenres(); if(!$("#wlq"))renderWLShell(); loadWL().then(()=>{ const q=$("#wlq"); if(q&&!$("#modalRoot").firstChild)q.focus(); }); }
  else { refreshGenres(); renderGrid(); }
  renderStatus(); viewFade();
}
function viewFade(list){
  (list||["#grid","#empty","#wl"]).forEach(s=>{ const el=$(s); if(!el)return; el.classList.remove("vt-in"); void el.offsetWidth; el.classList.add("vt-in"); });
}
async function loadWL(){
  let r; try{ r=await api("wl_list"); }catch(e){ return; }
  if(r&&r.ok){
    const sig=JSON.stringify(r.items), same=sig===S.wl.sig&&$("#wlGrid")&&$("#wlGrid").children.length>0;
    S.wl.sig=sig; S.wl.items=r.items; updateWlCount(); if(S.view==="wl")refreshGenres();
    if(!same)renderWLGrid();
    renderStatus();
  }
}
function renderWLShell(){
  $("#wl").innerHTML=`<div class="wl-wrap">
    <div class="wl-head"><div class="wl-t">Добавить фильм</div>
      <div class="search wl-s"><span>${svg("search")}</span><input id="wlq" class="inp" autocomplete="off" spellcheck="false"><button type="button" class="sx" data-act="sx" data-for="wlq" title="Очистить">${svg("close",14)}</button></div>
      <div id="lbBox">${lbBoxHTML()}</div></div>
    <div id="wlRes"></div>
    <div class="hint" id="lbMsg" style="margin:8px 12px 0"></div>
    <div id="wlGrid" class="wl-grid"></div></div>`;
  renderWLRes(); renderWLGrid(); updateWlCount();
}
function wlQueue(q){ clearTimeout(wlT); wlT=setTimeout(()=>wlSearch(q),650); }
async function wlSearch(q){
  q=(q||"").trim(); const my=++wlSeq;
  if(q.length<2){ S.wl.results=[]; S.wl.notes=[]; S.wl.msg=""; S.wl.busy=false; renderWLRes(); return; }
  S.wl.busy=true; S.wl.msg=""; renderWLRes();
  let r; try{ r=await api("wl_search",q); }catch(e){ r={ok:false,error:"Нет связи с приложением"}; }
  if(my!==wlSeq)return;
  S.wl.busy=false;
  if(!r||!r.ok){ S.wl.results=[]; S.wl.notes=[]; S.wl.msg=(r&&r.error)||"Ошибка поиска"; }
  else { S.wl.results=r.results; S.wl.notes=r.notes||[]; S.wl.msg=r.results.length?"":"Ничего не найдено. Попробуйте другое написание или латиницу."; }
  renderWLRes();
}
function renderWLRes(){
  const el=$("#wlRes"); if(!el)return; const w=S.wl;
  const notes=(w.notes||[]).map(n=>`<div class="hint" style="margin-top:10px">${esc(n)}</div>`).join("");
  if(w.busy){ el.innerHTML=`<div class="dd wl-dd"><div class="dd-e">Ищу…</div></div>`; return; }
  if(w.msg){ el.innerHTML=`<div class="dd wl-dd"><div class="dd-e">${esc(w.msg)}</div></div>${notes}`; return; }
  if(!w.results.length){ el.innerHTML=notes; return; }
  el.innerHTML=`<div class="dd wl-dd">${w.results.map((c,i)=>{
    const r=c.ratingKp!=null?c.ratingKp:(c.ratingImdb!=null?c.ratingImdb:c.ratingTmdb);
    const pv=c.posterPreview||c.poster;
    const orig=c.titleOrig&&c.titleOrig!==c.titleRu?c.titleOrig:"";
    const info=[orig,WL_SRC[c.source],c.year,c.type==="series"?"Сериал":"Фильм",r!=null?"★ "+fmtR(r):null].filter(Boolean).join(" · ");
    return `<div class="wl-r"><div>${pv?`<img data-poster="1" src="${esc(shown(pv))}" referrerpolicy="no-referrer" alt="">`:`<div class="ph"></div>`}</div>
      <div><b>${esc(c.titleRu||c.titleOrig||"Без названия")}</b><small>${esc(info)}</small></div>
      ${c.inList?`<span class="chip">В списке ${svg("check",13)}</span>`:`<button class="btn sm primary" data-act="wl-add" data-i="${i}">${svg("plus",14)} Добавить</button>`}</div>`;
  }).join("")}</div>${notes}`;
}
function wlCard(e,i){
  const m=e.meta||{}, title=metaTitle(m,"Без названия"), year=m.year||"";
  const pr=pickRating(m), r=pr?pr.v:null;
  const src=m.posterPreview||m.poster||"";
  const type=m.type==="series"?"Сериал":"Фильм";
  const pkey=src;
  return `<div class="card sheen${e.pinned?" pinned":""}" data-act="wl-open" data-key="${esc(e.key)}" data-pkey="${esc(pkey)}" style="animation-delay:${Math.min(i,24)*18}ms;${palStyle(pkey)}"><div class="halo"></div><div class="cv">
    <div class="stub" style="--g:${hash(title)%8}"><div class="stub-l">${esc(title.trim().charAt(0).toUpperCase())}</div></div>
    ${src?`<img data-poster="1" src="${esc(shown(src))}" decoding="async" loading="lazy" referrerpolicy="no-referrer" alt="">`:""}
    ${pr?`<div class="rt ${rcls(r)}">${pr.t}</div>`:""}${e.pinned?`<div class="pn${S.freshPin==="w|"+e.key?" fresh":""}">${svg("pin",14)}</div>`:""}
    ${(e.inLibrary||m.type==="series")?`<div class="tp">${e.inLibrary?"В библиотеке":type}</div>`:""}
    <div class="cap"><div class="cap-t">${esc(title)}</div><div class="cap-s">${esc(year)}${m.duration?" · "+m.duration+" мин":""}</div></div></div></div>`;
}
function wlVisible(){
  const a=S.wl.items.filter(e=>{
    const m=e.meta||{};
    if(S.type==="movie"||S.type==="series"){ if((m.type==="series"?"series":"movie")!==S.type)return false; }
    if(S.genre&&!(m.genres||[]).includes(S.genre))return false;
    const q=S.q.trim().toLowerCase().replace(/ё/g,"е");
    if(q){ const hay=[m.titleRu,m.titleOrig,m.titleEn,m.year].join(" ").toLowerCase().replace(/ё/g,"е"); if(!hay.includes(q))return false; }
    return true;
  });
  const t=e=>String(metaTitle(e.meta,"")||"").toLowerCase();
  const y=e=>(e.meta&&e.meta.year)||0;
  const r=e=>{ const p=pickRating(e.meta); return p?p.v:-1; };
  const cmp={
    added:(p,q)=>(q.added||0)-(p.added||0),
    rating:(p,q)=>r(q)-r(p),
    yearDesc:(p,q)=>y(q)-y(p),
    yearAsc:(p,q)=>(y(p)||9999)-(y(q)||9999),
    title:(p,q)=>t(p).localeCompare(t(q),"ru")
  }[S.sort]||(()=>0);
  a.sort(cmp);
  const pin=a.filter(x=>x.pinned).sort((x,z)=>z.pinned-x.pinned);
  return pin.length?pin.concat(a.filter(x=>!x.pinned)):a;
}
function renderWLGrid(){
  const g=$("#wlGrid"); if(!g)return;
  const items=wlVisible();
  g.innerHTML=items.length?items.map(wlCard).join(""):(S.wl.items.length?`<div class="wl-empty">Ничего не найдено</div>`:`<div class="wl-empty">Список пока пуст.<br>Введите название выше и нажмите «Добавить» у нужного варианта.</div>`);
  markPinGap(g); observePalettes();
}
function markPinGap(g){
  g.querySelectorAll(".card.pgn").forEach(c=>c.classList.remove("pgn"));
  const pins=g.querySelectorAll(".card.pinned"); if(!pins.length)return;
  const last=pins[pins.length-1]; const top=last.offsetTop;
  for(let c=last.nextElementSibling;c&&c.offsetTop===top;c=c.nextElementSibling)c.classList.add("pgn");
}
function flipRender(g,fn){
  const old=new Map(); g.querySelectorAll(".card").forEach(c=>old.set(c.dataset.id||c.dataset.key,c.getBoundingClientRect()));
  fn();
  g.querySelectorAll(".card").forEach(c=>{
    const o=old.get(c.dataset.id||c.dataset.key); if(!o)return;
    const n=c.getBoundingClientRect(), dx=o.left-n.left, dy=o.top-n.top;
    if(Math.abs(dx)<1&&Math.abs(dy)<1)return;
    c.animate([{transform:`translate(${dx}px,${dy}px)`},{transform:"none"}],{duration:560,easing:"cubic-bezier(.2,.8,.2,1)"});
  });
}
var pgT=0;
window.addEventListener("resize",()=>{ clearTimeout(pgT); pgT=setTimeout(()=>{ markPinGap($("#grid")); const w=$("#wlGrid"); if(w)markPinGap(w); },120); });
let lbBusy=false, lbFillBusy=false, lbPT=0;
async function lbProfRefresh(){
  const p=S.lbProf; if(!S.settings.lb_user||(p&&((p.films!=null&&p.avatar&&p.name)||p.err))||lbPT>=15||lbBusy)return;
  lbPT++;
  try{ const r=await api("lb_profile_refresh"); if(r&&r.ok&&r.profile){ S.lbProf=r.profile; renderLbBox(); } }catch(e){}
}
setInterval(lbProfRefresh,90000);
function fmtNum(n){ return n==null?"—":Number(n).toLocaleString("ru-RU"); }
function lbBoxHTML(){
  const nick=S.settings.lb_user||"", p=S.lbProf&&S.lbProf.nick===nick?S.lbProf:null;
  if(!nick)return `<div class="lb-row"><span class="lb-l">Letterboxd</span><input id="lbu" class="inp" autocomplete="off" spellcheck="false"><button class="btn" id="lbGo" data-act="lb-sync">Загрузить вотчлист</button></div>`;
  const shownName=(p&&p.name)||nick;
  const av=p&&p.avatar?`<img src="${esc(shown(p.avatar))}" referrerpolicy="no-referrer" alt="" onerror="this.remove()">`:esc(shownName.charAt(0).toUpperCase());
  const stats=p?(p.films!=null?`Просмотрено: ${fmtNum(p.films)} · `:"")+`В вотчлисте: ${fmtNum(p.watchlist)}`:"Загрузка…";
  const why="";
  return `<div class="lb-card"><div class="lb-av">${av}</div><div class="lb-i"><b>${esc(shownName)}</b><small>${stats}</small>${why}</div>
    <button class="btn icon" data-act="open-url" data-url="https://letterboxd.com/${encodeURIComponent(nick)}/" title="Открыть профиль на Letterboxd">${svg("ext",16)}</button>
    <button class="btn icon" id="lbGo" data-act="lb-sync" title="Обновить вотчлист">${svg("refresh",16)}</button>
    <button class="btn icon" data-act="lb-unlink" title="Удалить профиль">${svg("trash",16)}</button></div>`;
}
function renderLbBox(){ const b=$("#lbBox"); if(b)b.innerHTML=lbBoxHTML(); }
async function lbUnlink(){
  try{ await api("lb_unlink"); }catch(e){}
  S.settings.lb_user=""; S.lbProf=null; renderLbBox();
  const m=$("#lbMsg"); if(m)m.textContent="";
  const i=$("#lbu"); if(i)i.focus();
}
async function wlSync(silent){
  if(lbBusy)return;
  const inp=$("#lbu"); const nick=((inp?inp.value:S.settings.lb_user)||"").trim();
  if(!nick){ if(!silent){ toast("Укажите ник Letterboxd","err"); if(inp)inp.focus(); } return; }
  lbBusy=true; const go=$("#lbGo"), msg=$("#lbMsg"); if(go)go.disabled=true; if(msg&&!silent)msg.textContent="Загружаю вотчлист с Letterboxd…";
  let r; try{ r=await api("wl_lb_sync",nick); }catch(e){ r={ok:false,error:"Нет связи с приложением"}; }
  lbBusy=false; const go2=$("#lbGo"), msg2=$("#lbMsg"); if(go2)go2.disabled=false;
  if(!r||!r.ok){ const t=(r&&r.error)||"Не удалось загрузить вотчлист"; if(msg2)msg2.textContent=t; if(!silent)toast(t,"err"); return; }
  S.settings.lb_user=r.nick||nick; S.lbProf=r.profile||null; lbPT=0; renderLbBox();
  S.wl.items=r.items; updateWlCount(); renderWLGrid(); renderStatus();
  const t="Letterboxd: в списке "+r.total+", добавлено новых: "+r.added;
  if(msg2)msg2.textContent=t; if(!silent||r.added)toast(t);
  wlLbFill();
}
async function wlLbFill(){
  if(lbFillBusy)return; lbFillBusy=true;
  try{
    for(let i=0;i<150;i++){
      const r=await api("wl_lb_fill",3); if(!r||!r.ok)break;
      (r.updates||[]).forEach(u=>{ const k=S.wl.items.findIndex(x=>x.key===u.key); if(k>=0)S.wl.items[k]=u; });
      if(r.updates&&r.updates.length&&S.view==="wl")renderWLGrid();
      if(!r.remaining||r.stop)break;
    }
  }catch(e){}
  lbFillBusy=false;
}
setInterval(()=>{ if(S.wl&&S.wl.items.some(x=>x.meta&&x.meta.lb_pending))wlLbFill(); },60000);
function copyName(m,fb,year){
  const t=((m&&(m.titleEn||m.titleOrig))||fb||"").trim(), y=year||(m&&m.year)||"";
  return t+(y?" "+y:"");
}
function copyText(t){ if(!t)return; api("clip_set",t).catch(()=>{}); toast("Скопировано: "+t); }
async function wlWatch(key){
  let r; try{ r=await api("wl_to_watched",key); }catch(e){ r=null; }
  if(!r||!r.ok){ toast((r&&r.error)||"Не удалось перенести","err"); return; }
  S.wl.items=r.items;
  if(r.ghost){ S.items=S.items.filter(x=>x.id!==r.ghost.id); S.items.push(r.ghost); S.byId.set(r.ghost.id,r.ghost); }
  closeModal(); updateWlCount(); renderWLRes(); renderWLGrid(); refreshGenres(); renderGrid(); renderStatus(); toast("Перенесено в Watched");
}
let rmT=0;
function wlRematchOpen(key){
  const e=S.wl.items.find(x=>x.key===key); if(!e)return; const m=e.meta||{};
  S.rm={key,seq:0,results:[],busy:false,msg:""};
  const sl=String(m.urlLb||"").match(/\/film\/([^/]+)/);
  const base=sl?sl[1].replace(/-\d{4}$/,"").replace(/-/g," "):(m.titleOrig||m.titleRu||"");
  const q=(base+(m.year?" "+m.year:"")).trim();
  $("#dlgRoot").innerHTML=`<div class="overlay dlg" data-act="dlg-overlay"><div class="modal sm glass rm">
    <h2 class="t">Изменить совпадение</h2>
    <div class="hint" style="margin-bottom:10px">Если фильмов с одинаковым названием несколько, найдите нужный и выберите его. Можно писать название и год, например: Spring 2014.</div>
    <div class="search"><span>${svg("search")}</span><input id="rm-q" class="inp" autocomplete="off" spellcheck="false" value="${esc(q)}"></div>
    <div id="rmRes" class="rm-list"></div>
    <div class="foot"><button class="btn" data-act="dlg-close">Закрыть</button></div></div></div>`;
  rmSearch(q); const i=$("#rm-q"); if(i){ i.focus(); i.setSelectionRange(i.value.length,i.value.length); }
}
async function rmSearch(q){
  const R=S.rm; if(!R)return; q=(q||"").trim(); const my=++R.seq;
  if(q.length<2){ R.results=[]; R.msg=""; R.busy=false; renderRm(); return; }
  R.busy=true; R.msg=""; renderRm();
  let r; try{ r=await api("wl_search",q); }catch(e){ r={ok:false,error:"Нет связи с приложением"}; }
  if(S.rm!==R||my!==R.seq)return;
  R.busy=false;
  if(!r||!r.ok){ R.results=[]; R.msg=(r&&r.error)||"Ошибка поиска"; }
  else { R.results=r.results; R.msg=r.results.length?"":"Ничего не найдено. Попробуйте другое написание или латиницу."; }
  renderRm();
}
function renderRm(){
  const el=$("#rmRes"), R=S.rm; if(!el||!R)return;
  if(R.busy){ el.innerHTML=`<div class="dd-e">Ищу…</div>`; return; }
  if(R.msg){ el.innerHTML=`<div class="dd-e">${esc(R.msg)}</div>`; return; }
  el.innerHTML=R.results.map((c,i)=>{
    const r=c.ratingKp!=null?c.ratingKp:(c.ratingImdb!=null?c.ratingImdb:c.ratingTmdb);
    const pv=c.posterPreview||c.poster;
    const orig=c.titleOrig&&c.titleOrig!==c.titleRu?c.titleOrig:"";
    const info=[orig,WL_SRC[c.source],c.year,c.type==="series"?"Сериал":"Фильм",r!=null?"★ "+fmtR(r):null].filter(Boolean).join(" · ");
    return `<div class="wl-r"><div>${pv?`<img data-poster="1" src="${esc(shown(pv))}" referrerpolicy="no-referrer" alt="">`:`<div class="ph"></div>`}</div>
      <div><b>${esc(c.titleRu||c.titleOrig||"Без названия")}</b><small>${esc(info)}</small></div>
      <button class="btn sm primary" data-act="rm-pick" data-i="${i}">Выбрать</button></div>`;
  }).join("");
}
async function wlRematchPick(i){
  const R=S.rm; if(!R)return; const c=R.results[i]; if(!c||c.picking)return; c.picking=true;
  let r; try{ r=await api("wl_rematch",R.key,c); }catch(e){ r={ok:false,error:"Нет связи с приложением"}; }
  c.picking=false;
  if(!r||!r.ok){ toast((r&&r.error)||"Не удалось изменить","err"); return; }
  const key=R.key; S.rm=null; closeDlg();
  S.wl.items=r.items; const ne=S.wl.items.find(x=>x.key===key); if(ne)ne.enr=0;
  renderWLGrid(); renderWLRes(); wlOpen(key); toast("Совпадение изменено");
}
document.addEventListener("input",e=>{
  const t=e.target; if(!t||t.id!=="rm-q")return;
  clearTimeout(rmT); rmT=setTimeout(()=>rmSearch(t.value),600);
});
document.addEventListener("keydown",e=>{
  if(e.key==="Enter"&&e.target&&e.target.id==="rm-q"){ clearTimeout(rmT); rmSearch(e.target.value); }
});
async function wlAdd(i){
  const c=S.wl.results[i]; if(!c||c.adding)return; c.adding=true;
  let r; try{ r=await api("wl_add",c); }catch(e){ r={ok:false,error:"Нет связи с приложением"}; }
  c.adding=false;
  if(!r||!r.ok){ toast((r&&r.error)||"Не удалось добавить","err"); return; }
  S.wl.items=r.items; c.inList=true; updateWlCount(); renderWLRes(); renderWLGrid(); renderStatus(); toast("Добавлено в вотчлист");
  const ne=r.items[0]; if(ne)wlEnrich(ne.key);
}
async function wlEnrich(key){
  let r; try{ r=await api("wl_enrich",key); }catch(e){ return; }
  if(!r||!r.ok||!r.meta)return;
  const e=S.wl.items.find(x=>x.key===key); if(!e)return;
  e.meta=Object.assign({},e.meta,r.meta); e.enr=1;
  renderWLGrid();
  const mr=$("#modalRoot"); if(mr&&mr.querySelector("[data-wlkey=\""+key+"\"]"))wlOpen(key);
}
function wlOpen(key){
  const e=S.wl.items.find(x=>x.key===key); if(!e)return; const m=e.meta||{};
  const title=metaTitle(m,"Без названия"), orig=origLine(m,title);
  const poster=m.poster||m.posterPreview||"";
  const rb=[]; if(m.ratingKp!=null)rb.push(["Кинопоиск",m.ratingKp]); if(m.ratingImdb!=null)rb.push(["IMDb",m.ratingImdb]); if(m.ratingTmdb!=null)rb.push(["TMDB",m.ratingTmdb]);
  const chips=[`<span class="chip t">${m.type==="series"?"Сериал":"Фильм"}</span>`]; if(m.year)chips.push(`<span class="chip">${m.year}</span>`);
  if(m.duration)chips.push(`<span class="chip">${m.duration} мин</span>`); if(e.inLibrary)chips.push(`<span class="chip">Есть в библиотеке</span>`);
  chips.push(`<button class="chip cp" data-act="copy-title" data-key="${esc(e.key)}" title="Копировать название и год">${svg("copy",14)}</button>`);
  const genres=m.genres||[], countries=m.countries||[];
  $("#modalRoot").innerHTML=`<div class="overlay mv" data-act="overlay" data-wlkey="${esc(e.key)}"><div class="modal glass">
    <button class="btn icon x" data-act="close" title="Закрыть (Esc)">${svg("close")}</button>
    <div class="m-grid"><div class="m-left"><div class="m-wrap" data-purl="${esc(m.poster||m.posterPreview||"")}" data-pname="${esc(title+(m.year?" ("+m.year+")":""))}" data-ptype="key" data-pid="${esc(e.key)}" data-pkey="${esc(m.posterPreview||m.poster||"")}" style="${palStyle(m.posterPreview||m.poster||"")}"><div class="halo"></div><div class="m-poster"><div class="stub" style="--g:${hash(title)%8}"><div class="stub-l">${esc(title.trim().charAt(0).toUpperCase())}</div></div>${poster?`<img data-wlposter="1" src="${esc(shown(poster))}" referrerpolicy="no-referrer" alt="">`:""}</div></div></div>
    <div class="m-right"><h2>${esc(title)}</h2>${orig?`<div class="orig">${esc(orig)}</div>`:`<div style="height:10px"></div>`}
      <div class="chips">${chips.join("")}</div>
      ${(rb.length||lbBadge(m))?`<div class="ratings">${rb.map(r=>ratingBadge(r[0],r[1],srcLinks(m)[r[0]])).join("")}${lbBadge(m)}</div>`:""}
      ${genres.length?`<div class="chips">${genres.map(g=>`<span class="chip">${esc(cap1(g))}</span>`).join("")}</div>`:""}
      ${countries.length?`<div class="meta-l"><b>Страны:</b> ${esc(countries.join(", "))}</div>`:""}
      ${m.description?`<div class="desc">${esc(m.description)}</div>`:""}
      <div class="actions">
        <button class="btn lg" data-act="wl-watch" data-key="${esc(e.key)}">Просмотрено</button>
        <button class="btn lg" data-act="wl-remove" data-key="${esc(e.key)}">Убрать из вотчлиста</button>
        <button class="btn lg" data-act="wl-rematch" data-key="${esc(e.key)}">Изменить совпадение</button>
      </div>
      ${srcLine(m)}
      </div></div></div></div>`;
  const im=$("[data-wlposter]"); if(im)im.addEventListener("error",()=>{ const pv=m.posterPreview; if(pv&&im.src!==pv&&!im.dataset.t){im.dataset.t="1";im.src=pv;return;} im.remove(); });
  queuePalette(m.posterPreview||m.poster||"");
  if(!e.enr){ e.enr=1; wlEnrich(key); }
}
async function wlRemove(key){
  let r; try{ r=await api("wl_remove",key); }catch(e){ r=null; }
  if(!r||!r.ok){ toast("Не удалось удалить","err"); return; }
  S.wl.items=r.items; S.wl.results.forEach(c=>{ if(c.inList&&!r.items.some(x=>x.key===(c.source+":"+c.ext_id)))c.inList=false; });
  closeModal(); updateWlCount(); renderWLRes(); renderWLGrid(); renderStatus(); toast("Убрано из вотчлиста");
}
$("#viewSeg").addEventListener("click",e=>{ const b=e.target.closest("button"); if(b)setView(b.dataset.v); });

const inView=it=>S.view==="wd"?!!it.inWatched:!it.inWatched;
function emptyMsg(){
  const any=S.items.length>0;
  if(S.type==="hidden")return `<div class="box glass"><h2>Скрытых фильмов нет</h2><p>Нажмите правой кнопкой мыши по постеру и выберите «Скрыть».</p></div>`;
  if(S.view==="wd"&&!S.items.some(i=>i.inWatched))return `<div class="box glass"><h2>В Watched пока пусто</h2><p>Нажмите правой кнопкой мыши по постеру и выберите «Перенести в Watched».</p></div>`;
  if(S.view==="lib"&&any&&S.items.every(i=>i.inWatched))return `<div class="box glass"><h2>Всё просмотрено</h2><p>Все фильмы из папки находятся во вкладке Watched.</p></div>`;
  return `<div class="box glass"><h2>Ничего не найдено</h2><p>Измените запрос или фильтры.</p></div>`;
}
function updateCounts(){
  const nt=S.items.filter(i=>!i.inWatched&&!i.hidden).length, wd=S.items.filter(i=>i.inWatched&&!i.hidden).length, wl=S.wl.items.length;
  const set=(id,n)=>{ const el=$(id); if(el)el.textContent=" · "+n; };
  set("#ntCount",nt); set("#wdCount",wd); set("#wlCount",wl);
}
const extOf=f=>{ if(f&&typeof f==="object"&&f.fmt)return f.fmt; const n=(f&&typeof f==="object")?f.name:f; const m=/\.([A-Za-z0-9]+)$/.exec(n||""); return m?m[1].toUpperCase():"?"; };
const filesOf=it=>it.kind==="series"?it.seasons.flatMap(s=>s.episodes):it.files;
const titleOf=it=>metaTitle(it.meta,it.title);
function hideMenu(){ const m=$("#ctx"); if(m)m.remove(); }
function showMenu(x,y,html){
  hideMenu(); const m=document.createElement("div"); m.id="ctx"; m.className="ctx glass"; m.innerHTML=html; document.body.appendChild(m);
  const r=m.getBoundingClientRect();
  m.style.left=Math.max(8,Math.min(x,innerWidth-r.width-8))+"px"; m.style.top=Math.max(8,Math.min(y,innerHeight-r.height-8))+"px";
}
function infoRows(files){
  if(!files.length)return `<div class="ctx-i"><span>Файлы</span><b>нет на диске</b></div>`;
  if(files.length===1)return `<div class="ctx-fi"><span>${extOf(files[0])}</span><span>·</span><span>${fmtSize(files[0].size)||"—"}</span></div>`;
  const fm=[...new Set(files.map(f=>extOf(f)))].join(", "), tot=files.reduce((a,f)=>a+(f.size||0),0);
  return `<div class="ctx-i"><span>Файлов</span><b>${files.length}</b></div><div class="ctx-i"><span>Форматы</span><b>${fm}</b></div><div class="ctx-i"><span>Общий размер</span><b>${fmtSize(tot)||"—"}</b></div>`;
}
const cb=(act,label,icon,cls)=>`<button class="ctx-b${cls?" "+cls:""}" data-act="${act}">${svg(icon,16)}<span>${label}</span></button>`;
function openItemMenu(x,y,it){
  S.ctx={type:"item",id:it.id};
  const head=`<div class="ctx-h"><b>${esc(titleOf(it))}</b><small>${effType(it)==="series"?"Сериал":"Фильм"}${it.year?" · "+it.year:""}</small></div>${infoRows(filesOf(it))}<div class="ctx-sep"></div>`;
  const w=(it.ghost||it.inWatched)?cb("ctx-unwatch",it.ghost?"Убрать из Watched":"Вернуть в Not watched","undo"):cb("ctx-watch","Перенести в Watched","check");
  const pn=it.pinned?cb("ctx-unpin","Открепить","pin"):cb("ctx-pin","Закрепить","pin");
  const hd=it.hidden?cb("ctx-unhide","Вернуть из скрытых","eye"):cb("ctx-hide","Скрыть","eyeoff");
  const cp=cb("ctx-copy","Копировать название и год","copy");
  const rv=it.ghost?"":cb("ctx-reveal","Показать в папке","folder");
  const del=it.ghost?"":`<div class="ctx-sep"></div>`+cb("ctx-delete","Удалить с компьютера…","trash","danger");
  showMenu(x,y,head+w+pn+hd+`<div class="ctx-sep"></div>`+cp+rv+del);
}
function openFileMenu(x,y,it,path){
  const f=filesOf(it).find(z=>z.path===path); if(!f)return;
  S.ctx={type:"file",id:it.id,path};
  showMenu(x,y,`<div class="ctx-h"><b>${esc(f.name)}</b><small>${esc(titleOf(it))}</small></div>${infoRows([f])}<div class="ctx-sep"></div>`
    +cb("ctx-play","Смотреть","play")+cb("ctx-reveal","Показать в папке","folder")+`<div class="ctx-sep"></div>`+cb("ctx-delete","Удалить файл с компьютера…","trash","danger"));
}
const TXT_TYPES=["text","search","url","email","tel","password",""];
function editMenu(x,y,el){
  const ro=el.readOnly||el.disabled, has=el.selectionStart!==el.selectionEnd;
  S.ctx={type:"edit",el};
  showMenu(x,y,`<button class="ctx-b" data-act="ed-undo" ${ro?"disabled":""}>Отменить</button><div class="ctx-sep"></div>
    <button class="ctx-b" data-act="ed-cut" ${ro||!has?"disabled":""}>Вырезать</button>
    <button class="ctx-b" data-act="ed-copy" ${has?"":"disabled"}>Копировать</button>
    <button class="ctx-b" data-act="ed-paste" ${ro?"disabled":""}>Вставить</button>
    <button class="ctx-b" data-act="ed-del" ${ro||!has?"disabled":""}>Удалить</button><div class="ctx-sep"></div>
    <button class="ctx-b" data-act="ed-all" ${el.value?"":"disabled"}>Выделить всё</button>`);
}
function edReplace(el,text){
  const a=el.selectionStart, b=el.selectionEnd;
  el.focus(); el.setRangeText(text,a,b,"end"); el.dispatchEvent(new Event("input",{bubbles:true}));
}
async function edAct(kind){
  const c=S.ctx, el=c&&c.el; hideMenu(); if(!el)return;
  const sel=el.value.slice(el.selectionStart,el.selectionEnd);
  if(kind==="ed-copy"){ if(sel)api("clip_set",sel).catch(()=>{}); }
  else if(kind==="ed-cut"){ if(sel){ api("clip_set",sel).catch(()=>{}); edReplace(el,""); } }
  else if(kind==="ed-del"){ if(sel)edReplace(el,""); }
  else if(kind==="ed-all"){ el.focus(); el.select(); }
  else if(kind==="ed-undo"){ el.focus(); document.execCommand("undo"); }
  else if(kind==="ed-paste"){
    let r=null; try{ r=await api("clip_get"); }catch(e){}
    let t=(r&&r.ok&&r.text)||""; if(!t)return;
    if(el.tagName==="INPUT")t=t.replace(/\r?\n/g," ");
    edReplace(el,t);
  }
}
async function setPin(c,flag){
  const wl=c.type==="wl", ref=wl?"w|"+c.key:c.id;
  let r; try{ r=await api("set_pin",ref,flag); }catch(e){ r=null; }
  if(!r||!r.ok){ toast("Не удалось изменить","err"); return; }
  S.freshPin=flag?ref:null;
  if(wl){ const e=S.wl.items.find(x=>x.key===c.key); if(e)e.pinned=r.pinned; flipRender($("#wlGrid"),renderWLGrid); }
  else { const it=S.byId.get(c.id); if(it)it.pinned=r.pinned; flipRender($("#grid"),renderGrid); }
  S.freshPin=null;
  toast(flag?"Закреплено":"Откреплено");
}
async function setHidden(id,flag){
  let r; try{ r=await api("set_hidden",id,flag); }catch(e){ r=null; }
  if(!r||!r.ok){ toast("Не удалось изменить","err"); return; }
  const it=S.byId.get(id); if(it)it.hidden=flag;
  if(S.current===id)closeModal();
  refreshGenres(); renderGrid(); renderStatus(); toast(flag?"Фильм скрыт":"Фильм снова виден");
}
async function posterFrom(kind,id,src){
  toast(src==="none"?"Удаляю постер…":src?"Ищу постер…":"Возвращаю постер по умолчанию…");
  let r; try{ r=await api("set_item_poster",kind,id,src); }catch(e){ r=null; }
  if(!r||!r.ok){ toast((r&&r.error)||"Не удалось сменить постер","err"); return; }
  pzApply([r.row]);
  if(kind==="key"){ const w=S.wl.items.find(x=>x.key===id); if(w&&$("#modalRoot").firstChild)wlOpen(id); }
  else if(S.current===id&&$("#modalRoot").firstChild)renderModal();
  toast(src==="none"?"Постер удалён":"Постер обновлён");
}
async function savePoster(url,name){
  let r=null; try{ r=await api("get_poster_data",url); }catch(e){}
  if(!r||!r.ok){ toast((r&&r.error)||"Не удалось загрузить постер","err"); return; }
  let b64=r.b64;
  if(r.mime!=="image/png"){
    try{
      const img=new Image(); img.src="data:"+r.mime+";base64,"+r.b64; await img.decode();
      const cv=document.createElement("canvas"); cv.width=img.naturalWidth; cv.height=img.naturalHeight;
      cv.getContext("2d").drawImage(img,0,0);
      b64=cv.toDataURL("image/png").split(",")[1];
    }catch(e){ toast("Не удалось сохранить постер","err"); return; }
  }
  let s=null; try{ s=await api("save_png",b64,name); }catch(e){}
  if(s&&s.ok&&s.path)toast("Постер сохранён");
  else if(s&&!s.ok)toast(s.error||"Не удалось сохранить постер","err");
}
function openPosterZoom(src){
  closePosterZoom(); if(!src)return;
  const d=document.createElement("div"); d.id="pzoom"; d.className="pzoom"; d.innerHTML=`<img src="${esc(src)}" referrerpolicy="no-referrer" alt="">`;
  d.addEventListener("click",closePosterZoom); document.body.appendChild(d);
}
function closePosterZoom(){ const d=$("#pzoom"); if(d)d.remove(); }
document.addEventListener("dblclick",e=>{
  const im=e.target.closest&&e.target.closest(".m-poster img"); if(!im)return;
  e.preventDefault(); openPosterZoom(im.currentSrc||im.src);
});
document.addEventListener("contextmenu",e=>{
  const tg=e.target, tn=tg.tagName||"";
  if(tn==="TEXTAREA"||(tn==="INPUT"&&TXT_TYPES.includes(tg.type||""))){ e.preventDefault(); editMenu(e.clientX,e.clientY,tg); return; }
  if(tn==="INPUT")return;
  e.preventDefault();
  const mw=tg.closest&&tg.closest(".m-wrap");
  if(mw&&(mw.dataset.purl||mw.dataset.pid)){
    const has=!!mw.dataset.purl;
    S.ctx={type:"poster",url:mw.dataset.purl,name:mw.dataset.pname||"poster",ptype:mw.dataset.ptype,pid:mw.dataset.pid};
    const srcs=[["kp","Кинопоиск"],["imdb","IMDb"],["lb","Letterboxd"]];
    const pm=mw.dataset.ptype==="key"?(S.wl.items.find(x=>x.key===mw.dataset.pid)||{}).meta:(S.byId.get(mw.dataset.pid)||{}).meta;
    const cur=(pm&&pm.poster_sel)||"";
    showMenu(e.clientX,e.clientY,(has?cb("ctx-save-poster","Сохранить постер как PNG…","download"):"")
      +(mw.dataset.pid?(has?`<div class="ctx-sep"></div>`:"")+`<div class="ctx-h"><small>Загрузить постер из источника</small></div>`+srcs.map(x=>`<button class="ctx-b${cur===x[0]?" sel":""}" data-act="ctx-poster-src" data-src="${x[0]}">${cur===x[0]?svg("check",16):`<span class="ctx-ic"></span>`}<span>${x[1]}</span></button>`).join("")+(has?`<div class="ctx-sep"></div>`+cb("ctx-poster-src","Удалить постер","trash","danger").replace('data-act="ctx-poster-src"','data-act="ctx-poster-src" data-src="none"'):""):"")); return;
  }
  const card=e.target.closest(".card");
  if(card&&card.closest("#grid")){ const it=S.byId.get(card.dataset.id); if(it)openItemMenu(e.clientX,e.clientY,it); return; }
  if(card&&card.closest("#wlGrid")){
    const w=S.wl.items.find(x=>x.key===card.dataset.key); if(!w)return; S.ctx={type:"wl",key:w.key};
    showMenu(e.clientX,e.clientY,`<div class="ctx-h"><b>${esc(metaTitle(w.meta,"Без названия"))}</b><small>Watchlist</small></div><div class="ctx-sep"></div>`+cb("ctx-wl-watch","Перенести в Watched","check")+(w.pinned?cb("ctx-unpin","Открепить","pin"):cb("ctx-pin","Закрепить","pin"))+`<div class="ctx-sep"></div>`+cb("ctx-copy","Копировать название и год","copy")+cb("ctx-wl-remove","Убрать из Watchlist","close"));
    return;
  }
  const ep=e.target.closest(".ep[data-path]");
  if(ep&&S.current){ const it=S.byId.get(S.current); if(it&&!it.ghost)openFileMenu(e.clientX,e.clientY,it,ep.dataset.path); return; }
  hideMenu();
});
window.addEventListener("blur",hideMenu);
$("#main").addEventListener("scroll",hideMenu,{passive:true});

async function setWatched(id,flag){
  let r; try{ r=await api("set_watched",id,flag); }catch(e){ r=null; }
  if(!r||!r.ok){ toast((r&&r.error)||"Не удалось изменить","err"); return; }
  const it=S.byId.get(id); const wasGhost=!!(it&&it.ghost);
  if(it){ if(wasGhost&&!flag){ S.items=S.items.filter(x=>x.id!==id); S.byId.delete(id); } else it.inWatched=flag; }
  if(S.current===id){ if(S.byId.has(id))renderModal(); else closeModal(); }
  refreshGenres(); renderGrid();
  toast(flag?"Перенесено в Watched":(wasGhost?"Убрано из Watched":"Возвращено в Not watched"));
}
function closeDlg(){ $("#dlgRoot").innerHTML=""; S.del=null; S.rm=null; }
function openLbUnlink(){
  $("#dlgRoot").innerHTML=`<div class="overlay dlg" data-act="dlg-overlay"><div class="modal sm dlg-s glass">
    <h2 class="t">Удалить профиль Letterboxd?</h2>
    <div class="dlg-p">Загрузка вотчлиста с этого профиля остановится. Фильмы, уже добавленные в вотчлист, останутся.</div>
    <div class="foot"><button class="btn" data-act="dlg-close">Отмена</button><button class="btn danger" data-act="lb-unlink-ok">Удалить</button></div></div></div>`;
}
function openDelete(c){
  const it=S.byId.get(c.id); if(!it)return;
  const all=filesOf(it), files=c.path?all.filter(f=>f.path===c.path):all; if(!files.length)return;
  S.del={id:c.id,paths:files.map(f=>f.path),whole:files.length===all.length};
  const tot=files.reduce((a,f)=>a+(f.size||0),0);
  const list=files.slice(0,6).map(f=>`<div class="del-f"><span>${esc(f.name)}</span><small>${fmtSize(f.size)}</small></div>`).join("")+(files.length>6?`<div class="hint">…и ещё ${files.length-6}</div>`:"");
  $("#dlgRoot").innerHTML=`<div class="overlay dlg" data-act="dlg-overlay"><div class="modal sm glass">
    <h2 class="t">Удалить с компьютера?</h2>
    <div class="hint" style="margin-bottom:12px">«${esc(titleOf(it))}» · файлов: ${files.length}${tot?" · "+fmtSize(tot):""}</div>
    <div class="del-list">${list}</div>
    <label class="radio"><input type="checkbox" id="d-perm"> Удалить навсегда, минуя Корзину</label>
    ${S.del.whole?`<label class="radio"><input type="checkbox" id="d-keep" ${it.inWatched?"checked":""}> Оставить запись в Watched</label>`:""}
    <div class="hint" id="d-hint" style="margin-top:6px">Файлы будут перемещены в Корзину Windows, их можно восстановить.</div>
    <div class="foot"><button class="btn" data-act="dlg-close">Отмена</button><button class="btn danger" id="d-ok" data-act="dlg-confirm">Удалить</button></div></div></div>`;
}
document.addEventListener("change",e=>{
  if(e.target.id==="d-perm"){ const h=$("#d-hint"); if(h)h.textContent=e.target.checked?"Файлы будут удалены безвозвратно.":"Файлы будут перемещены в Корзину Windows, их можно восстановить."; }
});
async function confirmDelete(){
  const d=S.del; if(!d)return;
  const perm=$("#d-perm").checked, ke=$("#d-keep"), keep=!!(ke&&ke.checked), btn=$("#d-ok");
  btn.disabled=true; btn.textContent="Удаляю…";
  let r; try{ r=await api("delete_files",d.id,d.paths,perm,keep); }catch(e){ r={ok:false,error:"Нет связи с приложением"}; }
  closeDlg();
  if(!r||!r.ok){ toast((r&&r.error)||"Не удалось удалить","err"); return; }
  const it=S.byId.get(d.id);
  if(r.item&&it){ Object.assign(it,r.item); }
  else { S.items=S.items.filter(x=>x.id!==d.id); S.byId.delete(d.id); if(r.ghost){ S.items.push(r.ghost); S.byId.set(r.ghost.id,r.ghost); } }
  if(S.current===d.id){ if(S.byId.has(d.id))renderModal(); else closeModal(); }
  refreshGenres(); renderGrid();
  const bad=(r.failed||[]);
  if(bad.length)toast(`Удалено: ${r.deleted}, не удалось: ${bad.length} (${bad[0].error})`,"err");
  else toast(`Удалено файлов: ${r.deleted}${perm?"":" — в Корзине"}`);
}

function applyZoom(v){
  v=Math.max(110,Math.min(320,Number(v)||176));
  document.documentElement.style.setProperty("--cw",v+"px");
  clearTimeout(pgT); pgT=setTimeout(()=>{ const g=$("#grid"); if(g)markPinGap(g); const w=$("#wlGrid"); if(w)markPinGap(w); },60);
  const z=$("#zoom"); if(z&&Number(z.value)!==v)z.value=v;
  return v;
}
let zoomT=null;
function saveZoom(v){ clearTimeout(zoomT); zoomT=setTimeout(()=>{ api("save_settings",{poster_size:String(v)}).then(r=>{ if(r&&r.ok)S.settings.poster_size=String(v); }).catch(()=>{}); },500); }
$("#zoom").addEventListener("input",e=>saveZoom(applyZoom(e.target.value)));
$("#zoom").addEventListener("dblclick",()=>saveZoom(applyZoom(176)));

document.querySelectorAll("[data-ico]").forEach(el=>{ el.innerHTML=svg(el.dataset.ico); el.style.display="inline-flex"; });
document.querySelectorAll(".sx").forEach(b=>{ if(!b.innerHTML)b.innerHTML=svg("close",14); });
let booted=false;
const splashT0=Date.now();
function splashOut(){ const s=$("#splash"); if(!s||s.classList.contains("out"))return; setTimeout(()=>{ s.classList.add("out"); setTimeout(()=>s.remove(),600); },Math.max(0,900-(Date.now()-splashT0))); }
(function(){ const s=$("#splash"), l=document.querySelector(".brand img"); if(s&&l)s.querySelector("img").src=l.src; setTimeout(splashOut,4000); })();
async function boot(){
  if(booted)return; booted=true;
  try{ S.settings=await api("get_settings"); }catch(e){ S.settings={}; }
  S.base=S.settings.poster_base||""; applyBg();
  if(["added","rating","yearDesc","yearAsc","title"].includes(S.settings.sort)){ S.sort=S.settings.sort; $("#sort").value=S.sort; }
  if(S.settings.lang==="en")setLang("en",true); else S.lang="ru";
  try{ const pr=await api("get_palettes"); if(pr&&pr.palettes){ S.pal=pr.palettes; Object.keys(S.pal).forEach(k=>S.palSaved.add(k)); } }catch(e){}
  applyZoom(S.settings.poster_size||176);
  S.welcome=!hasRoots();
  refreshGenres(); renderGrid(); renderBanner();
  api("lb_profile").then(r=>{ if(r&&r.ok){ S.lbProf=r.profile; renderLbBox(); setTimeout(lbProfRefresh,9000); } }).catch(()=>{});
  loadWL().then(()=>{ if(S.wl.items.some(x=>x.meta&&x.meta.lb_pending))wlLbFill(); });
  if(S.settings.lb_user)setTimeout(()=>wlSync(true),6000);
  if(hasRoots())await loadLibrary(false);
  splashOut();
  pzFill();
  if((S.settings.auto_update||"1")!=="0")setTimeout(()=>checkUpdate(false),3500);
}
["#typeSel","#genre","#sort"].forEach(s=>ddEnhance($(s)));
segInit();
(function(){
  const top=$("#top"), app=$("#app"); if(!top||!app)return;
  const bot=$("#status");
  const set=()=>{ app.style.setProperty("--topH",top.offsetHeight+"px"); if(bot)app.style.setProperty("--botH",bot.offsetHeight+"px"); };
  set(); if(window.ResizeObserver){ const ro=new ResizeObserver(set); ro.observe(top); if(bot)ro.observe(bot); }
  window.addEventListener("resize",set); setTimeout(set,400); setTimeout(set,1500);
})();
window.addEventListener("pywebviewready",boot);
if(window.pywebview&&window.pywebview.api)boot();
setTimeout(()=>{ if(!booted){ $("#grid").classList.add("hidden"); const em=$("#empty"); em.classList.remove("hidden"); em.innerHTML=`<div class="box glass"><h2>Нет связи с Python</h2><p>Запустите программу через main.py или kino.exe — страница работает только внутри окна приложения.</p></div>`; } },5000);
})();
</script>
</body>
</html>
'''


def _kino_hwnd(own):
    import ctypes
    u32 = ctypes.windll.user32
    buf = ctypes.create_unicode_buffer(64)
    pid = ctypes.c_ulong()
    h = 0
    while True:
        h = u32.FindWindowExW(None, h, None, WINDOW_TITLE)
        if not h:
            return 0
        u32.GetClassNameW(h, buf, 64)
        u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if buf.value.startswith("WindowsForms") and (pid.value == os.getpid()) == own:
            return h


def _single_instance():
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.CreateMutexW.restype = ctypes.c_void_p
        name = "Kino.single." + hashlib.md5(os.path.normcase(APP_DIR).encode("utf-8")).hexdigest()
        h = k32.CreateMutexW(None, False, name)
        wait = 8000 if "--after-update" in sys.argv else 0
        if k32.WaitForSingleObject(ctypes.c_void_p(h), wait) in (0, 0x80):
            return True
        if "--minimized" in sys.argv:
            return False
        w = _kino_hwnd(False)
        if not w:
            return True
        u32 = ctypes.windll.user32
        u32.ShowWindow(w, 9 if u32.IsIconic(w) else 5)
        u32.SetForegroundWindow(w)
        return False
    except Exception:
        return True


def _style_window(show=True):
    try:
        import ctypes
        time.sleep(0.4)
        hwnd = _kino_hwnd(True)
        if not hwnd:
            return
        u32 = ctypes.windll.user32
        if show:
            if u32.IsIconic(hwnd):
                u32.ShowWindow(hwnd, 9)
            u32.ShowWindow(hwnd, 5)
            u32.SetForegroundWindow(hwnd)
        ico = os.path.join(getattr(sys, "_MEIPASS", os.environ.get("KINO_RT") or os.path.dirname(os.path.abspath(__file__))), "icon.ico")
        if os.path.isfile(ico):
            u32.LoadImageW.restype = ctypes.c_void_p
            for kind, size in ((1, 32), (0, 16)):
                hic = u32.LoadImageW(None, ico, 1, size, size, 0x10)
                if hic:
                    u32.SendMessageW(ctypes.c_void_p(hwnd), 0x80, kind, ctypes.c_void_p(hic))
        dwm = ctypes.windll.dwmapi
        dark = ctypes.c_int(1)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
        caption = ctypes.c_int(0x00080808)
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), ctypes.sizeof(caption))
    except Exception:
        pass


def _make_shortcut(folder, target, args, icon, name="Kino"):
    if os.name != "nt":
        return False
    script = (
        "$d=[Environment]::GetFolderPath($env:KINO_LNK_F);"
        "$p=Join-Path $d ($env:KINO_LNK_N+'.lnk');"
        "if(Test-Path $p){exit 0};"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($p);"
        "$s.TargetPath=$env:KINO_LNK_T;$s.Arguments=$env:KINO_LNK_A;"
        "$s.WorkingDirectory=Split-Path $env:KINO_LNK_T;"
        "if($env:KINO_LNK_I){$s.IconLocation=$env:KINO_LNK_I};"
        "$s.Description='Kino';$s.Save()"
    )
    env = dict(os.environ, KINO_LNK_F=folder, KINO_LNK_N=name, KINO_LNK_T=target, KINO_LNK_A=args, KINO_LNK_I=icon)
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                           env=env, creationflags=0x08000000, timeout=30, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def _ui_ru():
    try:
        import ctypes
        return (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3ff) == 0x19
    except Exception:
        return False


INSTALL_LINKS = (
    "https://kinopoiskapiunofficial.tech",
    "https://www.omdbapi.com/apikey.aspx",
    "https://www.themoviedb.org/settings/api",
)

INSTALL_DATA_FILES = ("config.json", "metadata_cache.json", "watched.json", "watchlist.json", "palettes.json", "background.jpg")


class InstallApi:
    def __init__(self):
        self._window = None
        self.code = 4
        self.exe = os.environ.get("KINO_EXE") or ""
        self.exe_dir = os.path.dirname(self.exe) if self.exe else APP_DIR

    def info(self):
        local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return {"dir": os.path.join(local, "Programs", "Kino"), "ru": _ui_ru(), "version": APP_VERSION}

    def _launch(self, target, cwd):
        env = {k: v for k, v in os.environ.items() if not k.startswith("KINO_") and not k.startswith("PYTHON")}
        subprocess.Popen([target], cwd=cwd, env=env, creationflags=0x00000008 | 0x00000200, close_fds=True)

    def open_url(self, url):
        if url in INSTALL_LINKS:
            webbrowser.open(url)
        return {"ok": True}

    def _write_keys(self, d, keys, force=False):
        cfg_path = os.path.join(d, "config.json")
        cfg = {}
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            cfg = {}
        dirty = force
        for k in ("kp_api_key", "omdb_api_key", "tmdb_api_key"):
            v = str((keys or {}).get(k) or "").strip()
            if v:
                cfg[k] = v
                dirty = True
        if str((keys or {}).get("tmdb_api_key") or "").strip():
            cfg["fallback_source"] = "tmdb"
        return cfg, cfg_path, dirty

    def install(self, folder, desktop, keys=None):
        try:
            if not self.exe or not os.path.isfile(self.exe):
                return {"ok": False, "error": "exe"}
            d = os.path.normpath(str(folder or "").strip())
            if not d or not os.path.isabs(d):
                return {"ok": False, "error": "path"}
            os.makedirs(d, exist_ok=True)
            same = os.path.normcase(d) == os.path.normcase(os.path.normpath(self.exe_dir))
            target = self.exe if same else os.path.join(d, "Kino.exe")
            if not same:
                tmp = target + ".tmp"
                with open(self.exe, "rb") as fi, open(tmp, "wb") as fo:
                    while True:
                        chunk = fi.read(1 << 20)
                        if not chunk:
                            break
                        fo.write(chunk)
                os.replace(tmp, target)
                for n in INSTALL_DATA_FILES:
                    s, t = os.path.join(self.exe_dir, n), os.path.join(d, n)
                    if os.path.isfile(s) and not os.path.exists(t):
                        shutil.copy2(s, t)
            cfg, cfg_path, dirty = self._write_keys(d, keys, force=not desktop)
            if not desktop:
                cfg["shortcut_done"] = "1"
            if dirty:
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
            with open(os.path.join(d, "kino.installed"), "w") as f:
                f.write("1")
            if desktop:
                _make_shortcut("Desktop", target, "", target + ",0")
            _make_shortcut("Programs", target, "", target + ",0")
            self._launch(target, d)
            self.code = 0
            threading.Timer(0.6, lambda: self._window.destroy()).start()
            return {"ok": True}
        except Exception as e:
            _log("install error: %s\n%s" % (e, traceback.format_exc()))
            return {"ok": False, "error": str(e)}

    def portable(self, keys=None):
        try:
            cfg, cfg_path, dirty = self._write_keys(self.exe_dir, keys)
            if dirty:
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
            with open(os.path.join(self.exe_dir, "kino.portable"), "w") as f:
                f.write("1")
        except OSError:
            pass
        self.code = 3
        self._window.destroy()
        return {"ok": True}

    def close(self):
        self._window.destroy()


def run_installer():
    global webview
    import webview as _wv
    webview = _wv
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Kino.installer")
    except Exception:
        pass
    api = InstallApi()
    logo = re.search(r"data:image/png;base64,([A-Za-z0-9+/=]+)", HTML)
    info = api.info()
    html = (INSTALL_HTML.replace("%%LOGO%%", logo.group(1) if logo else "")
            .replace("%%DIR%%", html_escape(info["dir"])).replace("%%LANG%%", "ru" if info["ru"] else "en"))
    api._window = webview.create_window(WINDOW_TITLE, html=html, js_api=api, width=580, height=620,
                                        resizable=False, background_color="#070707")
    webview.start(_style_window, gui="edgechromium")
    return api.code


INSTALL_HTML = r'''<!doctype html><html><head><meta charset="utf-8"><title>Kino</title><style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--text:#f2f2f2;--muted:rgba(242,242,242,.55)}
html,body{height:100%}
body{font-family:"Segoe UI Variable Text","Segoe UI",system-ui,sans-serif;color:var(--text);background:#060606;overflow:hidden;-webkit-font-smoothing:antialiased;user-select:none;font-size:14px;
  background-image:radial-gradient(900px 500px at 15% -10%,rgba(255,255,255,.07),transparent 60%),radial-gradient(700px 420px at 100% 110%,rgba(120,150,170,.10),transparent 60%)}
.where{margin-top:2px;font-size:12.5px;color:var(--muted);line-height:1.5;word-break:break-all}
.where b{font-weight:500;color:var(--text);user-select:text}
.wrap{height:100%;padding:16px;display:flex;flex-direction:column}
.panel{flex:1;border-radius:22px;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.045);box-shadow:inset 0 1px 0 rgba(255,255,255,.12);padding:20px 26px 18px;display:flex;flex-direction:column;min-height:0}
.logo{height:84px;width:auto;align-self:flex-start;display:block;margin-bottom:14px;pointer-events:none;-webkit-user-drag:none}
h1{font-size:24px;font-weight:650;letter-spacing:-.01em;margin-bottom:4px}
p.sub{color:var(--muted);line-height:1.5;margin-bottom:12px;font-size:14px}
label.l{display:block;font-size:12px;color:var(--muted);margin-bottom:7px;letter-spacing:.04em;text-transform:uppercase}
.row{display:flex;gap:10px}
.inp{flex:1;min-width:0;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);color:var(--text);border-radius:14px;padding:9px 14px;font-size:13.5px;font-family:inherit;outline:none;user-select:text}
.btn{display:inline-flex;align-items:center;justify-content:center;padding:10px 18px;border-radius:14px;cursor:pointer;font-size:13.5px;font-weight:600;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.13);box-shadow:inset 0 1px 0 rgba(255,255,255,.14);transition:all .2s ease;white-space:nowrap;color:inherit;font-family:inherit}
.btn:hover{background:rgba(255,255,255,.15);transform:translateY(-1px)}
.btn:active{transform:none}
.btn:disabled{opacity:.45;pointer-events:none}
.btn.primary{background:linear-gradient(180deg,#fff,#d9d9d9);border-color:rgba(255,255,255,.7);color:#0a0a0a;box-shadow:inset 0 1px 0 #fff,0 8px 28px rgba(255,255,255,.14)}
.btn.primary:hover{background:linear-gradient(180deg,#fff,#e8e8e8);box-shadow:inset 0 1px 0 #fff,0 12px 36px rgba(255,255,255,.22)}
.chk{display:flex;align-items:center;gap:10px;margin-top:10px;cursor:pointer;color:var(--text)}
.chk input{accent-color:#f2f2f2;width:16px;height:16px}
.keys{margin-top:12px}
.krow{margin-top:8px}
.kh{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:5px;font-size:13px}
.kh a{color:var(--muted);text-decoration:underline;cursor:pointer;font-size:12px}
.kh a:hover{color:var(--text)}
.inp.k{width:100%;user-select:text}
.tiny{font-size:12px;color:var(--muted);margin-top:8px}
.msg{min-height:18px;margin-top:6px;font-size:13px;color:#ff9b9b}
.msg.ok{color:var(--muted)}
.sp{flex:1}
.foot{display:flex;justify-content:space-between;align-items:center;gap:12px}
.link{background:none;border:0;color:var(--muted);cursor:pointer;font-size:13px;font-family:inherit;padding:8px 4px}
.link:hover{color:var(--text)}
.link:disabled{opacity:.4;pointer-events:none}
.panel{border-radius:18px;border:1px solid rgba(255,255,255,.08);background:rgba(20,20,22,.94);box-shadow:inset 0 1px 0 rgba(255,255,255,.08),0 12px 32px rgba(0,0,0,.4);padding:24px 28px 20px;overflow:hidden}
.body{flex:1;min-height:0;overflow:auto;padding-right:4px}
.logo{height:64px;margin-bottom:16px}
h1{font-size:24px;font-weight:700;letter-spacing:0}
p.sub{font-size:14px;line-height:1.55;margin-bottom:16px}
.where{font-size:13px;margin-top:0}
.inp{border-radius:12px;padding:10px 14px;transition:background-color .16s cubic-bezier(.22,1,.36,1),border-color .16s cubic-bezier(.22,1,.36,1)}
.inp:focus{border-color:rgba(255,255,255,.5);box-shadow:0 0 0 3px rgba(255,255,255,.1);background-color:rgba(255,255,255,.08)}
.btn{height:40px;padding:0 20px;border-radius:12px;box-shadow:inset 0 1px 0 rgba(255,255,255,.08);transition:background-color .22s ease,border-color .22s ease,transform .22s ease,box-shadow .22s ease}
.btn:hover{background:rgba(255,255,255,.15);border-color:rgba(255,255,255,.18);transform:translateY(-1px);box-shadow:inset 0 1px 0 rgba(255,255,255,.26),0 8px 22px rgba(0,0,0,.4)}
.btn:active{transform:translateY(0) scale(.98)}
.btn.primary{background:#ededed;border-color:#ededed;color:#0a0a0a;box-shadow:inset 0 1px 0 rgba(255,255,255,.6)}
.btn.primary:hover{background:#fff;border-color:#fff;box-shadow:inset 0 1px 0 #fff,0 10px 28px rgba(255,255,255,.18)}
.chk{flex-direction:row-reverse;justify-content:space-between;gap:16px;margin-top:8px;padding:12px 0;border-top:1px solid rgba(255,255,255,.08);border-bottom:1px solid rgba(255,255,255,.08)}
.chk input{-webkit-appearance:none;appearance:none;width:38px;height:22px;border-radius:11px;background:rgba(255,255,255,.14);position:relative;cursor:pointer;flex:none;margin:0;transition:background-color .16s cubic-bezier(.22,1,.36,1)}
.chk input::after{content:"";position:absolute;top:3px;left:3px;width:16px;height:16px;border-radius:50%;background:#bdbdbd;transition:transform .16s cubic-bezier(.22,1,.36,1),background-color .16s cubic-bezier(.22,1,.36,1)}
.chk input:checked{background:#ededed}
.chk input:checked::after{transform:translateX(16px);background:#141415}
.chk input:focus-visible{outline:2px solid rgba(255,255,255,.6);outline-offset:2px}
.keys{margin-top:0}
.ktog{display:flex;align-items:center;justify-content:space-between;width:100%;padding:14px 0;background:none;border:0;border-bottom:1px solid rgba(255,255,255,.08);color:var(--text);font-size:13.5px;font-weight:600;cursor:pointer;font-family:inherit;text-align:left}
.ktog svg{flex:none;opacity:.7;transition:transform .2s cubic-bezier(.22,1,.36,1)}
.ktog.open svg{transform:rotate(180deg)}
.kbody{display:none;padding-top:8px}
.kbody.open{display:block;animation:kfade .25s cubic-bezier(.22,1,.36,1)}
@keyframes kfade{from{opacity:0}}
.krow{margin-top:12px}
.tiny{font-size:12.5px;line-height:1.5}
.foot{padding-top:14px}
</style></head><body><div class="wrap"><div class="panel"><div class="body">
<img class="logo" src="data:image/png;base64,%%LOGO%%" alt="Kino" draggable="false">
<h1 id="t"></h1><p class="sub" id="s"></p>
<div class="where"><span id="fl"></span> <b id="dir">%%DIR%%</b></div>
<label class="chk"><input type="checkbox" id="sc" checked><span id="scT"></span></label>
<div class="keys"><button type="button" class="ktog" id="kts"><span id="kt"></span><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg></button><div class="kbody" id="kb">
<div class="krow"><div class="kh"><span>Кинопоиск Unofficial</span><a data-u="https://kinopoiskapiunofficial.tech" id="l1"></a></div><input class="inp k" id="k1" autocomplete="off" spellcheck="false"></div>
<div class="krow"><div class="kh"><span>OMDb (IMDb)</span><a data-u="https://www.omdbapi.com/apikey.aspx" id="l2"></a></div><input class="inp k" id="k2" autocomplete="off" spellcheck="false"></div>
<div class="krow"><div class="kh"><span>TMDB</span><a data-u="https://www.themoviedb.org/settings/api" id="l3"></a></div><input class="inp k" id="k3" autocomplete="off" spellcheck="false"></div>
<div class="tiny" id="kn"></div></div></div>
<div class="msg" id="msg"></div></div>
<div class="foot"><span></span><button class="btn primary" id="go"></button></div>
</div></div><script>
const $=s=>document.querySelector(s);
const L={ru:{nb:"Нет связи с Python — установка может не работать",kt:"API-ключи (необязательно)",lk:"Получить ключ",kn:"Без ключей Kino ищет данные медленнее. Ключи можно добавить позже в настройках.",t:"Установка Kino",s:"Локальный каталог ваших фильмов и сериалов: постеры, описания, рейтинги, список просмотренного и вотчлист.",fl:"Будет установлено в",sc:"Ярлык на рабочем столе",po:"Запустить без установки",go:"Установить",busy:"Устанавливаю…",done:"Готово, запускаю Kino…",err:"Не удалось установить: "},
 en:{nb:"No connection to the Python backend — installation may not work",kt:"API keys (optional)",lk:"Get a key",kn:"Without keys Kino searches slower. You can add keys later in settings.",t:"Install Kino",s:"A local catalog of your movies and series: posters, descriptions, ratings, a watched list and a watchlist.",fl:"Will be installed to",sc:"Desktop shortcut",po:"Run without installing",go:"Install",busy:"Installing…",done:"Done, starting Kino…",err:"Installation failed: "}};
let T="%%LANG%%"==="ru"?L.ru:L.en;
function apply(){
  $("#t").textContent=T.t; $("#s").textContent=T.s; $("#fl").textContent=T.fl;
  $("#kt").textContent=T.kt; $("#kn").textContent=T.kn; ["#l1","#l2","#l3"].forEach(s=>$(s).textContent=T.lk);
  $("#scT").textContent=T.sc; $("#go").textContent=T.go;
}
apply();
let started=false;
async function init(){
  if(started||!(window.pywebview&&pywebview.api&&pywebview.api.info))return;
  started=true;
  try{
    await pywebview.api.info();
  }catch(e){ started=false; }
}
function setMsg(t,ok){ $("#msg").className=ok?"msg ok":"msg"; $("#msg").textContent=t; }
function lock(v){ ["#go"].forEach(s=>$(s).disabled=v); document.querySelectorAll(".k").forEach(i=>i.disabled=v); }
const keys=()=>({kp_api_key:$("#k1").value,omdb_api_key:$("#k2").value,tmdb_api_key:$("#k3").value});
document.querySelectorAll(".kh a").forEach(a=>a.onclick=()=>pywebview.api.open_url(a.dataset.u));
$("#kts").onclick=()=>{ const o=$("#kb").classList.toggle("open"); $("#kts").classList.toggle("open",o); };
$("#go").onclick=async()=>{
  lock(true); $("#msg").className="msg ok"; $("#msg").textContent=T.busy;
  const r=await pywebview.api.install($("#dir").textContent,$("#sc").checked,keys());
  if(r&&r.ok){ $("#msg").textContent=T.done; return; }
  lock(false); $("#msg").className="msg"; $("#msg").textContent=T.err+((r&&r.error)||"");
};
window.addEventListener("pywebviewready",init);
setTimeout(()=>{ if(!started)setMsg(T.nb,false); },4000);
const iv=setInterval(()=>{ if(started)clearInterval(iv); else init(); },200);
init();
</script></body></html>'''


TV_UDP_PORT = 8766

TV_WEB = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Kino</title>
<style>body{margin:0;background:#070707;color:#eee;font:15px system-ui,sans-serif}header{padding:14px 18px;font-weight:700;font-size:18px}
#g{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:14px;padding:0 18px 30px}
.c{cursor:pointer;border-radius:14px;overflow:hidden;background:#151515;aspect-ratio:2/3;position:relative}.c img{width:100%;height:100%;object-fit:cover;display:block}
.c b{position:absolute;left:0;right:0;bottom:0;padding:22px 8px 8px;background:linear-gradient(transparent,#000);font-size:13px}
#p{display:none;position:fixed;inset:0;background:#000d;z-index:5;overflow:auto;padding:20px}video{width:100%;max-height:70vh;background:#000}
button,input{font:inherit;padding:9px 14px;border-radius:10px;border:1px solid #444;background:#222;color:#fff}.f{display:block;margin:6px 0;width:100%;text-align:left}
#l{max-width:340px;margin:20vh auto;text-align:center}</style></head><body>
<div id="l"><h2>Kino</h2><p>PIN from Kino settings</p><input id="pin" inputmode="numeric" maxlength="6"> <button onclick="pair()">Connect</button><p id="e"></p></div>
<div id="m" style="display:none"><header>Kino</header><div id="g"></div></div><div id="p"></div>
<script>
let T=localStorage.kt||"",D=[];
fetch("/api/ping").then(r=>r.json()).then(j=>{if(j.pin===false&&!T)pair()});
const q=(u,o)=>fetch(u,Object.assign({headers:{"X-Kino-Token":T}},o)).then(r=>r.json());
async function pair(){const r=await fetch("/api/pair",{method:"POST",body:JSON.stringify({pin:pin.value,device:"Browser"})});const j=await r.json();
if(j.token){T=j.token;localStorage.kt=T;go()}else e.textContent=j.error||"Wrong PIN"}
async function go(){const j=await q("/api/library");if(!j.ok){localStorage.kt="";T="";return}
l.style.display="none";m.style.display="block";D=j.items.filter(i=>!i.hidden);
g.innerHTML=D.map((i,k)=>`<div class="c" onclick="op(${k})"><img src="${i.localPoster?"/api/poster/"+i.id+"?t="+T:(i.meta&&i.meta.poster)||""}"><b>${i.title}</b></div>`).join("")}
function op(k){const i=D[k];const fs=i.files.concat(...i.seasons.map(s=>s.episodes));
p.style.display="block";p.innerHTML=`<button onclick="p.style.display='none';p.innerHTML=''">Close</button><h3>${i.title}</h3><video id="v" controls autoplay></video>`+
fs.map(f=>`<button class="f" onclick="v.src='/api/stream/${i.id}/${f.fid}?t=${T}';v.play()">${f.name}</button>`).join("")}
if(T)go();
</script></body></html>'''


def _rate_missing(m):
    return bool(m and not m.get("miss") and m.get("imdbId") and m.get("ratingImdb") is None
                and m.get("ratingKp") is None)


def _local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def _flat_paths(view):
    out = [f["path"] for f in view.get("files") or []]
    for s in view.get("seasons") or []:
        out += [e["path"] for e in s["episodes"]]
    return out


SUB_EXT = {".srt", ".ass", ".ssa", ".vtt"}
SUB_DIRS = {"subs", "sub", "subtitles", "subtitle", "субтитры"}


def _find_subs(path):
    d, name = os.path.split(path)
    stem = os.path.splitext(name)[0].lower()
    out = []
    dirs = [d]
    try:
        for e in os.listdir(d):
            if e.lower() in SUB_DIRS and os.path.isdir(os.path.join(d, e)):
                dirs.append(os.path.join(d, e))
    except OSError:
        return out
    for dd in dirs:
        try:
            names = sorted(os.listdir(dd))
        except OSError:
            continue
        for e in names:
            base, ext = os.path.splitext(e)
            if ext.lower() in SUB_EXT and base.lower().startswith(stem):
                label = base[len(stem):].strip(" ._-") or os.path.splitext(e)[1].lstrip(".").upper()
                out.append((os.path.join(dd, e), label))
    return out[:12]


def _tv_public(view):
    v = dict(view)
    n = [0]

    def strip(f):
        g = {k: x for k, x in f.items() if k != "path"}
        g["fid"] = n[0]
        n[0] += 1
        subs = _find_subs(f["path"])
        if subs:
            g["subs"] = [{"sid": i, "name": nm} for i, (_, nm) in enumerate(subs)]
        return g

    v["files"] = [strip(f) for f in view.get("files") or []]
    v["seasons"] = [dict(s, episodes=[strip(e) for e in s["episodes"]]) for s in view.get("seasons") or []]
    v["localPoster"] = bool(v.pop("hasLocalPoster", False))
    return v


class TvServer:
    def __init__(self, api, port):
        self.api = api
        self.port = port
        self.httpd = None
        self.fails = {}
        self.stopped = False

    def start(self):
        api = self.api
        srv = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _head(self, code, ctype, length, extra=None):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(length))
                self.send_header("Access-Control-Allow-Origin", "*")
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()

            def _json(self, code, obj):
                body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self._head(code, "application/json; charset=utf-8", len(body), {"Cache-Control": "no-store"})
                if self.command != "HEAD":
                    self.wfile.write(body)

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                if n < 0 or n > 8192:
                    return None
                try:
                    return json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return None

            def do_OPTIONS(self):
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "X-Kino-Token, Content-Type, Range")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, HEAD, OPTIONS")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_HEAD(self):
                self._route("GET")

            def do_GET(self):
                self._route("GET")

            def do_POST(self):
                self._route("POST")

            def _route(self, method):
                try:
                    u = urlparse(self.path)
                    q = parse_qs(u.query)
                    p = u.path
                    if p == "/":
                        body = TV_WEB.encode("utf-8")
                        self._head(200, "text/html; charset=utf-8", len(body))
                        if self.command != "HEAD":
                            self.wfile.write(body)
                        return
                    if p == "/api/ping":
                        return self._json(200, {"ok": True, "app": "kino", "name": socket.gethostname(),
                                                "version": APP_VERSION, "lang": api._cfg.get("lang"),
                                                "pin": api._cfg.get("srv_nopin") != "1"})
                    if method == "POST" and p == "/api/pair":
                        return self._pair()
                    t = self.headers.get("X-Kino-Token") or (q.get("t") or [""])[0]
                    if not api._tv_token_ok(t):
                        return self._json(401, {"ok": False, "error": "unauthorized"})
                    if method == "GET":
                        if p == "/api/library":
                            return self._json(200, self._library())
                        if p == "/api/watchlist":
                            return self._json(200, api.wl_list())
                        m = re.fullmatch(r"/api/stream/([^/]+)/(\d+)", p)
                        if m:
                            return self._stream(m.group(1), int(m.group(2)))
                        m = re.fullmatch(r"/api/poster/([^/]+)", p)
                        if m:
                            return self._poster(m.group(1))
                        m = re.fullmatch(r"/api/sub/([^/]+)/(\d+)/(\d+)(?:\.\w+)?", p)
                        if m:
                            return self._sub(m.group(1), int(m.group(2)), int(m.group(3)))
                    if method == "POST":
                        d = self._body()
                        if d is None:
                            return self._json(400, {"ok": False, "error": "bad request"})
                        flag = bool(d.get("flag"))
                        if p == "/api/watched":
                            return self._json(200, api.set_watched(str(d.get("id") or ""), flag))
                        if p == "/api/pin":
                            return self._json(200, api.set_pin(str(d.get("ref") or ""), flag))
                        if p == "/api/hidden":
                            return self._json(200, api.set_hidden(str(d.get("id") or ""), flag))
                        if p == "/api/progress":
                            return self._json(200, api.tv_progress(str(d.get("id") or ""), d.get("fid"), d.get("pos"), d.get("dur")))
                        if p == "/api/progress/clear":
                            return self._json(200, api.tv_progress_clear(str(d.get("id") or "")))
                        if p == "/api/refresh":
                            api.scan()
                            return self._json(200, self._library())
                    self._json(404, {"ok": False, "error": "not found"})
                except (BrokenPipeError, ConnectionError, OSError):
                    pass
                except Exception as e:
                    _log("tv server: %s" % e)
                    try:
                        self._json(500, {"ok": False, "error": "server error"})
                    except Exception:
                        pass

            def _pair(self):
                ip = self.client_address[0]
                now = time.time()
                f = [x for x in srv.fails.get(ip, []) if now - x < 600]
                if len(f) >= 5:
                    return self._json(429, {"ok": False, "error": "too many attempts"})
                d = self._body() or {}
                if api._cfg.get("srv_nopin") != "1" and not hmac.compare_digest(str(d.get("pin") or ""), api._srv_pin()):
                    f.append(now)
                    srv.fails[ip] = f
                    return self._json(403, {"ok": False, "error": "wrong pin"})
                srv.fails.pop(ip, None)
                token = api._tv_add_token(str(d.get("device") or "TV")[:40])
                self._json(200, {"ok": True, "token": token, "name": socket.gethostname()})

            def _library(self):
                api._srv_ensure_scan()
                items = [_tv_public(api._view(it)) for it in list(api._items.values())]
                prog = api._progress_all()
                for v in items:
                    best = None
                    for f in list(v["files"]) + [e for sn in v["seasons"] for e in sn["episodes"]]:
                        e = prog.get("%s|%d" % (v["id"], f["fid"]))
                        if e and not e.get("done") and e.get("pos", 0) > 5000:
                            f["pos"] = e["pos"]
                            f["dur"] = e.get("dur", 0)
                            if best is None or e["ts"] > best["ts"]:
                                best = {"fid": f["fid"], "pos": e["pos"], "dur": e.get("dur", 0), "ts": e["ts"]}
                    if best and not v.get("inWatched"):
                        v["resume"] = best
                ghosts = [_tv_public(api._ghost_view(k, e)) for k, e in list(api._wd.items()) if k not in api._items]
                return {"ok": True, "lang": api._cfg.get("lang"), "items": items, "ghosts": ghosts}

            def _poster(self, item_id):
                it = api._items.get(item_id)
                p = it.get("poster") if it else None
                if not p or not os.path.isfile(p) or os.path.getsize(p) > 8 * 1024 * 1024:
                    return self._json(404, {"ok": False})
                with open(p, "rb") as fh:
                    data = fh.read()
                mime = "image/png" if p.lower().endswith(".png") else "image/jpeg"
                self._head(200, mime, len(data), {"Cache-Control": "max-age=86400"})
                if self.command != "HEAD":
                    self.wfile.write(data)

            def _sub(self, item_id, fid, sid):
                it = api._items.get(item_id)
                paths = _flat_paths(api._view(it)) if it else []
                if fid >= len(paths):
                    return self._json(404, {"ok": False})
                subs = _find_subs(paths[fid])
                roots = api._cfg.get("root_folders") or []
                if sid >= len(subs):
                    return self._json(404, {"ok": False})
                sp = subs[sid][0]
                if not os.path.isfile(sp) or os.path.getsize(sp) > 5 * 1024 * 1024 or not any(_is_inside(r, sp) for r in roots):
                    return self._json(404, {"ok": False})
                with open(sp, "rb") as fh:
                    raw = fh.read()
                encs = ["utf-8-sig"]
                if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
                    encs = ["utf-16"]
                text = None
                for enc in encs + ["cp1251"]:
                    try:
                        text = raw.decode(enc)
                        break
                    except UnicodeError:
                        text = None
                if text is None:
                    text = raw.decode("latin-1")
                data = text.encode("utf-8")
                self._head(200, "text/plain; charset=utf-8", len(data))
                if self.command != "HEAD":
                    self.wfile.write(data)

            def _stream(self, item_id, fid):
                it = api._items.get(item_id)
                paths = _flat_paths(api._view(it)) if it else []
                if fid >= len(paths):
                    return self._json(404, {"ok": False})
                path = paths[fid]
                roots = api._cfg.get("root_folders") or []
                if not os.path.isfile(path) or not any(_is_inside(r, path) for r in roots):
                    return self._json(404, {"ok": False})
                size = os.path.getsize(path)
                ext = os.path.splitext(path)[1].lower()
                ctype = {".mkv": "video/x-matroska", ".mp4": "video/mp4", ".m4v": "video/mp4", ".avi": "video/x-msvideo",
                         ".webm": "video/webm", ".mov": "video/quicktime", ".ts": "video/mp2t"}.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream"
                start, end, code = 0, size - 1, 200
                m = re.fullmatch(r"bytes=(\d*)-(\d*)", (self.headers.get("Range") or "").strip())
                if m and (m.group(1) or m.group(2)):
                    if m.group(1):
                        start = int(m.group(1))
                        end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
                    else:
                        start = max(0, size - int(m.group(2)))
                    if start > end or start >= size:
                        return self._head(416, "text/plain", 0, {"Content-Range": "bytes */%d" % size})
                    code = 206
                length = end - start + 1
                extra = {"Accept-Ranges": "bytes"}
                if code == 206:
                    extra["Content-Range"] = "bytes %d-%d/%d" % (start, end, size)
                self._head(code, ctype, length, extra)
                if self.command == "HEAD":
                    return
                with open(path, "rb") as fh:
                    fh.seek(start)
                    left = length
                    while left > 0:
                        chunk = fh.read(min(262144, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)

        try:
            class Quiet(ThreadingHTTPServer):
                def handle_error(self, request, client_address):
                    pass

            self.httpd = Quiet(("0.0.0.0", self.port), H)
        except OSError as e:
            return "Порт %d занят или недоступен: %s" % (self.port, e)
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        threading.Thread(target=self._udp_loop, daemon=True).start()
        return ""

    def _udp_loop(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", TV_UDP_PORT))
            s.settimeout(1.0)
        except OSError:
            return
        while not self.stopped:
            try:
                data, addr = s.recvfrom(256)
            except socket.timeout:
                continue
            except OSError:
                break
            if data.strip() == b"KINO?":
                try:
                    s.sendto(json.dumps({"app": "kino", "name": socket.gethostname(), "port": self.port}).encode("utf-8"), addr)
                except OSError:
                    pass
        s.close()

    def stop(self):
        self.stopped = True
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass


class _Tray:
    def __init__(self, api, window):
        self.api = api
        self.window = window
        self.icon = None
        self.quitting = False
        self.ready = False
        threading.Thread(target=self._ensure_deps, daemon=True).start()

    def _ensure_deps(self):
        try:
            import pystray
            from PIL import Image
            self.ready = True
            return
        except Exception:
            pass
        try:
            import subprocess
            import importlib
            exe = sys.executable
            if os.path.basename(exe).lower() == "pythonw.exe":
                cand = os.path.join(os.path.dirname(exe), "python.exe")
                if os.path.isfile(cand):
                    exe = cand
            flags = 0x08000000 if os.name == "nt" else 0
            r = subprocess.run(
                [exe, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "pystray", "pillow"],
                capture_output=True, text=True, timeout=300, creationflags=flags,
            )
            _log("tray deps install: rc=%s %s" % (r.returncode, (r.stdout + r.stderr)[-300:].replace("\n", " ")))
            importlib.invalidate_caches()
            import pystray
            from PIL import Image
            self.ready = True
        except Exception as e:
            _log("tray deps: %s" % e)

    def _image(self):
        from PIL import Image
        ico = os.path.join(getattr(sys, "_MEIPASS", os.environ.get("KINO_RT") or os.path.dirname(os.path.abspath(__file__))), "icon.ico")
        if os.path.isfile(ico):
            try:
                return Image.open(ico).convert("RGBA")
            except Exception:
                pass
        return Image.new("RGBA", (64, 64), (230, 230, 230, 255))

    def _promote(self):
        try:
            import winreg
            exe = os.path.normcase(os.path.abspath(sys.executable))
            for _ in range(8):
                time.sleep(1.0)
                done = False
                try:
                    root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\NotifyIconSettings", 0, winreg.KEY_READ)
                except OSError:
                    return
                with root:
                    i = 0
                    while True:
                        try:
                            name = winreg.EnumKey(root, i)
                        except OSError:
                            break
                        i += 1
                        try:
                            with winreg.OpenKey(root, name, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
                                path = os.path.normcase(os.path.abspath(winreg.QueryValueEx(k, "ExecutablePath")[0]))
                                if path == exe:
                                    winreg.SetValueEx(k, "IsPromoted", 0, winreg.REG_DWORD, 1)
                                    done = True
                        except OSError:
                            continue
                if done:
                    return
        except Exception as e:
            _log("tray promote: %s" % e)

    def _show(self, *_):
        try:
            self.window.show()
            self.window.restore()
        except Exception:
            pass

    def _quit(self, *_):
        self.quitting = True
        try:
            if self.icon:
                self.icon.stop()
        except Exception:
            pass
        try:
            self.window.destroy()
        except Exception:
            pass

    def hide(self):
        try:
            import pystray
        except Exception:
            return False
        if self.icon is None:
            try:
                menu = pystray.Menu(
                    pystray.MenuItem("Открыть Kino" if self.api._cfg.get("lang") != "en" else "Open Kino", self._show, default=True),
                    pystray.MenuItem("Выход" if self.api._cfg.get("lang") != "en" else "Exit", self._quit),
                )
                self.icon = pystray.Icon("Kino", self._image(), WINDOW_TITLE, menu)
                self.icon.run_detached()
                threading.Thread(target=self._promote, daemon=True).start()
            except Exception as e:
                _log("tray: %s" % e)
                self.icon = None
                return False
        try:
            self.window.hide()
        except Exception:
            return False
        return True

    def on_closing(self):
        if self.quitting or self.api._cfg.get("tray_close") != "1":
            return True
        return not self.hide()


def _startup(tray, minimized):
    if not minimized:
        _style_window()
        return
    _style_window(False)
    for _ in range(40):
        if tray.ready:
            break
        time.sleep(0.5)
    if not (tray.ready and tray.hide()):
        tray._show()


def main():
    global webview
    import webview as _wv
    webview = _wv

    os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
                          "--renderer-process-limit=1 --disable-background-networking --disable-component-update "
                          "--disable-features=Translate,OptimizationHints,msSmartScreenProtection "
                          "--js-flags=--max-old-space-size=256")
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Kino.catalog.app")
    except Exception:
        pass
    if not _single_instance():
        return
    api = Api()
    threading.Thread(target=api._autostart_apply, daemon=True).start()
    threading.Thread(target=api._ensure_shortcut, daemon=True).start()
    minimized = "--minimized" in sys.argv
    api._srv_apply()
    ww, wh, wx, wy = 1400, 880, None, None
    try:
        import ctypes
        from ctypes import wintypes
        rc = wintypes.RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rc), 0)
        sc = (ctypes.windll.user32.GetDpiForSystem() or 96) / 96.0
        aw, ah = (rc.right - rc.left) / sc, (rc.bottom - rc.top) / sc
        ww, wh = int(min(ww, aw)), int(min(wh, ah))
        wx, wy = int(rc.left / sc + (aw - ww) / 2), int(rc.top / sc + (ah - wh) / 2)
    except Exception:
        pass
    window = webview.create_window(
        WINDOW_TITLE, html=HTML, js_api=api, x=wx, y=wy, hidden=minimized,
        width=ww, height=wh, min_size=(1000, 640), background_color="#070707",
    )
    api._window = window
    tray = _Tray(api, window)
    try:
        window.events.closing += tray.on_closing
    except Exception as e:
        _log("tray hook: %s" % e)
    try:
        webview.start(_startup, (tray, minimized), gui="edgechromium")
        api._flush_cache()
    except Exception as e:
        _log("start error: %s\n%s" % (e, traceback.format_exc()))
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                "Не удалось запустить окно (нужен Microsoft Edge WebView2 Runtime).\n"
                "Скачайте: https://developer.microsoft.com/microsoft-edge/webview2/\n\n" + str(e),
                WINDOW_TITLE, 0x10)
        except Exception:
            pass


if __name__ == "__main__":
    if "--install" in sys.argv:
        sys.exit(run_installer())
    main()
