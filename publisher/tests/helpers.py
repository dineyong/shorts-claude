import os, pathlib, tempfile, sys

def fresh_home():
    d = tempfile.mkdtemp(prefix="ytpub_")
    os.environ["YT_PUBLISHER_HOME"] = d
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    # config 는 import 시점에 경로를 고정하므로 재로딩
    import importlib
    from yt_publisher import config
    importlib.reload(config)
    from yt_publisher import db
    importlib.reload(db)
    db.init()
    return pathlib.Path(d)

def make_video(home, name="a.mp4", data=b"video-bytes"):
    p = home / name
    p.write_bytes(data)
    return str(p)
