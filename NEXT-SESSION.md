# NEXT-SESSION — Quick Sync handoff

This file is the single source of truth for "what changed, what is in flight,
and what to do next". Read it first in any new session.

**Status: Quick Sync 0.3 is committed on `arena/2aacc6d5-test-sync-kmk`
(brand-new session branch — the 0.2 branch `arena/01a10527-komikku-test-sync`
still exists on the remote). Pushing to the session branch triggers the
"Build Komikku Quick Sync (Private)" Action, which publishes release
`quick-sync-v0.3` with asset `Komikku-Quick-Sync-0.3-test.apk`.**

---

## 1. Why 0.3 exists — the reported breakage

The user reported (Oct 2026, from the Philippines): *"Recently, I cannot access
any extension. The pages would not load, and though some of the sources show,
pages still won't load. I assume it may have something to do with Cloudflare
bypass. I have tried to turn the setting on as well, but to no avail."*

Root cause (verified in the Komikku source, all versions up to and including
current upstream master): Komikku still ships the **2022-era
`CloudflareInterceptor`**. It only reacts to 403/503 responses whose HTML body
contains the old `challenge-error-title` / `challenge-error-text` markers.
Modern Cloudflare challenge pages no longer serve those markers, so the
interceptor never fires: every Cloudflare-protected source browse/popular page
and extension-store fetch just fails with an HTTP error, and the Cloudflare
setting appears to do nothing. Komikku upstream has NOT fixed this yet.

Mihon (the app Komikku is forked from) fully rewrote the bypass during 2026
(v0.21.2, last touched 2026-10-13): detection via the official
`cf-mitigated: challenge` response header, solving through a WebView with an
isolated-world JS bridge, per-host locks so concurrent requests share one
solver, non-GET challenges solved on the site root, renderer-crash survival.

Second request: the build was based on the older Komikku v1.14.1 — the user
asked for OG updates to be applied. Upstream master (2026-10-11,
`1656575e8fdaaef010c652f9758130c2a01d8890`) is 33 commits past v1.14.1:
dependency/security updates (Kotlin 2.4.20, jsoup 1.23.2 [security], sqldelight
2.4.1→2.3.2 chain, sqlcipher 4.19.1), the AndroidX bundled SQLite driver
switch, predictive-back revert, screen-transition keying fixes, MangaDex header
plumbing.

## 2. Every 0.3 change (all in the kit; the Action applies them to the pinned tree)

### Base re-pin

- Workflow now checks out upstream `komikku-app/komikku` at
  `1656575e8fdaaef010c652f9758130c2a01d8890` (master, 2026-10-11) instead of
  v1.14.1 `e30ff83265…`.
- `apply_patch.py`:
  * Removed the FlexibleAdapter JitPack→Maven-Central edit — upstream master
    did the same switch themselves (commit 3402f2c7), anchor no longer exists.
  * `versionName` → `1.14.1-quick-sync-0.3`.
  * All other Quick Sync anchors were re-validated against the master tree
    (only `app/build.gradle.kts` and `gradle/libs.versions.toml` changed
    upstream among kit-patched files; anchors still matched).

### Cloudflare bypass port (from Mihon main, CI-green snapshot of 2026-10-13/14, = v0.21.2 + Origin-header fix)

New **overlay** files (full replacements):

- `overlay/core/common/.../network/interceptor/CloudflareInterceptor.kt` —
  Mihon's rewrite verbatim: `cf-mitigated` detection, host locks,
  WebView challenge solving with `cloudflare-challenge` JS events
  (`interactiveBegin` = abort, `fail` = abort), `cf_clearance` cookie
  bookkeeping, render-process-gone handling, non-GET → site-root challenges.
- `overlay/core/common/.../network/interceptor/WebViewInterceptor.kt` —
  Mihon's version: added `scope: CoroutineScope` param, `prepareWebView()`,
  `setUserAgent` (keeps UA + `Sec-CH-UA` client hints consistent — important
  for Cloudflare), no more `parseHeaders` (moved to WebViewUtil).
