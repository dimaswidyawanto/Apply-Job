"""Uji pemantau otomatis: commit yang belum ter-push harus ikut dikirim.

Berbeda dari perubahan file biasa: setelah push gagal (mis. internet putus),
pohon kerja sudah bersih, jadi pemeriksaan `git status` saja tidak cukup.
"""

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest

AKAR = Path(__file__).resolve().parents[1]

alasan_lewati = None
if os.name == "nt":
    alasan_lewati = "skrip .sh tidak dijalankan di Windows"
elif shutil.which("bash") is None or shutil.which("git") is None:
    alasan_lewati = "butuh bash dan git"

pytestmark = pytest.mark.skipif(bool(alasan_lewati), reason=alasan_lewati or "")


def _git(folder, *args):
    return subprocess.run(
        ["git", *args], cwd=folder, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def _siapkan(tmp_path):
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    kerja = tmp_path / "kerja"
    _git(tmp_path, "clone", "-q", str(remote), str(kerja))
    _git(kerja, "config", "user.email", "uji@contoh.id")
    _git(kerja, "config", "user.name", "Uji")
    for nama in ("simpan.sh", "pantau.sh"):
        shutil.copy(AKAR / nama, kerja / nama)
        (kerja / nama).chmod(0o755)
    (kerja / "awal.txt").write_text("a\n", encoding="utf-8")
    _git(kerja, "add", "-A")
    _git(kerja, "commit", "-qm", "awal")
    _git(kerja, "push", "-q", "-u", "origin", "main")
    return remote, kerja


def _jalankan_pantau(kerja, detik=2, tunggu=7):
    proses = subprocess.Popen(
        ["./pantau.sh", str(detik)], cwd=kerja,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    time.sleep(tunggu)
    proses.send_signal(signal.SIGTERM)
    try:
        keluaran, _ = proses.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proses.kill()
        keluaran, _ = proses.communicate()
    return keluaran


def test_commit_belum_terkirim_ikut_dikirim(tmp_path):
    remote, kerja = _siapkan(tmp_path)

    # Pohon bersih: tidak boleh ada pengiriman.
    _git(kerja, "commit", "-q", "--allow-empty", "-m", "kosong")
    _git(kerja, "push", "-q", "origin", "main")
    keluaran = _jalankan_pantau(kerja, tunggu=4)
    assert "Perubahan terdeteksi" not in keluaran

    # Commit lokal yang gagal ter-push: pohon bersih, tapi tertinggal 1 commit.
    (kerja / "baru.txt").write_text("c\n", encoding="utf-8")
    _git(kerja, "add", "-A")
    _git(kerja, "commit", "-qm", "gagal ter-push")
    assert _git(kerja, "rev-list", "--count", "@{u}..HEAD") == "1"

    keluaran = _jalankan_pantau(kerja)
    assert "Perubahan terdeteksi" in keluaran
    assert _git(kerja, "rev-list", "--count", "@{u}..HEAD") == "0"
    isi = subprocess.run(
        ["git", "--git-dir", str(remote), "show", "main:baru.txt"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert isi.strip() == "c"
