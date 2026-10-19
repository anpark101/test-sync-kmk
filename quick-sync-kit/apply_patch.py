#!/usr/bin/env python3
"""Apply the experimental Quick Sync patch to the Komikku source tree.

Base: Komikku master 1656575e8 (2026-10-11, "refactor(MangaDex): Simplify request
header plumbing (#1930)"). This is newer than the v1.14.1 release: it also carries
upstream's dependency updates (Kotlin 2.4.20, jsoup security fix, SQLDelight/
sqlcipher bumps), the AndroidX bundled SQLite driver switch and the screen
transition fixes.

On top of the Quick Sync changes this also ports the modern Cloudflare bypass
stack from Mihon (mihonapp/mihon, as released in v0.21.2 / main 2026-10-13):
challenges are detected through the official `cf-mitigated: challenge` response
header instead of parsing challenge HTML that current Cloudflare pages no longer
serve, so browsing Cloudflare-protected sources and extension stores works again.
Not a phone setup script. End users install the compiled APK, not this file.
"""
from pathlib import Path
import argparse
import shutil

ROOT = Path(__file__).resolve().parent
p = argparse.ArgumentParser()
p.add_argument('source', type=Path)
args = p.parse_args()
source = args.source.resolve()


def edit(name, old, new, count=1):
    path = source / name
    text = path.read_text()
    occurrences = text.count(old)
    if occurrences != count:
        raise RuntimeError(f'{name}: expected {count} anchors; found {occurrences}: {old[:90]!r}')
    path.write_text(text.replace(old, new))


def imports(name, *names):
    path = source / name
    text = path.read_text()
    lines = ''.join('import ' + n + '\n' for n in names if 'import ' + n + '\n' not in text)
    if lines:
        at = text.index('\n\n')
        text = text[:at+2] + lines + text[at+2:]
        path.write_text(text)

app = 'app/src/main/java/'
sync = app + 'eu/kanade/tachiyomi/data/sync/'
reader = app + 'eu/kanade/tachiyomi/ui/reader/'
restore = app + 'eu/kanade/tachiyomi/data/backup/restore/'

# A side-by-side, telemetry-free test build; never replace the installed original.
edit('app/build.gradle.kts', 'applicationId = "app.komikku"', 'applicationId = "app.komikku.sync"')
edit('app/build.gradle.kts', 'versionName = "1.14.1"', 'versionName = "1.14.1-quick-sync-0.3"')
edit('app/build.gradle.kts', '    lint {', '    testOptions {\n        unitTests.isReturnDefaultValues = true\n    }\n\n    lint {')
edit('app/src/main/AndroidManifest.xml', 'android:label="@string/app_name"', 'android:label="Komikku Sync Lab"')

# --- Cloudflare bypass fix (ported from Mihon v0.21.2 / main 2026-10-13) ---
# The old interceptor only reacted to challenge pages that contained the
# "challenge-error-title"/"challenge-error-text" markers, which modern Cloudflare
# challenge pages no longer serve, so sources and extension stores protected by
# Cloudflare simply failed with an HTTP error and the bypass toggle did nothing.
# androidx.webkit provides the WebMessage/isolated-world APIs the new
# CloudflareInterceptor uses; upstream Komikku does not depend on it yet.
edit('gradle/androidx.versions.toml',
     'sqlite-bundled = { module = "androidx.sqlite:sqlite-bundled", version.ref = "sqlite" }',
     'sqlite-bundled = { module = "androidx.sqlite:sqlite-bundled", version.ref = "sqlite" }\n\nwebkit = "androidx.webkit:webkit:1.17.1"')
edit('core/common/build.gradle.kts', '    implementation(libs.jsoup)', '    implementation(androidx.webkit)\n\n    implementation(libs.jsoup)')

