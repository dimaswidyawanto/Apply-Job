"""Uji skrip simpan: harus pulih dari sisa rebase dan tidak melacak pantau.log."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

AKAR = Path(__file__).resolve().parents[1]

alasan_lewati = None
if os.name == "nt":
    alasan_lewati = "skrip .sh tidak dijalankan di Windows"
elif shutil.which("bash") is None or shutil.which("git") is None:
    alasan_lewati = "butuh bash dan git"

pytestmark = pytest.mark.skipif(bool(alasan_lewati), reason=alasan_lewati or "")


def _git(folder, *args, cek=True):
    return subprocess.run(
        ["git", *args], cwd=folder, check=cek, capture_output=True, text=True,
    )


def _siapkan(tmp_path):
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    kerja = tmp_path / "kerja"
    _git(tmp_path, "clone", "-q", str(remote), str(kerja))
    _git(kerja, "config", "user.email", "uji@contoh.id")
    _git(kerja, "config", "user.name", "Uji")
    for nama in ("simpan.sh", ".gitignore"):
        shutil.copy(AKAR / nama, kerja / nama)
    (kerja / "simpan.sh").chmod(0o755)
    (kerja / "awal.txt").write_text("a\n", encoding="utf-8")
    _git(kerja, "add", "-A")
    _git(kerja, "commit", "-qm", "awal")
    _git(kerja, "push", "-q", "-u", "origin", "main")
    return kerja


def test_pulih_dari_sisa_rebase_dan_log_tidak_terlacak(tmp_path):
    kerja = _siapkan(tmp_path)

    # Kondisi yang dulu menghentikan simpan.bat di PC pengguna:
    # pantau.log ikut ter-commit, dan ada sisa folder .git/rebase-merge.
    (kerja / "pantau.log").write_text("baris log\n", encoding="utf-8")
    _git(kerja, "add", "-f", "pantau.log")
    _git(kerja, "commit", "-qm", "log ikut terlacak")
    (kerja / ".git" / "rebase-merge").mkdir()
    (kerja / ".git" / "rebase-merge" / "head-name").write_text("refs/heads/main\n")

    hasil = subprocess.run(
        ["./simpan.sh", "Uji pemulihan"], cwd=kerja,
        capture_output=True, text=True, timeout=120,
    )

    assert hasil.returncode == 0, hasil.stdout + hasil.stderr
    assert "Membersihkan sisa" in hasil.stdout
    assert not (kerja / ".git" / "rebase-merge").exists()
    assert _git(kerja, "ls-files", "pantau.log").stdout.strip() == ""
    assert (kerja / "pantau.log").exists(), "berkas aslinya tidak boleh dihapus"
    assert _git(kerja, "rev-list", "--count", "@{u}..HEAD").stdout.strip() == "0"


def test_menggabungkan_perubahan_dari_klon_lain(tmp_path):
    kerja = _siapkan(tmp_path)

    lain = tmp_path / "lain"
    _git(tmp_path, "clone", "-q", str(tmp_path / "remote.git"), str(lain))
    _git(lain, "config", "user.email", "lain@contoh.id")
    _git(lain, "config", "user.name", "Lain")
    (lain / "dari_lain.txt").write_text("b\n", encoding="utf-8")
    _git(lain, "add", "-A")
    _git(lain, "commit", "-qm", "dari klon lain")
    _git(lain, "push", "-q", "origin", "main")

    (kerja / "dari_sini.txt").write_text("c\n", encoding="utf-8")
    _git(kerja, "add", "-A")
    _git(kerja, "commit", "-qm", "dari klon ini")

    hasil = subprocess.run(
        ["./simpan.sh", "Uji gabung"], cwd=kerja,
        capture_output=True, text=True, timeout=120,
    )

    assert hasil.returncode == 0, hasil.stdout + hasil.stderr
    assert _git(kerja, "rev-list", "--count", "@{u}..HEAD").stdout.strip() == "0"
    assert (kerja / "dari_lain.txt").exists()
    assert (kerja / "dari_sini.txt").exists()
