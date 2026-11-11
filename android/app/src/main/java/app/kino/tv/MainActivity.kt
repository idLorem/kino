package app.kino.tv

import android.app.PictureInPictureParams
import android.content.res.Configuration
import android.os.Build
import android.os.Bundle
import android.util.Rational
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import kotlinx.coroutines.launch
import org.json.JSONObject

class MainActivity : ComponentActivity() {
    val inPip = mutableStateOf(false)
    var pipReady = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        if (Build.VERSION.SDK_INT >= 28) {
            window.attributes.layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
        }
        hideBars()
        setContent { KinoApp() }
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) hideBars()
    }

    override fun onUserLeaveHint() {
        super.onUserLeaveHint()
        if (pipReady && !Prefs.isTv(this)) enterPip()
    }

    override fun onPictureInPictureModeChanged(isInPictureInPictureMode: Boolean, newConfig: Configuration) {
        super.onPictureInPictureModeChanged(isInPictureInPictureMode, newConfig)
        inPip.value = isInPictureInPictureMode
    }

    fun enterPip() {
        if (Build.VERSION.SDK_INT >= 26 && packageManager.hasSystemFeature(android.content.pm.PackageManager.FEATURE_PICTURE_IN_PICTURE)) {
            try {
                enterPictureInPictureMode(PictureInPictureParams.Builder().setAspectRatio(Rational(16, 9)).build())
            } catch (_: Exception) {
            }
        }
    }

    private fun hideBars() {
        val c = WindowInsetsControllerCompat(window, window.decorView)
        c.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        c.hide(WindowInsetsCompat.Type.systemBars())
    }
}

@Composable
fun KinoApp() {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var conn by remember { mutableStateOf(Prefs.load(ctx)) }
    var library by remember { mutableStateOf<List<Item>>(emptyList()) }
    var ghosts by remember { mutableStateOf<List<Item>>(emptyList()) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var tab by remember { mutableStateOf(Tab.Unwatched) }
    var selectedId by remember { mutableStateOf<String?>(null) }
    var playing by remember { mutableStateOf<Pair<Item, PlayFile>?>(null) }
    var settings by remember { mutableStateOf(false) }
    var update by remember { mutableStateOf<Rel?>(null) }
    var updStatus by remember { mutableStateOf("") }
    var updProgress by remember { mutableStateOf(-1) }
    var updFile by remember { mutableStateOf<java.io.File?>(null) }
    var lastFocus by remember { mutableStateOf<String?>(null) }
    val gridUn = rememberLazyGridState()
    val gridWa = rememberLazyGridState()
    val gridHi = rememberLazyGridState()

    fun checkUpdate(manual: Boolean) {
        scope.launch {
            if (manual) updStatus = tr("Проверяю…", "Checking…")
            val r = try { Updater.check(ctx) } catch (_: Exception) { null }
            if (r?.version != update?.version) updFile = null
            update = r
            if (manual) updStatus = if (r == null) tr("Установлена последняя версия", "You're up to date") else ""
        }
    }

    fun startUpdate() {
        val r = update ?: return
        val ready = updFile
        if (ready != null && ready.isFile) {
            Updater.install(ctx, ready)
            return
        }
        scope.launch {
            updProgress = 0
            try {
                updFile = Updater.download(ctx, r.version, r.url) { updProgress = it }
                updProgress = -1
            } catch (_: Exception) {
                updProgress = -1
                error = tr("Не удалось скачать обновление", "Couldn't download the update")
            }
        }
    }

    LaunchedEffect(Unit) {
        if (Prefs.str(ctx, "upd", "1") == "1") checkUpdate(false)
    }

    fun load(refresh: Boolean) {
        val c = conn ?: return
        scope.launch {
            loading = true
            error = ""
            try {
                val lib = if (refresh) Net.post(c, "/api/refresh", JSONObject()) else Net.get(c, "/api/library")
                val saved = Prefs.str(ctx, "lang", "")
                L.ru = if (saved.isNotEmpty()) saved == "ru" else lib.optString("lang", "ru") != "en"
                library = parseItems(lib.optJSONArray("items"), false)
                ghosts = parseItems(lib.optJSONArray("ghosts"), false)
            } catch (e: HttpFail) {
                if (e.code == 401) {
                    Prefs.clear(ctx)
                    conn = null
                } else error = tr("Ошибка сервера", "Server error")
            } catch (_: Exception) {
                error = tr("Нет связи с компьютером", "Can't reach the PC")
            }
            loading = false
        }
    }

    LaunchedEffect(conn) { if (conn != null) load(false) }

    val c = conn
    if (c == null) {
        ConnectScreen { conn = it }
        return
    }

    val pl = playing
    if (pl != null) {
        val files = pl.first.files
        val idx = files.indexOfFirst { it.fid == pl.second.fid }
        val nxt = if (pl.first.series && idx >= 0 && idx + 1 < files.size) files[idx + 1] else null
        key(pl.first.id, pl.second.fid) {
            PlayerScreen(
                conn = c,
                item = pl.first,
                file = pl.second,
                nextFile = nxt,
                onNext = { f -> playing = pl.first to f },
                onExit = {
                    playing = null
                    scope.launch {
                        kotlinx.coroutines.delay(700)
                        load(false)
                    }
                },
            )
        }
        return
    }

    if (settings) {
        SettingsScreen(
            c,
            onBack = { settings = false },
            onLang = {
                L.ru = !L.ru
                Prefs.setStr(ctx, "lang", if (L.ru) "ru" else "en")
                load(false)
            },
            onDisconnect = { Prefs.clear(ctx); settings = false; conn = null },
            update = update,
            updStatus = updStatus,
            updProgress = updProgress,
            updReady = updFile != null,
            onCheckUpdate = { checkUpdate(true) },
            onUpdate = { startUpdate() },
        )
        return
    }

    val sel = (library + ghosts).firstOrNull { it.id == selectedId }
    if (sel != null) {
        DetailScreen(c, sel, onBack = { selectedId = null }, onPlay = { it, f -> playing = it to f }, onChanged = { load(false) })
        return
    }

    HomeScreen(
        conn = c,
        library = library,
        ghosts = ghosts,
        loading = loading,
        error = error,
        tab = tab,
        onTab = { tab = it },
        onOpen = { lastFocus = it.id; selectedId = it.id },
        onRefresh = { load(true) },
        onSettings = { settings = true },
        update = update,
        updProgress = updProgress,
        updReady = updFile != null,
        onUpdate = { startUpdate() },
        gridState = when (tab) { Tab.Unwatched -> gridUn; Tab.Watched -> gridWa; Tab.Hidden -> gridHi },
        restoreId = lastFocus,
    )
}
