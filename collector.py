#!/usr/bin/env python3
"""danscout collector - fetch latest FC3D prediction posts from two CN forums.

55125.cn is geo-blocked outside CN -> fetched via local socks5 proxy.
bbs.17500.cn has a broken DNS record (->127.0.0.1) -> fetched via curl --resolve.
"""
import json
import os
import re
import subprocess
import sys
import time
import html as htmlmod
from urllib.parse import urljoin

ROOT = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(ROOT, "config.json")))
DATA = CFG["data_dir"] if CFG["data_dir"].startswith("/") else os.path.join(ROOT, "data")
IMG_DIR = os.path.join(DATA, "images")
os.makedirs(IMG_DIR, exist_ok=True)

_UA = CFG["ua"]


def _curl_args(url):
    host = re.sub(r"^https?://", "", url).split("/")[0]
    args = ["curl", "-sSL", "--max-time", "40", "-A", _UA,
            "-H", "Accept-Language: zh-CN,zh;q=0.9"]
    if host in CFG["proxied_hosts"]:
        args += ["-x", CFG["proxy"]]
    if host in CFG["resolve_map"]:
        ip = CFG["resolve_map"][host]
        args += ["--resolve", f"{host}:443:{ip}", "--resolve", f"{host}:80:{ip}"]
    args.append(url)
    return args


def fetch_bytes(url, referer=None, retries=2):
    args = _curl_args(url)
    if referer:
        args[1:1] = ["-e", referer]
    last = None
    for i in range(retries + 1):
        p = subprocess.run(args, capture_output=True, timeout=60)
        if p.returncode == 0:
            return p.stdout
        last = RuntimeError(f"curl rc={p.returncode}: {p.stderr.decode(errors='replace')[:200]}")
        time.sleep(1.5 * (i + 1))
    raise last


