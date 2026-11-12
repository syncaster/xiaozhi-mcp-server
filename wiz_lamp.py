# wiz_lamp.py
# Tool MCP untuk mengontrol lampu pintar Philips WiZ lewat API lokal (UDP 38899).
#
# Dipakai dengan dua cara:
#   1. Digabung ke kb_search.py:  wiz_lamp.register(mcp)
#   2. Berdiri sendiri:           python -m wiz_lamp
#
# Tes cepat tanpa Xiaozhi:
#   python wiz_lamp.py cari
#   python wiz_lamp.py status [nama/ip]
#   python wiz_lamp.py nyala  [nama/ip]
#   python wiz_lamp.py mati   [nama/ip]
#
# .env (beri nama tiap lampu, pisahkan koma):
#   WIZ_LAMPS=kamar=192.168.100.11,keluarga=192.168.100.12,dapur=192.168.100.13
#   WIZ_SUBNET=192.168.100         (opsional, untuk pencarian; otomatis terdeteksi jika kosong)
#   WIZ_IP=...                     (cara lama, masih didukung, tanpa nama)
import json
import logging
import os
import re
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger("WizLamp")

PORT = 38899

WARNA = {
    "merah": (255, 0, 0), "hijau": (0, 255, 0), "biru": (0, 0, 255),
    "kuning": (255, 220, 0), "oranye": (255, 120, 0), "jingga": (255, 120, 0),
    "ungu": (150, 0, 255), "pink": (255, 60, 150), "merah muda": (255, 60, 150),
    "cyan": (0, 255, 255), "biru muda": (0, 200, 255), "putih": (255, 255, 255),
}

# Suasana bawaan WiZ (sceneId)
SUASANA = {
    "laut": 1, "romantis": 2, "matahari terbenam": 3, "pesta": 4, "perapian": 5,
    "nyaman": 6, "hutan": 7, "bangun tidur": 9, "tidur": 10, "putih hangat": 11,
    "siang": 12, "putih dingin": 13, "lampu tidur": 14, "fokus": 15, "santai": 16,
    "nonton tv": 18, "lilin": 29, "klub": 26,
}

_POLA_IP = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


# ---------------------------------------------------------------- konfigurasi

def _peta_lampu():
    """Kembalikan dict {nama: ip} dari WIZ_LAMPS (dan WIZ_IP versi lama)."""
    peta = {}
    for item in os.environ.get("WIZ_LAMPS", "").split(","):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            nama, ip = item.split("=", 1)
            peta[nama.strip().lower()] = ip.strip()
        else:
            peta[item] = item
    for ip in os.environ.get("WIZ_IP", "").split(","):
        ip = ip.strip()
        if ip and ip not in peta.values():
            peta[ip] = ip
    return peta


def _pilih(lampu=""):
    """Tentukan lampu mana yang dikontrol. Kosong / 'semua' = semua lampu."""
    peta = _peta_lampu()
    if not peta:
        raise ValueError("WIZ_LAMPS belum diatur di .env")

    q = (lampu or "").strip().lower()
    if q.startswith("lampu "):
        q = q[6:].strip()
    if q in ("", "semua", "all", "seluruh"):
        return list(peta.items())

    if _POLA_IP.match(q):
        return [(q, q)]
    if q in peta:
        return [(q, peta[q])]

    # Cocok sebagian: "kamar tidur" cocok dengan "kamar", "ruang keluarga" cocok dengan "keluarga"
    cocok = [(n, ip) for n, ip in peta.items() if n in q or q in n]
    if cocok:
        return cocok

    raise ValueError(f"Lampu '{lampu}' tidak dikenal. Pilihan: {', '.join(peta)}")


# ---------------------------------------------------------------- komunikasi

def _kirim(ip, method, params=None, percobaan=3):
    """Kirim satu perintah UDP ke lampu dan kembalikan balasannya (dict)."""
    pesan = {"method": method}
    if params is not None:
        pesan["params"] = params
    data = json.dumps(pesan).encode()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(1.5)
        for _ in range(percobaan):
            try:
                s.sendto(data, (ip, PORT))
                resp, _ = s.recvfrom(2048)
                return json.loads(resp)
            except socket.timeout:
                continue
    raise TimeoutError(f"Lampu {ip} tidak merespons. Cek IP, WiFi, dan 'komunikasi lokal' di aplikasi WiZ.")


