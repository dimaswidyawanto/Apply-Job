"""Ingatan jawaban formulir lamaran.

Aturan pemakai: **apa pun yang pernah diisi pengguna harus diingat** dan diisi
otomatis pada lamaran berikutnya. Bot hanya perlu bertanya (atau berhenti)
untuk pertanyaan yang benar-benar belum pernah dijawab.

Kunci ingatan dibuat dari teks pertanyaan yang dinormalkan, sehingga
"Manajemen Rantai Pasokan", "manajemen rantai pasokan" dan
"Manajemen  Rantai Pasokan " dianggap sama. Bila teks berubah sedikit
(tanda baca, spasi, salah ketik kecil), pencocokan mirip dipakai sebagai
cadangan.
"""

import re
from difflib import SequenceMatcher

import teks
from config import config
from database import db

# Batas kemiripan teks pertanyaan agar dianggap pertanyaan yang sama.
AMBANG_MIRIP = 0.86

# Batas kemiripan untuk pertanyaan YA/TIDAK yang kalimatnya disusun ulang
# ("do you have sales negotiation experience?" vs "do you have experience in
# sales negotiation?" bernilai 0.70 — di bawah AMBANG_MIRIP). Hanya dipakai
# untuk jawaban ya/tidak dan hanya bila pemenangnya jelas (selisih di bawah).
AMBANG_MIRIP_YA_TIDAK = 0.72
SELISIH_YA_TIDAK = 0.06

# Batas kemiripan jawaban dengan teks opsi ("No" vs "No, I don't have any").
AMBANG_OPSI = 0.80

_TANDA_BACA = re.compile(r"[^\w\s]+", re.UNICODE)

# Normalisasi teks kini tinggal di `teks.py` (audit E-12) supaya aturan
# pembuangan karakter tak terlihat tidak berbeda antar modul.
TAK_TERLIHAT = teks.TAK_TERLIHAT
bersihkan_teks = teks.bersihkan


# Hiasan yang menempel pada teks pertanyaan dan tidak mengubah maksudnya.
# JobStreet menambahkan penanda wajib pada setiap pertanyaan kuesioner
# ("Do you have sales negotiation experience? This question is required."),
# sedangkan jawaban yang disimpan pengguna lewat `jawaban --isi` hanyalah
# kalimat pertanyaannya. Tanpa dibuang, kuncinya berbeda dan jawaban yang
# SUDAH ada tidak pernah terpakai.
_HIASAN_AKHIR = re.compile(
    r"\s*(?:"
    r"this question is required"
    r"|required field"
    r"|pertanyaan ini wajib diisi"
    r"|wajib diisi"
    r"|please select"
    r"|select one"
    r"|pilih salah satu"
    r")\s*[.:!]?\s*$",
    re.IGNORECASE,
)
_HIASAN_KURUNG = re.compile(
    r"\s*[\(\[]\s*(?:wajib|required|optional|opsional|harus diisi)\s*[\)\]]\s*$",
    re.IGNORECASE,
)
_HIASAN_NOMOR = re.compile(
    r"^\s*(?:q|pertanyaan|question)?\s*\d{1,2}\s*[.):\-]\s+", re.IGNORECASE
)


def _rapikan_pertanyaan(teks: str) -> str:
    """Buang penanda wajib/nomor urut yang menempel pada teks pertanyaan."""
    hasil = bersihkan_teks(teks)

    for _ in range(3):
        sebelum = hasil
        hasil = _HIASAN_AKHIR.sub("", hasil)
        hasil = _HIASAN_KURUNG.sub("", hasil)
        hasil = _HIASAN_NOMOR.sub("", hasil)
        hasil = " ".join(hasil.split())
        if hasil == sebelum:
            break

    return hasil or bersihkan_teks(teks)


def kunci_pertanyaan(pertanyaan: str) -> str:
    """Kunci pencarian stabil dari teks pertanyaan."""
    teks = _rapikan_pertanyaan(pertanyaan).casefold()
    teks = _TANDA_BACA.sub(" ", teks)
    return " ".join(teks.split())


