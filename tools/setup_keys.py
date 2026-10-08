"""API 키를 물어보고 .env 파일을 만들어 준다 (숨김 파일을 직접 만들 필요 없음).
사용: python tools/setup_keys.py
입력한 키는 화면에 표시되지 않고, 이 컴퓨터의 .env 파일에만 저장된다."""
import getpass
import pathlib

ENV = pathlib.Path(__file__).resolve().parent.parent / ".env"
KEYS = [
    ("ANTHROPIC_API_KEY", "Anthropic API 키 (sk-ant-...로 시작)"),
    ("PEXELS_API_KEY", "Pexels API 키 (아직 없으면 그냥 Enter)"),
]


def read_existing() -> dict:
    d = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    return d


def main():
    cur = read_existing()
    for k, desc in KEYS:
        have = " [이미 있음, Enter=유지]" if cur.get(k) else ""
        v = getpass.getpass(f"{desc}{have}: ").strip().strip('"').strip("'")
        if v:
            cur[k] = v
    ENV.write_text("\n".join(f"{k}={v}" for k, v in cur.items()) + "\n", encoding="utf-8")
    print(f"저장 완료: {ENV}")
    print("저장된 항목:", ", ".join(k for k, v in cur.items() if v) or "(없음)")


if __name__ == "__main__":
    main()