def fetch_text(url):
    raw = fetch_bytes(url)
    m = re.search(rb'charset=["\']?([\w-]+)', raw[:3000], re.I)
    enc = (m.group(1).decode().lower() if m else "utf-8")
    if enc in ("gbk", "gb2312"):
        enc = "gb18030"
    try:
        return raw.decode(enc, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def strip_tags(s):
    s = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br[^>]*>", "\n", s, flags=re.I)
    s = re.sub(r"</(?:p|div|li|tr|h\d)>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = htmlmod.unescape(s)
    s = re.sub(r"[ \t\r\f\v ​﻿]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def period_candidates(period):
    """Regex matching titles for e.g. period 2026291 -> '2026291' or standalone '291'."""
    full = str(period)
    short = full[-3:]
    return re.compile(rf"(?:{re.escape(full)}|(?<!\d){re.escape(short)}(?!\d))")


def resolve_period(game="3d"):
    """target period = last drawn + 1 (kjh page, via proxy); fallback: latest seen in titles."""
    out = {"target": None, "last_drawn": None, "evidence": []}
    url = CFG["kjh_url_p3"] if game == "p3" else CFG["kjh_url"]
    try:
        s = fetch_text(url)
        drawn = [int(x) for x in re.findall(r"第\s*(20\d{5})\s*期", s)]
        if drawn:
            last = max(drawn)
            out["last_drawn"] = last
            out["target"] = last + 1
            out["evidence"].append(f"{url} 显示最近开奖 {last} -> 目标 {last+1}")
    except Exception as e:
        out["evidence"].append(f"kjh 页抓取失败: {e}")
    return out


# ---------- 55125.cn ----------

def list_55125(bid, page=1):
    suffix = "" if page == 1 else f"_{page}"
    s = fetch_text(f"https://bbs.55125.cn/list_{bid}{suffix}.html")
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", s, re.S | re.I):
        t = re.search(r'<a href="(https://bbs\.55125\.cn/\d{4}-\d{2}/\d{1,2}/[a-z0-9]+\.html)"[^>]*>(.*?)</a>', tr, re.S | re.I)
        if not t:
            continue
        cat = re.search(r'class="posttype"[^>]*>\s*(\[[^\]]*\])', tr)
        au = re.search(r'userinfo\.aspx\?uid=\d+">([^<]+)</a>', tr)
        rows.append({
            "board": f"55125:bid{bid}",
            "cat": cat.group(1) if cat else "",
            "url": t.group(1),
            "title": htmlmod.unescape(re.sub(r"<[^>]+>", "", t.group(2))).strip(),
            "author": au.group(1).strip() if au else "",
        })
    return rows


def post_55125(url):
    s = fetch_text(url)
    # first <div class="text"> is the OP's post; later ones are replies (ignored)
    m = re.search(r'<div class="text"[^>]*>(.*?)</td>', s, re.S | re.I)
    blk = m.group(1) if m else ""
    inner = re.search(r'class="main-part"[^>]*>(.*?)</div>', blk, re.S | re.I)
    body = strip_tags(inner.group(1) if inner else blk)
    imgs = [u for u in re.findall(r'<img[^>]+src="([^"]+)"', blk, re.I)
            if not re.search(r"/images/|emoticons|avatars|medals|kindeditor", u)]
    return body, [urljoin(url, u) for u in imgs]


# ---------- 17500.cn (Discuz) ----------

B175 = "https://bbs.17500.cn"


def list_17500(fid, page=1):
    s = fetch_text(f"{B175}/forum.php?mod=forumdisplay&fid={fid}&page={page}")
    rows = []
    for m in re.finditer(r'<tbody id="normalthread_(\d+)">(.*?)</tbody>', s, re.S):
        tid, blk = m.group(1), m.group(2)
        t = re.search(r'<a[^>]*class="s xst"[^>]*>(.*?)</a>', blk, re.S)
        if not t:
            continue
        title = htmlmod.unescape(re.sub(r"<[^>]+>", "", t.group(1))).strip()
        au = re.search(r'<td class="by">\s*<cite>\s*<a[^>]*>([^<]+)</a>', blk, re.S)
        tm = re.search(r'<td class="by">.*?<em>\s*<span[^>]*>([^<]+)</span>', blk, re.S)
        cat = re.search(r'<em>\[<a[^>]*>([^<]+)</a>\]</em>', blk)
        rows.append({
            "board": f"17500:fid{fid}",
            "cat": f"[{cat.group(1)}]" if cat else "",
            "url": f"{B175}/forum.php?mod=viewthread&tid={tid}",
            "title": title,
            "author": au.group(1).strip() if au else "",
            "time": tm.group(1).strip() if tm else "",
        })
    return rows


def post_17500(url):
    s = fetch_text(url)
    # first post only (楼主); ignore replies and comments entirely
    m = re.search(r'<td[^>]*id="postmessage_\d+"[^>]*>(.*?)</td>', s, re.S)
    blk = m.group(1) if m else ""
    body = strip_tags(blk)
    imgs = re.findall(r'(?:src|file)="([^"]*(?:attachment|forum/)[^"]*)"', blk, re.I)
    return body, [urljoin(url, u) for u in imgs]


# ---------- top level ----------

_P3_MARK = re.compile(r"排列三|排列3|排三|P3|PL3", re.I)
_P3_EXCL = re.compile(r"排列五|排列5|排五|P5|PL5", re.I)
_NOISE = re.compile(r"排列|体彩|双色球|大乐透|七乐彩|时时彩|快乐8|快3|P3|P5", re.I)


def _is_p3(t):
    return bool(_P3_MARK.search(t["title"])) and not _P3_EXCL.search(t["title"])


def fetch_all(period=None, download_images=True, max_pages=1, game="3d"):
    info = resolve_period(game)
    period = int(period or info["target"] or 0)
    if not period:
        raise RuntimeError("无法确定目标期号")
    pat = period_candidates(period)
    p3 = game == "p3"

    boards = CFG["boards_55125_p3"] if p3 else CFG["boards_55125"]
    threads, seen = [], set()
    for bid in boards:
        for pg in range(1, max_pages + 1):
            try:
                for t in list_55125(bid, pg):
                    if t["url"] not in seen:
                        seen.add(t["url"])
                        threads.append(t)
            except Exception as e:
                threads.append({"board": f"55125:bid{bid}p{pg}", "error": str(e)})
                break
    for pg in range(1, max_pages + 1):
        try:
            for t in list_17500(CFG["board_17500_fid"], pg):
                if t["url"] not in seen:
                    seen.add(t["url"])
                    threads.append(t)
        except Exception as e:
            threads.append({"board": f"17500:fid6p{pg}", "error": str(e)})
            break

    if p3:
        # 55125 P3 boards are inherently p3; fid6 is mixed -> require p3 marker
        matched = [t for t in threads if t.get("title") and pat.search(t["title"])
                   and ("17500" not in t["board"] or _is_p3(t))]
    else:
        matched = [t for t in threads if t.get("title") and pat.search(t["title"])
                   and not _NOISE.search(t["title"])]
    matched = matched[: int(CFG["max_posts_per_board"] * 6)]

    posts = []
    for t in matched:
        p = dict(t)
        try:
            if "55125" in t["board"]:
                body, imgs = post_55125(t["url"])
            else:
                body, imgs = post_17500(t["url"])
            p["text"] = body
            p["images"] = []
            if download_images:
                for i, u in enumerate(imgs):
                    try:
                        ext = os.path.splitext(u.split("?")[0])[1] or ".jpg"
                        fp = os.path.join(IMG_DIR, f"p{period}_{re.sub(r'[^0-9a-zA-Z]+','_',t['url'])[-30:]}_{i}{ext}")
                        with open(fp, "wb") as f:
                            f.write(fetch_bytes(u, referer=t["url"]))
                        p["images"].append(fp)
                    except Exception:
                        pass
        except Exception as e:
            p["error"] = str(e)
        posts.append(p)

    result = {
        "period": period,
        "resolve": info,
        "scanned_threads": len([t for t in threads if t.get("title")]),
        "errors": [t for t in threads if t.get("error")],
        "post_count": len(posts),
        "posts": posts,
    }
    out_path = os.path.join(DATA, f"run_{game}_{period}_{len(posts)}.json")
    with open(out_path, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    result["saved_to"] = out_path
    return result


def cleanup_images():
    n = 0
    for fn in os.listdir(IMG_DIR):
        os.remove(os.path.join(IMG_DIR, fn))
        n += 1
    return n


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "fetch"
    if cmd == "period":
        print(json.dumps(resolve_period(), ensure_ascii=False, indent=1))
    elif cmd == "fetch":
        period = sys.argv[2] if len(sys.argv) > 2 else None
        pages = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        game = sys.argv[4] if len(sys.argv) > 4 else "3d"
        r = fetch_all(period, max_pages=pages, game=game)
        print(json.dumps({k: r[k] for k in ("period", "scanned_threads", "post_count", "saved_to", "errors")}, ensure_ascii=False, indent=1))
        for p in r["posts"]:
            print(f"  [{p['board']}] {p['author']}: {p['title']} | text={len(p.get('text',''))}c imgs={len(p.get('images',[]))} {'ERR:'+p.get('error','') if p.get('error') else ''}")
    elif cmd == "cleanup":
        print(f"removed {cleanup_images()} images")
