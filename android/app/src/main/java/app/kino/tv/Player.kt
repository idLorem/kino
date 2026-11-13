package app.kino.tv

import android.content.Context
import android.content.pm.ActivityInfo
import android.content.pm.PackageManager
import android.media.AudioManager
import android.net.Uri
import android.os.Build
import android.view.KeyEvent
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.focusable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.displayCutout
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import kotlinx.coroutines.delay
import org.json.JSONObject
import org.videolan.libvlc.LibVLC
import org.videolan.libvlc.Media
import org.videolan.libvlc.MediaPlayer
import org.videolan.libvlc.util.VLCVideoLayout
import java.util.Locale

class Opt(val label: String, val selected: Boolean, val apply: () -> Unit)

fun fmtTime(ms: Long): String {
    if (ms <= 0) return "0:00"
    val s = ms / 1000
    val h = s / 3600
    val m = (s % 3600) / 60
    val sec = s % 60
    return if (h > 0) String.format(Locale.US, "%d:%02d:%02d", h, m, sec) else String.format(Locale.US, "%d:%02d", m, sec)
}

private fun createVlc(ctx: Context, size: String, pos: String, bg: String, stereo: Boolean): LibVLC {
    val base = arrayListOf("--no-drop-late-frames", "--no-skip-frames")
    if (stereo) base.add("--aout=opensles")
    val styled = ArrayList(base)
    styled.add("--sub-text-scale=" + when (size) { "s" -> 80; "l" -> 150; else -> 100 })
    styled.add("--freetype-background-opacity=" + ((bg.toIntOrNull() ?: 50) * 255 / 100))
    styled.add("--freetype-background-color=0")
    styled.add("--sub-margin=" + when (pos) { "0" -> 0; "2" -> 60; "3" -> 120; else -> 25 })
    return try {
        LibVLC(ctx, styled)
    } catch (_: Exception) {
        LibVLC(ctx, base)
    }
}

private val SCALES = listOf(
    MediaPlayer.ScaleType.SURFACE_BEST_FIT,
    MediaPlayer.ScaleType.SURFACE_FIT_SCREEN,
    MediaPlayer.ScaleType.SURFACE_FILL,
    MediaPlayer.ScaleType.SURFACE_16_9,
    MediaPlayer.ScaleType.SURFACE_4_3,
    MediaPlayer.ScaleType.SURFACE_ORIGINAL,
)

private fun scaleLabel(i: Int): String = when (i) {
    0 -> tr("Вписать", "Fit")
    1 -> tr("Заполнить (с обрезкой)", "Fill (crop)")
    2 -> tr("Растянуть", "Stretch")
    3 -> "16:9"
    4 -> "4:3"
    else -> tr("Оригинал", "Original")
}

private val SPEEDS = listOf(0.5f, 0.75f, 1f, 1.25f, 1.5f, 1.75f, 2f)

private fun langMatch(name: String, lang: String): Boolean {
    val n = name.lowercase()
    return if (lang == "ru") n.contains("russian") || n.contains("рус") || n.contains("[ru") || n.contains("rus")
    else n.contains("english") || n.contains("[en") || n.contains("eng")
}

@Composable
fun DialogBox(title: String, onClose: () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    Box(
        Modifier
            .fillMaxSize()
            .background(Color(0xCC000000))
            .pointerInput(Unit) { detectTapGestures { } },
        contentAlignment = Alignment.Center,
    ) {
        Column(
            Modifier
                .widthIn(max = 600.dp)
                .fillMaxWidth(0.92f)
                .clip(RoundedCornerShape(18.dp))
                .background(Color(0xFF141416))
                .border(1.dp, C.stroke, RoundedCornerShape(18.dp))
                .padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                BackPill(onBack = onClose)
                Text(title, color = C.text, fontSize = 22.sp, fontWeight = FontWeight.Bold, maxLines = 1)
            }
            content()
        }
    }
}

