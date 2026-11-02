#!/usr/bin/env python3
"""Probe free kilo models: text latency + real vision check; pick fastest usable.

- Model list: `kilo models`, filtered to free ids (:free$/-free$//free$).
- Image capability: `kilo models kilo --verbose` capability metadata
  (authoritative); unknown models are still probed.
- Verification uses tokens that cannot collide with model names/headers.
- Message must precede -f: kilo's --file is an array flag that would
  otherwise swallow the prompt as another file argument.
- Never fails the workflow: LLM is not on the collection critical path.
"""
import json, os, re, struct, subprocess, time, zlib, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "models")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|[\x00-\x08\x0b-\x1f\x7f]")
FREE = re.compile(r"(:free|-free|/free)$")

TEXT_TOKEN = "ZQX9-READY"
VISION_GLYPH = ["11111", "00010", "00100", "00100", "01000", "01000", "01000"]  # digit 7


def png(path, px):
    h, w = len(px), len(px[0])
    raw = b"".join(b"\x00" + b"".join(bytes(p) for p in row) for row in px)

    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" +
        chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
        chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def digit_png(path):
    s, pad = 8, 8
    W, H = 5 * s + 2 * pad, 7 * s + 2 * pad
    px = [[(255, 255, 255)] * W for _ in range(H)]
    for y, row in enumerate(VISION_GLYPH):
        for x, c in enumerate(row):
            if c == "1":
                for dy in range(s):
                    for dx in range(s):
                        px[pad + y * s + dy][pad + x * s + dx] = (20, 20, 20)
    png(path, px)


def clean(s):
    return ANSI.sub("", s or "").strip()


def run(model, prompt, file=None, timeout=75):
    cmd = ["kilo", "run", "-m", model, prompt]
    if file:
        cmd += ["-f", file]  # -f is an array flag: must come after the message
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return round(time.time() - t0, 1), clean(p.stdout + "\n" + p.stderr)
    except subprocess.TimeoutExpired:
        return timeout, "TIMEOUT"


def models():
    p = subprocess.run(["kilo", "models"], capture_output=True, text=True, timeout=60)
    ids = [l.strip() for l in (p.stdout + p.stderr).splitlines() if l.strip().startswith("kilo/")]
    return [i for i in ids if FREE.search(i)], len(ids)


def capabilities(model_ids):
    """kilo models --verbose -> {id: image_capable|None}. {} on failure."""
    try:
        p = subprocess.run(["kilo", "models", "kilo", "--verbose"],
                           capture_output=True, text=True, timeout=60)
        caps = {}
        for blk in re.split(r"\n(?=kilo/)", p.stdout):
            m = re.match(r"kilo/(\S+)", blk.strip())
            j = re.search(r"\{.*\}", blk, re.S)
            if not (m and j):
                continue
            try:
                d = json.loads(j.group(0))
                inp = (d.get("capabilities") or {}).get("input") or {}
                caps["kilo/" + m.group(1)] = bool(inp.get("image"))
            except Exception:
                caps["kilo/" + m.group(1)] = None
        return caps
    except Exception:
        return {}


def main():
    ms, total_listed = models()
    caps = capabilities(ms)
    rows = []
    # image must live inside cwd: kilo rejects external_directory reads
    img = os.path.join(ROOT, ".probe-digit.png")
    digit_png(img)
    try:
        for m in ms:
            t1, o1 = run(m, f"Output exactly this token and nothing else: {TEXT_TOKEN}")
            row = {"model": m, "text_ok": TEXT_TOKEN in o1, "text_s": t1,
                   "text_out": o1[:160],
                   "image_capable": caps.get(m)}
            if caps.get(m) is not False:  # image-capable or unknown -> probe
                t2, o2 = run(m, "The attached image shows a single digit. "
                                "Reply with exactly: IMGOK <digit>", file=img)
                row["vision_ok"] = bool(re.search(r"IMGOK\D*7\b", o2))
                row["vision_s"] = t2
                row["vision_out"] = o2[:160]
            else:
                row["vision_ok"] = False
                row["vision_s"] = None
            rows.append(row)
            time.sleep(1)
    finally:
        os.path.exists(img) and os.remove(img)
    txt_ok = sorted([r for r in rows if r["text_ok"]], key=lambda r: r["text_s"])
    vis_ok = sorted([r for r in rows if r.get("vision_ok")], key=lambda r: r["vision_s"])
    doc = {"probed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "listed_total": total_listed, "probed": len(ms),
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


if __name__ == "__main__":
    main()
