import ctypes
from ctypes import wintypes
from pathlib import Path


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def build_data_blob(data):
    if not data:
        return DATA_BLOB(0, None), None
    buffer = ctypes.create_string_buffer(data, len(data))
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def protect_dpapi_bytes(raw_bytes, entropy):
    if not raw_bytes:
        return b""

    blob_in, buffer_in = build_data_blob(raw_bytes)
    blob_entropy, buffer_entropy = build_data_blob(entropy)
    blob_out = DATA_BLOB()
    result = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        None,
        ctypes.byref(blob_entropy),
        None,
        None,
        0,
        ctypes.byref(blob_out),
    )
    if not result:
        raise ctypes.WinError()

    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def unprotect_dpapi_bytes(protected_bytes, entropy):
    if not protected_bytes:
        return b""

    blob_in, buffer_in = build_data_blob(protected_bytes)
    blob_entropy, buffer_entropy = build_data_blob(entropy)
    blob_out = DATA_BLOB()
    result = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        ctypes.byref(blob_entropy),
        None,
        None,
        0,
        ctypes.byref(blob_out),
    )
    if not result:
        raise ctypes.WinError()

    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def read_protected_text(path, entropy, encoding="utf-8", unprotect_bytes=None):
    path = Path(path)
    if not path.exists():
        return ""
    unprotect_bytes = unprotect_bytes or unprotect_dpapi_bytes
    raw_bytes = unprotect_bytes(path.read_bytes(), entropy)
    return raw_bytes.decode(encoding, errors="ignore").strip()


def write_protected_text(path, text, entropy, encoding="utf-8", protect_bytes=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    protect_bytes = protect_bytes or protect_dpapi_bytes
    protected_bytes = protect_bytes(str(text or "").encode(encoding), entropy)
    path.write_bytes(protected_bytes)
    return path


def delete_secure_files(*paths):
    for path in paths:
        try:
            path = Path(path)
            if path.exists():
                path.unlink()
        except OSError:
            pass