network_helper = 'core/common/src/main/kotlin/eu/kanade/tachiyomi/network/NetworkHelper.kt'
imports(network_helper, 'kotlinx.coroutines.CoroutineScope', 'kotlinx.coroutines.Dispatchers', 'kotlinx.coroutines.SupervisorJob')
edit(network_helper, '''/* SY --> */ open /* SY <-- */ class NetworkHelper(
    private val context: Context,
    private val preferences: NetworkPreferences,
) {''', '''/* SY --> */ open /* SY <-- */ class NetworkHelper(
    private val context: Context,
    private val preferences: NetworkPreferences,
    // Quick Sync kit: app-lifetime scope for the Cloudflare WebView bypass (Mihon).
    // Defaulted so existing constructions (AppModule, source-api HttpSource) are unchanged.
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main),
) {''')
edit(network_helper, 'CloudflareInterceptor(context, cookieJar, ::defaultUserAgentProvider)',
     'CloudflareInterceptor(context, cookieJar, scope, ::defaultUserAgentProvider)', count=2)
# CloudflareInterceptor.kt / WebViewInterceptor.kt / WebViewUtil.kt are replaced
# wholesale by the overlay copies (the rewritten Mihon versions, adapted).

# The fork has no upstream Google OAuth client secrets. Do NOT ask users to share
# OAuth tokens. It supports WebDAV and SyncYomi; use a separate test folder/key.
prefs_ui = app + 'eu/kanade/presentation/more/settings/screen/SettingsDataScreen.kt'
edit(prefs_ui, '                            SyncManager.SyncService.GOOGLE_DRIVE.value to stringResource(SYMR.strings.google_drive),\n', '')
edit(prefs_ui, '            getSyncNowPref(),', '''            Preference.PreferenceItem.SwitchPreference(
                preference = syncPreferences.quickSyncEnabled(),
                title = "Quick sync (experimental)",
                subtitle = "Sync in the background on reader exit and app return; the reader opens instantly and catches up to the newest page",
            ),
            getSyncNowPref(),''')

prefs = app + 'eu/kanade/domain/sync/SyncPreferences.kt'
edit(prefs, '    fun syncInterval() =', '''    fun quickSyncEnabled() = preferenceStore.getBoolean("quick_sync_enabled_v1", true)

    fun syncInterval() =''')
# Keep endpoints/passwords/device-specific settings out of cloud payloads by default.
for key in ['appSettings', 'sourceSettings', 'privateSettings']:
    edit(prefs, f'getBoolean("sync_{key}", true)', f'getBoolean("sync_{key}", false)', count=2)

# Record an edit clock only when reading progress actually changes. Metadata,
# rescrapes and bookmarks cannot override a later page checkpoint.
chapter_repo = 'data/src/main/java/tachiyomi/data/chapter/ChapterRepositoryImpl.kt'
imports(chapter_repo, 'tachiyomi.domain.sync.ProgressStamp')
edit(chapter_repo, '''            chapterUpdates.forEach { chapterUpdate ->
                chaptersQueries.update(''', '''            chapterUpdates.forEach { chapterUpdate ->
                val current = chaptersQueries.getChapterById(chapterUpdate.id).executeAsOneOrNull()
                var mergedMemo = chapterUpdate.memo ?: current?.memo
                if (current != null) {
                    val proposed = mergedMemo ?: current.memo
                    mergedMemo = if (ProgressStamp.compare(current.memo, proposed, ProgressStamp.PAGE) > 0)
                        ProgressStamp.copyStamp(proposed, current.memo, ProgressStamp.PAGE) else proposed
                    val changed = (chapterUpdate.read != null && chapterUpdate.read != current.read) ||
                        (chapterUpdate.lastPageRead != null && chapterUpdate.lastPageRead != current.last_page_read)
                    if (changed) mergedMemo = ProgressStamp.changed(mergedMemo, ProgressStamp.PAGE, current.memo)
                }
                chaptersQueries.update(''')
edit(chapter_repo, 'memo = chapterUpdate.memo?.let(MemoColumnAdapter::encode),', 'memo = mergedMemo?.let(MemoColumnAdapter::encode),')

