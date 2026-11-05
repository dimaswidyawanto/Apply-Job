#!/usr/bin/env bash
# Tarik pembaruan dari repo pengembangan (akun dimasw1997) ke repo Anda.
# Contoh: ./tarik.sh
set -uo pipefail
cd "$(dirname "$0")"

ARENA_REMOTE="${ARENA_REMOTE:-arena}"
ARENA_CABANG="${ARENA_CABANG:-arena/4ab2b9fa-dimastes}"
ARENA_URL="${ARENA_URL:-https://github.com/dimasw1997/dimastes.git}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "[GAGAL] Folder ini bukan repo Git."
    exit 1
fi

if ! git remote get-url "$ARENA_REMOTE" >/dev/null 2>&1; then
    echo "Remote '$ARENA_REMOTE' belum ada, menambahkan..."
    git remote add "$ARENA_REMOTE" "$ARENA_URL"
fi

echo "[1/2] Mengambil pembaruan dari $ARENA_REMOTE ($ARENA_URL)..."
if ! git fetch "$ARENA_REMOTE"; then
    echo "[GAGAL] Tidak bisa mengambil pembaruan. Periksa koneksi internet."
    exit 1
fi

# Bereskan sisa penggabungan yang gagal sebelumnya.
if [ -f ".git/MERGE_HEAD" ]; then
    echo "[info] Membatalkan penggabungan sebelumnya yang belum selesai..."
    git merge --abort || true
fi

# Simpan perubahan lokal agar penggabungan tidak ditolak
# ("Your local changes ... would be overwritten by merge").
DISIMPAN=""
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "[info] Menyimpan perubahan lokal sementara (git stash)..."
    if git stash push -m "tarik-otomatis" >/dev/null 2>&1; then
        DISIMPAN="1"
    fi
fi

echo "[2/2] Menggabungkan $ARENA_REMOTE/$ARENA_CABANG ke cabang ini..."
if ! git merge --no-edit "$ARENA_REMOTE/$ARENA_CABANG"; then
    # Riwayat berbeda (repo baru dibuat ulang) -> coba gabungkan tetap.
    git merge --no-edit --allow-unrelated-histories \
        "$ARENA_REMOTE/$ARENA_CABANG"
fi

if [ -n "$(git ls-files --unmerged)" ]; then
    echo "[GAGAL] Penggabungan bentrok. Selesaikan dengan:"
    echo "  git status"
    echo "  ... perbaiki file yang bertanda konflik ..."
    echo "  git add -A && git commit"
    if [ -n "$DISIMPAN" ]; then
        echo "Perubahan lokal Anda masih tersimpan: git stash pop"
    fi
    exit 1
fi

if [ -n "$DISIMPAN" ]; then
    if git stash pop >/dev/null 2>&1; then
        echo "[info] Perubahan lokal dikembalikan."
    else
        echo "[PERHATIAN] Perubahan lokal belum bisa dikembalikan otomatis."
        echo "  Perubahan itu aman di git stash. Kembalikan dengan: git stash pop"
    fi
fi

echo
echo "Selesai. Kode sudah yang terbaru. Kirim balik ke repo Anda dengan: ./simpan.sh"
