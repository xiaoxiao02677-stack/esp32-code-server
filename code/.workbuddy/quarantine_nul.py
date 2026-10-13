import os, ctypes, struct
from ctypes import wintypes

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

# Proper signatures (critical on 64-bit: HANDLE is 8 bytes, WORD is 2 bytes).
kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
]
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.MoveFileExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
kernel32.MoveFileExW.restype = wintypes.BOOL
kernel32.SetFileInformationByHandle.argtypes = [
    wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.WORD
]
kernel32.SetFileInformationByHandle.restype = wintypes.BOOL

# \\?\ prefix + BACKSLASHES bypasses DOS device parsing so "nul" is a real file.
src = r"\\?\G:\demo\21_xiaozhi\code\small_secreen\xiaozhi-esp32\nul"
dst_dir = r"G:\demo\21_xiaozhi\.trash"
dst = r"\\?\G:\demo\21_xiaozhi\.trash\nul_quarantine.bin"

os.makedirs(dst_dir, exist_ok=True)

# --- Method 1: MoveFileExW (simplest) ---
ret = kernel32.MoveFileExW(src, dst, 1)  # MOVEFILE_REPLACE_EXISTING = 0x1
if ret:
    print("MoveFileExW OK ->", dst)
else:
    err = ctypes.get_last_error()
    print("MoveFileExW failed (err=%d), trying handle-rename" % err)

    DELETE = 0x00010000
    FILE_SHARE_DELETE = 0x00000004
    OPEN_EXISTING = 3
    FILE_FLAG_POSIX_SEMANTICS = 0x01000000
    FILE_RENAME_INFO = 3

    h = kernel32.CreateFileW(
        ctypes.c_wchar_p(src), DELETE, FILE_SHARE_DELETE, None,
        OPEN_EXISTING, FILE_FLAG_POSIX_SEMANTICS, None,
    )
    print("handle:", h)
    if h == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())

    name_bytes = dst.encode('utf-16-le')
    buf = ctypes.create_string_buffer(16 + len(name_bytes))
    struct.pack_into('B', buf, 0, 1)                 # ReplaceIfExists = TRUE
    struct.pack_into('I', buf, 12, len(name_bytes))  # FileNameLength (bytes)
    ctypes.memmove(ctypes.addressof(buf) + 16, name_bytes, len(name_bytes))

    ok = kernel32.SetFileInformationByHandle(
        h, FILE_RENAME_INFO, ctypes.byref(buf),
        ctypes.c_uint16(16 + len(name_bytes)),
    )
    print("rename ok:", ok)
    if not ok:
        e = ctypes.get_last_error()
        kernel32.CloseHandle(h)
        raise ctypes.WinError(e)
    kernel32.CloseHandle(h)
    print("handle-rename OK ->", dst)
