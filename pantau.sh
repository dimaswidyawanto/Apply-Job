#!/usr/bin/env bash
# Pantau folder ini dan kirim perubahan ke GitHub secara otomatis.
# Contoh: ./pantau.sh        (periksa tiap 60 detik)
#         ./pantau.sh 30     (periksa tiap 30 detik)
# Hentikan dengan Ctrl+C. File .env, *.db, dan debug/ tidak ikut terkirim.
set -uo pipefail
cd "$(dirname "$0")"

JEDA="${1:-60}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "[GAGAL] Folder ini bukan repo Git."
    exit 1
fi

CABANG="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "-")"
echo "Memantau perubahan di $(pwd)"
echo "Cabang: $CABANG"
echo "Selang pemeriksaan: $JEDA detik. Tekan Ctrl+C untuk berhenti."
echo

while true; do
    ADA=0
    [ -n "$(git status --porcelain)" ] && ADA=1

    # Commit yang belum terkirim (mis. push gagal karena internet putus).
    BELUM="$(git rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)"
    [ "${BELUM:-0}" != "0" ] && ADA=1

    if [ "$ADA" = "1" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Perubahan terdeteksi, mengirim..."
        ./simpan.sh || echo "[peringatan] pengiriman gagal, dicoba lagi nanti"
        echo
    fi
    sleep "$JEDA"
done
