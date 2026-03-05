# Production Deployment Guide — Spread Dashboard

## Architecture (Production)

```
Internet → Cloudflare (SSL) → Hetzner VPS (5.223.65.230)
                                 │
                          ┌──────┴──────┐
                          │  UFW (22/80/443 only)
                          └──────┬──────┘
                                 │
                     ┌───────────┴───────────┐
                     │  NPM (Nginx Proxy Mgr) │  ← ~/proxy
                     │  80:80, 443:443, 81:81 │
                     │  (81 not exposed by FW) │
                     └───────────┬───────────┘
                                 │  proxy-net (Docker network)
                     ┌───────────┴───────────┐
                     │  frontend (nginx)      │  ← ~/spread-dashboard
                     │  :80 (internal only)   │
                     │  Static files + proxy  │
                     └───────────┬───────────┘
                                 │  app-internal (Docker network)
                     ┌───────────┴───────────┐
                     │  backend (uvicorn)     │
                     │  :8000 (internal only) │
                     │  FastAPI + WebSocket   │
                     └───────────────────────┘
```

**Key principle:** Only NPM binds to host ports (80/443). Backend and frontend
are internal-only, reachable solely through Docker networks.

---

## Files Created

| File | Purpose |
|------|---------|
| `frontend/Dockerfile.prod` | Multi-stage build: Node → nginx |
| `frontend/nginx.conf` | Serves static + proxies /api, /ws to backend |
| `frontend/.dockerignore` | Excludes node_modules, dist from build context |
| `backend/Dockerfile.prod` | Production uvicorn (no --reload, no dev tools) |
| `backend/.dockerignore` | Excludes .venv, tests, data from build context |
| `docker-compose.prod.yml` | Production compose with health checks + networks |

---

## Migration Plan (Step-by-Step)

### Prerequisites
- SSH into server: `ssh -i ~/.ssh/hetzner_ed25519 deploy@5.223.65.230`
- All commands below run on the server as `deploy` user

### Phase 1: Push Code Changes to Server

```bash
# On your Mac — push changes to GitHub
cd ~/Desktop/Spread\ Dashboard
git add -A
git commit -m "Add production Docker setup"
git push

# On the server — pull changes
cd ~/spread-dashboard
git pull origin main
```

### Phase 2: Create Shared Docker Network

```bash
# Create the external network that NPM and app will share
docker network create proxy-net
```

### Phase 3: Connect NPM to proxy-net

Edit `~/proxy/docker-compose.yml` — add the external network:

```yaml
services:
  npm:
    image: 'jc21/nginx-proxy-manager:latest'
    restart: always
    ports:
      - '80:80'
      - '443:443'
      - '127.0.0.1:81:81'   # ← bind admin UI to localhost only!
    volumes:
      - ./data:/data
      - ./letsencrypt:/etc/letsencrypt
    networks:
      - proxy-net

networks:
  proxy-net:
    external: true
```

**Important:** Change `81:81` to `127.0.0.1:81:81` — this binds NPM admin
to localhost only, accessible only via SSH tunnel.

Restart NPM:
```bash
cd ~/proxy
docker compose down
docker compose up -d
```

### Phase 4: Stop Old App + Start Production

```bash
cd ~/spread-dashboard

# Stop old dev containers
docker compose down

# Verify backend/.env exists and has correct settings
# Add CORS_ORIGINS if not already set:
echo 'CORS_ORIGINS=https://dash.firstyjps.com' >> backend/.env

# Ensure data directory exists with correct permissions
mkdir -p backend/data
chmod 700 backend/data

# Build and start production containers
docker compose -f docker-compose.prod.yml build --no-cache
docker compose -f docker-compose.prod.yml up -d

# Verify containers are running and healthy
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=50 backend
docker compose -f docker-compose.prod.yml logs --tail=50 frontend
```

### Phase 5: Update NPM Proxy Host

In NPM admin (via SSH tunnel):
```bash
# On your Mac:
ssh -i ~/.ssh/hetzner_ed25519 -L 8081:127.0.0.1:81 deploy@5.223.65.230
# Then open: http://127.0.0.1:8081
```

