# AWS Lightsail Deployment Plan
## Trinity Dashboard - Production Deployment Strategy

**Document Version:** 1.0  
**Date:** January 2025  
**Prepared For:** Senior Management Review  
**Application:** Trinity Data Science Dashboard (Streamlit)

---

## Executive Summary

This document outlines the complete deployment strategy for hosting the Trinity Dashboard on AWS Lightsail. The solution is designed for 10-30 concurrent users with a focus on data persistence, security, and cost-effectiveness.

**Key Highlights:**
- **Monthly Cost:** $21-23/month
- **User Capacity:** 10-30 concurrent users (mostly viewers)
- **Data Safety:** 100% persistent with automatic weekly backups
- **Deployment Time:** 2-3 hours for initial setup
- **Scalability:** Easy upgrade path as user base grows

---

## 1. Infrastructure Overview

### 1.1 Hosting Platform: AWS Lightsail

**Why Lightsail?**
- Fixed, predictable pricing (no surprise bills)
- Persistent storage included (critical for SQLite + file uploads)
- Simple management interface
- Easy scaling path
- Automatic backup capabilities

**Alternative Considered:** Heroku
- **Rejected Reason:** Ephemeral filesystem - would lose all data (database + uploads) on every restart
- **Would Require:** Major code refactoring (SQLite → PostgreSQL, local storage → S3)

### 1.2 Selected Instance Specifications

| Specification | Value | Notes |
|---------------|-------|-------|
| **Plan** | $20/month | Linux/Unix bundle |
| **vCPUs** | 2 | Sufficient for 30 concurrent users |
| **RAM** | 2 GB | Handles Streamlit + data processing |
| **Storage** | 60 GB SSD | Persistent, high-performance |
| **Data Transfer** | 1.5 TB/month | More than sufficient for dashboard usage (Mumbai region) |
| **Region** | Asia Pacific (Mumbai) | Lowest latency for Indian users |

**Scaling Path:**
- Current: $20/month (10-30 users)
- Growth: $40/month plan (4GB RAM, 50+ users)
- Enterprise: $80/month plan (8GB RAM, 100+ users)

---

## 2. Architecture Design

### 2.1 Server Directory Structure

```
AWS Lightsail Instance
│
├── /home/ubuntu/pri_app/              # Application Code (Git Repository)
│   ├── app.py                         # Main Streamlit application
│   ├── requirements.txt               # Python dependencies
│   ├── Dockerfile                     # Container definition
│   ├── docker-compose.yml             # Orchestration config
│   ├── app_core/                      # Core business logic
│   │   ├── auth.py                    # User authentication
│   │   ├── database.py                # SQLite operations (WAL mode enabled)
│   │   ├── media.py                   # File upload handling
│   │   └── ...
│   ├── app_ui/                        # User interface modules
│   │   ├── dashboard.py               # Dashboard rendering
│   │   ├── data_studio.py             # Data configuration UI
│   │   └── ...
│   └── static/                        # Static assets
│
└── /srv/pri_dashboard/data/           # Persistent Data (OUTSIDE app folder)
    ├── db/
    │   └── app.db                     # SQLite database (WAL mode)
    ├── uploads/                       # User-uploaded datasets
    │   ├── dataset_2024.csv
    │   ├── market_data.xlsx
    │   └── ...
    └── media/                         # Dashboard images/slides
        ├── segment_analysis.png
        ├── brand_trends.pptx
        └── ...
```

**Key Design Decisions:**

1. **Separation of Code and Data**
   - Application code: `/home/ubuntu/pri_app/` (can be updated via Git)
   - Persistent data: `/srv/pri_dashboard/data/` (survives all updates)
   - Benefit: Clean deployments without data loss risk

2. **Docker Containerization**
   - Consistent environment (development = production)
   - Easy rollback capabilities
   - Simplified dependency management
   - Bind mount ensures data persistence

3. **Absolute Path Binding**
   - Docker volume: `/srv/pri_dashboard/data:/app/data`
   - Ensures data survives container rebuilds
   - No risk of accidental data deletion

### 2.2 Data Flow Diagram

```
User Browser
    ↓ (HTTPS - Port 443)
Nginx Reverse Proxy
    ↓ (HTTP - localhost:8501)
Streamlit App (Docker Container)
    ↓ (Read/Write)
/app/data/ (Container Path)
    ↓ (Bind Mount)
/srv/pri_dashboard/data/ (Host Disk)
    ↓ (Automatic Backup)
Lightsail Snapshots (Weekly)
```

