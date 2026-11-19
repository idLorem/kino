package app.kino.tv

import android.content.Context
import android.content.Intent
import android.media.tv.TvContract
import android.media.tv.TvInputInfo
import android.media.tv.TvInputManager
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.ui.draw.clip
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject

object Pc {
    suspend fun state(c: Conn, tv: Boolean = false, watch: Boolean = false): JSONObject? = try {
        Net.get(c, if (tv) "/api/tv/state" + (if (watch) "?w=1" else "") else "/api/pc/state")
    } catch (_: Exception) {
        null
    }

    suspend fun play(c: Conn, id: String, fid: Int, pos: Long): String? = try {
        val r = Net.post(c, "/api/pc/play", JSONObject().put("id", id).put("fid", fid).put("pos", pos))
        if (r.optBoolean("ok")) null else r.optString("error", "start")
    } catch (_: Exception) {
        "net"
    }

    suspend fun outputs(c: Conn): JSONObject? = try {
        Net.get(c, "/api/pc/outputs")
    } catch (_: Exception) {
        null
    }

    suspend fun setOutput(c: Conn, key: String, v: String): JSONObject? = try {
        Net.post(c, "/api/pc/output", JSONObject().put(key, v))
    } catch (_: Exception) {
        null
    }

    suspend fun cmd(c: Conn, op: String, key: String? = null, v: Any? = null, tv: Boolean = false, dev: String = ""): JSONObject? = try {
        val b = JSONObject().put("op", op).put("dev", dev)
        if (key != null) b.put(key, v)
        Net.post(c, if (tv) "/api/tv/cmd" else "/api/pc/cmd", b)
    } catch (_: Exception) {
        null
    }

    suspend fun report(c: Conn, body: JSONObject): JSONObject? = try {
        Net.post(c, "/api/tv/report", body)
    } catch (_: Exception) {
        null
    }

    fun errText(code: String): String = when (code) {
        "noplayer" -> tr("На компьютере нет плеера: установите VLC или скачайте mpv в настройках Kino.", "The PC has no player: install VLC or download mpv in Kino settings.")
        "nofile" -> tr("Файл не найден на компьютере", "File not found on the PC")
        "net" -> tr("Нет связи с компьютером", "Can't reach the PC")
        else -> tr("Не удалось запустить на ПК", "Couldn't start on the PC")
    }
}

object Hdmi {
    fun inputs(ctx: Context): List<Pair<String, String>> = try {
        val tm = ctx.getSystemService(Context.TV_INPUT_SERVICE) as TvInputManager
        tm.tvInputList.filter { it.type == TvInputInfo.TYPE_HDMI }.map { i ->
            i.id to (i.loadCustomLabel(ctx)?.toString() ?: i.loadLabel(ctx)?.toString() ?: i.id)
        }
    } catch (_: Exception) {
        emptyList()
    }

