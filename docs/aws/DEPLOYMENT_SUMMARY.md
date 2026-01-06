# Trinity Dashboard - AWS Deployment Summary
## Production Instance Details

**Deployment Date:** January 6, 2026  
**Status:** ✅ LIVE & RUNNING  
**Deployed By:** Development Team

---

## 🌐 Access Information

### **Application URL**
```
http://13.205.110.57:8517
```

**Access:** Public (anyone with URL can access)  
**Uptime:** 24/7  
**Region:** Asia Pacific (Mumbai)

---

## 🖥️ Server Details

### **AWS Lightsail Instance**

| Property | Value |
|----------|-------|
| **Instance Name** | `pri-dashboard-prod` |
| **Instance ID** | (Check Lightsail console) |
| **Region** | Asia Pacific (Mumbai) |
| **Availability Zone** | Mumbai, Zone A |
| **Operating System** | Ubuntu 22.04 LTS |
| **Instance Plan** | $20/month |
| **vCPUs** | 2 |
| **RAM** | 2 GB |
| **Storage** | 60 GB SSD |
| **Data Transfer** | 1.5 TB/month |

### **Network Configuration**

| Property | Value |
|----------|-------|
| **Public IPv4** | `13.205.110.57` |
| **Static IP Name** | `pri-dashboard-ip` |
| **Private IPv4** | `172.26.5.83` |
| **Network Type** | Dual-stack (IPv4 and IPv6) |

### **Firewall Rules**

| Port | Protocol | Application | Purpose |
|------|----------|-------------|---------|
| 22 | TCP | SSH | Server management |
| 80 | TCP | HTTP | Web access (future) |
| 443 | TCP | HTTPS | Secure web access (future) |
| 8517 | TCP | Custom | Streamlit application |

---

## 🔐 SSH Access

### **Connection Method**

**Via Lightsail Browser SSH:**
1. Go to: https://lightsail.aws.amazon.com
2. Click on instance: `pri-dashboard-prod`
3. Click terminal icon (>_)

**Via SSH Client:**
```bash
ssh -i LightsailKey.pem ubuntu@13.205.110.57
```

### **SSH Key Location**
- **Key Name:** Default key for Asia Pacific (Mumbai)
- **Downloaded As:** `LightsailKey.pem`
- **Local Path:** `C:\Users\YourName\Downloads\LightsailKey.pem`
- **Username:** `ubuntu`

---

## 📁 Directory Structure

### **Application Code**
```
/home/ubuntu/pri_app/
├── app.py                    # Main Streamlit application
├── requirements.txt          # Python dependencies
├── Dockerfile               # Docker image definition
├── docker-compose.yml       # Docker orchestration
├── app_core/                # Core business logic
├── app_ui/                  # User interface modules
└── static/                  # Static assets
```

### **Persistent Data (CRITICAL - DO NOT DELETE)**
```
/srv/pri_dashboard/data/
├── db/
│   └── app.db              # SQLite database (all user data)
├── uploads/                # User-uploaded CSV/Excel files
│   └── (dataset files)
└── media/                  # Dashboard images/slides
    └── (uploaded images)
```

**⚠️ WARNING:** The `/srv/pri_dashboard/data/` folder contains ALL your data. Never delete this!

---

## 🐳 Docker Configuration

### **Container Details**

| Property | Value |
|----------|-------|
| **Container Name** | `pri_dashboard` |
| **Image** | `pri_app_dashboard:latest` |
| **Status** | Running |
| **Port Mapping** | `0.0.0.0:8517 → 8517/tcp` |
| **Restart Policy** | `unless-stopped` |
| **Volume Mount** | `/srv/pri_dashboard/data:/app/data` |

### **Docker Compose Configuration**
```yaml
services:
  dashboard:
    build: .
    container_name: pri_dashboard
    ports:
      - "0.0.0.0:8517:8517"
    volumes:
      - /srv/pri_dashboard/data:/app/data
    restart: unless-stopped
```

---

## 🔧 Management Commands

### **Application Management**

```bash
# View application logs (real-time)
docker logs pri_dashboard -f

# View last 100 lines of logs
docker logs pri_dashboard --tail 100

# Restart application
cd /home/ubuntu/pri_app
docker-compose restart

# Stop application
docker-compose down

# Start application
docker-compose up -d

# Check if running
docker ps

# Check resource usage
docker stats pri_dashboard
```

