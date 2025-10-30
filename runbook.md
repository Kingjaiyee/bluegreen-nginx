# Runbook – Blue/Green Ops & Alerts

## Alerts

### 1) Failover Detected (blue → green or green → blue)
Meaning: Nginx is now serving the other pool (auto-failover or manual toggle).
Actions:
- Check primary health:
  - `curl -i http://<VM_IP>:8081/healthz` (blue)
  - `curl -i http://<VM_IP>:8082/healthz` (green)
- Inspect app logs: `docker logs app_blue --tail=100`, `docker logs app_green --tail=100`
- If planned maintenance: set `MAINTENANCE_MODE=true` in `.env` and `docker compose restart alert_watcher`.

### 2) High Error Rate
Meaning: 5xx rate exceeded `ERROR_RATE_THRESHOLD` over last `WINDOW_SIZE` requests.
Actions:
- Check upstream logs and resources.
- Consider temporary manual toggle:
  - `sed -i 's/^ACTIVE_POOL=.*/ACTIVE_POOL=green/' .env` (or blue)
  - `docker exec nginx_lb sh -lc '/docker-entrypoint.d/99-render-and-run.sh && nginx -s reload'`

## Maintenance Mode (suppress alerts)
- Set `MAINTENANCE_MODE=true` in `.env`
- `docker compose restart alert_watcher`
- Re-enable later with `MAINTENANCE_MODE=false` then restart watcher.

## Where to look
- Nginx logs: `docker exec -it nginx_lb sh -lc 'tail -n 100 /var/log/nginx/access.log'`
- App health: `curl -i http://localhost:8081/healthz`, `curl -i http://localhost:8082/healthz`
- Compose status: `docker compose ps`
