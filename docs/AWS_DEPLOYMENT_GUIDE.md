# AWS Lightsail Deployment Guide
## Trinity Dashboard - Quick Setup

**Cost:** $21-23/month | **Users:** 10-30 concurrent | **Setup Time:** 2-3 hours

---

## 1. Infrastructure Setup

### Create Lightsail Instance
1. AWS Console → Lightsail → Create Instance
2. Select Region: **Asia Pacific (Mumbai)** - for Indian users
3. Select: Ubuntu 22.04 LTS, $20/month plan (2GB RAM, 2 vCPU)
4. Attach Static IP (FREE when attached)
5. Configure Firewall: Allow ports 22 (SSH), 80 (HTTP), 443 (HTTPS)

---

## 2. Server Setup

### Connect & Install Dependencies
```bash
# Connect via SSH
ssh -i LightsailKey.pem ubuntu@YOUR_STATIC_IP

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu
sudo apt install docker-compose -y

# Logout and login again
exit
```

### Create Data Directory
```bash
# Create persistent storage (OUTSIDE app folder)
sudo mkdir -p /srv/pri_dashboard/data/{db,uploads,media}
sudo chown -R ubuntu:ubuntu /srv/pri_dashboard
```

### Clone Application
```bash
cd /home/ubuntu
git clone https://github.com/QUANTMATRIXAI/pri_app.git
cd pri_app
git checkout prilink
```

---

## 3. Configure Application

### Update docker-compose.yml
```bash
nano docker-compose.yml
```

**Change this line:**
```yaml
# BEFORE:
volumes:
  - ./data:/app/data

# AFTER:
volumes:
  - /srv/pri_dashboard/data:/app/data
```

**Keep ports as-is for now:**
```yaml
ports:
  - "8501:8501"  # Accessible from internet (will change later)
```

### Build & Run
```bash
docker-compose build
docker-compose up -d

# Verify
docker ps
docker logs pri_dashboard
```

### Test Basic Access
```
http://YOUR_STATIC_IP:8501
```

**✅ Application should be accessible now!**

**Note:** We'll secure this with Nginx in the next step.

---

## 4. Install Nginx Reverse Proxy

### Install Nginx
```bash
sudo apt install nginx certbot python3-certbot-nginx -y
```

### Configure Nginx
```bash
sudo nano /etc/nginx/sites-available/pri-dashboard
```

**Paste this configuration:**
```nginx
server {
    listen 80;
    server_name YOUR_DOMAIN_OR_IP;

    # CRITICAL: Allow large file uploads (40MB+)
    client_max_body_size 200M;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support for Streamlit
        proxy_read_timeout 86400;
        
        # CRITICAL: Allow large uploads in proxy
        proxy_request_buffering off;
    }
}
```

**⚠️ IMPORTANT:** `client_max_body_size 200M;` is required for 40MB file uploads!

### Enable Site
```bash
# Enable configuration
sudo ln -s /etc/nginx/sites-available/pri-dashboard /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx
sudo systemctl enable nginx
```

### Secure Streamlit (Bind to Localhost Only)

Now that Nginx is working, secure Streamlit:

```bash
cd /home/ubuntu/pri_app
nano docker-compose.yml
```

**Change ports:**
```yaml
# BEFORE:
ports:
  - "8501:8501"

# AFTER:
ports:
  - "127.0.0.1:8501:8501"  # Only localhost
```

**Restart application:**
```bash
docker-compose down
docker-compose up -d
```

**Update Firewall (Remove Port 8501):**
1. Lightsail Console → Networking → Firewall
2. Ensure only these ports are open:
   - SSH (22)
   - HTTP (80)
   - HTTPS (443)
3. Port 8501 should NOT be listed

**✅ Now Streamlit is only accessible via Nginx!**

---

## 5. Enable HTTPS (Optional - If Domain Available)

```bash
# Get free SSL certificate
sudo certbot --nginx -d yourdomain.com

# Follow prompts and choose: Redirect HTTP to HTTPS
```

**If no domain:** Skip this step, access via `http://YOUR_STATIC_IP`

