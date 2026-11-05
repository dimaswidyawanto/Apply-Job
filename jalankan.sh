#!/usr/bin/env bash
# Skrip bantu macOS/Linux: siapkan .venv, pasang dependensi (sekali saja),
# lalu jalankan CLI.
# Contoh: ./jalankan.sh run
#         ./jalankan.sh config
#   PAKSA_PASANG=1  -> pasang ulang dependensi
#   LEWATI_PASANG=1 -> jangan memasang dependensi
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo "[1/3] Membuat virtual environment..."
    python3 -m venv .venv
fi

PERLU=0
if [ "${PAKSA_PASANG:-0}" = "1" ]; then
    PERLU=1
elif [ "${LEWATI_PASANG:-0}" = "1" ]; then
    PERLU=0
elif [ ! -f ".venv/.deps-terpasang" ]; then
    PERLU=1
elif ! cmp -s requirements.txt ".venv/.deps-terpasang"; then
    PERLU=1
fi

if [ "$PERLU" = "1" ]; then
    echo "[2/3] Memasang dependensi (sekali saja, mohon tunggu)..."
    .venv/bin/python -m pip install --quiet --upgrade pip
    .venv/bin/python -m pip install --quiet -r requirements.txt
    cp requirements.txt .venv/.deps-terpasang
else
    echo "[2/3] Dependensi sudah terpasang, dilewati."
fi

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    echo "File .env dibuat dari .env.example. Sesuaikan dulu bila perlu."
fi

echo "[3/3] Menjalankan program..."
echo
exec ".venv/bin/python" cli.py "$@"
