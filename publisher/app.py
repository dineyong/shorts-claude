"""실행: python app.py   (브라우저가 자동으로 열립니다)
옵션: --port 8765  --no-browser  --home <데이터 폴더>"""
from __future__ import annotations
import argparse
import os
import sys
import threading
import webbrowser


def main():
    ap = argparse.ArgumentParser(description="유튜브 자동 발행 · 통계 추적")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--home", help="데이터 폴더(기본: 이 폴더의 data)")
    a = ap.parse_args()
    if a.home:
        os.environ["YT_PUBLISHER_HOME"] = a.home
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from yt_publisher import config, db, server, worker
    db.init()
    srv = server.make_server(a.port)
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    w = worker.Worker()
    w.start()
    print(f"\n  유튜브 발행 스튜디오가 켜졌습니다  →  {url}")
    print(f"  데이터 폴더: {config.DATA_DIR}")
    print("  끄려면 이 창에서 Ctrl+C 를 누르세요\n")
    if not a.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        w.stop()
        srv.server_close()


if __name__ == "__main__":
    main()
