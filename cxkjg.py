# -*- coding: utf-8 -*-
"""
创享影视  ys.cxkjg.cn  —— TVBox / FongMi（默影视/webhtv）type=3 源

站型：Next.js App Router 影视聚合站（Nginx 反代），
      但自带标准 MacCMS v10 采集接口，数据层完全不用碰 HTML：
          https://ys.cxkjg.cn/api/provide/vod
      站点自身 /api/provide/tvbox 暴露的 TVBox 配置里，
      11 个 api 全部指向它（默认全量 + 11 个 source 分源）。

实测结论（2026-10-15）：
  · /api.php/provide/vod  → 308 跳 /api/provide/vod（非标准路径，别用）
  · ac=list   → class(9) + filters + list(20)   recordcount=14880 / pagecount=744
  · ac=detail&ids=ID → vod_play_from/vod_play_url 直接给 m3u8 直链
        线路示例：金鹰$$$非凡$$$量子$$$速博$$$红牛$$$光速（6 线路，集数各异）
  · m3u8 裸请求 200，无需 UA/Referer；ts 分片 200；#EXT-X-KEY 的 enc.key 也 200
  · 分页 t={tid}&pg={n}；筛选 cid/area/language/sort 组合实测生效
  · 搜索 ac=detail&wd={关键词}
  → 零解密、零嗅探，parse=0 直出。

extend（可选，JSON 串或 dict）：
  {"host":"https://ys.cxkjg.cn", "source":"2680151544", "limit":30}
"""
import re
import json
import time
import gzip
import urllib.request
import urllib.parse

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass


# ---------------------------------------------------------------- 网络层（纯标准库）
_OPENER = None
_COOKIE_JAR = None


def _get_opener():
    global _OPENER, _COOKIE_JAR
    if _OPENER is None:
        try:
            import http.cookiejar
            _COOKIE_JAR = http.cookiejar.CookieJar()
            _OPENER = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(_COOKIE_JAR))
        except Exception:
            _OPENER = urllib.request.build_opener()
        try:
            _OPENER.addheaders = [
                ('User-Agent', Spider.UA),
                ('Accept', '*/*'),
                ('Accept-Language', 'zh-CN,zh;q=0.9'),
            ]
        except Exception:
            pass
    return _OPENER


def _decompress(raw, enc):
    if not raw:
        return raw
    if enc and 'gzip' in enc.lower():
        try:
            return gzip.decompress(raw)
        except Exception:
            pass
    if raw[:2] == b'\x1f\x8b':
        try:
            return gzip.decompress(raw)
        except Exception:
            pass
    return raw


