# -*- coding: utf-8 -*-
import urllib.request
import json
import re
import sys
from base.spider import Spider
from pyquery import PyQuery as pq

class Spider(Spider):
    def init(self, extend=""):
        self.host = "https://qswyt4444.com"
        self._HOST_POOL = []
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': f'{self.host}/',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }

    def __init__(self):

        try:

            super().__init__()

        except Exception:

            pass


    def getName(self):
        return "QS五月天"

    def isVideoFormat(self, url):
        return url.lower().endswith('.m3u8')

    def manualVideoCheck(self):
        return True

    def destroy(self):
        pass

    def homeContent(self, filter):
        result = {}
        classes = []
        seen_ids = set()
        try:
            res = self.fetch(self.host, headers=self.headers)
            d = pq(res.text)
            items = d('a[href^="/movie/block/"]')
            for item in items.items():
                href = item.attr('href')
                match = re.search(r'/movie/block/(\d+)', href)
                if match:
                    tid = match.group(1)
                    name = item.text().strip() or item.find('span').text().strip()
                    if tid and name and tid not in seen_ids:
                        classes.append({'type_name': name, 'type_id': tid})
                        seen_ids.add(tid)
        except Exception:
            pass

        if not classes:
            cateManual = {
                "最新": "newest",
                "国产": "50",
                "淫荡少妇": "21",
                "人妻诱惑": "22",
                "大奶萝莉": "23",
                "丝袜制服": "24",
                "强奸": "45",
                "群P": "46"
            }
            for k, v in cateManual.items():
                classes.append({'type_name': k, 'type_id': v})

        result['class'] = classes
        result['filters'] = {}
        return result

    def homeVideoContent(self):
        try:
            res = self.fetch(self.host, headers=self.headers)
            return {'list': self.parse_list(res.text)}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        result = {}
        if tid.isdigit():
            url = f'{self.host}/movie/block/{tid}?page={pg}'
        else:
            url = f'{self.host}/movie/{tid}?page={pg}'
        try:
            res = self.fetch(url, headers=self.headers)
            result['list'] = self.parse_list(res.text)
            result['page'] = int(pg)
            result['pagecount'] = 999
            result['limit'] = 20
            result['total'] = 9999
        except Exception:
            result['list'] = []
        return result

    def detailContent(self, ids):
        tid = ids[0]
        url = tid if tid.startswith('http') else (f'{self.host}{tid}' if tid.startswith('/') else f'{self.host}/movie/detail/{tid}')
        res = self.fetch(url, headers=self.headers)
        content = res.text
        title = ""
        pic = ""
        
        title_match = re.search(r'<meta property="og:title" content="(.*?)">', content)
        if title_match:
            title = title_match.group(1).split(' - ')[0]
        
        pic_match = re.search(r'<meta property="og:image" content="(.*?)">', content)
        if pic_match:
            pic = pic_match.group(1)

        vod_play_from_list = []
        vod_play_url_list = []
        pat = r'(/api/m3u8/p/[a-zA-Z0-9]+\.m3u8)'
        matches = re.findall(pat, content)
        unique_urls = []
        seen = set()
        
        for m in matches:
            full_url = m if m.startswith('http') else f"{self.host}{m}"
            if full_url not in seen:
                seen.add(full_url)
                unique_urls.append(full_url)

        for index, u in enumerate(unique_urls):
            vod_play_from_list.append(f"线路{index + 1}")
            vod_play_url_list.append(u)

        vod = {
            'vod_id': tid,
            'vod_name': title,
            'vod_pic': pic,
            'type_name': '',
            'vod_year': '',
            'vod_area': '',
            'vod_remarks': '',
            'vod_actor': '',
            'vod_director': '',
            'vod_content': '',
            'vod_play_from': '$$$'.join(vod_play_from_list),
            'vod_play_url': '$$$'.join(vod_play_url_list)
        }
        return {'list': [vod]}

    def searchContent(self, key, quick, pg="1"):
        url = f'{self.host}/search/{key}?page={pg}'
        try:
            res = self.fetch(url, headers=self.headers)
            return {'list': self.parse_list(res.text)}
        except:
            return {'list': []}

    def playerContent(self, flag, id, vipFlags):
        return {
            'parse': 0,
            'url': id,
            'header': {
                'User-Agent': self.headers['User-Agent']
            }
        }

    def localProxy(self, param=None):
            # 壳按 list.get(0/1/2) 取值 → 至少要 3 位，header 必须 dict
            return [200, "video/MP2T", b"", {}]

    def parse_list(self, html):
        videos = []
        d = pq(html)
        items = d('a[href^="/movie/detail/"]')
        seen_ids = set()
        for item in items.items():
            href = item.attr('href')
            if href in seen_ids:
                continue
            title = item.attr('title')
            if not title:
                title = item.find('span').text() or item.text()
            img_tag = item.find('img')
            pic = img_tag.attr('data-src') or img_tag.attr('src') or ""
            remarks = item.find('.duration').text()
            if href and title:
                seen_ids.add(href)
                videos.append({
                    'vod_id': href,
                    'vod_name': title.strip(),
                    'vod_pic': pic,
                    'vod_remarks': remarks
                })
        return videos


    # ---------- 域名自愈（2026-10-19 域名普查加装） ----------
    _RE_NEWDOM = re.compile(
        r'<a[^>]+href=["\'](https?://[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})["\'][^>]*>'
        r'(?:\s*<[^>]+>\s*)*(?:立\s*立即\s*跳\s*转|立即跳转|新地址|马上访问|点击跳转|进入网站|新网址)',
        re.I)
    _SKIP_HOST = re.compile(
        r'(google|baidu|t\.me|telegram|cloudflare|jsdelivr|jsdmirror|github|ghproxy|'
        r'51\.la|cnzz|alicdn|weixin|qq\.com|weibo|gstatic)', re.I)

    def _pool(self):
        p = list(self._HOST_POOL)
        cur = getattr(self, "host", "") or ""
        if cur and cur not in p:
            p.insert(0, cur)
        return p

    def _discover(self, html):
        """首页公告里抠新域名入池（该类站域名频繁轮换）"""
        if not html:
            return None
        if not any(k in html for k in ("新网址", "立即跳转", "进入网站", "防失联", "永久地址")):
            return None
        for m in self._RE_NEWDOM.finditer(html):
            try:
                host = urlparse(m.group(1)).netloc
            except Exception:
                continue
            if not host or self._SKIP_HOST.search(host):
                continue
            full = "https://" + host
            if full not in self._pool():
                self._HOST_POOL.insert(0, full)
                return full
        return None


    def action(self, action):
        """壳的动作协议入口：本源不提供动作卡"""
        return {"list": []}

    def liveContent(self, url):
        """壳的直播入口：本源不做直播"""
        return ""

    def getDependence(self):
        return []