# Padanan istilah lintas bahasa. Formulir lamaran yang sama sering muncul
# dalam bahasa Indonesia atau Inggris ("Nama Lengkap" / "Full Name"), jadi
# kedua bentuk dipetakan ke satu kata kunci canonik sebelum dibandingkan.
PADANAN = {
    # identitas
    "nama lengkap": "nama",
    "nama": "nama",
    "full name": "nama",
    "name": "nama",
    "nama depan": "nama depan",
    "first name": "nama depan",
    "given name": "nama depan",
    "nama belakang": "nama belakang",
    "last name": "nama belakang",
    "surname": "nama belakang",
    "family name": "nama belakang",
    "email": "email",
    "surel": "email",
    "alamat email": "email",
    "email address": "email",
    "telepon": "telepon",
    "telpon": "telepon",
    "phone": "telepon",
    "phone number": "telepon",
    "mobile phone": "telepon",
    "nomor telepon": "telepon",
    "no telepon": "telepon",
    "nomor handphone": "telepon",
    "handphone": "telepon",
    "hp": "telepon",
    "alamat": "alamat",
    "address": "alamat",
    "alamat tinggal": "alamat",
    "current address": "alamat",
    "kota": "kota",
    "city": "kota",
    "kabupaten": "kota",
    "provinsi": "provinsi",
    "province": "provinsi",
    "kode pos": "kode pos",
    "postal code": "kode pos",
    "zip code": "kode pos",
    "negara": "negara",
    "country": "negara",
    "kewarganegaraan": "kewarganegaraan",
    "nationality": "kewarganegaraan",
    "citizenship": "kewarganegaraan",
    "tempat lahir": "tempat lahir",
    "place of birth": "tempat lahir",
    "tanggal lahir": "tanggal lahir",
    "date of birth": "tanggal lahir",
    "birth date": "tanggal lahir",
    "jenis kelamin": "jenis kelamin",
    "gender": "jenis kelamin",
    "sex": "jenis kelamin",
    "agama": "agama",
    "religion": "agama",
    "status perkawinan": "status perkawinan",
    "status pernikahan": "status perkawinan",
    "marital status": "status perkawinan",
    # pendidikan & pengalaman
    "pendidikan": "pendidikan",
    "pendidikan terakhir": "pendidikan",
    "education": "pendidikan",
    "highest education": "pendidikan",
    "educational background": "pendidikan",
    "universitas": "universitas",
    "university": "universitas",
    "sekolah": "universitas",
    "school": "universitas",
    "institusi": "universitas",
    "institution": "universitas",
    "jurusan": "jurusan",
    "major": "jurusan",
    "bidang studi": "jurusan",
    "field of study": "jurusan",
    "ipk": "ipk",
    "gpa": "ipk",
    "pengalaman": "pengalaman",
    "pengalaman kerja": "pengalaman",
    "experience": "pengalaman",
    "work experience": "pengalaman",
    "years of experience": "pengalaman",
    "lama pengalaman": "pengalaman",
    # pekerjaan
    "gaji": "gaji",
    "gaji yang diharapkan": "gaji",
    "ekspektasi gaji": "gaji",
    "expected salary": "gaji",
    "salary": "gaji",
    "salary expectation": "gaji",
    "jabatan": "posisi",
    "posisi": "posisi",
    "position": "posisi",
    "applied position": "posisi",
    "posisi yang dilamar": "posisi",
    "kapan bisa mulai": "mulai",
    "tanggal bergabung": "mulai",
    "available start date": "mulai",
    "start date": "mulai",
    "notice period": "mulai",
    "sim": "sim",
    "sim c": "sim",
    "driving license": "sim",
    "bahasa": "bahasa",
    "language": "bahasa",
}


def kunci_padanan(pertanyaan: str) -> str:
    """Kunci canonik setelah istilah Indonesia/Inggris disamakan."""
    kata = kunci_pertanyaan(pertanyaan).split()
    hasil = []
    i = 0
    while i < len(kata):
        dua = " ".join(kata[i : i + 2])
        if dua in PADANAN:
            hasil.append(PADANAN[dua])
            i += 2
            continue
        hasil.append(PADANAN.get(kata[i], kata[i]))
        i += 1
    return " ".join(hasil)


def _mirip_kunci(pertanyaan: str, kunci_tersimpan: str) -> float:
    """Kemiripan teks, juga setelah istilah dua bahasa disamakan."""
    kunci = kunci_pertanyaan(pertanyaan)
    skor = SequenceMatcher(None, kunci, kunci_tersimpan).ratio()
    skor_padanan = SequenceMatcher(
        None, kunci_padanan(pertanyaan), kunci_padanan(kunci_tersimpan)
    ).ratio()
    return max(skor, skor_padanan)


# Pertanyaan persetujuan/hukum tidak boleh diisi otomatis — sekalipun pernah
# dijawab (master prompt pasal 8.4). Bot wajib berhenti dan meminta Anda.
# Pertanyaan yang WAJIB dijawab pengguna sendiri (master prompt pasal 8.4).
# Hanya pernyataan/persetujuan/hukum — pertanyaan kesediaan biasa
# ("bersedia kerja shift?") tetap boleh dijawab otomatis.
POLA_KONFIRMASI = (
    r"\bsaya setuju\b",
    r"\bi agree\b",
    r"\bsetuju dengan\b",
    r"\bmenyetujui pernyataan\b",
    r"\bpernyataan (ini|di atas|tersebut)\b",
    r"\bpersetujuan\b",
    r"\bsaya bersedia\b",
    r"\bperjanjian\b",
    r"\bkesepakatan\b",
    r"\bkontrak\b",
    r"\bdata pribadi\b",
    r"\bkerahasiaan\b",
    r"\bprivasi\b",
    r"\bsanksi\b",
    r"\bhukum\b",
    r"\blegal\b",
    r"\bterms\b",
    r"\bconditions\b",
    r"\bprivacy\b",
    r"\bconsent\b",
    r"\bagree\b",
    r"\bdeclaration\b",
    r"\bdeclare\b",
    r"\bbackground check\b",
    r"\bbebas narkoba\b",
    r"\bnarkoba\b",
)