# Library membership/category edits get their own clock, not the chapter counter.
manga_repo = 'data/src/main/java/tachiyomi/data/manga/MangaRepositoryImpl.kt'
imports(manga_repo, 'tachiyomi.domain.sync.ProgressStamp')
edit(manga_repo, '''            mangaUpdates.forEach { value ->
                mangasQueries.update(''', '''            mangaUpdates.forEach { value ->
                val current = mangasQueries.getMangaById(value.id, MangaMapper::mapManga).executeAsOneOrNull()
                var mergedMemo = value.memo ?: current?.memo
                if (current != null) {
                    val proposed = mergedMemo ?: current.memo
                    mergedMemo = if (ProgressStamp.compare(current.memo, proposed, ProgressStamp.LIBRARY) > 0)
                        ProgressStamp.copyStamp(proposed, current.memo, ProgressStamp.LIBRARY) else proposed
                    if (value.favorite != null && value.favorite != current.favorite) {
                        mergedMemo = ProgressStamp.changed(mergedMemo, ProgressStamp.LIBRARY, current.memo)
                    }
                }
                mangasQueries.update(''')
edit(manga_repo, 'memo = value.memo?.let(MemoColumnAdapter::encode),', 'memo = mergedMemo?.let(MemoColumnAdapter::encode),')
edit(manga_repo, '''    override suspend fun setMangaCategories(mangaId: Long, categoryIds: List<Long>) {
        handler.await(inTransaction = true) {''', '''    override suspend fun setMangaCategories(mangaId: Long, categoryIds: List<Long>) {
        val changedMemo = handler.await(inTransaction = true) {''')
edit(manga_repo, '''            categoryIds.map { categoryId ->
                mangas_categoriesQueries.insert(mangaId, categoryId)
            }
        }
    }''', '''            categoryIds.map { categoryId ->
                mangas_categoriesQueries.insert(mangaId, categoryId)
            }
            mangasQueries.getMangaById(mangaId, MangaMapper::mapManga).executeAsOneOrNull()?.let {
                ProgressStamp.changed(it.memo, ProgressStamp.LIBRARY)
            }
        }
        if (changedMemo != null) partialUpdate(MangaUpdate(id = mangaId, memo = changedMemo))
    }''')

# Membership updates request a debounced transfer while the app is still open.
manga_update = app + 'eu/kanade/domain/manga/interactor/UpdateManga.kt'
imports(manga_update, 'android.app.Application', 'eu.kanade.tachiyomi.data.sync.QuickSync', 'uy.kohesive.injekt.Injekt', 'uy.kohesive.injekt.api.get')
edit(manga_update, '        return mangaRepository.update(mangaUpdate)', '''        val result = mangaRepository.update(mangaUpdate)
        if (result && mangaUpdate.favorite != null) QuickSync.request(Injekt.get<Application>())
        return result''')
edit(manga_update, '        return mangaRepository.updateAll(mangaUpdates)', '''        val result = mangaRepository.updateAll(mangaUpdates)
        if (result && mangaUpdates.any { it.favorite != null }) QuickSync.request(Injekt.get<Application>())
        return result''')
edit(manga_update, '''        return mangaRepository.update(
            MangaUpdate(id = mangaId, favorite = favorite, dateAdded = dateAdded),
        )''', '''        val result = mangaRepository.update(
            MangaUpdate(id = mangaId, favorite = favorite, dateAdded = dateAdded),
        )
        if (result) QuickSync.request(Injekt.get<Application>())
        return result''')

