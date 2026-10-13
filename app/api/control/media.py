from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from ...utils.logger import logger

VIDEO_EXTS = {".ts", ".flv", ".mp4", ".mkv", ".mov", ".nut", ".mp3", ".m4a", ".aac", ".wav"}
AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".wav"}
SAMPLE_INTERVAL = 2.0
THUMB_INTERVAL_RECORDING = 30.0
THUMB_INTERVAL_LIVE = 120.0


@dataclass
class LiveStats:
    file: str | None = None
    size_bytes: int = 0
    speed_bps: float = 0.0
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    vcodec: str | None = None
    thumb_version: int = 0
    _last_size: int = 0
    _last_t: float = 0.0
    _probed_file: str | None = None
    _thumb_at: float = 0.0
    _thumb_busy: bool = field(default=False, repr=False)

    def public(self) -> dict:
        return {
            "file": self.file,
            "size_bytes": self.size_bytes,
            "speed_bps": round(self.speed_bps),
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "vcodec": self.vcodec,
            "thumb_version": self.thumb_version,
        }


async def run_cmd(*args: str, timeout: float = 15.0) -> tuple[int, bytes]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
    except FileNotFoundError:
        return 127, b""
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
        return proc.returncode or 0, out
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, b""


async def probe(source: str) -> dict:
    code, out = await run_cmd(
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,width,height,avg_frame_rate",
        "-of",
        "json",
        source,
        timeout=12,
    )
    if code != 0:
        return {}
    try:
        streams = json.loads(out or b"{}").get("streams") or []
    except ValueError:
        return {}
    if not streams:
        return {}
    s = streams[0]
    fps = None
    if s.get("avg_frame_rate") and "/" in s["avg_frame_rate"]:
        num, den = s["avg_frame_rate"].split("/")
        fps = round(int(num) / int(den), 2) if int(den) else None
    return {"width": s.get("width"), "height": s.get("height"), "fps": fps, "vcodec": s.get("codec_name")}


