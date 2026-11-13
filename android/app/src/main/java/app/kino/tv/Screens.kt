package app.kino.tv

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.layout.displayCutout
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import org.json.JSONObject

@Composable
fun Logo(h: Int = 44) {
    Image(
        painterResource(R.drawable.logo),
        contentDescription = null,
        modifier = Modifier.height(h.dp).aspectRatio(153f / 80f),
    )
}

@Composable
fun Backdrop(content: @Composable () -> Unit) {
    Box(
        Modifier
            .fillMaxSize()
            .background(C.bg)
            .windowInsetsPadding(androidx.compose.foundation.layout.WindowInsets.displayCutout)
            .background(
                Brush.radialGradient(
                    listOf(Color(0x14FFFFFF), Color(0x00FFFFFF)),
                    center = androidx.compose.ui.geometry.Offset(300f, 0f),
                    radius = 1400f,
                ),
            ),
    ) { content() }
}

@Composable
fun KeyBtn(label: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    Pill(label, onClick = onClick, modifier = modifier.width(if (compact()) 56.dp else 84.dp), radius = 16.dp, hPad = 4.dp)
}

@Composable
fun ConnectScreen(onConnected: (Conn) -> Unit) {
    val scope = rememberCoroutineScope()
    var found by remember { mutableStateOf<List<Found>>(emptyList()) }
    var scanning by remember { mutableStateOf(true) }
    var target by remember { mutableStateOf<Found?>(null) }
    var pin by remember { mutableStateOf("") }
    var error by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var manual by remember { mutableStateOf("") }
    var manualMode by remember { mutableStateOf(false) }
    val ctx = LocalContext.current
    val cp = compact()

    fun scan() {
        scope.launch {
            scanning = true
            found = try { Net.discover() } catch (_: Exception) { emptyList() }
            scanning = false
        }
    }

    LaunchedEffect(Unit) { scan() }

    fun pairNow(t: Found, code: String) {
        if (busy) return
        busy = true
        error = ""
        scope.launch {
            try {
                val token = Net.pair(t.host, t.port, code, android.os.Build.MODEL ?: "TV")
                val c = Conn(t.host, t.port, token)
                Prefs.save(ctx, c)
                onConnected(c)
            } catch (e: HttpFail) {
                error = if (e.code == 403) tr("Неверный PIN", "Wrong PIN")
                else if (e.code == 429) tr("Слишком много попыток, подождите", "Too many attempts, wait a bit")
                else tr("Ошибка сервера", "Server error")
                pin = ""
                target = t
            } catch (_: Exception) {
                error = tr("Не удалось подключиться", "Can't connect")
                target = null
            }
            busy = false
        }
    }

    fun submit() {
        val t = target ?: return
        if (pin.length != 6) return
        pairNow(t, pin)
    }

    fun choose(f: Found) {
        scope.launch {
            val needPin = try { Net.ping(f.host, f.port).optBoolean("pin", true) } catch (_: Exception) { true }
            if (needPin) target = f else pairNow(f, "")
        }
    }

    if (target != null) BackHandler { target = null; pin = ""; error = "" }

    Backdrop {
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(androidx.compose.foundation.rememberScrollState())
                .padding(horizontal = if (cp) 20.dp else 64.dp, vertical = if (cp) 24.dp else 40.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Logo(56)
            Spacer(Modifier.height(10.dp))
            Text(
                tr("Каталог на вашем компьютере. Смотрите прямо на телевизоре.", "Your PC catalog, right on the TV."),
                color = C.muted, fontSize = 16.sp, textAlign = TextAlign.Center,
            )
            Spacer(Modifier.height(28.dp))
            val t = target
            if (t == null) {
                Text(
                    if (scanning) tr("Ищу Kino в сети…", "Looking for Kino on the network…")
                    else if (found.isEmpty()) tr("Компьютер не найден. Проверьте, что Kino запущен и режим «ТВ» включён в настройках.", "No PC found. Make sure Kino is running with TV mode enabled in settings.")
                    else tr("Выберите компьютер", "Choose a PC"),
                    color = C.text, fontSize = 20.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center,
                )
                if (error.isNotEmpty()) Text(error, color = C.bad, fontSize = 14.sp)
                Spacer(Modifier.height(18.dp))
                LazyRow(
                    horizontalArrangement = Arrangement.spacedBy(14.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 18.dp, vertical = 12.dp),
                ) {
                    items(found) { f ->
                        Pill(f.name + "  ·  " + f.host, onClick = { choose(f) }, radius = 16.dp)
                    }
                }
                Spacer(Modifier.height(18.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    Pill(tr("Искать снова", "Scan again"), onClick = { scan() })
                    Pill(tr("Ввести адрес", "Enter address"), selected = manualMode, onClick = { manualMode = !manualMode })
                }
                if (manualMode) {
                    Spacer(Modifier.height(18.dp))
                    Text(manual.ifEmpty { "192.168." }, color = if (manual.isEmpty()) C.muted else C.text, fontSize = 28.sp, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(12.dp))
                    val rows = listOf(listOf("1", "2", "3", "4", "5"), listOf("6", "7", "8", "9", "0"), listOf(".", "⌫", "OK"))
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        rows.forEach { r ->
                            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                r.forEach { k ->
                                    KeyBtn(k, onClick = {
                                        when (k) {
                                            "⌫" -> manual = manual.dropLast(1)
                                            "OK" -> if (manual.isNotEmpty()) choose(Found(manual, 8765, manual))
                                            else -> if (manual.length < 21) manual += k
                                        }
                                    })
                                }
                            }
                        }
                    }
                }
            } else {
                BackPill(onBack = { target = null; pin = ""; error = "" })
                Spacer(Modifier.height(14.dp))
                Text(
                    tr("PIN из настроек Kino на компьютере", "PIN from Kino settings on your PC"),
                    color = C.text, fontSize = 20.sp, fontWeight = FontWeight.SemiBold,
                )
                Spacer(Modifier.height(6.dp))
                Text(t.name, color = C.muted, fontSize = 14.sp)
                Spacer(Modifier.height(18.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    for (i in 0 until 6) {
                        Box(
                            Modifier
                                .size(width = if (cp) 40.dp else 46.dp, height = 58.dp)
                                .clip(RoundedCornerShape(12.dp))
                                .background(C.glass)
                                .border(1.dp, if (i == pin.length) C.text else C.stroke, RoundedCornerShape(12.dp)),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(if (i < pin.length) pin[i].toString() else "", color = C.text, fontSize = 26.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                }
                Spacer(Modifier.height(8.dp))
                Text(error, color = C.bad, fontSize = 14.sp, modifier = Modifier.height(22.dp))
                Spacer(Modifier.height(6.dp))
                val rows = listOf(listOf("1", "2", "3", "4", "5"), listOf("6", "7", "8", "9", "0"))
                Column(verticalArrangement = Arrangement.spacedBy(10.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    rows.forEach { r ->
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            r.forEach { k ->
                                KeyBtn(k, onClick = {
                                    if (pin.length < 6) {
                                        pin += k
                                        if (pin.length == 6) submit()
                                    }
                                })
                            }
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        KeyBtn("⌫", onClick = { pin = pin.dropLast(1) })
                        Pill(
                            if (busy) tr("Подключаю…", "Connecting…") else tr("Подключиться", "Connect"),
                            selected = pin.length == 6,
                            onClick = { submit() },
                            radius = 16.dp,
                        )
                    }
                }
            }
        }
    }
}

enum class Tab { Unwatched, Watched, Hidden }

@Composable
fun HomeScreen(
    conn: Conn,
    library: List<Item>,
    ghosts: List<Item>,
    loading: Boolean,
    error: String,
    tab: Tab,
    onTab: (Tab) -> Unit,
    onOpen: (Item) -> Unit,
    onRefresh: () -> Unit,
    onSettings: () -> Unit,
    update: Rel?,
    updProgress: Int,
    updReady: Boolean,
    onUpdate: () -> Unit,
    gridState: androidx.compose.foundation.lazy.grid.LazyGridState,
    restoreId: String?,
) {
    val restoreFr = remember { androidx.compose.ui.focus.FocusRequester() }
    LaunchedEffect(Unit) {
        if (restoreId != null) {
            kotlinx.coroutines.delay(80)
            try { restoreFr.requestFocus() } catch (_: Exception) { }
        }
    }
    var dismissed by remember { mutableStateOf(setOf<String>()) }
    var clearTarget by remember { mutableStateOf<Item?>(null) }
    val cont = remember(library, dismissed) {
        library.filter { it.resumeFid >= 0 && !it.inWatched && !it.hidden && it.id !in dismissed }.sortedByDescending { it.resumeTs }.take(12)
    }
    clearTarget?.let { t ->
        androidx.compose.ui.window.Dialog(onDismissRequest = { clearTarget = null }) {
            Column(
                Modifier.clip(RoundedCornerShape(22.dp)).background(Color(0xF2141416)).padding(24.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Text(t.title, color = C.text, fontSize = 18.sp, fontWeight = FontWeight.Bold, maxLines = 2)
                Text(tr("Убрать из «Продолжить просмотр»?", "Remove from “Continue watching”?"), color = C.muted, fontSize = 14.sp)
                Pill(tr("Убрать", "Remove"), onClick = {
                    Net.postAsync(conn, "/api/progress/clear", org.json.JSONObject().put("id", t.id))
                    dismissed = dismissed + t.id
                    clearTarget = null
                }, modifier = Modifier.fillMaxWidth())
                Pill(tr("Отмена", "Cancel"), onClick = { clearTarget = null }, modifier = Modifier.fillMaxWidth())
            }
        }
    }
    val shown = remember(library, ghosts, tab) {
        val base = when (tab) {
            Tab.Unwatched -> library.filter { !it.inWatched && !it.hidden }
            Tab.Watched -> library.filter { it.inWatched && !it.hidden } + ghosts
            Tab.Hidden -> library.filter { it.hidden }
        }
        base.sortedWith(compareByDescending<Item> { it.pinned > 0 }.thenByDescending { if (it.pinned > 0) it.pinned else it.added })
    }
    val cp = compact()
    Backdrop {
        Column(Modifier.fillMaxSize().padding(start = if (cp) 14.dp else 48.dp, end = if (cp) 14.dp else 48.dp, top = if (cp) 14.dp else 28.dp)) {
            Row(
                Modifier.then(if (cp) Modifier.horizontalScroll(androidx.compose.foundation.rememberScrollState()) else Modifier),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Logo(if (cp) 30 else 40)
                Spacer(Modifier.width(if (cp) 6.dp else 10.dp))
                Pill(tr("Не просмотрено", "Not watched"), tab == Tab.Unwatched, { onTab(Tab.Unwatched) }, hPad = 16.dp)
                Pill(tr("Просмотрено", "Watched"), tab == Tab.Watched, { onTab(Tab.Watched) }, hPad = 16.dp)
                Pill(tr("Скрытое", "Hidden"), tab == Tab.Hidden, { onTab(Tab.Hidden) }, hPad = 16.dp)
                if (!cp) Spacer(Modifier.weight(1f))
                if (update != null) {
                    Pill(
                        if (updProgress >= 0) tr("Загрузка ", "Downloading ") + updProgress + "%" else if (updReady) tr("Установить v", "Install v") + update.version else tr("Скачать v", "Download v") + update.version,
                        onClick = { if (updProgress < 0) onUpdate() },
                        hPad = 16.dp,
                    )
                }
                Pill(tr("Обновить", "Refresh"), onClick = onRefresh, hPad = 16.dp)
                Pill(tr("Настройки", "Settings"), onClick = onSettings, hPad = 16.dp)
            }
            Spacer(Modifier.height(20.dp))
            if (error.isNotEmpty()) {
                Text(error, color = C.bad, fontSize = 16.sp, modifier = Modifier.padding(bottom = 10.dp))
            }
            if (shown.isEmpty()) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(
                        if (loading) tr("Загрузка…", "Loading…") else tr("Здесь пока пусто", "Nothing here yet"),
                        color = C.muted, fontSize = 20.sp,
                    )
                }
            } else {
                LazyVerticalGrid(
                    state = gridState,
                    columns = GridCells.Adaptive(if (cp) 128.dp else 168.dp),
                    horizontalArrangement = Arrangement.spacedBy(if (cp) 12.dp else 20.dp),
                    verticalArrangement = Arrangement.spacedBy(if (cp) 14.dp else 24.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(top = 12.dp, bottom = 48.dp, start = 10.dp, end = 10.dp),
                ) {
                    if (tab == Tab.Unwatched && cont.isNotEmpty()) {
                        item(span = { androidx.compose.foundation.lazy.grid.GridItemSpan(maxLineSpan) }, key = "continue") {
                            Column {
                                Text(tr("Продолжить просмотр", "Continue watching"), color = C.text, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                                LazyRow(
                                    horizontalArrangement = Arrangement.spacedBy(16.dp),
                                    contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 6.dp, vertical = 12.dp),
                                ) {
                                    items(cont, key = { it.id }) { it ->
                                        PosterCard(it, conn, { onOpen(it) }, Modifier.width(if (cp) 110.dp else 150.dp).aspectRatio(2f / 3f), onLongClick = { clearTarget = it })
                                    }
                                }
                            }
                        }
                    }
                    items(shown, key = { it.id }) { it ->
                        PosterCard(
                            it, conn, { onOpen(it) }, Modifier.aspectRatio(2f / 3f),
                            focusRequester = if (it.id == restoreId) restoreFr else null,
                        )
                    }
                }
            }
        }
    }
}

@Composable
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
fun DetailScreen(
    conn: Conn,
    item: Item,
    onBack: () -> Unit,
    onPlay: (Item, PlayFile) -> Unit,
    onChanged: () -> Unit,
) {
    BackHandler { onBack() }
    val scope = rememberCoroutineScope()
    var cur by remember(item) { mutableStateOf(item) }
    val ghost = cur.files.isEmpty() && !cur.isWatchlist
    val fr = remember { androidx.compose.ui.focus.FocusRequester() }
    val cp = compact()
    LaunchedEffect(Unit) {
        try { fr.requestFocus() } catch (_: Exception) { }
    }

    fun act(path: String, body: JSONObject, apply: (Item) -> Item) {
        scope.launch {
            try {
                Net.post(conn, path, body)
                cur = apply(cur)
                onChanged()
            } catch (_: Exception) {
            }
        }
    }

    val actions: @Composable () -> Unit = {
        val bw = if (cp) 150.dp else 240.dp
        Column(Modifier.padding(vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                if (cur.files.isNotEmpty()) {
                    val resume = cur.files.firstOrNull { cur.resumeFid >= 0 && it.fid == cur.resumeFid }
                    val next = resume ?: cur.files.firstOrNull { !it.watched } ?: cur.files[0]
                    Pill(
                        if (resume != null) tr("Продолжить ", "Resume ") + fmtTime(resume.pos) else tr("Смотреть", "Play"),
                        selected = true,
                        onClick = { onPlay(cur, next) },
                        modifier = Modifier.width(bw),
                        focusRequester = fr,
                    )
                }
                if (!cur.isWatchlist && !ghost) {
                    Pill(
                        if (cur.inWatched) tr("Не просмотрено", "Unwatched") else tr("Просмотрено", "Watched"),
                        onClick = { act("/api/watched", JSONObject().put("id", cur.id).put("flag", !cur.inWatched)) { it.copy(inWatched = !it.inWatched) } },
                        modifier = Modifier.width(bw),
                    )
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Pill(
                    if (cur.pinned > 0) tr("Открепить", "Unpin") else tr("Закрепить", "Pin"),
                    onClick = {
                        val now = cur.pinned <= 0
                        act("/api/pin", JSONObject().put("ref", cur.id).put("flag", now)) { it.copy(pinned = if (now) System.currentTimeMillis() / 1000.0 else 0.0) }
                    },
                    modifier = Modifier.width(bw),
                    focusRequester = if (cur.files.isEmpty()) fr else null,
                )
                if (!cur.isWatchlist && !ghost) {
                    Pill(
                        if (cur.hidden) tr("Вернуть", "Unhide") else tr("Скрыть", "Hide"),
                        onClick = { act("/api/hidden", JSONObject().put("id", cur.id).put("flag", !cur.hidden)) { it.copy(hidden = !it.hidden) } },
                        modifier = Modifier.width(bw),
                    )
                }
            }
            if (cur.resumeFid >= 0 && !ghost) {
                Pill(
                    tr("Убрать из «Продолжить»", "Remove from Continue"),
                    onClick = { act("/api/progress/clear", JSONObject().put("id", cur.id)) { it.copy(resumeFid = -1, resumePos = 0, resumeDur = 0, files = it.files.map { f -> f.copy(pos = 0, dur = 0) }) } },
                    modifier = Modifier.width(bw * 2 + 12.dp),
                )
            }
        }
    }

    val head: @Composable () -> Unit = {
        Text(cur.title, color = C.text, fontSize = if (cp) 24.sp else 34.sp, fontWeight = FontWeight.Bold, maxLines = 2)
        Spacer(Modifier.height(8.dp))
        val meta = listOfNotNull(
            if (cur.year > 0) cur.year.toString() else null,
            if (cur.duration > 0) "${cur.duration} " + tr("мин", "min") else null,
            cur.genres.ifEmpty { null },
        ).joinToString("  ·  ")
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            if (cur.ratingText.isNotEmpty()) Chip(cur.ratingText, ratingColor(cur.rating))
            Text(meta, color = C.muted, fontSize = 16.sp)
        }
        Spacer(Modifier.height(14.dp))
        if (cur.description.isNotEmpty()) {
            Text(cur.description, color = Color(0xCCF2F2F2), fontSize = 16.sp, maxLines = if (cp) 8 else 5, lineHeight = 23.sp)
            Spacer(Modifier.height(18.dp))
        }
        actions()
    }

    Backdrop {
        if (cp) {
            Column(
                Modifier
                    .fillMaxSize()
                    .verticalScroll(androidx.compose.foundation.rememberScrollState())
                    .padding(16.dp),
            ) {
                BackPill(onBack = onBack)
                Spacer(Modifier.height(12.dp))
                PosterImage(
                    cur, conn,
                    Modifier.width(150.dp).aspectRatio(2f / 3f).clip(RoundedCornerShape(16.dp)).border(1.dp, Color(0x21FFFFFF), RoundedCornerShape(16.dp)),
                )
                Spacer(Modifier.height(16.dp))
                head()
                if (cur.files.size > 1) {
                    Spacer(Modifier.height(18.dp))
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        cur.files.forEach { f ->
                            Pill((if (f.watched) "✓  " else "") + f.label + (if (f.pos > 0 && f.dur > 0) "  ·  " + (f.pos * 100 / f.dur) + "%" else ""), onClick = { onPlay(cur, f) }, modifier = Modifier.fillMaxWidth())
                        }
                    }
                }
                if (ghost) Text(tr("Файлов на компьютере нет", "No files on the PC"), color = C.muted, fontSize = 16.sp)
                Spacer(Modifier.height(24.dp))
            }
        } else {
            Row(Modifier.fillMaxSize().padding(horizontal = 56.dp, vertical = 36.dp), horizontalArrangement = Arrangement.spacedBy(36.dp)) {
                PosterImage(cur, conn, Modifier.width(280.dp).aspectRatio(2f / 3f).clip(RoundedCornerShape(20.dp)).border(1.dp, Color(0x21FFFFFF), RoundedCornerShape(20.dp)))
                Column(Modifier.weight(1f)) {
                    BackPill(onBack = onBack)
                    Spacer(Modifier.height(12.dp))
                    head()
                    if (cur.files.size > 1) {
                        Spacer(Modifier.height(18.dp))
                        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                            items(cur.files) { f ->
                                Pill(
                                    (if (f.watched) "✓  " else "") + f.label + (if (f.pos > 0 && f.dur > 0) "  ·  " + (f.pos * 100 / f.dur) + "%" else ""),
                                    onClick = { onPlay(cur, f) },
                                    modifier = Modifier.fillMaxWidth(),
                                    radius = 14.dp,
                                )
                            }
                        }
                    }
                    if (ghost) {
                        Text(tr("Файлов на компьютере нет", "No files on the PC"), color = C.muted, fontSize = 16.sp)
                    }
                }
            }
        }
    }
}

@Composable
fun SettingsScreen(
    conn: Conn,
    onBack: () -> Unit,
    onLang: () -> Unit,
    onDisconnect: () -> Unit,
    update: Rel?,
    updStatus: String,
    updProgress: Int,
    updReady: Boolean,
    onCheckUpdate: () -> Unit,
    onUpdate: () -> Unit,
) {
    var page by remember { mutableStateOf("main") }
    val goBack: () -> Unit = { when (page) { "sub" -> page = "play"; "play" -> page = "main"; else -> onBack() } }
    BackHandler { goBack() }
    val ctx = LocalContext.current
    var aud by remember { mutableStateOf(Prefs.str(ctx, "aud", "auto")) }
    var sub by remember { mutableStateOf(Prefs.str(ctx, "sub", "off")) }
    var resume by remember { mutableStateOf(Prefs.str(ctx, "resume", "1")) }
    var vdec by remember { mutableStateOf(Prefs.str(ctx, "vdec", "auto")) }
    var aout by remember { mutableStateOf(Prefs.str(ctx, "aout", "auto")) }
    var autoNext by remember { mutableStateOf(Prefs.str(ctx, "autonext", "1")) }
    var updAuto by remember { mutableStateOf(Prefs.str(ctx, "upd", "1")) }
    var sSize by remember { mutableStateOf(Prefs.str(ctx, "sub_size", "m")) }
    var sPos by remember { mutableStateOf(Prefs.str(ctx, "sub_pos", "1")) }
    var sBg by remember { mutableStateOf(Prefs.str(ctx, "sub_bg", "50")) }
    val fr = remember { androidx.compose.ui.focus.FocusRequester() }
    LaunchedEffect(page) {
        try { fr.requestFocus() } catch (_: Exception) { }
    }

    fun next(cur: String, all: List<String>): String = all[(all.indexOf(cur) + 1) % all.size]

    val cp = compact()
    val title = when (page) {
        "sub" -> tr("Настройки субтитров", "Subtitle settings")
        "play" -> tr("Воспроизведение", "Playback")
        else -> tr("Настройки", "Settings")
    }
    Backdrop {
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(androidx.compose.foundation.rememberScrollState())
                .padding(horizontal = if (cp) 16.dp else 80.dp, vertical = if (cp) 20.dp else 28.dp),
        ) {
            BackPill(onBack = goBack)
            Spacer(Modifier.height(10.dp))
            Text(title, color = C.text, fontSize = 30.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(12.dp))
            Column(Modifier.then(if (cp) Modifier else Modifier.fillMaxWidth(0.62f))) {
                when (page) {
                    "sub" -> {
                        SettingRow(tr("Размер", "Size"), subSizeLabel(sSize), { sSize = nextOf(sSize, SUB_SIZES); Prefs.setStr(ctx, "sub_size", sSize) }, fr)
                        SettingRow(tr("Высота", "Height"), subPosLabel(sPos), { sPos = nextOf(sPos, SUB_POS); Prefs.setStr(ctx, "sub_pos", sPos) })
                        SettingRow(tr("Подложка", "Background"), subBgLabel(sBg), { sBg = nextOf(sBg, SUB_BG); Prefs.setStr(ctx, "sub_bg", sBg) })
                    }
                    "play" -> {
                        SettingRow(
                            tr("Аудиодорожка по умолчанию", "Default audio"),
                            when (aud) { "ru" -> "Русская"; "en" -> "English"; else -> tr("Авто", "Auto") },
                            { aud = next(aud, listOf("auto", "ru", "en")); Prefs.setStr(ctx, "aud", aud) },
                            fr,
                        )
                        SettingRow(
                            tr("Субтитры по умолчанию", "Default subtitles"),
                            when (sub) { "ru" -> "Русские"; "en" -> "English"; else -> tr("Выкл", "Off") },
                            { sub = next(sub, listOf("off", "ru", "en")); Prefs.setStr(ctx, "sub", sub) },
                        )
                        SettingRow(tr("Настройки субтитров", "Subtitle settings"), tr("Открыть", "Open"), { page = "sub" })
                        SettingRow(
                            tr("Декодер видео", "Video decoder"),
                            if (vdec == "soft") tr("Программный", "Software") else tr("Авто (аппаратный)", "Auto (hardware)"),
                            { vdec = if (vdec == "soft") "auto" else "soft"; Prefs.setStr(ctx, "vdec", vdec) },
                        )
                        SettingRow(
                            tr("Вывод звука", "Audio output"),
                            if (aout == "stereo") tr("Стерео (если нет звука)", "Stereo (if no sound)") else tr("Авто", "Auto"),
                            { aout = if (aout == "stereo") "auto" else "stereo"; Prefs.setStr(ctx, "aout", aout) },
                        )
                        SettingRow(
                            tr("Автозапуск следующей серии", "Auto-play next episode"),
                            if (autoNext == "1") tr("Да", "Yes") else tr("Нет", "No"),
                            { autoNext = if (autoNext == "1") "0" else "1"; Prefs.setStr(ctx, "autonext", autoNext) },
                        )
                        SettingRow(
                            tr("Продолжать с места остановки", "Resume playback"),
                            if (resume == "1") tr("Да", "Yes") else tr("Нет", "No"),
                            { resume = if (resume == "1") "0" else "1"; Prefs.setStr(ctx, "resume", resume) },
                        )
                    }
                    else -> {
                        SettingRow(tr("Язык", "Language"), if (L.ru) "Русский" else "English", { onLang() }, fr)
                        SettingRow(tr("Воспроизведение", "Playback"), tr("Открыть", "Open"), { page = "play" })
                        SettingRow(
                            tr("Проверять обновления при запуске", "Check for updates on start"),
                            if (updAuto == "1") tr("Да", "Yes") else tr("Нет", "No"),
                            { updAuto = if (updAuto == "1") "0" else "1"; Prefs.setStr(ctx, "upd", updAuto) },
                        )
                        if (update != null) {
                            SettingRow(
                                tr("Доступна версия ", "New version ") + update.version,
                                if (updProgress >= 0) tr("Загрузка ", "Downloading ") + updProgress + "%" else if (updReady) tr("Установить", "Install") else tr("Скачать", "Download"),
                                { if (updProgress < 0) onUpdate() },
                            )
                        } else {
                            SettingRow(
                                tr("Версия ", "Version ") + Updater.current(ctx),
                                updStatus.ifEmpty { tr("Проверить обновления", "Check for updates") },
                                { onCheckUpdate() },
                            )
                        }
                        SettingRow(
                            tr("Компьютер", "PC"),
                            conn.host + ":" + conn.port + "  ·  " + tr("Отключиться", "Disconnect"),
                            { onDisconnect() },
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun SettingRow(label: String, value: String, onClick: () -> Unit, focusRequester: androidx.compose.ui.focus.FocusRequester? = null) {
    Column(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth().padding(vertical = 5.dp)) {
            Text(label, color = C.text, fontSize = 20.sp, modifier = Modifier.weight(1f))
            Pill(value, onClick = onClick, modifier = Modifier.widthIn(min = 110.dp), focusRequester = focusRequester)
        }
        Box(Modifier.fillMaxWidth().height(1.dp).background(C.stroke))
    }
}
