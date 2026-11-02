#!/usr/bin/env python3
"""Telegram sender for danscout. HTML parse_mode with plain-text fallback."""
import json
import os
import re
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(ROOT, "config.json")))


def _post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _send_one(text, token, chat_id, parse_mode):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text,
               "disable_web_page_preview": True}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        return _post(url, payload)
    except urllib.error.HTTPError as e:
        # malformed HTML/markup -> strip tags and retry as plain text
        if e.code == 400 and parse_mode:
            payload.pop("parse_mode")
            payload["text"] = re.sub(r"<[^>]+>", "", text)
            return _post(url, payload)
        raise


def send(text, token=None, chat_id=None, parse_mode="HTML"):
    token = token or os.environ.get("TG_TOKEN") or CFG["telegram"].get("bot_token")
    chat_id = chat_id or os.environ.get("TG_CHAT_ID") or CFG["telegram"].get("chat_id")
    results = []
    # telegram limit 4096 chars; split on blank-line boundaries
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > 3900:
            chunks.append(cur)
            cur = line
        else:
            cur = (cur + "\n" + line).strip("\n")
    if cur:
        chunks.append(cur)
    for c in chunks:
        results.append(_send_one(c, token, chat_id, parse_mode))
    return results


if __name__ == "__main__":
    import sys
    text = sys.argv[1] if len(sys.argv) > 1 else "danscout test"
    print(json.dumps(send(text), ensure_ascii=False)[:500])
