package tachiyomi.domain.sync

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class ProgressStampTest {
    @Test
    fun `a later progress edit wins independently of metadata versions`() {
        val first = ProgressStamp.changed(JsonObject(emptyMap()), ProgressStamp.PAGE, now = 1000, id = "A")
        val next = ProgressStamp.changed(first, ProgressStamp.PAGE, now = 1001, id = "B")
        assertTrue(ProgressStamp.compare(next, first, ProgressStamp.PAGE) > 0)
    }

    @Test
    fun `clock moves forward even if device clock is behind an observed edit`() {
        val remote = JsonObject(mapOf(ProgressStamp.PAGE to JsonObject(mapOf("time" to JsonPrimitive(9000000000000L), "id" to JsonPrimitive("remote")))))
        val next = ProgressStamp.changed(JsonObject(emptyMap()), ProgressStamp.PAGE, observed = remote, now = 1, id = "local")
        assertTrue(ProgressStamp.time(next, ProgressStamp.PAGE) > ProgressStamp.time(remote, ProgressStamp.PAGE))
    }

    @Test
    fun `clock tie breaks deterministically`() {
        fun memo(id: String) = JsonObject(mapOf(ProgressStamp.PAGE to JsonObject(mapOf("time" to JsonPrimitive(2), "id" to JsonPrimitive(id)))))
        assertTrue(ProgressStamp.compare(memo("B"), memo("A"), ProgressStamp.PAGE) > 0)
        assertTrue(ProgressStamp.compare(memo("A"), memo("B"), ProgressStamp.PAGE) < 0)
    }

    @Test
    fun `merge keeps unrelated notes and only replaces reserved stamp`() {
        val base = JsonObject(mapOf("note" to JsonPrimitive("keep me")))
        val winner = ProgressStamp.changed(JsonObject(emptyMap()), ProgressStamp.PAGE, now = 5, id = "X")
        val merged = ProgressStamp.copyStamp(base, winner, ProgressStamp.PAGE)
        assertEquals(base["note"], merged["note"])
        assertEquals(winner[ProgressStamp.PAGE], merged[ProgressStamp.PAGE])
    }

    @Test
    fun `malformed or legacy memo has no progress clock`() {
        assertEquals(0L, ProgressStamp.time(JsonObject(emptyMap()), ProgressStamp.PAGE))
        assertEquals(0L, ProgressStamp.time(JsonObject(mapOf(ProgressStamp.PAGE to JsonPrimitive("bad"))), ProgressStamp.PAGE))
    }
}
