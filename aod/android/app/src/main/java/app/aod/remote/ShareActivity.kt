package app.aod.remote

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.widget.Toast
import org.json.JSONObject
import kotlin.concurrent.thread

/** Android's Share menu -> "AOD": send a link, text or files to the PC. */
class ShareActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val p = Net.prefs(this)
        if ((p.getString("token", "") ?: "").isBlank() || p.getString("host", null) == null) {
            toast("Open AOD and connect to your PC first"); finish(); return
        }
        when (intent.action) {
            Intent.ACTION_SEND -> {
                @Suppress("DEPRECATION") val uri = intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM)
                val text = intent.getStringExtra(Intent.EXTRA_TEXT)
                if (uri != null) sendFiles(listOf(uri)) else if (text != null) askText(text) else finish()
            }
            Intent.ACTION_SEND_MULTIPLE -> {
                @Suppress("DEPRECATION") val uris = intent.getParcelableArrayListExtra<Uri>(Intent.EXTRA_STREAM)
                if (uris.isNullOrEmpty()) finish() else sendFiles(uris)
            }
            else -> finish()
        }
    }

    private fun toast(m: String) = runOnUiThread { Toast.makeText(this, m, Toast.LENGTH_LONG).show() }

    private fun askText(text: String) {
        val isUrl = text.trim().lowercase().startsWith("http")
        val b = AlertDialog.Builder(this).setTitle("Send to PC").setMessage(text.take(300))
            .setOnCancelListener { finish() }
            .setPositiveButton(if (isUrl) "Open on PC" else "Copy to PC") { _, _ -> post(if (isUrl) "open" else "clip", text.trim()) }
            .setNegativeButton("Cancel") { _, _ -> finish() }
        if (isUrl) b.setNeutralButton("Copy to PC") { _, _ -> post("clip", text.trim()) }
        b.show()
    }

    private fun post(kind: String, text: String) = thread {
        try {
            val host = Net.pickHost(this) ?: throw java.io.IOException("PC unreachable")
            val c = Net.open(this, host, "/api/share", "POST")
            c.doOutput = true
            c.setRequestProperty("Content-Type", "application/json")
            c.outputStream.use { it.write(JSONObject().put("kind", kind).put("text", text).toString().toByteArray()) }
            toast(if (c.responseCode == 200) (if (kind == "open") "Opened on your PC" else "Copied to your PC") else "PC refused (${c.responseCode})")
        } catch (e: Exception) { toast("Couldn't reach your PC") }
        runOnUiThread { finish() }
    }

    private fun nameOf(uri: Uri): String {
        contentResolver.query(uri, null, null, null, null)?.use {
            if (it.moveToFirst()) { val i = it.getColumnIndex(OpenableColumns.DISPLAY_NAME); if (i >= 0) return it.getString(i) }
        }
        return uri.lastPathSegment ?: "file"
    }

    private fun sendFiles(uris: List<Uri>) {
        toast("Sending ${uris.size} file(s) to your PC…")
        thread {
            var ok = 0
            try {
                val host = Net.pickHost(this) ?: throw java.io.IOException("PC unreachable")
                for (uri in uris) {
                    val boundary = "----aod" + System.nanoTime()
                    val c = Net.open(this, host, "/api/upload", "POST")
                    c.doOutput = true
                    c.setChunkedStreamingMode(65536)
                    c.readTimeout = 600000
                    c.setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
                    c.outputStream.use { out ->
                        out.write(("--$boundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"${nameOf(uri).replace("\"", "_")}\"\r\n" +
                            "Content-Type: application/octet-stream\r\n\r\n").toByteArray())
                        contentResolver.openInputStream(uri)!!.use { it.copyTo(out) }
                        out.write("\r\n--$boundary--\r\n".toByteArray())
                    }
                    if (c.responseCode == 200) ok++
                }
                toast(if (ok == uris.size) "Sent to your PC (Downloads\\AOD)" else "Sent $ok of ${uris.size}")
            } catch (e: Exception) { toast("Couldn't send: ${e.message}") }
            runOnUiThread { finish() }
        }
    }
}
