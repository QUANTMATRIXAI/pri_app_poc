# Planned Updates

This document tracks agreed-upon enhancements for the Trinity Dashboard.

---

## 1. Three-Tier Role System

**Current State:** Two roles (`editor`, `viewer`)

**Proposed Change:** Add a third role `admin` with the following permission matrix:

| Capability | `admin` | `editor` | `viewer` |
|------------|---------|----------|----------|
| View Dashboard | ✅ | ✅ | ✅ |
| Access Data Studio | ✅ | ✅ | ❌ |
| Configure charts/tables/media | ✅ | ✅ | ❌ |
| Delete dashboard content | ✅ | ✅ | ❌ |
| Upload data files | ✅ | ❌ | ❌ |
| Clear all data | ✅ | ❌ | ❌ |

**Files to modify:**
- `app_core/database.py` - Update role CHECK constraint to include `admin`
- `app_core/auth.py` - Add default admin user, update `add_user()` to accept `admin` role
- `app.py` - Split sidebar logic: upload/clear only for `admin`, Data Studio for both `admin` and `editor`

---

## Future Updates

*(Add more items here as we discuss them)*