---

## 6. Enable Automatic Backups

1. Lightsail Console → Your Instance → Snapshots
2. Enable automatic snapshots
3. Schedule: Weekly (Sunday 2 AM)
4. Retention: 7 snapshots
5. Cost: ~$1-3/month

---

## 7. Verify Deployment

### Test Application Access
```
# Via Nginx (port 80)
http://YOUR_STATIC_IP

# Or with HTTPS (if configured)
https://yourdomain.com

# Direct Streamlit access should NOT work (secured)
http://YOUR_STATIC_IP:8501  ❌ Should timeout/refuse
```

### Test File Upload
1. Login to application
2. Upload a 40MB CSV file
3. Verify no "413 Request Entity Too Large" error

### Check Logs
```bash
# Application logs
docker logs pri_dashboard -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

---

## Common Operations

### Update Application
```bash
cd /home/ubuntu/pri_app
git pull origin prilink
docker-compose down
docker-compose build
docker-compose up -d
```

### Restart Application
```bash
docker-compose restart
```

### View Logs
```bash
docker logs pri_dashboard -f
```

### Check Disk Space
```bash
df -h
du -sh /srv/pri_dashboard/data/*
```

### Manual Backup
```bash
sudo tar -czf backup_$(date +%Y%m%d).tar.gz /srv/pri_dashboard/data/
```

---

## Troubleshooting

### Problem: 413 Request Entity Too Large
**Solution:** Check Nginx config has `client_max_body_size 200M;`
```bash
sudo nano /etc/nginx/sites-available/pri-dashboard
# Add: client_max_body_size 200M;
sudo nginx -t
sudo systemctl restart nginx
```

### Problem: Application not accessible
```bash
# Check container
docker ps
docker logs pri_dashboard

# Check Nginx
sudo systemctl status nginx
sudo nginx -t
```

### Problem: Database locked errors
**Already handled:** WAL mode enabled in `app_core/database.py`

### Problem: Out of disk space
```bash
# Check usage
df -h

# Clean Docker
docker system prune -a

# Upgrade plan if needed
```

---

## Cost Summary

| Item | Monthly Cost |
|------|--------------|
| Lightsail Instance ($20 plan) | $20.00 |
| Static IP (attached) | $0.00 |
| Automatic Snapshots | $1-3.00 |
| **Total** | **$21-23/month** |

---

## Security Checklist

- ✅ Streamlit bound to localhost only
- ✅ Nginx reverse proxy configured
- ✅ HTTPS enabled (if domain)
- ✅ Firewall: Only 22, 80, 443 open
- ✅ Automatic backups enabled
- ✅ SSH restricted to known IPs (recommended)

---

## Performance Expectations

- **Concurrent Viewers:** 30+ (read-only)
- **Concurrent Editors:** 5-10 (writes)
- **File Upload:** 40MB in 10-15 seconds
- **Page Load:** 2-4 seconds
- **Uptime:** 99.5%+

---

## Scaling Path

| Users | Plan | Monthly Cost | Action |
|-------|------|--------------|--------|
| 10-30 | $20 (2GB) | $21-23 | Current |
| 30-50 | $40 (4GB) | $41-43 | Upgrade in console (5 min) |
| 50+ | $80 (8GB) | $81-83 | + Consider PostgreSQL |

---

## Critical Configuration Summary

### 1. Docker Volume (Data Persistence)
```yaml
volumes:
  - /srv/pri_dashboard/data:/app/data  # Absolute path
```

### 2. Nginx Upload Limit (File Uploads)
```nginx
client_max_body_size 200M;  # Required for 40MB files
```

### 3. SQLite WAL Mode (Concurrency)
```python
# Already in app_core/database.py
PRAGMA journal_mode = WAL
PRAGMA busy_timeout = 30000
```

**These 3 configurations are CRITICAL for proper operation!**

---

## Support

**AWS Support:** https://console.aws.amazon.com/support/  
**Repository:** https://github.com/QUANTMATRIXAI/pri_app  
**Branch:** prilink

---

**Deployment Complete!** 🚀
