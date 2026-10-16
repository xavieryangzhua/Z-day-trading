#!/bin/zsh
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo '请先按 README 安装 Python 环境。'
  exit 1
fi
exec .venv/bin/python -m streamlit run app.py
