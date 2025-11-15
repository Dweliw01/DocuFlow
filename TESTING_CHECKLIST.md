# DocuFlow Authentication Flow - Testing Checklist

## Pre-Test Setup ✅ COMPLETE

- ✅ Database cleared (all users & organizations deleted)
- ✅ Database schema updated with organization tables
- ✅ Auth0 configured
- ✅ 54/57 tests passing (95%)

## Testing Instructions

### Step 1: Clear Browser Cache

**Open Browser Console (F12) and run:**
```javascript
localStorage.clear();
console.log('✓ Browser cache cleared');
```

**Or use Incognito/Private browsing mode**

---

### Step 2: Start the Server

```bash
cd "C:\Users\Dusha\OneDrive\Desktop\Python Projects\FileBot"
conda activate filebuddy
python backend/main.py
```

**Expected Output:**
```
[OK] Configuration loaded
[OK] Database initialized
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

### Step 3: Test Landing Page

1. **Open:** `http://localhost:8000/`

**Expected Behavior:**
- ✅ Clean professional landing page loads
- ✅ No purple backgrounds
- ✅ No emojis
- ✅ "Start Free Trial" button visible
- ✅ Feature cards display properly
- ✅ Pricing section shows 3 tiers

**Screenshot location:** Landing page should look modern/professional

---

### Step 4: Test Login Flow

1. **Click:** "Start Free Trial" button
2. **Should redirect to:** `http://localhost:8000/login.html`

**Expected Behavior:**
- ✅ Minimal clean login page loads
- ✅ Two buttons: "Continue with Google" and "Continue with Auth0"
- ✅ Footer shows "Don't have an account? Start free trial"

**Click:** "Continue with Google"

**Expected Behavior:**
- ✅ Redirects to Auth0/Google login screen
- ✅ Can select Google account
- ✅ Grants permissions

---

### Step 5: Test Onboarding Flow (NEW USER)

**After Google login, should redirect to:** `http://localhost:8000/onboarding.html`

**Expected Behavior:**
- ✅ Step 1 shows "Create your organization"
- ✅ Organization name field is shown
- ✅ Placeholder suggests org name from email domain (e.g., "Gmail" if @gmail.com)
- ✅ **NO email field** (removed as redundant!)
- ✅ Progress indicator shows step 1 of 3

**Actions:**
1. Enter organization name (e.g., "My Test Org")
2. Click "Continue"

**Expected Behavior - Step 2:**
- ✅ Progress indicator advances to step 2
- ✅ Plan selection shows: Trial, Pay Per Document, Starter
- ✅ "Trial" is pre-selected
- ✅ Each plan shows features

**Actions:**
1. Keep "Trial" selected (or choose another)
2. Click "Create Organization"

**Expected Behavior - Step 3:**
- ✅ Progress indicator shows step 3 (complete)
- ✅ Success message displays
- ✅ "Go to Dashboard" button appears

**Actions:**
1. Click "Go to Dashboard"

**Expected Behavior:**
- ✅ Redirects to `http://localhost:8000/dashboard.html`
- ✅ Dashboard loads successfully
- ✅ Upload section visible
- ✅ **NO redirect back to login!**

---

### Step 6: Test Cross-Page Navigation (CRITICAL TEST)

**You are now on dashboard. This is where your issue was happening!**

**Actions:**
1. Click "Settings" in navigation bar

**Expected Behavior:**
- ✅ Redirects to `http://localhost:8000/settings.html`
- ✅ Settings page loads
- ✅ **NO redirect to login!**
- ✅ User remains authenticated

**Actions:**
2. Click "Process Documents" in navigation bar

**Expected Behavior:**
- ✅ Redirects to `http://localhost:8000/dashboard.html`
- ✅ Dashboard loads
- ✅ **NO redirect to login!** ← **THIS WAS YOUR BUG**
- ✅ User remains authenticated

**Try navigating back and forth 3-4 times:**
- Dashboard → Settings → Dashboard → Settings → Dashboard

**Expected Behavior:**
- ✅ All navigation works smoothly
- ✅ NO login redirects
- ✅ Auth persists across all pages

