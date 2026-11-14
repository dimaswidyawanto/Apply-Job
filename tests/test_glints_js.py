"""Jalankan pemeriksaan skrip pembaca kartu Glints (tests/glints_kartu_js.js).

Butuh Node.js + jsdom. Bila tidak tersedia (umumnya di mesin pengguna),
test ini dilewati tanpa menggagalkan suite.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

SKRIP = Path(__file__).with_name("glints_kartu_js.js")


@pytest.mark.skipif(shutil.which("node") is None, reason="node tidak tersedia")
def test_skrip_pembaca_kartu_glints():
    try:
        cek = subprocess.run(
            ["node", "-e", "require('jsdom')"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pytest.skip("node tidak bisa dijalankan")

    if cek.returncode != 0:
        pytest.skip("jsdom belum terpasang (npm install jsdom)")

    hasil = subprocess.run(
        ["node", str(SKRIP)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(SKRIP.parent),
        check=False,
    )

    assert hasil.returncode == 0, hasil.stdout + hasil.stderr
