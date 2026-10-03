package eu.kanade.tachiyomi.data.sync

import android.content.Context
import eu.kanade.domain.sync.SyncPreferences
import eu.kanade.tachiyomi.data.backup.models.Backup
import eu.kanade.tachiyomi.data.backup.models.BackupChapter
import eu.kanade.tachiyomi.data.backup.models.BackupManga
import eu.kanade.tachiyomi.data.sync.service.SyncData
import eu.kanade.tachiyomi.data.sync.service.SyncService
import io.mockk.every
import io.mockk.mockk
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Test
import tachiyomi.data.MemoColumnAdapter
import tachiyomi.domain.sync.ProgressStamp

class QuickSyncMergeTest {
    private val preferences = mockk<SyncPreferences>(relaxed = true).apply {
        every { uniqueDeviceID() } returns "test-device"
    }
    private val service = object : SyncService(mockk<Context>(relaxed = true), Json { ignoreUnknownKeys = true }, preferences) {
        override suspend fun doSync(syncData: SyncData): Backup? = syncData.backup
    }

    private fun memo(key: String, time: Long, id: String = "test") = MemoColumnAdapter.encode(
        JsonObject(mapOf(key to JsonObject(mapOf("time" to JsonPrimitive(time), "id" to JsonPrimitive(id))))),
    )

    private fun entry(chapter: BackupChapter, title: String = "Title", favorite: Boolean = true, version: Long = 1, stamp: Long = 0) =
        BackupManga(source = 1, url = "/manga/1", title = title, favorite = favorite, chapters = listOf(chapter), version = version, memo = memo(ProgressStamp.LIBRARY, stamp))

    private fun merge(local: BackupManga, remote: BackupManga) = service.mergeSyncData(
        SyncData(backup = Backup(backupManga = listOf(local))),
        SyncData(backup = Backup(backupManga = listOf(remote))),
    ).backup!!.backupManga.single()

    @Test
    fun `latest page beats a larger metadata counter`() {
        val stale = BackupChapter(url = "/chapter/1", name = "Chapter 1", lastPageRead = 2, version = 500, memo = memo(ProgressStamp.PAGE, 10))
        val recent = BackupChapter(url = "/chapter/1", name = "Chapter 1", lastPageRead = 8, version = 2, memo = memo(ProgressStamp.PAGE, 20))
        assertEquals(8L, merge(entry(stale), entry(recent)).chapters.single().lastPageRead)
        assertEquals(8L, merge(entry(recent), entry(stale)).chapters.single().lastPageRead)
    }

    @Test
    fun `intentional backwards seek and mark unread are not sticky`() {
        val done = BackupChapter(url = "/chapter/1", name = "Chapter 1", read = true, lastPageRead = 50, version = 100, memo = memo(ProgressStamp.PAGE, 10))
        val reset = BackupChapter(url = "/chapter/1", name = "Chapter 1", read = false, lastPageRead = 0, version = 2, memo = memo(ProgressStamp.PAGE, 20))
        val result = merge(entry(done), entry(reset)).chapters.single()
        assertFalse(result.read)
        assertEquals(0L, result.lastPageRead)
    }

    @Test
    fun `a metadata rename does not duplicate the same chapter or manga`() {
        val old = BackupChapter(url = "/chapter/1", name = "Chapter 1", lastPageRead = 2, memo = memo(ProgressStamp.PAGE, 10))
        val renamed = BackupChapter(url = "/chapter/1", name = "New chapter title", lastPageRead = 8, memo = memo(ProgressStamp.PAGE, 20))
        val result = merge(entry(old, "Old title"), entry(renamed, "New title"))
        assertEquals(1, result.chapters.size)
        assertEquals(8L, result.chapters.single().lastPageRead)
    }

    @Test
    fun `library removal is independent of reading version counters`() {
        val chapter = BackupChapter(url = "/chapter/1", name = "Chapter 1")
        val local = entry(chapter, favorite = true, version = 900, stamp = 10)
        val remote = entry(chapter, favorite = false, version = 2, stamp = 20)
        assertFalse(merge(local, remote).favorite)
    }
}
