# Git Workflow Guide

## Repository Information

**Production Repository:** https://github.com/QUANTMATRIXAI/pri_app.git  
**Remote Name:** `pri_app`

## Branch Structure

```
pri_app (remote)
├── prilink (PRODUCTION - deployed to AWS, client uses this)
├── feature/client-requests (Quick client additions)
└── feature/migration (Long-term internal enhancements)
```

---

## 🚀 QUICK START - Daily Steps

### For Client Features (Most Common)

```bash
# 1. Switch to client branch
git checkout feature/client-requests

# 2. Pull latest changes
git pull pri_app feature/client-requests

# 3. Make your changes in VS Code
# Edit files, test locally...

# 4. Save and commit
git add -A
git commit -m "Add feature: description"

# 5. Push to remote
git push pri_app feature/client-requests

# 6. When ready to deploy to production:
git checkout prilink
git merge feature/client-requests
git push pri_app prilink

# 7. Deploy to AWS (see deployment section below)
```

### For Migration Work (Long-term)

```bash
# 1. Switch to migration branch
git checkout feature/migration

# 2. Pull latest changes
git pull pri_app feature/migration

# 3. Make your changes in VS Code
# Edit files, test locally...

# 4. Save and commit
git add -A
git commit -m "Migration progress: description"

# 5. Push to remote
git push pri_app feature/migration

# 6. DON'T merge to prilink yet - keep working!
```

---

## Branch Purposes

### 1. **prilink** (Production Branch)
- **Purpose:** Production code deployed to AWS
- **Who uses it:** Client (live environment)
- **When to update:** Only merge tested, approved features
- **Deploy to:** AWS instance at http://13.205.110.57:8517

### 2. **feature/client-requests** (Client Features Branch)
- **Purpose:** Quick client-requested features and fixes
- **Merge to:** `prilink` when ready for production
- **Timeline:** Short-term (days to weeks)

### 3. **feature/migration** (Internal Enhancement Branch)
- **Purpose:** Long-term internal work (smart file migration, major refactoring)
- **Merge to:** `prilink` when fully complete and tested
- **Timeline:** Long-term (weeks to months)

---

## Daily Workflows

### Working on Client Requests (Quick Features)

```bash
# 1. Switch to client-requests branch
git checkout feature/client-requests

# 2. Pull latest changes
git pull pri_app feature/client-requests

# 3. Make your changes
# Edit files...

# 4. Commit changes
git add -A
git commit -m "Add client feature: description"

# 5. Push to remote
git push pri_app feature/client-requests

# 6. When ready to deploy to production:
git checkout prilink
git pull pri_app prilink
git merge feature/client-requests
git push pri_app prilink

# 7. Deploy to AWS (see AWS_DEPLOYMENT_GUIDE.md)
```

### Working on Migration (Long-term Work)

```bash
# 1. Switch to migration branch
git checkout feature/migration

# 2. Pull latest changes
git pull pri_app feature/migration

# 3. Make your changes
# Edit files...

# 4. Commit changes
git add -A
git commit -m "Progress on migration: description"

# 5. Push to remote
git push pri_app feature/migration

# 6. Keep working... DON'T merge to prilink yet!
```

### Keeping Migration Branch Updated

When client features are merged to `prilink`, update your migration branch:

```bash
# 1. Make sure prilink is up to date
git checkout prilink
git pull pri_app prilink

# 2. Switch to migration branch
git checkout feature/migration

# 3. Merge latest prilink changes
git merge prilink

# 4. Resolve any conflicts if needed
# Edit conflicting files...
git add -A
git commit -m "Merge latest prilink changes into migration"

# 5. Push updated migration branch
git push pri_app feature/migration
```

### Final Migration Merge (When Complete)

```bash
# 1. Ensure migration is fully tested
# Run all tests, verify functionality

# 2. Update migration with latest prilink
git checkout feature/migration
git merge prilink
git push pri_app feature/migration

# 3. Merge to production
git checkout prilink
git pull pri_app prilink
git merge feature/migration

# 4. Push to production
git push pri_app prilink

# 5. Deploy to AWS (see AWS_DEPLOYMENT_GUIDE.md)

# 6. Optional: Delete migration branch after successful deployment
git branch -d feature/migration
git push pri_app --delete feature/migration
```

---

## Quick Reference Commands

### Check Current Branch
```bash
git branch
```

### Check Remote Branches
```bash
git branch -r
```

### Switch Branches
```bash
git checkout prilink
git checkout feature/client-requests
git checkout feature/migration
```

### View Branch Status
```bash
git status
```

### View Commit History
```bash
git log --oneline --graph --all
```

### Undo Last Commit (Keep Changes)
```bash
git reset --soft HEAD~1
```

### Discard All Local Changes
```bash
git checkout .
```

---

## Important Rules

✅ **DO:**
- Always pull before starting work: `git pull pri_app <branch-name>`
- Commit frequently with clear messages
- Test before merging to `prilink`
- Keep migration branch updated with prilink changes
- Push to `pri_app` remote only

❌ **DON'T:**
- Don't work directly on `prilink` branch
- Don't merge untested code to `prilink`
- Don't force push to `prilink`: `git push -f` ❌
- Don't merge migration to prilink until fully complete

---

## Conflict Resolution

If you get merge conflicts:

```bash
# 1. Git will mark conflicting files
git status

# 2. Open conflicting files and look for:
<<<<<<< HEAD
Your changes
=======
Incoming changes
>>>>>>> branch-name

# 3. Edit files to resolve conflicts
# Remove conflict markers and keep desired code

# 4. Mark as resolved
git add <resolved-file>

# 5. Complete the merge
git commit -m "Resolve merge conflicts"

# 6. Push
git push pri_app <branch-name>
```

---

## Emergency Rollback

If production breaks after merge:

```bash
# 1. Find the last good commit
git log --oneline

# 2. Reset to that commit
git checkout prilink
git reset --hard <commit-hash>

# 3. Force push (ONLY in emergency!)
git push pri_app prilink --force

# 4. Redeploy to AWS
```

---

## Branch Visualization

```
Time →

prilink:     A---B---C---D---E---F---G (PRODUCTION)
                  \       \       \
client-requests:   \---X---Y (merge) \
                        \             \
migration:               \---M---N---O---P (merge when ready)
```

---

## Contact & Support

- **Repository:** https://github.com/QUANTMATRIXAI/pri_app
- **AWS Instance:** http://13.205.110.57:8517
- **Deployment Guide:** See `docs/AWS_DEPLOYMENT_GUIDE.md`