def _ke_lampu(method, params=None, lampu=""):
    try:
        target = _pilih(lampu)
    except ValueError as e:
        return {"success": False, "result": str(e)}

    def kerja(item):
        nama, ip = item
        try:
            r = _kirim(ip, method, params)
            return True, {"lampu": nama, "ip": ip, "respons": r.get("result", r)}
        except Exception as e:
            return False, f"{nama} ({ip}): {e}"

    with ThreadPoolExecutor(max_workers=len(target)) as ex:
        semua = list(ex.map(kerja, target))

    hasil = [x for ok, x in semua if ok]
    gagal = [x for ok, x in semua if not ok]
    if gagal and not hasil:
        return {"success": False, "result": "; ".join(gagal)}
    out = {"success": True, "lampu": hasil}
    if gagal:
        out["gagal"] = gagal
    return out


# ---------------------------------------------------------------- pencarian

def _prefix_subnet():
    """Kumpulkan awalan subnet /24 (mis. '192.168.100') yang perlu dipindai."""
    prefix = set()
    env = os.environ.get("WIZ_SUBNET", "").strip().rstrip(".")
    if env:
        prefix.add(env)

    ips = [ip for ip in _peta_lampu().values() if _POLA_IP.match(ip)]
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
    except Exception:
        pass
    try:
        ips += socket.gethostbyname_ex(socket.gethostname())[2]
    except Exception:
        pass

    for ip in ips:
        if ip.startswith(("192.168.", "10.", "172.")):
            prefix.add(ip.rsplit(".", 1)[0])
    return sorted(prefix)


def cari_lampu(detik=3.0):
    """Pindai subnet (unicast ke tiap IP + broadcast), kembalikan lampu WiZ yang menjawab."""
    data = json.dumps({"method": "getPilot", "params": {}}).encode()
    nama_dari_ip = {ip: n for n, ip in _peta_lampu().items()}
    ditemukan = {}

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(0.3)

        def tembak():
            for p in _prefix_subnet():
                for i in range(1, 256):
                    try:
                        s.sendto(data, (f"{p}.{i}", PORT))
                    except OSError:
                        pass
            try:
                s.sendto(data, ("255.255.255.255", PORT))
            except OSError:
                pass

        akhir = time.time() + detik
        putaran_dua = time.time() + detik / 2
        tembak()
        sudah_dua = False
        while time.time() < akhir:
            if not sudah_dua and time.time() >= putaran_dua:
                tembak()
                sudah_dua = True
            try:
                resp, addr = s.recvfrom(2048)
                r = json.loads(resp).get("result", {})
                if "mac" not in r and "state" not in r:
                    continue
                ip = addr[0]
                ditemukan[ip] = {"ip": ip, "mac": r.get("mac", ""),
                                 "menyala": r.get("state"),
                                 "nama": nama_dari_ip.get(ip, "(belum diberi nama di .env)")}
            except socket.timeout:
                continue
            except Exception:
                continue
    return sorted(ditemukan.values(), key=lambda x: tuple(int(o) for o in x["ip"].split(".")))


# ---------------------------------------------------------------- tool MCP

