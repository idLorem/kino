package app.kino.tv

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.SocketTimeoutException
import java.net.URL

class HttpFail(val code: Int, message: String) : Exception(message)

data class Conn(val host: String, val port: Int, val token: String) {
    val base: String get() = "http://$host:$port"
    fun streamUrl(id: String, fid: Int): String = "$base/api/stream/$id/$fid?t=$token"
    fun posterUrl(id: String): String = "$base/api/poster/$id?t=$token"
}

data class Found(val host: String, val port: Int, val name: String)

object Net {
    private fun call(method: String, url: String, token: String?, body: String?): String {
        val c = URL(url).openConnection() as HttpURLConnection
        try {
            c.requestMethod = method
            c.connectTimeout = 6000
            c.readTimeout = 45000
            if (token != null) c.setRequestProperty("X-Kino-Token", token)
            if (body != null) {
                c.doOutput = true
                c.setRequestProperty("Content-Type", "application/json")
                c.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            }
            val code = c.responseCode
            val stream = if (code in 200..299) c.inputStream else c.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
            if (code !in 200..299) throw HttpFail(code, text)
            return text
        } finally {
            c.disconnect()
        }
    }

    suspend fun ping(host: String, port: Int): JSONObject = withContext(Dispatchers.IO) {
        JSONObject(call("GET", "http://$host:$port/api/ping", null, null))
    }

    suspend fun pair(host: String, port: Int, pin: String, device: String): String = withContext(Dispatchers.IO) {
        val body = JSONObject().put("pin", pin).put("device", device).toString()
        val r = JSONObject(call("POST", "http://$host:$port/api/pair", null, body))
        r.getString("token")
    }

    suspend fun get(conn: Conn, path: String): JSONObject = withContext(Dispatchers.IO) {
        JSONObject(call("GET", conn.base + path, conn.token, null))
    }

    suspend fun post(conn: Conn, path: String, body: JSONObject): JSONObject = withContext(Dispatchers.IO) {
        JSONObject(call("POST", conn.base + path, conn.token, body.toString()))
    }

    private val bg = kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.SupervisorJob() + Dispatchers.IO)

    fun postAsync(conn: Conn, path: String, body: JSONObject) {
        bg.launch {
            try {
                call("POST", conn.base + path, conn.token, body.toString())
            } catch (_: Exception) {
            }
        }
    }

    suspend fun discover(): List<Found> = withContext(Dispatchers.IO) {
        val found = LinkedHashMap<String, Found>()
        val socket = DatagramSocket()
        try {
            socket.broadcast = true
            socket.soTimeout = 400
            val msg = "KINO?".toByteArray()
            for (round in 0 until 3) {
                try {
                    socket.send(DatagramPacket(msg, msg.size, InetAddress.getByName("255.255.255.255"), 8766))
                } catch (_: Exception) {
                }
                val end = System.currentTimeMillis() + 900
                while (System.currentTimeMillis() < end) {
                    try {
                        val buf = ByteArray(512)
                        val p = DatagramPacket(buf, buf.size)
                        socket.receive(p)
                        val j = JSONObject(String(p.data, 0, p.length))
                        val host = p.address.hostAddress ?: ""
                        if (j.optString("app") == "kino" && host.isNotEmpty()) {
                            found[host] = Found(host, j.optInt("port", 8765), j.optString("name", host))
                        }
                    } catch (_: SocketTimeoutException) {
                    } catch (_: Exception) {
                    }
                }
                if (found.isNotEmpty()) break
            }
        } finally {
            socket.close()
        }
        if (found.isEmpty() && isEmulator()) {
            try {
                val j = ping("10.0.2.2", 8765)
                if (j.optString("app") == "kino") found["10.0.2.2"] = Found("10.0.2.2", 8765, j.optString("name", "PC"))
            } catch (_: Exception) {
            }
        }
        found.values.toList()
    }

    private fun isEmulator(): Boolean {
        val h = android.os.Build.HARDWARE.lowercase()
        return h.contains("ranchu") || h.contains("goldfish") || android.os.Build.FINGERPRINT.contains("generic")
    }
}

object Prefs {
    private const val NAME = "kino"

    fun load(ctx: Context): Conn? {
        val p = ctx.getSharedPreferences(NAME, Context.MODE_PRIVATE)
        val host = p.getString("host", null) ?: return null
        val token = p.getString("token", null) ?: return null
        return Conn(host, p.getInt("port", 8765), token)
    }

    fun save(ctx: Context, c: Conn) {
        ctx.getSharedPreferences(NAME, Context.MODE_PRIVATE).edit()
            .putString("host", c.host).putInt("port", c.port).putString("token", c.token).apply()
    }

    fun clear(ctx: Context) {
        ctx.getSharedPreferences(NAME, Context.MODE_PRIVATE).edit().remove("token").apply()
    }

    fun position(ctx: Context, key: String): Long =
        ctx.getSharedPreferences(NAME, Context.MODE_PRIVATE).getLong("pos_$key", 0L)

    fun setPosition(ctx: Context, key: String, ms: Long) {
        val e = ctx.getSharedPreferences(NAME, Context.MODE_PRIVATE).edit()
        if (ms > 0) e.putLong("pos_$key", ms) else e.remove("pos_$key")
        e.apply()
    }

    fun isTv(ctx: Context): Boolean {
        val m = ctx.getSystemService(Context.UI_MODE_SERVICE) as? android.app.UiModeManager
        return m?.currentModeType == android.content.res.Configuration.UI_MODE_TYPE_TELEVISION
    }

    fun str(ctx: Context, key: String, def: String): String =
        ctx.getSharedPreferences(NAME, Context.MODE_PRIVATE).getString("s_$key", def) ?: def

    fun setStr(ctx: Context, key: String, v: String) {
        ctx.getSharedPreferences(NAME, Context.MODE_PRIVATE).edit().putString("s_$key", v).apply()
    }
}
