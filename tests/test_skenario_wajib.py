"""15 skenario uji wajib dari master prompt, satu tes per skenario.

Setiap tes memakai database sementara dan konfigurasi yang dipasang eksplisit,
jadi hasilnya sama di komputer mana pun dan tidak menyentuh data asli.

Daftar skenario (pasal 14):
 1. 200 lowongan diproses tanpa lambat/gagal
 2. duplikat lintas sumber dibuang
 3. lowongan tanpa logo ditolak (Indeed dikecualikan)
 4. gaji Rp4,0 jt ditolak, Rp4,5 jt lolos (rentang 4,0-6,0 jt tidak lolos)
 5. lowongan tanpa info gaji tetap boleh dilamar
 6. lowongan tidak relevan CV tersaring
 7. batas 50 lamaran per hari dihormati
 8. kuota habis -> berhenti, bukan melebihi batas
 9. aplikasi dimatikan saat berjalan -> berhenti rapi
10. internet putus -> dicatat gagal, sesi tidak mati
11. resume setelah aplikasi ditutup -> lanjut dari progres terakhir
12. pertanyaan formulir berulang -> dijawab dari ingatan
13. pertanyaan bahasa berbeda -> tetap dikenali
14. status kirim tidak pasti -> REVIEW_REQUIRED, bukan "berhasil"
15. klik dua kali tidak menghasilkan lamaran ganda
"""

import pytest

import antrean
import jawaban
import job_filter as jf_modul
import kendali
import kunci
import kuota
import skor_cv
from config import config
from database import Database
from job_filter import JobFilter, dedupe_jobs


@pytest.fixture
def lingkungan(tmp_path, monkeypatch):
    """Database sementara + aturan aktif yang dipakai tes."""
    database = Database(str(tmp_path / "skenario.db"))
    monkeypatch.setattr(jf_modul, "db", database)
    monkeypatch.setattr(antrean, "db", database)
    monkeypatch.setattr(jawaban, "db", database)

    monkeypatch.setattr(config, "require_company_logo", True)
    monkeypatch.setattr(config, "min_salary", 4_500_000)
    monkeypatch.setattr(config, "require_keyword_match", False)
    monkeypatch.setattr(config, "strict_location", False)
    monkeypatch.setattr(config, "max_age_days", 0)

    return database


def lowongan(**ubah):
    job = {
        "job_id": "js-1",
        "title": "Inventory Control Staff",
        "company": "PT Contoh",
        "location": "Bandung, West Java",
        "salary": "Rp 7.000.000 per month",
        "description": "Mengelola stok gudang dan stock opname.",
        "url": "https://id.jobstreet.com/job/1",
        "date_posted": "Hari ini",
        "has_logo": True,
    }
    job.update(ubah)
    return job


# 1 ------------------------------------------------------------------------
def test_skenario_01_dua_ratus_lowongan_diproses(lingkungan):
    jobs = [
        lowongan(
            job_id=f"js-{i}",
            title=f"Inventory Control Staff {i}",
            url=f"https://id.jobstreet.com/job/{i}",
        )
        for i in range(200)
    ]

    hasil = JobFilter().rank_jobs(jobs)

    assert len(hasil) == 200
    assert all("_score" in job and "_skor_rincian" in job for job in hasil)
    skor = [job["_score"] for job in hasil]
    assert skor == sorted(skor, reverse=True)


# 2 ------------------------------------------------------------------------
def test_skenario_02_duplikat_lintas_sumber_dibuang(lingkungan):
    jobstreet = lowongan(job_id="")
    glints = lowongan(job_id="", url="https://glints.com/id/opportunities/jobs/1")
    indeed = lowongan(job_id="", url="https://id.indeed.com/viewjob?jk=1")

    unik = dedupe_jobs([jobstreet, glints, indeed])
    assert len(unik) == 1

    # Job yang sama dari sumber mana pun tidak disimpan dua kali di database.
    assert lingkungan.add_job(lowongan()) is True
    assert lingkungan.add_job(lowongan()) is False


