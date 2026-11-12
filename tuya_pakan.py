# tuya_pakan.py
# Tool MCP untuk memberi makan lewat pakan Tuya (BARDI Smart Pet Feeder) memakai Tuya Cloud API.
# Dipakai karena integrasi Tuya di Home Assistant tidak menyediakan fitur makan untuk model ini.
#
#   pip install tinytuya
#
# Dipakai dengan dua cara:
#   1. Digabung ke kb_search.py:  tuya_pakan.register(mcp)
#   2. Berdiri sendiri:           python -m tuya_pakan
#
# Tes cepat tanpa Xiaozhi:
#   python tuya_pakan.py info        (lihat kode fitur yang didukung perangkat)
#   python tuya_pakan.py makan 1
#
# .env:
#   TUYA_ACCESS_ID=...               (Access ID/Client ID dari iot.tuya.com)
#   TUYA_ACCESS_SECRET=...
#   TUYA_REGION=sg                   (sg = Singapore, us, eu, in, cn)
#   TUYA_PAKAN_ID=...                (Device ID Pakan Momoi)
#   TUYA_PAKAN_CODE=manual_feed      (kode fitur makan; cek lewat 'info')
#   TUYA_PORSI_MAKS=5                (batas porsi per perintah)
import json
import logging
import os
import sys

logger = logging.getLogger("TuyaPakan")


def _cloud():
    try:
        import tinytuya
    except ImportError:
        raise RuntimeError("Modul tinytuya belum terpasang. Jalankan: pip install tinytuya")
    kunci = os.environ.get("TUYA_ACCESS_ID", "").strip()
    rahasia = os.environ.get("TUYA_ACCESS_SECRET", "").strip()
    dev = os.environ.get("TUYA_PAKAN_ID", "").strip()
    if not (kunci and rahasia and dev):
        raise RuntimeError("TUYA_ACCESS_ID, TUYA_ACCESS_SECRET, dan TUYA_PAKAN_ID belum lengkap di .env")
    region = os.environ.get("TUYA_REGION", "sg").strip()
    return tinytuya.Cloud(apiRegion=region, apiKey=kunci, apiSecret=rahasia, apiDeviceID=dev), dev


def info():
    """Tampilkan fungsi, properti, dan status perangkat untuk mencari kode fitur makan."""
    c, dev = _cloud()
    out = {}
    for nama, fn in (("fungsi", "getfunctions"), ("properti", "getproperties"), ("status", "getstatus")):
        f = getattr(c, fn, None)
        if f is None:
            continue
        try:
            out[nama] = f(dev)
        except Exception as e:
            out[nama] = f"gagal: {e}"
    return out


def makan(porsi=1):
    maks = int(os.environ.get("TUYA_PORSI_MAKS", "5"))
    try:
        porsi = int(porsi)
    except (TypeError, ValueError):
        porsi = 1
    porsi = max(1, min(maks, porsi))

    c, dev = _cloud()
    kode = os.environ.get("TUYA_PAKAN_CODE", "manual_feed").strip()
    r = c.sendcommand(dev, {"commands": [{"code": kode, "value": porsi}]})
    if isinstance(r, dict) and r.get("success"):
        return {"success": True, "porsi": porsi}
    pesan = (r or {}).get("msg") if isinstance(r, dict) else str(r)
    return {"success": False,
            "result": f"Perintah makan ditolak Tuya: {pesan}. Cek TUYA_PAKAN_CODE lewat 'python tuya_pakan.py info'."}


def register(mcp):
    """Daftarkan tool pakan Tuya ke server FastMCP yang sudah ada."""

    @mcp.tool()
    def beri_makan_hewan(porsi: int = 1) -> dict:
        """
        Keluarkan makanan dari pakan otomatis (pet feeder) Momoi. Gunakan saat user minta
        'beri makan Momoi / kucing'. porsi: jumlah porsi, default 1 (maksimal 5).
        """
        logger.info(f"Beri makan Momoi: {porsi} porsi")
        try:
            return makan(porsi)
        except Exception as e:
            return {"success": False, "result": str(e)}

    return mcp


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")

    if len(sys.argv) > 1:
        try:
            if sys.argv[1] == "info":
                print(json.dumps(info(), indent=2, ensure_ascii=False, default=str))
            elif sys.argv[1] == "makan":
                print(makan(int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 1))
            else:
                print("Perintah: info | makan [porsi]")
        except Exception as e:
            print(f"Gagal: {e}")
        sys.exit(0)

    from fastmcp import FastMCP
    if sys.platform == "win32":
        sys.stderr.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
    register(FastMCP("Pakan Momoi")).run(transport="stdio")