# ha_tuya.py
# Tool MCP untuk mengontrol perangkat Tuya (lampu depan, colokan, pakan kucing, dst)
# lewat Home Assistant REST API. Perangkat dicari otomatis berdasarkan NAMA di Home Assistant,
# jadi tidak perlu menulis entity_id satu per satu.
#
# Dipakai dengan dua cara:
#   1. Digabung ke kb_search.py:  ha_tuya.register(mcp)
#   2. Berdiri sendiri:           python -m ha_tuya
#
# Tes cepat tanpa Xiaozhi:
#   python ha_tuya.py daftar
#   python ha_tuya.py status "stok kontak lemari"
#   python ha_tuya.py nyala  "lampu depan"
#   python ha_tuya.py mati   "lampu depan"
#
# .env:
#   HA_URL=http://192.168.100.17:8123
#   HA_TOKEN=<Long-Lived Access Token dari profil Home Assistant>
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.request

logger = logging.getLogger("HATuya")

# Domain yang boleh dikontrol. Sengaja TIDAK memuat lock / alarm / kamera.
DOMAIN_NYALA = {"light", "switch", "fan"}
DOMAIN_KONTROL = DOMAIN_NYALA | {"button", "number", "select", "cover"}

WARNA = {
    "merah": (255, 0, 0), "hijau": (0, 255, 0), "biru": (0, 0, 255),
    "kuning": (255, 220, 0), "oranye": (255, 120, 0), "jingga": (255, 120, 0),
    "ungu": (150, 0, 255), "pink": (255, 60, 150), "merah muda": (255, 60, 150),
    "cyan": (0, 255, 255), "biru muda": (0, 200, 255), "putih": (255, 255, 255),
}


# ---------------------------------------------------------------- HTTP ke Home Assistant

class HAError(Exception):
    pass


def _ha(path, data=None, method=None):
    url = os.environ.get("HA_URL", "").rstrip("/")
    token = os.environ.get("HA_TOKEN", "").strip()
    if not url or not token:
        raise HAError("HA_URL atau HA_TOKEN belum diatur di .env")
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        f"{url}/api{path}", data=body,
        method=method or ("POST" if body is not None else "GET"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise HAError("Token Home Assistant ditolak (401). Buat token baru dan perbarui HA_TOKEN.")
        raise HAError(f"Home Assistant membalas HTTP {e.code}: {e.read()[:200].decode(errors='ignore')}")
    except Exception as e:
        raise HAError(f"Tidak bisa menghubungi Home Assistant di {url}: {e}")


def _semua_state():
    return _ha("/states")


def _service(domain, service, data):
    return _ha(f"/services/{domain}/{service}", data)


# ---------------------------------------------------------------- pencarian entitas

def _norm(s):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split())


def _nama(st):
    return st.get("attributes", {}).get("friendly_name") or st["entity_id"]


def _cocok(nama, domains=None):
    """Kembalikan daftar state yang cocok, diurutkan dari yang paling pas."""
    q = _norm(nama)
    if not q:
        return []
    kata = q.split()
    hasil = []
    for st in _semua_state():
        dom = st["entity_id"].split(".")[0]
        if domains and dom not in domains:
            continue
        fn = _norm(_nama(st))
        hay = fn + " " + _norm(st["entity_id"].split(".", 1)[1])
        if fn == q:
            skor = 3
        elif all(k in fn.split() for k in kata):
            skor = 2
        elif all(k in hay for k in kata):
            skor = 1
        else:
            continue
        hasil.append((skor, st))
    if not hasil:
        return []
    terbaik = max(s for s, _ in hasil)
    return [st for s, st in hasil if s == terbaik]


_PENGATURAN = ("kunci anak", "child", "atur ulang", "reset", "alarm", "balikkan", "tanda air",
               "privasi", "rekaman", "deteksi", "pelacakan", "sensitivitas", "indikator",
               "kecepatan efek", "behavior")


def _satu(nama, domains):
    """Cari tepat satu entitas. Kembalikan (state, None) atau (None, pesan_error)."""
    cocok = _cocok(nama, domains)
    if not cocok:
        return None, f"Perangkat '{nama}' tidak ditemukan di Home Assistant."
    if len(cocok) > 1:
        # Abaikan saklar pengaturan (kunci anak, reset, alarm, dst) jika masih ada pilihan lain
        bersih = [s for s in cocok if not any(k in _norm(_nama(s)) for k in _PENGATURAN)]
        if bersih:
            cocok = bersih
    if len(cocok) > 1:
        daftar = ", ".join(f"{_nama(s)} [{s['entity_id']}]" for s in cocok[:8])
        return None, f"Nama '{nama}' cocok dengan beberapa perangkat: {daftar}. Sebutkan lebih spesifik."
    return cocok[0], None


def _jalankan(fn):
    try:
        return fn()
    except HAError as e:
        return {"success": False, "result": str(e)}


# ---------------------------------------------------------------- aksi

def daftar_perangkat():
    out = []
    for st in _semua_state():
        dom = st["entity_id"].split(".")[0]
        if dom in DOMAIN_KONTROL:
            out.append({"nama": _nama(st), "entity_id": st["entity_id"], "status": st["state"]})
    out.sort(key=lambda x: x["entity_id"])
    return {"success": True, "jumlah": len(out), "perangkat": out}