service = sync + 'service/SyncService.kt'
imports(service, 'tachiyomi.data.MemoColumnAdapter', 'tachiyomi.domain.sync.ProgressStamp')
edit(service, '    protected fun mergeSyncData(', '    fun mergeSyncData(')
edit(service, 'return "${manga.source}|${manga.url}|${manga.title.lowercase().trim()}|${manga.author?.lowercase()?.trim()}"', 'return "${manga.source}|${manga.url}"')
edit(service, 'return "${chapter.url}|${chapter.name}|${chapter.chapterNumber}"', 'return chapter.url')
edit(service, '''                    // Compare versions to decide which manga to keep
                    if (local.version >= remote.version) {''', '''                    // Page counters must not decide library membership or categories.
                    val localMemo = MemoColumnAdapter.decode(local.memo)
                    val remoteMemo = MemoColumnAdapter.decode(remote.memo)
                    val libraryOrder = ProgressStamp.compare(localMemo, remoteMemo, ProgressStamp.LIBRARY)
                    val takeLocal = if (libraryOrder != 0) libraryOrder > 0 else
                        (local.favoriteModifiedAt ?: 0L) > (remote.favoriteModifiedAt ?: 0L) ||
                        ((local.favoriteModifiedAt ?: 0L) == (remote.favoriteModifiedAt ?: 0L) && local.version >= remote.version)
                    if (takeLocal) {''')
edit(service, '''                    chosenChapter
                }
                else -> {''', '''                    // Latest explicit reading edit wins, including rereads and
                    // marking unread. Do not use sticky OR/max progress or bookmarks.
                    val localMemo = MemoColumnAdapter.decode(localChapter.memo)
                    val remoteMemo = MemoColumnAdapter.decode(remoteChapter.memo)
                    val readingOrder = ProgressStamp.compare(localMemo, remoteMemo, ProgressStamp.PAGE)
                    val progress = if (readingOrder > 0) localChapter else if (readingOrder < 0) remoteChapter else chosenChapter
                    val winningRead = progress.read
                    val winningPage = progress.lastPageRead
                    val winningMemo = MemoColumnAdapter.decode(progress.memo)
                    chosenChapter.read = winningRead
                    chosenChapter.lastPageRead = winningPage
                    chosenChapter.memo = MemoColumnAdapter.encode(
                        ProgressStamp.copyStamp(MemoColumnAdapter.decode(chosenChapter.memo), winningMemo, ProgressStamp.PAGE),
                    )
                    chosenChapter.version = maxOf(localChapter.version, remoteChapter.version)
                    chosenChapter
                }
                else -> {''')

# WebDAV must keep ETags verbatim and surface conditional-write conflicts so the
# worker actually retries; do not claim success and restore an uncommitted merge.
webdav = sync + 'service/WebDavSyncService.kt'
edit(webdav, '''            pushSyncData(finalSyncData, etag)
            return finalSyncData.backup''', '''            if (!pushSyncData(finalSyncData, etag)) return null
            return finalSyncData.backup''')
edit(webdav, 'response.headers["ETag"]?.trim(\'"\') ?: ""', 'response.headers["ETag"] ?: ""', count=2)
edit(webdav, '    private suspend fun pushSyncData(syncData: SyncData, eTag: String) {', '    private suspend fun pushSyncData(syncData: SyncData, eTag: String): Boolean {')
edit(webdav, '        val backup = syncData.backup ?: return\n\n        if (!validateSettings()) return', '        val backup = syncData.backup ?: return false\n\n        if (!validateSettings()) return false')
edit(webdav, '                xLogI("WebDAV sync completed")', '                xLogI("WebDAV sync completed")\n                return true')
edit(webdav, '                notifier.showSyncError(message)\n', '                notifier.showSyncError(message)\n                return false\n')
# Close every response body, including 304/404 paths.
edit(webdav, '''        return when (response.code) {''', '''        return response.use { response -> when (response.code) {''')
edit(webdav, '''        }
    }

    private suspend fun pushSyncData''', '''        } }
    }

    private suspend fun pushSyncData''')
edit(webdav, '''        when {
            response.isSuccessful ->''', '''        response.use { response -> when {
            response.isSuccessful ->''')
edit(webdav, '''                throw WebDavException("Upload failed: $bodyStr")
            }
        }
    }''', '''                throw WebDavException("Upload failed: $bodyStr")
            }
        } }
    }''')

# Restoring sync state is part of the sync, not a second asynchronous background
# job that the UI can outrun. Keep latest DB edits made during the transfer.
restorer = restore + 'BackupRestorer.kt'
edit(restorer, '    suspend fun restore(uri: Uri, options: RestoreOptions) {', '    suspend fun restore(uri: Uri, options: RestoreOptions): Int {')
edit(restorer, '''            isSync,
        )
    }

    private suspend fun restoreFromFile''', '''            isSync,
        )
        return errors.size
    }

    private suspend fun restoreFromFile''')
