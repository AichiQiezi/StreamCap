from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import Body, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ...core.platforms.platform_handlers import get_platform_info
from ...models.media.audio_format_model import AudioFormat
from ...models.media.video_format_model import VideoFormat
from ...models.media.video_quality_model import VideoQuality
from ...models.recording.recording_model import Recording
from ...models.recording.recording_status_model import RecordingStatus
from ...utils import utils
from ...utils.logger import logger
from ..video_stream_utils import InvalidVideoPathError, resolve_video_path
from .bridge import WebSocketBridge
from .media import AUDIO_EXTS, VIDEO_EXTS, MediaMonitor

ERROR_STATUSES = {RecordingStatus.RECORDING_ERROR, RecordingStatus.LIVE_STATUS_CHECK_ERROR}

# Settings the web UI may edit. Everything else in user_settings.json is left untouched.
EDITABLE_SETTINGS = {
    "live_save_path",
    "filename_includes_title",
    "remove_emojis",
    "folder_name_platform",
    "folder_name_author",
    "folder_name_time",
    "folder_name_title",
    "ascii_save_path",
    "enable_proxy",
    "proxy_address",
    "default_platform_with_proxy",
    "video_format",
    "record_quality",
    "loop_time_seconds",
    "platform_max_concurrent_requests",
    "segmented_recording_enabled",
    "video_segment_time",
    "force_https_recording",
    "default_live_source",
    "flv_use_direct_download",
    "recording_space_threshold",
    "convert_to_mp4",
    "delete_original",
    "generate_time_subtitle_file",
    "execute_custom_script",
    "custom_script_command",
    "stream_start_notification_enabled",
    "stream_end_notification_enabled",
    "only_notify_no_record",
    "custom_notification_title",
    "custom_stream_start_content",
    "custom_stream_end_content",
    "dingtalk_enabled",
    "dingtalk_webhook_url",
    "dingtalk_at_objects",
    "dingtalk_at_all",
    "wechat_enabled",
    "wechat_webhook_url",
    "feishu_enabled",
    "feishu_webhook_url",
    "bark_enabled",
    "bark_webhook_url",
    "bark_interrupt_level",
    "bark_sound",
    "ntfy_enabled",
    "ntfy_server_url",
    "ntfy_tags",
    "ntfy_email",
    "ntfy_action_url",
    "serverchan_enabled",
    "serverchan_sendkey",
    "serverchan_channel",
    "serverchan_tags",
    "telegram_enabled",
    "telegram_api_token",
    "telegram_chat_id",
    "email_enabled",
    "smtp_server",
    "email_username",
    "email_password",
    "sender_email",
    "sender_name",
    "recipient_email",
}


def derive_state(rec: Recording) -> str:
    """Single display state, same precedence as the Flet card (RecordingCardState)."""
    if rec.is_recording:
        return "recording"
    if rec.status_info in ERROR_STATUSES or rec.status_info == RecordingStatus.NOT_RECORDING_SPACE:
        return "error"
    if not rec.monitor_status:
        return "paused"
    if rec.is_checking:
        return "checking"
    if rec.status_info == RecordingStatus.NOT_IN_SCHEDULED_CHECK:
        return "scheduled"
    if rec.is_live:
        return "live"
    return "offline"


def duration_seconds(rec: Recording) -> int:
    if rec.is_recording and rec.start_time is not None:
        total = rec.cumulative_duration + (datetime.now() - rec.start_time)
    else:
        total = rec.last_duration or timedelta()
    return int(total.total_seconds())


class RecordingIn(BaseModel):
    url: str
    streamer_name: str | None = None
    quality: str | None = None
    record_format: str | None = None
    segment_record: bool | None = None
    segment_time: str | None = None
    video_bitrate: int | None = None
    recording_dir: str | None = None
    monitor_status: bool = True
    scheduled_recording: bool | None = None
    scheduled_start_time: str | None = None
    monitor_hours: str | None = None
    enabled_message_push: bool | None = None
    only_notify_no_record: bool | None = None
    flv_use_direct_download: bool | None = None


