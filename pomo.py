# -*- coding: utf-8 -*-
"""
pomo.mom  4K原盘免费下载  TVBox / FongMi / WebHTV(默影视) Python Spider (type=3)

站点说明（逆向要点）：
  1) emlog 内核 + 自写 4K 模板，非 MacCMS，无采集接口。
  2) 分类：/  /huayurm /jiating /donghuadadiany /lengmenjiapian /paihangbang /sort/12 /dianshiju
     分页：/page/{n}  与  /{slug}/page/{n}
  3) 详情：/{数字id}   卡片 <a href="{HOST}/{id}" ...> 内含 img/h3/别名/类型/tag(IMDB/HDR)
  4) 播放：详情页自带插件播放页  /?plugin=plyr_player&gid={id}
       - 页内 const route1Data / route2Data = ["名称$m3u8", ...]   （站方自有源，部分片子没有）
       - 没有自有源时页面走「自动搜索」，调用
         /content/plugins/plyr_player/api.php?type=auto_search&wd={片名}
         返回 {"西瓜":[{name,play_url,...}], "暴风":[...], "天堂":[...], "非凡":[...]}
         play_url 形如  名称$地址#名称$地址  或  名称$地址$$$名称$m3u8
       - 另有 type=parse&url= 二次解析（本环境实测会 302 到版权提示片，只作兜底）
  5) 详情页另有磁力/BT 下载区  data-url="magnet:?xt=..."（作为下载线路）
"""
import re
import json
import time
import base64
import gzip
import io
import threading
import urllib.request
import urllib.parse
import urllib.error
import http.cookiejar

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass


HOST = "https://pomo.mom"
UA = ("Mozilla/5.0 (Linux; Android 13; M2102J2SC) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
PLUG = HOST + "/?plugin=plyr_player&gid="
API = HOST + "/content/plugins/plyr_player/api.php"

CATS = [
    ("\u9996\u9875\u6700\u65b0", "/"),
    ("\u534e\u8bed\u70ed\u95e8", "/huayurm"),
    ("\u5bb6\u5ead\u5f71\u9662", "/jiating"),
    ("\u52a8\u753b\u5927\u7535\u5f71", "/donghuadadiany"),
    ("\u51b7\u95e8\u4f73\u7247", "/lengmenjiapian"),
    ("TOP250", "/paihangbang"),
    ("\u84dd\u5149\u539f\u76d8", "/sort/12"),
    ("\u5267\u96c6", "/dianshiju"),
]

_CACHE = {}
_LOCK = threading.Lock()
_CJ = http.cookiejar.CookieJar()
_OP = None

RE_CARD = re.compile(r'<a\s+href="https://pomo\.mom/(\d+)"[^>]*>(.*?)</a>', re.S)
RE_IMG = re.compile(r'<img[^>]+src="([^"]+)"', re.I)
RE_H3 = re.compile(r'<h3[^>]*>(.*?)</h3>', re.S)
RE_TAG = re.compile(r'<div class="tag">(.*?)</div>', re.S)
RE_TAGTXT = re.compile(r'<[^>]+>')
RE_PAGE = re.compile(r'page/(\d+)')
RE_ROUTE = re.compile(r'const\s+route(\d+)Data\s*=\s*(\[.*?\])\s*;', re.S)
RE_MAG = re.compile(r'data-url="(magnet:[^"]+)"')
RE_QUARK = re.compile(r'href="(https://pan\.quark\.cn/s/[^"]+)"')
RE_M3U8 = re.compile(r'https?:\\?/\\?/[^"\'\\\s]+?\.m3u8[^"\'\\\s]*')


def _op():
    global _OP
    if _OP is None:
        _OP = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_CJ))
        _OP.addheaders = [
            ("User-Agent", UA),
            ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
            ("Accept-Language", "zh-CN,zh;q=0.9"),
            ("Accept-Encoding", "gzip, deflate"),
        ]
    return _OP


def _decomp(raw, enc):
    try:
        if "gzip" in (enc or "") or raw[:2] == b"\x1f\x8b":
            return gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        if "deflate" in (enc or ""):
            try:
                import zlib
                return zlib.decompress(raw)
            except Exception:
                import zlib
                return zlib.decompressobj(-15).decompress(raw)
    except Exception:
        pass
    return raw


