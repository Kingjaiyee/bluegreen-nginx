import os, time, json, requests, collections, re

LOG_FILE = "/var/log/nginx/access.log"

SLACK_WEBHOOK_URL   = os.getenv("SLACK_WEBHOOK_URL", "").strip()
THRESHOLD_PCT       = int(os.getenv("ERROR_RATE_THRESHOLD", "2"))
WINDOW_SIZE         = int(os.getenv("WINDOW_SIZE", "200"))
COOLDOWN_SEC        = int(os.getenv("ALERT_COOLDOWN_SEC", "300"))
MAINTENANCE_MODE    = os.getenv("MAINTENANCE_MODE", "false").lower() == "true"

status_window = collections.deque(maxlen=WINDOW_SIZE)
last_alert_ts = {"failover": 0, "error_rate": 0}
last_pool_seen = None

five_xx = re.compile(r"^5\d\d$")

def now(): return int(time.time())

def post_slack(title, text, color="#ffcc00"):
    if not SLACK_WEBHOOK_URL:
        return
    payload = {"attachments": [{"color": color, "title": title, "text": text}]}
    try:
        requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=5).raise_for_status()
    except Exception as e:
        print(f"[watcher] Slack post failed: {e}", flush=True)

def should_alert(kind): return now() - last_alert_ts.get(kind, 0) >= COOLDOWN_SEC
def mark_alert(kind): last_alert_ts[kind] = now()

def handle_log_line(line: str):
    global last_pool_seen
    try:
        data = json.loads(line)
    except Exception:
        return

    pool = (data.get("pool") or "").lower()
    release = data.get("release") or ""
    status = str(data.get("status") or "")
    upstream_status = str(data.get("upstream_status") or "")
    upstream = data.get("upstream_addr") or ""
    req_time = data.get("request_time")

    # Detect pool flips
    if pool:
        if last_pool_seen is None:
            last_pool_seen = pool
        elif pool != last_pool_seen:
            if not MAINTENANCE_MODE and should_alert("failover"):
                title = f"Failover detected: {last_pool_seen} → {pool}"
                text = f"Now serving: *{pool}* (release `{release}`)\nupstream: `{upstream}`\nrequest_time: `{req_time}`"
                post_slack(title, text, color="#36a64f" if pool == "green" else "#439FE0")
                mark_alert("failover")
            last_pool_seen = pool

    # Track error rate
    if status:
        status_window.append(status)

    if len(status_window) >= max(10, WINDOW_SIZE // 2):
        errors = sum(1 for s in status_window if five_xx.match(str(s)))
        rate = (errors / len(status_window)) * 100.0
        if not MAINTENANCE_MODE and rate >= THRESHOLD_PCT and should_alert("error_rate"):
            title = "High upstream error rate"
            text = (f"5xx rate: *{rate:.2f}%* over last {len(status_window)} requests "
                    f"(threshold {THRESHOLD_PCT}%).\nLast pool: `{last_pool_seen}`\n"
                    f"Recent upstream_status: `{upstream_status}` @ `{upstream}`")
            post_slack(title, text, color="#ff0000")
            mark_alert("error_rate")

def tail_file(path):
    # simple tail -F
    while not os.path.exists(path):
        time.sleep(0.5)
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        f.seek(0, os.SEEK_END)
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
