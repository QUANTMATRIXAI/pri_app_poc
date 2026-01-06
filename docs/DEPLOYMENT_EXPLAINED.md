# AWS Deployment - Complete Beginner's Guide
## Understanding Your Deployment from Scratch

**Total Time Required:** 2-3 hours (first time)  
**Your Experience Level:** Complete beginner ✅  
**Difficulty:** Medium (we'll explain everything!)

---

## ⏱️ Time Breakdown

| Phase | Time | What You'll Do |
|-------|------|----------------|
| **1. AWS Setup** | 15 min | Create account, launch server |
| **2. Server Preparation** | 30 min | Install software, create folders |
| **3. Deploy Application** | 30 min | Upload code, configure, run |
| **4. Add Security (Nginx)** | 45 min | Set up web server, HTTPS |
| **5. Testing & Verification** | 30 min | Test everything works |
| **Total** | **2.5 hours** | First-time deployment |

**Next time:** 30 minutes (you'll know what to do!)

---

## 🤔 Why AWS Lightsail Over Other Options?

### Option 1: Your Local Computer ❌
**Why NOT:**
- Your computer must run 24/7
- If you close laptop, app goes down
- No one can access when you're offline
- Your home internet IP changes
- Not professional

### Option 2: Heroku ❌
**Why NOT:**
- **CRITICAL ISSUE:** Deletes your data every 24 hours!
- Your SQLite database would disappear
- All uploaded files would be lost
- Would need major code changes (SQLite → PostgreSQL, files → S3)
- More expensive after changes

### Option 3: AWS EC2 ⚠️
**Why NOT (for beginners):**
- Too complex for first deployment
- Need to configure everything manually
- Easy to make security mistakes
- Billing can surprise you (not fixed price)
- Requires more technical knowledge

### Option 4: AWS Lightsail ✅ **WINNER!**
**Why YES:**
- ✅ **Fixed price:** $20/month, no surprises
- ✅ **Your data stays forever:** SQLite + files persist
- ✅ **Simple interface:** Easier than EC2
- ✅ **Runs 24/7:** Always accessible
- ✅ **Professional:** Real server, real IP address
- ✅ **Scalable:** Easy to upgrade as you grow
- ✅ **Backups included:** Automatic snapshots
- ✅ **No code changes needed:** Works as-is

---

## 📊 Comparison Table

| Feature | Local PC | Heroku | AWS EC2 | AWS Lightsail |
|---------|----------|--------|---------|---------------|
| **Cost** | Free | $25-50/mo | $30-40/mo | $20/mo |
| **24/7 Uptime** | ❌ No | ✅ Yes | ✅ Yes | ✅ Yes |
| **Data Persists** | ✅ Yes | ❌ No | ✅ Yes | ✅ Yes |
| **Setup Difficulty** | Easy | Medium | Hard | Medium |
| **Code Changes** | None | Major | None | None |
| **Beginner Friendly** | ✅ Yes | ⚠️ No | ❌ No | ✅ Yes |
| **Fixed Pricing** | ✅ Yes | ⚠️ Varies | ❌ No | ✅ Yes |
| **Auto Backups** | ❌ No | ⚠️ Paid | ⚠️ Manual | ✅ Yes |
| **Scalability** | ❌ No | ✅ Yes | ✅ Yes | ✅ Yes |
| **Professional** | ❌ No | ✅ Yes | ✅ Yes | ✅ Yes |

**Verdict:** AWS Lightsail is the best balance of simplicity, cost, and features for your first deployment.

---

## 🎯 What You're Actually Building

Think of it like building a house:

### Your Current Situation (Local Computer)
```
Your Laptop
└── Trinity App running
    └── Only you can access it
    └── Stops when you close laptop
```

### After Deployment (AWS Lightsail)
```
AWS Server (Always Running)
├── Your App (24/7 accessible)
├── Database (SQLite - all your data)
├── Uploaded Files (images, CSVs)
└── Web Server (Nginx - security guard)
    └── Internet → Anyone can access via URL
```

---

## 🏗️ Step-by-Step Explanation (What & Why)

### **Phase 1: Create Your Server (15 minutes)**

#### What is AWS Lightsail?
Think of it as **renting a computer in the cloud** that runs 24/7.

#### What You'll Do:
1. **Create AWS Account** (if you don't have one)
   - Go to aws.amazon.com
   - Sign up (need credit card, but won't charge yet)
   - Verify email

2. **Launch a Server (called "Instance")**
   - Choose Region: **Asia Pacific (Mumbai)** - fastest for Indian users
   - Choose: Ubuntu (type of operating system)
   - Choose: $20/month plan (2GB RAM, 2 CPUs)
   - Click "Create"
   - Wait 2 minutes for server to start

3. **Get a Static IP (Free!)**
   - This is your server's permanent address
   - Like a phone number that never changes
   - Attach it to your server

#### Why This Matters:
- Your app needs a permanent home
- Static IP means the address never changes
- Users can always find your app at the same URL

---

### **Phase 2: Prepare Your Server (30 minutes)**

#### What is SSH?
**SSH = Secure Shell** - It's like remote control for your server.  
You'll type commands on your laptop, but they run on the AWS server.

#### What You'll Do:

**Step 1: Connect to Server**
```bash
ssh -i LightsailKey.pem ubuntu@YOUR_SERVER_IP
```
- `ssh` = remote connection tool
- `-i LightsailKey.pem` = your key (like a password file)
- `ubuntu` = username on the server
- `YOUR_SERVER_IP` = your static IP address

**Step 2: Install Docker**
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
```

**What is Docker?**
- Think of it as a **shipping container for your app**
- Packages your app + all dependencies together
- Ensures it runs the same everywhere
- Makes updates easy

**Why Docker?**
- ✅ Consistent environment (no "works on my machine" issues)
- ✅ Easy to update (just rebuild container)
- ✅ Isolated from server (won't break other things)

**Step 3: Create Data Folder**
```bash
sudo mkdir -p /srv/pri_dashboard/data/{db,uploads,media}
```

**What This Does:**
- Creates folders OUTSIDE your app
- `/srv/pri_dashboard/data/db/` = Your SQLite database
- `/srv/pri_dashboard/data/uploads/` = User CSV/Excel files
- `/srv/pri_dashboard/data/media/` = Dashboard images

**Why Outside the App?**
- When you update app code, data stays safe
- Can't accidentally delete database
- Easy to backup just the data folder

---

### **Phase 3: Deploy Your Application (30 minutes)**

#### What You'll Do:

**Step 1: Download Your Code**
```bash
git clone https://github.com/QUANTMATRIXAI/pri_app.git
cd pri_app
```

**What is Git?**
- Version control system (like Google Docs history)
- `git clone` = download your code from GitHub
- Your code is now on the server

**Step 2: Configure Data Storage**
```bash
nano docker-compose.yml
```

**What is docker-compose.yml?**
- Configuration file for Docker
- Tells Docker how to run your app
- You'll change one line to point to your data folder

**Change this:**
```yaml
volumes:
  - ./data:/app/data  # OLD: data inside app folder

# TO:
volumes:
  - /srv/pri_dashboard/data:/app/data  # NEW: data in safe location
```

**What This Does:**
- Links your data folder to the Docker container
- App thinks data is at `/app/data/`
- But it's actually stored at `/srv/pri_dashboard/data/`
- **Magic:** Data survives when you update the app!

**Step 3: Build & Run**
```bash
docker-compose build  # Package your app
docker-compose up -d  # Start running (in background)
```

**What Happens:**
1. Docker reads your `Dockerfile`
2. Installs Python + all dependencies
3. Copies your app code
4. Starts Streamlit
5. App is now running on port 8501

**Step 4: Test It**
```
http://YOUR_SERVER_IP:8501
```

**✅ Your app is live!** But not secure yet...

---

### **Phase 4: Add Security with Nginx (45 minutes)**

#### What is Nginx?
Think of Nginx as a **security guard + receptionist** for your app.

**Without Nginx:**
```
Internet → Your App (port 8501)
❌ No HTTPS (not secure)
❌ Anyone can access port 8501 directly
❌ No protection
```

**With Nginx:**
```
Internet → Nginx (port 80/443) → Your App (localhost:8501)
✅ HTTPS encryption
✅ App hidden behind Nginx
✅ Can block bad traffic
✅ Professional setup
```

#### What You'll Do:

**Step 1: Install Nginx**
```bash
sudo apt install nginx
```

**Step 2: Configure Nginx**
```bash
sudo nano /etc/nginx/sites-available/pri-dashboard
```

**Paste this configuration:**
```nginx
server {
    listen 80;  # Listen on port 80 (HTTP)
    server_name YOUR_IP;
    
    client_max_body_size 200M;  # Allow 200MB uploads
    
    location / {
        proxy_pass http://localhost:8501;  # Forward to Streamlit
        # ... other settings ...
    }
}
```

**What This Does:**
- Nginx listens on port 80 (standard web port)
- When someone visits `http://YOUR_IP`
- Nginx forwards request to `localhost:8501` (your app)
- Your app responds
- Nginx sends response back to user

**Why `client_max_body_size 200M;`?**
- Default Nginx limit: 1MB
- Your users upload 40MB files
- Without this line: "413 Request Entity Too Large" error
- With this line: Uploads work! ✅

**Step 3: Enable Nginx**
```bash
sudo ln -s /etc/nginx/sites-available/pri-dashboard /etc/nginx/sites-enabled/
sudo systemctl restart nginx
```

**Step 4: Secure Streamlit (Hide Port 8501)**
```bash
nano docker-compose.yml
```

**Change:**
```yaml
ports:
  - "8501:8501"  # OLD: accessible from internet

# TO:
ports:
  - "127.0.0.1:8501:8501"  # NEW: only localhost
```

**What This Does:**
- `127.0.0.1` = localhost (only accessible from the server itself)
- Now only Nginx can talk to Streamlit
- Direct access to port 8501 is blocked
- **More secure!** ✅

**Step 5: Update Firewall**
- Remove port 8501 from allowed ports
- Keep only: 22 (SSH), 80 (HTTP), 443 (HTTPS)

**Step 6: Add HTTPS (Optional)**
```bash
sudo certbot --nginx -d yourdomain.com
```

**What is HTTPS?**
- Encrypted connection (secure)
- Green padlock in browser
- Required for production apps
- Free with Let's Encrypt

---

### **Phase 5: Testing & Verification (30 minutes)**

#### What You'll Test:

**1. Basic Access**
```
http://YOUR_SERVER_IP
```
✅ Should show your login page

**2. Login**
- Use your admin credentials
- ✅ Should log in successfully

**3. Upload File**
- Upload a 40MB CSV file
- ✅ Should upload without errors
- ✅ Check file appears in dashboard

**4. View Dashboard**
- Navigate through different sections
- ✅ All charts/tables should load
- ✅ No errors in console

**5. Check Data Persistence**
```bash
# Restart app
docker-compose restart

# Check if data is still there
ls -lh /srv/pri_dashboard/data/
```
✅ Database and files should still exist

**6. Check Logs**
```bash
docker logs pri_dashboard -f
```
✅ No error messages

**7. Security Check**
```
http://YOUR_SERVER_IP:8501
```
❌ Should NOT be accessible (timeout/refused)
✅ This means Streamlit is properly secured!

---

## 🎓 Key Concepts Explained

### 1. **Localhost vs Public IP**

**Localhost (127.0.0.1):**
- Only accessible from the server itself
- Like talking to yourself
- Secure (no one else can access)

**Public IP (YOUR_SERVER_IP):**
- Accessible from anywhere on internet
- Like your home address
- Need security (firewall, Nginx)

**Our Setup:**
```
Internet → Public IP:80 (Nginx) → Localhost:8501 (Streamlit)
         ✅ Accessible        ❌ Hidden
```

### 2. **Ports Explained**

Think of ports like **apartment numbers** in a building:

- **Port 22:** SSH entrance (for you to manage server)
- **Port 80:** HTTP entrance (for users to access app)
- **Port 443:** HTTPS entrance (secure access)
- **Port 8501:** Streamlit's door (we hide this behind Nginx)

### 3. **Docker Volumes (Data Persistence)**

**Without Volume:**
```
Docker Container
└── /app/data/app.db
    └── ❌ Deleted when container is removed
```

**With Volume:**
```
Docker Container                    Server Disk
└── /app/data/ ←→ (linked) ←→ /srv/pri_dashboard/data/
                                    └── ✅ Persists forever
```

### 4. **Reverse Proxy (Nginx)**

**Direct Access (Insecure):**
```
User → Streamlit (port 8501)
❌ No encryption
❌ No protection
❌ Exposed to attacks
```

**Reverse Proxy (Secure):**
```
User → Nginx (port 80/443) → Streamlit (localhost:8501)
✅ Encryption (HTTPS)
✅ Protection (firewall)
✅ Hidden backend
```

---

## 💰 Cost Breakdown (Monthly)

| Item | Cost | What It Is |
|------|------|------------|
| **Lightsail Server** | $20.00 | Your computer in the cloud |
| **Static IP** | $0.00 | Permanent address (free when attached) |
| **Automatic Backups** | $1-3.00 | Weekly snapshots of entire server |
| **Domain Name** | $0-12.00 | Optional (e.g., dashboard.company.com) |
| **SSL Certificate** | $0.00 | HTTPS encryption (free with Let's Encrypt) |
| **Data Transfer** | $0.00 | Included (3TB/month) |
| **Total** | **$21-23/month** | **~$258/year** |

**Compare to:**
- Heroku: $25-50/month (+ need code changes)
- AWS EC2: $30-40/month (more complex)
- Your laptop: Free but not professional

---

## 🚀 Advantages of This Setup

### 1. **Data Safety**
- ✅ SQLite database persists forever
- ✅ Uploaded files never deleted
- ✅ Automatic weekly backups
- ✅ Can restore from snapshot in 15 minutes

### 2. **Professional**
- ✅ 24/7 uptime (99.5%+)
- ✅ Real server, not your laptop
- ✅ HTTPS encryption
- ✅ Custom domain possible

### 3. **Scalable**
- ✅ Start with $20/month (10-30 users)
- ✅ Upgrade to $40/month (50+ users) in 5 minutes
- ✅ Can add PostgreSQL later if needed
- ✅ Can add more servers if traffic grows

### 4. **Easy Maintenance**
- ✅ Update code: `git pull` + rebuild (5 minutes)
- ✅ Restart app: `docker-compose restart` (30 seconds)
- ✅ Check logs: `docker logs` (instant)
- ✅ Backup: Automatic (no manual work)

### 5. **Security**
- ✅ Firewall configured
- ✅ Streamlit hidden behind Nginx
- ✅ HTTPS encryption
- ✅ SSH key authentication
- ✅ Regular security updates

### 6. **Cost-Effective**
- ✅ Fixed price ($20/month)
- ✅ No surprise bills
- ✅ Includes backups
- ✅ Includes data transfer
- ✅ Can cancel anytime

---

## 🎯 What You'll Have After Deployment

### Before (Local Development)
```
Your Laptop
├── Trinity App
├── SQLite Database
└── Uploaded Files

❌ Only you can access
❌ Stops when laptop closes
❌ Not professional
```

### After (Production on AWS)
```
AWS Lightsail Server (24/7)
├── Nginx (Security Guard)
│   └── HTTPS Encryption
│   └── Port 80/443 (Public)
├── Docker Container
│   └── Trinity App (Streamlit)
│   └── Port 8501 (Hidden)
└── Persistent Storage
    ├── SQLite Database
    ├── User Uploads (CSV/Excel)
    └── Dashboard Media (Images/PPT)

✅ Accessible 24/7 from anywhere
✅ Professional setup
✅ Secure (HTTPS + Firewall)
✅ Automatic backups
✅ Scalable
✅ Fixed cost ($21/month)
```

---

## 📝 Quick Reference: What Each Command Does

### Server Management
```bash
# Connect to server
ssh -i key.pem ubuntu@IP
# "Remote control" your server

# Check disk space
df -h
# See how much storage is used

# Check memory
free -h
# See RAM usage
```

### Docker Commands
```bash
# Start app
docker-compose up -d
# Run app in background

# Stop app
docker-compose down
# Stop and remove container

# Restart app
docker-compose restart
# Quick restart (keeps data)

# View logs
docker logs pri_dashboard -f
# See what app is doing (real-time)

# Check if running
docker ps
# List running containers
```

### Nginx Commands
```bash
# Restart Nginx
sudo systemctl restart nginx
# Apply new configuration

# Test config
sudo nginx -t
# Check for errors before restarting

# View logs
sudo tail -f /var/log/nginx/access.log
# See who's accessing your app
```

### Git Commands
```bash
# Update code
git pull
# Download latest changes from GitHub

# Check status
git status
# See what changed

# View history
git log --oneline
# See recent updates
```

---

## ⚠️ Common Mistakes to Avoid

### 1. **Forgetting to Change Volume Path**
```yaml
❌ volumes: - ./data:/app/data
✅ volumes: - /srv/pri_dashboard/data:/app/data
```
**Why:** Data would be inside app folder and get deleted on updates

### 2. **Not Setting Nginx Upload Limit**
```nginx
❌ Missing: client_max_body_size 200M;
✅ Added: client_max_body_size 200M;
```
**Why:** 40MB file uploads would fail with "413 Error"

### 3. **Exposing Port 8501 Publicly**
```yaml
❌ ports: - "8501:8501"
✅ ports: - "127.0.0.1:8501:8501"
```
**Why:** Security risk - anyone could bypass Nginx

### 4. **Not Enabling Automatic Backups**
**Why:** If server fails, you lose all data

### 5. **Using Relative Paths**
```yaml
❌ /home/ubuntu/pri_app/data
✅ /srv/pri_dashboard/data
```
**Why:** Cleaner separation of code and data

---

## 🎓 Learning Resources

### If You Get Stuck:

**AWS Lightsail:**
- Official Docs: https://lightsail.aws.amazon.com/ls/docs/
- Video Tutorials: Search "AWS Lightsail tutorial" on YouTube

**Docker:**
- Official Docs: https://docs.docker.com/
- Beginner Guide: https://docker-curriculum.com/

**Nginx:**
- Official Docs: https://nginx.org/en/docs/
- Beginner Guide: https://www.nginx.com/resources/wiki/start/

**Linux Commands:**
- Cheat Sheet: https://www.linuxtrainingacademy.com/linux-commands-cheat-sheet/

---

## ✅ Final Checklist

Before you start, make sure you have:

- [ ] AWS account created
- [ ] Credit card added (for billing)
- [ ] GitHub repository access
- [ ] 2-3 hours of uninterrupted time
- [ ] This guide open
- [ ] Coffee/tea ☕

After deployment, verify:

- [ ] App accessible at `http://YOUR_IP`
- [ ] Can login successfully
- [ ] Can upload 40MB file
- [ ] Data persists after restart
- [ ] Port 8501 NOT accessible directly
- [ ] Automatic backups enabled
- [ ] Logs show no errors

---

## 🎉 You're Ready!

**Next Steps:**
1. Read through this guide once more
2. Open the `AWS_DEPLOYMENT_GUIDE.md` file
3. Follow it step-by-step
4. Take your time - no rush!
5. Test everything thoroughly

**Remember:**
- It's okay to make mistakes (that's why we have backups!)
- Take breaks if you get stuck
- Google error messages (they're usually helpful)
- You can always restore from a snapshot

**Good luck with your first deployment!** 🚀

---

**Questions? Check the troubleshooting section in `AWS_DEPLOYMENT_GUIDE.md`**
