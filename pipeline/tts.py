"""② 장면별 TTS. voice 프리셋(rate/pitch)으로 웃긴 톤을 만든다."""
import asyncio
import pathlib
import edge_tts


async def _synth(text, voice_cfg, out):
    comm = edge_tts.Communicate(
        text, voice_cfg["name"], rate=voice_cfg["rate"], pitch=voice_cfg["pitch"]
    )
    await comm.save(str(out))


def synthesize(scenes: list, cfg: dict, workdir: pathlib.Path) -> list:
    """각 scene에 audio 경로를 채워 반환."""
    voices = cfg["tts"]["voices"]
    for i, sc in enumerate(scenes):
        out = workdir / f"tts_{i:02d}.mp3"
        voice_cfg = voices.get(sc.get("voice", "narrator"), voices["narrator"])
        asyncio.run(_synth(sc["text"], voice_cfg, out))
        sc["audio"] = str(out)
    return scenes
