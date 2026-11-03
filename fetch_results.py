#!/usr/bin/env python3
"""Fetch draw results into data/{game}/results.json (accumulative)."""
import json, os, re, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import collector

GAMES = {"3d": ("xq_sd.aspx", "3d-kjjg"), "p3": ("xq_p3.aspx", "p3-kjjg")}


def result_for(prefix, period):
    h = collector.fetch_text(f"https://kjh.55123.cn/{prefix}-{period}.htm")
    ds = re.findall(r'red-40">(\d)', h)
    return "".join(ds[:3]) if len(ds) >= 3 else ""


def main():
    for game, (main_page, prefix) in GAMES.items():
        gdir = os.path.join(ROOT, "data", game)
        rp = os.path.join(gdir, "results.json")
        res = json.load(open(rp)) if os.path.exists(rp) else {}
        idx_p = os.path.join(gdir, "index.json")
        have = {str(p) for p in (json.load(open(idx_p)).get("periods") if os.path.exists(idx_p) else [])}
        try:
            h = collector.fetch_text(f"https://kjh.55123.cn/{main_page}")
            have |= set(re.findall(rf"{re.escape(prefix)}-(\d{{7}})\.htm", h))
        except Exception as e:
            print(game, "main page fail:", e)
        for per in sorted(have):
            if res.get(per):
                continue
            try:
                n = result_for(prefix, per)
                if n:
                    res[per] = n
                    print(game, per, "=", n)
            except Exception as e:
                print(game, per, "fail:", str(e)[:60])
        os.makedirs(gdir, exist_ok=True)
        json.dump(dict(sorted(res.items())), open(rp, "w"), ensure_ascii=False, indent=0)
        print(game, "results:", len(res))


if __name__ == "__main__":
    main()