class BatchIn(BaseModel):
    ids: list[str]
    action: str  # start | stop | delete | check


def create_app(services, static_dir: Path | None, cache_dir: Path, allowed_hosts: list[str] | None = None) -> FastAPI:
    rm = services.recording_manager
    settings = services.settings_config
    state: dict[str, Any] = {}

    def serialize(rec: Recording) -> dict:
        stats = state["media"].get(rec.rec_id).public() if "media" in state else {}
        return {
            "id": rec.rec_id,
            "url": rec.url,
            "name": rec.streamer_name,
            "platform": rec.platform,
            "platform_key": rec.platform_key,
            "live_title": rec.live_title,
            "quality": rec.quality,
            "format": rec.record_format,
            "state": derive_state(rec),
            "status_info": rec.status_info,
            "monitor": bool(rec.monitor_status),
            "is_live": bool(rec.is_live),
            "is_recording": bool(rec.is_recording),
            "duration_s": duration_seconds(rec),
            "started_at": rec.start_time.isoformat() if rec.start_time else None,
            "recording_dir": rec.recording_dir,
            "segment_record": bool(rec.segment_record),
            "segment_time": rec.segment_time,
            "video_bitrate": rec.video_bitrate,
            "scheduled_recording": bool(rec.scheduled_recording),
            "scheduled_start_time": rec.scheduled_start_time,
            "monitor_hours": rec.monitor_hours,
            "enabled_message_push": bool(rec.enabled_message_push),
            "only_notify_no_record": bool(rec.only_notify_no_record),
            "flv_use_direct_download": bool(rec.flv_use_direct_download),
            "checked_at": rec.detection_time.isoformat() if rec.detection_time else None,
            "stats": stats,
        }

    def find(rec_id: str) -> Recording:
        rec = rm.find_recording_by_id(rec_id)
        if rec is None:
            raise HTTPException(404, "录制项不存在")
        return rec

    async def on_backend(coro):
        """Run a core coroutine on the BackendServices loop and wait for it."""
        fut = services.run_coro(coro)
        if fut is None:
            raise HTTPException(503, "录制后台未就绪")
        return await asyncio.wrap_future(fut) if not isinstance(fut, asyncio.Task) else await fut

    def push(rec: Recording) -> None:
        state["bridge"].emit("recording", serialize(rec))

    inflight_checks: set[str] = set()

    def check_live(rec: Recording):
        """check_if_live is not re-entrant: two concurrent calls start two recorders for one room.
        The guard runs on the backend loop, so it is atomic relative to the core's own checks."""

        async def guarded():
            if rec.rec_id in inflight_checks or rec.is_checking:
                return
            inflight_checks.add(rec.rec_id)
            try:
                await rm.check_if_live(rec)
            finally:
                inflight_checks.discard(rec.rec_id)

        return services.run_coro(guarded())

    def quality_label(q: str) -> str:
        return rm._.get(q, q)

    def save_root() -> Path:
        return Path(settings.get_video_save_path())

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        loop = asyncio.get_running_loop()
        bridge = WebSocketBridge(loop, serialize)
        state["bridge"] = bridge
        services.register_ui_bridge(bridge)
        media = MediaMonitor(services, cache_dir / "thumbs", on_change=push)
        state["media"] = media
        media.start()
        # With check_live_on_browser_refresh=False the core's periodic task checks immediately on
        # startup; otherwise it waits one interval and the Flet UI checks on load — so do that here.
        if settings.user_config.get("check_live_on_browser_refresh", True):
            for rec in rm.recordings:
                if rec.monitor_status and not rec.is_recording:
                    check_live(rec)
        yield
        await media.stop()
        services.unregister_ui_bridge(bridge)

    app = FastAPI(title="StreamCap Control API", lifespan=lifespan)
    if allowed_hosts:
        # The API has no auth (it can set the post-recording shell command), so when bound to
        # loopback, refuse foreign Host headers to block DNS-rebinding attacks from web pages.
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    # ---- state -------------------------------------------------------------
    @app.get("/api/state")
    async def get_state():
        root = save_root()
        root.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(root)
        return {
            "recordings": [serialize(r) for r in rm.recordings],
            "recording_enabled": services.recording_enabled,
            "disk": {"path": str(root), "free": usage.free, "total": usage.total},
            "options": {
                "qualities": [{"value": q, "label": quality_label(q)} for q in VideoQuality.get_qualities()],
                "video_formats": VideoFormat.get_formats(),
                "audio_formats": AudioFormat.get_formats(),
            },
        }

    # ---- recordings ---------------------------------------------------------
    @app.post("/api/recordings")
    async def add_recordings(items: list[RecordingIn]):
        cfg = settings.user_config
        existing = {r.url for r in rm.recordings}
        created, skipped = [], []
        for item in items:
            url = item.url.strip()
            platform, platform_key = get_platform_info(url)
            if not platform:
                skipped.append({"url": url, "reason": "不支持的直播平台"})
                continue
            if url in existing:
                skipped.append({"url": url, "reason": "已在列表中"})
                continue
            quality = item.quality or cfg.get("record_quality", VideoQuality.OD)
            rec = Recording(
                rec_id=str(uuid.uuid4()),
                url=url,
                streamer_name=(item.streamer_name or "").strip() or rm._.get("live_room", "直播间"),
                record_format=item.record_format or cfg.get("video_format", "TS"),
                quality=quality,
                segment_record=item.segment_record
                if item.segment_record is not None
                else cfg.get("segmented_recording_enabled", False),
                segment_time=item.segment_time or cfg.get("video_segment_time", "1800"),
                monitor_status=item.monitor_status,
                scheduled_recording=bool(item.scheduled_recording),
                scheduled_start_time=item.scheduled_start_time,
                monitor_hours=item.monitor_hours,
                recording_dir=item.recording_dir or None,
                enabled_message_push=bool(item.enabled_message_push),
                only_notify_no_record=item.only_notify_no_record
                if item.only_notify_no_record is not None
                else cfg.get("only_notify_no_record", False),
                flv_use_direct_download=item.flv_use_direct_download
                if item.flv_use_direct_download is not None
                else cfg.get("flv_use_direct_download", False),
                video_bitrate=item.video_bitrate,
            )
            rec.platform, rec.platform_key = platform, platform_key
            rec.loop_time_seconds = int(cfg.get("loop_time_seconds") or 300)
            rec.update_title(quality_label(quality))
            if not rec.monitor_status:
                rec.status_info = RecordingStatus.STOPPED_MONITORING
            await on_backend(rm.add_recording(rec))
            rec.scheduled_time_range = await rm.get_scheduled_time_range(rec.scheduled_start_time, rec.monitor_hours)
            existing.add(url)
            created.append(rec)
            push(rec)
            if rec.monitor_status:
                check_live(rec)
        return {"created": [serialize(r) for r in created], "skipped": skipped}

    @app.patch("/api/recordings/{rec_id}")
    async def edit_recording(rec_id: str, item: RecordingIn):
        rec = find(rec_id)
        updates = item.model_dump(exclude_unset=True)
        updates.pop("monitor_status", None)  # monitoring has its own endpoint
        if "url" in updates:
            updates["url"] = updates["url"].strip()
            platform, platform_key = get_platform_info(updates["url"])
            if not platform:
                raise HTTPException(400, "不支持的直播平台")
            updates["platform"], updates["platform_key"] = platform, platform_key
        if "recording_dir" in updates:
            updates["recording_dir"] = updates["recording_dir"] or None
        await on_backend(rm.update_recording_card(rec, updated_info=updates))
        rec.update_title(quality_label(rec.quality))
        rec.scheduled_time_range = await rm.get_scheduled_time_range(rec.scheduled_start_time, rec.monitor_hours)
        push(rec)
        return serialize(rec)

    @app.delete("/api/recordings/{rec_id}")
    async def delete_recording(rec_id: str):
        rec = find(rec_id)
        await _delete([rec])
        return {"ok": True}

    async def _delete(recs: list[Recording]):
        for rec in recs:
            if rec.monitor_status or rec.is_recording:
                await on_backend(rm.stop_monitor_recording(rec, auto_save=False))
        await on_backend(rm.delete_recording_cards(recs))
        for rec in recs:
            state["media"].thumb_path(rec.rec_id).unlink(missing_ok=True)
            state["media"].forget(rec.rec_id)

    @app.post("/api/recordings/{rec_id}/monitor")
    async def set_monitor(rec_id: str, on: Annotated[bool, Body(embed=True)]):
        rec = find(rec_id)
        if on:
            await on_backend(rm.start_monitor_recording(rec))
        else:
            await on_backend(rm.stop_monitor_recording(rec))
        push(rec)
        return serialize(rec)

    @app.post("/api/recordings/{rec_id}/record")
    async def set_record(rec_id: str, on: Annotated[bool, Body(embed=True)]):
        """Stop the current recording without pausing monitoring, or try to (re)start it now."""
        rec = find(rec_id)
        if not services.recording_enabled:
            raise HTTPException(409, "磁盘空间不足，录制已暂停")
        if not on:
            if rec.is_recording:

                async def _stop():
                    rm.stop_recording(rec, manually_stopped=True)
                    services.broadcast_card_update(rec)

                await on_backend(_stop())
            return serialize(rec)
        if not rec.monitor_status:
            await on_backend(rm.start_monitor_recording(rec))
        else:
            rec.manually_stopped = False
            await asyncio.wrap_future(check_live(rec))
        push(rec)
        return serialize(rec)

    @app.post("/api/recordings/{rec_id}/check")
    async def check_now(rec_id: str):
        rec = find(rec_id)
        if not rec.monitor_status:
            raise HTTPException(409, "请先开启监控")
        check_live(rec)
        return {"ok": True}

    @app.post("/api/recordings/batch")
    async def batch(body: BatchIn):
        recs = [r for r in (rm.find_recording_by_id(i) for i in body.ids) if r is not None]
        if body.action == "start":
            for rec in recs:
                await on_backend(rm.start_monitor_recording(rec, auto_save=False))
        elif body.action == "stop":
            for rec in recs:
                await on_backend(rm.stop_monitor_recording(rec, auto_save=False))
        elif body.action == "delete":
            await _delete(recs)
        elif body.action == "check":
            for rec in recs:
                if rec.monitor_status:
                    check_live(rec)
        else:
            raise HTTPException(400, "未知操作")
        services.run_coro(rm.persist_recordings())
        for rec in recs:
            if rec in rm.recordings:
                push(rec)
        return {"ok": True, "count": len(recs)}

    @app.get("/api/recordings/{rec_id}/thumbnail")
    async def thumbnail(rec_id: str):
        path = state["media"].thumb_path(rec_id)
        if not path.exists():
            raise HTTPException(404)
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=31536000"})

    @app.post("/api/recordings/{rec_id}/open-folder")
    async def open_rec_folder(rec_id: str):
        rec = find(rec_id)
        target = rec.recording_dir if rec.recording_dir and os.path.isdir(rec.recording_dir) else str(save_root())
        if not await asyncio.to_thread(utils.open_folder, target):
            raise HTTPException(500, "无法打开文件夹")
        return {"ok": True, "path": target}

    # ---- settings -----------------------------------------------------------
    @app.get("/api/settings")
    async def get_settings():
        cfg = settings.user_config
        return {
            "values": {k: cfg.get(k) for k in sorted(EDITABLE_SETTINGS)},
            "default_save_path": str(Path(settings.get_video_save_path())),
            "cookies": dict(settings.cookies_config or {}),
        }

    @app.put("/api/settings")
    async def put_settings(values: Annotated[dict, Body()]):
        unknown = set(values) - EDITABLE_SETTINGS
        if unknown:
            raise HTTPException(400, f"不可修改的配置项: {', '.join(sorted(unknown))}")
        settings.user_config.update(values)
        await on_backend(services.config_manager.save_user_config(settings.user_config))
        if "loop_time_seconds" in values:
            rm.initialize_dynamic_state()
        if "recording_space_threshold" in values or "live_save_path" in values:
            services.recording_enabled = True
            services.run_coro(rm.check_free_space())
        return {"ok": True}

    @app.put("/api/cookies")
    async def put_cookies(values: Annotated[dict[str, str], Body()]):
        cookies = settings.cookies_config
        for key, val in values.items():
            if val:
                cookies[key] = val
            else:
                cookies.pop(key, None)
        await on_backend(services.config_manager.save_cookies_config(cookies))
        return {"ok": True}

    # ---- files --------------------------------------------------------------
    @app.get("/api/files")
    async def list_files():
        root = save_root()

        def scan():
            items = []
            if not root.exists():
                return items
            for dirpath, _dirs, files in os.walk(root):
                for name in files:
                    ext = Path(name).suffix.lower()
                    if ext not in VIDEO_EXTS:
                        continue
                    full = Path(dirpath) / name
                    st = full.stat()
                    rel = full.relative_to(root)
                    items.append(
                        {
                            "path": rel.as_posix(),
                            "name": name,
                            "folder": rel.parent.as_posix() if rel.parent != Path(".") else "",
                            "size": st.st_size,
                            "mtime": st.st_mtime,
                            "kind": "audio" if ext in AUDIO_EXTS else "video",
                            "ext": ext[1:],
                        }
                    )
            items.sort(key=lambda f: f["mtime"], reverse=True)
            return items

        return {"root": str(root), "files": await asyncio.to_thread(scan)}

    def resolve_file(path: str) -> Path:
        rel = Path(path)
        try:
            full = resolve_video_path(save_root(), rel.name, rel.parent.as_posix() if rel.parent != Path(".") else None)
        except InvalidVideoPathError:
            raise HTTPException(400, "非法路径")
        if not full.is_file():
            raise HTTPException(404, "文件不存在")
        return full

    @app.get("/api/files/raw")
    async def file_raw(path: str = Query(...)):
        full = resolve_file(path)
        media_types = {
            ".mp4": "video/mp4",
            ".ts": "video/mp2t",
            ".flv": "video/x-flv",
            ".mkv": "video/x-matroska",
            ".mov": "video/quicktime",
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".aac": "audio/aac",
            ".wav": "audio/wav",
        }
        return FileResponse(full, media_type=media_types.get(full.suffix.lower(), "application/octet-stream"))

    @app.delete("/api/files")
    async def delete_file(path: str = Query(...)):
        full = resolve_file(path)
        await asyncio.to_thread(full.unlink)
        return {"ok": True}

    @app.post("/api/files/reveal")
    async def reveal_file(path: str = Query("")):
        target = resolve_file(path).parent if path else save_root()
        if not await asyncio.to_thread(utils.open_folder, str(target)):
            raise HTTPException(500, "无法打开文件夹")
        return {"ok": True}

    # ---- live updates ---------------------------------------------------------
    @app.websocket("/api/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        bridge: WebSocketBridge = state["bridge"]
        bridge.clients.add(ws)
        try:
            while True:
                await ws.receive_text()  # client pings keep the socket alive
        except WebSocketDisconnect:
            pass
        finally:
            bridge.clients.discard(ws)

    @app.exception_handler(Exception)
    async def unhandled(_request, exc: Exception):
        logger.exception(f"control api error: {exc}")
        return JSONResponse({"detail": str(exc)}, status_code=500)

    # ---- static frontend --------------------------------------------------------
    if static_dir and static_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        @app.get("/{full_path:path}")
        async def spa(full_path: str):
            candidate = static_dir / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(static_dir / "index.html", headers={"Cache-Control": "no-cache"})

    return app
