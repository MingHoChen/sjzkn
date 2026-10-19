# -*- coding: utf-8 -*-
# 胖大AV / 熊猫视频 站群 - TVBox/FongMi type=3
# 2026-10-19 新发现：该站群是纯 JSON API 架构
#   前台 www.9g88x.com / www.xm66xm.com 只是 JS 壳，真实数据全在：
#   POST https://data.7wzx9.com/getDataInit  → 分类树 (menu0ListMap[].menu2List[])
#   POST https://data.7wzx9.com/forward
#        command=WEB_GET_ALL          → 首页各栏最新
#        command=WEB_GET_INFO         → 列表 (pageNumber/RecordsPage/typeId/typeMid)
#        command=WEB_GET_INFO_DETAIL  → 详情 (id/type_Mid) → 直接给 vod_url(m3u8 相对路径)
#   播放地址 = 列表里 vod_pic 的【域】+ 详情的 vod_url(相对路径)
# 站点域名频繁轮换 → 域名池 + 公告自动发现
import json, re, ssl, time, threading, urllib.parse, urllib.request, urllib.error

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider(object):
        pass

try:
    from Crypto.Cipher import AES
except Exception:
    AES = None


class Spider(_BaseSpider):
    HOSTS = ["https://www.9g88x.com", "https://www.9k88x.com", "https://www.xm66xm.com"]
    API = "https://data.7wzx9.com"
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
    LOCK = threading.Lock()
    _CATS = []          # 模块级缓存：分类树
    _PICS = {}          # 模块级：vid -> 封面绝对URL（含流域名）

    def __init__(self):
        try:
            super(Spider, self).__init__()
        except Exception:
            pass
        self.host = self.HOSTS[0]
        self.extend = {}
        self._cache = {}

    # ---------- 壳子契约 ----------
    def init(self, extend=""):
        self.extend = self._parse_extend(extend)
        h = self.extend.get("host")
        if h:
            h = str(h).rstrip("/")
            if h.startswith("//"):
                h = "https:" + h
            elif not h.startswith("http"):
                h = "https://" + h
            if h not in self.HOSTS:
                self.HOSTS.insert(0, h)
            self.host = h

    def getDependence(self):
        return []

    def getName(self):
        return "胖大AV·熊猫"

    def isVideoFormat(self, url):
        return bool(url) and any(x in url.lower() for x in
                                 (".m3u8", ".mp4", ".flv", ".ts", ".mkv"))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {"list": []}

    def liveContent(self, url):
        return ""

    def localProxy(self, param=None):
        return [200, "video/MP2T", b"", {}]

    @staticmethod
    def _parse_extend(extend):
        out = {}
        if not extend:
            return out
        if isinstance(extend, dict):
            out.update(extend)
        else:
            s = str(extend).strip()
            if s.startswith("{"):
                try:
                    out.update(json.loads(s))
                except Exception:
                    pass
        return out

    # ---------- 网络 ----------
    def _post(self, path, payload, timeout=20, retries=2):
        url = self.API + path
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "User-Agent": self.UA,
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": self.host.rstrip("/"),
            "Referer": self.host.rstrip("/") + "/",
        }
        for i in range(retries + 1):
            try:
                req = urllib.request.Request(url, data=data, headers=headers)
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                r = urllib.request.urlopen(req, timeout=timeout, context=ctx)
                raw = r.read()
                try:
                    return json.loads(raw.decode("utf-8", "ignore"))
                except Exception:
                    return {}
            except Exception as e:
                if i < retries:
                    time.sleep(0.6)
        return {}

    # ---------- 分类 ----------
    def _cats(self):
        if self._CATS:
            return self._CATS
        j = self._post("/getDataInit", {"name": "John", "age": 31, "city": "New York"})
        data = (j or {}).get("data") or {}
        groups = data.get("menu0ListMap") or []
        out = []
        for g in groups:
            if not isinstance(g, dict):
                continue
            for z in (g.get("menu2List") or []):
                if not isinstance(z, dict):
                    continue
                tid = z.get("typeId2")
                name = z.get("typeName2")
                if tid is None or not name:
                    continue
                out.append({
                    "type_id": "%s@%s" % (tid, z.get("typeMid2") or 1),
                    "type_name": str(name),
                })
        # 去重
        seen = set()
        uniq = []
        for c in out:
            if c["type_id"] in seen:
                continue
            seen.add(c["type_id"])
            uniq.append(c)
        with self.LOCK:
            self._CATS = uniq
        return uniq

    # ---------- 列表 ----------
    def _list(self, tid, pg):
        try:
            t, mid = str(tid).split("@")
            t = int(t)
            mid = int(mid or 1)
        except Exception:
            t, mid = 6, 1
        try:
            pg = max(1, int(pg))
        except Exception:
            pg = 1
        j = self._post("/forward", {
            "command": "WEB_GET_INFO",
            "pageNumber": pg,
            "RecordsPage": 20,
            "typeId": t,
            "typeMid": mid,
            "languageType": "CN",
            "content": "",
        })
        data = (j or {}).get("data") or {}
        raw = data.get("resultList") or []
        items = []
        for it in raw:
            if not isinstance(it, dict):
                continue
            vid = it.get("id")
            name = it.get("vod_name")
            if vid is None or not name:
                continue
            pic = it.get("vod_pic") or ""
            vid = str(vid)
            with self.LOCK:
                self._PICS[vid] = pic
            items.append({
                "vod_id": vid,
                "vod_name": self._clean(name),
                "vod_pic": pic,
                "vod_remarks": it.get("vod_class") or "HD",
            })
        pages = data.get("pageAllNumber") or 1
        try:
            pages = int(pages)
        except Exception:
            pages = 1
        total = data.get("count") or len(items)
        try:
            total = int(total)
        except Exception:
            total = len(items)
        if not items:
            pages = pg
        return items, max(1, pages), total

    @staticmethod
    def _clean(t):
        t = str(t or "").replace("$", "＄").replace("#", "＃")
        return re.sub(r"\s+", " ", t).strip()

    # ---------- 六接口 ----------
    def homeContent(self, filter=False):
        cats = self._cats()
        items = []
        try:
            j = self._post("/forward", {"command": "WEB_GET_ALL",
                                         "languageType": "CN", "content": ""})
            data = (j or {}).get("data") or {}
            for grp in (data.get("resultList") or []):
                if not isinstance(grp, dict):
                    continue
                for it in (grp.get("t_list") or []):
                    if not isinstance(it, dict) or it.get("id") is None:
                        continue
                    vid = str(it.get("id"))
                    pic = it.get("vod_pic") or ""
                    with self.LOCK:
                        self._PICS[vid] = pic
                    items.append({"vod_id": vid,
                                  "vod_name": self._clean(it.get("vod_name")),
                                  "vod_pic": pic,
                                  "vod_remarks": it.get("vod_class") or "HD"})
        except Exception:
            pass
        if not items and cats:
            try:
                items, _, _ = self._list(cats[0]["type_id"], 1)
            except Exception:
                pass
        return {"class": cats, "list": items}

    def homeVideoContent(self):
        try:
            items, _, _ = self._list("6@1", 1)
        except Exception:
            items = []
        return {"list": items, "page": 1, "pagecount": 1,
                "limit": len(items), "total": len(items)}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            items, pages, total = self._list(tid, pg)
        except Exception:
            items, pages, total = [], 1, 0
        return {"list": items, "page": int(pg or 1), "pagecount": pages,
                "limit": len(items), "total": total}

    def detailContent(self, ids):
        vid = str(ids[0] if isinstance(ids, (list, tuple)) else ids)
        try:
            mid = 1
            with self.LOCK:
                pic = self._PICS.get(vid, "")
        except Exception:
            pic = ""
        j = self._post("/forward", {"command": "WEB_GET_INFO_DETAIL",
                                     "type_Mid": mid, "id": int(vid),
                                     "languageType": "CN"})
        res = ((j or {}).get("data") or {}).get("result") or {}
        name = res.get("vod_name") or ""
        url = res.get("vod_url") or ""
        dpic = res.get("vod_pic") or ""
        # 播放域 = 封面域（列表里 vod_pic 的 host）
        base = ""
        if pic:
            m = re.match(r"(https?://[^/]+)", pic)
            if m:
                base = m.group(1)
        if not base:
            base = self.host.rstrip("/")
        if dpic and dpic.startswith("/"):
            dpic = base + dpic
        if not pic:
            pic = dpic
        play = ""
        if url:
            if url.startswith("http"):
                play = url
            else:
                play = base + url
        if not name:
            name = "影片 " + vid
        if play:
            ep = "正片$" + play
        else:
            ep = "正片$s0@@" + self.host.rstrip("/") + "/moviePlayer.html?id=" + vid
        return {"list": [{"vod_id": vid,
                           "vod_name": self._clean(name),
                           "vod_pic": pic,
                           "vod_remarks": "正片",
                           "vod_play_from": "胖大AV·直连$$$胖大AV·原页",
                           "vod_play_url": ep}]}

    def playerContent(self, flag, id, vipFlags=None):
        pid = str(id or "")
        if pid.startswith("s0@@"):
            return {"parse": 0, "url": pid[4:], "header": {"User-Agent": self.UA}}
        if not pid:
            return {"parse": 0, "url": "", "header": {}}
        return {"parse": 0, "url": pid,
                "header": {"User-Agent": self.UA,
                           "Referer": self.host.rstrip("/") + "/"}}

    def searchContent(self, key, quick, pg="1"):
        # 该站未开放搜索接口 → 退化为按分类名模糊匹配本地缓存
        out = []
        k = str(key or "").strip()
        if k:
            try:
                cats = self._cats()
                for c in cats:
                    if k in c["type_name"]:
                        try:
                            items, _, _ = self._list(c["type_id"], 1)
                            out.extend(items[:10])
                        except Exception:
                            pass
                    if len(out) >= 30:
                        break
            except Exception:
                pass
        return {"list": out, "page": 1, "pagecount": 1,
                "limit": len(out), "total": len(out)}
