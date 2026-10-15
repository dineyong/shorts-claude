"""로컬 웹 서버(표준 라이브러리만 사용). 이 컴퓨터(127.0.0.1)에서만 접속된다."""
from __future__ import annotations
import datetime as dt
import json
import mimetypes
import pathlib
import re
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from . import __version__, checks, config, db, grid, inbox, jobs, publisher, stats, worker
from .catalog import FORMATS, SHORTS_CATEGORIES, STATUS_LABEL
from .errors import PublishError
from .youtube import YouTubeClient, client_for, token_path

MAX_UPLOAD = 8 << 30          # 8GB
_auth_state = {}              # 채널 로그인 진행 상태


class Api(Exception):
    def __init__(self, status: int, msg: str, extra: dict | None = None):
        super().__init__(msg)
        self.status, self.msg, self.extra = status, msg, extra or {}


EDITABLE = {"title", "description", "tags", "category", "affiliate", "rights_confirmed", "synthetic", "claims"}


def _video_out(v: dict, settings: dict) -> dict:
    errs, warns = checks.validate_video(v, settings)
    out = {k: v[k] for k in ("id", "format", "category", "title", "description", "tags", "status", "publish_at",
                             "youtube_id", "affiliate", "rights_confirmed", "synthetic", "error", "attempts",
                             "channel_id", "created_at", "uploaded_at", "claims", "sources", "problems")}
    out["status_label"] = STATUS_LABEL.get(v["status"], v["status"])
    out["file_name"] = pathlib.Path(v["file_path"]).name
    out["errors"], out["warnings"] = errs, warns
    return out


def state_payload() -> dict:
    s = db.get_settings()
    chans = []
    for c in db.list_channels():
        live = s["mode"] == "live"
        chans.append({**c, "authorized": YouTubeClient(c["id"]).authorized() if live else None})
    counts = {}
    for v in db.list_videos():
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    return {"version": __version__, "settings": s, "channels": chans, "counts": counts,
            "formats": FORMATS, "shorts_categories": SHORTS_CATEGORIES, "status_label": STATUS_LABEL,
            "pipeline_ready": bool(jobs.pipeline_dir(s)), "job_subs": jobs.SUBS,
            "has_secret": config.SECRET_PATH.exists(), "last_tick": worker.last_tick(),
            "data_dir": str(config.DATA_DIR), "inbox_dir": str(config.INBOX_DIR),
            "auth": _auth_state}


def _json_body(h) -> dict:
    n = int(h.headers.get("Content-Length") or 0)
    if n > 2_000_000:
        raise Api(413, "요청이 너무 큽니다")
    raw = h.rfile.read(n) if n else b"{}"
    try:
        d = json.loads(raw.decode("utf-8") or "{}")
    except ValueError:
        raise Api(400, "JSON 형식이 올바르지 않습니다")
    if not isinstance(d, dict):
        raise Api(400, "JSON 객체가 필요합니다")
    return d


def _need_video(vid: int) -> dict:
    v = db.get_video(vid)
    if not v:
        raise Api(404, "영상을 찾을 수 없습니다")
    return v


def _auth_thread(cid: str):
    _auth_state[cid] = {"state": "waiting", "msg": "브라우저에서 구글 로그인을 완료하세요"}
    try:
        YouTubeClient(cid).authorize()
        _auth_state[cid] = {"state": "done", "msg": "연결되었습니다"}
    except Exception as e:
        _auth_state[cid] = {"state": "error", "msg": str(e)}


