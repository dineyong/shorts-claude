"""④ 편집/렌더(MoviePy 2.x). 장면별 클립 -> 효과 -> 자막 -> 효과음 -> 이어붙이기.
뼈대 단계: 실제 실행 후 폰트/효과 튜닝 필요."""
import pathlib
from moviepy import (
    AudioFileClip, ColorClip, CompositeAudioClip, CompositeVideoClip,
    ImageClip, TextClip, VideoFileClip, concatenate_videoclips,
)

from pipeline.subtitle import timings

W, H = 1080, 1920


def _base_clip(media, dur):
    if media is None:
        return ColorClip((W, H), color=(20, 20, 28), duration=dur)
    ext = pathlib.Path(media).suffix.lower()
    if ext in {".mp4", ".webm", ".gif"}:
        c = VideoFileClip(media)
        c = c.with_effects([]) if False else c
        c = c.looped(duration=dur) if hasattr(c, "looped") and c.duration < dur else c.subclipped(0, dur)
    else:
        c = ImageClip(media).with_duration(dur)
    # 화면을 꽉 채우도록 확대 후 중앙 크롭
    scale = max(W / c.w, H / c.h)
    c = c.resized(scale).cropped(width=W, height=H, x_center=c.w * scale / 2, y_center=c.h * scale / 2)
    return c


def _apply_effect(c, effect):
    if effect == "punch_in":
        return c.resized(lambda t: 1.0 + 0.18 * min(t / 0.25, 1.0))   # 0.25초 안에 확대
    if effect == "zoom_slow":
        return c.resized(lambda t: 1.0 + 0.04 * t)
    if effect == "shake":
        return c.with_position(lambda t: (int(8 * ((t * 40) % 2 - 1)), int(8 * (((t * 53) % 2) - 1))))
    return c


def _captions(text, dur, font, style):
    """구절 단위로 순서대로 바뀌는 자막. 마지막 구절은 강조색."""
    parts = timings(text, dur)
    clips = []
    for i, (chunk, s, e) in enumerate(parts):
        color = style["accent"] if i == len(parts) - 1 else style["text"]
        clips.append(
            TextClip(font=font, text=chunk, font_size=style["font_size"], color=color,
                     stroke_color=style["stroke"], stroke_width=8, method="caption",
                     size=(W - 160, None), text_align="center")
            .with_start(s).with_duration(max(e - s, 0.05))
            .with_position(("center", style["caption_y"]))
        )
    return clips


def render(scenes: list, cfg: dict, out_path: pathlib.Path, style: dict) -> pathlib.Path:
    font = cfg["assets"]["font"]
    sfx_dir = pathlib.Path(cfg["assets"]["sfx_dir"])
    clips = []
    for sc in scenes:
        voice = AudioFileClip(sc["audio"])
        dur = voice.duration + 0.12                      # 대사 뒤 짧은 여백(리듬)
        base = _apply_effect(_base_clip(sc.get("media"), dur), sc.get("effect", "none"))
        comp = CompositeVideoClip([base, *_captions(sc["text"], dur, font, style)], size=(W, H))
        tracks = [voice]
        sfx = sc.get("sfx")
        if sfx and (sfx_dir / f"{sfx}.mp3").exists():
            tracks.append(AudioFileClip(str(sfx_dir / f"{sfx}.mp3")).with_start(0))
        clips.append(comp.with_audio(CompositeAudioClip(tracks)).with_duration(dur))
    final = concatenate_videoclips(clips, method="compose")
    final.write_videofile(str(out_path), fps=cfg["video"]["fps"], codec="libx264",
                          audio_codec="aac", preset="medium")
    return out_path