### **System Management**

```bash
# Check disk space
df -h

# Check data folder size
du -sh /srv/pri_dashboard/data/*

# Check memory usage
free -h

# Check system load
htop

# Update system packages
sudo apt update && sudo apt upgrade -y
```

### **Update Application Code**

```bash
# Connect to server
ssh -i LightsailKey.pem ubuntu@13.205.110.57

# Navigate to app folder
cd /home/ubuntu/pri_app

# Pull latest code from GitHub
git pull origin prilink

# Rebuild and restart
docker-compose down
docker-compose build
docker-compose up -d

# Verify it's running
docker ps
docker logs pri_dashboard --tail 50
```

---

## 💾 Backup Strategy

### **Automatic Snapshots**

**Status:** ⚠️ NOT YET ENABLED (Recommended to enable)

**To Enable:**
1. Go to Lightsail Console
2. Click on instance: `pri-dashboard-prod`
3. Go to "Snapshots" tab
4. Click "Enable automatic snapshots"
5. Schedule: Weekly (Sunday 2 AM UTC)
6. Retention: 7 snapshots

**Cost:** ~$1-3/month (based on data size)

### **Manual Backup**

```bash
# Backup data folder
sudo tar -czf /home/ubuntu/backup_$(date +%Y%m%d_%H%M%S).tar.gz \
  /srv/pri_dashboard/data/

# Download to local machine
scp -i LightsailKey.pem \
  ubuntu@13.205.110.57:/home/ubuntu/backup_*.tar.gz \
  ./backups/
```

### **Restore from Snapshot**

1. Lightsail Console → Snapshots
2. Select snapshot to restore
3. Click "Create new instance from snapshot"
4. Choose same plan ($20/month)
5. Wait 10-15 minutes
6. Detach static IP from old instance
7. Attach static IP to new instance
8. Test application
9. Delete old instance

---

## 💰 Cost Breakdown

### **Monthly Costs**

| Item | Cost | Notes |
|------|------|-------|
| Lightsail Instance | $20.00 | 2 vCPU, 2GB RAM, 60GB SSD |
| Static IP | $0.00 | Free when attached |
| Automatic Snapshots | $1-3.00 | ~30GB data × $0.05/GB |
| Data Transfer | $0.00 | Included (1.5TB/month) |
| **Total** | **$21-23/month** | **~$258/year** |

### **Scaling Costs**

| User Count | Plan | Monthly Cost | When to Upgrade |
|------------|------|--------------|-----------------|
| 10-30 users | $20 (2GB) | $21-23 | Current |
| 30-50 users | $40 (4GB) | $41-43 | If app feels slow |
| 50-100 users | $80 (8GB) | $81-83 | High traffic |

---

## 🔒 Security Configuration

### **Current Security Measures**

- ✅ Firewall configured (only necessary ports open)
- ✅ SSH key authentication (no password login)
- ✅ Application-level authentication (login required)
- ✅ SQLite with WAL mode (prevents database locks)
- ✅ Parameterized queries (SQL injection protection)
- ✅ Path validation (file system security)

### **Future Security Enhancements**

- ⏳ Add Nginx reverse proxy
- ⏳ Enable HTTPS with Let's Encrypt
- ⏳ Restrict SSH to specific IP addresses
- ⏳ Set up CloudWatch monitoring
- ⏳ Configure automated security updates

---

## 📊 Performance Specifications

### **Expected Performance**

| Metric | Value | Notes |
|--------|-------|-------|
| Page Load Time | 2-4 seconds | First load |
| Dashboard Refresh | <1 second | Cached data |
| File Upload (40MB) | 10-15 seconds | Depends on user internet |
| Concurrent Viewers | 30+ | Read-only operations |
| Concurrent Editors | 5-10 | Write operations |
| Database Query Time | <500ms | Most queries |
| Uptime | 99.5%+ | Lightsail SLA |

### **Resource Usage (Typical)**

- **CPU:** 10-30% (idle), 50-80% (active users)
- **RAM:** 500MB-1.5GB (depends on data size)
- **Disk:** ~5GB (app + data)
- **Network:** 1-5 GB/day (typical usage)

---

## 🚨 Troubleshooting

### **App Not Accessible**

**Problem:** Can't access `http://13.205.110.57:8517`