# ---------------- 라우팅 ----------------
def handle(method: str, path: str, query: dict, h) -> object:
    p = path.rstrip("/") or "/"
    s = db.get_settings()

    if method == "GET":
        if p == "/api/state":
            return state_payload()
        if p == "/api/videos":
            vs = db.list_videos(fmt=query.get("format"), category=query.get("category"), status=query.get("status"))
            return [_video_out(v, s) for v in vs]
        m = re.fullmatch(r"/api/videos/(\d+)", p)
        if m:
            return _video_out(_need_video(int(m.group(1))), s)
        if p == "/api/schedule":
            return grid.build(int(query.get("days", 7)))
        if p == "/api/stats/overview":
            return stats.overview(fmt=query.get("format"))
        if p == "/api/stats/series":
            return stats.daily_series(int(query.get("days", 14)), category=query.get("category"), fmt=query.get("format"))
        m = re.fullmatch(r"/api/stats/video/(\d+)", p)
        if m:
            v = _need_video(int(m.group(1)))
            now = dt.datetime.now(ZoneInfo(s["timezone"]))
            return {"summary": stats.video_summary(v, now), "snapshots": db.snapshots(v["id"])}
        if p == "/api/jobs":
            return db.list_jobs()
        m = re.fullmatch(r"/api/jobs/(\d+)", p)
        if m:
            j = db.get_job(int(m.group(1)))
            if not j:
                raise Api(404, "작업을 찾을 수 없습니다")
            if j.get("script_path") and pathlib.Path(j["script_path"]).exists():
                try:
                    j["script"] = json.loads(pathlib.Path(j["script_path"]).read_text(encoding="utf-8"))
                except ValueError:
                    pass
            return j
        if p == "/api/settings":
            return s
        if p == "/api/logs":
            return db.logs(int(query.get("limit", 100)))
        raise Api(404, "없는 주소입니다")

    if method == "PUT":
        m = re.fullmatch(r"/api/videos/(\d+)", p)
        if m:
            v = _need_video(int(m.group(1)))
            if v["status"] in ("uploaded", "published"):
                raise Api(409, "이미 업로드된 영상은 여기서 수정할 수 없습니다 (유튜브 스튜디오에서 수정)")
            body = _json_body(h)
            f = {k: body[k] for k in body if k in EDITABLE}
            for k in ("affiliate", "rights_confirmed", "synthetic"):
                if k in f:
                    f[k] = int(bool(f[k]))
            if "tags" in f and isinstance(f["tags"], str):
                f["tags"] = [t.strip().lstrip("#") for t in re.split(r"[,\n]", f["tags"]) if t.strip()]
            if "claims" in f:
                if not isinstance(f["claims"], list):
                    raise Api(400, "claims 형식이 올바르지 않습니다")
                old = v["claims"]
                f["claims"] = [{"claim": old[i]["claim"], "source": old[i]["source"], "checked": bool(c.get("checked"))}
                               for i, c in enumerate(f["claims"][:len(old)])]
            if "category" in f and v["format"] == "shorts" and f["category"] not in SHORTS_CATEGORIES:
                raise Api(400, "카테고리가 올바르지 않습니다")
            if f:
                db.update_video(v["id"], **f)
            return _video_out(db.get_video(v["id"]), s)
        if p == "/api/settings":
            return db.save_settings(_json_body(h))
        raise Api(404, "없는 주소입니다")

    if method == "DELETE":
        m = re.fullmatch(r"/api/videos/(\d+)", p)
        if m:
            v = _need_video(int(m.group(1)))
            if v["status"] in ("uploaded", "published"):
                raise Api(409, "유튜브에 올라간 영상은 목록에서 지울 수 없습니다 (통계 기록 보존)")
            db.delete_video(v["id"])
            return {"ok": True}
        raise Api(404, "없는 주소입니다")

    if method == "POST":
        m = re.fullmatch(r"/api/videos/(\d+)/queue", p)
        if m:
            body = _json_body(h)
            try:
                r = publisher.enqueue(int(m.group(1)), body.get("publish_at"))
            except publisher.ValidationError as e:
                raise Api(422, "발행 대기로 넘길 수 없습니다", {"errors": e.errors})
            except ValueError as e:
                raise Api(409, str(e))
            return {**r, "video": _video_out(db.get_video(int(m.group(1))), s)}
        m = re.fullmatch(r"/api/videos/(\d+)/unqueue", p)
        if m:
            try:
                publisher.unqueue(int(m.group(1)))
            except ValueError as e:
                raise Api(409, str(e))
            return {"ok": True}
        if p == "/api/make":
            body = _json_body(h)
            try:
                jid = jobs.start(s, body.get("topic", ""), body.get("sub", "science"), body.get("category", "science"),
                                 bool(body.get("script_only")), body.get("from_job"))
            except jobs.JobError as e:
                raise Api(409, str(e))
            return {"id": jid}
        if p == "/api/inbox/scan":
            return inbox.scan_inbox()
        if p == "/api/run":
            body = _json_body(h)
            return worker.run_once(client_for, force_stats=bool(body.get("force_stats")))
        if p == "/api/upload":
            return _receive_upload(query, h)
        if p == "/api/client-secret":
            raw = h.rfile.read(int(h.headers.get("Content-Length") or 0))
            try:
                d = json.loads(raw.decode("utf-8"))
                assert "installed" in d or "web" in d
            except Exception:
                raise Api(400, "구글 클라우드에서 받은 OAuth 클라이언트 JSON 파일이 아닙니다")
            config.SECRET_PATH.write_bytes(raw)
            return {"ok": True}
        if p == "/api/channels":
            body = _json_body(h)
            cid = re.sub(r"[^a-z0-9_\-]", "", str(body.get("id", "")).lower())
            if not cid or not str(body.get("name", "")).strip():
                raise Api(400, "채널 id(영문/숫자)와 이름이 필요합니다")
            db.add_channel(cid, str(body["name"]).strip())
            return {"ok": True, "id": cid}
        m = re.fullmatch(r"/api/channels/([a-z0-9_\-]+)/auth", p)
        if m:
            if s["mode"] != "live":
                raise Api(409, "데모 모드입니다. 설정에서 '실제 발행'으로 바꾼 뒤 연결하세요")
            if not config.SECRET_PATH.exists():
                raise Api(409, "먼저 구글 인증 파일(client_secret.json)을 올려주세요")
            threading.Thread(target=_auth_thread, args=(m.group(1),), daemon=True).start()
            return {"started": True}
        raise Api(404, "없는 주소입니다")

    raise Api(405, "허용되지 않는 방식입니다")