manager = sync + 'SyncManager.kt'
imports(manager, 'eu.kanade.tachiyomi.data.backup.BackupNotifier', 'eu.kanade.tachiyomi.data.backup.restore.BackupRestorer', 'tachiyomi.data.MemoColumnAdapter')
edit(manager, 'private val mangaRestorer: MangaRestorer = MangaRestorer()', 'private val mangaRestorer: MangaRestorer = MangaRestorer(isSync = true)')
edit(manager, '    suspend fun syncData() {', '    suspend fun syncData(): Boolean {')
edit(manager, '''            // should we call showSyncError?
            return''', '            return false')
edit(manager, '''            notifier.showSyncSuccess("Sync completed successfully")
            return''', '''            notifier.showSyncSuccess("Sync completed successfully")
            return true''', count=2)
edit(manager, '''            notifier.showSyncError("No data found on remote server.")
            return''', '''            // Empty initial libraries are allowed; do not invent a successful pull.
            return false''')
edit(manager, '''        // Check if it's first sync based on lastSyncTimestamp
        if (syncPreferences.lastSyncTimestamp().get() == 0L && databaseManga.isNotEmpty()) {
            // It's first sync no need to restore data. (just update remote data)
            syncPreferences.lastSyncTimestamp().set(Date().time)
            notifier.showSyncSuccess("Updated remote data successfully")
            return
        }
''', '')
# Re-merge with the database after the network round trip: pages may have been
# saved since the initial snapshot. The restore merge below is a second guard.
edit(manager, '        val (filteredFavorites, nonFavorites) = filterFavoritesAndNonFavorites(remoteBackup)', '''        val freshManga = backupCreator.backupMangas(getAllMangaThatNeedsSync(), backupOptions)
        val currentBackup = backup.copy(backupManga = freshManga)
        val safeRemote = syncService!!.mergeSyncData(
            SyncData(backup = currentBackup), SyncData(backup = remoteBackup),
        ).backup ?: return false
        val (filteredFavorites, nonFavorites) = filterFavoritesAndNonFavorites(safeRemote)''')
# For all remaining restore field assignments use the freshly merged state.
for field in ['backupCategories', 'backupSources', 'backupPreferences', 'backupSourcePreferences', 'backupExtensionStores', 'backupSavedSearches', 'backupFeeds']:
    edit(manager, f'{field} = remoteBackup.{field}', f'{field} = safeRemote.{field}')
edit(manager, '''            BackupRestoreJob.start(
                context,
                backupUri,
                sync = true,
                options = RestoreOptions(
                    appSettings = true,
                    sourceSettings = true,
                    libraryEntries = true,
                    extensionStores = true,
                ),
            )

            // update the sync timestamp
            syncPreferences.lastSyncTimestamp().set(Date().time)
        } else {
            logcat(LogPriority.ERROR) { "Failed to write sync data to file" }
        }
    }''', '''            val errors = BackupRestorer(context, BackupNotifier(context), true).restore(
                backupUri,
                RestoreOptions(
                    appSettings = syncOptions.appSettings,
                    sourceSettings = syncOptions.sourceSettings,
                    libraryEntries = true,
                    extensionStores = syncOptions.extensionStores,
                    categories = syncOptions.categories,
                ),
            )
            if (errors != 0) return false
            syncPreferences.lastSyncTimestamp().set(Date().time)
            return true
        }
        logcat(LogPriority.ERROR) { "Failed to write sync data to file" }
        return false
    }''')
edit(manager, '''            if (remoteChapter == null || localChapter.version != remoteChapter.version) {''', '''            if (remoteChapter == null || localChapter.version != remoteChapter.version ||
                localChapter.read != remoteChapter.read || localChapter.last_page_read != remoteChapter.lastPageRead ||
                localChapter.bookmark != remoteChapter.bookmark || localChapter.memo != MemoColumnAdapter.decode(remoteChapter.memo)
            ) {''')
