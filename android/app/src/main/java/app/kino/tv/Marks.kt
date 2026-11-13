package app.kino.tv

import android.content.Context
import org.json.JSONObject

object Marks {
    lateinit var app: Context
    private var cache: JSONObject? = null

    private fun root(): JSONObject {
        cache?.let { return it }
        val s = app.getSharedPreferences("kino_marks", Context.MODE_PRIVATE).getString("m", null)
        val o = try { if (s == null) JSONObject() else JSONObject(s) } catch (_: Exception) { JSONObject() }
        cache = o
        return o
    }

    private fun sect(name: String): JSONObject {
        val r = root()
        return r.optJSONObject(name) ?: JSONObject().also { r.put(name, it) }
    }

    @Synchronized
    private fun save() {
        app.getSharedPreferences("kino_marks", Context.MODE_PRIVATE).edit().putString("m", root().toString()).apply()
    }

    @Synchronized
    fun setWatched(id: String, flag: Boolean) { sect("w").put(id, flag); save() }

    @Synchronized
    fun setHidden(id: String, flag: Boolean) { sect("h").put(id, flag); save() }

    @Synchronized
    fun setPinned(id: String, ts: Double) { sect("p").put(id, ts); save() }

    @Synchronized
    fun clearProgress(id: String) {
        val f = sect("f")
        val pre = "$id|"
        f.keys().asSequence().filter { it.startsWith(pre) }.toList().forEach { k ->
            val e = f.getJSONObject(k)
            if (e.optBoolean("done")) e.put("pos", 0) else f.remove(k)
        }
        save()
    }

    @Synchronized
    fun progress(item: Item, fid: Int, pos: Long, dur: Long) {
        if (dur <= 0) return
        val done = pos >= dur * 0.9
        val f = sect("f")
        f.put("${item.id}|$fid", JSONObject().put("pos", if (done) 0 else pos).put("dur", dur).put("ts", System.currentTimeMillis() / 1000.0).put("done", done))
        if (done && item.files.all { it.fid == fid || f.optJSONObject("${item.id}|${it.fid}")?.optBoolean("done") == true }) {
            sect("w").put(item.id, true)
        }
        save()
    }

    @Synchronized
    fun apply(it: Item): Item {
        val w = sect("w"); val h = sect("h"); val p = sect("p"); val f = sect("f")
        var rf = -1; var rp = 0L; var rd = 0L; var rt = 0.0
        val files = it.files.map { pf ->
            val e = f.optJSONObject("${it.id}|${pf.fid}")
            if (e == null) pf.copy(watched = false, pos = 0, dur = 0) else {
                val done = e.optBoolean("done")
                val pos = e.optLong("pos")
                val ts = e.optDouble("ts", 0.0)
                if (!done && pos > 0 && ts >= rt) { rf = pf.fid; rp = pos; rd = e.optLong("dur"); rt = ts }
                pf.copy(watched = done, pos = pos, dur = e.optLong("dur"))
            }
        }
        return it.copy(
            inWatched = w.optBoolean(it.id),
            hidden = h.optBoolean(it.id),
            pinned = p.optDouble(it.id, 0.0),
            files = files,
            resumeFid = rf, resumePos = rp, resumeDur = rd, resumeTs = rt,
        )
    }
}
