import os
import time
import json
import requests
import collections
import re

# Nginx writes JSON access logs here (from nginx.conf.template):
# access_log /var/log/nginx/access_json.log main_json;
LOG_FILE = "/var/log/nginx/access_json.log"

SLACK_WEBHOOK_URL   = os.getenv("SLACK_WEBHOOK_URL", "").strip()
THRESHOLD_PCT       = int(os.getenv("ERROR_RATE_THRESHOLD", "2"))    # percent of requests with any 5xx upstream
WINDOW_SIZE         = int(os.getenv("WINDOW_SIZE", "200"))           # track last N requests
COOLDOWN_SEC        = int(os.getenv("ALERT_COOLDOWN_SEC", "300"))    # min seconds between same alert
MAINTENANCE_MODE    = os.getenv("MAINTENANCE_MODE", "false").lower() == "true"

# Rolling window: store True (had 5xx upstream) / False (no 5xx upstream)
error_window = collections.deque(maxlen=WINDOW_SIZE)
last_alert_ts = {"failover": 0, "error_rate": 0}
last_pool_seen = None

five_xx = re.compile(r"^5\d\d$")

def now() -> int:
    return int(time.time())

def post_slack(title: str, text: str, color: str = "#ffcc00") -> None:
    if not SLACK_WEBHOOK_URL:
        return
    payload = {"attachments": [{"color": color, "title": title, "text": text}]}
    try:
        requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=5).raise_for_status()
    except Exception as e:
        print(f"[watcher] Slack post failed: {e}", flush=True)

def should_alert(kind: str) -> bool:
    return now() - last_alert_ts.get(kind, 0) >= COOLDOWN_SEC

def mark_alert(kind: str) -> None:
    last_alert_ts[kind] = now()

def had_upstream_5xx(upstream_status: str) -> bool:
    """
    upstream_status may be like "502, 200" (first attempt failed, retry succeeded)
    or "200" for single-attempt success. Return True if any token is 5xx.
    """
    if not upstream_status:
        return False
    # Split on comma and/or whitespace
    tokens = [tok.strip() for tok in upstream_status.replace(",", " ").split()]
    return any(five_xx.match(tok) for tok in tokens)

def handle_log_line(line: str) -> None:
    global last_pool_seen

    try:
        data = json.loads(line)
    except Exception:
        return

    pool = (data.get("pool") or "").lower()                # blue/green
    release = data.get("release") or ""
    final_status = str(data.get("status") or "")           # final LB status (often 200)
    upstream_status = str(data.get("upstream_status") or "")
    upstream_addr = data.get("upstream_addr") or ""
    req_time = data.get("request_time")

    # ---- Failover detection (pool flip) ----
    if pool:
        if last_pool_seen is None:
            last_pool_seen = pool
        elif pool != last_pool_seen:
            if not MAINTENANCE_MODE and should_alert("failover"):
                title = f"Failover detected: {last_pool_seen} → {pool}"
                text = (
                    f"Now serving: *{pool}* (release `{release}`)\n"
                    f"upstream: `{upstream_addr}`\n"
                    f"request_time: `{req_time}`"
                )
                post_slack(title, text, color="#36a64f" if pool == "green" else "#439FE0")
                mark_alert("failover")
            last_pool_seen = pool

    # ---- Error-rate from upstream attempts (not final status) ----
    error_window.append(had_upstream_5xx(upstream_status))

    if len(error_window) >= max(10, WINDOW_SIZE // 2):
        errors = sum(1 for v in error_window if v)
        rate = (errors / len(error_window)) * 100.0
        if not MAINTENANCE_MODE and rate >= THRESHOLD_PCT and should_alert("error_rate"):
            title = "High upstream error rate"
            text = (
                f"5xx in upstream attempts: *{rate:.2f}%* over last {len(error_window)} requests "
                f"(threshold {THRESHOLD_PCT}%).\n"
                f"Last pool: `{last_pool_seen}`\n"
                f"Recent upstream_status: `{upstream_status}` @ `{upstream_addr}`\n"
                f"Final LB status (for info): `{final_status}`"
            )
            post_slack(title, text, color="#ff0000")
            mark_alert("error_rate")

def tail_file(path: str) -> None:
    # Wait for file to exist
    while not os.path.exists(path):
        time.sleep(0.5)

    f = open(path, "r", encoding="utf-8", errors="ignore")
    # Try to start from end; if not seekable, just continue
    try:
        f.seek(0, os.SEEK_END)
    except Exception:
        pass

    while True:
        line = f.readline()
        if not line:
            time.sleep(0.25)
            continue
        line = line.strip()
        if line:
            handle_log_line(line)

if __name__ == "__main__":
    print("[watcher] starting… maintenance_mode =", MAINTENANCE_MODE, flush=True)
    tail_file(LOG_FILE)
