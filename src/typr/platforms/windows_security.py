"""Read-only Win32 ACL checks for secret persistence, not an ACL editor.

Only the token user, SYSTEM and built-in Administrators may access secret files.
Ancestors may grant non-inheritable read/list access (never mutation).
Unknown ACE forms, null DACLs, reparse points and non-profile locations fail closed.
No ACLs or profile settings are modified.
"""

import ctypes as C
import os
from ctypes import wintypes as W
from pathlib import Path


class ACL(C.Structure):
    _fields_ = [("revision", W.BYTE), ("reserved", W.BYTE), ("size", W.WORD),
                ("count", W.WORD), ("reserved2", W.WORD)]


class ACE_HEADER(C.Structure):
    _fields_ = [("kind", W.BYTE), ("flags", W.BYTE), ("size", W.WORD)]


class SID_AND_ATTRIBUTES(C.Structure):
    _fields_ = [("sid", C.c_void_p), ("attributes", W.DWORD)]


def _bind(dll, name, args, result):
    function = getattr(dll, name)
    function.argtypes = args
    function.restype = result
    return function


def check_private_path(path: Path, *, allow_missing: bool = False) -> None:
    """Validate real profile ancestry and actual (including inherited) DACLs."""
    kernel = C.WinDLL("kernel32", use_last_error=True)
    advapi = C.WinDLL("advapi32", use_last_error=True)
    userenv = C.WinDLL("userenv", use_last_error=True)
    ptr = C.c_void_p
    current = _bind(kernel, "GetCurrentProcess", [], W.HANDLE)
    close = _bind(kernel, "CloseHandle", [W.HANDLE], W.BOOL)
    free = _bind(kernel, "LocalFree", [ptr], ptr)
    open_token = _bind(advapi, "OpenProcessToken", [W.HANDLE, W.DWORD,
                       C.POINTER(W.HANDLE)], W.BOOL)
    token_info = _bind(advapi, "GetTokenInformation", [W.HANDLE, C.c_int, ptr,
                       W.DWORD, C.POINTER(W.DWORD)], W.BOOL)
    profile_dir = _bind(userenv, "GetUserProfileDirectoryW", [W.HANDLE, W.LPWSTR,
                        C.POINTER(W.DWORD)], W.BOOL)
    sid_string = _bind(advapi, "ConvertSidToStringSidW", [ptr, C.POINTER(ptr)], W.BOOL)
    security = _bind(advapi, "GetNamedSecurityInfoW", [W.LPWSTR, C.c_int, W.DWORD,
                     C.POINTER(ptr), ptr, C.POINTER(ptr), ptr, C.POINTER(ptr)], W.DWORD)
    get_ace = _bind(advapi, "GetAce", [ptr, W.DWORD, C.POINTER(ptr)], W.BOOL)

    def require(result):
        if not result:
            raise C.WinError(C.get_last_error())

    def sid_text(sid):
        text = ptr()
        require(sid_string(sid, C.byref(text)))
        try:
            return C.wstring_at(text)
        finally:
            free(text)

    token = W.HANDLE()
    require(open_token(current(), 0x0008, C.byref(token)))  # TOKEN_QUERY
    try:
        size = W.DWORD()
        token_info(token, 1, None, 0, C.byref(size))  # TokenUser
        buffer = C.create_string_buffer(size.value)
        require(token_info(token, 1, buffer, size, C.byref(size)))
        user = sid_text(C.cast(buffer, C.POINTER(SID_AND_ATTRIBUTES)).contents.sid)
        size = W.DWORD(32768)
        profile = C.create_unicode_buffer(size.value)
        require(profile_dir(token, profile, C.byref(size)))
    finally:
        close(token)

    root = Path(profile.value)
    # Lexical comparison deliberately precedes resolve: never follow reparse points.
    path = Path(os.path.abspath(path))
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise OSError("Typr secrets must remain inside the token user's profile") from error
    trusted = {user, "S-1-5-18", "S-1-5-32-544"}
    for candidate in [root, *(root.joinpath(*relative.parts[:i])
                              for i in range(1, len(relative.parts) + 1))]:
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            if allow_missing:
                continue
            raise
        if info.st_file_attributes & 0x400:  # FILE_ATTRIBUTE_REPARSE_POINT
            raise OSError(f"Reparse point in private Typr path: {candidate}")
        owner, dacl, descriptor = ptr(), ptr(), ptr()
        result = security(str(candidate), 1, 0x5, C.byref(owner), None,
                          C.byref(dacl), None, C.byref(descriptor))
        if result:
            raise C.WinError(result)
        try:
            if not owner or sid_text(owner) not in trusted or not dacl:
                raise OSError(f"Untrusted owner or null DACL: {candidate}")
            acl = C.cast(dacl, C.POINTER(ACL)).contents
            for index in range(acl.count):
                ace = ptr()
                require(get_ace(dacl, index, C.byref(ace)))
                header = C.cast(ace, C.POINTER(ACE_HEADER)).contents
                if header.kind == 1:  # ACCESS_DENIED_ACE cannot grant access
                    continue
                if header.kind != 0 or header.size < 16:
                    raise OSError(f"Unsupported ACE in private Typr path: {candidate}")
                # ACCESS_ALLOWED_ACE: header (4), ACCESS_MASK (4), variable SID.
                sid = sid_text(ace.value + 8)
                mask = C.cast(ace.value + 4, C.POINTER(W.DWORD)).contents.value
                # Ancestor listing alone does not expose file contents. However,
                # mutation or inherited access can compromise future children.
                mutation = 0x10000000 | 0x40000000 | 0xD0156
                safe_ancestor_read = (
                    candidate != path and not header.flags & 0x03 and not mask & mutation
                )
                # OWNER RIGHTS refers to this object's owner, already verified
                # above. It is not an unrelated principal or a wildcard user.
                if sid not in trusted and sid != "S-1-3-4" and not safe_ancestor_read:
                    raise OSError(
                        f"Non-private DACL in Typr path: {candidate} "
                        f"(SID {sid}, flags {header.flags:#x})"
                    )
        finally:
            free(descriptor)