---

## 3. Data Persistence & Safety

### 3.1 Database: SQLite with WAL Mode

**Current Implementation:**
- SQLite database with Write-Ahead Logging (WAL) enabled
- Busy timeout: 30 seconds (prevents "database locked" errors)
- Foreign keys enforced
- Automatic connection pooling

**Concurrency Handling:**
```python
# Already implemented in app_core/database.py
conn.execute("PRAGMA journal_mode = WAL")      # Unlimited concurrent readers
conn.execute("PRAGMA busy_timeout = 30000")    # 30s wait for write locks
conn.execute("PRAGMA foreign_keys = ON")       # Data integrity
```

**Performance Characteristics:**
- **Read Operations:** Unlimited concurrent users (WAL mode)
- **Write Operations:** Serialized with 30s timeout
- **Suitable For:** 10-30 users (mostly viewing dashboards)
- **Migration Path:** Can upgrade to PostgreSQL if >50 concurrent users

### 3.2 File Storage

**Upload Limits:**
- Streamlit default: 200 MB per file
- Current usage: ~40 MB CSV/Excel files
- No changes required

**Storage Locations:**
- User datasets: `/srv/pri_dashboard/data/uploads/`
- Dashboard media: `/srv/pri_dashboard/data/media/`
- All files persist indefinitely

### 3.3 Backup Strategy

#### Automatic Snapshots (Recommended)

| Parameter | Value |
|-----------|-------|
| **Frequency** | Weekly (every Sunday 2 AM UTC) |
| **Retention** | Latest 7 snapshots (rolling) |
| **Scope** | Entire server (OS + Docker + Data) |
| **Cost** | $0.05/GB-month (~$1-3/month) |
| **Restore Time** | 10-15 minutes (create new instance from snapshot) |

**Setup:** Enable in Lightsail Console → Instance → Snapshots → Enable Automatic

#### Manual Backup (Optional)

```bash
# Backup data folder only
sudo tar -czf backup_$(date +%Y%m%d).tar.gz /srv/pri_dashboard/data/

# Download to local machine
scp -i LightsailKey.pem ubuntu@SERVER_IP:/home/ubuntu/backup_*.tar.gz ./
```

**Recommendation:** Use automatic snapshots for disaster recovery, manual backups for archival.

---

## 4. Security Configuration

### 4.1 Network Security

**Firewall Rules (Lightsail Console):**

| Port | Protocol | Source | Purpose |
|------|----------|--------|---------|
| 22 | TCP | Your Office IP | SSH access (restrict to known IPs) |
| 80 | TCP | 0.0.0.0/0 | HTTP (redirects to HTTPS) |
| 443 | TCP | 0.0.0.0/0 | HTTPS (production access) |
| 8501 | TCP | BLOCKED | Streamlit (only accessible via Nginx) |

**Key Security Measures:**
1. Streamlit bound to `localhost:8501` only (not publicly accessible)
2. All traffic routed through Nginx reverse proxy
3. HTTPS encryption with Let's Encrypt SSL certificate
4. SSH access restricted to specific IP addresses

### 4.2 Application Security

**Already Implemented:**
- User authentication system (`app_core/auth.py`)
- Role-based access control (Admin, Editor, Viewer)
- SQL injection protection (parameterized queries)
- Path traversal protection (validated file paths)
- Session management

**Additional Recommendations:**
- Change default admin password on first deployment
- Regular security updates: `sudo apt update && sudo apt upgrade`
- Monitor failed login attempts
- Consider adding rate limiting for login attempts

### 4.3 SSL/TLS Configuration

**Option 1: With Custom Domain (Recommended)**
```bash
# Free SSL certificate from Let's Encrypt
sudo certbot --nginx -d yourdomain.com
# Auto-renewal configured automatically
```

**Option 2: Without Domain (Self-Signed)**
```bash
# Self-signed certificate (browser warning)
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/nginx-selfsigned.key \
  -out /etc/ssl/certs/nginx-selfsigned.crt
```

---

## 5. Deployment Procedure

### 5.1 Phase 1: Initial Setup (1-2 hours)

#### Step 1: Create Lightsail Instance