_konfirmasi = re.compile("|".join(POLA_KONFIRMASI), re.IGNORECASE)


def perlu_konfirmasi(pertanyaan: str) -> bool:
    """True bila pertanyaan menyangkut persetujuan/hukum (wajib ditanyakan)."""
    return bool(_konfirmasi.search(str(pertanyaan or "")))



# ---------------------------------------------------------------------------
# Pencocokan berdasarkan MAKSUD pertanyaan (keputusan pemakai 2026-11-12)
#
# JobStreet menanyakan hal yang sama dengan kalimat berbeda di tiap lowongan:
#   "How many years' experience do you have as a Purchasing Specialist?"
#   "How many years of experience do you have in a Purchasing role?"
#   "Berapa tahun pengalaman kerjamu di bidang pengadaan?"
# Kemiripan teksnya di bawah AMBANG_MIRIP sehingga jawaban yang SUDAH pernah
# diberikan tidak terpakai, dan lamaran berhenti sebagai "perlu manual".
#
# Aturan ini hanya MEMAKAI ULANG jawaban yang sudah ada. Tidak ada jawaban
# baru yang dikarang: kalau jenis pertanyaannya belum pernah dijawab, tetap
# dikembalikan None dan lowongan dilewati seperti sebelumnya.
# ---------------------------------------------------------------------------

# Frasa pembuka yang tidak mengubah maksud pertanyaan.
_PENGISI_MAKSUD = (
    (
        r"how many years of [a-z' ]{0,40}experience do you have"
        r"( as| in| with| for)?"
    ),
    (
        r"how many years'? [a-z' ]{0,40}experience do you have"
        r"( as| in| with| for)?"
    ),
    (
        r"berapa tahun pengalaman( kerja)?( mu| anda| kamu)?"
        r"( sebagai| di bidang| dalam| untuk)?"
    ),
    r"do you have (any )?experience( in| with| as| working)?",
    r"apakah (kamu|anda) (memiliki|punya) pengalaman( kerja)?( di| dalam)?",
    r"have you (ever )?worked( in a role which requires experience with| as| in)?",
    r"pernahkah (kamu|anda) bekerja( dalam peran| sebagai| di)?",
    r"pengalaman( kerja)?( mu| anda| kamu)?( di| dalam| sebagai)?",
    r"\b(role|posisi|peran|sebagai|as an?|in an?)\b",
)

_PENGISI_RE = re.compile("|".join(_PENGISI_MAKSUD), re.IGNORECASE)

# Jenis pertanyaan terstruktur. Hanya jenis ini yang boleh dicocokkan lewat
# maksud; pertanyaan terbuka/cerita tetap harus persis atau mirip sekali.
KELUARGA_PERTANYAAN = (
    ("pengalaman", r"\b(pengalaman|experience)\b"),
    ("gaji", r"\b(gaji|salary|upah|pendapatan|compensation|remuneration)\b"),
    (
        "pendidikan",
        r"\b(pendidikan|education|kualifikasi|qualification|gelar|degree)\b",
    ),
    ("bahasa", r"\b(bahasa|language|english|inggris|mandarin|jepang|japanese)\b"),
    (
        "hak_kerja",
        r"\b(hak|right to work|warga negara|citizen|izin kerja|work permit)\b",
    ),
    ("industri", r"\b(industri|industry)\b"),
    (
        "ketersediaan",
        r"\b(bersedia|kesediaan|available|availability|relokasi|relocate|shift)\b",
    ),
    ("sim", r"\b(sim|driving license)\b"),
)

_KELUARGA_RE = tuple(
    (nama, re.compile(pola, re.IGNORECASE)) for nama, pola in KELUARGA_PERTANYAAN
)

# Ambang kemiripan subjek (mis. "purchasing" vs "purchasing specialist").
AMBANG_SUBJEK = 0.70


def keluarga(pertanyaan: str) -> str:
    """Jenis pertanyaan: pengalaman, gaji, pendidikan, ... ("" bila umum)."""
    teks = bersihkan_teks(pertanyaan)

    for nama, pola in _KELUARGA_RE:
        if pola.search(teks):
            return nama

    return ""


# Istilah jabatan lintas bahasa, supaya "di bidang pengadaan" dan
# "purchasing role" dianggap subjek yang sama.
PADANAN_SUBJEK = {
    "pengadaan": "purchasing",
    "pembelian": "purchasing",
    "gudang": "warehouse",
    "persediaan": "inventory",
    "perencanaan produksi": "production planning",
    "administrasi": "admin",
    "sumber daya manusia": "hr",
    "keuangan": "finance",
    "akuntansi": "accounting",
}


def subjek(pertanyaan: str) -> str:
    """Inti pertanyaan tanpa frasa pembuka, mis. "purchasing specialist"."""
    teks = bersihkan_teks(pertanyaan).casefold()
    teks = _PENGISI_RE.sub(" ", teks)
    teks = _TANDA_BACA.sub(" ", teks)
    kata = [k for k in teks.split() if k not in _KATA_UMUM]
    hasil = " ".join(kata)

    for istilah, ganti in PADANAN_SUBJEK.items():
        hasil = re.sub(rf"\b{istilah}\b", ganti, hasil)

    return hasil.strip()


