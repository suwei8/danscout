#!/usr/bin/env python3
"""Aggregate fetched posts into normalized per-period JSON for the web panel."""
import json, os, re, sys, datetime
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import collector  # noqa

DATA = os.path.join(ROOT, "data")

ZX = re.compile(
    r"直选推荐|直选\d+注|直选定位|直选复式|直、组|"
    r"直组大底|直组精选|直组几注|直组\d+注|直组|"
    r"单选推荐|单选号码|单选\d+注|单选|"
    r"单挑一注|单挑|乾坤\d*注|精选单注|精选号码|精选\d+注|专家精选|重点关注")
GRP = re.compile(r"组选推荐|组选号码|组选\d+注|组选大底|组选|组六|组三")
BOUNDARY = re.compile(
    r"和值|跨度|杀码|杀|复式|定位|胆码|胆|开机|防组选|缩水|字谜|开奖|"
    r"包星|胆拖|形态|奇偶|大小|质合|尾数|和尾|直选|单选|直组|单挑|精选")


def _segs(text, label_re):
    zs = [(m.start(), m.end(), m.group(0)) for m in label_re.finditer(text)]
    out = []
    for i, (s, e, label) in enumerate(zs):
        end = zs[i + 1][0] if i + 1 < len(zs) else len(text)
        b = BOUNDARY.search(text, e, end)
        if b and b.start() > e:
            end = b.start()
        out.append(text[e:end])
    return out


def _nums(seg):
    nums = []
    for tok in re.split(r"[\s，,、；;:：\-—~·]+", seg):
        tok = tok.strip()
        if re.fullmatch(r"\d{3}", tok):
            nums.append(tok)
        elif re.fullmatch(r"(?:\d{3}[./|])+?\d{3}", tok):
            nums.extend(re.findall(r"\d{3}", tok))
    return nums


def _dig(text, pat, nd=1):
    m = re.search(pat, text)
    if not m:
        return ""
    return "".join(re.findall(r"\d", m.group(1)))[:nd]


def predictor(title, author):
    t = re.sub(r"20\d{5}|\d{2,3}期|福彩3[Dd]|3[Dd]|排列三|排列3|体彩|P3|预测|推荐|分析|精选|全国首发|专家|本期|开奖|号码|定位|胆码|复式|免费|【|】|\[|\]|（|）|\(|\)|第|年|期|：|:|·|\.|，|,|最|准|新|今|日", " ", title)
    t = " ".join(t.split()).strip()
    if len(t) > 12:
        t = t[:12]
    return t or author or "未知"


def fields(text):
    f = {}
    f["dutan"] = _dig(text, r"(?:独胆|毒胆|金胆|孤胆|一胆|一码)[:：]?\s*[参为是]?\s*(\d)")
    f["shuangdan"] = _dig(text, r"双胆[:：]?\s*[参为是]?\s*(\d[\d,，\s]{0,4}\d)", 2)
    f["sandan"] = _dig(text, r"三胆[:：]?\s*[参为是]?\s*(\d[\d,，\s]{0,6}\d)", 3)
    f["ma5"] = _dig(text, r"五码(?:复式)?[^0-9]{0,4}(\d[\d,，\s]{3,9}\d)", 5)
    f["ma6"] = _dig(text, r"六码(?:复式)?[^0-9]{0,4}(\d[\d,，\s]{4,11}\d)", 6)
    f["shama"] = _dig(text, r"(?:绝杀|通杀|排除|可杀|杀码|杀一码)[:：]?[^0-9]{0,6}(\d[\d,，\s]{0,6}\d|\d)", 3)
    hz = re.search(r"和值[^0-9]{0,4}([\d,，\s\-~至]{2,40})", text)
    f["hezhi"] = hz.group(1).strip() if hz else ""
    kd = re.search(r"跨度[^0-9]{0,4}([\d,，\s]{1,20})", text)
    f["kuadu"] = kd.group(1).strip() if kd else ""
    zx, gp = [], []
    for seg in _segs(text, ZX):
        zx += _nums(seg)
    for seg in _segs(text, GRP):
        gp += _nums(seg)
    f["zhixuan"] = list(dict.fromkeys(zx))
    f["zuxuan"] = list(dict.fromkeys(gp))
    return f


def consensus(posts):
    from collections import Counter
    dt, cover, zx = Counter(), Counter(), Counter()
    for p in posts:
        f = p.get("fields", {})
        if f.get("dutan"):
            dt[f["dutan"]] += 1
        for d in set(f.get("sandan", "") + f.get("shuangdan", "") + f.get("dutan", "")):
            if d:
                cover[d] += 1
        for n in f.get("zuxuan", []):
            zx[n] += 1
    return {"dutan_freq": dict(dt.most_common()),
            "dan_cover": dict(cover.most_common()),
            "zuxuan_freq": dict(zx.most_common()),
            "zhixuan_count": len({n for p in posts for n in p.get("fields", {}).get("zhixuan", [])})}


def aggregate(game):
    r = collector.fetch_all(game=game, max_pages=2)
    posts = []
    for p in r["posts"]:
        if p.get("error") or not p.get("text") and not p.get("images"):
            continue
        posts.append({
            "predictor": predictor(p["title"], p.get("author", "")),
            "title": p["title"], "author": p.get("author", ""),
            "board": p["board"], "url": p["url"], "time": p.get("time", ""),
            "image_count": len(p.get("images", [])),
            "fields": fields(p.get("text") or ""),
            "text": (p.get("text") or "")[:4000],
        })
    doc = {"game": game, "period": r["period"],
           "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "post_count": len(posts), "posts": posts, "consensus": consensus(posts)}
    gdir = os.path.join(DATA, game)
    os.makedirs(gdir, exist_ok=True)
    with open(os.path.join(gdir, f"{r['period']}.json"), "w") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    # manifest
    idx_path = os.path.join(gdir, "index.json")
    idx = json.load(open(idx_path)) if os.path.exists(idx_path) else {"periods": []}
    if r["period"] not in idx["periods"]:
        idx["periods"].append(r["period"])
    idx["periods"] = sorted(idx["periods"], reverse=True)
    idx["latest"] = idx["periods"][0] if idx["periods"] else None
    with open(idx_path, "w") as f:
        json.dump(idx, f)
    print(f"{game}: period={r['period']} posts={len(posts)} zx_unique={doc['consensus']['zhixuan_count']}")
    return doc


if __name__ == "__main__":
    games = sys.argv[1:] or ["3d", "p3"]
    for g in games:
        aggregate(g)
