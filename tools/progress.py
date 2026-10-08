"""docs/ROADMAP.md 의 체크박스를 세어 진행률 막대를 갱신한다.
사용: python tools/progress.py"""
import pathlib
import re

P = pathlib.Path(__file__).resolve().parent.parent / "docs" / "ROADMAP.md"
BAR = 20


def bar(done, total):
    n = round(BAR * done / total) if total else 0
    pct = round(100 * done / total) if total else 0
    return f"{'█' * n}{'░' * (BAR - n)} {pct}% ({done}/{total})"


def main():
    text = P.read_text(encoding="utf-8")
    body = text.split("## 세션 계획", 1)[1]
    sessions = re.split(r"^### ", body, flags=re.M)[1:]
    rows, td, tt = [], 0, 0
    for s in sessions:
        title = s.splitlines()[0].replace("✅", "").replace("←", "←").strip()
        d = len(re.findall(r"^- \[x\]", s, flags=re.M | re.I))
        t = d + len(re.findall(r"^- \[ \]", s, flags=re.M))
        td, tt = td + d, tt + t
        rows.append(f"{'✅' if t and d == t else '🔄' if d else '⬜'} {title.split(' (')[0]:<40} {bar(d, t)}")
    block = "```\n전체  " + bar(td, tt) + "\n\n" + "\n".join(rows) + "\n```"
    text = re.sub(
        r"<!-- PROGRESS:START -->.*?<!-- PROGRESS:END -->",
        f"<!-- PROGRESS:START -->\n{block}\n<!-- PROGRESS:END -->",
        text, flags=re.S,
    )
    P.write_text(text, encoding="utf-8")
    print(block)


if __name__ == "__main__":
    main()