def maksud(pertanyaan: str) -> tuple[str, str]:
    return keluarga(pertanyaan), subjek(pertanyaan)


def _subjek_cocok(a: str, b: str) -> bool:
    """Dua subjek dianggap sama bila salah satu memuat yang lain."""
    if not a or not b:
        return True

    if a in b or b in a:
        return True

    return SequenceMatcher(None, a, b).ratio() >= AMBANG_SUBJEK


def _cari_berdasarkan_maksud(pertanyaan: str) -> str | None:
    """Pakai jawaban lama untuk pertanyaan sejenis walau kalimatnya berbeda."""
    jenis = keluarga(pertanyaan)
    if not jenis:
        return None

    inti = subjek_utama(pertanyaan)
    terbaik = None
    skor_terbaik = -1.0

    for baris in db.daftar_jawaban():
        jawaban_lama = str(baris.get("jawaban") or "").strip()
        kunci_lama = str(baris.get("kunci") or "")

        if not jawaban_lama or keluarga(kunci_lama) != jenis:
            continue

        inti_lama = subjek_utama(kunci_lama)
        if not _subjek_cocok(inti, inti_lama):
            continue

        # Subjek dibandingkan tanpa kata tingkat jabatan, supaya "purchasing
        # staff" dan "purchasing specialist" bernilai sama dan pemenangnya
        # ditentukan jumlah pemakaian (ajek, bukan tebak-tebakan).
        skor = SequenceMatcher(None, inti, inti_lama).ratio()
        skor += min(int(baris.get("dipakai") or 0), 20) / 1000  # stabil

        if skor > skor_terbaik:
            terbaik, skor_terbaik = baris, skor

    if terbaik and terbaik.get("jawaban"):
        db.tandai_jawaban_dipakai(terbaik["kunci"])
        return str(terbaik["jawaban"])

    return None


# --------------------------------------------------------------- angka/nilai --
# "Rp 5 Jt", "Rp 5 million", "Rp 5.000.000", "5 juta" → 5_000_000.
_SATUAN_ANGKA = {
    "jt": 1_000_000,
    "juta": 1_000_000,
    "jtan": 1_000_000,
    "million": 1_000_000,
    "mio": 1_000_000,
    "rb": 1_000,
    "ribu": 1_000,
    "k": 1_000,
    "tahun": 1,
    "thn": 1,
    "year": 1,
    "years": 1,
    "tahun)": 1,
}

_RIBUAAN = re.compile(r"^(\d{1,3})((?:[.,]\d{3})+)$")
_ANGKA_SATUAN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(jt|juta|jtan|million|mio|ribu|rb|k|tahun|thn|years?|year)?"
)

# Kata yang tidak membedakan maksud pertanyaan.
_KATA_UMUM = frozenset((
    "a", "an", "the", "of", "in", "on", "for", "with", "you", "your",
    "do", "does", "have", "has", "how", "many", "much", "kamu", "anda",
    "mu", "yang", "di", "ke", "dari", "dan", "atau", "ini", "itu",
    "adalah", "apakah", "berapa", "bidang", "role", "posisi", "peran",
    "sebagai",
))


def angka_dari_teks(teks) -> tuple[float, str] | None:
    """Nilai angka + satuan dari teks jawaban/opsi; None bila tidak ada angka."""
    teks_bersih = bersihkan_teks(teks).casefold().replace("rp", " ")

    for potong in re.split(r"[;/|]", teks_bersih):
        potongan = potong.strip()
        if not potongan:
            continue

        ribuan = _RIBUAAN.match(potongan.replace(" ", ""))
        if ribuan:
            return float(ribuan.group(1) + ribuan.group(2).replace(".", "")
                         .replace(",", "")), "rupiah"

        cocok = _ANGKA_SATUAN.search(potongan)
        if not cocok:
            continue

        teks_angka = cocok.group(1).replace(",", ".")
        satuan = (cocok.group(2) or "").strip()
        nilai = float(teks_angka)
        faktor = _SATUAN_ANGKA.get(satuan)

        if faktor is None:
            if "." in potongan and len(teks_angka.split(".")[-1]) == 3:
                continue
            return nilai, ""

        return nilai * faktor, ("rupiah" if faktor >= 1_000 else "tahun")

    return None


# Ungkapan yang membatasi nilai: "kurang dari 1 tahun" BUKAN "1 tahun".
_PENYANGKAL_NILAI = (
    "kurang dari",
    "less than",
    "no experience",
    "tanpa pengalaman",
    "tidak berpengalaman",
    "belum berpengalaman",
)


def _bersyarat(teks) -> bool:
    teks = bersihkan_teks(teks).casefold()
    return any(pola in teks for pola in _PENYANGKAL_NILAI)