# ---------------------------------------------------------------- Spider
class Spider(BaseSpider):
    HOSTS = ['https://ys.cxkjg.cn']
    NAME = '创享影视'
    UA = ('Mozilla/5.0 (Linux; Android 13; M2102J2SC) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36')
    LIMIT = 30
    TTL = 300

    def __init__(self):
        try:
            BaseSpider.__init__(self)
        except Exception:
            pass
        self.host = self.HOSTS[0]
        self.source = ''
        self.limit = self.LIMIT
        self._cls = None
        self._filters = {}
        self._cache = {}
        self.NAME = '创享影视'

    def getName(self):
        return self.NAME

    def isVideoFormat(self, url):
        return any(x in (url or '').lower()
                   for x in ['.m3u8', '.mp4', '.flv', '.mkv', '.ts'])

    def manualVideoCheck(self):
        return False

    def getDependence(self):
        return []

    # ------------------------------------------------------------ 初始化
    def init(self, extend=""):
        cfg = {}
        try:
            if isinstance(extend, dict):
                cfg = extend
            elif isinstance(extend, str) and extend.strip():
                s = extend.strip()
                cfg = json.loads(s) if s.startswith('{') else (
                    {'host': s} if s.startswith('http') else {})
        except Exception:
            cfg = {}
        h = cfg.get('host')
        if isinstance(h, str) and h.startswith('http'):
            self.host = h.rstrip('/')
        src = cfg.get('source')
        if src:
            self.source = str(src)
        try:
            if int(cfg.get('limit', 0)) > 0:
                self.limit = min(100, int(cfg['limit']))
        except Exception:
            pass

    # ------------------------------------------------------------ 底层请求
    def _raw(self, url, tries=3):
        last = ''
        for i in range(tries):
            try:
                req = urllib.request.Request(url)
                req.add_header('User-Agent', self.UA)
                req.add_header('Accept-Encoding', 'gzip, deflate')
                r = _get_opener().open(req, timeout=20)
                data = _decompress(r.read(), r.headers.get('Content-Encoding'))
                txt = data.decode('utf-8', 'ignore')
                if txt:
                    return txt
                last = 'empty'
            except Exception as e:
                last = str(e)
            time.sleep(0.4 * (i + 1))
        return last if last.startswith('{') else ''

    def _api(self, params):
        if self.source and 'source' not in params:
            params['source'] = self.source
        q = urllib.parse.urlencode(params)
        url = '%s/api/provide/vod?%s' % (self.host, q)
        txt = self._raw(url)
        try:
            return json.loads(txt)
        except Exception:
            return {}

    def _cached(self, key, fn):
        now = time.time()
        hit = self._cache.get(key)
        if hit and now - hit[0] < self.TTL:
            return hit[1]
        val = fn()
        if val:
            if len(self._cache) > 200:
                self._cache.clear()
            self._cache[key] = (now, val)
        return val

    # ------------------------------------------------------------ 列表格式化
    def _items(self, lst):
        out = []
        for it in (lst or []):
            try:
                vid = str(it.get('vod_id') or '').strip()
                if not vid:
                    continue
                nm = self._clean(it.get('vod_name') or '')
                if not nm:
                    continue
                pic = (it.get('vod_pic') or it.get('vod_pic_thumb') or '').strip()
                out.append({
                    'vod_id': vid,
                    'vod_name': nm,
                    'vod_pic': pic,
                    'vod_remarks': self._clean(it.get('vod_remarks') or ''),
                })
            except Exception:
                continue
        return out

    @staticmethod
    def _clean(s):
        s = str(s or '')
        for ch in ['$', '#']:
            s = s.replace(ch, '')
        return s.strip()

    def _norm_filters(self, raw):
        """接口 filters 已是 {tid: [{key,name,value:[{n,v}]}]}，规范化后直用"""
        out = {}
        try:
            for tid, arr in (raw or {}).items():
                lst = []
                for f in arr:
                    vals = []
                    for v in (f.get('value') or []):
                        vals.append({'n': str(v.get('n', '')), 'v': str(v.get('v', ''))})
                    if vals:
                        lst.append({'key': str(f.get('key', '')),
                                    'name': str(f.get('name', '')),
                                    'value': vals})
                if lst:
                    out[str(tid)] = lst
        except Exception:
            pass
        return out

    def _cls_data(self):
        def fetch():
            j = self._api({'ac': 'list'})
            return j if j.get('class') else {}
        j = self._cached('cls', fetch)
        if j.get('class'):
            self._cls = [{'type_id': str(c.get('type_id')),
                          'type_name': c.get('type_name')}
                         for c in j['class'] if c.get('type_id') is not None]
            self._filters = self._norm_filters(j.get('filters'))
        return j

    # ------------------------------------------------------------ 六接口
    def homeContent(self, filter=False):
        j = self._cls_data()
        cls = self._cls or []
        try:
            if filter and self._filters:
                for c in cls:
                    fl = self._filters.get(str(c['type_id']))
                    if fl:
                        c['filters'] = fl
            else:
                cls = [{'type_id': c['type_id'], 'type_name': c['type_name']} for c in cls]
        except Exception:
            pass
        return {'class': cls, 'filters': self._filters}

    def homeVideoContent(self):
        j = self._api({'ac': 'detail', 'pg': 1, 'limit': self.limit})
        return {'list': self._items(j.get('list'))}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1) if str(pg or 1).isdigit() else 1
        params = {'ac': 'detail', 't': tid, 'pg': pg, 'limit': self.limit}
        flt = filter if isinstance(filter, dict) else {}
        if not flt and isinstance(extend, dict):
            flt = extend
        for k in ('cid', 'area', 'language', 'sort', 'year'):
            v = (flt or {}).get(k)
            if v not in (None, ''):
                params[k] = v
        j = self._api(params)
        items = self._items(j.get('list'))
        try:
            pc = int(j.get('pagecount') or 0) or pg
        except Exception:
            pc = pg
        try:
            total = int(j.get('total') or j.get('recordcount') or 0)
        except Exception:
            total = 0
        return {'list': items, 'page': pg, 'pagecount': max(pc, pg),
                'limit': self.limit, 'total': total}

    def searchContent(self, key, quick=False, pg='1'):
        pg = int(pg) if str(pg).isdigit() else 1
        j = self._api({'ac': 'detail', 'wd': key, 'pg': pg, 'limit': self.limit})
        items = self._items(j.get('list'))
        try:
            pc = int(j.get('pagecount') or 0) or pg
        except Exception:
            pc = pg
        return {'list': items, 'page': pg, 'pagecount': max(pc, pg),
                'limit': self.limit, 'total': int(j.get('total') or len(items))}

    def detailContent(self, ids):
        if isinstance(ids, (list, tuple)):
            vid = str(ids[0]) if ids else ''
        else:
            vid = str(ids or '')
        vid = vid.split('@')[-1].split(',')[0].strip()
        if not vid:
            return {'list': []}
        j = self._api({'ac': 'detail', 'ids': vid})
        lst = j.get('list') or []
        if not lst:
            return {'list': []}
        it = lst[0]
        name = self._clean(it.get('vod_name') or '')
        pf = it.get('vod_play_from') or ''
        pu = it.get('vod_play_url') or ''
        # 线路名与地址段数对齐（接口给的是 MacCMS 标准 $$$/#）
        froms = [x for x in str(pf).split('$$$') if x.strip()]
        urls = [x for x in str(pu).split('$$$') if x.strip()]
        if len(urls) < len(froms):
            froms = froms[:len(urls)]
        if not urls:
            return {'list': []}
        play_from = '$$$'.join(froms)
        play_url = '$$$'.join(urls)
        vod = {
            'vod_id': vid,
            'vod_name': name,
            'vod_pic': (it.get('vod_pic') or it.get('vod_pic_thumb') or '').strip(),
            'vod_remarks': self._clean(it.get('vod_remarks') or ''),
            'type_name': it.get('type_name') or '',
            'vod_year': str(it.get('vod_year') or ''),
            'vod_area': str(it.get('vod_area') or ''),
            'vod_actor': self._clean(it.get('vod_actor') or ''),
            'vod_director': self._clean(it.get('vod_director') or ''),
            'vod_content': self._clean(it.get('vod_blurb') or it.get('vod_content') or ''),
            'vod_play_from': play_from,
            'vod_play_url': play_url,
        }
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags=None):
        url = str(id or '')
        if '$$$' in url:
            url = url.split('$$$')[0]
        if '#' in url:
            url = url.split('#')[0]
        if '$' in url:
            url = url.split('$')[-1]
        header = {'User-Agent': self.UA}
        if self.isVideoFormat(url):
            return {'parse': 0, 'url': url, 'header': header}
        return {'parse': 0, 'url': url, 'header': header}

    def action(self, action):
        return {}

    def liveContent(self, url):
        return ''

    # ------------------------------------------------------------ 可选本地代理
    def localProxy(self, param=None):
        # 本站直链，无需代理；保留契约（list ≥3 位，header 必须 dict）
        return [404, 'text/plain', b'no-proxy', {'Content-Type': 'text/plain'}]