edit(manager, '        if (localManga.version != remoteManga.version) {', '        if (localManga.version != remoteManga.version || localManga.favorite != remoteManga.favorite || localManga.memo != MemoColumnAdapter.decode(remoteManga.memo)) {')
edit(manager, 'Triple(it.source, it.url, it.title)', 'Pair(it.source, it.url)', count=2)
edit(manager, 'Triple(remoteManga.source, remoteManga.url, remoteManga.title)', 'Pair(remoteManga.source, remoteManga.url)')
edit(manager, 'Triple(nonFavorite.source, nonFavorite.url, nonFavorite.title)', 'Pair(nonFavorite.source, nonFavorite.url)')
edit(manager, '                    val updatedManga = localManga.copy(favorite = nonFavorite.favorite)', '''                    val updatedManga = localManga.copy(
                        favorite = nonFavorite.favorite,
                        favoriteModifiedAt = nonFavorite.favoriteModifiedAt,
                        version = maxOf(localManga.version, nonFavorite.version),
                        memo = MemoColumnAdapter.decode(nonFavorite.memo),
                    )''')

manga_restorer = restore + 'restorers/MangaRestorer.kt'
imports(manga_restorer, 'tachiyomi.domain.sync.ProgressStamp')
edit(manga_restorer, '''        return if (isSync) {
            chapter.copy(
                id = dbChapter.id,
                bookmark = chapter.bookmark || dbChapter.bookmark,
                read = chapter.read,
                lastPageRead = chapter.lastPageRead,''', '''        return if (isSync) {
            val progress = if (ProgressStamp.compare(dbChapter.memo, chapter.memo, ProgressStamp.PAGE) > 0) dbChapter else chapter
            chapter.copy(
                id = dbChapter.id,
                bookmark = chapter.bookmark,
                read = progress.read,
                lastPageRead = progress.lastPageRead,
                memo = ProgressStamp.copyStamp(chapter.memo, progress.memo, ProgressStamp.PAGE),''')
edit(manga_restorer, '        if (mangaCategoriesToUpdate.isNotEmpty()) {', '        if (mangaCategoriesToUpdate.isNotEmpty() || isSync) {')

# A running job no longer drops subsequent requests, and failed/conflicted
# requests are retried rather than reported as success.
worker = sync + 'SyncDataJob.kt'
imports(worker, 'kotlinx.coroutines.CancellationException')
edit(worker, '''            SyncManager(context).syncData()
            Result.success()''', '''            if (QuickSync.perform(context)) Result.success() else Result.retry()''')
edit(worker, '''        } catch (e: Exception) {
            logcat(LogPriority.ERROR, e)''', '''        } catch (e: Exception) {
            if (e is CancellationException) throw e
            logcat(LogPriority.ERROR, e)''')
edit(worker, '            Result.success() // try again next time', '            Result.retry()')
edit(worker, '''        fun startNow(context: Context, manual: Boolean = false) {
            val wm''', '''        fun startNow(context: Context, manual: Boolean = false) {
            if (Injekt.get<SyncPreferences>().quickSyncEnabled().get()) {
                QuickSync.request(context, immediate = manual)
                return
            }
            val wm''')

app_file = app + 'eu/kanade/tachiyomi/App.kt'
imports(app_file, 'eu.kanade.tachiyomi.data.sync.QuickSync')
edit(app_file, 'if (syncPreferences.isSyncEnabled() && syncTriggerOpt.syncOnAppStart)', 'if (syncPreferences.isSyncEnabled() && (syncTriggerOpt.syncOnAppStart || syncPreferences.quickSyncEnabled().get()))')
edit(app_file, 'if (syncPreferences.isSyncEnabled() && syncTriggerOpt.syncOnAppResume)', 'if (syncPreferences.isSyncEnabled() && (syncTriggerOpt.syncOnAppResume || syncPreferences.quickSyncEnabled().get()))')
edit(app_file, '''        SecureActivityDelegate.onApplicationStopped()
''', '''        SecureActivityDelegate.onApplicationStopped()
        QuickSync.request(this@App, immediate = true)
''')

