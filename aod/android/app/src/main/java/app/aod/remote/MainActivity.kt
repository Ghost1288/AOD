package app.aod.remote

import android.app.AlertDialog
import android.app.Activity
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.content.pm.ActivityInfo
import android.net.Uri
import android.net.http.SslError
import android.os.Build
import android.os.Bundle
import android.provider.MediaStore
import android.view.View
import android.view.WindowManager
import android.webkit.*
import android.widget.EditText
import android.widget.Toast
import com.google.zxing.integration.android.IntentIntegrator
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.Socket
import java.net.URL
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.cert.X509Certificate
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager
import kotlin.concurrent.thread

/**
 * AOD Android app: a hardened WebView around the host's web client.
 * - pairs from a QR code (aod://pair?host=&port=&fp=&pin=)
 * - trusts ONLY the host certificate whose SHA-256 fingerprint came from the QR (cert pinning)
 * - adds Wake-on-LAN, file download and keep-screen-on
 */
class MainActivity : Activity() {
    private lateinit var web: WebView
    private val prefs by lazy { getSharedPreferences("aod", Context.MODE_PRIVATE) }
    private var fileCallback: ValueCallback<Array<Uri>>? = null

    private val host get() = prefs.getString("host", null)
    private val port get() = prefs.getInt("port", 8765)
    private val fp get() = prefs.getString("fp", "")!!.lowercase()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        web = WebView(this)
        setContentView(web)
        setupWebView()
        if (!handleIntent(intent)) start()
        Updater.check(this)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        if (!handleIntent(intent)) start()
    }

    // ---------------------------------------------------------------- pairing
    private fun handleIntent(i: Intent?): Boolean {
        val data = i?.data ?: return false
        return if (savePairing(data.toString())) { start(); true } else false
    }

    private fun savePairing(text: String): Boolean {
        val u = Uri.parse(text.trim())
        if (u.scheme != "aod" || u.host != "pair") return false
        val h = u.getQueryParameter("host") ?: return false
        prefs.edit()
            .putString("host", h).putInt("port", u.getQueryParameter("port")?.toIntOrNull() ?: 8765)
            .putString("fp", u.getQueryParameter("fp") ?: "").putString("pin", u.getQueryParameter("pin") ?: "")
            .putString("ts", u.getQueryParameter("ts") ?: "")
            .apply()
        return true
    }

    private fun start() {
        val h = host
        if (h == null) { askForPc(); return }
        val pin = prefs.getString("pin", "") ?: ""
        prefs.edit().remove("pin").apply() // PIN is one-time
        // Home address first; if the PC isn't reachable there (you're away), use its Tailscale address.
        val ts = prefs.getString("ts", null)?.takeIf { it.isNotBlank() }
        thread {
            val chosen = listOfNotNull(h, ts).firstOrNull { reachable(it, port) } ?: h
            runOnUiThread { web.loadUrl("https://$chosen:$port/" + if (pin.isNotEmpty()) "?pin=$pin" else "") }
        }
    }

    private fun askForPc() {
        AlertDialog.Builder(this).setTitle("Connect to your PC")
            .setMessage("Open the AOD dashboard on your PC, then scan the \"AOD Android app\" QR code.")
            .setCancelable(false)
            .setPositiveButton("Scan QR") { _, _ ->
                IntentIntegrator(this).setPrompt("Scan the AOD QR code").setBeepEnabled(false)
                    .setOrientationLocked(false).initiateScan()
            }
            .setNeutralButton("Enter address") { _, _ -> manualEntry() }
            .setNegativeButton("Close") { _, _ -> finish() }.show()
    }

    private fun manualEntry() {
        val box = EditText(this).apply { hint = "192.168.1.20:8765 (certificate fingerprint not pinned)" }
        AlertDialog.Builder(this).setTitle("PC address").setView(box)
            .setPositiveButton("OK") { _, _ ->
                val parts = box.text.toString().trim().split(":")
                prefs.edit().putString("host", parts[0]).putInt("port", parts.getOrNull(1)?.toIntOrNull() ?: 8765)
                    .putString("fp", "").apply()
                start()
            }.setNegativeButton("Cancel") { _, _ -> askForPc() }.show()
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        val scan = IntentIntegrator.parseActivityResult(requestCode, resultCode, data)
        if (scan != null) {
            if (scan.contents != null && savePairing(scan.contents)) start()
            else { Toast.makeText(this, "That is not an AOD QR code", Toast.LENGTH_LONG).show(); askForPc() }
            return
        }
        if (requestCode == 77) {
            fileCallback?.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data))
            fileCallback = null
            return
        }
        @Suppress("DEPRECATION") super.onActivityResult(requestCode, resultCode, data)
    }

    // ---------------------------------------------------------------- web view
    private fun setupWebView() {
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false
            allowFileAccess = false
            setSupportZoom(false)
        }
        web.setBackgroundColor(0xFF0B0D12.toInt())
        web.addJavascriptInterface(Bridge(), "AODNative")
        web.setDownloadListener { url, _, disposition, _, _ ->
            val name = URLUtil.guessFileName(url, disposition, null)
            downloadPinned(url, name)
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(v: WebView, cb: ValueCallback<Array<Uri>>, p: FileChooserParams): Boolean {
                fileCallback?.onReceiveValue(null)
                fileCallback = cb
                return try { startActivityForResult(p.createIntent(), 77); true }
                catch (e: Exception) { fileCallback = null; false }
            }
        }
        web.webViewClient = object : WebViewClient() {
            override fun onReceivedSslError(v: WebView, handler: SslErrorHandler, error: SslError) {
                val der = error.certificate.x509Certificate?.encoded
                val seen = der?.let { sha256(it) }
                // Self-signed cert: accept only if it is exactly the one pinned from the QR code.
                if (fp.isNotEmpty() && seen == fp) handler.proceed()
                else if (fp.isEmpty() && (error.url.contains(host ?: "~"))) handler.proceed() // manual address, unpinned
                else { handler.cancel(); showError("Certificate does not match the paired PC.") }
            }

            override fun onReceivedError(v: WebView, r: WebResourceRequest, e: WebResourceError) {
                if (r.isForMainFrame) showError("Can't reach your PC (${e.description}).")
            }

            override fun shouldOverrideUrlLoading(v: WebView, r: WebResourceRequest): Boolean {
                val u = r.url
                if (u.scheme == "aod-app") {
                    when (u.host) {
                        "retry" -> start()
                        "wake" -> { wake(prefs.getString("mac", "") ?: ""); Toast.makeText(this@MainActivity, "Wake signal sent. Give the PC a minute.", Toast.LENGTH_LONG).show() }
                        "rescan" -> { prefs.edit().clear().apply(); askForPc() }
                    }
                    return true
                }
                return false
            }
        }
    }

    private fun showError(msg: String) {
        val mac = prefs.getString("mac", "") ?: ""
        val wake = if (mac.isNotEmpty()) "<a class=b href='aod-app://wake'>Wake PC</a>" else ""
        web.loadDataWithBaseURL(null, """
            <body style='background:#0b0d12;color:#e8ecf4;font:16px sans-serif;text-align:center;padding:48px 24px'>
            <h1 style='letter-spacing:.15em'>AOD</h1><p style='color:#8b93a7'>$msg</p>
            <style>.b{display:block;margin:12px auto;max-width:260px;padding:14px;border-radius:12px;background:#151922;border:1px solid #262c3a;color:#e8ecf4;text-decoration:none}
            .p{background:#4ade80;color:#04210f;font-weight:700}</style>
            <a class='b p' href='aod-app://retry'>Try again</a>$wake
            <a class=b href='aod-app://rescan'>Pair with a different PC</a></body>""", "text/html", "utf-8", null)
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() { if (web.canGoBack()) web.goBack() else moveTaskToBack(true) }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) window.decorView.systemUiVisibility = (View.SYSTEM_UI_FLAG_LAYOUT_STABLE or
            View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY)
    }

    // ---------------------------------------------------------------- JS bridge
    inner class Bridge {
        @JavascriptInterface fun deviceName(): String = "${Build.MANUFACTURER} ${Build.MODEL}"
        @JavascriptInterface fun saveHost(name: String, mac: String) { prefs.edit().putString("pcname", name).putString("mac", mac).apply() }
        @JavascriptInterface fun wake(mac: String) = this@MainActivity.wake(mac)
        @JavascriptInterface fun setLandscape(on: Boolean) {
            runOnUiThread { requestedOrientation = if (on) ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE else ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED }
        }
        @JavascriptInterface fun forget() { prefs.edit().clear().apply(); runOnUiThread { askForPc() } }
    }

    // ---------------------------------------------------------------- helpers
    private fun reachable(h: String, p: Int): Boolean = try {
        Socket().use { it.connect(InetSocketAddress(h, p), 1500); true }
    } catch (_: Exception) { false }

    private fun sha256(b: ByteArray) = MessageDigest.getInstance("SHA-256").digest(b).joinToString("") { "%02x".format(it) }

    /** Wake-on-LAN magic packet (works when the PC's network adapter has WoL enabled). */
    private fun wake(mac: String) = thread {
        try {
            val m = mac.split(":", "-").map { it.toInt(16).toByte() }.toByteArray()
            if (m.size != 6) return@thread
            val pkt = ByteArray(6) { 0xFF.toByte() } + (1..16).flatMap { m.toList() }.toByteArray()
            DatagramSocket().use { s ->
                s.broadcast = true
                val targets = mutableListOf("255.255.255.255")
                host?.substringBeforeLast(".")?.let { targets += "$it.255" }
                for (t in targets) for (p in intArrayOf(9, 7)) s.send(DatagramPacket(pkt, pkt.size, InetAddress.getByName(t), p))
            }
        } catch (_: Exception) {}
    }

    /** Download a file from the host, trusting only the pinned certificate. */
    private fun downloadPinned(url: String, name: String) = thread {
        try {
            val trust = object : X509TrustManager {
                override fun checkClientTrusted(c: Array<X509Certificate>, a: String) {}
                override fun checkServerTrusted(c: Array<X509Certificate>, a: String) {
                    if (fp.isNotEmpty() && sha256(c[0].encoded) != fp) throw java.security.cert.CertificateException("pin mismatch")
                }
                override fun getAcceptedIssuers() = emptyArray<X509Certificate>()
            }
            val ctx = SSLContext.getInstance("TLS").apply { init(null, arrayOf(trust), SecureRandom()) }
            val conn = (URL(url).openConnection() as HttpsURLConnection).apply {
                sslSocketFactory = ctx.socketFactory; setHostnameVerifier { _, _ -> true }
            }
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, name)
                put(MediaStore.Downloads.IS_PENDING, 1)
            }
            val uri = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)!!
            contentResolver.openOutputStream(uri)!!.use { out -> conn.inputStream.use { it.copyTo(out) } }
            values.clear(); values.put(MediaStore.Downloads.IS_PENDING, 0)
            contentResolver.update(uri, values, null, null)
            runOnUiThread { Toast.makeText(this, "Saved to Downloads: $name", Toast.LENGTH_LONG).show() }
        } catch (e: Exception) {
            runOnUiThread { Toast.makeText(this, "Download failed: ${e.message}", Toast.LENGTH_LONG).show() }
        }
    }
}