---

### Step 7: Test Page Refresh (Auth Persistence)

**While on dashboard:**

**Actions:**
1. Press F5 (refresh page)

**Expected Behavior:**
- ✅ Page reloads
- ✅ User stays logged in
- ✅ Dashboard displays
- ✅ **NO redirect to login!**

**Actions:**
2. Close browser tab
3. Reopen and navigate to `http://localhost:8000/dashboard.html`

**Expected Behavior:**
- ✅ Dashboard loads immediately
- ✅ User still authenticated (localStorage token still valid)
- ✅ **NO redirect to login!**

---

### Step 8: Test Returning User (Skip Onboarding)

**Actions:**
1. Open new incognito window
2. Navigate to `http://localhost:8000/`
3. Click "Start Free Trial"
4. Log in with **SAME Google account**

**Expected Behavior:**
- ✅ After Google login, **SKIPS onboarding**
- ✅ Redirects directly to `http://localhost:8000/dashboard.html`
- ✅ Dashboard loads immediately
- ✅ Organization name displays in navbar (if we added that feature)

---

### Step 9: Test New User with Different Account

**Actions:**
1. Log out (if logout button exists) or clear localStorage
2. Log in with **DIFFERENT Google account**

**Expected Behavior:**
- ✅ Goes through onboarding flow (new user)
- ✅ Can create new organization
- ✅ Gets separate dashboard

---

## What to Watch For (Common Issues)

### ❌ ISSUE: Infinite redirect loop
**Symptom:** Login → Dashboard → Login → Dashboard
**Cause:** Token not persisting or organization context missing
**Check:** Browser console for errors, localStorage for auth_token

### ❌ ISSUE: "Old email" appearing
**Symptom:** Previous user's email shows during onboarding
**Cause:** Database not cleared properly
**Fix:** Run clear scripts again

### ❌ ISSUE: Onboarding not showing
**Symptom:** New user goes straight to dashboard
**Cause:** Database already has organization for this user
**Fix:** Check database, clear users table

### ❌ ISSUE: Settings → Login redirect
**Symptom:** Clicking settings redirects to login
**Cause:** Auth token not being sent with requests
**Check:** Network tab in browser DevTools, look for 401 errors

---

## Success Criteria ✅

All of these should work:

- [x] Landing page loads (professional design)
- [x] Login with Google works
- [x] New user sees onboarding (simplified, no email field)
- [x] Organization creation works
- [x] Dashboard loads after onboarding
- [x] Settings navigation works (NO login redirect)
- [x] Dashboard navigation works (NO login redirect)
- [x] Page refresh maintains auth
- [x] Returning user skips onboarding
- [x] Multiple users can have separate organizations

---

## Browser Console Debugging

**Open DevTools (F12) and watch for:**

**Good signs:**
```
[Auth] Checking authentication...
[Auth] Stored token exists: true
[Auth] User authenticated via localStorage
[Auth] Authentication successful!
[Onboarding] User already has organization, redirecting to dashboard
```

**Bad signs (report these):**
```
[Auth] Not authenticated, redirecting to login...
Error: No authentication token available
401 Unauthorized
Failed to load organization context
```

---

## Test Results Template

**Fill this out after testing:**

```
✅ / ❌  Landing page loads
✅ / ❌  Google login works
✅ / ❌  Onboarding flow (simplified)
✅ / ❌  Dashboard loads
✅ / ❌  Settings navigation (no redirect)
✅ / ❌  Dashboard navigation (no redirect)
✅ / ❌  Page refresh maintains auth
✅ / ❌  Returning user skips onboarding

Issues found:
1. [describe issue]
2. [describe issue]

Browser errors (from console):
[paste any errors]
```

---

## Next Steps After Testing

**If all tests pass:**
1. Commit changes
2. Consider adding logout button
3. Add organization name display in navbar
4. Deploy to production

**If tests fail:**
1. Note which step failed
2. Check browser console for errors
3. Check server logs
4. Report back with specific error messages
5. We'll debug systematically with tests