# Await all queued DB page writes before the outgoing sync checkpoint.
vm = reader + 'ReaderViewModel.kt'
imports(vm, 'eu.kanade.tachiyomi.data.sync.QuickSync', 'kotlinx.coroutines.Job', 'kotlinx.coroutines.sync.Mutex', 'kotlinx.coroutines.sync.withLock', 'kotlinx.coroutines.withTimeoutOrNull', 'tachiyomi.domain.chapter.interactor.GetChapter')
edit(vm, '    private val mutableState = MutableStateFlow(State())', '''    private val pageSaveMutex = Mutex()
    private var lastPageSave: Job? = null
    private var refreshingCloudProgress = false
    private var userNavigatedDuringRefresh = false

    private val mutableState = MutableStateFlow(State())''')
edit(vm, '''        // Save last page read and mark as read if needed
        viewModelScope.launchNonCancellable {
            updateChapterProgress(selectedChapter, page/* SY --> */, hasExtraPage/* SY <-- */)
        }''', '''        // Do not turn an old, initially rendered page into a newer edit while
        // refreshing the suspended reader on device switch. If the user turns a
        // page while the background refresh runs, their position always wins
        // and the pending jump to the synced page is dropped.
        if (refreshingCloudProgress) {
            userNavigatedDuringRefresh = true
            return
        }
        lastPageSave = viewModelScope.launchNonCancellable {
            pageSaveMutex.withLock {
                updateChapterProgress(selectedChapter, page/* SY --> */, hasExtraPage/* SY <-- */)
            }
        }''')
edit(vm, '''            try {
                val manga = getManga.await(mangaId)''', '''            try {
                val app = Injekt.get<Application>()
                // Open instantly from the local library; page loading must never
                // wait for the network (Quick Sync 0.2: no black screen). The
                // background refresh below applies the newer cloud page once it
                // lands, unless the user already turned a page themselves.
                if (page == null && !getIncognitoState.await(getManga.await(mangaId)?.source) && syncPreferences.quickSyncEnabled().get()) {
                    beginCloudRefresh()
                    viewModelScope.launchNonCancellable {
                        if (!refreshCloudProgress(incognitoChecked = true)) withUIContext {
                            android.widget.Toast.makeText(app, "Cloud sync has not finished. This device may show an older page.", android.widget.Toast.LENGTH_LONG).show()
                        }
                    }
                }
                val manga = getManga.await(mangaId)''')
edit(vm, '''    fun onActivityFinish() {
        deletePendingChapters()
    }''', '''    fun onActivityFinish() {
        deletePendingChapters()
    }

    suspend fun checkpointForSync() {
        lastPageSave?.join()
        updateHistory()
        if (!incognitoMode) QuickSync.request(Injekt.get<Application>(), immediate = true)
    }

    fun beginCloudRefresh() {
        refreshingCloudProgress = true
    }

    /**
     * Bounded background catch-up: pages are already on screen when this runs.
     * Only a merged, newer cloud page is applied; a page the user turned to
     * while the sync ran keeps priority and the jump is dropped.
     */
    suspend fun refreshCloudProgress(incognitoChecked: Boolean = false): Boolean {
        try {
            if (!incognitoChecked && incognitoMode) return true
            lastPageSave?.join()
            val fresh = QuickSync.beforeReading(Injekt.get<Application>())
            if (!fresh) return false
            // The refresh can land before the loader finished: wait briefly for
            // the chapter so the synced position is not silently dropped.
            val current = withTimeoutOrNull(10_000) {
                state.map { it.currentChapter }.filterNotNull().first()
            } ?: return true
            val id = current.chapter.id ?: return true
            val saved = Injekt.get<GetChapter>().await(id) ?: return false
            val localPage = current.chapter.last_page_read
            val syncedPage = saved.lastPageRead.toInt()
            current.chapter.read = saved.read
            current.chapter.last_page_read = syncedPage
            if (!userNavigatedDuringRefresh && syncedPage >= 0 && syncedPage != localPage) {
                chapterPageIndex = syncedPage
                current.requestedPage = syncedPage
                // If pages are still loading, the viewer starts at requestedPage;
                // if they are already shown, seek to the synced position now.
                if (current.pages != null) eventChannel.send(Event.RestoreSyncedPage(syncedPage))
            }
            return true
        } finally {
            refreshingCloudProgress = false
            userNavigatedDuringRefresh = false
        }
    }''')
