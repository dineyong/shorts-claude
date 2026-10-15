"""배포용 ZIP 만들기: python3 build_zip.py → dist/yt-publisher.zip (data, .venv, 테스트 제외)"""
import pathlib, zipfile
root = pathlib.Path(__file__).parent
out = root / "dist"; out.mkdir(exist_ok=True)
SKIP = {"data", ".venv", "dist", "__pycache__", "tests"}
with zipfile.ZipFile(out / "yt-publisher.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.is_dir() or SKIP & set(rel.parts) or p.suffix == ".pyc":
            continue
        info = zipfile.ZipInfo(f"yt-publisher/{rel.as_posix()}", (2026, 1, 1, 0, 0, 0))
        info.external_attr = (0o755 if p.suffix in (".command", ".sh") else 0o644) << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, p.read_bytes())
print("만들었습니다:", out / "yt-publisher.zip")