def _raw(url, referer=None, timeout=12):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Accept-Language", "zh-CN,zh;q=0.9")
    req.add_header("Accept-Encoding", "gzip, deflate")
    req.add_header("Referer", referer or (HOST + "/"))
    try:
        r = _op().open(req, timeout=timeout)
        body = r.read()
        return r.status, _decomp(body, r.headers.get("Content-Encoding")), dict(r.headers)
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except Exception:
            body = b""
        return e.code, _decomp(body, e.headers.get("Content-Encoding") if e.headers else None), \
            dict(e.headers) if e.headers else {}
    except Exception:
        return 0, b"", {}


def _get(url, referer=None, timeout=12, tries=3, cache_ttl=0, ckey=None):
    if ckey:
        with _LOCK:
            hit = _CACHE.get(ckey)
        if hit and (time.time() - hit[0]) < cache_ttl:
            return hit[1]
    txt = ""
    for i in range(tries):
        st, body, _h = _raw(url, referer, timeout)
        if st == 200 and body:
            try:
                txt = body.decode("utf-8", "ignore")
            except Exception:
                txt = ""
            if len(txt) > 300:
                break
        time.sleep(0.35 * (i + 1))
    if ckey:
        with _LOCK:
            _CACHE[ckey] = (time.time(), txt)
            if len(_CACHE) > 300:
                _CACHE.clear()
    return txt


def _json(url, referer=None, timeout=25, cache_ttl=600):
    ck = "J:" + url
    with _LOCK:
        hit = _CACHE.get(ck)
    if hit and (time.time() - hit[0]) < cache_ttl:
        return hit[1]
    out = None
    for i in range(2):
        st, body, _h = _raw(url, referer, timeout)
        if st == 200 and body:
            try:
                out = json.loads(body.decode("utf-8", "ignore"))
                break
            except Exception:
                try:
                    out = json.loads(body.decode("gbk", "ignore"))
                    break
                except Exception:
                    out = None
        time.sleep(0.4)
    with _LOCK:
        _CACHE[ck] = (time.time(), out)
    return out


def _b64(s):
    try:
        return base64.urlsafe_b64encode((s or "").encode("utf-8")).decode("ascii").rstrip("=")
    except Exception:
        return ""


def _unb64(s):
    try:
        s = (s or "").strip()
        s += "=" * ((4 - len(s) % 4) % 4)
        return base64.urlsafe_b64decode(s.encode("ascii")).decode("utf-8", "ignore")
    except Exception:
        return ""


def _clean(s):
    if not s:
        return ""
    s = RE_TAGTXT.sub("", s)
    for a, b in (("&amp;", "&"), ("&quot;", '"'), ("&#39;", "'"),
                 ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " ")):
        s = s.replace(a, b)
    s = s.replace("$", "").replace("#", "").replace("\u3010", "[").replace("\u3011", "]")
    return re.sub(r"\s+", " ", s).strip()


def _pic(u):
    if not u:
        return ""
    u = u.strip().replace("\\/", "/")
    if u.startswith("//"):
        u = "https:" + u
    if u.startswith("/"):
        u = HOST + u
    return u


def _cards(html):
    out = []
    seen = set()
    for m in RE_CARD.finditer(html or ""):
        vid, body = m.group(1), m.group(2)
        if vid in seen:
            continue
        if "<img" not in body and "<h3" not in body:
            continue
        mi = RE_IMG.search(body)
        pic = _pic(mi.group(1)) if mi else ""
        mh = RE_H3.search(body)
        name = _clean(mh.group(1)) if mh else ""
        if not name:
            mt = re.search(r'alt="([^"]+)"', body)
            name = _clean(mt.group(1)) if mt else ""
        if not name:
            continue
        tags = [_clean(t) for t in RE_TAG.findall(body)]
        tags = [t for t in tags if t]
        seen.add(vid)
        out.append({
            "vod_id": vid + "@@" + _b64(name) + "@@" + _b64(pic),
            "vod_name": name,
            "vod_pic": pic,
            "vod_remarks": " ".join(tags)[:40],
        })
    return out


def _pagecount(html):
    mx = 1
    for n in RE_PAGE.findall(html or ""):
        try:
            v = int(n)
            if v > mx:
                mx = v
        except Exception:
            pass
    return min(mx, 3000)