edit(vm, '''        data object PageChanged : Event''', '''        data object PageChanged : Event
        data class RestoreSyncedPage(val index: Int) : Event''')
edit(vm, '''                    lastPageRead = readerChapter.chapter.last_page_read.toLong(),
                ),
            )''', '''                    lastPageRead = readerChapter.chapter.last_page_read.toLong(),
                ),
            )
            if (syncPreferences.quickSyncEnabled().get()) {
                if (readerChapter.pages?.lastIndex == pageIndex) QuickSync.request(Injekt.get<Application>())
                else QuickSync.pageSaved(Injekt.get<Application>())
            }''')

activity = reader + 'ReaderActivity.kt'
edit(activity, '            viewModel.updateHistory()', '            viewModel.checkpointForSync()')
edit(activity, '''        viewModel.restartReadTimer()
''', '''        viewModel.restartReadTimer()
        // Background catch-up only: resume never blocks the reader behind a
        // dialog while a sync runs (Quick Sync 0.2).
        if (!viewModel.needsInit() && !viewModel.incognitoMode && Injekt.get<eu.kanade.domain.sync.SyncPreferences>().quickSyncEnabled().get()) {
            viewModel.beginCloudRefresh()
            lifecycleScope.launch {
                if (!viewModel.refreshCloudProgress()) {
                    toast("Cloud sync has not finished. This device may show an older page.")
                }
            }
        }
''')
edit(activity, '''                    ReaderViewModel.Event.PageChanged -> {''', '''                    is ReaderViewModel.Event.RestoreSyncedPage -> moveToPageIndex(event.index)
                    ReaderViewModel.Event.PageChanged -> {''')

# Read/resume buttons open immediately again (Quick Sync 0.2); a background
# sync is scheduled and the open reader jumps to the newest page when it lands.
library_ui = app + 'eu/kanade/tachiyomi/ui/library/LibraryTab.kt'
imports(library_ui, 'eu.kanade.tachiyomi.data.sync.QuickSync')
edit(library_ui, '''                            scope.launchIO {
                                val chapter = screenModel.getNextUnreadChapter(it.manga)''', '''                            scope.launchIO {
                                QuickSync.request(context, immediate = true)
                                val chapter = screenModel.getNextUnreadChapter(it.manga)''')
manga_ui = app + 'eu/kanade/tachiyomi/ui/manga/MangaScreen.kt'
imports(manga_ui, 'eu.kanade.tachiyomi.data.sync.QuickSync')
edit(manga_ui, 'onContinueReading = { continueReading(context, screenModel.getNextUnreadChapter()) },', '''onContinueReading = {
                QuickSync.request(context, immediate = true)
                continueReading(context, screenModel.getNextUnreadChapter())
            },''')
history_ui = app + 'eu/kanade/tachiyomi/ui/history/HistoryTab.kt'
imports(history_ui, 'eu.kanade.tachiyomi.data.sync.QuickSync')
edit(history_ui, '''                openChapter(context, screenModel.getNextChapter())''', '''                QuickSync.request(context, immediate = true)
                openChapter(context, screenModel.getNextChapter())''')

for file in (ROOT / 'overlay').rglob('*'):
    if file.is_file():
        destination = source / file.relative_to(ROOT / 'overlay')
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, destination)

print('Applied Quick Sync 0.3 (Komikku master 1656575e8 + modern Cloudflare bypass) to the source tree. Device testing is still required.')
