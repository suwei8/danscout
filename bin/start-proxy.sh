#!/bin/bash
# write singbox config from VLESS_URL env + start sing-box on 127.0.0.1:11080
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
python3 - <<'PY'
import json, os, re, urllib.parse
u = os.environ["VLESS_URL"]
m = re.match(r"vless://([^@]+)@([^:]+):(\d+)\?(.*)", u)
uuid, host, port, qs = m.group(1), m.group(2), int(m.group(3)), urllib.parse.parse_qs(m.group(4))
q = {k: v[0] for k, v in qs.items()}
cfg = {"log": {"level": "warn"},
 "inbounds": [{"type": "socks", "tag": "in", "listen": "127.0.0.1", "listen_port": 11080}],
 "outbounds": [{"type": "vless", "server": host, "server_port": port, "uuid": uuid,
   "transport": {"type": q.get("type", "ws"), "path": q.get("path", "/"),
                 "headers": {"Host": q.get("host", "")}}}]}
json.dump(cfg, open(os.path.join(os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else "bin", "singbox.json"), "w"))
PY
if pgrep -f "singbox run" >/dev/null; then exit 0; fi
setsid "$DIR/singbox" run -c "$DIR/singbox.json" >/tmp/singbox.log 2>&1 < /dev/null &
for i in $(seq 1 15); do
  curl -fsS --max-time 8 --socks5-hostname 127.0.0.1:11080 -o /dev/null https://bbs.55125.cn/ && { echo "proxy up"; exit 0; }
  sleep 2
done
echo "proxy FAILED"; cat /tmp/singbox.log; exit 1
