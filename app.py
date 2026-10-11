import sys
import os
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from PySide6.QtCore import QObject, QThread, Signal, QUrl, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QProgressBar, QMessageBox, QFileDialog, QSplitter, QSlider
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget


APP_NAME = "PikaTube"
VIDEO_DIR = Path.home() / "Movies" / "PikaTube"


def is_supported_youtube_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
        host = (parsed.hostname or "").lower()
        return parsed.scheme in ("https", "http") and (
            host == "youtu.be"
            or host == "youtube.com"
            or host.endswith(".youtube.com")
        )
    except Exception:
        return False


def safe_error_message(exc: Exception) -> str:
    message = str(exc).strip()
    return message[:500] if message else exc.__class__.__name__


class DownloadWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, url: str, output_dir: Path):
        super().__init__()
        self.url = url
        self.output_dir = output_dir

    def run(self):
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)

            def hook(data):
                status = data.get("status")
                if status == "downloading":
                    total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                    downloaded = data.get("downloaded_bytes") or 0
                    percent = int(downloaded * 100 / total) if total else 0
                    speed = data.get("speed")
                    speed_text = f"{speed / 1024 / 1024:.1f} MB/s" if speed else "速度計算中"
                    self.progress.emit(
                        max(0, min(percent, 100)),
                        f"ダウンロード中… {percent}% / {speed_text}"
                    )
                elif status == "finished":
                    self.progress.emit(100, "ダウンロード完了。ファイルを確認中…")

            # Prefer progressive MP4 with audio and video already combined.
            # This usually avoids needing FFmpeg for a merge, but some videos
            # may not offer a matching format.
            options = {
                "format": (
                    "best[height<=720][ext=mp4][acodec!=none][vcodec!=none]/"
                    "best[height<=480][ext=mp4][acodec!=none][vcodec!=none]"
                ),
                "outtmpl": str(self.output_dir / "%(title).180B [%(id)s].%(ext)s"),
                "noplaylist": True,
                "progress_hooks": [hook],
                "quiet": True,
                "no_warnings": True,
                "restrictfilenames": False,
                "windowsfilenames": False,
                "overwrites": False,
                "continuedl": True,
                "ignoreerrors": False,
            }
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(self.url, download=True)
                if not info:
                    raise RuntimeError("動画情報を取得できませんでした。")
                prepared = ydl.prepare_filename(info)
                path = Path(prepared)
                if not path.exists():
                    matches = list(self.output_dir.glob(f"*[{info.get('id', '')}].*"))
                    if matches:
                        path = matches[0]
                    else:
                        raise RuntimeError("ダウンロード後の動画ファイルが見つかりません。")
                self.finished.emit(str(path))
        except Exception as exc:
            self.failed.emit(safe_error_message(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PikaTube")
        self.resize(1100, 720)
        VIDEO_DIR.mkdir(parents=True, exist_ok=True)

        self.thread = None
        self.worker = None

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.video = QVideoWidget()
        self.player.setVideoOutput(self.video)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("YouTubeの動画URLを貼り付け")
        self.download_button = QPushButton("動画を保存")
        self.refresh_button = QPushButton("一覧を更新")
        self.open_button = QPushButton("動画ファイルを開く")
        self.play_button = QPushButton("再生")
        self.pause_button = QPushButton("一時停止")
        self.status = QLabel("動画URLを貼り付けて保存するか、保存済み動画を選択してください。")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        self.library = QListWidget()
        self.library.setMinimumWidth(250)
        self.position = QSlider(Qt.Orientation.Horizontal)
        self.position.setRange(0, 0)
        self.time_label = QLabel("00:00 / 00:00")

        top = QHBoxLayout()
        top.addWidget(self.url_input, 1)
        top.addWidget(self.download_button)

        controls = QHBoxLayout()
        controls.addWidget(self.play_button)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.open_button)
        controls.addWidget(self.refresh_button)
        controls.addStretch(1)

        player_panel = QWidget()
        player_layout = QVBoxLayout(player_panel)
        player_layout.addWidget(self.video, 1)
        player_layout.addWidget(self.position)
        player_layout.addWidget(self.time_label)
        player_layout.addLayout(controls)

        library_panel = QWidget()
        library_layout = QVBoxLayout(library_panel)
        library_layout.addWidget(QLabel("保存済み動画"))
        library_layout.addWidget(self.library, 1)

        splitter = QSplitter()
        splitter.addWidget(library_panel)
        splitter.addWidget(player_panel)
        splitter.setStretchFactor(1, 1)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(top)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(central)

        self.download_button.clicked.connect(self.start_download)
        self.refresh_button.clicked.connect(self.refresh_library)
        self.open_button.clicked.connect(self.open_file)
        self.play_button.clicked.connect(self.player.play)
        self.pause_button.clicked.connect(self.player.pause)
        self.library.itemDoubleClicked.connect(self.play_selected)
        self.player.durationChanged.connect(self.duration_changed)
        self.player.positionChanged.connect(self.position_changed)
        self.position.sliderMoved.connect(self.player.setPosition)
        self.player.errorOccurred.connect(self.player_error)

        self._add_menu()
        self.refresh_library()

    def _add_menu(self):
        file_menu = self.menuBar().addMenu("ファイル")
        choose = QAction("保存フォルダーを開く", self)
        choose.triggered.connect(self.open_video_folder)
        file_menu.addAction(choose)
        open_action = QAction("動画ファイルを開く…", self)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

    def start_download(self):
        url = self.url_input.text().strip()
        if not is_supported_youtube_url(url):
            QMessageBox.warning(self, "URLを確認", "YouTubeの動画URLを入力してください。")
            return
        if self.thread and self.thread.isRunning():
            QMessageBox.information(
                self, "ダウンロード中",
                "ダウンロードが終わってから次の動画を開始してください。"
            )
            return

        self.download_button.setEnabled(False)
        self.progress.setValue(0)
        self.status.setText("ダウンロードを準備しています…")
        self.thread = QThread(self)
        self.worker = DownloadWorker(url, VIDEO_DIR)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_download_finished)
        self.worker.failed.connect(self.on_download_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.cleanup_worker)
        self.thread.start()

    def on_progress(self, value, message):
        self.progress.setValue(value)
        self.status.setText(message)

    def on_download_finished(self, path):
        self.download_button.setEnabled(True)
        self.progress.setValue(100)
        self.status.setText(f"保存しました: {Path(path).name}")
        self.refresh_library()
        self.play_path(Path(path))

    def on_download_failed(self, message):
        self.download_button.setEnabled(True)
        self.status.setText("ダウンロードに失敗しました。")
        QMessageBox.warning(
            self, "ダウンロード失敗",
            "動画を取得できませんでした。\n\n"
            f"{message}\n\n"
            "URL、ネット接続、動画の公開状態、yt-dlpの対応状況を確認してください。"
        )

    def cleanup_worker(self):
        if self.worker:
            self.worker.deleteLater()
        self.worker = None
        self.thread = None

    def refresh_library(self):
        self.library.clear()
        VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        supported = {".mp4", ".m4v", ".mov", ".webm", ".mkv"}
        files = sorted(
            (p for p in VIDEO_DIR.iterdir() if p.is_file() and p.suffix.lower() in supported),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in files:
            item = QListWidgetItem(path.stem)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.library.addItem(item)
        if not files:
            self.library.addItem(QListWidgetItem("保存済み動画はありません"))

    def play_selected(self, item=None):
        item = item or self.library.currentItem()
        if not item:
            return
        value = item.data(Qt.ItemDataRole.UserRole)
        if value:
            self.play_path(Path(value))

    def play_path(self, path: Path):
        if path.exists():
            self.player.setSource(QUrl.fromLocalFile(str(path.resolve())))
            self.player.play()
            self.status.setText(f"再生中: {path.name}")

    def open_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "動画ファイルを選択", str(VIDEO_DIR),
            "動画 (*.mp4 *.m4v *.mov *.webm *.mkv);;すべてのファイル (*)"
        )
        if filename:
            self.play_path(Path(filename))

    def open_video_folder(self):
        import platform
        import subprocess
        try:
            if platform.system() == "Darwin":
                subprocess.Popen(["open", str(VIDEO_DIR)])
            elif platform.system() == "Windows":
                os.startfile(str(VIDEO_DIR))
            else:
                subprocess.Popen(["xdg-open", str(VIDEO_DIR)])
        except Exception as exc:
            QMessageBox.warning(self, "フォルダーを開けません", str(exc))

    def duration_changed(self, duration):
        self.position.setRange(0, duration)
        self.update_time_label(self.player.position(), duration)

    def position_changed(self, position):
        if not self.position.isSliderDown():
            self.position.setValue(position)
        self.update_time_label(position, self.player.duration())

    def update_time_label(self, position, duration):
        def fmt(ms):
            total = max(0, int(ms // 1000))
            return f"{total // 60:02d}:{total % 60:02d}"
        self.time_label.setText(f"{fmt(position)} / {fmt(duration)}")

    def player_error(self, error, message):
        if message:
            self.status.setText(f"再生エラー: {message}")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