def sama_nilai(a, b) -> bool:
    """Dua teks menyebut angka & satuan yang sama ("Rp 5 Jt" = "Rp 5 million")."""
    if _bersyarat(a) or _bersyarat(b):
        return kunci_pertanyaan(a) == kunci_pertanyaan(b)

    nilai_a = angka_dari_teks(a)
    nilai_b = angka_dari_teks(b)

    if not nilai_a or not nilai_b:
        return False

    if nilai_a[1] != nilai_b[1]:
        return False

    # Toleransi hanya pembulatan relatif 1%: "2 tahun" dan "3 tahun" BUKAN
    # nilai yang sama. Toleransi absolut 1 (versi sebelumnya) membuat semua
    # angka 0-4 tahun dianggap sama.
    selisih = abs(nilai_a[0] - nilai_b[0])
    return selisih <= max(1e-9, nilai_a[0] * 0.01)


# ------------------------------------------------------------ pilihan opsi ---
# Pertanyaan ya/tidak adalah yang paling sering memblokir lamaran: jawabannya
# sudah tersimpan, tetapi label opsinya berbeda ("No" vs "Tidak" vs
# "No, I don't have any"), sehingga bot melaporkan "belum bisa dijawab
# otomatis" dan membakar waktu tunggu. Peta di bawah menyamakan sisi YA dan
# sisi TIDAK tanpa mengarang nilai baru: hanya memakai jawaban yang sudah ada.
_YA_KATA = frozenset((
    "ya", "yes", "iya", "y", "benar", "betul", "true", "sudah", "have", "has",
    "punya", "memiliki", "ada", "bersedia", "siap", "setuju", "sure", "bisa",
    "mampu", "mau",
))
_TIDAK_KATA = frozenset((
    "no", "not", "tidak", "bukan", "belum", "nggak", "gak", "ga", "tdk",
    "none", "never", "nope", "tanpa",
))
# Kata penghubung yang boleh menemani "Yes"/"No" pada label opsi panjang
# ("Yes, I have", "No, I don't", "Tidak, saya belum pernah").
_KATA_PENGHUBUNG = frozenset((
    "i", "saya", "aku", "kami", "anda", "you", "do", "does", "did", "am",
    "is", "are", "have", "has", "had", "pernah", "sudah", "sih", "kok",
    "yang", "itu", "memang", "juga", "t", "don", "doesn", "isn", "won",
    "in", "of", "the", "a", "an", "lah", "pun", "sekali", "any", "at",
    "all", "now", "currently", "right", "sama", "juga", "dengan", "untuk",
))


def padanan_ya_tidak(nilai) -> str:
    """"ya" / "tidak" bila teks benar-benar jawaban ya/tidak; "" bila bukan.

    Hanya teks pendek yang seluruh katanya berasal dari kosakata ya/tidak yang
    dianggap cocok. "No experience" dan "Sudah vaksinasi lengkap" SENGAJA
    tidak termasuk: keduanya jawaban bernilai, bukan ya/tidak.
    """
    kata = kunci_pertanyaan(nilai).split()
    if not kata:
        return ""

    for sisi, kosakata in (("ya", _YA_KATA), ("tidak", _TIDAK_KATA)):
        if not any(item in kosakata for item in kata):
            continue
        if all(item in kosakata or item in _KATA_PENGHUBUNG for item in kata):
            return sisi

    return ""


def _sisi_tunggal(opsi) -> tuple[str, str] | None:
    """(opsi_ya, opsi_tidak) bila grup itu benar-benar pasangan ya/tidak."""
    if len(opsi) > 3:
        return None

    ya = [item for item in opsi if padanan_ya_tidak(item) == "ya"]
    tidak = [item for item in opsi if padanan_ya_tidak(item) == "tidak"]

    if len(ya) == 1 and len(tidak) == 1:
        return ya[0], tidak[0]

    return None


def _memuat(teks: str, bagian: str) -> bool:
    """True bila `bagian` muncul sebagai kata utuh di dalam `teks`."""
    if not teks or not bagian:
        return False
    return re.search(rf"(?<!\w){re.escape(bagian)}(?!\w)", teks) is not None


def cocok_opsi(nilai, opsi) -> str:
    """Opsi yang mewakili jawaban tersimpan ("" bila tidak ada yang cocok).

    Urutan: kunci persis → sisi ya/tidak → kata utuh → angka/satuan →
    kemiripan teks. Semua jalur hanya MEMILIH di antara opsi yang benar-benar
    ada di formulir; tidak ada nilai baru yang dibuat.
    """
    daftar = [str(item) for item in (opsi or []) if str(item or "").strip()]
    teks_nilai = " ".join(str(nilai or "").split())

    if not daftar or not teks_nilai:
        return ""

    kunci_nilai = kunci_pertanyaan(teks_nilai)

    for item in daftar:
        if kunci_pertanyaan(item) == kunci_nilai:
            return item

    pasangan = _sisi_tunggal(daftar)
    sisi = padanan_ya_tidak(teks_nilai)
    if pasangan and sisi:
        return pasangan[0] if sisi == "ya" else pasangan[1]

    # Jawaban ya/tidak pada grup yang TIDAK jelas pasangannya (mis. ada dua
    # opsi "tidak"): jangan menebak, biarkan pengguna yang memutuskan.
    if sisi:
        return ""

    for item in daftar:
        kunci_opsi = kunci_pertanyaan(item)
        if _memuat(kunci_opsi, kunci_nilai) or _memuat(kunci_nilai, kunci_opsi):
            return item

    for item in daftar:
        if sama_nilai(teks_nilai, item):
            return item

    # Kemiripan teks hanya untuk opsi yang BUKAN angka: "Rp 5 jt" dan
    # "Rp 1 jt" mirip 0.86 padahal nilainya berbeda, dan itu sudah diputuskan
    # oleh `sama_nilai` di atas.
    terbaik = ""
    skor_terbaik = 0.0
    for item in daftar:
        if angka_dari_teks(item) and angka_dari_teks(teks_nilai):
            continue

        skor = SequenceMatcher(None, kunci_nilai, kunci_pertanyaan(item)).ratio()
        if skor >= AMBANG_OPSI and skor > skor_terbaik:
            terbaik, skor_terbaik = item, skor

    return terbaik


