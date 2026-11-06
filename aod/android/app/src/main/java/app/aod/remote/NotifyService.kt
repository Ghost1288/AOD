package app.aod.remote

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import org.json.JSONObject
import kotlin.concurrent.thread

/** Keeps a long-poll open to the PC and turns its events ("Download finished", ...) into Android notifications. */
class NotifyService : Service() {
    @Volatile private var running = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("fg", "Connection", NotificationManager.IMPORTANCE_MIN))
        nm.createNotificationChannel(NotificationChannel("pc", "PC notifications", NotificationManager.IMPORTANCE_HIGH))
        val n = Notification.Builder(this, "fg").setContentTitle("AOD")
            .setContentText("Listening for PC notifications").setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentIntent(openApp()).setOngoing(true).build()
        if (Build.VERSION.SDK_INT >= 34) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_REMOTE_MESSAGING)
        else startForeground(1, n)
        if (!running) { running = true; thread { loop() } }
        return START_STICKY
    }

    override fun onDestroy() { running = false; super.onDestroy() }

    private fun openApp() = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)

    private fun loop() {
        val p = Net.prefs(this)
        var backoff = 3000L
        while (running) {
            if (!p.getBoolean("notify", false) || (p.getString("token", "") ?: "").isBlank()) { stopSelf(); return }
            try {
                val host = Net.pickHost(this) ?: throw java.io.IOException("PC unreachable")
                val last = p.getLong("ev_last", -1)
                val c = Net.open(this, host, "/api/events?after=$last&wait=25")
                c.readTimeout = 40000
                if (c.responseCode == 401) { stopSelf(); return }          // this phone was unpaired
                val j = JSONObject(c.inputStream.bufferedReader().readText())
                val arr = j.getJSONArray("events")
                for (i in 0 until arr.length()) {
                    val e = arr.getJSONObject(i)
                    show(e.getInt("id"), e.getString("title"), e.getString("text"))
                }
                p.edit().putLong("ev_last", j.getLong("last")).apply()     // also resets if the PC restarted
                backoff = 3000
            } catch (_: Exception) {
                try { Thread.sleep(backoff) } catch (_: InterruptedException) { return }
                backoff = minOf(backoff * 2, 30000)
            }
        }
    }

    private fun show(id: Int, title: String, text: String) {
        val n = Notification.Builder(this, "pc").setContentTitle(title).setContentText(text)
            .setStyle(Notification.BigTextStyle().bigText(text)).setSmallIcon(android.R.drawable.stat_notify_chat)
            .setAutoCancel(true).setContentIntent(openApp()).build()
        getSystemService(NotificationManager::class.java).notify(1000 + id, n)
    }
}

/** Restarts the notification listener after the phone reboots. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(c: Context, i: Intent) {
        if (i.action == Intent.ACTION_BOOT_COMPLETED && Net.prefs(c).getBoolean("notify", false)) {
            try { c.startForegroundService(Intent(c, NotifyService::class.java)) } catch (_: Exception) {}
        }
    }
}
