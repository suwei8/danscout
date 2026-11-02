#!/usr/bin/env python3
"""Probe opencode models: text latency + vision check; pick fastest usable."""
import json, os, re, subprocess, sys, tempfile, time, zlib, struct, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "models")


def png(path, rgb=(52, 120, 200)):
    w = h = 8
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" +
        chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
        chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def run(model, prompt, file=None, timeout=75):
    cmd = ["opencode", "run", "-m", model]
    if file:
        cmd += ["-f", file]
    cmd.append(prompt)
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return time.time() - t0, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return timeout, "TIMEOUT"


def models():
    p = subprocess.run(["opencode", "models"], capture_output=True, text=True, timeout=30)
    return [l.strip() for l in (p.stdout + p.stderr).splitlines() if re.match(r"^[\w.-]+/[\w.-]+$", l.strip())]


def main():
    ms = models()
    with tempfile.TemporaryDirectory() as td:
        img = os.path.join(td, "s.png")
        png(img)
        rows = []
        for m in ms:
            t1, o1 = run(m, "只回复一个数字：2+3等于几")
            ok_text = "5" in o1
            t2, o2 = run(m, "这张图片是什么颜色？只回答颜色名一个词。", file=img)
            ok_img = bool(re.search(r"蓝|blue", o2, re.I))
            rows.append({"model": m, "text_ok": ok_text, "text_s": round(t1, 1),
                         "vision_ok": ok_img, "vision_s": round(t2, 1)})
            time.sleep(1)
    txt_ok = sorted([r for r in rows if r["text_ok"]], key=lambda r: r["text_s"])
    vis_ok = sorted([r for r in rows if r["vision_ok"]], key=lambda r: r["vision_s"])
    doc = {"probed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "results": rows,
           "chosen_text": txt_ok[0]["model"] if txt_ok else None,
           "chosen_vision": vis_ok[0]["model"] if vis_ok else None}
    os.makedirs(DATA, exist_ok=True)
    fn = os.path.join(DATA, datetime.date.today().isoformat() + ".json")
    json.dump(doc, open(fn, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(doc, ensure_ascii=False, indent=1))
    env = os.environ.get("GITHUB_ENV")
    if env:
        with open(env, "a") as f:
            f.write(f"MODEL_TEXT={doc['chosen_text'] or ''}\nMODEL_VISION={doc['chosen_vision'] or ''}\n")
    if not txt_ok:
        sys.exit(2)


if __name__ == "__main__":
    main()
