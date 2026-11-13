package app.kino.tv

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import org.json.JSONArray
import org.json.JSONObject

object L {
    var ru by mutableStateOf(true)
}

fun tr(ru: String, en: String): String = if (L.ru) ru else en

class SubFile(val sid: Int, val name: String)

data class PlayFile(
    val fid: Int,
    val label: String,
    val size: Long,
    val watched: Boolean,
    val pos: Long = 0,
    val dur: Long = 0,
    val subs: List<SubFile> = emptyList(),
)

data class Item(
    val id: String,
    val title: String,
    val year: Int,
    val poster: String?,
    val localPoster: Boolean,
    val description: String,
    val duration: Int,
    val rating: Double,
    val genres: String,
    val series: Boolean,
    val inWatched: Boolean,
    val hidden: Boolean,
    val pinned: Double,
    val added: Double,
    val isWatchlist: Boolean,
    val files: List<PlayFile>,
    val resumeFid: Int = -1,
    val resumePos: Long = 0,
    val resumeDur: Long = 0,
    val resumeTs: Double = 0.0,
) {
    val progress: Float get() = if (resumeFid >= 0 && resumeDur > 0) (resumePos.toFloat() / resumeDur.toFloat()).coerceIn(0f, 1f) else 0f

    val ratingText: String get() = if (rating > 0) String.format(java.util.Locale.US, "%.1f", rating) else ""
}

private fun JSONObject.str(name: String): String = if (isNull(name)) "" else optString(name)

private fun JSONObject.num(name: String): Double {
    if (isNull(name)) return 0.0
    val v = opt(name)
    return if (v is Number) v.toDouble() else 0.0
}

private fun isLatin(s: String): Boolean = s.isNotEmpty() && s.all { it.code < 0x250 }

private fun displayTitle(meta: JSONObject?, fallback: String): String {
    if (meta == null) return fallback
    if (!L.ru) {
        val en = meta.str("titleEn")
        if (en.isNotEmpty()) return en
        val o = meta.str("titleOrig")
        if (isLatin(o)) return o
    }
    val ru = meta.str("titleRu")
    if (ru.isNotEmpty()) return ru
    val o = meta.str("titleOrig")
    return if (o.isNotEmpty()) o else fallback
}

private fun genresOf(meta: JSONObject?): String {
    val a: JSONArray = meta?.optJSONArray("genres") ?: return ""
    val out = ArrayList<String>()
    for (i in 0 until minOf(a.length(), 3)) out.add(a.optString(i))
    return out.joinToString(", ")
}

private fun ratingOf(meta: JSONObject?): Double {
    if (meta == null) return 0.0
    for (k in listOf("ratingImdb", "ratingKp", "ratingTmdb")) {
        val v = meta.num(k)
        if (v > 0) return v
    }
    val lb = meta.num("ratingLb")
    return if (lb > 0) lb * 2 else 0.0
}

private fun subsOf(f: JSONObject): List<SubFile> {
    val a = f.optJSONArray("subs") ?: return emptyList()
    val out = ArrayList<SubFile>()
    for (i in 0 until a.length()) {
        val s = a.getJSONObject(i)
        out.add(SubFile(s.optInt("sid"), s.str("name")))
    }
    return out
}

private fun playFiles(o: JSONObject): List<PlayFile> {
    val out = ArrayList<PlayFile>()
    val files = o.optJSONArray("files")
    if (files != null) {
        for (i in 0 until files.length()) {
            val f = files.getJSONObject(i)
            out.add(PlayFile(f.optInt("fid"), f.str("name"), f.optLong("size"), f.optBoolean("watched"), f.optLong("pos"), f.optLong("dur"), subsOf(f)))
        }
    }
    val seasons = o.optJSONArray("seasons")
    if (seasons != null) {
        for (i in 0 until seasons.length()) {
            val s = seasons.getJSONObject(i)
            val sn = s.optInt("season")
            val eps = s.optJSONArray("episodes") ?: continue
            for (j in 0 until eps.length()) {
                val e = eps.getJSONObject(j)
                val en = if (e.isNull("episode")) null else e.optInt("episode")
                val tag = if (en != null) String.format("S%02dE%02d", sn, en) else String.format("S%02d", sn)
                val raw = e.str("name")
                val nice = if (en != null && raw.substringAfterLast('.', "").lowercase() in setOf("mkv", "mp4", "avi", "mov", "m4v", "ts", "webm", "wmv")) tr("Серия ", "Episode ") + en else raw
                out.add(PlayFile(e.optInt("fid"), tag + "  " + nice, e.optLong("size"), e.optBoolean("watched"), e.optLong("pos"), e.optLong("dur"), subsOf(e)))
            }
        }
    }
    return out
}

fun parseLibraryItem(o: JSONObject): Item {
    val meta = o.optJSONObject("meta")
    val title = displayTitle(meta, o.str("title"))
    var year = meta?.optInt("year") ?: 0
    if (year <= 0) year = o.optInt("year")
    val type = meta?.str("type") ?: ""
    val series = if (type.isNotEmpty()) type == "series" else o.str("kind") == "series"
    return Item(
        id = o.str("id"),
        title = title,
        year = year,
        poster = meta?.str("posterPreview")?.ifEmpty { meta?.str("poster") ?: "" }?.ifEmpty { null },
        localPoster = o.optBoolean("localPoster"),
        description = meta?.str("description") ?: "",
        duration = meta?.optInt("duration") ?: 0,
        rating = ratingOf(meta),
        genres = genresOf(meta),
        series = series,
        inWatched = o.optBoolean("inWatched"),
        hidden = o.optBoolean("hidden"),
        pinned = o.num("pinned"),
        added = o.num("added"),
        isWatchlist = false,
        files = playFiles(o),
        resumeFid = o.optJSONObject("resume")?.optInt("fid", -1) ?: -1,
        resumePos = o.optJSONObject("resume")?.optLong("pos") ?: 0,
        resumeDur = o.optJSONObject("resume")?.optLong("dur") ?: 0,
        resumeTs = o.optJSONObject("resume")?.optDouble("ts", 0.0) ?: 0.0,
    )
}

fun parseWatchlistItem(o: JSONObject): Item {
    val meta = o.optJSONObject("meta")
    val key = o.str("key")
    val title = displayTitle(meta, key)
    val type = meta?.str("type") ?: ""
    return Item(
        id = "w|$key",
        title = title,
        year = meta?.optInt("year") ?: 0,
        poster = meta?.str("posterPreview")?.ifEmpty { meta?.str("poster") ?: "" }?.ifEmpty { null },
        localPoster = false,
        description = meta?.str("description") ?: "",
        duration = meta?.optInt("duration") ?: 0,
        rating = ratingOf(meta),
        genres = genresOf(meta),
        series = type == "series",
        inWatched = false,
        hidden = false,
        pinned = o.num("pinned"),
        added = o.num("added"),
        isWatchlist = true,
        files = emptyList(),
    )
}

fun parseItems(arr: JSONArray?, watchlist: Boolean): List<Item> {
    val out = ArrayList<Item>()
    if (arr == null) return out
    for (i in 0 until arr.length()) {
        val o = arr.getJSONObject(i)
        try {
            out.add(Marks.apply(if (watchlist) parseWatchlistItem(o) else parseLibraryItem(o)))
        } catch (_: Exception) {
        }
    }
    return out
}