def _aktif() -> bool:
    return bool(getattr(config, "ingat_jawaban", True))


def cari(pertanyaan: str) -> str | None:
    """Jawaban yang pernah diberikan untuk pertanyaan ini (None bila belum).

    Pencocokan: kunci sama → kembalikan; bila tidak, cari pertanyaan tersimpan
    yang paling mirip (>= AMBANG_MIRIP). Setiap pemakaian dihitung supaya
    urutan prioritas bisa ditinjau lewat perintah `jawaban`.
    """
    if not _aktif():
        return None

    kunci = kunci_pertanyaan(pertanyaan)
    if not kunci:
        return None

    # Pasal 8.4: pertanyaan persetujuan/hukum wajib dikonfirmasi pengguna,
    # tidak boleh diisi otomatis walau sudah pernah dijawab.
    if perlu_konfirmasi(pertanyaan):
        return None

    tersimpan = db.cari_jawaban(kunci)
    if tersimpan and tersimpan.get("jawaban"):
        db.tandai_jawaban_dipakai(kunci)
        return str(tersimpan["jawaban"])

    # Cadangan 1: pertanyaan sejenis dengan kalimat berbeda
    # ("as a Purchasing Specialist" vs "in a Purchasing role"). Didahulukan
    # sebelum pencocokan kemiripan teks karena cara ini membandingkan MAKSUD
    # (jenis + subjek) sehingga tidak bergantung pada selisih kata "staff"
    # atau "specialist" — sumber pilihan yang berubah-ubah.
    hasil = _cari_berdasarkan_maksud(pertanyaan)
    if hasil:
        return hasil

    # Cadangan 2: pertanyaan yang mirip (mis. salah ketik / tanda baca berubah).
    terbaik = None
    skor_terbaik = 0.0

    for baris in db.daftar_jawaban():
        skor = _mirip_kunci(pertanyaan, baris.get("kunci") or "")
        # Imbuhan kecil dari jumlah pemakaian: kalau dua pertanyaan sama
        # miripnya, jawaban yang paling sering dipakai yang menang (ajek).
        skor += min(int(baris.get("dipakai") or 0), 20) / 1000
        if skor > skor_terbaik:
            terbaik, skor_terbaik = baris, skor

    if terbaik and skor_terbaik >= AMBANG_MIRIP and terbaik.get("jawaban"):
        db.tandai_jawaban_dipakai(terbaik["kunci"])
        return str(terbaik["jawaban"])

    # Cadangan 3: pertanyaan ya/tidak yang disusun ulang. Hanya jawaban
    # ya/tidak yang boleh dipakai di sini (ruang kemungkinannya sempit) dan
    # hanya bila kandidat terbaik jelas mengungguli kandidat berikutnya.
    return _cadangan_ya_tidak(pertanyaan)


_SAPAAN_YA_TIDAK = re.compile(
    r"\b(do|does|did|have|has|are|is|can|could|will|would|pernahkah|apakah"
    r"|sudahkah|bisakah|dapatkah)\b",
    re.IGNORECASE,
)


def _pertanyaan_ya_tidak(pertanyaan: str) -> bool:
    return bool(_SAPAAN_YA_TIDAK.search(bersihkan_teks(pertanyaan)))


# Kata yang tidak membedakan isi pertanyaan ya/tidak ("do you have … experience").
_KATA_UMUM_YA_TIDAK = frozenset((
    "do", "does", "did", "have", "has", "had", "are", "is", "was", "were",
    "can", "could", "will", "would", "you", "your", "i", "me", "my", "we",
    "the", "a", "an", "of", "in", "on", "for", "with", "to", "at", "as",
    "any", "experience", "pengalaman", "kerja", "work", "working", "pernah",
    "apakah", "kamu", "anda", "saya", "sudah", "bisa", "dapat", "mampu",
    "bersedia", "siap", "memiliki", "punya", "ada", "yang", "itu", "ini",
    "tahun", "years", "year", "bulan", "month", "months", "atas", "dan",
    "atau", "di", "ke", "question", "required", "this",
))


