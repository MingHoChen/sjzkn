# -*- coding: utf-8 -*-
import sys, time, json
sys.path.insert(0, "/workspace")
import pomo

sp = pomo.Spider()
sp.init("")
ok = ng = 0
def chk(name, cond, extra=""):
    global ok, ng
    if cond:
        ok += 1; print("  PASS %s %s" % (name, extra))
    else:
        ng += 1; print("  FAIL %s %s" % (name, extra))

print("=== 1 首页 ===")
t = time.time(); r = sp.homeContent(False); print("  耗时 %.1fs" % (time.time()-t))
chk("class 数", len(r.get("class", [])) == 8, len(r.get("class", [])))
chk("list 非空", len(r.get("list", [])) >= 10, len(r.get("list", [])))
c0 = r["list"][0]
print("  样例:", c0["vod_name"], "|", c0["vod_pic"][:60], "|", c0["vod_remarks"])
chk("vod_id 格式", "@@" in c0["vod_id"])
chk("有封面", c0["vod_pic"].startswith("http"))

print("=== 2 homeVideoContent ===")
r2 = sp.homeVideoContent(); chk("list 非空", len(r2.get("list", [])) >= 10, len(r2.get("list", [])))

print("=== 3 分类 ===")
for tid in ["/huayurm", "/dianshiju", "/sort/12"]:
    t = time.time(); r3 = sp.categoryContent(tid, 1, False, {})
    chk("cat %s" % tid, len(r3["list"]) >= 10, "n=%d pc=%d %.1fs" % (len(r3["list"]), r3["pagecount"], time.time()-t))
r3b = sp.categoryContent("/dianshiju", 2, False, {})
chk("分页 p2", len(r3b["list"]) >= 10 and r3b["page"] == 2, "n=%d" % len(r3b["list"]))
chk("分页内容不同", r3b["list"][0]["vod_name"] != r3["list"][0]["vod_name"],
    "%s vs %s" % (r3b["list"][0]["vod_name"], [x for x in r3["list"]][0]["vod_name"]))

print("=== 4 搜索 ===")
t = time.time(); r4 = sp.searchContent("希望", False, "1")
chk("搜索命中", len(r4["list"]) >= 3, "n=%d %.1fs" % (len(r4["list"]), time.time()-t))
for x in r4["list"][:5]:
    print("   ", x["vod_name"], x["vod_id"][:30])
r4b = sp.searchContent("蜘蛛侠", False, "1")
chk("搜索2", len(r4b["list"]) >= 3, "n=%d" % len(r4b["list"]))

print("=== 5 详情 ===")
t = time.time(); r5 = sp.detailContent([sp.homeContent(False)["list"][0]["vod_id"]])
v = r5["list"][0]; print("  耗时 %.1fs" % (time.time()-t))
print("  片名", v["vod_name"], "|", v["vod_year"], "|", v["vod_area"], "| 封面", bool(v["vod_pic"]))
print("  简介", (v["vod_content"] or "")[:60])
print("  线路", v["vod_play_from"])
fl = v["vod_play_from"].split("$$$"); ul = v["vod_play_url"].split("$$$")
chk("线路数=地址段数", len(fl) == len(ul), "%d/%d" % (len(fl), len(ul)))
for f, u in zip(fl, ul):
    print("   [%s] 集数=%d  首集=%s" % (f, len(u.split("#")), u.split("#")[0][:90]))

print("=== 5b 详情(有站内源的那部) ===")
r5b = sp.detailContent(["3962@@" + pomo._b64("蜘蛛侠：崭新之日") + "@@"])
if r5b["list"]:
    vb = r5b["list"][0]
    print("  ", vb["vod_name"], "|", vb["vod_play_from"])
    for f, u in zip(vb["vod_play_from"].split("$$$"), vb["vod_play_url"].split("$$$")):
        print("   [%s] 集数=%d 首集=%s" % (f, len(u.split("#")), u.split("#")[0][:100]))

print("=== 6 播放 ===")
for f, u in zip(fl, ul):
    if f in ("西瓜", "暴风", "天堂", "非凡", "站内1"):
        pid = u.split("#")[0]
        t = time.time(); pr = sp.playerContent(f, pid, "")
        print("   [%s] %s url=%s %.1fs" % (f, pid.split("|")[0], pr["url"][:110], time.time()-t))
        chk("[%s] header dict" % f, isinstance(pr["header"], dict))
mb = [x for x in ul if x.split("#")[0].endswith(".m3u8")]
print("  直链线路:", "".join(f for f, u in zip(fl, ul) if "#" in u and ".m3u8" in u.split("$")[-1])[:200])

print("=== 7 localProxy ===")
lp = sp.localProxy({"url": "https://pomo.mom/content/uploadfile/db/p2935912706.webp"})
chk("localProxy 4元组", len(lp) == 4 and isinstance(lp[3], dict), "status=%s mime=%s len=%s" % (lp[0], lp[1], len(lp[2])))
if lp[0] == 200:
    print("   magic", lp[2][:4])

print("\n==== 结果 %d PASS / %d FAIL ====" % (ok, ng))
