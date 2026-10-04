# NEXT-SESSION — Quick Sync handoff

This file is the single source of truth for "what changed, what is in flight,
and what to do next". Read it first in any new session.

**Status: Quick Sync 0.2 is committed on `arena/01a10527-komikku-test-sync`,
which triggers the "Build Komikku Quick Sync (Private)" Action on push. The
green run publishes GitHub release `quick-sync-v0.2` with asset
`Komikku-Quick-Sync-0.2-test.apk`.**

---

## 1. What was lost, and how 0.2 was reconstructed

The previous session finished 0.2 as **unpushed local commits** (`3609753` +
handoff `5e47bd5`) on `arena/01a0feed-komikku-test-sync`. That sandbox closed
before pushing, so those commits — including the original version of this
file — are gone for good (verified: not in any remote ref, PR ref, or tag;
the old branch head `dc9db46` is the 0.1 state).

This 0.2 is therefore a **fresh reconstruction** of the described fixes
("slow Start/Resume button" + "black screen when opening chapters"), rebuilt
from the 0.1 kit that is merged in `main` (PR #1). The merge rules, sync data
format and WebDAV logic are intentionally untouched, so 0.1/0.2 phones can
still sync with each other.

## 2. The 0.2 root causes (found in the 0.1 kit)

* `QuickSync.beforeReading()` ran a **full synchronous sync cycle**
  (download → merge → full DB restore → upload, up to 3 attempts / 30 s,
  serialized through a mutex). 0.1 called it **inline from tap paths**:
  - `ReaderViewModel.init()` → pages could not load until sync finished →
    **black screen** when opening any chapter.
  - `LibraryTab` resume, `MangaScreen` continue-reading, `HistoryTab` resume
    → the **Start/Resume** action stalled for the whole cycle, often twice in
    a row right after the app-start sync.
  - `ReaderActivity.onResume()` additionally showed a **modal loading
    dialog** for its full-sync refresh.

## 3. Every 0.2 change

All changes are in the kit (`quick-sync-kit/`); the Action applies them to
the pinned Komikku `e30ff83` tree with `apply_patch.py`.

### `apply_patch.py` (edit anchors — validated against the pinned tree)

1. `versionName` → `1.14.1-quick-sync-0.2`; final print says 0.2.
2. Settings toggle subtitle now describes background sync ("the reader opens
   instantly and catches up to the newest page").
3. `ReaderViewModel.kt`:
   - New field `userNavigatedDuringRefresh`; new import
     `kotlinx.coroutines.withTimeoutOrNull`.
   - `init()` **no longer calls `beforeReading`**. It launches
     `refreshCloudProgress(incognitoChecked = true)` as a background
     coroutine (skipped for explicit-page opens `page != null` and
     incognito). Pages render immediately = no black screen.
   - Page-save handler: while a refresh runs it still suppresses saves, but
     now also records `userNavigatedDuringRefresh = true`.
   - `refreshCloudProgress(incognitoChecked)`:
     * still runs `QuickSync.beforeReading` (now freshness-aware, see
       below), then waits up to 10 s for the chapter to exist in state;
     * applies the merged read flag/page to the open chapter;
     * **only jumps if** the user did not navigate during the refresh and
       the synced page differs from the local one;
     * sets `requestedPage` (viewer honours it if pages are still loading)
       and sends `Event.RestoreSyncedPage` only when pages are already
       visible (live seek). No more unconditional re-yank.
4. `ReaderActivity.onResume()`: refresh stays, but the **modal dialog is
   gone** — background coroutine + toast on failure.
5. `LibraryTab` / `MangaScreen` / `HistoryTab`: tap paths now call
   `QuickSync.request(context, immediate = true)` (fire-and-forget) instead
   of awaiting `beforeReading`. Buttons are instant; the reader's own
   background refresh closes the freshness gap.

### `overlay/.../QuickSync.kt`

- New `lastSuccessAt` timestamp, set by `perform()` on every completed sync.
- New **15 s freshness window**: `beforeReading()` and `request()` treat a
  just-finished sync as fresh and skip starting a second full cycle (kills
  the "app-start sync then immediate second sync" double stall).
- `beforeReading` doc now states: background-refresh use only, never on a
  tap path; attempts/timeout unchanged (3 tries, 30 s cap).

### `.github/workflows/quick-sync-private-build.yml`

- Push trigger now also includes branch `arena/01a10527-komikku-test-sync`
  (the `arena/01a0feed…` entry is kept; that branch still exists on the
  remote at the 0.1 state).
- Release tag `quick-sync-v0.2`, asset `Komikku-Quick-Sync-0.2-test.apk`,
  title "Komikku Quick Sync 0.2 (test build)", notes describe the fixes.

### `README.md`

- Download link/name → 0.2, version string → `1.14.1-quick-sync-0.2`.
- Step 5 description matches the new "open instantly, jump when sync lands"
  behaviour; new "What's new in Quick Sync 0.2" section.

### `quick-sync-kit/SHA256SUMS`

- Regenerated after the edits (the build refuses to run on a mismatch).

## 4. Deliberately not changed

- Merge policy (`SyncService.kt`, `MangaRestorer.kt`, repositories),
  `ProgressStamp`, WebDAV conditional-write handling, `SyncManager.syncData`
  re-merge/restore flow, both unit-test classes, the debounced scheduler
  skeleton. The phone-to-phone sync format is byte-compatible with 0.1.

## 5. Next steps

1. Wait for the Action; confirm release `quick-sync-v0.2` has
   `Komikku-Quick-Sync-0.2-test.apk` (plus SHA256.txt, READ-FIRST.txt).
2. Install the same 0.2 APK on both test phones and verify:
   chapter open is instant, Start/Resume is instant, and the reader still
   jumps to the other phone's page a few seconds later.
3. If good: merge this branch into `main` (open a PR) so the guide and the
   0.2 kit become the default; optional — delete the stale
   `arena/01a0feed…` branch afterwards.
4. Keep this file updated in every future session.
