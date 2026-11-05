// Pemeriksaan SKRIP_KARTU (pembaca kartu Glints) memakai DOM sungguhan.
// Jalankan:  npm install jsdom && node tests/glints_kartu_js.js
// Dilewati otomatis oleh pytest bila node/jsdom tidak tersedia.
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

// Ambil SKRIP_KARTU apa adanya dari glints.py
const berkas = path.join(__dirname, "..", "glints.py");
const py = fs.readFileSync(berkas, "utf8");
const mulai = py.indexOf('SKRIP_KARTU = r"""') + 'SKRIP_KARTU = r"""'.length;
const akhir = py.indexOf('"""', mulai);
const skrip = py.slice(mulai, akhir);

const kartu = (judul, gaji, perusahaan, lokasi, badge, id, gambar = "") => `
<div class="job-card">
  ${gambar}
  <div class="header">
    <a class="title" href="/id/opportunities/jobs/${judul.toLowerCase().replace(/[^a-z0-9]+/g, "-")}/${id}?utm_referrer=explore&traceInfo=abc">
      <h2>${judul}</h2>
    </a>
    ${badge ? `<span class="badge">${badge}</span>` : ""}
  </div>
  <div class="info"><span>${gaji}</span><span>Penuh Waktu</span></div>
  <a class="company" href="/id/companies/${perusahaan.toLowerCase().replace(/[^a-z0-9]+/g, "-")}/d8d151f0">${perusahaan}</a>
  <div class="loc">
    <a href="/id/job-location/indonesia/jawa-barat/bekasi">${lokasi}</a>,
    <a href="/id/job-location/indonesia/jawa-barat">Jawa Barat</a>
  </div>
</div>`;

const html = `<!doctype html><html><body>
<div class="list">
  ${kartu("Admin Warehouse", "Rp 2-3jt", "PT Bangun Selaras Bersama", "Bekasi", "", "aaaaaaaa-1111-2222-3333-444444444444", '<img alt="PT Bangun Selaras Bersama" src="https://cdn/brand/logo-pt-bsb.png" class="company-logo">')}
  ${kartu("Staff Gudang", "Rp 5-6jt", "PT Sinar Abadi Nusantara", "Kota Bekasi", "", "bbbbbbbb-1111-2222-3333-444444444444")}
  ${kartu("Kepala Gudang", "Gaji Tidak Ditampilkan", "PT Contoh", "Cikarang", "Lamar 1x tap di aplikasi", "cccccccc-1111-2222-3333-444444444444", '<img alt="" src="https://cdn/icon-search.svg">')}
  <a href="/id/opportunities/jobs/warehouse">Warehouse (tanpa UUID, harus diabaikan)</a>
  <a href="/id/opportunities/jobs/warehouse/aaaaaaaa-1111-2222-3333-444444444444?utm_referrer=similar">Duplikat</a>
</div>
</body></html>`;

const dom = new JSDOM(html, { url: "https://glints.com/id/opportunities/jobs/explore?keyword=warehouse" });
const hasil = new Function("document", skrip)(dom.window.document);

let gagal = 0;
const cek = (syarat, pesan) => {
  if (!syarat) { gagal += 1; console.log("GAGAL:", pesan); } else { console.log("OK   :", pesan); }
};

cek(Array.isArray(hasil), "skrip mengembalikan array");
cek(hasil.length === 3, `jumlah kartu unik = 3 (dapat ${hasil.length})`);
cek(hasil[0].title === "Admin Warehouse", `judul kartu 1: ${hasil[0].title}`);
cek(hasil[0].company === "PT Bangun Selaras Bersama", `perusahaan: ${hasil[0].company}`);
cek(hasil[0].location.startsWith("Bekasi"), `lokasi: ${hasil[0].location}`);
cek(hasil[0].salary === "Rp 2-3jt", `gaji: ${hasil[0].salary}`);
cek(hasil[1].salary === "Rp 5-6jt", `gaji kartu 2: ${hasil[1].salary}`);
cek(hasil[2].salary === "", `gaji tidak ditampilkan -> kosong (dapat "${hasil[2].salary}")`);
cek(/1x tap di aplikasi/i.test(hasil[2].text), "badge aplikasi masuk ke teks kartu");
cek(!hasil.some((x) => x.url.includes("?")), "URL dibersihkan dari query");
cek(new Set(hasil.map((x) => x.url)).size === 3, "tidak ada URL ganda");
cek(Array.isArray(hasil[0].logo) && hasil[0].logo.length === 1, "kartu 1 punya data gambar");
cek(hasil[0].logo[0].alt === "PT Bangun Selaras Bersama", `alt gambar: ${hasil[0].logo[0].alt}`);
cek(hasil[0].logo[0].src.includes("logo-pt-bsb"), "src gambar terbaca");
cek(hasil[0].logo[0].penanda.includes("company-logo"), `penanda gambar: ${hasil[0].logo[0].penanda}`);
cek(hasil[1].logo.length === 0, "kartu tanpa gambar -> logo kosong");
cek(hasil[2].logo.length === 1 && hasil[2].logo[0].src.includes("icon"), "ikon ikut terbaca sebagai gambar");

console.log(gagal === 0 ? "\nSEMUA CEK JS LULUS" : `\n${gagal} CEK GAGAL`);
process.exit(gagal === 0 ? 0 : 1);
