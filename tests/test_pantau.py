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
    for nama in ("simpan.sh", "pantau.sh", "tarik.sh", ".gitignore"):
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


# ----------------------------------------------------------------------
# Tarik pembaruan otomatis
# ----------------------------------------------------------------------
def test_menarik_pembaruan_dari_repo_pengembangan(tmp_path, monkeypatch):
    """Commit baru di repo pengembangan masuk otomatis, tanpa perintah manual."""
    remote, kerja = _siapkan(tmp_path)

    asal = tmp_path / "asal.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(asal))

    dev = tmp_path / "dev"
    _git(tmp_path, "clone", "-q", str(asal), str(dev))
    _git(dev, "config", "user.email", "dev@contoh.id")
    _git(dev, "config", "user.name", "Dev")
    _git(kerja, "remote", "add", "arena", str(asal))
    (dev / "fitur.txt").write_text("v1\n", encoding="utf-8")
    _git(dev, "add", "-A")
    _git(dev, "commit", "-qm", "v1")
    _git(dev, "push", "-q", "origin", "main")

    # Samakan riwayat: kerja ikut memuat commit pengembangan.
    _git(kerja, "fetch", "-q", "arena")
    _git(kerja, "merge", "-q", "--allow-unrelated-histories", "arena/main")
    _git(kerja, "push", "-q", "origin", "main")

    monkeypatch.setenv("ARENA_REMOTE", "arena")
    monkeypatch.setenv("ARENA_CABANG", "main")
    monkeypatch.setenv("ARENA_URL", str(asal))

    # Pengembangan menambah commit baru.
    (dev / "fitur.txt").write_text("v1\nv2\n", encoding="utf-8")
    _git(dev, "commit", "-qam", "v2")
    _git(dev, "push", "-q", "origin", "main")

    keluaran = _jalankan_pantau(kerja)

    assert "menarik" in keluaran.lower()
    assert (kerja / "fitur.txt").read_text(encoding="utf-8") == "v1\nv2\n"
    # Setelah ditarik, perubahannya juga dikirim ke origin pada putaran berikut.
    assert _git(kerja, "rev-list", "--count", "@{u}..HEAD") == "0"


def test_menarik_perubahan_dari_github(tmp_path, monkeypatch):
    """Perubahan yang dibuat di GitHub (klon lain) ikut masuk otomatis."""
    remote, kerja = _siapkan(tmp_path)
    monkeypatch.setenv("ARENA_URL", str(tmp_path / "tidak-ada.git"))

    lain = tmp_path / "lain"
    _git(tmp_path, "clone", "-q", str(remote), str(lain))
    _git(lain, "config", "user.email", "lain@contoh.id")
    _git(lain, "config", "user.name", "Lain")
    (lain / "dari_github.txt").write_text("x\n", encoding="utf-8")
    _git(lain, "add", "-A")
    _git(lain, "commit", "-qm", "dari klon lain")
    _git(lain, "push", "-q", "origin", "main")

    keluaran = _jalankan_pantau(kerja)

    assert "commit baru di GitHub" in keluaran
    assert (kerja / "dari_github.txt").exists()
    # Jejak hidup: berkas ini menandakan pemantau benar-benar berputar.
    jejak = kerja / ".pantau-terakhir"
    assert jejak.exists() and jejak.read_text(encoding="utf-8").strip()


def test_tidak_menarik_saat_ada_perubahan_lokal(tmp_path, monkeypatch):
    """Berkas yang sedang disunting tidak boleh tertimpa proses tarik."""
    remote, kerja = _siapkan(tmp_path)
    monkeypatch.setenv("ARENA_URL", str(tmp_path / "tidak-ada.git"))

    lain = tmp_path / "lain"
    _git(tmp_path, "clone", "-q", str(remote), str(lain))
    _git(lain, "config", "user.email", "lain@contoh.id")
    _git(lain, "config", "user.name", "Lain")
    (lain / "dari_github.txt").write_text("x\n", encoding="utf-8")
    _git(lain, "add", "-A")
    _git(lain, "commit", "-qm", "dari klon lain")
    _git(lain, "push", "-q", "origin", "main")

    # Ada berkas lokal yang belum disimpan ke Git.
    (kerja / "sedang_disunting.txt").write_text("draf\n", encoding="utf-8")

    keluaran = _jalankan_pantau(kerja)

    # Putaran ini mengirim perubahan lokal dulu; penarikan menunggu.
    assert "Perubahan terdeteksi" in keluaran
    assert (kerja / "sedang_disunting.txt").read_text(encoding="utf-8") == "draf\n"