    fun go(ctx: Context, id: String): Boolean = try {
        ctx.startActivity(Intent(Intent.ACTION_VIEW, TvContract.buildChannelUriForPassthroughInput(id)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        true
    } catch (_: Exception) {
        false
    }
}

private fun JSONObject.items(key: String): List<JSONObject> {
    val a = optJSONArray(key) ?: return emptyList()
    return (0 until a.length()).map { a.getJSONObject(it) }
}

private fun JSONObject.tracks(key: String): List<Triple<Int, String, Boolean>> {
    val a = optJSONArray(key) ?: return emptyList()
    return (0 until a.length()).map { i ->
        val o = a.getJSONObject(i)
        Triple(o.optInt("id"), o.optString("title"), o.optBoolean("sel"))
    }
}

@Composable
fun PcRemoteScreen(conn: Conn, onBack: () -> Unit, onHdmi: (() -> Unit)?, onRefresh: () -> Unit, tv: Boolean = false) {
    BackHandler { onBack() }
    val scope = rememberCoroutineScope()
    var st by remember { mutableStateOf<JSONObject?>(null) }
    var dialog by remember { mutableStateOf<String?>(null) }
    var scrub by remember { mutableStateOf<Long?>(null) }
    var vscrub by remember { mutableStateOf<Int?>(null) }
    var vbarW by remember { mutableIntStateOf(1) }
    var barW by remember { mutableIntStateOf(1) }
    var lost by remember { mutableIntStateOf(0) }
    var wasActive by remember { mutableStateOf(false) }
    var outs by remember { mutableStateOf<JSONObject?>(null) }
    var outBusy by remember { mutableStateOf(false) }
    val cp = compact()

    LaunchedEffect(Unit) { if (!tv) outs = Pc.outputs(conn) }

    LaunchedEffect(Unit) {
        while (true) {
            val r = Pc.state(conn, tv, true)
            if (r != null) {
                st = r
                lost = 0
                if (r.optBoolean("active")) wasActive = true
            } else {
                lost++
            }
            delay(250)
        }
    }

    fun send(op: String, key: String? = null, v: Any? = null) {
        scope.launch {
            val r = Pc.cmd(conn, op, key, v, tv, st?.optString("dev") ?: "")
            if (r != null && r.optBoolean("ok") && r.has("pos")) st = r
        }
    }

    fun pickOut(key: String, v: String) {
        scope.launch {
            outBusy = true
            val r = Pc.setOutput(conn, key, v)
            if (r != null && r.optBoolean("ok")) outs = r
            outBusy = false
        }
    }

    val o = outs
    val monList = o?.items("monitors") ?: emptyList()
    val audList = o?.items("audio") ?: emptyList()
    val monSel = o?.optString("monitor") ?: ""
    val audSel = o?.optString("audioSel") ?: ""
    val monName = monList.firstOrNull { it.optString("key") == monSel }?.optString("label") ?: tr("По умолчанию", "Default")
    val audName = audList.firstOrNull { it.optString("id") == audSel }?.optString("name") ?: tr("По умолчанию", "Default")

    val s = st
    val active = s?.optBoolean("active") == true
    val pos = s?.optLong("pos") ?: 0L
    val dur = s?.optLong("dur") ?: 0L
    val paused = s?.optBoolean("pause") == true
    val vol = s?.optInt("vol") ?: 100
    val audio = s?.tracks("audio") ?: emptyList()
    val subs = s?.tracks("sub") ?: emptyList()

    Backdrop {
        val pid = s?.optString("id") ?: ""
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = if (cp) 16.dp else 48.dp, vertical = if (cp) 16.dp else 28.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                BackPill(onBack = onBack)
                if (onHdmi != null) Pill(tr("Вход HDMI", "HDMI input"), onClick = onHdmi, hPad = 16.dp)
                if (monList.isNotEmpty() || audList.isNotEmpty()) Pill(tr("Вывод", "Output"), onClick = { dialog = "out" }, hPad = 16.dp)
                if (active && s?.optBoolean("tracks", true) == true) {
                    Spacer(Modifier.weight(1f))
                    Pill("", onClick = { dialog = "set" }, hPad = 12.dp, leading = { c -> GearIcon(c, 20.dp) })
                }
            }
            if (s == null) {
                Text(if (lost > 2) tr("Нет связи с компьютером", "Can't reach the PC") else tr("Загрузка…", "Loading…"), color = C.muted, fontSize = 18.sp)
            } else if (!active) {
                Text(if (wasActive) if (tv) tr("Воспроизведение на ТВ закончилось", "Playback on the TV has ended") else tr("Воспроизведение на ПК закончилось", "Playback on the PC has ended") else tr("На ПК ничего не играет", "Nothing is playing on the PC"), color = C.muted, fontSize = 18.sp)
                if (wasActive) Pill(tr("Обновить список", "Refresh list"), onClick = { onRefresh() }, hPad = 16.dp)
            } else {
                if (cp && pid.isNotEmpty()) {
                    coil.compose.AsyncImage(
                        model = conn.posterUrl(pid),
                        contentDescription = null,
                        contentScale = androidx.compose.ui.layout.ContentScale.Crop,
                        modifier = Modifier.fillMaxWidth().aspectRatio(1f).clip(androidx.compose.foundation.shape.RoundedCornerShape(20.dp)).background(androidx.compose.ui.graphics.Color(0xFF111111)),
                    )
                }
                Text(s.optString("title"), color = C.text, fontSize = if (cp) 20.sp else 28.sp, fontWeight = FontWeight.Bold, maxLines = 2)
                Text(if (tv) tr("Играет на ТВ", "Playing on the TV") else tr("Играет на ПК", "Playing on the PC"), color = C.muted, fontSize = 14.sp)
                val shown = scrub ?: pos
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(fmtTime(shown), color = if (scrub != null) C.good else C.text, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.weight(1f))
                    Text(fmtTime(dur), color = C.muted, fontSize = 16.sp)
                }
                androidx.compose.foundation.layout.Box(
                    Modifier
                        .fillMaxWidth()
                        .height(36.dp)
                        .onSizeChanged { barW = it.width.coerceAtLeast(1) }
                        .pointerInput(dur) {
                            detectTapGestures(onTap = { o -> if (dur > 0) send("seekto", "ms", (dur * (o.x / barW.toFloat())).toLong()) })
                        }
                        .pointerInput(dur) {
                            detectHorizontalDragGestures(
                                onDragStart = { o -> if (dur > 0) scrub = (dur * (o.x / barW.toFloat())).toLong().coerceIn(0L, dur) },
                                onDragEnd = { scrub?.let { send("seekto", "ms", it) }; scrub = null },
                                onDragCancel = { scrub = null },
                                onHorizontalDrag = { c, _ -> if (dur > 0) scrub = (dur * (c.position.x / barW.toFloat())).toLong().coerceIn(0L, dur) },
                            )
                        },
                    contentAlignment = Alignment.Center,
                ) {
                    androidx.compose.foundation.Canvas(Modifier.fillMaxWidth().height(20.dp)) {
                        val th = 6.dp.toPx()
                        val y = (size.height - th) / 2f
                        val r = th / 2f
                        val frac = if (dur > 0) (shown.toFloat() / dur.toFloat()).coerceIn(0f, 1f) else 0f
                        val x = size.width * frac
                        val col = if (scrub != null) C.good else C.white
                        drawRoundRect(androidx.compose.ui.graphics.Color(0x33FFFFFF), androidx.compose.ui.geometry.Offset(0f, y), androidx.compose.ui.geometry.Size(size.width, th), androidx.compose.ui.geometry.CornerRadius(r, r))
                        drawRoundRect(col, androidx.compose.ui.geometry.Offset(0f, y), androidx.compose.ui.geometry.Size(x, th), androidx.compose.ui.geometry.CornerRadius(r, r))
                        drawCircle(col, 8.dp.toPx(), androidx.compose.ui.geometry.Offset(x.coerceIn(8.dp.toPx(), size.width - 8.dp.toPx()), size.height / 2f))
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.align(Alignment.CenterHorizontally)) {
                    Pill("−30", onClick = { send("seek", "ms", -30_000) }, hPad = 14.dp)
                    Pill("−10", onClick = { send("seek", "ms", -10_000) }, hPad = 14.dp)
                    Pill("", selected = true, onClick = { send("pause", "v", !paused) }, hPad = 32.dp, leading = { c -> if (paused) PlayGlyph(c, 26.dp) else PauseGlyph(c, 26.dp) })
                    Pill("+10", onClick = { send("seek", "ms", 10_000) }, hPad = 14.dp)
                    Pill("+30", onClick = { send("seek", "ms", 30_000) }, hPad = 14.dp)
                }
                val shownVol = vscrub ?: vol
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(tr("Громкость", "Volume"), color = C.muted, fontSize = 14.sp)
                    Spacer(Modifier.weight(1f))
                    Text("$shownVol%", color = if (vscrub != null) C.good else C.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                }
                androidx.compose.foundation.layout.Box(
                    Modifier
                        .fillMaxWidth()
                        .height(36.dp)
                        .onSizeChanged { vbarW = it.width.coerceAtLeast(1) }
                        .pointerInput(Unit) {
                            detectTapGestures(onTap = { o -> send("vol", "v", (100 * o.x / vbarW.toFloat()).toInt().coerceIn(0, 100)) })
                        }
                        .pointerInput(Unit) {
                            detectHorizontalDragGestures(
                                onDragStart = { o -> vscrub = (100 * o.x / vbarW.toFloat()).toInt().coerceIn(0, 100) },
                                onDragEnd = { vscrub?.let { send("vol", "v", it) }; vscrub = null },
                                onDragCancel = { vscrub = null },
                                onHorizontalDrag = { c, _ -> vscrub = (100 * c.position.x / vbarW.toFloat()).toInt().coerceIn(0, 100) },
                            )
                        },
                    contentAlignment = Alignment.Center,
                ) {
                    androidx.compose.foundation.Canvas(Modifier.fillMaxWidth().height(20.dp)) {
                        val th = 6.dp.toPx()
                        val y = (size.height - th) / 2f
                        val rr = th / 2f
                        val x = size.width * shownVol.coerceIn(0, 100) / 100f
                        val col = if (vscrub != null) C.good else C.white
                        drawRoundRect(androidx.compose.ui.graphics.Color(0x33FFFFFF), androidx.compose.ui.geometry.Offset(0f, y), androidx.compose.ui.geometry.Size(size.width, th), androidx.compose.ui.geometry.CornerRadius(rr, rr))
                        drawRoundRect(col, androidx.compose.ui.geometry.Offset(0f, y), androidx.compose.ui.geometry.Size(x, th), androidx.compose.ui.geometry.CornerRadius(rr, rr))
                        drawCircle(col, 8.dp.toPx(), androidx.compose.ui.geometry.Offset(x.coerceIn(8.dp.toPx(), size.width - 8.dp.toPx()), size.height / 2f))
                    }
                }
            }
        }
        val close = { dialog = null }
        when (dialog) {
            "out" -> DialogBox(tr("Вывод на ПК", "PC output"), close) {
                Text(
                    tr("Выбор запоминается. Если фильм играет, плеер перезапустится с того же места.", "The choice is remembered. If a movie is playing, the player restarts from the same spot."),
                    color = C.muted, fontSize = 14.sp,
                )
                if (monList.isNotEmpty()) Pill(tr("Монитор: ", "Monitor: ") + monName, onClick = { dialog = "mon" }, modifier = Modifier.fillMaxWidth())
                if (audList.isNotEmpty()) Pill(tr("Звук: ", "Audio: ") + audName, onClick = { dialog = "aud" }, modifier = Modifier.fillMaxWidth())
                if (outBusy) Text(tr("Применяю…", "Applying…"), color = C.muted, fontSize = 14.sp)
            }
            "mon" -> DialogBox(tr("Монитор", "Monitor"), close) {
                val def = Opt(tr("По умолчанию", "Default"), monSel.isEmpty()) { pickOut("monitor", "") }
                OptionList(listOf(def) + monList.map { m -> Opt(m.optString("label"), m.optString("key") == monSel) { pickOut("monitor", m.optString("key")) } }, onPicked = close)
            }
            "aud" -> DialogBox(tr("Аудиовыход", "Audio output"), close) {
                val def = Opt(tr("По умолчанию", "Default"), audSel.isEmpty()) { pickOut("audio", "") }
                OptionList(listOf(def) + audList.map { a -> Opt(a.optString("name"), a.optString("id") == audSel) { pickOut("audio", a.optString("id")) } }, onPicked = close)
            }
            "set" -> DialogBox(tr("Настройки", "Settings"), close) {
                Pill(tr("Аудио", "Audio"), onClick = { dialog = "audio" }, modifier = Modifier.fillMaxWidth())
                Pill(tr("Субтитры", "Subtitles"), onClick = { dialog = "sub" }, modifier = Modifier.fillMaxWidth())
            }
            "audio" -> DialogBox(tr("Аудиодорожка", "Audio track"), close) {
                OptionList(audio.map { t -> Opt(t.second, t.third) { send("aid", "id", t.first) } }, onPicked = close)
            }
            "sub" -> DialogBox(tr("Субтитры", "Subtitles"), close) {
                val off = Opt(tr("Выключены", "Off"), subs.none { it.third }) { send("sid", "id", 0) }
                OptionList(listOf(off) + subs.map { t -> Opt(t.second, t.third) { send("sid", "id", t.first) } }, onPicked = close)
            }
        }
    }
}
