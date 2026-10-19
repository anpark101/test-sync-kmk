# Komikku Quick Sync — automatic library & page sync between two phones

**Komikku Sync Lab** is an experimental, unofficial version of the
[Komikku](https://github.com/komikku-app/komikku) manga reader with a new
**Quick Sync** feature: your library and your exact reading progress
(**down to the page you are on**) automatically stay in sync between two
devices, phone to phone, through a storage folder you control.

> ⚠️ This is a **test build for experimentation**. It is not affiliated with
> the official Komikku project. Keep your original Komikku installed and keep
> making backups. See [Important safety notes](#important-safety-notes).

---

## What you get

| Feature | What it means for you |
|---|---|
| **Separate app** | Installs **next to** your normal Komikku (it does not replace it). App name: **Komikku Sync Lab**. |
| **Page-level sync** | Open a manga on phone A at page 17 of chapter 5 → open it on phone B → you land on page 17 of chapter 5. |
| **Auto sync** | Syncs by itself: when you leave the reader, when you switch back to the app, and on a schedule — no "Sync now" tapping needed. |
| **Latest edit wins** | Marking a chapter unread, re-reading, or going *backwards* to an earlier page all count as real edits and win over older progress. Metadata refreshes can never overwrite a newer page checkpoint. |
| **Library membership** | Adding/removing favourites and changing categories syncs too, with its own separate clock. |
| **Phone to phone** | Both phones talk to **one shared folder** you choose (WebDAV or SyncYomi). No server of ours exists — no accounts, no telemetry, no one else can read your data. |

**How sync travels (both phones ⇄ your folder):**

```
 Phone A ──┐                       ┌── Phone B
           ├──► your WebDAV / ─────┤
           │    SyncYomi folder    │
           └───────────────────────┘
```

The two phones never need to be near each other or on the same Wi-Fi.

---

## The 5-step walkthrough (no coding needed)

### Step 1 — Get the APK file

The APK (the installable app file) is built **in the cloud by GitHub** — you
never need a computer.

1. Open this repository on GitHub (the `komikku-test-sync` repo).
2. Open the **Releases** section — direct link:
   [`test-sync-kmk/releases/tag/quick-sync-v0.3`](https://github.com/anpark101/test-sync-kmk/releases/tag/quick-sync-v0.3)
3. Download **`Komikku-Quick-Sync-0.3-test.apk`** on **each phone**.

*If there is no release yet, the build has not finished — see
[Rebuilding the APK yourself](#rebuilding-the-apk-yourself).*

### Step 2 — Install it on BOTH phones

1. Tap the downloaded `.apk` file.
2. Your phone will warn: **"Install blocked / this app is from an unknown
   source"**. This is normal for any app not from the Play Store.
3. Tap **Settings → allow from this source** (wording varies by phone), go
   back, tap **Install**.
4. You will now have **two readers side by side**: your original *Komikku*
   and the new **Komikku Sync Lab**. They do not touch each other.

> 📱 **Both phones must install the exact same APK file** (same version).
> A mismatch is the #1 cause of "it does not sync".

### Step 3 — Prepare one shared folder (WebDAV, recommended)

Quick Sync stores its data in **one folder you own**. Any WebDAV works, for
example:

* **Nextcloud** (self-hosted or a provider), **Box**, **Koofr**,
  **IONOS HiDrive**, your NAS (Synology/QNAP), etc.
* Or pick **SyncYomi** as the sync service instead, if you already use it.

Create a **dedicated empty folder** for this test, e.g.
`/KomikkuSyncTest`. Do **not** point it at your real Komikku backups folder.

### Step 4 — Tell BOTH phones about that folder

On **each** phone, in **Komikku Sync Lab**:

1. **More (⋯) → Settings → Data → Synchronization**.
2. Turn **Synchronization** on.
3. Pick the service: **WebDAV**.
4. Enter the **same** server address, folder path and password on both phones.
5. Leave **Quick sync (experimental)** ON (it is on by default).
6. Suggested: turn sync **on app start / on app resume** triggers on as well.
7. Leave **"Sync now"** and let the first sync finish on one phone (it will
   upload), then run it on the other phone (it will download + merge).

That's it — from now on sync happens **automatically**.

### Step 5 — Use it

Read normally. Watch for:

* A short **"Sync completed"** notification after you leave a chapter.
* When you open a chapter, it appears **immediately** — no waiting, no black
  screen — and a moment later the reader jumps to the page the **other phone**
  last read, once the background sync lands. If the network is down you will
  see: *"Cloud sync has not finished. This device may show an older page."*
* The **Start / Resume** buttons react instantly again; the sync for that
  tap happens in the background.

---

## What's new in Quick Sync 0.3

0.3 fixes the **"no extension loads / sources show but pages never load"**
problem and brings the app current with original Komikku again:

| What changed | Why it matters |
|---|---|
| **New Cloudflare bypass** (ported from Mihon, the project Komikku is based on). Old code only recognised challenge pages that today's Cloudflare no longer serves — so protected sources and extension lists just failed, and turning the bypass setting on did nothing. | Sources, extension stores and chapter pages behind Cloudflare load again. Challenges are now detected the official way (the `cf-mitigated` response header) and solved in the background WebView; concurrent requests share one solver instead of piling up. |
| **Base updated** from Komikku v1.14.1 (July 2026) to Komikku master of 2026-10-11. | Brings in upstream's dependency & security updates (Kotlin 2.4.20, jsoup 1.23.2 security fix, SQLDelight/sqlcipher bumps), the faster bundled SQLite driver, and screen-transition fixes. |
| Quick Sync behaviour is unchanged. | Same instant-open reader, same background catch-up, same merge rules and sync data format — 0.3 phones can sync with 0.2/0.1 phones. |

The merge rules ("latest edit wins", page clock / library clock) and the sync
data format are unchanged, so a 0.3 phone and a 0.2/0.1 phone can still exchange
progress. Even so, prefer installing the **same 0.3 APK on both phones**.

---

## What's new in Quick Sync 0.2

0.2 fixes the two annoyances found while device-testing 0.1:

| 0.1 behaviour | 0.2 behaviour |
|---|---|
| **Black screen when opening a chapter** — the reader waited for a full cloud sync (download → merge → restore → upload) before any page appeared. | Chapter pages appear **instantly** from local data. A background refresh then applies the newer cloud page and the reader seeks to it (you see the jump, never a stall). If you already turned a page yourself, your position wins. |
| **Slow Start / Resume buttons** — every tap performed a whole sync (often twice in a row right after app start) before the chapter opened. | Taps respond **immediately**: they schedule a background sync and open the reader. The open reader's own background refresh keeps the page correct. |
| Returning to the reader showed a **blocking loading dialog** during sync. | Resume refreshes silently in the background; you only get a toast if sync could not finish. |
| Opening the reader right after an app-start sync ran the sync **a second time**. | A sync that completed within the last 15 seconds counts as *fresh* and is reused — no duplicate full cycle. |

The merge rules ("latest edit wins", page clock / library clock) and the sync
data format are unchanged, so a 0.2 phone and a 0.1 phone can still exchange
progress. Even so, prefer installing the **same 0.2 APK on both phones**.

---

## Rebuilding the APK yourself

Every file needed to build is in this repository (nothing is hidden). The
build runs on GitHub's servers:

1. Open the repository on GitHub → **Actions** tab.
2. Choose **Build Komikku Quick Sync (Private)** on the left.
3. Press **Run workflow → Run workflow** (green button).
4. Wait for the green ✅ (roughly 15–40 minutes).
5. Open the finished run → bottom of the page, artifact
   **`Komikku-Quick-Sync-APK`** → **Download artifact**.
6. Unzip if needed and install the `.apk` on both phones.

If the run turns red ❌, open it and send a screenshot of the failing step —
that log tells us exactly what to fix.

---

## How the "latest edit wins" rule works (the short version)

Each time your **reading progress** or **library membership** really changes,
the app writes a tiny edit timestamp ("stamp") into data it already syncs:

* ⏱ **Page clock** — page turns, mark read/unread, backwards seeks.
* 📚 **Library clock** — add/remove from library, category changes.

When two devices disagree, **the newer stamp wins — always**. Titles,
chapter renames, rescans and metadata refreshes carry **no** stamp, so they
can never override your newest page. Ties are broken deterministically, so
both phones always agree on the same winner.

---

## Important safety notes

* **Experimental software.** Device testing is still ongoing. Bugs are
  possible — including, in the worst case, data loss on the *sync* copy.
* **Keep your original Komikku** and its backups. Never uninstall it "to
  save space" before you trust the new build.
* **Make a backup first** in the new app (More → Backup) before the first
  big sync.
* **Use a separate/dedicated WebDAV folder**, not a folder holding important
  files.
* **Google Drive sync is intentionally disabled** in this build: the
  unofficial fork has no Google OAuth credentials, and we will not ask you
  for tokens or passwords. Use WebDAV or SyncYomi.
* **No encryption is added by us** — whatever your WebDAV provider does is
  what you get. Use a strong folder password.
* This APK is signed with a debug key for the trial; a later build may have
  a different signing key (you would have to uninstall + reinstall to
  update).

---

## What is in this repository

| Path | Purpose |
|---|---|
| `.github/workflows/quick-sync-private-build.yml` | The cloud build recipe: fetches the pinned Komikku v1.14.1 source, applies the kit, runs the sync tests, builds and packages the APK. |
| `quick-sync-kit/apply_patch.py` | Applies all Quick Sync changes to the exact upstream commit. Every edit is anchored — it fails loudly if upstream differs. |
| `quick-sync-kit/overlay/` | New source files: `QuickSync.kt` (scheduler), `ProgressStamp.kt` (edit clocks), plus their unit tests. |
| `quick-sync-kit/SHA256SUMS` | Checksums; the build refuses to run if any kit file was corrupted or half-uploaded. |
| `README.md` | This guide. |

The compiled app's package name is `app.komikku.sync.beta`, version
`1.14.1-quick-sync-0.3…` — that is how you can confirm both phones run the
same build (Settings → About in the app).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Nothing syncs | Check both phones use the same service, folder, and password; open the sync settings and press **Sync now** on each and read the notification text. |
| "This device may show an older page" toast | The other phone hasn't pushed yet, or the network is slow. The app will retry automatically. |
| Pages jump back on one phone | That phone had an *older* edit win — read one page further; the newest edit then wins everywhere. |
| Build fails on GitHub Actions | The failing step name says why (test failure vs. compile error). Send the log. |
| App not installable | You downloaded the wrong file, or a phone blocks unknown sources — allow it in Settings (Step 2). |
| Want to start clean | Uninstall **Komikku Sync Lab**, delete the dedicated WebDAV folder contents, reinstall, sync again. Your original Komikku is untouched. |