Update the `dash.firstyjps.com` proxy host:
- **Forward Hostname/IP:** `frontend`  (Docker service name, not host IP!)
- **Forward Port:** `80`
- **Websockets Support:** ✅ Enabled
- **SSL:** Keep existing Cloudflare origin cert + Force SSL

### Phase 6: Verify Everything Works

```bash
# On the server:

# 1. Check containers are healthy
docker compose -f docker-compose.prod.yml ps

# 2. Test backend health (internal)
docker compose -f docker-compose.prod.yml exec backend \
  python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/api/v1/health').read().decode())"

# 3. Test frontend serves static files (internal)
docker compose -f docker-compose.prod.yml exec frontend \
  wget -qO- http://localhost:80/ | head -5

# 4. Test API proxy through frontend nginx (internal)
docker compose -f docker-compose.prod.yml exec frontend \
  wget -qO- http://localhost:80/api/v1/health

# 5. Test from outside (on your Mac)
curl -I https://dash.firstyjps.com
curl https://dash.firstyjps.com/api/v1/health
```

### Phase 7: Cleanup

```bash
# Remove old dev images
docker image prune -f

# Verify no host ports are exposed for app services
docker ps --format "table {{.Names}}\t{{.Ports}}" | grep spread
# Should show NO host port mappings (only internal ports)
```

---

## Day-to-Day Operations

### View logs
```bash
cd ~/spread-dashboard
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f frontend
docker compose -f docker-compose.prod.yml logs --tail=100 backend
```

### Restart services
```bash
docker compose -f docker-compose.prod.yml restart backend
docker compose -f docker-compose.prod.yml restart frontend
```

### Update code
```bash
cd ~/spread-dashboard
git pull origin main
docker compose -f docker-compose.prod.yml build --no-cache
docker compose -f docker-compose.prod.yml up -d
```

### Access NPM admin
```bash
# On your Mac (SSH tunnel):
ssh -i ~/.ssh/hetzner_ed25519 -L 8081:127.0.0.1:81 deploy@5.223.65.230
# Open: http://127.0.0.1:8081
```

### Database backup
```bash
cd ~/spread-dashboard
cp backend/data/spread_dashboard.db backend/data/spread_dashboard.db.bak
```

### Log rotation (add to crontab)
```bash
# Edit crontab: crontab -e
# Add:
0 3 * * * docker system prune -f --filter "until=72h" > /dev/null 2>&1
```

---

## Security Checklist

### ✅ Already Done
- [x] UFW active: only 22/80/443
- [x] Hetzner firewall: only 22/80/443
- [x] Cloudflare proxied (hides origin IP)
- [x] HTTPS via Cloudflare origin cert + Full (strict)
- [x] Separate deploy user (not root for daily use)
- [x] SSH key-only auth

### 🔧 Recommended Improvements
- [ ] **Lock SSH to your IP:** In Hetzner firewall, restrict TCP 22 source
      to your public IP (e.g., `203.0.113.5/32`). Find your IP: `curl ifconfig.me`
- [ ] **Bind NPM admin to localhost:** Change `81:81` to `127.0.0.1:81:81`
      in ~/proxy/docker-compose.yml (included in migration plan above)
- [ ] **Secure backend/.env:** `chmod 600 ~/spread-dashboard/backend/.env`
- [ ] **Disable root SSH login:** Edit `/etc/ssh/sshd_config`:
      `PermitRootLogin no` then `sudo systemctl reload sshd`
- [ ] **Install fail2ban:**
      ```bash
      sudo apt install fail2ban
      sudo systemctl enable fail2ban
      sudo systemctl start fail2ban
      ```
- [ ] **No app ports on host:** Verified by docker-compose.prod.yml using
      `expose` (internal) instead of `ports` (host-mapped)
- [ ] **Backend .env not in git:** Already in .gitignore ✅
- [ ] **Add CORS_ORIGINS to .env:** Set to `https://dash.firstyjps.com`
