package tachiyomi.domain.sync

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import java.util.UUID

/**
 * Reading and library edits use independent logical clocks, carried in the existing
 * memo field. Metadata refreshes do not get to impersonate reading progress.
 * Only install this experimental build on both devices; older clients do not
 * implement this merge policy. No backup/protobuf schema migration is required.
 */
object ProgressStamp {
    const val PAGE = "__komikku_sync_page_v1"
    const val LIBRARY = "__komikku_sync_library_v1"
    private var lastClock = 0L

    fun time(memo: JsonObject, key: String): Long = runCatching {
        (memo[key] as? JsonObject)?.get("time")?.jsonPrimitive?.longOrNull ?: 0L
    }.getOrDefault(0L)

    private fun nonce(memo: JsonObject, key: String): String = runCatching {
        (memo[key] as? JsonObject)?.get("id")?.jsonPrimitive?.content ?: ""
    }.getOrDefault("")

    fun compare(left: JsonObject, right: JsonObject, key: String): Int {
        val clock = time(left, key).compareTo(time(right, key))
        return if (clock != 0) clock else nonce(left, key).compareTo(nonce(right, key))
    }

    @Synchronized
    fun changed(
        memo: JsonObject,
        key: String,
        observed: JsonObject = memo,
        now: Long = System.currentTimeMillis(),
        id: String = UUID.randomUUID().toString(),
    ): JsonObject {
        lastClock = maxOf(now, lastClock + 1, time(memo, key) + 1, time(observed, key) + 1)
        val stamp = JsonObject(mapOf("time" to JsonPrimitive(lastClock), "id" to JsonPrimitive(id)))
        return JsonObject(memo + (key to stamp))
    }

    fun copyStamp(base: JsonObject, winner: JsonObject, key: String): JsonObject {
        val stamp = winner[key] ?: return base
        return JsonObject(base + (key to stamp))
    }
}