def kata_isi(pertanyaan: str) -> set:
    """Kata pembeda maksud pertanyaan (tanpa kata tanya dan kata jenis)."""
    return {
        kata
        for kata in kunci_pertanyaan(pertanyaan).split()
        if kata not in _KATA_UMUM_YA_TIDAK
    }


def _isi_sejalan(a: set, b: set) -> bool:
    """True bila dua pertanyaan benar-benar membicarakan hal yang sama.

    "Are you able to work under pressure?" dan "Can you work under pressure?"
    berbagi inti {pressure}; "ERP implementation" dan "sales negotiation"
    tidak berbagi apa pun sehingga tidak boleh saling meminjam jawaban.
    """
    if not a or not b:
        return False

    if a <= b or b <= a:
        return True

    return len(a & b) / len(a | b) >= 0.6


def _cadangan_ya_tidak(pertanyaan: str) -> str | None:
    """Pakai jawaban ya/tidak lama untuk pertanyaan yang disusun ulang."""
    if not _pertanyaan_ya_tidak(pertanyaan):
        return None

    kandidat = []
    for baris in db.daftar_jawaban():
        nilai = str(baris.get("jawaban") or "")
        if not nilai or not padanan_ya_tidak(nilai):
            continue

        if not _isi_sejalan(kata_isi(pertanyaan), kata_isi(baris.get("kunci") or "")):
            continue

        skor = _mirip_kunci(pertanyaan, baris.get("kunci") or "")
        skor += min(int(baris.get("dipakai") or 0), 20) / 1000
        kandidat.append((skor, baris))

    if not kandidat:
        return None

    kandidat.sort(key=lambda item: item[0], reverse=True)
    skor_terbaik, terbaik = kandidat[0]
    skor_kedua = kandidat[1][0] if len(kandidat) > 1 else 0.0

    if skor_terbaik < AMBANG_MIRIP_YA_TIDAK:
        return None
    if skor_terbaik - skor_kedua < SELISIH_YA_TIDAK:
        return None

    db.tandai_jawaban_dipakai(terbaik["kunci"])
    return str(terbaik["jawaban"])


def ingat(pertanyaan: str, jawaban: str, jenis: str = "",
          sumber: str = "pengguna") -> bool:
    """Simpan jawaban untuk pertanyaan ini (menimpa jawaban lama)."""
    if not _aktif():
        return False

    kunci = kunci_pertanyaan(pertanyaan)
    jawaban = " ".join(str(jawaban or "").split())

    if not kunci or not jawaban:
        return False

    return db.simpan_jawaban(
        kunci, " ".join(str(pertanyaan or "").split()), jawaban, jenis, sumber
    )


def daftar() -> list[dict]:
    """Semua jawaban tersimpan (untuk ditampilkan / diperiksa)."""
    return db.daftar_jawaban()


# Kata tingkat jabatan yang tidak mengubah subjek pembicaraan
# ("purchasing staff" dan "purchasing specialist" sama-sama soal purchasing).
_KATA_JABATAN = frozenset(
    (
        "staff", "staf", "specialist", "spesialis", "officer",
        "executive", "assistant", "asisten", "supervisor", "spv",
        "manager", "manajer", "admin", "administrator", "representative",
        "rep", "clerk", "helper", "analyst", "analys",
        "senior", "junior", "intern", "magang", "role",
        "posisi",
    )
)

# Jenis pertanyaan yang tidak perlu dibedakan subjeknya: semua pertanyaan gaji
# pada dasarnya satu pertanyaan.
_KELUARGA_TANPA_SUBJEK = frozenset(("gaji", "hak_kerja", "ketersediaan", "sim"))


# Kata jenis pertanyaan yang tidak membedakan SUBJEK. Tanpa dibuang,
# "Do you have ERP implementation experience?" dan "Do you have sales
# negotiation experience?" dianggap sejenis (0.70) semata-mata karena
# keduanya berakhiran "experience" — jawaban yang salah pun ikut terpakai.
_KATA_JENIS = frozenset((
    "experience", "experiences", "pengalaman", "kerja", "work", "working",
    "salary", "gaji", "upah", "pendapatan", "compensation", "remuneration",
    "education", "pendidikan", "kualifikasi", "qualification", "gelar",
    "degree", "industry", "industri", "years", "year", "tahun", "bulan",
    "month", "months",
))


def subjek_utama(pertanyaan: str) -> str:
    """Subjek tanpa kata tingkat jabatan: "purchasing specialist" → "purchasing"."""
    kata = [
        k
        for k in subjek(pertanyaan).split()
        if k not in _KATA_JABATAN and k not in _KATA_JENIS
    ]
    return " ".join(kata)


