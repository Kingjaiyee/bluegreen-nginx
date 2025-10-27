# Stage 2 DevOps — Blue/Green with Nginx Upstreams (Auto-Failover + Manual Toggle)

This repo implements **Blue/Green** routing using **Nginx** in front of two pre-built Node.js containers.
- **Normal:** all traffic → **Blue**
- **Failure:** request retries within the same client call → **Green**
- **Manual toggle:** set `ACTIVE_POOL=green` and reload to flip traffic

Public entry: `http://localhost:8080`  
Direct app ports (used by the grader): `http://localhost:8081` (blue), `http://localhost:8082` (green)

---

## Files
- `docker-compose.yml` — Orchestrates `nginx`, `app_blue`, `app_green`
- `nginx.conf.template` — Nginx upstream + retry/failover template
- `.env.example` — All parameters required by the grader
- `render-and-run.sh` — Small script to compute backup server based on `ACTIVE_POOL`
- `DECISION.md` — (Optional) Rationale and design trade-offs

---

## Quickstart (Local)

```bash
# 1) Prepare env
cp .env.example .env
# set BLUE_IMAGE / GREEN_IMAGE to the provided images

# 2) Launch
docker compose up -d

# 3) Verify baseline (Blue active)
curl -i http://localhost:8080/version | grep -E 'HTTP|X-App-Pool|X-Release-Id'

# 4) Induce Blue failure
curl -X POST "http://localhost:8081/chaos/start?mode=error"

# 5) Observe instant failover (within ~seconds, 0 non-200s expected)
for i in $(seq 1 10); do curl -sI http://localhost:8080/version | grep X-App-Pool; sleep 1; done

# 6) Stop chaos
curl -X POST "http://localhost:8081/chaos/stop"
```

**Manual toggle** (no failures, route traffic to Green on purpose):
```bash
# Edit .env → ACTIVE_POOL=green
docker compose down && docker compose up -d
# or hot reload:
docker exec nginx_lb nginx -s reload
```

All application headers (e.g. `X-App-Pool`, `X-Release-Id`) are forwarded unchanged.

---

## Azure VM Deployment (Public IP submission ready)

> Works on Ubuntu 22.04 LTS. Replace values in ALL_CAPS.

1. **Create VM**
   - Size: `Standard_B1s` (ok for test)  
   - **Inbound ports**: open 22 (SSH). You will open app ports later.

2. **SSH into VM**
```bash
ssh -i /path/to/KEY.pem azureuser@YOUR_VM_PUBLIC_IP
```

3. **Install Docker & Compose Plugin**
```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo   "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu   $(. /etc/os-release && echo $VERSION_CODENAME) stable" |   sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
newgrp docker
```

4. **Open firewall ports (VM + Azure NSG)**
   - In Azure **NSG**: allow **8080, 8081, 8082** (TCP) from your IP or 0.0.0.0/0 for grading.
   - On VM (UFW):
```bash
sudo ufw allow 22/tcp
sudo ufw allow 8080/tcp
sudo ufw allow 8081/tcp
sudo ufw allow 8082/tcp
sudo ufw enable
sudo ufw status
```

5. **Upload repo & run**
```bash
# on your laptop
scp -i /path/to/KEY.pem -r bluegreen-nginx azureuser@YOUR_VM_PUBLIC_IP:~
# on VM
cd bluegreen-nginx
cp .env.example .env
# set correct BLUE_IMAGE / GREEN_IMAGE (provided by task), optionally UPDATE RELEASE_IDs
docker compose up -d
```

6. **Smoke test from your laptop or VM**
```bash
curl -sI http://YOUR_VM_PUBLIC_IP:8080/version | egrep 'HTTP|X-App-Pool|X-Release-Id'
```

7. **Submit the public IP** exactly as shown in Azure portal.

---

## Notes
- Request timeout budget: `~5–6s` worst-case due to `proxy_*_timeout` and `proxy_next_upstream_timeout`. No request should exceed **10s**.
- Failover: We use `backup` server in upstream + `max_fails=1 fail_timeout=3s` to mark primary down quickly. Retry happens **within the same client request** via `proxy_next_upstream`.
- Headers: We explicitly pass `X-App-Pool` and `X-Release-Id` (not overwritten).

---

## Troubleshooting
- **502/504**: check app health on direct ports: `curl -i http://localhost:8081/healthz`
- **No failover**: ensure `/chaos/start?mode=error` hit **blue** at `8081`.
- **Swap active pool**: set `ACTIVE_POOL` and reload Nginx: `docker exec nginx_lb nginx -s reload`.
