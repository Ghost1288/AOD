package app.aod.remote

import android.app.Activity
import android.app.AlertDialog
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.widget.Toast
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

/**
 * Checks the newest GitHub Release for a newer build of this app, downloads the APK and hands it
 * to Android's installer. Android always asks you to confirm (the first time; later updates can
 * be silent on Android 12+).
 */
object Updater {
    const val REPO = "Ghost1288/AOD"
    private const val BASE = "https://github.com/$REPO/releases/latest/download/"

    private fun open(name: String): HttpURLConnection =
        (URL(BASE + name).openConnection() as HttpURLConnection).apply {
            connectTimeout = 15000; readTimeout = 60000; instanceFollowRedirects = true
            setRequestProperty("User-Agent", "AOD-app")
        }

    fun check(a: Activity) = thread {
        try {
            val info = JSONObject(open("version.json").inputStream.bufferedReader().readText())
            val build = info.optInt("apk_build", info.getInt("build"))
            val current = a.packageManager.getPackageInfo(a.packageName, 0).longVersionCode
            if (build > current) a.runOnUiThread { offer(a, info) }
        } catch (_: Exception) { /* offline or no release yet: stay quiet */ }
    }

    private fun offer(a: Activity, info: JSONObject) {
        if (!a.packageManager.canRequestPackageInstalls()) {
            AlertDialog.Builder(a).setTitle("AOD update ${info.optString("version")}")
                .setMessage("To update itself, AOD needs permission to install apps. Allow it on the next screen, then reopen AOD.")
                .setPositiveButton("Open settings") { _, _ ->
                    a.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${a.packageName}")))
                }.setNegativeButton("Later", null).show()
            return
        }
        Toast.makeText(a, "Updating AOD to ${info.optString("version")}…", Toast.LENGTH_LONG).show()
        install(a, info.optString("apk", "AOD.apk"))
    }

    private fun install(a: Activity, apkName: String) = thread {
        try {
            val file = File(a.cacheDir, "update.apk")
            open(apkName).inputStream.use { i -> file.outputStream().use { i.copyTo(it) } }
            val pi = a.packageManager.packageInstaller
            val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
            if (Build.VERSION.SDK_INT >= 31) params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED)
            val id = pi.createSession(params)
            pi.openSession(id).use { s ->
                s.openWrite("aod", 0, file.length()).use { out -> file.inputStream().copyTo(out); s.fsync(out) }
                val cb = PendingIntent.getBroadcast(a, id, Intent(a, UpdateReceiver::class.java),
                    PendingIntent.FLAG_MUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
                s.commit(cb.intentSender)
            }
        } catch (e: Exception) {
            a.runOnUiThread { Toast.makeText(a, "Update failed: ${e.message}", Toast.LENGTH_LONG).show() }
        }
    }
}

/** Receives the installer's progress; shows Android's confirm screen when it needs one. */
class UpdateReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.getIntExtra(PackageInstaller.EXTRA_STATUS, -1) == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            @Suppress("DEPRECATION")
            val confirm = intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT)
            confirm?.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            if (confirm != null) context.startActivity(confirm)
        }
    }
}