@Composable
fun OptionList(opts: List<Opt>, onPicked: () -> Unit) {
    val first = remember { FocusRequester() }
    val sel = opts.indexOfFirst { it.selected }.let { if (it < 0) 0 else it }
    LaunchedEffect(Unit) {
        try { first.requestFocus() } catch (_: Exception) { }
    }
    if (opts.isEmpty()) {
        Text(tr("Нет вариантов", "No options"), color = C.muted, fontSize = 16.sp)
    }
    LazyColumn(
        verticalArrangement = Arrangement.spacedBy(8.dp),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 8.dp, vertical = 6.dp),
        modifier = Modifier.heightIn(max = 300.dp),
    ) {
        itemsIndexed(opts) { i, o ->
            Pill(
                (if (o.selected) "✓  " else "") + o.label,
                selected = o.selected,
                onClick = { o.apply(); onPicked() },
                modifier = Modifier.fillMaxWidth(),
                focusRequester = if (i == sel) first else null,
            )
        }
    }
}

@Composable
fun PlayerScreen(
    conn: Conn,
    item: Item,
    file: PlayFile,
    nextFile: PlayFile?,
    onNext: (PlayFile) -> Unit,
    onExit: () -> Unit,
) {
    val ctx = LocalContext.current
    val act = ctx as? MainActivity
    val scope = rememberCoroutineScope()
    val touchDevice = remember { ctx.packageManager.hasSystemFeature(PackageManager.FEATURE_TOUCHSCREEN) && !Prefs.isTv(ctx) }
    val pipOk = remember { touchDevice && Build.VERSION.SDK_INT >= 26 && ctx.packageManager.hasSystemFeature(PackageManager.FEATURE_PICTURE_IN_PICTURE) }

    var gen by remember { mutableIntStateOf(0) }
    var startPos by remember { mutableLongStateOf(if (Prefs.str(ctx, "resume", "1") == "1") file.pos else 0L) }
    var hw by remember { mutableStateOf(Prefs.str(ctx, "vdec", "auto") == "auto") }
    var triedSoft by remember { mutableStateOf(false) }
    var aoutStereo by remember { mutableStateOf(Prefs.str(ctx, "aout", "auto") == "stereo") }

    var subSize by remember { mutableStateOf(Prefs.str(ctx, "sub_size", "m")) }
    var subPos by remember { mutableStateOf(Prefs.str(ctx, "sub_pos", "1")) }
    var subBg by remember { mutableStateOf(Prefs.str(ctx, "sub_bg", "50")) }

    var started by remember { mutableStateOf(false) }
    var playing by remember { mutableStateOf(true) }
    var buffering by remember { mutableStateOf(true) }
    var ended by remember { mutableStateOf(false) }
    var failed by remember { mutableStateOf(false) }
    var pos by remember { mutableLongStateOf(0L) }
    var dur by remember { mutableLongStateOf(0L) }
    var tracksTick by remember { mutableIntStateOf(0) }
    var audioList by remember { mutableStateOf<List<Pair<Int, String>>>(emptyList()) }
    var textList by remember { mutableStateOf<List<Pair<Int, String>>>(emptyList()) }
    var audioSel by remember { mutableIntStateOf(-1) }
    var textSel by remember { mutableIntStateOf(-1) }
    var subsAdded by remember { mutableStateOf(false) }
    var audioApplied by remember { mutableStateOf(false) }
    var textApplied by remember { mutableStateOf(false) }

    var showUi by remember { mutableStateOf(true) }
    var touch by remember { mutableLongStateOf(0L) }
    var topFocus by remember { mutableStateOf(false) }
    var bottomFocus by remember { mutableStateOf(false) }
    var dialog by remember { mutableStateOf<String?>(null) }
    var scrub by remember { mutableStateOf<Long?>(null) }
    var scrubStamp by remember { mutableLongStateOf(0L) }
    var dragging by remember { mutableStateOf(false) }
    var hud by remember { mutableStateOf("") }
    var rate by remember { mutableFloatStateOf(1f) }
    var delayMs by remember { mutableIntStateOf(Prefs.str(ctx, "adelay", "0").toIntOrNull() ?: 0) }
    var scaleIdx by remember { mutableIntStateOf(Prefs.str(ctx, "scale", "0").toIntOrNull() ?: 0) }
    var brightness by remember {
        mutableFloatStateOf(
            (act?.window?.attributes?.screenBrightness ?: -1f).takeIf { it >= 0f }
                ?: (android.provider.Settings.System.getInt(ctx.contentResolver, android.provider.Settings.System.SCREEN_BRIGHTNESS, 128) / 255f).coerceIn(0.02f, 1f),
        )
    }
    var volF by remember { mutableFloatStateOf(0f) }
    var barW by remember { mutableIntStateOf(1) }

    val rootFr = remember { FocusRequester() }
    val firstTopFr = remember { FocusRequester() }
    val playFr = remember { FocusRequester() }
    val inUi = topFocus || bottomFocus
    val inPip = act?.inPip?.value == true

    val vlc = remember(gen) { createVlc(ctx, subSize, subPos, subBg, aoutStereo) }
    val mp = remember(gen) { MediaPlayer(vlc) }

    fun poke() {
        showUi = true
        touch = System.currentTimeMillis()
    }

    fun focusRoot() {
        try { rootFr.requestFocus() } catch (_: Exception) { }
    }

    fun readTracks() {
        val a = mp.getAudioTracks() ?: emptyArray()
        val s = mp.getSpuTracks() ?: emptyArray()
        audioList = a.filter { it.id >= 0 }.map { it.id to (it.name ?: "") }
        textList = s.map { it.id to (it.name ?: "") }
        audioSel = mp.getAudioTrack()
        textSel = mp.getSpuTrack()
    }

    fun reportProgress(p: Long, d: Long) {
        Marks.progress(item, file.fid, p, d)
    }

    fun leave() {
        reportProgress(pos, dur)
        onExit()
    }

    fun seekTo(ms: Long) {
        val t = ms.coerceIn(0L, if (dur > 0) dur - 500 else ms)
        mp.setTime(t)
        pos = t
    }

    fun seekRel(delta: Long) {
        seekTo(mp.getTime() + delta)
        hud = (if (delta > 0) "+" else "−") + (kotlin.math.abs(delta) / 1000) + " " + tr("с", "s")
        poke()
    }

    fun applyScrub() {
        val t = scrub
        if (t != null) seekTo(t)
        scrub = null
    }

    fun togglePlay() {
        if (mp.isPlaying()) mp.pause() else mp.play()
        poke()
    }

    BackHandler {
        when {
            dialog != null -> { dialog = null; focusRoot() }
            scrub != null -> scrub = null
            inUi -> { showUi = false; focusRoot() }
            showUi && playing && started -> showUi = false
            else -> leave()
        }
    }

    DisposableEffect(Unit) {
        val a = act
        a?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        a?.pipReady = true
        onDispose {
            a?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
            a?.pipReady = false
            a?.window?.let { w ->
                val lp = w.attributes
                lp.screenBrightness = android.view.WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE
                w.attributes = lp
            }
        }
    }

    val keepOn = (playing || buffering) && !failed
    DisposableEffect(keepOn) {
        val w = act?.window
        if (keepOn) w?.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        onDispose { w?.clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
    }

    var reloadOnStart by remember { mutableStateOf(false) }
    DisposableEffect(act, gen) {
        val owner = act
        val obs = androidx.lifecycle.LifecycleEventObserver { _, ev ->
            if (ev == androidx.lifecycle.Lifecycle.Event.ON_STOP && owner?.inPip?.value != true) {
                try { mp.pause() } catch (_: Exception) { }
                reloadOnStart = true
            } else if (ev == androidx.lifecycle.Lifecycle.Event.ON_START && reloadOnStart) {
                reloadOnStart = false
                failed = false
                started = false
                startPos = pos
                subsAdded = false
                audioApplied = false
                textApplied = false
                gen++
            }
        }
        owner?.lifecycle?.addObserver(obs)
        onDispose { owner?.lifecycle?.removeObserver(obs) }
    }

    DisposableEffect(gen) {
        audioList = emptyList()
        textList = emptyList()
        val m = Media(vlc, Uri.parse(conn.streamUrl(item.id, file.fid)))
        m.setHWDecoderEnabled(hw, false)
        m.addOption(":network-caching=3000")
        if (startPos > 0) m.addOption(":start-time=" + (startPos / 1000.0))
        mp.setMedia(m)
        m.release()
        mp.setEventListener(object : MediaPlayer.EventListener {
            override fun onEvent(event: MediaPlayer.Event) {
                when (event.type) {
                    MediaPlayer.Event.Playing -> { started = true; buffering = false }
                    MediaPlayer.Event.Buffering -> buffering = event.getBuffering() < 100f
                    MediaPlayer.Event.EndReached -> ended = true
                    MediaPlayer.Event.EncounteredError -> failed = true
                    MediaPlayer.Event.ESAdded, MediaPlayer.Event.ESDeleted, MediaPlayer.Event.ESSelected -> tracksTick++
                }
            }
        })
        mp.play()
        onDispose {
            try { mp.setEventListener(null) } catch (_: Exception) { }
            try { mp.stop() } catch (_: Exception) { }
            try { mp.detachViews() } catch (_: Exception) { }
            try { mp.release() } catch (_: Exception) { }
            try { vlc.release() } catch (_: Exception) { }
        }
    }

    LaunchedEffect(gen) {
        var n = 0
        while (true) {
            if (started) {
                pos = mp.getTime().coerceAtLeast(0L)
                dur = mp.getLength().coerceAtLeast(0L)
                playing = mp.isPlaying()
                n++
                if (n % 25 == 0 && dur > 0) reportProgress(pos, dur)
            }
            delay(400)
        }
    }

    LaunchedEffect(tracksTick, started) {
        if (started) readTracks()
    }

    LaunchedEffect(started) {
        if (started && !subsAdded) {
            subsAdded = true
            for (s in file.subs) {
                mp.addSlave(0, Uri.parse(conn.base + "/api/sub/" + item.id + "/" + file.fid + "/" + s.sid + ".srt?t=" + conn.token), false)
            }
            delay(600)
            readTracks()
        }
    }

    LaunchedEffect(started, scaleIdx) {
        if (started) mp.setVideoScale(SCALES[scaleIdx])
    }

    LaunchedEffect(started, rate) {
        if (started) mp.setRate(rate)
    }

    LaunchedEffect(started, delayMs) {
        if (started) mp.setAudioDelay(delayMs * 1000L)
    }

    LaunchedEffect(audioList.size) {
        if (audioList.isNotEmpty() && !audioApplied) {
            audioApplied = true
            val saved = Prefs.str(ctx, "ta_" + item.id, "")
            val pick = audioList.firstOrNull { saved.isNotEmpty() && it.second == saved }
                ?: Prefs.str(ctx, "aud", "auto").takeIf { it != "auto" }?.let { l -> audioList.firstOrNull { langMatch(it.second, l) } }
            if (pick != null) {
                mp.setAudioTrack(pick.first)
                readTracks()
            }
        }
    }

    LaunchedEffect(subsAdded, textList.size) {
        if (subsAdded && !textApplied && textList.isNotEmpty()) {
            delay(300)
            textApplied = true
            val saved = Prefs.str(ctx, "ts_" + item.id, "")
            val pref = Prefs.str(ctx, "sub", "off")
            val pick: Pair<Int, String>? = when {
                saved == "-" -> Pair(-1, "")
                saved.isNotEmpty() -> textList.firstOrNull { it.second == saved }
                pref == "off" -> Pair(-1, "")
                else -> textList.firstOrNull { langMatch(it.second, pref) }
            }
            if (pick != null) {
                mp.setSpuTrack(pick.first)
                readTracks()
            }
        }
    }

    LaunchedEffect(ended) {
        if (ended) {
            reportProgress(dur, dur)
            if (nextFile != null && Prefs.str(ctx, "autonext", "1") == "1") onNext(nextFile) else onExit()
        }
    }

    LaunchedEffect(failed) {
        if (failed && hw && !triedSoft) {
            triedSoft = true
            failed = false
            hw = false
            started = false
            startPos = pos
            gen++
        }
    }

    LaunchedEffect(showUi, touch, inUi, dialog, playing, scrub) {
        if (showUi && !inUi && dialog == null && playing && scrub == null) {
            delay(4500)
            showUi = false
        }
    }

    LaunchedEffect(scrub, scrubStamp, dragging) {
        if (scrub != null && !dragging) {
            delay(4000)
            applyScrub()
        }
    }

    LaunchedEffect(hud) {
        if (hud.isNotEmpty()) {
            delay(1300)
            hud = ""
        }
    }

    LaunchedEffect(Unit) { focusRoot() }

    fun scrubBy(delta: Long, repeat: Int) {
        val step = when {
            repeat < 4 -> 10_000L
            repeat < 12 -> 30_000L
            repeat < 25 -> 60_000L
            else -> 180_000L
        }
        val base = scrub ?: pos
        scrub = (base + delta * step / 10_000L).coerceIn(0L, if (dur > 0) dur else base + step)
        scrubStamp = System.currentTimeMillis()
        showUi = true
    }

    fun adjust(left: Boolean, d: Float) {
        if (left) {
            brightness = (brightness + d * 1.2f).coerceIn(0.02f, 1f)
            act?.window?.let { w ->
                val lp = w.attributes
                lp.screenBrightness = brightness
                w.attributes = lp
            }
            hud = tr("Яркость ", "Brightness ") + (brightness * 100).toInt() + "%"
        } else {
            val am = ctx.getSystemService(Context.AUDIO_SERVICE) as AudioManager
            val max = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
            volF = (volF + d * max * 1.2f).coerceIn(0f, max.toFloat())
            am.setStreamVolume(AudioManager.STREAM_MUSIC, Math.round(volF), 0)
            hud = tr("Громкость ", "Volume ") + Math.round(volF) + "/" + max
        }
    }

    Box(
        Modifier
            .fillMaxSize()
            .background(Color.Black)
            .pointerInput(Unit) {
                var left = true
                detectVerticalDragGestures(
                    onDragStart = { o ->
                        left = o.x < size.width / 2f
                        val am = ctx.getSystemService(Context.AUDIO_SERVICE) as AudioManager
                        volF = am.getStreamVolume(AudioManager.STREAM_MUSIC).toFloat()
                    },
                    onVerticalDrag = { _, dy -> adjust(left, -dy / size.height) },
                )
            }
            .pointerInput(Unit) {
                detectTapGestures(
                    onTap = { if (showUi) showUi = false else poke() },
                    onDoubleTap = { o -> if (o.x < size.width / 2f) seekRel(-10_000) else seekRel(10_000) },
                )
            }
            .focusRequester(rootFr)
            .focusable()
            .onPreviewKeyEvent { e ->
                val code = e.nativeKeyEvent.keyCode
                val handled = when (code) {
                    KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE,
                    KeyEvent.KEYCODE_MEDIA_PLAY, KeyEvent.KEYCODE_MEDIA_PAUSE,
                    KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN,
                    KeyEvent.KEYCODE_MEDIA_REWIND, KeyEvent.KEYCODE_MEDIA_FAST_FORWARD,
                    KeyEvent.KEYCODE_MENU, KeyEvent.KEYCODE_CAPTIONS, KeyEvent.KEYCODE_MEDIA_AUDIO_TRACK -> true
                    else -> false
                }
                if (dialog != null || inUi || !handled) return@onPreviewKeyEvent false
                if (e.type != KeyEventType.KeyDown) return@onPreviewKeyEvent true
                val rc = e.nativeKeyEvent.repeatCount
                when (code) {
                    KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> {
                        if (scrub != null) applyScrub() else togglePlay()
                        poke()
                    }
                    KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE -> togglePlay()
                    KeyEvent.KEYCODE_MEDIA_PLAY -> { mp.play(); poke() }
                    KeyEvent.KEYCODE_MEDIA_PAUSE -> { mp.pause(); poke() }
                    KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_MEDIA_REWIND -> scrubBy(-10_000L, rc)
                    KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_MEDIA_FAST_FORWARD -> scrubBy(10_000L, rc)
                    KeyEvent.KEYCODE_DPAD_UP -> {
                        poke()
                        try { firstTopFr.requestFocus() } catch (_: Exception) { }
                    }
                    KeyEvent.KEYCODE_DPAD_DOWN -> {
                        poke()
                        try { playFr.requestFocus() } catch (_: Exception) { }
                    }
                    KeyEvent.KEYCODE_MENU, KeyEvent.KEYCODE_MEDIA_AUDIO_TRACK -> dialog = "audio"
                    KeyEvent.KEYCODE_CAPTIONS -> dialog = "text"
                }
                true
            },
    ) {
        key(gen) {
            AndroidView(
                factory = { c ->
                    VLCVideoLayout(c).also {
                        mp.attachViews(it, null, true, false)
                    }
                },
                modifier = Modifier.fillMaxSize(),
            )
        }

        if (buffering && !failed) {
            Text(tr("Загрузка…", "Loading…"), color = C.text, fontSize = 20.sp, modifier = Modifier.align(Alignment.Center))
        }

        if (hud.isNotEmpty() && !inPip) {
            Text(
                hud, color = C.text, fontSize = 22.sp, fontWeight = FontWeight.Bold,
                modifier = Modifier
                    .align(Alignment.Center)
                    .clip(RoundedCornerShape(12.dp))
                    .background(Color(0xB3000000))
                    .padding(horizontal = 22.dp, vertical = 12.dp),
            )
        }

        if ((showUi || inUi || scrub != null) && !inPip && dialog == null) {
            Column(
                Modifier
                    .align(Alignment.TopCenter)
                    .fillMaxWidth()
                    .background(Brush.verticalGradient(listOf(Color(0xCC000000), Color(0x00000000))))
                    .windowInsetsPadding(WindowInsets.displayCutout)
                    .padding(horizontal = 24.dp, vertical = 14.dp)
                    .onFocusChanged { topFocus = it.hasFocus },
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                    BackPill(onBack = { leave() })
                    Text(
                        item.title + if (item.series) "  ·  " + file.label else "",
                        color = C.text, fontSize = 20.sp, fontWeight = FontWeight.SemiBold, maxLines = 1,
                        modifier = Modifier.weight(1f),
                    )
                    if (pipOk) Pill("PiP", onClick = { act?.enterPip() })
                    Pill(tr("Настройки", "Settings") + if (rate != 1f) "  " + rate.toString() + "×" else "", onClick = { dialog = "menu" }, focusRequester = firstTopFr)
                }
            }
            Column(
                Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .background(Brush.verticalGradient(listOf(Color(0x00000000), Color(0xCC000000))))
                    .windowInsetsPadding(WindowInsets.displayCutout)
                    .padding(horizontal = 24.dp, vertical = 14.dp)
                    .onFocusChanged { bottomFocus = it.hasFocus },
            ) {
                val shown = scrub ?: pos
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(fmtTime(shown), color = if (scrub != null) C.good else C.text, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                    if (scrub != null) Text("   (" + (if (shown >= pos) "+" else "−") + fmtTime(kotlin.math.abs(shown - pos)) + ")", color = C.muted, fontSize = 14.sp)
                    Spacer(Modifier.weight(1f))
                    Text(fmtTime(dur), color = C.muted, fontSize = 16.sp)
                }
                Spacer(Modifier.height(6.dp))
                Box(
                    Modifier
                        .fillMaxWidth()
                        .height(30.dp)
                        .onSizeChanged { barW = it.width.coerceAtLeast(1) }
                        .pointerInput(dur) {
                            detectTapGestures(onTap = { o ->
                                if (dur > 0) {
                                    seekTo((dur * (o.x / barW.toFloat())).toLong())
                                    poke()
                                }
                            })
                        }
                        .pointerInput(dur) {
                            detectHorizontalDragGestures(
                                onDragStart = { o -> dragging = true; if (dur > 0) scrub = (dur * (o.x / barW.toFloat())).toLong().coerceIn(0L, dur) },
                                onDragEnd = { dragging = false; applyScrub() },
                                onDragCancel = { dragging = false; scrub = null },
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
                        drawRoundRect(Color(0x33FFFFFF), androidx.compose.ui.geometry.Offset(0f, y), androidx.compose.ui.geometry.Size(size.width, th), androidx.compose.ui.geometry.CornerRadius(r, r))
                        drawRoundRect(col, androidx.compose.ui.geometry.Offset(0f, y), androidx.compose.ui.geometry.Size(x, th), androidx.compose.ui.geometry.CornerRadius(r, r))
                        drawCircle(col, 8.dp.toPx(), androidx.compose.ui.geometry.Offset(x.coerceIn(8.dp.toPx(), size.width - 8.dp.toPx()), size.height / 2f))
                    }
                }
                Spacer(Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.align(Alignment.CenterHorizontally)) {
                    Pill("−10", onClick = { seekRel(-10_000) }, hPad = 16.dp)
                    Pill("", selected = true, onClick = { togglePlay() }, hPad = 26.dp, focusRequester = playFr, leading = { c -> if (playing) PauseGlyph(c, 18.dp) else PlayGlyph(c, 18.dp) })
                    Pill("+10", onClick = { seekRel(10_000) }, hPad = 16.dp)
                }
            }
        }

        val dlg = dialog
        if (dlg != null && !inPip) {
            val close = { dialog = null; focusRoot() }
            when (dlg) {
                "audio" -> DialogBox(tr("Аудиодорожка", "Audio track"), close) {
                    OptionList(
                        audioList.map { t ->
                            Opt(t.second.ifEmpty { tr("Дорожка ", "Track ") + t.first }, t.first == audioSel) {
                                mp.setAudioTrack(t.first)
                                audioSel = t.first
                                Prefs.setStr(ctx, "ta_" + item.id, t.second)
                            }
                        },
                        onPicked = close,
                    )
                    Spacer(Modifier.height(10.dp))
                    Pill(
                        tr("Вывод звука: ", "Audio output: ") + if (aoutStereo) tr("стерео (совместимый)", "stereo (compatible)") else tr("авто", "auto"),
                        onClick = {
                            aoutStereo = !aoutStereo
                            Prefs.setStr(ctx, "aout", if (aoutStereo) "stereo" else "auto")
                            dialog = null
                            failed = false
                            started = false
                            startPos = pos
                            subsAdded = false
                            audioApplied = false
                            textApplied = false
                            gen++
                        },
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                "menu" -> DialogBox(tr("Настройки", "Settings"), close) {
                    val fr = remember { FocusRequester() }
                    LaunchedEffect(Unit) {
                        try { fr.requestFocus() } catch (_: Exception) { }
                    }
                    Pill(tr("Аудио", "Audio"), onClick = { dialog = "audio" }, modifier = Modifier.fillMaxWidth(), focusRequester = fr)
                    Pill(tr("Субтитры", "Subtitles"), onClick = { dialog = "text" }, modifier = Modifier.fillMaxWidth())
                    Pill(tr("Настройки субтитров", "Subtitle settings"), onClick = { dialog = "style" }, modifier = Modifier.fillMaxWidth())
                    Pill(tr("Экран", "Screen"), onClick = { dialog = "scale" }, modifier = Modifier.fillMaxWidth())
                    Pill(if (rate == 1f) tr("Скорость", "Speed") else tr("Скорость ", "Speed ") + rate.toString() + "×", onClick = { dialog = "speed" }, modifier = Modifier.fillMaxWidth())
                    Pill(tr("Синхронизация звука", "Audio sync"), onClick = { dialog = "sync" }, modifier = Modifier.fillMaxWidth())
                }
                "text" -> DialogBox(tr("Субтитры", "Subtitles"), close) {
                    OptionList(
                        textList.map { t ->
                            val off = t.first < 0
                            Opt(if (off) tr("Выключены", "Off") else t.second.ifEmpty { tr("Дорожка ", "Track ") + t.first }, t.first == textSel) {
                                mp.setSpuTrack(t.first)
                                textSel = t.first
                                Prefs.setStr(ctx, "ts_" + item.id, if (off) "-" else t.second)
                            }
                        },
                        onPicked = close,
                    )
                }
                "scale" -> DialogBox(tr("Режим экрана", "Screen mode"), close) {
                    OptionList(
                        SCALES.indices.map { i ->
                            Opt(scaleLabel(i), i == scaleIdx) {
                                scaleIdx = i
                                Prefs.setStr(ctx, "scale", i.toString())
                            }
                        },
                        onPicked = close,
                    )
                }
                "speed" -> DialogBox(tr("Скорость", "Speed"), close) {
                    OptionList(
                        SPEEDS.map { r -> Opt(r.toString() + "×", r == rate) { rate = r } },
                        onPicked = close,
                    )
                }
                "sync" -> DialogBox(tr("Синхронизация звука", "Audio sync"), close) {
                    val fr = remember { FocusRequester() }
                    LaunchedEffect(Unit) {
                        try { fr.requestFocus() } catch (_: Exception) { }
                    }
                    Text(
                        (if (delayMs > 0) "+" else "") + delayMs + " " + tr("мс", "ms") + "   (" + tr("минус: звук раньше, плюс: звук позже", "minus: audio earlier, plus: audio later") + ")",
                        color = C.text, fontSize = 16.sp,
                    )
                    Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 14.dp, vertical = 10.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        fun setDelay(v: Int) {
                            delayMs = v.coerceIn(-5000, 5000)
                            Prefs.setStr(ctx, "adelay", delayMs.toString())
                        }
                        Pill("−100", onClick = { setDelay(delayMs - 100) })
                        Pill("−50", onClick = { setDelay(delayMs - 50) }, focusRequester = fr)
                        Pill("+50", onClick = { setDelay(delayMs + 50) })
                        Pill("+100", onClick = { setDelay(delayMs + 100) })
                        Pill(tr("Сброс", "Reset"), onClick = { setDelay(0) })
                    }
                }
                "style" -> DialogBox(tr("Настройки субтитров", "Subtitle settings"), close) {
                    val fr = remember { FocusRequester() }
                    var changed by remember { mutableStateOf(false) }
                    LaunchedEffect(Unit) {
                        try { fr.requestFocus() } catch (_: Exception) { }
                    }
                    SettingRow(tr("Размер", "Size"), subSizeLabel(subSize), {
                        subSize = nextOf(subSize, SUB_SIZES); Prefs.setStr(ctx, "sub_size", subSize); changed = true
                    }, fr)
                    SettingRow(tr("Высота", "Height"), subPosLabel(subPos), {
                        subPos = nextOf(subPos, SUB_POS); Prefs.setStr(ctx, "sub_pos", subPos); changed = true
                    })
                    SettingRow(tr("Подложка", "Background"), subBgLabel(subBg), {
                        subBg = nextOf(subBg, SUB_BG); Prefs.setStr(ctx, "sub_bg", subBg); changed = true
                    })
                    Pill(
                        tr("Применить", "Apply"),
                        selected = true,
                        onClick = {
                            dialog = null
                            if (changed) {
                                startPos = pos
                                started = false
                                subsAdded = false
                                audioApplied = false
                                textApplied = false
                                gen++
                            }
                            focusRoot()
                        },
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        }

        if (failed) {
            Box(Modifier.fillMaxSize().background(Color(0xE6000000)), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Text(tr("Не удалось воспроизвести файл", "Can't play this file"), color = C.bad, fontSize = 20.sp)
                    BackPill(onBack = { onExit() })
                }
            }
        }
    }
}
