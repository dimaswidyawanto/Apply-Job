"""Formulir lamaran di dalam iframe (Indeed Apply / smartapply).

Latar belakang: sesi 12 Nov 2026 mencatat Indeed 381 lowongan, 297 disaring
filter, 84 "perlu manual", dan **0 terkirim**. Salah satu penyebab yang bisa
dipastikan dari kode: Indeed Apply menaruh formulirnya di dalam iframe
(`smartapply.indeed.com`), sedangkan alur lamaran hanya mencari tombol dan
isian di dokumen utama. Tanpa masuk ke iframe, alur tidak pernah menemukan
tombol "Lanjutkan"/"Kirim lamaran".

Tes di sini memakai driver tiruan: hanya membuktikan logika masuk/keluar
iframe, bukan perilaku situs sungguhan.
"""

import auto_apply
import indeed


class Elemen:
    def __init__(self, src="", tampil=True):
        self.src = src
        self.tampil = tampil

    def is_displayed(self):
        return self.tampil

    def get_attribute(self, nama):
        return self.src if nama == "src" else ""

    def click(self):
        return None


class SwitchTo:
    def __init__(self):
        self.kerangka = None
        self.jumlah_default = 0

    def frame(self, elemen):
        if "gagal" in (getattr(elemen, "src", "") or ""):
            raise RuntimeError("no such frame")
        self.kerangka = elemen

    def default_content(self):
        self.kerangka = None
        self.jumlah_default += 1


class Driver:
    def __init__(self, peta=None):
        self.peta = peta or {}
        self.switch_to = SwitchTo()
        self.current_url = "https://id.indeed.com/viewjob?jk=abc123"

    def find_elements(self, by, selector):
        return list(self.peta.get(selector, []))

    def execute_script(self, *argumen):
        return None

    def get(self, url):
        self.current_url = url


def _applier(kls, peta, timeout=0.05):
    applier = kls(Driver(peta))
    applier.kerangka_timeout = timeout
    return applier


# --------------------------------------------------------- JobStreet tetap ---
def test_jobstreet_tidak_mencari_kerangka():
    applier = _applier(auto_apply.AutoApplier, {})

    assert applier.kerangka_lamaran_selectors == ()
    assert applier._masuk_kerangka_lamaran() == ""
    assert applier.di_kerangka is False
    assert applier.driver.switch_to.kerangka is None


# ------------------------------------------------------------- Indeed Apply ---
def test_masuk_kerangka_smartapply():
    kerangka = Elemen("https://smartapply.indeed.com/beta/indeedapply/form/1")
    applier = _applier(
        indeed.IndeedApplier,
        {"iframe[id*='indeedapply']": [kerangka]},
    )

    assert applier._masuk_kerangka_lamaran() == ""
    assert applier.di_kerangka is True
    assert applier.driver.switch_to.kerangka is kerangka


def test_kerangka_tersembunyi_dilewati():
    kerangka = Elemen("https://smartapply.indeed.com/x", tampil=False)
    applier = _applier(
        indeed.IndeedApplier,
        {"iframe[id*='indeedapply']": [kerangka]},
    )

    assert applier._masuk_kerangka_lamaran() == ""
    assert applier.di_kerangka is False


def test_kerangka_situs_lain_tidak_dimasuki():
    kerangka = Elemen("https://forms.gle/contoh")
    applier = _applier(
        indeed.IndeedApplier,
        {"iframe[id*='indeedapply']": [kerangka]},
    )

    assert applier._masuk_kerangka_lamaran() == ""
    assert applier.di_kerangka is False


def test_kerangka_gagal_dibuka_memberi_alasan():
    applier = _applier(
        indeed.IndeedApplier,
        {"iframe[id*='indeedapply']": [Elemen("https://smartapply.indeed.com/gagal")]},
    )

    alasan = applier._masuk_kerangka_lamaran()

    assert "iframe" in alasan
    assert applier.di_kerangka is False


def test_tidak_ada_kerangka_berarti_alur_lama():
    applier = _applier(indeed.IndeedApplier, {})

    assert applier._masuk_kerangka_lamaran() == ""
    assert applier.di_kerangka is False


# ---------------------------------------------------------------- keluar ------
def test_keluar_kerangka_selalu_kembali_ke_dokumen_utama():
    applier = _applier(indeed.IndeedApplier, {})
    applier.di_kerangka = True

    applier._keluar_kerangka()

    assert applier.di_kerangka is False
    assert applier.driver.switch_to.jumlah_default == 1


def test_keluar_kerangka_tetap_aman_tanpa_kerangka():
    applier = _applier(auto_apply.AutoApplier, {})

    applier._keluar_kerangka()

    assert applier.driver.switch_to.jumlah_default == 1


# ------------------------------------------------------- penyaring alamat ---
def test_penyaring_alamat_kerangka():
    applier = _applier(indeed.IndeedApplier, {})

    assert applier._kerangka_diizinkan("https://smartapply.indeed.com/a")
    assert applier._kerangka_diizinkan("")
    assert not applier._kerangka_diizinkan("https://forms.gle/a")

    jobstreet = _applier(auto_apply.AutoApplier, {})
    assert jobstreet._kerangka_diizinkan("https://contoh.test/a")


def test_alur_memanggil_keluar_kerangka_sebelum_membuka_lowongan(monkeypatch):
    applier = _applier(indeed.IndeedApplier, {})
    urutan = []

    def keluar():
        urutan.append("keluar")

    def buka(url):
        urutan.append("buka")
        raise RuntimeError("berhenti di sini")

    monkeypatch.setattr(applier, "_keluar_kerangka", keluar)
    monkeypatch.setattr(applier.driver, "get", buka)

    applier._apply_alur({"url": "https://id.indeed.com/viewjob?jk=abc"})

    assert urutan[:2] == ["keluar", "buka"]