def _receive_upload(query: dict, h) -> dict:
    fmt, cat = query.get("format", "shorts"), query.get("category") or None
    if fmt not in FORMATS:
        raise Api(400, "포맷이 올바르지 않습니다")
    if fmt == "shorts" and cat not in SHORTS_CATEGORIES:
        raise Api(400, "쇼츠는 카테고리가 필요합니다")
    name = inbox.safe_name(query.get("name", "video.mp4"))
    if pathlib.Path(name).suffix.lower() not in config.VIDEO_EXT:
        raise Api(400, "mp4, mov, webm, m4v 영상만 올릴 수 있습니다")
    n = int(h.headers.get("Content-Length") or 0)
    if n <= 0 or n > MAX_UPLOAD:
        raise Api(413, "파일 크기가 올바르지 않습니다 (최대 8GB)")
    dest = config.UPLOAD_DIR / name
    left = n
    with open(dest, "wb") as f:
        while left > 0:
            chunk = h.rfile.read(min(1 << 20, left))
            if not chunk:
                break
            f.write(chunk)
            left -= len(chunk)
    if left:
        dest.unlink(missing_ok=True)
        raise Api(400, "업로드가 중간에 끊겼습니다")
    vid, new = inbox.register(dest, fmt, cat, {"title": pathlib.Path(query.get("name", name)).stem})
    if not new:
        dest.unlink(missing_ok=True)
    return {"id": vid, "duplicate": not new}


class Handler(BaseHTTPRequestHandler):
    server_version = "YtPublisher/" + __version__

    def log_message(self, *a):         # 콘솔 소음 줄이기
        pass

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0].strip("[]")
        return host in ("localhost", "127.0.0.1", "::1")

    def _send(self, status: int, payload, ctype="application/json; charset=utf-8"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _dispatch(self, method: str):
        if not self._host_ok():
            return self._send(403, {"error": "이 컴퓨터에서만 접속할 수 있습니다"})
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path.startswith("/api/"):
            # 다른 사이트가 몰래 요청을 보내지 못하게: 변경 요청은 커스텀 헤더 필수
            if method != "GET" and self.headers.get("X-Requested-With") != "yt-publisher":
                return self._send(403, {"error": "허용되지 않은 요청입니다"})
            try:
                return self._send(200, handle(method, u.path, q, self))
            except Api as e:
                return self._send(e.status, {"error": e.msg, **e.extra})
            except PublishError as e:
                return self._send(502, {"error": str(e)})
            except Exception:
                db.log("error", traceback.format_exc(limit=4))
                return self._send(500, {"error": "서버 오류가 발생했습니다. 로그를 확인하세요"})
        if method != "GET":
            return self._send(405, {"error": "허용되지 않는 방식입니다"})
        rel = "index.html" if u.path in ("", "/") else u.path.lstrip("/")
        f = (config.WEB_DIR / rel).resolve()
        if config.WEB_DIR.resolve() not in f.parents or not f.is_file():
            return self._send(404, b"not found", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        return self._send(200, f.read_bytes(), ctype)

    def do_GET(self): self._dispatch("GET")
    def do_POST(self): self._dispatch("POST")
    def do_PUT(self): self._dispatch("PUT")
    def do_DELETE(self): self._dispatch("DELETE")


def make_server(port: int = 8765) -> ThreadingHTTPServer:
    for p in range(port, port + 20):
        try:
            return ThreadingHTTPServer(("127.0.0.1", p), Handler)
        except OSError:
            continue
    raise OSError("사용 가능한 포트를 찾지 못했습니다")