def register(mcp):
    """Daftarkan tool lampu WiZ ke server FastMCP yang sudah ada."""

    @mcp.tool()
    def nyalakan_lampu_pintar(lampu: str = "") -> dict:
        """
        Nyalakan lampu pintar WiZ di rumah (bukan LED merah di perangkat ini).
        lampu: nama lampu yang diminta user (mis. kamar, keluarga, dapur).
               Kosongkan HANYA jika user minta semua lampu.
        """
        logger.info(f"Nyalakan lampu WiZ: {lampu or 'semua'}")
        return _ke_lampu("setPilot", {"state": True}, lampu)

    @mcp.tool()
    def matikan_lampu_pintar(lampu: str = "") -> dict:
        """
        Matikan lampu pintar WiZ di rumah (bukan LED merah di perangkat ini).
        lampu: nama lampu yang diminta user (mis. kamar, keluarga, dapur).
               Kosongkan HANYA jika user minta semua lampu.
        """
        logger.info(f"Matikan lampu WiZ: {lampu or 'semua'}")
        return _ke_lampu("setPilot", {"state": False}, lampu)

    @mcp.tool()
    def atur_lampu_pintar(lampu: str = "", kecerahan: int = 0, warna: str = "",
                          suhu_warna: int = 0, suasana: str = "") -> dict:
        """
        Atur lampu pintar WiZ di rumah (otomatis menyala). Isi hanya yang diminta user.
        lampu: nama lampu (mis. kamar, keluarga, dapur). Kosongkan HANYA jika user minta semua lampu.
        kecerahan: 10 sampai 100 persen (0 = tidak diubah).
        warna: nama warna: merah, hijau, biru, kuning, oranye, ungu, pink, cyan, biru muda, putih.
        suhu_warna: 2200 (kuning hangat) sampai 6500 (putih dingin), untuk lampu putih (0 = tidak diubah).
        suasana: romantis, laut, pesta, santai, fokus, nyaman, hutan, lilin, nonton tv, tidur,
                 bangun tidur, putih hangat, putih dingin, siang, lampu tidur, perapian, klub.
        Prioritas: suasana > warna > suhu_warna.
        """
        params = {"state": True}
        try:
            kecerahan = int(kecerahan)
        except (TypeError, ValueError):
            kecerahan = 0
        if kecerahan > 0:
            params["dimming"] = max(10, min(100, kecerahan))

        nama = (suasana or "").strip().lower()
        wrn = (warna or "").strip().lower()
        if nama:
            if nama not in SUASANA:
                return {"success": False,
                        "result": f"Suasana '{suasana}' tidak dikenal. Pilihan: {', '.join(SUASANA)}"}
            params["sceneId"] = SUASANA[nama]
        elif wrn:
            if wrn not in WARNA:
                return {"success": False,
                        "result": f"Warna '{warna}' tidak dikenal. Pilihan: {', '.join(WARNA)}"}
            params["r"], params["g"], params["b"] = WARNA[wrn]
        elif suhu_warna:
            params["temp"] = max(2200, min(6500, int(suhu_warna)))

        logger.info(f"Atur lampu WiZ ({lampu or 'semua'}): {params}")
        return _ke_lampu("setPilot", params, lampu)

    @mcp.tool()
    def status_lampu_pintar(lampu: str = "") -> dict:
        """
        Cek apakah lampu pintar WiZ di rumah sedang menyala, beserta kecerahan dan warnanya.
        lampu: nama lampu tertentu, atau kosong untuk semua lampu.
        """
        return _ke_lampu("getPilot", None, lampu)

    @mcp.tool()
    def cari_lampu_pintar_di_jaringan() -> dict:
        """
        Cari lampu WiZ yang ada di jaringan WiFi untuk mengetahui alamat IP-nya.
        Gunakan hanya saat user minta mencari / mendeteksi lampu.
        """
        daftar = cari_lampu()
        if not daftar:
            return {"success": False, "result": "Tidak ada lampu WiZ yang menjawab."}
        return {"success": True, "jumlah": len(daftar), "lampu": daftar}

    return mcp


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")

    # Mode tes dari terminal
    if len(sys.argv) > 1:
        perintah = sys.argv[1]
        target = sys.argv[2] if len(sys.argv) > 2 else ""
        if perintah == "cari":
            print(json.dumps(cari_lampu(), indent=2, ensure_ascii=False))
        elif perintah == "status":
            print(json.dumps(_ke_lampu("getPilot", None, target), indent=2, ensure_ascii=False))
        elif perintah == "nyala":
            print(_ke_lampu("setPilot", {"state": True}, target))
        elif perintah == "mati":
            print(_ke_lampu("setPilot", {"state": False}, target))
        else:
            print("Perintah: cari | status [nama] | nyala [nama] | mati [nama]")
        sys.exit(0)

    from fastmcp import FastMCP
    if sys.platform == "win32":
        sys.stderr.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
    register(FastMCP("Lampu WiZ")).run(transport="stdio")