async def grab_thumbnail(source: str, dest: Path, from_end: bool) -> bool:
    tmp = dest.with_suffix(".tmp.jpg")
    args = ["ffmpeg", "-y", "-v", "error"]
    if from_end:
        args += ["-sseof", "-3"]
    args += ["-i", source, "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "4", str(tmp)]
    code, _ = await run_cmd(*args, timeout=20)
    if code == 0 and tmp.exists() and tmp.stat().st_size > 0:
        os.replace(tmp, dest)
        return True
    tmp.unlink(missing_ok=True)
    return False


def newest_media_file(directory: str | None, since: float, ext: str | None) -> tuple[str | None, int]:
    """Return the newest file of this recording session and the total size of its segments.

    Only files with the recording's own extension that were *created* after the session started
    count, so an MP4 the core is still converting from the previous session isn't included.
    """
    if not directory or not os.path.isdir(directory):
        return None, 0
    wanted = {f".{ext.lower()}"} if ext else VIDEO_EXTS
    newest, newest_mtime, total = None, 0.0, 0
    with os.scandir(directory) as it:
        for entry in it:
            if not entry.is_file() or Path(entry.name).suffix.lower() not in wanted:
                continue
            st = entry.stat()
            if getattr(st, "st_birthtime", st.st_ctime) < since:
                continue
            total += st.st_size
            if st.st_mtime > newest_mtime:
                newest, newest_mtime = entry.path, st.st_mtime
    return newest, total


def _has_frames(file: str) -> bool:
    """Enough video written to decode a frame from the tail (checked before arming the retry timer)."""
    try:
        return Path(file).suffix.lower() not in AUDIO_EXTS and os.path.getsize(file) > 256 * 1024
    except OSError:
        return False


class MediaMonitor:
    """Samples size/speed of active recordings and keeps cover thumbnails fresh."""

    def __init__(self, services, thumbs_dir: Path, on_change):
        self.services = services
        self.thumbs_dir = thumbs_dir
        self.thumbs_dir.mkdir(parents=True, exist_ok=True)
        self.on_change = on_change
        self.stats: dict[str, LiveStats] = {}
        self._task: asyncio.Task | None = None
        # Pre-existing thumbnails survive restarts.
        for thumb in self.thumbs_dir.glob("*.jpg"):
            self.stats.setdefault(thumb.stem, LiveStats()).thumb_version = int(thumb.stat().st_mtime)

    def get(self, rec_id: str) -> LiveStats:
        return self.stats.setdefault(rec_id, LiveStats())

    def thumb_path(self, rec_id: str) -> Path:
        return self.thumbs_dir / f"{rec_id}.jpg"

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        while True:
            try:
                await self._sample()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # keep sampling even if one pass fails
                logger.debug(f"media sample failed: {exc}")
            await asyncio.sleep(SAMPLE_INTERVAL)

    async def _sample(self) -> None:
        rm = self.services.recording_manager
        now = time.time()
        for rec in list(rm.recordings):
            st = self.get(rec.rec_id)
            if rec.is_recording and rec.start_time is not None:
                since = rec.start_time.timestamp() - 5
                file, total = await asyncio.to_thread(newest_media_file, rec.recording_dir, since, rec.record_format)
                changed = file != st.file
                if st._last_t and total >= st._last_size:
                    inst = (total - st._last_size) / max(now - st._last_t, 0.001)
                    st.speed_bps = inst if not st.speed_bps else st.speed_bps * 0.6 + inst * 0.4
                st.file, st.size_bytes, st._last_size, st._last_t = file, total, total, now
                if file and file != st._probed_file and Path(file).suffix.lower() not in AUDIO_EXTS:
                    st._probed_file = file
                    asyncio.create_task(self._probe(rec.rec_id, file))
                # Only ever read the local file here: some CDNs (e.g. Douyu) hand out single-use
                # stream URLs, and a second pull on the recorder's URL breaks the recording.
                due = now - st._thumb_at > THUMB_INTERVAL_RECORDING or changed or not st.thumb_version
                if file and due and _has_frames(file):
                    self._refresh_thumb(rec, st, now, file)
                self.on_change(rec)
            else:
                if st.speed_bps or st._last_t:
                    st.speed_bps, st._last_t, st._last_size = 0.0, 0.0, 0
                    self.on_change(rec)
                # Live but deliberately not recorded (notify-only mode): peek at the stream now and then.
                # Never do this otherwise — the recorder may be about to open this very URL.
                if (
                    rec.is_live
                    and rec.monitor_status
                    and rec.only_notify_no_record
                    and now - st._thumb_at > THUMB_INTERVAL_LIVE
                ):
                    self._refresh_thumb(rec, st, now, None)

    async def _probe(self, rec_id: str, file: str) -> None:
        await asyncio.sleep(4)  # let the muxer write enough to identify the stream
        info = await probe(file)
        if info:
            st = self.get(rec_id)
            st.width, st.height, st.fps, st.vcodec = info["width"], info["height"], info["fps"], info["vcodec"]

    def _refresh_thumb(self, rec, st: LiveStats, now: float, file: str | None) -> None:
        if st._thumb_busy:
            return
        st._thumb_at = now
        st._thumb_busy = True
        asyncio.create_task(self._thumb(rec, st, file))

    async def _thumb(self, rec, st: LiveStats, file: str | None) -> None:
        try:
            dest = self.thumb_path(rec.rec_id)
            ok = False
            if file and _has_frames(file):
                ok = await grab_thumbnail(file, dest, from_end=True)
            if not ok and not rec.is_recording:
                remote = rec.preview_url or rec.record_url
                if remote:
                    ok = await grab_thumbnail(remote, dest, from_end=False)
            if ok:
                st.thumb_version = int(time.time())
                self.on_change(rec)
        finally:
            st._thumb_busy = False
