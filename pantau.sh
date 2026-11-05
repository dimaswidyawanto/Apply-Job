#!/usr/bin/env bash
# Pantau folder ini: kirim perubahan ke GitHub DAN tarik pembaruan baru,
# keduanya otomatis.
# Contoh: ./pantau.sh        (periksa tiap 60 detik)
#         ./pantau.sh 30     (periksa tiap 30 detik)
# Hentikan dengan Ctrl+C. File .env, *.db, *.log, dan debug/ tidak ikut terkirim.
set -uo pipefail
cd "$(dirname "$0")"

JEDA="${1:-60}"
REMOTE_ARENA="${ARENA_REMOTE:-arena}"
CABANG_ARENA="${ARENA_CABANG:-arena/4ab2b9fa-dimastes}"
URL_ARENA="${ARENA_URL:-https://github.com/dimasw1997/dimastes.git}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "[GAGAL] Folder ini bukan repo Git."
    exit 1
fi

CABANG="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "-")"
echo "Memantau perubahan di $(pwd)"
echo "Cabang: $CABANG"
echo "Selang pemeriksaan: $JEDA detik. Tekan Ctrl+C untuk berhenti."
echo "Kirim otomatis + tarik pembaruan otomatis (saat tidak ada perubahan lokal)."
echo

while true; do
    # Jejak hidup: berkas ini diperbarui tiap putaran.
    date '+%Y-%m-%d %H:%M:%S' > .pantau-terakhir

    ADA=0
    # Berkas jejak hidup pemantau tidak dihitung sebagai perubahan.
    PERUBAHAN="$(git status --porcelain | grep -v '\.pantau-terakhir' || true)"
    [ -n "$PERUBAHAN" ] && ADA=1

    # Commit yang belum terkirim (mis. push gagal karena internet putus).
    BELUM="$(git rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)"
    [ "${BELUM:-0}" != "0" ] && ADA=1

    if [ "$ADA" = "1" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Perubahan terdeteksi, mengirim..."
        ./simpan.sh || echo "[peringatan] pengiriman gagal, dicoba lagi nanti"
        echo
    else
        # --- Tarik pembaruan: hanya saat tidak ada perubahan lokal,
        #     supaya berkas yang sedang Anda sunting tidak tertimpa. ---
        git remote get-url "$REMOTE_ARENA" >/dev/null 2>&1 \
            || git remote add "$REMOTE_ARENA" "$URL_ARENA" >/dev/null 2>&1

        git fetch --quiet origin >/dev/null 2>&1 || true
        git fetch --quiet "$REMOTE_ARENA" >/dev/null 2>&1 || true

        BARU_ORIGIN="$(git rev-list --count 'HEAD..@{u}' 2>/dev/null || echo 0)"
        BARU_ARENA="$(git rev-list --count \
            "HEAD..$REMOTE_ARENA/$CABANG_ARENA" 2>/dev/null || echo 0)"

        if [ "${BARU_ORIGIN:-0}" != "0" ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Ada ${BARU_ORIGIN} commit baru di GitHub, menarik..."
            ./simpan.sh "Tarik pembaruan $(date '+%Y-%m-%d %H:%M')" \
                || echo "[peringatan] gagal menarik pembaruan"
            echo
        fi

        if [ "${BARU_ARENA:-0}" != "0" ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Ada ${BARU_ARENA} pembaruan dari repo pengembangan, menarik..."
            if ! ./tarik.sh; then
                git merge --abort >/dev/null 2>&1 || true
                echo "[peringatan] penggabungan bentrok — dilewati putaran ini"
            fi
            echo
        fi
    fi

    sleep "$JEDA"
done
