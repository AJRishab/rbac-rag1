# SentryRAG — Android App Links (deep linking)

This lets `https://rbac-rag-nine.vercel.app/auth/callback` open the installed
SentryRAG Android app (Android App Links / digital asset links verification).
It does **not** change any backend/RBAC/auth logic — it only adds Android
deep-link support on top of the existing web callback.

---

## 1. Web callback stays unchanged

The Supabase `emailRedirectTo` target remains:

```
https://rbac-rag-nine.vercel.app/auth/callback
```

Nothing in the web/auth flow was modified. On Android this same URL now
resolves to the APK when the app is installed (see §5 fallback when it isn't).

---

## 2. AndroidManifest.xml

File: `RBAC-RAG/frontend/android/app/src/main/AndroidManifest.xml`

Added an `intent-filter` (with `android:autoVerify="true"`) to the existing
`MainActivity` (`android:launchMode="singleTask"`, `android:exported="true"`):

```xml
<intent-filter android:autoVerify="true">
    <action android:name="android.intent.action.VIEW" />
    <category android:name="android.intent.category.DEFAULT" />
    <category android:name="android.intent.category.BROWSABLE" />
    <data
        android:scheme="https"
        android:host="rbac-rag-nine.vercel.app"
        android:pathPrefix="/auth/callback" />
</intent-filter>
```

- `autoVerify="true"` tells Android to confirm the association against
  `assetlinks.json` at install time.
- `pathPrefix="/auth/callback"` scopes the association to the auth-callback
  route only (the main `https://rbac-rag-nine.vercel.app` site still opens in
  the browser).

---

## 3. assetlinks.json content

File (in-repo): `RBAC-RAG/frontend/public/.well-known/assetlinks.json`

```json
[
  {
    "relation": ["delegate_permission/common.handle_all_urls"],
    "target": {
      "namespace": "android_app",
      "package_name": "com.ajrishab.sentryrag",
      "sha256_cert_fingerprints": [
        "7C4F53A72913C58CF5AA0E5B87605D9F0AF469E147BAD5EB24BB5D5D6789DBB0"
      ]
    }
  }
]
```

> **Certificate note (important).** The fingerprint above is the **debug**
> signing certificate (SHA-256) — the one matching the APKs this project
> currently builds (there is no release signing config/keystore yet):
> - `keystore: %USERPROFILE%\.android\debug.keystore`
> - `alias: androiddebugkey`
> - `keytool -list -v -keystore <debug.keystore> -storepass android -alias androiddebugkey`
>   → `SHA256: 7C:4F:53:A7:...`
>
> If you later sign with a **release/upload keystore** (required for Play
> Store), you MUST replace the fingerprint with that certificate's SHA-256
> (`keytool -list -v -keystore <release.jks> -alias <alias>`), format it
> without colons, redeploy `assetlinks.json`, and reconfigure. The debug and
> release certs have different fingerprints.

---

## 4. Where assetlinks.json must be hosted

**Exact URL Android checks at install/verification time:**

```
https://rbac-rag-nine.vercel.app/.well-known/assetlinks.json
```

Hosting (auto-deploys with your existing Vercel branch):

1. The file lives at `RBAC-RAG/frontend/public/.well-known/assetlinks.json`.
2. On a normal React/CRA build, everything in `public/` is copied verbatim
   into the `build/` output, so Vercel serves it at the site root.
3. After deploying the front-end branch to Vercel, confirm it's reachable:

   ```bash
   curl -s https://rbac-rag-nine.vercel.app/.well-known/assetlinks.json
   ```

   It must return the JSON array above with HTTP 200 and no redirect.

> If you deploy the frontend outside the repo's `public/` pipeline, you can
> instead upload the identical file to a static host pointed at
> `rbac-rag-nine.vercel.app` under `/.well-known/assetlinks.json`. The
> filename/path must be exactly `.well-known/assetlinks.json`.

Note: if you later change the app's `applicationId` (`com.ajrishab.sentryrag`),
update the `package_name` in `assetlinks.json` accordingly.

---

## 5. Behavior

- **App not installed** → the `https://.../auth/callback` link simply opens in
  the browser and loads the normal web `AuthCallback` page (no app, no
  redirect-to-store). This is default Android App Links behavior — no extra
  config needed.
- **App installed + verification succeeded** → the link opens the APK
  directly; Capacitor hands `/auth/callback` to the web app's route.
- **Verification failed** (bad fingerprint / unreachable JSON) → Android
  falls back to showing a chooser or opening the browser.

---

## 6. Build / verify steps

```bash
cd frontend

# 1) Re-sync the native project (picks up the manifest intent-filter)
npx cap sync android

# 2) Build a debug APK and install it
cd android && ./gradlew assembleDebug && cd ..
adb install -r android/app/build/outputs/apk/debug/app-debug.apk

# 3) Confirm the association verified
adb shell pm verify-app-links com.ajrishab.sentryrag   # lists rbac-rag-nine.vercel.app as VERIFIED

# 4) Inspect open-by-default link state
adb shell pm get-app-links com.ajrishab.sentryrag
```

Test end-to-end: from the browser/email, open
`https://rbac-rag-nine.vercel.app/auth/callback` and confirm it launches the
app (or the web page if the app is uninstalled).

---

## 7. Files changed in this task

| File | Change |
|------|--------|
| `frontend/android/app/src/main/AndroidManifest.xml` | Added `autoVerify` `VIEW` intent-filter for `https://rbac-rag-nine.vercel.app/auth/callback`. |
| `frontend/public/.well-known/assetlinks.json` | **New** — Android App Links association file (deployed to `/.well-known/assetlinks.json`). |
| `android_deep_links.md` | This document. |

No backend, RBAC, authentication, or web callback logic was modified.