# 3 ------------------------------------------------------------------------
def test_skenario_03_logo_wajib_kecuali_indeed(lingkungan):
    tanpa_logo = lowongan(job_id="js-2", has_logo=False)
    boleh, alasan = JobFilter().should_apply(tanpa_logo)
    assert boleh is False
    assert "logo" in alasan.lower()

    indeed = lowongan(
        job_id="ind-1", has_logo=False, logo_diabaikan=True,
        url="https://id.indeed.com/viewjob?jk=1",
    )
    boleh, alasan = JobFilter().should_apply(indeed)
    assert boleh is True, alasan


# 4 ------------------------------------------------------------------------
def test_skenario_04_gaji_empat_juta_ditolak_empat_setengah_lolos(lingkungan):
    saring = JobFilter()

    boleh, alasan = saring.should_apply(lowongan(salary="Rp 4.000.000 per month"))
    assert boleh is False and "rendah" in alasan.lower()

    # Rentang 4,0-6,0 juta: batas bawah tetap di bawah 4,5 juta -> tidak lolos.
    boleh, _ = saring.should_apply(
        lowongan(salary="Rp 4.000.000 - Rp 6.000.000 per month")
    )
    assert boleh is False

    boleh, alasan = saring.should_apply(lowongan(salary="Rp 4.500.000 per month"))
    assert boleh is True, alasan


# 5 ------------------------------------------------------------------------
def test_skenario_05_tanpa_info_gaji_tetap_boleh(lingkungan):
    saring = JobFilter()

    for teks in ("", "Tidak disebutkan", "-"):
        boleh, alasan = saring.should_apply(lowongan(salary=teks))
        assert boleh is True, f"{teks!r}: {alasan}"


# 6 ------------------------------------------------------------------------
def test_skenario_06_tidak_relevan_cv_tersaring(lingkungan, monkeypatch):
    profil = {
        "pengalaman_tahun": 4,
        "pendidikan": "S1",
        "bidang": ["inventory", "supply chain", "ppic", "warehouse"],
        "keterampilan": ["sap", "excel", "wms"],
        "jabatan": ["inventory control", "ppic"],
        "lokasi": ["bandung"],
    }
    monkeypatch.setattr(skor_cv, "aktif", lambda: True)
    monkeypatch.setattr(skor_cv, "muat_profil", lambda path="": profil)
    monkeypatch.setattr(config, "min_skor_cv", 70)

    relevan = lowongan(
        description=(
            "Mengelola stok gudang dan stock opname memakai SAP dan Excel."
        )
    )
    akuntansi = lowongan(
        job_id="js-9",
        title="Accounting Staff",
        description="Menyusun laporan keuangan dan pajak.",
        location="Jakarta",
    )

    lolos, dibuang = skor_cv.saring_minimal(
        [relevan, akuntansi], minimal=70, skor_sudah=False
    )

    assert relevan in lolos
    assert akuntansi in dibuang
    assert relevan["_skor_cv"] > akuntansi["_skor_cv"]


# 7 ------------------------------------------------------------------------
def test_skenario_07_batas_lima_puluh_per_hari():

    class Db:
        def __init__(self, n):
            self.n = n

        def get_today_apply_count(self):
            return self.n

    class Cfg:
        max_apply_per_day = 50

    kandidat = [lowongan(job_id=f"j{i}") for i in range(80)]

    assert len(kuota.potong(kandidat, Db(0), Cfg())) == 50
    assert len(kuota.potong(kandidat, Db(45), Cfg())) == 5
    assert kuota.sisa(Db(12), Cfg()) == 38


# 8 ------------------------------------------------------------------------
def test_skenario_08_kuota_habis_berhenti():

    class Db:
        def __init__(self, n):
            self.n = n

        def get_today_apply_count(self):
            return self.n

    class Cfg:
        max_apply_per_day = 50

    assert kuota.habis(Db(49), Cfg()) is False
    assert kuota.habis(Db(50), Cfg()) is True
    assert kuota.potong([lowongan()], Db(50), Cfg()) == []


# 9 ------------------------------------------------------------------------
def test_skenario_09_aplikasi_dimatikan_berhenti_rapi(tmp_path):
    # Sesi kedua tidak boleh jalan bersamaan (aplikasi/mesin lain memakai data).
    with (
        kunci.sesi_tunggal(tmp_path),
        pytest.raises(kunci.SesiBerjalan),
        kunci.sesi_tunggal(tmp_path),
    ):
        pass

    # Tombol Stop dari dashboard menghentikan sesi di antara lowongan.
    assert kendali.perintah("stop", tmp_path) is True
    with pytest.raises(kendali.Berhenti):
        kendali.periksa(tmp_path)