1. Log in to AWS Console → Lightsail
2. Click "Create Instance"
3. Select:
   - Platform: Linux/Unix
   - Blueprint: Ubuntu 22.04 LTS
   - Plan: $20/month (2GB RAM, 2 vCPU, 60GB SSD)
   - Instance name: `pri-dashboard-prod`
4. Click "Create Instance"
5. Wait 2-3 minutes for instance to start

#### Step 2: Attach Static IP

1. Go to Networking tab
2. Click "Create static IP"
3. Attach to `pri-dashboard-prod`
4. Name: `pri-dashboard-ip`
5. **Cost: FREE** (when attached to running instance)

#### Step 3: Configure Firewall

1. Go to Networking → Firewall
2. Add rules:
   - SSH (22) - Restrict to your office IP
   - HTTP (80) - Allow all
   - HTTPS (443) - Allow all
3. Save changes

#### Step 4: Connect via SSH

```bash
# Download SSH key from Lightsail console
chmod 400 LightsailKey.pem

# Connect to server
ssh -i LightsailKey.pem ubuntu@YOUR_STATIC_IP
```

#### Step 5: Install Docker & Docker Compose

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker ubuntu

# Install Docker Compose
sudo apt install docker-compose -y

# Verify installation
docker --version
docker-compose --version

# Logout and login for group changes to take effect
exit
# SSH back in
```

#### Step 6: Create Data Directory Structure

```bash
# Create persistent data folder
sudo mkdir -p /srv/pri_dashboard/data/{db,uploads,media}
sudo chown -R ubuntu:ubuntu /srv/pri_dashboard

# Verify structure
tree /srv/pri_dashboard/
```

#### Step 7: Clone Application Repository

```bash
cd /home/ubuntu
git clone https://github.com/QUANTMATRIXAI/pri_app.git
cd pri_app
git checkout prilink  # or your production branch

# Verify files
ls -la
```

#### Step 8: Update docker-compose.yml

```bash
# Edit docker-compose.yml
nano docker-compose.yml
```

**Change this section:**
```yaml
# BEFORE:
volumes:
  - ./data:/app/data

# AFTER:
volumes:
  - /srv/pri_dashboard/data:/app/data
```

**Also update ports (for Nginx):**
```yaml
# BEFORE:
ports:
  - "8501:8501"

# AFTER:
ports:
  - "127.0.0.1:8501:8501"  # Only localhost
```

Save and exit (Ctrl+X, Y, Enter)

#### Step 9: Build and Run Application

```bash
# Build Docker image
docker-compose build

# Start application
docker-compose up -d

# Verify running
docker ps
docker logs pri_dashboard

# Test locally
curl http://localhost:8501
```

#### Step 10: Enable Automatic Snapshots

1. Lightsail Console → Your Instance
2. Snapshots tab
3. Click "Enable automatic snapshots"
4. Schedule: Weekly (Sunday 2 AM UTC)
5. Retention: 7 snapshots
6. Click "Enable"

**Initial deployment complete!** Access at `http://YOUR_STATIC_IP:8501`

---

### 5.2 Phase 2: Production Hardening (1 hour)

#### Step 11: Install Nginx Reverse Proxy

```bash
# Install Nginx and Certbot
sudo apt install nginx certbot python3-certbot-nginx -y

# Create Nginx configuration
sudo nano /etc/nginx/sites-available/pri-dashboard
```

**Nginx Configuration:**
```nginx
server {
    listen 80;
    server_name YOUR_DOMAIN_OR_IP;

    # Redirect HTTP to HTTPS (after SSL setup)
    # return 301 https://$server_name$request_uri;

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
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/pri-dashboard /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx
sudo systemctl enable nginx
```

#### Step 12: Configure SSL/HTTPS (If Domain Available)

```bash
# Get free SSL certificate from Let's Encrypt
sudo certbot --nginx -d yourdomain.com

# Follow prompts:
# - Enter email address
# - Agree to terms
# - Choose: Redirect HTTP to HTTPS (option 2)

# Verify auto-renewal
sudo certbot renew --dry-run
```

**If no domain:** Skip this step, access via `http://YOUR_STATIC_IP`

#### Step 13: Update Firewall (Remove Direct Streamlit Access)

1. Lightsail Console → Networking → Firewall
2. Ensure only these ports are open:
   - SSH (22) - Restricted to your IP
   - HTTP (80) - All
   - HTTPS (443) - All
