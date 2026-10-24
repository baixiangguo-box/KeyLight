"""Minimal Win32 HID access layer (ctypes only, no pip packages).

Only what the AULA / RuiLianWei lighting path needs: enumerate every HID
top-level collection with its VID/PID/usage page/usage, product string and
report lengths, then open one interface by device path and write 64-byte
output reports.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes as w

setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
hid = ctypes.WinDLL("hid", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x01
FILE_SHARE_WRITE = 0x02
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", w.DWORD),
        ("Data2", w.WORD),
        ("Data3", w.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", w.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", w.DWORD),
        ("Reserved", ctypes.c_size_t),
    ]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Size", w.ULONG),
        ("VendorID", w.USHORT),
        ("ProductID", w.USHORT),
        ("VersionNumber", w.USHORT),
    ]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", w.USHORT),
        ("UsagePage", w.USHORT),
        ("InputReportByteLength", w.USHORT),
        ("OutputReportByteLength", w.USHORT),
        ("FeatureReportByteLength", w.USHORT),
        ("Reserved", w.USHORT * 17),
        ("NumberLinkCollectionNodes", w.USHORT),
        ("NumberInputButtonCaps", w.USHORT),
        ("NumberInputValueCaps", w.USHORT),
        ("NumberInputDataIndices", w.USHORT),
        ("NumberOutputButtonCaps", w.USHORT),
        ("NumberOutputValueCaps", w.USHORT),
        ("NumberOutputDataIndices", w.USHORT),
        ("NumberFeatureButtonCaps", w.USHORT),
        ("NumberFeatureValueCaps", w.USHORT),
        ("NumberFeatureDataIndices", w.USHORT),
    ]


setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), w.LPCWSTR, w.HWND, w.DWORD]
setupapi.SetupDiEnumDeviceInterfaces.restype = w.BOOL
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GUID), w.DWORD,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = w.BOOL
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA), ctypes.c_void_p,
    w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p,
]
setupapi.SetupDiDestroyDeviceInfoList.restype = w.BOOL
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]

kernel32.CreateFileW.restype = ctypes.c_void_p
kernel32.CreateFileW.argtypes = [
    w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, ctypes.c_void_p,
]
kernel32.CloseHandle.restype = w.BOOL
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
kernel32.WriteFile.restype = w.BOOL
kernel32.WriteFile.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p,
]

hid.HidD_GetPreparsedData.restype = w.BOOL
hid.HidD_GetPreparsedData.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
hid.HidD_FreePreparsedData.restype = w.BOOL
hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
hid.HidP_GetCaps.restype = ctypes.c_long
hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
hid.HidD_GetAttributes.restype = w.BOOL
hid.HidD_GetAttributes.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDD_ATTRIBUTES)]
hid.HidD_GetProductString.restype = w.BOOL
hid.HidD_GetProductString.argtypes = [ctypes.c_void_p, ctypes.c_void_p, w.ULONG]
hid.HidD_GetManufacturerString.restype = w.BOOL
hid.HidD_GetManufacturerString.argtypes = [ctypes.c_void_p, ctypes.c_void_p, w.ULONG]

HID_GUID = GUID(
    0x4D1E55B2, 0xF16F, 0x11CF,
    (ctypes.c_ubyte * 8)(0x88, 0xCB, 0x00, 0x11, 0x11, 0x00, 0x00, 0x30),
)


def _string(fn, handle) -> str:
    buf = ctypes.create_string_buffer(512)
    if fn(handle, buf, 512):
        return buf.raw.decode("utf-16-le", "ignore").split("\x00")[0]
    return ""


def _paths() -> list[str]:
    hdev = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(HID_GUID), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    )
    if not hdev or hdev == INVALID_HANDLE_VALUE:
        raise OSError("SetupDiGetClassDevs failed")
    out: list[str] = []
    idx = 0
    try:
        while True:
            did = SP_DEVICE_INTERFACE_DATA()
            did.cbSize = ctypes.sizeof(did)
            if not setupapi.SetupDiEnumDeviceInterfaces(
                hdev, None, ctypes.byref(HID_GUID), idx, ctypes.byref(did)
            ):
                break
            idx += 1
            need = w.DWORD(0)
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                hdev, ctypes.byref(did), None, 0, ctypes.byref(need), None
            )
            buf = ctypes.create_string_buffer(max(need.value, 64) + 8)
            ctypes.c_uint32.from_buffer(buf, 0).value = 8  # cbSize on x64
            if setupapi.SetupDiGetDeviceInterfaceDetailW(
                hdev, ctypes.byref(did), buf, len(buf), ctypes.byref(need), None
            ):
                out.append(ctypes.wstring_at(ctypes.addressof(buf) + 4))
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(hdev)
    return out


def _open(path: str, write: bool = True):
    access = GENERIC_READ | (GENERIC_WRITE if write else 0)
    handle = kernel32.CreateFileW(
        path, access, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None
    )
    if handle == INVALID_HANDLE_VALUE or not handle:
        return None
    return handle


def enumerate_devices() -> list[dict]:
    """Every HID interface present, with the fields needed to pick an endpoint."""
    found = []
    for path in _paths():
        handle = _open(path, write=False)
        if not handle:
            handle = _open(path, write=True)
        if not handle:
            continue
        try:
            att = HIDD_ATTRIBUTES()
            att.Size = ctypes.sizeof(att)
            hid.HidD_GetAttributes(handle, ctypes.byref(att))
            caps = HIDP_CAPS()
            preparsed = ctypes.c_void_p()
            if hid.HidD_GetPreparsedData(handle, ctypes.byref(preparsed)):
                hid.HidP_GetCaps(preparsed, ctypes.byref(caps))
                hid.HidD_FreePreparsedData(preparsed)
            found.append({
                "path": path,
                "vid": att.VendorID,
                "pid": att.ProductID,
                "version": att.VersionNumber,
                "usage_page": caps.UsagePage,
                "usage": caps.Usage,
                "in_len": caps.InputReportByteLength,
                "out_len": caps.OutputReportByteLength,
                "feature_len": caps.FeatureReportByteLength,
                "product": _string(hid.HidD_GetProductString, handle),
                "manufacturer": _string(hid.HidD_GetManufacturerString, handle),
            })
        finally:
            kernel32.CloseHandle(handle)
    return found


class HidDevice:
    """One opened HID interface."""

    def __init__(self, path: str):
        self.path = path
        self._handle = None
        self.out_len = 0

    def open(self) -> None:
        handle = _open(self.path, write=True)
        if not handle:
            raise OSError(f"cannot open HID path: {self.path}")
        self._handle = handle
        caps = HIDP_CAPS()
        preparsed = ctypes.c_void_p()
        if hid.HidD_GetPreparsedData(handle, ctypes.byref(preparsed)):
            hid.HidP_GetCaps(preparsed, ctypes.byref(caps))
            hid.HidD_FreePreparsedData(preparsed)
        self.out_len = caps.OutputReportByteLength

    def write(self, data: bytes) -> int:
        if not self._handle:
            raise OSError("device not open")
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        written = w.DWORD(0)
        if not kernel32.WriteFile(
            self._handle, buf, len(data), ctypes.byref(written), None
        ):
            raise OSError(f"WriteFile failed, error {ctypes.get_last_error()}")
        return written.value

    def close(self) -> None:
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()