def _list_url(path, pg):
    pg = int(pg or 1)
    p = (path or "/").strip()
    if p in ("", "/"):
        base = HOST
    else:
        base = HOST + p
    if pg > 1:
        return base.rstrip("/") + "/page/%d" % pg
    return base if base.endswith("/") or p not in ("", "/") else base + "/"


def _split_play(play_url):
    """play_url -> [(集名, 地址)]  优先取含 m3u8 的分段"""
    if not play_url:
        return []
    best = ""
    for seg in str(play_url).split("$$$"):
        if ".m3u8" in seg:
            best = seg
            break
        if not best:
            best = seg
    if ".m3u8" not in best:
        for seg in str(play_url).split("$$$"):
            if seg and not best:
                best = seg
    eps = []
    for item in best.split("#"):
        item = item.strip().replace("\\/", "/")
        if not item:
            continue
        if "$" in item:
            nm, _, u = item.partition("$")
        else:
            nm, u = "", item
        nm = _clean(nm) or ("\u7b2c%d\u96c6" % (len(eps) + 1))
        u = u.strip()
        if not u:
            continue
        eps.append((nm, u))
    if not eps:
        for m in RE_M3U8.findall(str(play_url).replace("\\/", "/")):
            eps.append(("\u7b2c%d\u96c6" % (len(eps) + 1), m))
    return eps