3. Port 8501 should NOT be in the list

**Production deployment complete!** Access at `https://yourdomain.com` or `http://YOUR_STATIC_IP`

---

## 6. Maintenance & Operations

### 6.1 Routine Maintenance Tasks

#### Daily
- Monitor application logs: `docker logs pri_dashboard -f`
- Check disk space: `df -h`

#### Weekly
- Review automatic snapshot status
- Check for security updates: `sudo apt update`

#### Monthly
- Apply security updates: `sudo apt upgrade -y`
- Review user access logs
- Verify backup restore process (test once)

### 6.2 Common Operations

#### Update Application Code

```bash
cd /home/ubuntu/pri_app
git pull origin prilink
docker-compose down
docker-compose build
docker-compose up -d

# Verify
docker logs pri_dashboard
```

#### Restart Application

```bash
docker-compose restart
# or
docker-compose down && docker-compose up -d
```

#### View Logs

```bash
# Real-time logs
docker logs pri_dashboard -f

# Last 100 lines
docker logs pri_dashboard --tail 100

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

#### Check Resource Usage

```bash
# Disk space
df -h
du -sh /srv/pri_dashboard/data/*

# Memory usage
free -h

# Docker stats
docker stats pri_dashboard

# System load
htop  # (install: sudo apt install htop)
```

#### Backup Data Manually

```bash
# Create backup
sudo tar -czf /home/ubuntu/backup_$(date +%Y%m%d_%H%M%S).tar.gz \
  /srv/pri_dashboard/data/

# Download to local machine
scp -i LightsailKey.pem \
  ubuntu@YOUR_IP:/home/ubuntu/backup_*.tar.gz \
  ./backups/
```

#### Restore from Snapshot

1. Lightsail Console → Snapshots
2. Select snapshot to restore
3. Click "Create new instance from snapshot"
4. Choose same plan ($20/month)
5. Wait 10-15 minutes
6. Attach static IP to new instance
7. Test application
8. Delete old instance if successful

### 6.3 Monitoring & Alerts

**Lightsail Built-in Metrics:**
- CPU utilization
- Network in/out
- Disk read/write
- Status check failures

**Recommended Alerts:**
1. CPU > 80% for 10 minutes
2. Disk usage > 85%
3. Status check failures

**Setup:** Lightsail Console → Metrics → Create Alarm

---

## 7. Cost Analysis

### 7.1 Monthly Cost Breakdown

| Item | Cost | Notes |
|------|------|-------|
| Lightsail Instance | $20.00 | 2 vCPU, 2GB RAM, 60GB SSD |
| Static IP | $0.00 | Free when attached |
| Automatic Snapshots | $1.50 | ~30GB data × $0.05/GB |
| Data Transfer | $0.00 | Included (3TB/month) |
| SSL Certificate | $0.00 | Let's Encrypt (free) |
| **Total** | **$21.50/month** | **~$258/year** |

### 7.2 Scaling Costs

| User Count | Plan | Monthly Cost | Notes |
|------------|------|--------------|-------|
| 10-30 users | $20 (2GB RAM) | $21.50 | Current recommendation |
| 30-50 users | $40 (4GB RAM) | $41.50 | Simple upgrade |
| 50-100 users | $80 (8GB RAM) | $81.50 | + Consider PostgreSQL |
| 100+ users | Custom | $150+ | Multi-instance + RDS |

**Upgrade Process:** 
- Takes 5 minutes in Lightsail console
- Zero downtime with snapshot → new instance → switch IP
- Can upgrade/downgrade anytime

### 7.3 Cost Comparison

| Platform | Monthly Cost | Data Persistence | Setup Complexity |
|----------|--------------|------------------|------------------|
| **AWS Lightsail** | **$21.50** | ✅ Yes | Medium |
| Heroku | $25-50 | ❌ No (requires S3 + RDS) | Low |
| AWS EC2 | $30-40 | ✅ Yes | High |
| DigitalOcean | $24 | ✅ Yes | Medium |
| Streamlit Cloud | $0-250 | ✅ Yes | Very Low |

**Verdict:** Lightsail offers best value for this use case.

---

## 8. Risk Assessment & Mitigation

### 8.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Data loss due to disk failure | Low | Critical | Automatic weekly snapshots |
| Database locked errors | Low | Medium | WAL mode + 30s timeout (implemented) |
| Server downtime | Low | High | Snapshot-based recovery (15 min) |
| Exceeded storage capacity | Medium | Medium | Monitor disk usage, upgrade plan |
| SSL certificate expiration | Low | Medium | Certbot auto-renewal (configured) |
| Concurrent user overload | Low | Medium | Upgrade to $40 plan (5 min) |

### 8.2 Security Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Unauthorized access | Medium | High | Authentication system, HTTPS, firewall |
| SQL injection | Low | High | Parameterized queries (implemented) |
| DDoS attack | Low | Medium | Lightsail DDoS protection (built-in) |
| Data breach | Low | Critical | Encrypted connections, access controls |
| Brute force login | Medium | Medium | Consider rate limiting |

### 8.3 Operational Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Accidental instance deletion | Low | Critical | Require confirmation, snapshots |
| Failed deployment | Medium | Medium | Test in staging, rollback via Git |
| Dependency conflicts | Low | Medium | Docker ensures consistency |
| Knowledge loss | Medium | High | This documentation |

---

## 9. Performance Expectations

### 9.1 Expected Performance Metrics

| Metric | Expected Value | Notes |
|--------|----------------|-------|
| Page Load Time | 2-4 seconds | First load (includes data fetch) |
| Dashboard Refresh | <1 second | Cached data |
| File Upload (40MB) | 10-15 seconds | Depends on user internet |
| Concurrent Viewers | 30+ | Read-only operations (WAL mode) |
| Concurrent Editors | 5-10 | Write operations (serialized) |
| Database Query Time | <500ms | Most queries |
| Uptime | 99.5%+ | Lightsail SLA |

### 9.2 Load Testing Recommendations

**Before Production Launch:**
1. Test with 10 concurrent users (viewing dashboards)
2. Test with 3 concurrent users (uploading data)
3. Test with 40MB file upload
4. Monitor CPU/RAM usage during tests
5. Verify no "database locked" errors

**Tools:**
- Apache JMeter (load testing)
- Locust (Python-based load testing)
- Streamlit built-in metrics

---

## 10. Disaster Recovery Plan

### 10.1 Recovery Time Objectives (RTO)

| Scenario | RTO | Procedure |
|----------|-----|-----------|
| Application crash | 2 minutes | `docker-compose restart` |
| Server reboot | 5 minutes | Auto-restart (configured) |
| Corrupted deployment | 10 minutes | Rollback via Git + rebuild |
| Complete server failure | 15 minutes | Restore from snapshot |
| Data corruption | 30 minutes | Restore from snapshot + verify |

### 10.2 Recovery Procedures

#### Scenario 1: Application Not Responding

```bash
# Check if container is running
docker ps

# Restart container
docker-compose restart

# If still failing, check logs
docker logs pri_dashboard --tail 100

# Rebuild if necessary
docker-compose down
docker-compose build
docker-compose up -d
```

#### Scenario 2: Database Corruption

```bash
# Stop application
docker-compose down

# Restore from latest snapshot (Lightsail Console)
# OR restore from manual backup
cd /srv/pri_dashboard/
sudo rm -rf data/
sudo tar -xzf /home/ubuntu/backup_YYYYMMDD.tar.gz

# Restart application
docker-compose up -d
```

#### Scenario 3: Complete Server Failure

1. Lightsail Console → Snapshots
2. Select most recent snapshot
3. Click "Create new instance from snapshot"
4. Choose same plan ($20/month)
5. Wait 10-15 minutes for instance creation
6. Detach static IP from old instance
7. Attach static IP to new instance
8. Verify application: `https://yourdomain.com`
9. Delete failed instance

**Total Recovery Time:** 15-20 minutes

---

## 11. Future Enhancements

### 11.1 Short-term (3-6 months)

1. **Custom Domain Setup**
   - Register domain (e.g., dashboard.company.com)
   - Configure DNS in Route 53
   - Enable HTTPS with Let's Encrypt
   - Cost: ~$12/year (domain)

2. **Monitoring Dashboard**
   - Set up CloudWatch integration
   - Create custom metrics dashboard
   - Configure email alerts
   - Cost: Free tier sufficient

3. **Automated Deployments**
   - GitHub Actions for CI/CD
   - Automatic testing before deployment
   - Zero-downtime deployments
   - Cost: Free (GitHub Actions)

### 11.2 Long-term (6-12 months)

1. **Database Migration (if >50 users)**
   - Migrate SQLite → PostgreSQL (AWS RDS)
   - Better concurrency handling
   - Automated backups
   - Cost: +$15-30/month

2. **Multi-Region Deployment**
   - Deploy in multiple AWS regions
   - Load balancing
   - Disaster recovery
   - Cost: +$40-60/month

3. **Advanced Analytics**
   - User behavior tracking
   - Performance monitoring
   - Usage analytics
   - Cost: Varies

---

## 12. Success Criteria

### 12.1 Technical Success Metrics

- ✅ Application accessible 24/7 (99.5%+ uptime)
- ✅ Page load time <4 seconds
- ✅ Support 30 concurrent users without performance degradation
- ✅ Zero data loss incidents
- ✅ Successful weekly backups
- ✅ SSL/HTTPS enabled (if domain available)

### 12.2 Business Success Metrics

- ✅ Monthly cost within budget ($25/month)
- ✅ User satisfaction with performance
- ✅ No security incidents
- ✅ Easy maintenance (< 2 hours/month)
- ✅ Successful disaster recovery test

---

## 13. Approval & Sign-off

### 13.1 Deployment Checklist

- [ ] Infrastructure costs approved ($21.50/month)
- [ ] AWS account credentials obtained
- [ ] Domain name registered (if applicable)
- [ ] Deployment timeline approved
- [ ] Backup strategy approved
- [ ] Security measures reviewed
- [ ] Disaster recovery plan accepted
- [ ] Maintenance responsibilities assigned

### 13.2 Stakeholder Approval

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Technical Lead | | | |
| Senior Management | | | |
| IT Security | | | |
| Finance/Budget | | | |

---

## 14. Appendices

### Appendix A: Technical Specifications

**Application Stack:**
- Frontend: Streamlit 1.x
- Backend: Python 3.10+
- Database: SQLite 3.x (WAL mode)
- Data Processing: Pandas, DuckDB
- Containerization: Docker 24.x, Docker Compose 2.x
- Web Server: Nginx 1.18+
- SSL: Let's Encrypt (Certbot)

**Dependencies:**
- See `requirements.txt` in repository
- All dependencies containerized via Docker

### Appendix B: Contact Information

**Technical Support:**
- AWS Support: https://console.aws.amazon.com/support/
- Lightsail Documentation: https://lightsail.aws.amazon.com/ls/docs/

**Application Support:**
- Repository: https://github.com/QUANTMATRIXAI/pri_app
- Branch: prilink

### Appendix C: Useful Commands Reference

```bash
# Application Management
docker-compose up -d              # Start application
docker-compose down               # Stop application
docker-compose restart            # Restart application
docker-compose logs -f            # View logs
docker-compose build              # Rebuild image

# System Maintenance
sudo apt update                   # Check for updates
sudo apt upgrade -y               # Install updates
df -h                            # Check disk space
free -h                          # Check memory
htop                             # System monitor

# Backup & Restore
sudo tar -czf backup.tar.gz /srv/pri_dashboard/data/  # Backup
sudo tar -xzf backup.tar.gz                           # Restore

# Nginx
sudo systemctl restart nginx      # Restart Nginx
sudo nginx -t                     # Test config
sudo certbot renew               # Renew SSL

# Git Operations
git pull origin prilink          # Update code
git log --oneline -10            # View recent commits
git checkout <commit>            # Rollback to commit
```

### Appendix D: Troubleshooting Guide

**Problem:** Application not accessible
```bash
# Check if container is running
docker ps

# Check logs
docker logs pri_dashboard

# Check Nginx
sudo systemctl status nginx
```

**Problem:** Database locked errors
```bash
# Already mitigated with WAL mode
# If still occurring, check concurrent users
# Consider upgrading to PostgreSQL
```

**Problem:** Out of disk space
```bash
# Check usage
df -h
du -sh /srv/pri_dashboard/data/*

# Clean Docker
docker system prune -a

# Upgrade to larger plan if needed
```

**Problem:** Slow performance
```bash
# Check resources
docker stats pri_dashboard
htop

# Consider upgrading to $40 plan
```

---

## Document Control

**Version History:**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | Jan 2025 | Development Team | Initial deployment plan |

**Review Schedule:** Quarterly or after major changes

**Next Review Date:** April 2025

---

**END OF DOCUMENT**
