"""② 장면별 TTS. voice 프리셋(rate/pitch)으로 웃긴 톤을 만든다."""
import asyncio
import hashlib
import json
import pathlib
import shutil


async def _synth(text, voice_cfg, out):
    import edge_tts  # 지연 import: 캐시 히트/오프라인 테스트 시 불필요
    comm = edge_tts.Communicate(
        text, voice_cfg["name"], rate=voice_cfg["rate"], pitch=voice_cfg["pitch"]
    )
    await comm.save(str(out))


def cache_path(text: str, voice_cfg: dict, cache_dir: pathlib.Path) -> pathlib.Path:
    key = hashlib.sha256(json.dumps([text, voice_cfg], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    return cache_dir / f"{key}.mp3"


def synthesize(scenes: list, cfg: dict, workdir: pathlib.Path, cache_dir: pathlib.Path = pathlib.Path("cache/tts")) -> list:
    """각 scene에 audio 경로를 채워 반환. 같은 대사+보이스는 캐시를 재사용한다."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    voices = cfg["tts"]["voices"]
    for i, sc in enumerate(scenes):
        out = workdir / f"tts_{i:02d}.mp3"
        voice_cfg = voices.get(sc.get("voice", "narrator"), voices["narrator"])
        cached = cache_path(sc["text"], voice_cfg, cache_dir)
        if cached.exists():
            shutil.copy(cached, out)
        else:
            asyncio.run(_synth(sc["text"], voice_cfg, out))
            shutil.copy(out, cached)
        sc["audio"] = str(out)
    return scenes