**Solutions:**
1. Check if container is running: `docker ps`
2. Check firewall: Port 8517 must be open
3. Check logs: `docker logs pri_dashboard`
4. Restart app: `docker-compose restart`

### **Container Not Running**

**Problem:** `docker ps` shows no containers

**Solutions:**
```bash
cd /home/ubuntu/pri_app
docker-compose up -d
docker logs pri_dashboard
```

### **Database Locked Errors**

**Problem:** Users see "database is locked" errors

**Solutions:**
- Already mitigated with WAL mode
- If still occurring, check concurrent users
- Consider upgrading to $40 plan (more RAM)

### **Out of Disk Space**

**Problem:** App crashes, can't upload files

**Solutions:**
```bash
# Check disk usage
df -h

# Clean Docker
docker system prune -a

# If still full, upgrade to larger plan
```

### **Slow Performance**

**Problem:** App is slow, pages take long to load

**Solutions:**
```bash
# Check resource usage
docker stats pri_dashboard
htop

# If CPU/RAM maxed out, upgrade to $40 plan
```

---

## 📞 Support & Resources

### **AWS Support**
- Console: https://console.aws.amazon.com/support/
- Lightsail Docs: https://lightsail.aws.amazon.com/ls/docs/

### **Application Repository**
- GitHub: https://github.com/QUANTMATRIXAI/pri_app
- Branch: `prilink`

### **Documentation**
- Deployment Guide: `docs/AWS_DEPLOYMENT_GUIDE.md`
- Detailed Explanation: `docs/DEPLOYMENT_EXPLAINED.md`
- Full Plan: `docs/AWS_DEPLOYMENT_PLAN.md`

---

## 📝 Change Log

### **January 6, 2026 - Initial Deployment**
- Created Lightsail instance in Mumbai region
- Installed Docker & Docker Compose
- Deployed Trinity Dashboard application
- Configured firewall rules
- Application live at: `http://13.205.110.57:8517`

---

## ✅ Post-Deployment Checklist

- [x] Instance created and running
- [x] Static IP attached
- [x] Firewall configured
- [x] Docker installed
- [x] Application deployed
- [x] App accessible via URL
- [ ] Automatic backups enabled (RECOMMENDED)
- [ ] Domain configured (OPTIONAL)
- [ ] HTTPS enabled (OPTIONAL)
- [ ] Nginx reverse proxy (OPTIONAL)

---

## 🎯 Next Steps

### **Immediate (This Week)**
1. ✅ Test all application features
2. ✅ Upload sample dataset
3. ✅ Create test dashboard
4. ⏳ Enable automatic snapshots
5. ⏳ Share URL with team

### **Short-term (This Month)**
1. Monitor performance and costs
2. Set up billing alerts
3. Document any issues
4. Train users on the application

### **Long-term (3-6 Months)**
1. Consider adding custom domain
2. Enable HTTPS with SSL certificate
3. Set up monitoring/alerts
4. Evaluate if need to upgrade plan

---

## 📋 Important Notes

### **⚠️ CRITICAL - DO NOT DELETE**
- `/srv/pri_dashboard/data/` - Contains ALL your data
- Static IP: `13.205.110.57` - Your permanent address
- Instance: `pri-dashboard-prod` - Your server

### **💡 TIPS**
- Take a snapshot before major changes
- Test updates in a separate instance first
- Monitor disk space regularly
- Keep GitHub token secure
- Document any custom changes

### **🔄 REGULAR MAINTENANCE**
- Weekly: Check application logs
- Monthly: Review costs and usage
- Monthly: Test backup restore process
- Quarterly: Update system packages
- Quarterly: Review security settings

---

## 📧 Contact Information

**Technical Owner:** [Your Name]  
**AWS Account:** [Your AWS Account ID]  
**Deployment Date:** January 6, 2026  
**Last Updated:** January 6, 2026

---

**END OF DOCUMENT**

---

## Quick Reference Card

```
APP URL:        http://13.205.110.57:8517
SSH:            ssh -i LightsailKey.pem ubuntu@13.205.110.57
RESTART:        docker-compose restart
LOGS:           docker logs pri_dashboard -f
DATA LOCATION:  /srv/pri_dashboard/data/
COST:           $21-23/month
STATUS:         ✅ RUNNING
```

**Save this document! You'll need it for managing your deployment.**
