"""프로젝트 루트의 .env 파일을 읽어 환경변수로 등록한다(의존성 없음).
이미 설정된 환경변수는 덮어쓰지 않는다. .env 는 .gitignore 로 git에서 제외됨."""
import os
import pathlib


def load_env(path: str = ".env") -> None:
    p = pathlib.Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
