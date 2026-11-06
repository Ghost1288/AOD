package app.aod.remote

import android.content.Context
import android.content.SharedPreferences
import java.net.InetSocketAddress
import java.net.Socket
import java.net.URL
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.cert.X509Certificate
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager

/** Talks to the AOD host from outside the WebView (notifications, share-to-PC), trusting only the pinned certificate. */
object Net {
    fun prefs(c: Context): SharedPreferences = c.getSharedPreferences("aod", Context.MODE_PRIVATE)

    fun sha256(b: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(b).joinToString("") { "%02x".format(it) }

    fun reachable(h: String, p: Int): Boolean = try {
        Socket().use { it.connect(InetSocketAddress(h, p), 1500); true }
    } catch (_: Exception) { false }

    /** Home address first, then the Tailscale address. */
    fun pickHost(c: Context): String? {
        val p = prefs(c)
        val h = p.getString("host", null) ?: return null
        val port = p.getInt("port", 8765)
        val ts = p.getString("ts", null)?.takeIf { it.isNotBlank() }
        return listOfNotNull(h, ts).firstOrNull { reachable(it, port) }
    }

    fun open(c: Context, host: String, path: String, method: String = "GET"): HttpsURLConnection {
        val p = prefs(c)
        val fp = (p.getString("fp", "") ?: "").lowercase()
        val trust = object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<X509Certificate>, a: String) {}
            override fun checkServerTrusted(chain: Array<X509Certificate>, a: String) {
                if (fp.isNotEmpty() && sha256(chain[0].encoded) != fp) throw java.security.cert.CertificateException("pin mismatch")
            }
            override fun getAcceptedIssuers() = emptyArray<X509Certificate>()
        }
        val ctx = SSLContext.getInstance("TLS").apply { init(null, arrayOf(trust), SecureRandom()) }
        val conn = URL("https://$host:${p.getInt("port", 8765)}$path").openConnection() as HttpsURLConnection
        conn.sslSocketFactory = ctx.socketFactory
        conn.hostnameVerifier = HostnameVerifier { _, _ -> true }
        conn.requestMethod = method
        conn.connectTimeout = 5000
        conn.readTimeout = 15000
        conn.setRequestProperty("Authorization", "Bearer " + (p.getString("token", "") ?: ""))
        return conn
    }
}
