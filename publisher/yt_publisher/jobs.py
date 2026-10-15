"""영상 제작 작업: 주제 한 줄 → (옆 폴더의) 제작 프로그램 main.py 실행 → 영상·메타를 초안으로 등록."""
from __future__ import annotations
import json
import os
import pathlib
import shutil
import subprocess
import sys
import threading

from . import config, db, inbox

_lock = threading.Lock()
SUBS = {"science": "일상 속 과학 원리", "kitchen": "주방·청소 꿀팁", "habit": "습관·수면 상식"}


class JobError(Exception):
    pass


def pipeline_dir(settings: dict) -> pathlib.Path | None:
    cands = [settings.get("pipeline_dir") or "", str(config.APP_DIR.parent)]
    for c in cands:
        if c and (pathlib.Path(c) / "main.py").exists() and (pathlib.Path(c) / "pipeline").is_dir():
            return pathlib.Path(c)
    return None


def _abs(pdir: pathlib.Path, text: str) -> pathlib.Path:
    p = pathlib.Path(text.strip())
    return p if p.is_absolute() else pdir / p


def _python(settings: dict, pdir: pathlib.Path) -> str:
    if settings.get("pipeline_python"):
        return settings["pipeline_python"]
    for rel in (".venv/bin/python", ".venv/Scripts/python.exe"):
        if (pdir / rel).exists():
            return str(pdir / rel)
    return sys.executable


def start(settings: dict, topic: str = "", sub: str = "science", category: str = "science",
          script_only: bool = False, from_job: int | None = None) -> int:
    pdir = pipeline_dir(settings)
    if not pdir:
        raise JobError("영상 제작 프로그램(main.py)을 찾을 수 없습니다. 설정에서 제작 폴더를 지정하세요")
    if category != "science":
        raise JobError("지금은 과학 카테고리만 자동 제작을 지원합니다 (나머지는 영상을 직접 올려주세요)")
    if sub not in SUBS:
        raise JobError("세부 분야가 올바르지 않습니다")
    script_file = None
    if from_job is not None:
        j = db.get_job(from_job)
        if not j or not j.get("script_path") or not pathlib.Path(j["script_path"]).exists():
            raise JobError("이 작업에는 저장된 스크립트가 없습니다")
        topic, sub = j["topic"], j["sub"] or sub
        script_file = j["script_path"]
    topic = topic.strip()
    if not topic or len(topic) > 200:
        raise JobError("주제를 한 줄(200자 이내)로 입력하세요")
    if not _lock.acquire(blocking=False):
        raise JobError("다른 제작이 진행 중입니다. 끝난 뒤 다시 시도하세요")
    try:
        jid = db.add_job(topic, sub, category, script_only)
    except Exception:
        _lock.release()
        raise
    threading.Thread(target=_run, args=(jid, settings, pdir, topic, sub, script_only, script_file), daemon=True).start()
    return jid


def _run(jid, settings, pdir, topic, sub, script_only, script_file):
    final = {}
    try:
        final = _work(jid, settings, pdir, topic, sub, script_only, script_file)
    except Exception as e:
        final = {"status": "failed", "error": str(e), "finished_at": db.now_iso()}
    finally:
        _lock.release()          # 먼저 락을 풀어야, 완료를 본 화면이 곧바로 새 작업을 시작할 수 있다
        db.update_job(jid, **final)


def _work(jid, settings, pdir, topic, sub, script_only, script_file) -> dict:
    log, work, meta_path, video = [], None, None, None
    try:
        cmd = [_python(settings, pdir), "-u", "main.py", topic, "--category", sub]
        if script_only:
            cmd.append("--script-only")
        if script_file:
            cmd += ["--script-file", script_file]
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        p = subprocess.Popen(cmd, cwd=str(pdir), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace")
        for line in p.stdout:
            line = line.rstrip()
            log.append(line)
            if line.startswith("WORK_DIR="):
                work = pdir / line.split("=", 1)[1].strip()
            elif line.startswith("RENDER_DONE="):
                video = _abs(pdir, line.split("=", 1)[1])
            elif line.startswith("META="):
                meta_path = _abs(pdir, line.split("=", 1)[1])
            if len(log) % 5 == 0:
                db.update_job(jid, log="\n".join(log[-200:]))
        code = p.wait()
        if code != 0:
            raise JobError(f"제작 프로그램이 오류로 끝났습니다 (코드 {code}). 로그를 확인하세요")
        if script_only:
            sp = work / "script.json" if work else None
            if not sp or not sp.exists():
                raise JobError("스크립트 파일을 찾지 못했습니다")
            dest = config.DATA_DIR / "jobs" / str(jid)
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sp, dest / "script.json")
            return {"status": "script_ready", "script_path": str(dest / "script.json"),
                    "log": "\n".join(log[-200:]), "finished_at": db.now_iso()}
        if not video:
            video = next(iter(sorted((pdir / "out").glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True)), None)
        if not video or not video.exists():
            raise JobError("만들어진 영상 파일을 찾지 못했습니다")
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path and meta_path.exists() else {}
        dest_dir = config.INBOX_DIR / "shorts" / "science"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{video.stem}.mp4"
        shutil.copy2(video, dest)
        meta["problems"] = [x.strip(" ⚠") for x in log if x.strip().startswith("⚠")]
        dest.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        vid, _ = inbox.register(dest, "shorts", "science", meta)
        return {"status": "done", "video_id": vid, "log": "\n".join(log[-200:]), "finished_at": db.now_iso()}
    except Exception as e:
        return {"status": "failed", "error": str(e), "log": "\n".join(log[-200:]), "finished_at": db.now_iso()}