- `overlay/core/common/.../util/system/WebViewUtil.kt` — Komikku's file plus
  Mihon's `setUserAgent` (rewrites WebView brand hints to Chrome),
  `Headers.toWebViewHeaders()` (drops unsafe headers incl. `Origin` — renderer
  is killed if it doesn't match the initiator), `isRequestHeaderSafe`.

`apply_patch.py` additions:

- `gradle/androidx.versions.toml`: new `webkit = "androidx.webkit:webkit:1.17.1"`
  (Komikku does not depend on androidx.webkit at all; the new APIs
  `ScriptHandler`, `WebViewCompat.addJavaScriptOnEvent`,
  `WebViewFeature.JS_INJECTION_IN_FRAME_AND_WORLD` need it).
- `core/common/build.gradle.kts`: `implementation(androidx.webkit)`.
- `NetworkHelper.kt`: new defaulted ctor param
  `private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)`
  (defaulted so `AppModule` and source-api `HttpSource` constructions stay
  untouched) and both `CloudflareInterceptor(...)` calls now pass `scope`.

### Workflow / release

- Push trigger now also includes branch `arena/2aacc6d5-test-sync-kmk`.
- Release tag `quick-sync-v0.3`, asset `Komikku-Quick-Sync-0.3-test.apk`,
  title "Komikku Quick Sync 0.3 (test build)", notes describing the Cloudflare
  fix + master rebase.

### Docs

- `README.md`: download links/names → 0.3, new "What's new in Quick Sync 0.3"
  section (kept the 0.2 history section below it).
- `quick-sync-kit/SHA256SUMS` regenerated (build refuses to run on mismatch).

## 3. Verification already done locally

- Dry-run + REAL run of `apply_patch.py` against a copy of the pinned master
  tree: applies cleanly, all anchors found, overlay files land correctly.
- Ported Kotlin is byte-identical to Mihon's (except the merged WebViewUtil
  which keeps Komikku's existing functions); Mihon main CI is green on exactly
  this code with webkit 1.17.1 ("Build & Test App → success" on deeb9b258).
- No remaining references to the removed `parseHeaders`; `toWebViewHeaders`
  resolves; `NetworkHelper` construction sites (AppModule, source-api
  HttpSource) compile unchanged thanks to the defaulted param.
- Not verified: an actual Gradle build (no Android SDK in the sandbox). The
  GitHub Action is the compile check — watch it.

## 4. Deliberately not changed

- All Quick Sync merge/sync logic, overlay `QuickSync.kt`, `ProgressStamp`,
  both unit-test classes, the 0.2 reader/button behaviour. Sync data format
  stays compatible with 0.1/0.2.
- Komikku's default User-Agent string (still Chrome/141): extensions can and do
  override the UA per source; changing the global default is riskier than the
  interceptor fix and not needed for it.
- Mihon's `spoofedPackageName` randomization (unrelated to the bypass).
- Extension repositories themselves: the user's repo list lives in their app
  database; the app now *can* get through Cloudflare-protected indexes.

## 5. Next steps

1. Wait for the Action on `arena/2aacc6d5-test-sync-kmk`; confirm release
   `quick-sync-v0.3` has `Komikku-Quick-Sync-0.3-test.apk` (+ SHA256.txt,
   READ-FIRST.txt).
2. User installs the same 0.3 APK on both phones and checks: extension list
   loads again, source pages load again, reader still opens instantly and syncs
   pages between phones.
3. If Cloudflare still fails on a specific source: ask the user to open that
   source → ⋮ → Open in WebView once (the manual fallback), and to make sure
   Android System WebView is updated (the new code toasts if it is too old).
4. If good: open a PR to merge this branch into `main` so 0.3 becomes the
   default guide/kit.
5. Keep this file updated in every future session.
