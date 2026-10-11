# PikaTube

A small PySide6 desktop app for downloading eligible YouTube videos and watching local video files.

## Important
- Only download videos you own, have permission to download, or that YouTube explicitly makes available for download.
- Follow YouTube's Terms of Service and applicable copyright law. This app does not bypass DRM, paywalls, or access controls.
- The app currently requests a progressive MP4 format with audio and video combined, up to 720p (falling back to 480p). Some videos may not offer a matching format.
- A local copy avoids repeated streaming stalls after the download has completed, but the download itself still depends on the internet connection.
- FFmpeg is not bundled in this initial version. The app prefers a progressive MP4 to avoid a separate audio/video merge, but some videos may not be available in that format.
- The GitHub Actions workflow creates an unsigned app bundle. For broad distribution, code signing and notarization are recommended.

## Run from source on Windows
Python 3.10 or newer is recommended.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

## Build the macOS app
1. Push this project to the main branch.
2. Open Actions in this repository and enable workflows if prompted.
3. Select Build PikaTube for macOS, then choose Run workflow.
4. After a successful run, open the run page.
5. In Artifacts, download PikaTube-macOS-arm64.
6. Unzip it on the Mac and move PikaTube.app to Applications.

The workflow uses the macos-14-arm64 runner label. If GitHub reports that this runner is unavailable, select a supported macOS runner and adjust the artifact architecture/name accordingly.

## Storage
Downloaded videos are saved to the Movies/PikaTube folder inside the user's home directory.

Double-click a saved video in the library to play it. Use File → Open Video Folder to find saved files.

## Troubleshooting
- If a video cannot be downloaded, it may not offer a combined MP4 format at the selected resolution, or the URL/video may be unavailable to yt-dlp.
- If YouTube changes cause extraction failures, update yt-dlp in requirements.txt and rerun the workflow.
- This initial app is unsigned. A signed and notarized release is recommended for a polished distribution.
