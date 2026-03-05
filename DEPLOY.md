# Production Deployment — Spread Dashboard

## Architecture

```
Internet → Cloudflare (SSL/proxy) → Hetzner VPS (5.223.65.230)
                                      │
                               ┌──────┴──────┐
                               │  UFW (22/80/443)
                               └──────┬──────┘
                                      │
                          ┌───────────┴───────────┐
                          │  NPM (Nginx Proxy Mgr) │  ← ~/proxy
                          │  0.0.0.0:80, 0.0.0.0:443 │
                          │  127.0.0.1:81 (admin)  │
                          └───────────┬───────────┘
                                      │  host.docker.internal:3000
                          ┌───────────┴───────────┐
                          │  frontend (nginx)      │  ← ~/spread-dashboard
                          │  127.0.0.1:3000 → :80  │
                          │  Static files + proxy  │
                          └───────────┬───────────┘
                                      │  Docker default network (DNS: "backend")
                          ┌───────────┴───────────┐
                          │  backend (uvicorn)     │
                          │  127.0.0.1:8000 → :8000│
                          │  FastAPI + WebSocket   │
                          └───────────────────────┘
```

**Networking (Option A — localhost binding):**
- Frontend and backend bind to `127.0.0.1` only — invisible to the internet.
- NPM reaches frontend via `host.docker.internal:3000` (Docker's host-gateway).
- Frontend nginx proxies `/api/*` and `/ws` to `backend:8000` using Docker DNS.
- NPM is the ONLY service with public port bindings (80/443).

---

## What Changed (from dev → production)

| File | Change |
|------|--------|
| `frontend/Dockerfile` | Vite dev server → multi-stage build (Node → nginx) |
| `frontend/nginx.conf` | Serves static files, proxies /api and /ws to backend |
| `backend/Dockerfile` | Removed `--reload`, added `--workers 1`, `--timeout-keep-alive 65` |
| `docker-compose.yml` | Localhost-only ports, no dev volumes, healthchecks |
| `frontend/src/App.tsx` | WebSocket URL: `ws://` → protocol-aware `wss://`/`ws://` |

---

## Deployment Steps

### Prerequisites
- SSH into server: `ssh -i ~/.ssh/hetzner_ed25519 deploy@5.223.65.230`
- All commands below run on the server as `deploy` user

### Step 1: Update NPM compose to support host.docker.internal

Edit `~/proxy/docker-compose.yml` on the server:

```yaml
services:
  npm:
    image: 'jc21/nginx-proxy-manager:latest'
    restart: always
    ports:
      - '80:80'
      - '443:443'
      - '127.0.0.1:81:81'
    extra_hosts:
      - "host.docker.internal:host-gateway"
    volumes:
      - ./data:/data
      - ./letsencrypt:/etc/letsencrypt
```

Restart NPM:
```bash
cd ~/proxy
docker compose down
docker compose up -d
```

### Step 2: Pull and rebuild the app

```bash
cd ~/spread-dashboard
git fetch --all
git reset --hard origin/main

# Ensure data directory exists
mkdir -p backend/data
chmod 700 backend/data

# Ensure .env exists with CORS_ORIGINS
grep -q CORS_ORIGINS backend/.env || echo 'CORS_ORIGINS=https://dash.firstyjps.com' >> backend/.env

# Build and start
docker compose up -d --build

# Verify
docker compose ps
docker compose logs --tail=50 backend
docker compose logs --tail=50 frontend
```

### Step 3: Configure NPM proxy host

Access NPM admin:
```bash
# On your Mac — SSH tunnel:
ssh -i ~/.ssh/hetzner_ed25519 -L 8081:127.0.0.1:81 deploy@5.223.65.230
# Open: http://127.0.0.1:8081
```

**Edit the `dash.firstyjps.com` proxy host:**

| Field | Value |
|-------|-------|
| **Forward Hostname / IP** | `host.docker.internal` |
| **Forward Port** | `3000` |
| **Scheme** | `http` |
| **Websockets Support** | ✅ Enabled |
| **Block Common Exploits** | ✅ Enabled |

**SSL tab** (keep existing):
- Custom SSL certificate (Cloudflare origin cert)
- Force SSL: ✅

**Advanced tab** — add this to the Custom Nginx Configuration box:
```nginx
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

### Step 4: Verify

```bash
# On the server:

# 1. Containers running and healthy
docker compose ps
# Expected: backend (healthy), frontend (running)

# 2. Backend health (localhost)
curl -s http://127.0.0.1:8000/api/v1/health
# Expected: {"status":"ok",...}

# 3. Frontend serves HTML (localhost)
curl -s http://127.0.0.1:3000/ | head -5
# Expected: <!doctype html>...

# 4. API proxy works through frontend nginx (localhost)
curl -s http://127.0.0.1:3000/api/v1/health
# Expected: {"status":"ok",...}

# 5. No ports exposed publicly (only 127.0.0.1 bindings)
docker ps --format "table {{.Names}}\t{{.Ports}}"
# Expected: 127.0.0.1:3000->80/tcp, 127.0.0.1:8000->8000/tcp

# On your Mac:

# 6. Public HTTPS works
curl -I https://dash.firstyjps.com
# Expected: HTTP/2 200

# 7. API through public URL
curl -s https://dash.firstyjps.com/api/v1/health
# Expected: {"status":"ok",...}

# 8. WebSocket test (brief connect)
curl -s -o /dev/null -w "%{http_code}" \
  -H "Upgrade: websocket" -H "Connection: Upgrade" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Sec-WebSocket-Version: 13" \
  https://dash.firstyjps.com/ws
# Expected: 101 (switching protocols) or connection upgrade
```

---

## Rollback Plan

If something breaks after deployment:

```bash
cd ~/spread-dashboard

# Revert to previous commit
git log --oneline -5           # find the last working commit
git reset --hard <commit-sha>  # revert to it

# Rebuild and restart
docker compose up -d --build

# Verify
docker compose ps
curl -s http://127.0.0.1:3000/api/v1/health
```

If NPM config was changed and is broken:
- Access NPM admin via SSH tunnel
- Change Forward Hostname/IP back to the previous value
- Save

---

## Day-to-Day Operations

### View logs
```bash
cd ~/spread-dashboard
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs --tail=100 backend
```

### Restart services
```bash
docker compose restart backend
docker compose restart frontend
```

### Update code (automatic via CI)
GitHub Actions auto-deploys on push to `main`:
1. SSH into VPS
2. `git reset --hard origin/main`
3. `docker compose up -d --build`

### Manual update
```bash
cd ~/spread-dashboard
git pull origin main
docker compose up -d --build
```

### Access NPM admin
```bash
# On your Mac (SSH tunnel):
ssh -i ~/.ssh/hetzner_ed25519 -L 8081:127.0.0.1:81 deploy@5.223.65.230
# Open: http://127.0.0.1:8081
```

### Database backup
```bash
cp ~/spread-dashboard/backend/data/spread_dashboard.db \
   ~/spread-dashboard/backend/data/spread_dashboard.db.bak.$(date +%Y%m%d)
```

---

## Security Checklist

### Done
- [x] UFW active: only 22/80/443
- [x] Hetzner firewall: only 22/80/443
- [x] Cloudflare proxied (hides origin IP)
- [x] HTTPS via Cloudflare origin cert + Full (strict)
- [x] Separate deploy user (not root)
- [x] SSH key-only auth
- [x] App ports bound to 127.0.0.1 only
- [x] NPM admin bound to 127.0.0.1:81 only
- [x] No dev server in production (nginx static serving)
- [x] No source code volumes mounted
- [x] No `--reload` flag on uvicorn
- [x] Backend healthcheck configured
- [x] WebSocket uses wss:// over HTTPS

### Recommended
- [ ] Lock SSH to your IP in Hetzner firewall
- [ ] `chmod 600 ~/spread-dashboard/backend/.env`
- [ ] Disable root SSH: `PermitRootLogin no` in sshd_config
- [ ] Install fail2ban: `sudo apt install fail2ban && sudo systemctl enable fail2ban`
