"""Cloudflare / captcha diperlakukan sebagai kondisi "butuh manusia".

Aturan (master prompt pasal 16): dinding verifikasi TIDAK dilewati. Yang diuji
di sini: deteksi, status tersimpan, kuota tidak terpakai, tidak ada pengulangan
tanpa batas, dan situs berhenti setelah beberapa kegagalan beruntun.
"""

import pytest

import blokir
import indeed as indeed_module
from auto_apply import ApplyResult
from config import config
from tests.test_indeed import KARTU_MENTAH, BotPalsu, _siapkan_sesi, rapikan_kartu

KARTU_KEDUA = dict(
    KARTU_MENTAH,
    url="https://id.indeed.com/viewjob?jk=def456789abc",
    kunci="def456789abc",
)
KARTU_KETIGA = dict(
    KARTU_MENTAH,
    url="https://id.indeed.com/viewjob?jk=ghi789abc123",
    kunci="ghi789abc123",
)
KARTU_KEEMPAT = dict(
    KARTU_MENTAH,
    url="https://id.indeed.com/viewjob?jk=jkl012abc345",
    kunci="jkl012abc345",
)


# ------------------------------------------------------------- deteksi ----
def test_kena_blokir_mengenali_halaman_verifikasi():
    for teks in (
        "Halaman Indeed diblokir Cloudflare",
        "Just a moment...",
        "Tunggu sebentar",
        "Diperlukan verifikasi tambahan (ID Ray: 8f2…)",
        "Please verify you are human",
        "unusual traffic from your network",
    ):
        assert blokir.kena_blokir(teks) is True, teks


def test_kena_blokir_tidak_menuduh_galat_biasa():
    for teks in (
        "",
        "Tombol Lamar tidak ditemukan",
        "timeout menunggu elemen",
        "Formulir meminta isian yang belum bisa dijawab otomatis",
    ):
        assert blokir.kena_blokir(teks) is False, teks


# ------------------------------------------------------------ penghitung ---
def test_penghitung_berhenti_pada_batas():
    penghitung = blokir.PenghitungBlokir(batas=3)

    assert penghitung.catat(True) is False
    assert penghitung.catat(True) is False
    assert penghitung.catat(True) is True


def test_penghitung_reset_oleh_hasil_biasa():
    penghitung = blokir.PenghitungBlokir(batas=3)

    penghitung.catat(True)
    penghitung.catat(True)
    assert penghitung.catat(False) is False
    assert penghitung.jumlah == 0

    assert penghitung.catat(True) is False
    assert penghitung.catat(True) is False
    assert penghitung.catat(True) is True


# ------------------------------------------------- status & sesi Indeed ---
class BotDiblokir(BotPalsu):
    """Bot tiruan yang selalu tertahan dinding verifikasi."""

    def __init__(self, kartu=None):
        super().__init__(kartu)
        self.dicatat = []

    def lamar(self, job):
        self.dilamar.append(job["job_id"])
        return ApplyResult(
            False, "error", "Halaman Indeed diblokir Cloudflare (Just a moment...)"
        )


def _siapkan_blokir(monkeypatch):
    db, notifier, bot = _siapkan_sesi(monkeypatch)
    bot_baru = BotDiblokir(
        [
            rapikan_kartu(kartu)
            for kartu in (KARTU_MENTAH, KARTU_KEDUA, KARTU_KETIGA, KARTU_KEEMPAT)
        ]
    )
    monkeypatch.setattr(indeed_module, "IndeedBot", lambda: bot_baru)
    monkeypatch.setattr(
        indeed_module,
        "kumpulkan_lowongan",
        lambda bot_, kata, halaman, lokasi=None: [dict(job) for job in bot_.kartu],
    )
    return db, notifier, bot_baru


def test_sesi_indeed_berhenti_setelah_tiga_kali_tertahan(monkeypatch):
    _, notifier, bot = _siapkan_blokir(monkeypatch)

    laporan = indeed_module.jalankan_indeed(
        max_pages=1, keywords=["inventory"], batas=10
    )

    # Tiga percobaan, bukan empat: kandidat keempat tidak ikut hangus.
    assert len(bot.dilamar) == blokir.BATAS_BLOKIR_BERHENTI
    assert laporan["perlu_manusia"] == 1
    assert laporan["dilamar"] == 0
    assert notifier.galat, "laporan butuh tindakan manusia harus dikirim"


def test_blokir_tidak_dihitung_sebagai_lamaran_terkirim(monkeypatch):
    db, _, _ = _siapkan_blokir(monkeypatch)

    laporan = indeed_module.jalankan_indeed(
        max_pages=1, keywords=["inventory"], batas=10
    )

    assert laporan["dilamar"] == 0
    assert laporan["gagal"] == blokir.BATAS_BLOKIR_BERHENTI
    # Tidak ada satu pun yang dicatat "applied".
    assert all(status != "applied" for _, status in db.dicatat)


def test_status_lamaran_tertahan_adalah_requires_human(monkeypatch):
    """`lamar()` mencatat requires_human, bukan error biasa."""
    dicatat = []

    monkeypatch.setattr(
        indeed_module,
        "db",
        type(
            "Db",
            (),
            {
                "is_already_applied": staticmethod(lambda *_: False),
                "record_application": staticmethod(
                    lambda job_id, status="applied", notes="": dicatat.append(
                        (job_id, status)
                    )
                ),
            },
        )(),
    )
    monkeypatch.setattr(
        indeed_module,
        "IndeedApplier",
        lambda driver=None: type(
            "Applier",
            (),
            {
                "apply": staticmethod(
                    lambda job: ApplyResult(
                        False, "error", "Just a moment... (Cloudflare)"
                    )
                )
            },
        )(),
    )
    monkeypatch.setattr(config, "auto_apply", True, raising=False)

    Indeed_hasil = indeed_module.IndeedBot().lamar(rapikan_kartu(KARTU_MENTAH))

    assert Indeed_hasil.applied is False
    assert dicatat and dicatat[0][1] == blokir.STATUS_PERLU_MANUSIA


def test_status_requires_human_bukan_status_kuota():
    from database import APPLIED_STATUSES, QUOTA_STATUSES

    assert blokir.STATUS_PERLU_MANUSIA not in APPLIED_STATUSES
    assert blokir.STATUS_PERLU_MANUSIA not in QUOTA_STATUSES


@pytest.mark.parametrize(
    "alasan",
    [
        "Halaman Indeed diblokir Cloudflare",
        "Terjadi captcha saat membuka lamaran",
    ],
)
def test_alasan_blokir_dikenali_pada_hasil_lamar(alasan):
    assert blokir.kena_blokir(alasan) is True
