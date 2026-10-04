package eu.kanade.tachiyomi.data.sync

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OutOfQuotaPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkInfo
import eu.kanade.domain.sync.SyncPreferences
import eu.kanade.tachiyomi.data.backup.restore.BackupRestoreJob
import eu.kanade.tachiyomi.util.system.isOnline
import eu.kanade.tachiyomi.util.system.workManager
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import uy.kohesive.injekt.Injekt
import uy.kohesive.injekt.api.get
import java.util.concurrent.TimeUnit

/**
 * Event-driven scheduling, plus a bounded freshness check used by the reader's
 * background catch-up. Opening a chapter, the Start/Resume buttons and app
 * resume never wait for a sync: this object only feeds the background refresh
 * that applies the newest cloud page after pages are already on screen.
 */
object QuickSync {
    private const val WORK = "KomikkuQuickSync"

    /** A sync that finished this recently is fresh; do not run a second full cycle. */
    private const val FRESH_WINDOW_MS = 15_000L

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val queueMutex = Mutex()
    private val syncMutex = Mutex()
    private var pending: Job? = null
    private var pageCheckpoint: Job? = null

    @Volatile
    private var lastSuccessAt = 0L

    private fun enabled(): Boolean = Injekt.get<SyncPreferences>().let {
        it.isSyncEnabled() && it.quickSyncEnabled().get()
    }

    /** Milliseconds since the last fully completed sync; Long.MAX_VALUE if none. */
    private fun syncAge(): Long {
        val done = lastSuccessAt
        return if (done == 0L) Long.MAX_VALUE else System.currentTimeMillis() - done
    }

    @Synchronized
    fun request(context: Context, immediate: Boolean = false) {
        if (!enabled()) return
        val app = context.applicationContext
        if (immediate) pageCheckpoint?.cancel()
        pending?.cancel()
        pending = scope.launch {
            if (!immediate) delay(1500)
            queueMutex.withLock {
                // A sync that just landed already captures the newest edits.
                if (syncAge() < FRESH_WINDOW_MS) return@withLock
                val manager = app.workManager
                // A queued successor will take its snapshot AFTER the active job.
                // Do not drop an edit merely because another sync is running.
                val work = manager.getWorkInfosForUniqueWork(WORK).get()
                if (work.any { it.state == WorkInfo.State.ENQUEUED || it.state == WorkInfo.State.BLOCKED }) {
                    return@withLock
                }
                val request = OneTimeWorkRequestBuilder<SyncDataJob>()
                    .addTag("SyncDataJob")
                    .addTag("SyncDataJob:auto")
                    .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                    .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 10, TimeUnit.SECONDS)
                    .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
                    .build()
                manager.enqueueUniqueWork(WORK, ExistingWorkPolicy.APPEND_OR_REPLACE, request).result.get()
            }
        }
    }

    /** Do not transfer the complete library on every page turn. */
    @Synchronized
    fun pageSaved(context: Context) {
        if (!enabled() || pageCheckpoint?.isActive == true) return
        val app = context.applicationContext
        pageCheckpoint = scope.launch {
            delay(30000)
            request(app, immediate = true)
        }
    }

    /** Also used by scheduled/manual workers, so database restores cannot overlap. */
    suspend fun perform(context: Context): Boolean = withContext(Dispatchers.IO) {
        syncMutex.withLock {
            if (!context.isOnline() || BackupRestoreJob.isRunning(context)) return@withLock false
            val completed = SyncManager(context).syncData()
            if (completed) lastSuccessAt = System.currentTimeMillis()
            completed
        }
    }

    /**
     * Bounded check used only by the reader's background refresh; navigation
     * code must not call this on a tap path. A sync completed moments ago
     * counts as fresh and returns immediately instead of running another
     * download/merge/restore/upload cycle.
     */
    suspend fun beforeReading(context: Context): Boolean {
        if (!enabled()) return true
        if (syncAge() < FRESH_WINDOW_MS) return true
        if (!context.isOnline()) {
            request(context, immediate = true)
            return false
        }
        val success = withTimeoutOrNull(30000) {
            withContext(Dispatchers.IO) {
                for (attempt in 0 until 3) {
                    try {
                        if (perform(context)) return@withContext true
                    } catch (e: CancellationException) {
                        throw e
                    } catch (_: Exception) {
                        // Offline, provider failure or a conditional-write conflict.
                    }
                    if (attempt < 2) delay(1000L * (attempt + 1))
                }
                false
            }
        } ?: false
        if (!success) request(context, immediate = true)
        return success
    }

}