def nyala_mati(nama, nyala):
    st, err = _satu(nama, DOMAIN_NYALA)
    if err:
        return {"success": False, "result": err}
    _service("homeassistant", "turn_on" if nyala else "turn_off", {"entity_id": st["entity_id"]})
    return {"success": True, "perangkat": _nama(st), "aksi": "dinyalakan" if nyala else "dimatikan"}


def atur_lampu(nama, kecerahan=0, warna="", suhu_warna=0):
    st, err = _satu(nama, {"light"})
    if err:
        return {"success": False, "result": err}
    data = {"entity_id": st["entity_id"]}
    try:
        kecerahan = int(kecerahan)
    except (TypeError, ValueError):
        kecerahan = 0
    if kecerahan > 0:
        data["brightness_pct"] = max(10, min(100, kecerahan))
    wrn = (warna or "").strip().lower()
    if wrn:
        if wrn not in WARNA:
            return {"success": False, "result": f"Warna '{warna}' tidak dikenal. Pilihan: {', '.join(WARNA)}"}
        data["rgb_color"] = list(WARNA[wrn])
    elif suhu_warna:
        data["color_temp_kelvin"] = max(2000, min(6500, int(suhu_warna)))
    _service("light", "turn_on", data)
    data.pop("entity_id")
    return {"success": True, "perangkat": _nama(st), "diatur": data}


def tekan_tombol(nama):
    st, err = _satu(nama, {"button"})
    if err:
        return {"success": False, "result": err}
    _service("button", "press", {"entity_id": st["entity_id"]})
    return {"success": True, "perangkat": _nama(st), "aksi": "ditekan"}


def atur_nilai(nama, nilai):
    st, err = _satu(nama, {"number"})
    if err:
        return {"success": False, "result": err}
    _service("number", "set_value", {"entity_id": st["entity_id"], "value": float(nilai)})
    return {"success": True, "perangkat": _nama(st), "nilai": nilai}


_KATA_PAKAN = ("feed", "pakan", "makan", "momoi")
_KATA_BUKAN = ("slow", "child", "lock", "weight", "report", "history", "record", "voice",
               "volume", "light", "sound", "reset", "count")


def _kandidat_pakan(nama=""):
    """Cari entitas button/number milik pakan hewan. Kembalikan list state."""
    states = _semua_state()
    ent = os.environ.get("HA_PAKAN", "").strip()
    if ent:
        return [s for s in states if s["entity_id"] == ent]

    kata = _norm(nama).split()
    hasil = []
    for st in states:
        if st["entity_id"].split(".")[0] not in ("button", "number"):
            continue
        hay = _norm(_nama(st)) + " " + _norm(st["entity_id"].split(".", 1)[1])
        if not any(k in hay for k in _KATA_PAKAN):
            continue
        if any(k in hay for k in _KATA_BUKAN):
            continue
        if kata and not all(k in hay for k in kata):
            continue
        hasil.append(st)
    # utamakan tombol, lalu yang bernama manual/feed
    hasil.sort(key=lambda s: (s["entity_id"].startswith("number."),
                              0 if "manual" in s["entity_id"] else 1))
    return hasil


def beri_makan(porsi=1, nama=""):
    maks = int(os.environ.get("HA_PORSI_MAKS", "5"))
    try:
        porsi = int(porsi)
    except (TypeError, ValueError):
        porsi = 1
    porsi = max(1, min(maks, porsi))

    kand = _kandidat_pakan(nama)
    if not kand:
        terkait = [f"{_nama(s)} [{s['entity_id']}]" for s in _semua_state()
                   if any(k in (_norm(_nama(s)) + " " + s["entity_id"]) for k in _KATA_PAKAN)]
        return {"success": False,
                "result": "Entitas pakan (button/number) tidak ditemukan di Home Assistant. "
                          "Entitas terkait yang ada: " + (", ".join(terkait[:10]) or "tidak ada")
                          + ". Atur HA_PAKAN=<entity_id> di .env jika namanya tidak biasa."}
    st = kand[0]
    dom = st["entity_id"].split(".")[0]
    if dom == "button":
        _service("button", "press", {"entity_id": st["entity_id"]})
        return {"success": True, "perangkat": _nama(st), "aksi": "tombol makan ditekan"}

    a = st.get("attributes", {})
    nilai = max(float(a.get("min", 1)), min(float(a.get("max", maks)), float(porsi)))
    _service("number", "set_value", {"entity_id": st["entity_id"], "value": nilai})
    return {"success": True, "perangkat": _nama(st), "porsi": int(nilai)}


def status(nama):
    cocok = _cocok(nama)
    if not cocok:
        return {"success": False, "result": f"Perangkat '{nama}' tidak ditemukan di Home Assistant."}
    out = []
    for st in cocok[:12]:
        a = st.get("attributes", {})
        item = {"nama": _nama(st), "status": st["state"]}
        if a.get("unit_of_measurement"):
            item["satuan"] = a["unit_of_measurement"]
        if "brightness" in a and a["brightness"] is not None:
            item["kecerahan_persen"] = round(a["brightness"] * 100 / 255)
        out.append(item)
    return {"success": True, "perangkat": out}


