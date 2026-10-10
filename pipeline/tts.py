"""② 장면별 TTS. voice 프리셋(rate/pitch)으로 웃긴 톤을 만든다."""
import asyncio
import hashlib
import json
import pathlib
import shutil
import subprocess


async def _synth(text, voice_cfg, out):
    import edge_tts  # 지연 import: 캐시 히트/오프라인 테스트 시 불필요
    comm = edge_tts.Communicate(
        text, voice_cfg["name"], rate=voice_cfg["rate"], pitch=voice_cfg["pitch"]
    )
    await comm.save(str(out))


def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def postprocess(path: pathlib.Path, post: dict) -> None:
    """앞뒤 무음을 자르고 속도를 올린다(피치 유지). 실패하면 원본을 그대로 둔다."""
    tempo = float(post.get("tempo", 1.0))
    # 앞쪽 무음 제거 → 뒤집어서 같은 방식으로 뒤쪽 무음 제거 → 다시 뒤집기.
    # (stop_periods를 쓰면 대사 중간 쉼에서 뒤를 통째로 잘라 버려서 이 방식을 쓴다)
    trim = "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.04"
    af = f"{trim},areverse,{trim},areverse"
    if tempo != 1.0:
        af += f",atempo={tempo}"
    tmp = path.with_suffix(".post.mp3")
    r = subprocess.run([_ffmpeg(), "-loglevel", "error", "-y", "-i", str(path), "-af", af, str(tmp)],
                       capture_output=True)
    if r.returncode == 0 and tmp.exists() and tmp.stat().st_size > 1000:
        tmp.replace(path)
    elif tmp.exists():
        tmp.unlink()


def cache_path(text: str, voice_cfg: dict, cache_dir: pathlib.Path) -> pathlib.Path:
    key = hashlib.sha256(json.dumps([text, voice_cfg], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    return cache_dir / f"{key}.mp3"


def synthesize(scenes: list, cfg: dict, workdir: pathlib.Path, cache_dir: pathlib.Path = pathlib.Path("cache/tts")) -> list:
    """각 scene에 audio 경로를 채워 반환. 같은 대사+보이스는 캐시를 재사용한다."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    voices = cfg["tts"]["voices"]
    for i, sc in enumerate(scenes):
        out = workdir / f"tts_{i:02d}.mp3"
        voice_cfg = dict(voices.get(sc.get("voice", "narrator"), voices["narrator"]))
        post = cfg["tts"].get("postprocess") or {}
        key_cfg = {**voice_cfg, "_post": post}      # 후처리 설정이 바뀌면 캐시도 새로 만든다
        cached = cache_path(sc["text"], key_cfg, cache_dir)
        if cached.exists():
            shutil.copy(cached, out)
        else:
            asyncio.run(_synth(sc["text"], voice_cfg, out))
            if post:
                postprocess(out, post)
            shutil.copy(out, cached)
        sc["audio"] = str(out)
    return scenes
