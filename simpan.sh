#!/usr/bin/env bash
# Simpan perubahan ke GitHub dengan satu perintah (macOS/Linux).
# Contoh: ./simpan.sh
#         ./simpan.sh "Perbaiki filter judul"
# Skrip ini: bersihkan sisa rebase -> git add -A -> commit -> tarik -> push.
# Aman dipakai berkali-kali: kalau tidak ada perubahan, hanya mengirim saja.
set -uo pipefail
cd "$(dirname "$0")"

PESAN="${1:-}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "[GAGAL] Folder ini bukan repo Git."
    exit 1
fi

# --- 0. Sisa rebase yang gagal sebelumnya bisa menghentikan git pull ---
for sisa in rebase-merge rebase-apply; do
    folder="$(git rev-parse --git-path "$sisa" 2>/dev/null || true)"
    if [ -n "$folder" ] && [ -d "$folder" ]; then
        echo "[1/5] Membersihkan sisa '$sisa' dari percobaan sebelumnya..."
        git rebase --abort >/dev/null 2>&1 || true
        [ -d "$folder" ] && rm -rf "$folder"
    fi
done

CABANG="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
CABANG="${CABANG:-main}"
echo "[2/5] Cabang: $CABANG"

git add -A

# Berkas catatan pemantau tidak perlu ikut ke GitHub.
if git ls-files --error-unmatch pantau.log >/dev/null 2>&1; then
    git rm --cached -q pantau.log
    echo "      pantau.log dikeluarkan dari daftar berkas Git."
fi

if ! git diff --cached --quiet; then
    if [ -z "$PESAN" ]; then
        PESAN="Update otomatis $(date '+%Y-%m-%d %H:%M')"
    fi
    echo "[3/5] Commit: $PESAN"
    if ! git commit -m "$PESAN"; then
        echo "[GAGAL] Commit ditolak. Periksa pesan di atas."
        exit 1
    fi
else
    echo "[3/5] Tidak ada perubahan baru yang perlu di-commit."
fi

if git ls-remote --exit-code --heads origin "$CABANG" >/dev/null 2>&1; then
    echo "[4/5] Menarik perubahan terbaru dari GitHub..."
    # Gabung (bukan rebase): riwayat berisi commit gabungan dari tarik.sh,
    # dan rebase pada commit gabungan sering gagal.
    if ! git pull --no-rebase --autostash origin "$CABANG"; then
        echo "[GAGAL] Penggabungan bentrok."
        echo "  1. Ketik:  git status   lalu periksa berkas yang bertanda konflik."
        echo "  2. Perbaiki, lalu:  git add -A && git commit"
        echo "  3. Jalankan lagi:  ./simpan.sh"
        exit 1
    fi
else
    echo "[4/5] Cabang belum ada di GitHub, langsung dikirim."
fi

echo "[5/5] Mengirim ke GitHub..."
if ! git push origin "$CABANG"; then
    echo "[GAGAL] Push ditolak. Kemungkinan login GitHub belum tersimpan."
    echo "  Jalankan sekali:  git push origin $CABANG"
    echo "  lalu ikuti login (browser/token). Setelah sekali berhasil,"
    echo "  kredensial tersimpan dan ./simpan.sh berikutnya tidak bertanya lagi."
    exit 1
fi

echo
echo "Selesai. Perubahan sudah ada di GitHub (cabang $CABANG)."
