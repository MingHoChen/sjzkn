# -*- coding: utf-8 -*-
"""cxkjg.py 独立自测（spider 本体不含 __main__）"""
import importlib.util
import json
import sys
import time
import urllib.request

PASS = 0
NG = 0


def ok(name, cond, extra=''):
    global PASS, NG
    if cond:
        PASS += 1
        print('  OK  %s %s' % (name, extra))
    else:
        NG += 1
        print('  NG  %s %s' % (name, extra))


def load(path):
    spec = importlib.util.spec_from_file_location('cxkjg_mod', path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def head_ok(url, ua):
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', ua)
        r = urllib.request.urlopen(req, timeout=20)
        body = r.read(2048)
        return r.status, body
    except Exception as e:
        return 0, str(e).encode()


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else '/workspace/cxkjg.py'
    m = load(path)
    S = m.Spider()
    print('=' * 60)
    print('自测: %s  getName=%s' % (path, S.getName()))
    print('=' * 60)

    # 1 init
    S.init('')
    ok('init("")', S.host.startswith('http'), S.host)
    S.init('{"host":"https://ys.cxkjg.cn","limit":30}')
    ok('init(extend json)', S.limit == 30)

    # 2 homeContent
    hc = S.homeContent(False)
    cls = hc.get('class') or []
    ok('homeContent.class', len(cls) >= 5, '%d 类' % len(cls))
    fl = hc.get('filters') or {}
    ok('homeContent.filters', len(fl) >= 1, '%d 组筛选' % len(fl))
    print('     分类:', [(c['type_id'], c['type_name']) for c in cls])
    hcf = S.homeContent(True)
    has_sub = any('filters' in c for c in (hcf.get('class') or []))
    ok('homeContent(filter=True) 带 filters', has_sub)

    # 3 homeVideoContent
    hv = S.homeVideoContent()
    l = hv.get('list') or []
    ok('homeVideoContent', len(l) > 0, '%d 条' % len(l))
    if l:
        ok('  item 字段', all(k in l[0] for k in ('vod_id', 'vod_name', 'vod_pic', 'vod_remarks')))

    # 4 categoryContent
    c1 = S.categoryContent('1', '1', False, {})
    ok('categoryContent t=1 p1', len(c1.get('list') or []) > 0, '%d 条' % len(c1.get('list') or []))
    ok('  page/pagecount/limit/total',
       all(k in c1 for k in ('list', 'page', 'pagecount', 'limit', 'total')),
       'pagecount=%s total=%s' % (c1.get('pagecount'), c1.get('total')))
    c2 = S.categoryContent('1', '2', False, {})
    ok('categoryContent 翻页 p2',
       (c2.get('list') or [{}])[0].get('vod_id') != (c1.get('list') or [{}])[0].get('vod_id'),
       '首片不同 OK')
    cf = S.categoryContent('1', '1', False, {'cid': '2', 'area': '美国'})
    ok('categoryContent 筛选 cid+area', len(cf.get('list') or []) > 0,
       'total=%s 首片=%s' % (cf.get('total'), (cf.get('list') or [{}])[0].get('vod_name')))

    # 5 searchContent
    sc = S.searchContent('流浪地球', False, '1')
    ok('searchContent', len(sc.get('list') or []) > 0, '%d 条' % len(sc.get('list') or []))
    if sc.get('list'):
        print('     搜索首条:', sc['list'][0]['vod_name'], sc['list'][0]['vod_remarks'])

    # 6 detailContent
    vid = (c1.get('list') or [{}])[0].get('vod_id')
    dc = S.detailContent([vid])
    d = (dc.get('list') or [{}])[0]
    ok('detailContent', bool(d.get('vod_name')), d.get('vod_name'))
    pfs = (d.get('vod_play_from') or '').split('$$$')
    pus = (d.get('vod_play_url') or '').split('$$$')
    ok('  线路数匹配', len(pfs) == len(pus) and len(pfs) >= 1,
       '%d 线路: %s' % (len(pfs), pfs))
    ok('  集数 # 分隔', '#' in (pus[0] if pus else ''), '%d 集' % len((pus[0] if pus else '').split('#')))

    # 7 playerContent + 真链探活
    first_ep = pus[0].split('#')[0] if pus else ''
    play_val = first_ep.split('$')[-1] if '$' in first_ep else first_ep
    pc = S.playerContent(pfs[0] if pfs else '', play_val)
    ok('playerContent parse=0', pc.get('parse') == 0)
    ok('  header 是 dict', isinstance(pc.get('header'), dict))
    u = pc.get('url') or ''
    ok('  返回 url', u.startswith('http'), u[:70])
    if u.startswith('http'):
        st, body = head_ok(u, S.UA)
        ok('  m3u8 真链探活', st == 200 and (b'#EXTM3U' in body or b'#EXTINF' in body),
           'http=%s %s' % (st, body[:20]))
        # 无 header 再测一次（防"我环境可通、用户不通"）
        st2, _ = head_ok(u, 'okhttp/4.9.0')
        ok('  m3u8 换 UA 也通', st2 == 200, 'http=%s' % st2)

    # 8 localProxy 契约
    r = S.localProxy(None)
    ok('localProxy 4位', len(r) == 4 and isinstance(r[3], dict))

    print('-' * 60)
    print('结果: PASS=%d  NG=%d' % (PASS, NG))
    return 0 if NG == 0 else 1


if __name__ == '__main__':
    t0 = time.time()
    rc = main()
    print('耗时 %.1fs' % (time.time() - t0))
    sys.exit(rc)
