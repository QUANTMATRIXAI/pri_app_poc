# Update Deployment Guide

This guide shows how to pull the latest code changes and redeploy the Docker container.

---

## Prerequisites

- Git installed
- Docker Desktop running
- Already cloned the repository once

---

## Update Steps

### 1. Navigate to project directory
```powershell
cd F:\pri_app
```

### 2. Pull latest changes and restart
```powershell
docker compose down
git reset --hard HEAD
git pull origin prilink
docker compose up --build -d
```

The `-d` flag runs containers in detached mode (background).

---

## Verify Deployment

### Check if container is running
```powershell
docker ps
```

You should see `pri_dashboard` in the list.

### View container logs
```powershell
docker logs pri_dashboard
```

### Access the app
Open browser and go to: `http://10.2.4.48:8517`

---

## Troubleshooting

### If DNS errors occur during build
The server might have DNS issues. Try:
```powershell
# Restart Docker Desktop, then retry
docker compose up --build -d
```

### If port is already in use
```powershell
# Stop all containers first
docker compose down

# Then rebuild
docker compose up --build -d
```

### View real-time logs
```powershell
docker logs -f pri_dashboard
```
Press `Ctrl+C` to stop viewing logs.

---

## Quick Reference

| Command | Purpose |
|---------|---------|
| `docker compose down` | Stop and remove containers |
| `docker compose up -d` | Start containers in background |
| `docker compose up --build -d` | Rebuild and start |
| `docker ps` | List running containers |
| `docker logs pri_dashboard` | View app logs |
| `git pull origin prilink` | Get latest code |

---

## Notes

- The `data/` folder persists between updates (database, uploads, media)
- Only code changes require rebuild
- Cloudflare tunnel runs separately (not affected by Docker updates)
