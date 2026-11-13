package app.kino.tv

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

data class Rel(val version: String, val url: String)

object Updater {
    private const val API = "https://api.github.com/repos/idLorem/kino/releases/latest"

    fun current(ctx: Context): String =
        try { ctx.packageManager.getPackageInfo(ctx.packageName, 0).versionName ?: "0" } catch (_: Exception) { "0" }

    private fun parts(v: String): List<Int> =
        v.trimStart('v').split('.', '-').mapNotNull { it.toIntOrNull() }

    fun isNewer(remote: String, local: String): Boolean {
        val a = parts(remote)
        val b = parts(local)
        for (i in 0 until maxOf(a.size, b.size)) {
            val x = a.getOrElse(i) { 0 }
            val y = b.getOrElse(i) { 0 }
            if (x != y) return x > y
        }
        return false
    }

    suspend fun check(ctx: Context): Rel? = withContext(Dispatchers.IO) {
        val c = URL(API).openConnection() as HttpURLConnection
        try {
            c.connectTimeout = 8000
            c.readTimeout = 12000
            c.setRequestProperty("Accept", "application/vnd.github+json")
            c.setRequestProperty("User-Agent", "kino-android")
            if (c.responseCode != 200) return@withContext null
            val j = JSONObject(c.inputStream.bufferedReader().use { it.readText() })
            val tag = j.optString("tag_name")
            val assets = j.optJSONArray("assets") ?: return@withContext null
            var url = ""
            for (i in 0 until assets.length()) {
                val a = assets.getJSONObject(i)
                if (a.optString("name") == "kino.apk") url = a.optString("browser_download_url")
            }
            if (tag.isEmpty() || url.isEmpty()) return@withContext null
            if (isNewer(tag, current(ctx))) Rel(tag.trimStart('v'), url) else null
        } finally {
            c.disconnect()
        }
    }

    suspend fun download(ctx: Context, version: String, url: String, onProgress: (Int) -> Unit): File = withContext(Dispatchers.IO) {
        val dir = File(ctx.cacheDir, "updates")
        dir.mkdirs()
        val name = "kino-" + version + ".apk"
        val out = File(dir, name)
        dir.listFiles()?.forEach { if (it.name != name) it.delete() }
        if (out.isFile && out.length() > 1_000_000) {
            onProgress(100)
            return@withContext out
        }
        val part = File(dir, name + ".part")
        val c = URL(url).openConnection() as HttpURLConnection
        try {
            c.connectTimeout = 10000
            c.readTimeout = 30000
            c.setRequestProperty("User-Agent", "kino-android")
            val total = c.contentLengthLong
            var done = 0L
            var last = -1
            c.inputStream.use { input ->
                part.outputStream().use { o ->
                    val buf = ByteArray(64 * 1024)
                    while (true) {
                        val n = input.read(buf)
                        if (n < 0) break
                        o.write(buf, 0, n)
                        done += n
                        if (total > 0) {
                            val p = (done * 100 / total).toInt()
                            if (p != last) {
                                last = p
                                onProgress(p)
                            }
                        }
                    }
                }
            }
        } finally {
            c.disconnect()
        }
        part.renameTo(out)
        out
    }

    fun install(ctx: Context, f: File): Boolean = try {
        if (Build.VERSION.SDK_INT >= 26 && !ctx.packageManager.canRequestPackageInstalls()) {
            ctx.startActivity(
                Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + ctx.packageName))
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
        } else {
            val uri = FileProvider.getUriForFile(ctx, ctx.packageName + ".files", f)
            ctx.startActivity(
                Intent(Intent.ACTION_VIEW)
                    .setDataAndType(uri, "application/vnd.android.package-archive")
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK),
            )
        }
        true
    } catch (_: Exception) {
        false
    }
}