# ---------------------------------------------------------- rapikan konflik ---
def konflik(daftar: list[dict] | None = None) -> list[dict]:
    """Kelompok jawaban yang maksudnya sama tetapi nilainya berbeda.

    Contoh nyata (sesi 12 Nov 2026): pertanyaan pengalaman purchasing dijawab
    "Less than 1 year", "1 year", "2 tahun", dan "3 years" di lowongan
    berbeda. Dengan pencocokan berdasarkan maksud, bot bisa memilih salah
    satunya secara berubah-ubah — jadi konfliknya harus dirapikan dulu.
    """
    baris = daftar if daftar is not None else db.daftar_jawaban()
    kelompok: dict[tuple[str, str], dict] = {}

    for item in baris:
        pertanyaan = str(item.get("pertanyaan") or item.get("kunci") or "")
        nilai = str(item.get("jawaban") or "").strip()
        jenis = keluarga(pertanyaan)

        if not jenis or not nilai:
            continue

        inti = "" if jenis in _KELUARGA_TANPA_SUBJEK else subjek_utama(pertanyaan)
        kunci_kelompok = (jenis, inti)

        data = kelompok.setdefault(
            kunci_kelompok,
            {"keluarga": jenis, "subjek": inti, "nilai": {}, "pertanyaan": []},
        )
        for nilai_lain in list(data["nilai"]):
            if sama_nilai(nilai, nilai_lain) or (
                kunci_pertanyaan(nilai) == kunci_pertanyaan(nilai_lain)
            ):
                nilai = nilai_lain
                break

        catatan = data["nilai"].setdefault(nilai, {"jumlah": 0, "dipakai": 0})
        catatan["jumlah"] += 1
        catatan["dipakai"] += int(item.get("dipakai") or 0)
        data["pertanyaan"].append(pertanyaan)

    hasil = []

    for data in kelompok.values():
        if len(data["nilai"]) < 2:
            continue

        data["jumlah"] = len(data["pertanyaan"])
        hasil.append(data)

    hasil.sort(key=lambda item: (-item["jumlah"], item["subjek"]))
    return hasil


def _nilai_terbanyak(nilai: dict) -> str:
    """Nilai yang paling sering dipakai (tie-break: jumlah lalu abjad)."""
    return sorted(
        nilai.items(),
        key=lambda item: (-item[1]["dipakai"], -item[1]["jumlah"], item[0]),
    )[0][0]


def tetapkan(subjek_dicari: str, nilai_baru: str,
            daftar: list[dict] | None = None) -> int:
    """Samakan semua jawaban dalam satu kelompok menjadi satu nilai.

    Kembalikan jumlah jawaban yang diubah. `subjek_dicari` boleh sebagian,
    mis. "purchasing" akan mengenai "purchasing specialist" juga. Hanya
    jawaban dengan jenis pertanyaan yang sama yang diubah, supaya nilai
    "3 years" tidak ikut masuk ke pertanyaan soal industri purchasing.
    """
    nilai_baru = str(nilai_baru or "").strip()
    if not nilai_baru:
        return 0

    dicari = (
        subjek_utama(subjek_dicari)
        or subjek(subjek_dicari)
        or str(subjek_dicari or "").strip().casefold()
    )
    if not dicari:
        return 0

    baris = daftar if daftar is not None else db.daftar_jawaban()

    # Kumpulkan calon sasaran, kelompokkan per jenis pertanyaan.
    calon: dict[str, list[dict]] = {}
    for item in baris:
        pertanyaan = str(item.get("pertanyaan") or item.get("kunci") or "")
        inti = subjek_utama(pertanyaan) or subjek_utama(str(item.get("kunci") or ""))
        jenis = keluarga(pertanyaan)

        cocok = dicari in inti or inti in dicari or dicari == jenis
        if not cocok or not jenis:
            continue

        calon.setdefault(jenis, []).append(item)

    if not calon:
        return 0

    # Bila beberapa jenis ikut cocok, pilih yang paling banyak barisnya.
    jenis_terpilih = sorted(calon, key=lambda j: (-len(calon[j]), j))[0]

    jumlah = 0
    for item in calon[jenis_terpilih]:
        pertanyaan = str(item.get("pertanyaan") or "")
        kunci = str(item.get("kunci") or "")
        if not kunci:
            continue

        if str(item.get("jawaban") or "").strip() == nilai_baru:
            continue

        if db.simpan_jawaban(
            kunci,
            pertanyaan or kunci,
            nilai_baru,
            str(item.get("jenis") or ""),
            "manual",
        ):
            jumlah += 1

    return jumlah


def lupakan(pertanyaan: str) -> bool:
    """Hapus satu jawaban dari ingatan."""
    kunci = kunci_pertanyaan(pertanyaan)
    if not kunci:
        return False

    if db.hapus_jawaban(kunci):
        return True

    # Bila yang diketik bukan kunci persis, pakai pencocokan mirip.
    terbaik = None
    skor_terbaik = 0.0

    for baris in db.daftar_jawaban():
        skor = _mirip_kunci(pertanyaan, baris.get("kunci") or "")
        if skor > skor_terbaik:
            terbaik, skor_terbaik = baris, skor

    if terbaik and skor_terbaik >= AMBANG_MIRIP:
        return db.hapus_jawaban(terbaik["kunci"])

    return False


def lupakan_semua() -> int:
    """Kosongkan ingatan jawaban."""
    return db.reset_jawaban()


def jumlah() -> int:
    return db.hitung_jawaban()