# 10 -----------------------------------------------------------------------
def test_skenario_10_internet_putus_dicatat_gagal(lingkungan):
    assert antrean.status_gagal("net::ERR_INTERNET_DISCONNECTED") == "failed"
    assert antrean.status_gagal("chrome not reachable") == "failed"

    lingkungan.add_job(lowongan(job_id="js-10"))
    antrean.selesai("js-10", antrean.status_gagal("ERR_INTERNET_DISCONNECTED"))

    job = lingkungan.get_job("js-10")
    assert job["status_antrean"] == "failed"

    # Kegagalan tidak menghapus riwayat; lowongan bisa diulang nanti.
    assert lingkungan.ulang_gagal() == 1
    assert lingkungan.get_job("js-10")["status_antrean"] != "failed"


# 11 -----------------------------------------------------------------------
def test_skenario_11_resume_setelah_aplikasi_ditutup(tmp_path):
    jalur = str(tmp_path / "lanjut.db")

    pertama = Database(jalur)
    pertama.add_job(lowongan(job_id="js-11"))
    pertama.add_job(lowongan(job_id="js-12", url="https://id.jobstreet.com/job/12"))
    pertama.set_status_antrean("js-11", "applied")
    pertama.record_application("js-11")

    # "Aplikasi ditutup" -> objek baru membaca database yang sama.
    kedua = Database(jalur)
    assert kedua.get_job("js-11")["status_antrean"] == "applied"

    # Yang sudah terkirim tidak dikerjakan lagi, sisanya tetap bisa dilanjutkan.
    assert kedua.is_already_applied("js-11") is True
    assert kedua.get_job("js-12")["status_antrean"] == "found"


# 12 -----------------------------------------------------------------------
def test_skenario_12_pertanyaan_berulang_diingat(lingkungan):
    assert jawaban.ingat("Nama Lengkap", "Dimas Wibowo") is True

    assert jawaban.cari("Nama Lengkap") == "Dimas Wibowo"
    # Spasi, huruf besar, dan tanda baca yang berbeda tetap pertanyaan yang sama.
    assert jawaban.cari("  nama   lengkap? ") == "Dimas Wibowo"


# 13 -----------------------------------------------------------------------
def test_skenario_13_bahasa_berbeda_tetap_dikenali(lingkungan):
    jawaban.ingat("Nama Lengkap", "Dimas Wibowo")
    jawaban.ingat("Ekspektasi Gaji", "Rp 8.000.000")

    assert jawaban.cari("Full Name") == "Dimas Wibowo"
    assert jawaban.cari("Expected Salary") == "Rp 8.000.000"

    # Berlaku dua arah: pertanyaan Inggris yang dijawab, ditanya versi Indonesia.
    jawaban.ingat("Phone Number", "08123456789")
    assert jawaban.cari("Nomor Telepon") == "08123456789"


# 14 -----------------------------------------------------------------------
def test_skenario_14_status_kirim_tidak_pasti_masuk_review(lingkungan):
    ragu = "Konfirmasi pengiriman tidak dapat dipastikan"
    assert antrean.status_untuk(ragu) == "review_required"
    assert antrean.status_untuk("Logo tidak dapat dipastikan") == "review_required"

    lingkungan.add_job(lowongan(job_id="js-14"))
    antrean.tandai_hasil("js-14", ragu)

    job = lingkungan.get_job("js-14")
    assert job["status_antrean"] == "review_required"
    assert job["alasan"] == ragu

    # Bukan dihitung sebagai lamaran terkirim.
    assert lingkungan.get_today_apply_count() == 0


# 15 -----------------------------------------------------------------------
def test_skenario_15_klik_dua_kali_tidak_dobel(lingkungan):
    lingkungan.add_job(lowongan(job_id="js-15"))

    assert antrean.klaim("js-15") is True
    lingkungan.record_application("js-15")
    lingkungan.record_application("js-15")

    # Klaim kedua ditolak karena sudah pernah terkirim.
    assert antrean.klaim("js-15") is False
    assert lingkungan.get_today_apply_count() == 1
    assert len(lingkungan.get_recent_applications()) == 1