class Spider(BaseSpider):

    def __init__(self):
        try:
            BaseSpider.__init__(self)
        except Exception:
            pass
        self.host = HOST

    def init(self, extend=""):
        try:
            if isinstance(extend, dict):
                h = extend.get("host") or extend.get("ext")
                if h:
                    self.host = str(h).rstrip("/")
            elif isinstance(extend, str) and extend.strip():
                s = extend.strip()
                if s.startswith("{"):
                    d = json.loads(s)
                    if isinstance(d, dict) and d.get("host"):
                        self.host = str(d["host"]).rstrip("/")
                elif s.startswith("http"):
                    self.host = s.rstrip("/")
        except Exception:
            pass
        return None

    def getName(self):
        return "4K\u539f\u76d8"

    def getDependence(self):
        return []

    def isVideoFormat(self, url):
        try:
            return any(x in (url or "").lower() for x in
                       (".m3u8", ".mp4", ".flv", ".mkv", ".avi", ".ts"))
        except Exception:
            return False

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {}

    def liveContent(self, url):
        return ""

    def destroy(self):
        return None

    # ------------------------------------------------------------------ home
    def homeContent(self, filter=False):
        cls = [{"type_id": p, "type_name": n} for n, p in CATS]
        lst = []
        try:
            html = _get(HOST + "/", cache_ttl=300, ckey="home")
            lst = _cards(html)
        except Exception:
            lst = []
        return {"class": cls, "list": lst, "filters": {}}

    def homeVideoContent(self):
        try:
            return {"list": _cards(_get(HOST + "/", cache_ttl=300, ckey="home"))}
        except Exception:
            return {"list": []}

    # -------------------------------------------------------------- category
    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg or 1)
        except Exception:
            pg = 1
        path = tid if isinstance(tid, str) else "/"
        if not path.startswith("/"):
            path = "/" + path
        url = _list_url(path, pg)
        html = _get(url, cache_ttl=300, ckey="c:%s:%d" % (path, pg))
        lst = _cards(html)
        return {
            "list": lst,
            "page": pg,
            "pagecount": _pagecount(html),
            "limit": 24,
            "total": 999999,
        }

    # --------------------------------------------------------------- search
    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg or 1)
        except Exception:
            pg = 1
        if pg > 1:
            # 本站搜索不支持分页（/page/N/?keyword= 返回的是最新列表），只出第 1 页
            return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}
        kw = urllib.parse.quote((key or "").strip())
        url = "%s/?keyword=%s" % (HOST, kw)
        html = _get(url, cache_ttl=180, ckey="s:%s" % kw)
        lst = _cards(html)
        return {
            "list": lst,
            "page": 1,
            "pagecount": 1,
            "limit": 24,
            "total": len(lst),
        }

    # --------------------------------------------------------------- detail
    def _auto_search(self, title):
        if not title:
            return {}
        url = "%s?type=auto_search&wd=%s" % (API, urllib.parse.quote(title))
        d = _json(url, referer=HOST + "/", timeout=25, cache_ttl=600)
        try:
            if isinstance(d, dict) and isinstance(d.get("data"), dict):
                return d["data"]
        except Exception:
            pass
        return {}

    def _best_item(self, items, title):
        if not items or not title:
            return None
        t = title.strip()
        for it in items:
            if _clean(it.get("name", "")) == t:
                return it
        for it in items:
            n = _clean(it.get("name", ""))
            if n and (n.startswith(t) or t.startswith(n) or t in n):
                return it
        return None

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        vid = str(vid or "")
        parts = vid.split("@@")
        pid = parts[0].strip()
        title = _unb64(parts[1]) if len(parts) > 1 else ""
        pic = _unb64(parts[2]) if len(parts) > 2 else ""
        if not pid.isdigit():
            m = re.search(r"(\d+)", pid)
            pid = m.group(1) if m else pid

        html = _get("%s/%s" % (HOST, pid), cache_ttl=600, ckey="d:" + pid)
        if not title:
            m = re.search(r'class="x-dbjs-title"[^>]*>(.*?)</h2>', html, re.S)
            title = _clean(m.group(1)) if m else ""
        if not pic:
            m = re.search(r'class="x-dbjs-poster"[^>]*>\s*<img[^>]+src="([^"]+)"', html, re.S)
            pic = _pic(m.group(1)) if m else ""

        cont = ""
        m = re.search(r"\u5267\u60c5\u7b80\u4ecb</h3>\s*<p>(.*?)</p>", html, re.S)
        if m:
            cont = _clean(m.group(1))
        actor = ""
        m = re.search(r"\u6f14\u5458\u9635\u5bb9\uff1a</span>(.*?)</div>", html, re.S)
        if m:
            actor = _clean(m.group(1))
        director = ""
        m = re.search(r"\u5bfc\u6f14\uff1a</span>(.*?)</div>", html, re.S)
        if m:
            director = _clean(m.group(1))
        year = ""
        m = re.search(r"<h2[^>]*x-dbjs-title[^>]*>.*?\((\d{4})\)", html, re.S)
        if not m:
            m = re.search(r"\u65f6\u95f4\uff1a</span>(\d{4})", html, re.S)
        if m:
            year = m.group(1)
        area = ""
        m = re.search(r"\u56fd\u5bb6\uff1a</span>(.*?)</div>", html, re.S)
        if m:
            area = _clean(m.group(1))

        pfrom, purl = [], []

        # ---- 1. 站内自有源（播放页 route1/route2）
        try:
            ph = _get(PLUG + pid, referer="%s/%s" % (HOST, pid),
                      cache_ttl=600, ckey="p:" + pid)
            routes = []
            for rm in RE_ROUTE.finditer(ph or ""):
                try:
                    arr = json.loads(rm.group(2))
                except Exception:
                    arr = []
                eps = []
                for it in arr:
                    for nm, u in _split_play(it):
                        eps.append((nm, u))
                if eps:
                    routes.append(eps)
            for i, eps in enumerate(routes[:4]):
                pfrom.append("\u7ad9\u5185%d" % (i + 1))
                purl.append("#".join("%s$u|%s" % (nm, u) for nm, u in eps))
        except Exception:
            pass

        # ---- 2. 外源自动搜索（西瓜/暴风/天堂/非凡）
        try:
            data = self._auto_search(title)
            for src in ("\u897f\u74dc", "\u66b4\u98ce", "\u5929\u5802", "\u975e\u51e1"):
                it = self._best_item(data.get(src), title)
                if not it:
                    continue
                eps = _split_play(it.get("play_url", ""))
                if not eps:
                    continue
                body = []
                for nm, u in eps:
                    tag = "u" if ".m3u8" in u else "p"
                    body.append("%s$%s|%s" % (nm, tag, u))
                pfrom.append(src)
                purl.append("#".join(body))
        except Exception:
            pass

        # ---- 3. 嗅探兜底（回插件播放页）
        pfrom.append("\u5668\u63a2\u5e95")
        purl.append("\u6b63\u7247$p|%s%s" % (PLUG, pid))
        pfrom.append("\u89e3\u6790\u63a2\u5e95")
        purl.append("\u6b63\u7247$q|%s%s" % (PLUG, pid))

        # ---- 4. 磁力/BT 下载
        try:
            mags = []
            for mu in RE_MAG.findall(html):
                mu = mu.replace("&amp;", "&").strip()
                if mu and mu not in mags:
                    mags.append(mu)
            for qu in RE_QUARK.findall(html):
                qu = qu.strip()
                if qu and qu not in mags:
                    mags.append(qu)
            if mags:
                body = []
                for i, mu in enumerate(mags[:60]):
                    body.append("\u8d44\u6e90%d$m|%s" % (i + 1, mu.replace("#", "%23")))
                pfrom.append("\u78c1\u529b\u4e0b\u8f7d")
                purl.append("#".join(body))
        except Exception:
            pass

        vod = {
            "vod_id": pid + "@@" + _b64(title) + "@@" + _b64(pic),
            "vod_name": title or ("\u5f71\u7247 " + pid),
            "vod_pic": pic,
            "type_name": "",
            "vod_year": year,
            "vod_area": area,
            "vod_actor": actor,
            "vod_director": director,
            "vod_content": cont,
            "vod_play_from": "$$$".join(pfrom),
            "vod_play_url": "$$$".join(purl),
        }
        return {"list": [vod]}

    # --------------------------------------------------------------- player
    def _resolve(self, purl):
        """把 播放页/OEM 解析成直链，失败返回 ''"""
        if not purl:
            return ""
        if ".m3u8" in purl or ".mp4" in purl:
            return purl
        url = "%s?type=parse&url=%s" % (API, urllib.parse.quote(purl, safe=""))
        d = _json(url, referer=HOST + "/", timeout=20, cache_ttl=0)
        try:
            if isinstance(d, dict):
                u = d.get("data")
                if isinstance(u, dict):
                    u = u.get("url") or u.get("direct")
                if isinstance(u, str) and u.startswith("http"):
                    u = u.replace("\\/", "/")
                    if ".m3u8" in u:
                        return u
        except Exception:
            pass
        return ""

    def playerContent(self, flag, id, vipFlags):
        hdr = {"User-Agent": UA, "Referer": HOST + "/"}
        try:
            line = str(id or "")
            if "|" in line:
                kind, _, payload = line.partition("|")
            else:
                kind, payload = "p", line
            kind = kind.strip().lower()
            payload = payload.strip()

            if kind == "m":
                return {"parse": 0, "url": payload, "header": hdr}
            if kind == "q":
                # 交壳子的解析接口
                return {"parse": 1, "url": payload, "header": hdr}
            if kind == "u":
                if payload.startswith("http"):
                    return {"parse": 0, "url": payload, "header": hdr}
                kind = "p"
            # kind == "p" : 先试解析，失败回原页交 App 内建嗅探
            real = self._resolve(payload)
            if real:
                return {"parse": 0, "url": real, "header": hdr}
            if payload.startswith("http"):
                return {"parse": 0, "url": payload, "header": hdr}
            return {"parse": 0, "url": "", "header": hdr}
        except Exception:
            return {"parse": 0, "url": "", "header": hdr}

    # ------------------------------------------------------------ localProxy
    def localProxy(self, param=None):
        try:
            if isinstance(param, str) and param.strip().startswith("{"):
                param = json.loads(param)
            if not isinstance(param, dict):
                param = {}
        except Exception:
            param = {}
        url = param.get("url") or param.get("u") or ""
        if url:
            url = url.strip()
            if not url.startswith("http"):
                url = _unb64(url)
        if not url:
            return [404, "text/plain", b"no url", {}]
        ref = param.get("referer") or HOST + "/"
        st, body, hdr = _raw(url, ref, 15)
        if not body:
            return [404, "text/plain", b"empty", {}]
        mime = "application/octet-stream"
        if body[:1] == b"<":
            return [404, "text/plain", b"html", {}]
        if body[:3] == b"\xff\xd8\xff":
            mime = "image/jpeg"
        elif body[:8] == b"\x89PNG\r\n\x1a\n":
            mime = "image/png"
        elif body[:4] == b"RIFF":
            mime = "image/webp"
        elif body[:3] == b"GIF":
            mime = "image/gif"
        elif body[:7] == b"#EXTM3U":
            mime = "application/vnd.apple.mpegurl"
        elif b"ftyp" in body[:16]:
            mime = "video/mp4"
        else:
            mime = (hdr.get("Content-Type") or "application/octet-stream").split(";")[0]
        return [200, mime, body, {"User-Agent": UA, "Referer": ref}]
