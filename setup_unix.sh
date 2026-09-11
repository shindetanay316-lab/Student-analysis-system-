#!/usr/bin/env sh
set -eu

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if [ ! -f .env ]; then
    cp .env.example .env
fi

python seed.py
printf '\nSetup complete. Edit .env, then run: .venv/bin/python app.py\n'