# ---------------------------------------------------------------- tool MCP

def register(mcp):
    """Daftarkan tool perangkat Tuya (via Home Assistant) ke server FastMCP yang sudah ada."""

    @mcp.tool()
    def daftar_perangkat_rumah() -> dict:
        """
        Tampilkan daftar perangkat Tuya/Home Assistant yang bisa dikontrol (lampu depan,
        colokan, pakan kucing, dll). Gunakan hanya saat user bertanya perangkat apa saja yang ada.
        """
        return _jalankan(daftar_perangkat)

    @mcp.tool()
    def nyalakan_perangkat_rumah(nama: str) -> dict:
        """
        Nyalakan perangkat Tuya via Home Assistant: lampu depan / lampu teras, colokan atau
        stop kontak lemari, dan sejenisnya. Bukan untuk lampu WiZ (kamar, keluarga, dapur).
        nama: nama perangkat sesuai ucapan user, mis. "lampu depan", "stok kontak lemari".
        """
        logger.info(f"HA nyalakan: {nama}")
        return _jalankan(lambda: nyala_mati(nama, True))

    @mcp.tool()
    def matikan_perangkat_rumah(nama: str) -> dict:
        """
        Matikan perangkat Tuya via Home Assistant: lampu depan / lampu teras, colokan atau
        stop kontak lemari, dan sejenisnya. Bukan untuk lampu WiZ (kamar, keluarga, dapur).
        nama: nama perangkat sesuai ucapan user, mis. "lampu depan", "stok kontak lemari".
        """
        logger.info(f"HA matikan: {nama}")
        return _jalankan(lambda: nyala_mati(nama, False))

    @mcp.tool()
    def atur_lampu_rumah(nama: str, kecerahan: int = 0, warna: str = "", suhu_warna: int = 0) -> dict:
        """
        Atur lampu Tuya via Home Assistant, mis. lampu depan (otomatis menyala). Isi hanya yang diminta.
        nama: nama lampu, mis. "lampu depan".
        kecerahan: 10 sampai 100 persen (0 = tidak diubah).
        warna: merah, hijau, biru, kuning, oranye, ungu, pink, cyan, biru muda, putih.
        suhu_warna: 2000 (kuning hangat) sampai 6500 (putih dingin), untuk cahaya putih (0 = tidak diubah).
        Prioritas: warna > suhu_warna.
        """
        logger.info(f"HA atur lampu: {nama} {kecerahan} {warna} {suhu_warna}")
        return _jalankan(lambda: atur_lampu(nama, kecerahan, warna, suhu_warna))

    @mcp.tool()
    def tekan_tombol_rumah(nama: str) -> dict:
        """
        Tekan tombol perangkat Tuya via Home Assistant (bukan untuk memberi makan hewan,
        pakai beri_makan_hewan). nama: nama tombol atau perangkatnya.
        """
        logger.info(f"HA tekan tombol: {nama}")
        return _jalankan(lambda: tekan_tombol(nama))

    @mcp.tool()
    def atur_nilai_rumah(nama: str, nilai: float) -> dict:
        """
        Atur nilai angka pada perangkat Tuya via Home Assistant, mis. jumlah porsi pakan kucing
        ('manual feed'). nama: nama entitas angka. nilai: angka yang diminta user.
        """
        logger.info(f"HA atur nilai: {nama} = {nilai}")
        return _jalankan(lambda: atur_nilai(nama, nilai))

    @mcp.tool()
    def status_perangkat_rumah(nama: str) -> dict:
        """
        Cek status perangkat Tuya via Home Assistant (menyala/mati, kecerahan, daya colokan,
        sisa pakan, dll). nama: nama perangkat, mis. "lampu depan", "stok kontak lemari", "momoi".
        """
        return _jalankan(lambda: status(nama))

    return mcp


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")

    # Mode tes dari terminal
    if len(sys.argv) > 1:
        perintah = sys.argv[1]
        nama = sys.argv[2] if len(sys.argv) > 2 else ""
        try:
            if perintah == "daftar":
                hasil = daftar_perangkat()
            elif perintah == "status":
                hasil = status(nama)
            elif perintah == "nyala":
                hasil = nyala_mati(nama, True)
            elif perintah == "mati":
                hasil = nyala_mati(nama, False)
            elif perintah == "tombol":
                hasil = tekan_tombol(nama)
            elif perintah == "makan":
                hasil = beri_makan(int(nama) if nama.isdigit() else 1)
            else:
                hasil = "Perintah: daftar | status <nama> | nyala <nama> | mati <nama> | tombol <nama>"
        except HAError as e:
            hasil = {"success": False, "result": str(e)}
        print(json.dumps(hasil, indent=2, ensure_ascii=False) if isinstance(hasil, dict) else hasil)
        sys.exit(0)

    from fastmcp import FastMCP
    if sys.platform == "win32":
        sys.stderr.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
    register(FastMCP("Perangkat Rumah")).run(transport="stdio")