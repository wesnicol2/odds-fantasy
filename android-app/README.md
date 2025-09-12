Odds Fantasy Android App (WebView)

Overview
- Bundles `ui/` as assets and displays them in a WebView.
- The UI’s `apiBase` field controls which backend to query (e.g., your Python API at http://<PC-IP>:8000).

Build (Android Studio)
- Open `android-app/` in Android Studio (File → Open → select this folder).
- Let it install/upgrade the Gradle plugin as prompted.
- Connect your Android phone with USB debugging enabled.
- Build & run the `app` configuration, or Build → Build APK(s) for sideloading.

Notes
- The WebView allows cleartext HTTP to talk to your local server; you can change this later.
- On first launch, set `API Base` to your server (e.g., http://192.168.1.50:8000) in the header input.
- Ensure your phone and the server machine are on the same network; consider firewall rules.

