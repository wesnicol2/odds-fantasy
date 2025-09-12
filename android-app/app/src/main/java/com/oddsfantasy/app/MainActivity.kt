package com.oddsfantasy.app

import android.net.Uri
import android.os.Bundle
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import androidx.appcompat.app.AppCompatActivity
import androidx.webkit.WebViewAssetLoader
import androidx.webkit.WebViewClientCompat
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        // 1) Prepare Python cache/data dir with pre-bundled files on first run
        seedInitialCaches()

        // 2) Start embedded Python API on localhost
        startEmbeddedApi()

        // 3) Configure WebView to load bundled UI and talk to http://127.0.0.1:8000
        val webView = findViewById<WebView>(R.id.webview)
        val settings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW

        // Map https://appassets.androidplatform.net/ui/* to assets/ui/*
        val assetLoader = WebViewAssetLoader.Builder()
            .addPathHandler("/ui/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()

        webView.webViewClient = object : WebViewClientCompat() {
            override fun shouldInterceptRequest(
                view: WebView,
                request: WebResourceRequest
            ): WebResourceResponse? {
                return assetLoader.shouldInterceptRequest(request.url)
            }

            @Deprecated("Deprecated in Java")
            override fun shouldInterceptRequest(view: WebView, url: String): WebResourceResponse? {
                return assetLoader.shouldInterceptRequest(Uri.parse(url))
            }
        }

        // Load bundled UI. Default API base in UI is http://127.0.0.1:8000
        webView.loadUrl("https://appassets.androidplatform.net/ui/index.html")
    }

    private fun seedInitialCaches() {
        try {
            val dataDir = File(filesDir, "data")
            if (!dataDir.exists()) dataDir.mkdirs()
            // Copy cache files if they don't exist
            val toCopy = listOf(
                "odds_api_cache.json",
                "odds_api_cache_meta.json",
                "sleeper_players.json" // optional warm cache
            )
            for (name in toCopy) {
                val dst = File(dataDir, name)
                if (!dst.exists()) {
                    assets.open("python-data/$name").use { inp ->
                        dst.outputStream().use { out -> inp.copyTo(out) }
                    }
                }
            }
        } catch (_: Exception) {
            // best effort
        }
    }

    private fun startEmbeddedApi() {
        try {
            if (!Python.isStarted()) {
                Python.start(AndroidPlatform(this))
            }
            val py = Python.getInstance()
            val bootstrap = py.getModule("bootstrap")
            // Pass API key and data dir. Replace the string in resources before building.
            val apiKey = getString(R.string.odds_api_key)
            val dataDir = File(filesDir, "data").absolutePath
            // Start server in a Python thread
            bootstrap.callAttr("start_server", "127.0.0.1", 8000, true, apiKey, dataDir)
        } catch (_: Exception) {
        }
    }
}
