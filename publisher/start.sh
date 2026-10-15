#!/bin/bash
# Mac: 이 파일을 더블클릭. (처음 한 번 "열 수 없음"이 뜨면 우클릭 → 열기)
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3가 없습니다. https://www.python.org/downloads/ 에서 설치한 뒤 다시 실행하세요."
  read -n 1 -s -r -p "아무 키나 누르면 닫힙니다"; exit 1
fi
if [ ! -d .venv ]; then
  echo "처음 실행: 필요한 부품을 설치합니다 (1~2분)…"
  python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt || { echo "설치 실패"; read -n 1 -s -r; exit 1; }
fi
.venv/bin/python app.py
