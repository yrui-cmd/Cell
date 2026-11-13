"""Capture only the bound PowerPoint window; never fall back to desktop pixels."""
import subprocess
import threading
import time
from pathlib import Path


def matches_preview_title(title, path):
    path = Path(path)
    return any(title.startswith(name + " - ") for name in (path.name, path.stem))


def bound_window(info, state, gui, process):
    if any(info.get(k) != state.get(k) for k in ("job_id", "run_id")):
        raise ValueError("Recording window belongs to another playback")
    hwnd = info.get("hwnd")
    if not isinstance(hwnd, int) or not gui.IsWindow(hwnd):
        raise RuntimeError("PowerPoint preview window is closed")
    if process.GetWindowThreadProcessId(hwnd)[1] != info.get("pid"):
        raise RuntimeError("PowerPoint preview window identity changed")
    if not matches_preview_title(gui.GetWindowText(hwnd), state["copy"]):
        raise RuntimeError("PowerPoint preview window no longer matches this file")
    return hwnd


class WindowRecorder:
    def __init__(self, ffmpeg, hwnd, root):
        import cv2
        import numpy as np
        import win32gui
        from windows_capture import WindowsCapture

        self.error = None
        self.latest = None
        self.frames = 0
        self.ready = threading.Event()
        self.stopping = threading.Event()
        self.control = self.encoder = self.writer = self.log = None
        self.returncode = None
        title = win32gui.GetWindowText(hwnd)
        # Version 1.5 binds by a title substring. Require an unambiguous match first.
        matches = []
        win32gui.EnumWindows(lambda h, _: matches.append(h) if title in win32gui.GetWindowText(h) else None, None)
        if not title or matches != [hwnd]:
            raise RuntimeError("Ambiguous PowerPoint capture window")
        capture = WindowsCapture(cursor_capture=False, draw_border=False,
            secondary_window=False, minimum_update_interval=50, window_name=title)
        self.capture = capture

        @capture.event
        def on_frame_arrived(frame, control):
            try:
                # Fixed output size with letterboxing preserves the full window on resize.
                scale = min(1920 / frame.width, 1080 / frame.height)
                w, h = max(1, int(frame.width * scale)), max(1, int(frame.height * scale))
                resized = cv2.resize(frame.frame_buffer[:, :, :3], (w, h))
                pixels = np.zeros((1080, 1920, 3), dtype=np.uint8)
                x, y = (1920 - w) // 2, (1080 - h) // 2
                pixels[y:y+h, x:x+w] = resized
                self.latest = pixels.tobytes()
                self.ready.set()
            except Exception as error:
                self.error = error
                self.ready.set()

        @capture.event
        def on_closed():
            if not self.stopping.is_set():
                self.error = RuntimeError("Captured PowerPoint window was closed")
                self.ready.set()

        try:
            self.control = capture.start_free_threaded()
            if not self.ready.wait(15) or self.latest is None or self.error:
                raise RuntimeError(f"No usable PowerPoint window frames: {self.error}")
            root = Path(root)
            self.log = (root / "recording.log").open("wb")
            self.encoder = subprocess.Popen([
                ffmpeg, "-hide_banner", "-nostats", "-f", "rawvideo", "-pix_fmt", "bgr24",
                "-video_size", "1920x1080", "-framerate", "20", "-i", "pipe:0", "-an",
                "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+frag_keyframe+empty_moov",
                "-g", "40", "-flush_packets", "1", "-progress", str(root / "recording-progress.txt"),
                str(root / "PPT-output.mp4")], stdin=subprocess.PIPE, stdout=self.log, stderr=self.log,
                creationflags=subprocess.CREATE_NO_WINDOW)
            self.writer = threading.Thread(target=self._write_frames, daemon=True)
            self.writer.start()
        except Exception:
            self.communicate(timeout=20)
            raise

    def _write_frames(self):
        deadline = time.monotonic()
        try:
            while not self.stopping.is_set():
                self.encoder.stdin.write(self.latest)
                self.frames += 1
                deadline += 0.05
                self.stopping.wait(max(0, deadline - time.monotonic()))
        except Exception as error:
            if not self.stopping.is_set():
                self.error = error

    def poll(self):
        if self.error:
            raise RuntimeError(f"Window recording failed: {self.error}")
        return self.encoder.poll()

    def communicate(self, _input=None, timeout=30):
        self.stopping.set()
        if self.writer:
            self.writer.join(timeout=10)
            if self.writer.is_alive() and self.encoder:
                self.encoder.kill()
                self.writer.join(timeout=5)
                self.error = self.error or RuntimeError("Recording encoder stopped accepting frames")
        if self.control:
            self.control.stop()
            self.control = None
        if self.encoder:
            try:
                self.encoder.stdin.close()
            except OSError:
                pass
            try:
                self.returncode = self.encoder.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.encoder.kill()
                self.returncode = self.encoder.wait(timeout=5)
        if self.log:
            self.log.close()
            self.log = None
        if self.error:
            raise RuntimeError(f"Window recording failed: {self.error}")
