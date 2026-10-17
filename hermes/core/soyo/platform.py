# SPDX-License-Identifier: MIT
"""Platform boundaries shared by the launcher and isolated business workers.

Windows private files use DACLs, not misleading POSIX mode bits. Missing ACL
support is an error, never a reason to silently accept a public credential.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import stat
import sys
import subprocess
import time

WINDOWS = os.name == "nt"


def uid():
    return os.getuid() if hasattr(os, "getuid") else None


def is_root():
    return uid() == 0


def public_mode(mode):
    # Call assert_private/open_private as well: on NTFS the DACL is authoritative.
    return not WINDOWS and bool(mode & 0o077)


def is_link(path):
    path = Path(path)
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def _windows_security():
    import win32api
    import win32con
    import win32security as security
    token = security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        owner = security.GetTokenInformation(token, security.TokenUser)[0]
    finally:
        token.Close()
    trusted = {security.ConvertSidToStringSid(owner), "S-1-5-18", "S-1-5-32-544"}
    return security, owner, trusted


def assert_private(path, *, max_bytes=None, directory=False):
    path = Path(path)
    info = path.lstat()
    if not path.is_absolute() or is_link(path) or any(is_link(parent) for parent in path.parents):
        raise ValueError("private_path_must_be_absolute_and_unlinked")
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ValueError("private_path_type_rejected")
    if max_bytes is not None and info.st_size > max_bytes:
        raise ValueError("private_file_size_exceeded")
    if WINDOWS:
        security, _owner, trusted = _windows_security()
        descriptor = security.GetNamedSecurityInfo(str(path), security.SE_FILE_OBJECT,
            security.OWNER_SECURITY_INFORMATION | security.DACL_SECURITY_INFORMATION)
        owner = descriptor.GetSecurityDescriptorOwner()
        dacl = descriptor.GetSecurityDescriptorDacl()
        if owner is None or security.ConvertSidToStringSid(owner) not in trusted or dacl is None:
            raise ValueError("private_file_owner_or_dacl_rejected")
        allowed = {security.ACCESS_ALLOWED_ACE_TYPE,
                   getattr(security, "ACCESS_ALLOWED_OBJECT_ACE_TYPE", 5)}
        denied = {security.ACCESS_DENIED_ACE_TYPE,
                  getattr(security, "ACCESS_DENIED_OBJECT_ACE_TYPE", 6)}
        for index in range(dacl.GetAceCount()):
            ace = dacl.GetAce(index)
            kind = ace[0][0]
            if kind in allowed:
                if security.ConvertSidToStringSid(ace[-1]) not in trusted:
                    raise ValueError("private_file_grants_other_principals")
            elif kind not in denied:
                raise ValueError("unsupported_private_file_ace")
    elif public_mode(info.st_mode) or info.st_uid not in {uid(), 0}:
        raise ValueError("private_file_permissions_rejected")
    return info


def protect(path, *, directory=False):
    path = Path(path)
    if is_link(path):
        raise ValueError("refusing_to_protect_link")
    if WINDOWS:
        security, owner, _trusted = _windows_security()
        dacl = security.ACL()
        inheritance = 0x03 if directory else 0  # OBJECT/CONTAINER_INHERIT_ACE
        for sid in (owner, security.ConvertStringSidToSid("S-1-5-18"),
                    security.ConvertStringSidToSid("S-1-5-32-544")):
            dacl.AddAccessAllowedAceEx(security.ACL_REVISION, inheritance, 0x1F01FF, sid)
        security.SetNamedSecurityInfo(str(path), security.SE_FILE_OBJECT,
            security.DACL_SECURITY_INFORMATION | security.PROTECTED_DACL_SECURITY_INFORMATION,
            None, None, dacl, None)
    else:
        path.chmod(0o700 if directory else 0o600)
    assert_private(path, directory=directory)


def private_fchmod(fd, mode):
    if not WINDOWS:
        os.fchmod(fd, mode)
        return
    import msvcrt
    import win32file
    # A CRT-created descriptor does not necessarily carry WRITE_DAC. Reopen
    # the same, handle-derived filename for SetNamedSecurityInfo instead of
    # pretending fchmod or SetSecurityInfo on that descriptor is sufficient.
    name = win32file.GetFinalPathNameByHandle(msvcrt.get_osfhandle(fd), 0)
    if name.startswith('\\\\?\\UNC\\'): name = '\\\\' + name[8:]
    elif name.startswith('\\\\?\\'): name = name[4:]
    path = Path(name)
    if path.stat().st_ino != os.fstat(fd).st_ino:
        raise ValueError('private_file_handle_path_changed')
    protect(path)


def open_private(path, flags=os.O_RDONLY, mode=0o600):
    path = Path(path)
    if not path.is_absolute() or is_link(path):
        raise ValueError("private_path_rejected")
    fd = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0), mode)
    try:
        if flags & os.O_CREAT:
            private_fchmod(fd, mode)
        assert_private(path)
        if os.fstat(fd).st_ino != path.stat().st_ino:
            raise ValueError("private_path_changed_during_open")
        return fd
    except BaseException:
        os.close(fd)
        raise


def sync_directory(path):
    if WINDOWS:
        # NTFS has no Python directory-fsync primitive. Files are flushed before
        # atomic replacement; this is not a claim of POSIX power-loss parity.
        return False
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return True


def load_private_json(path, *, max_bytes=2 * 1024 * 1024):
    fd = open_private(Path(path))
    with os.fdopen(fd, "r", encoding="utf-8") as stream:
        if os.fstat(stream.fileno()).st_size > max_bytes:
            raise ValueError("private_json_size_exceeded")
        text = stream.read(max_bytes + 1)
        if len(text) > max_bytes:
            raise ValueError("private_json_size_exceeded")
        return json.loads(text)


if WINDOWS:
    import msvcrt

    class _FileLocks:
        LOCK_EX, LOCK_SH, LOCK_NB, LOCK_UN = 2, 1, 4, 8

        @staticmethod
        def flock(fd, operation):
            os.lseek(fd, 0, os.SEEK_SET)
            if operation & _FileLocks.LOCK_UN:
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                return
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")
                os.fsync(fd)
                os.lseek(fd, 0, os.SEEK_SET)
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    return
                except OSError as error:
                    if operation & _FileLocks.LOCK_NB or error.errno not in {13, 36}:
                        raise
                    time.sleep(0.05)

    fcntl = _FileLocks()
else:
    import fcntl


@contextmanager
def file_lock(path, *, blocking=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = open_private(path, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        yield fd
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def worker_environment(*, home=None, extra=None):
    keys = {"PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP",
             "LOCALAPPDATA", "APPDATA", "USERPROFILE", "HOME", "LANG", "LC_ALL"}
    # Windows environment names are case-insensitive; Python enumerates them in
    # uppercase. Dropping SYSTEMROOT prevents PowerShell/.NET from even starting.
    env = {key: value for key, value in os.environ.items() if key.upper() in keys}
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    if home is not None:
        env["HOME"] = str(home)
    env.update(extra or {})
    return env


def powershell(script, *, values):
    """Static scripts only; paths go through environment variables, never interpolation."""
    if not WINDOWS:
        raise ValueError("Windows operation requested on another platform")
    executable = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    subprocess.run([str(executable), "-NoProfile", "-NonInteractive", "-Command",
                    "$ErrorActionPreference='Stop'; " + script], check=True,
                   env=worker_environment(extra=values), capture_output=True)


def bootstrap_directory(path):
    """Restrict a new installer home before pywin32/venv are available."""
    path = Path(path)
    if not path.is_absolute() or is_link(path):
        raise ValueError("Unsafe installer home")
    if path.exists() and any(path.iterdir()) and not (path / "deployment.json").is_file() and not (path / ".native-bootstrap").is_file():
        raise ValueError("Nonempty unfamiliar directory; choose a new native instance home")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if WINDOWS:
        try:
            import win32security  # Available once the private venv is installed.
        except ImportError:
            pass
        else:
            protect(path, directory=True)
            (path / ".native-bootstrap").touch(exist_ok=True)
            return
        powershell("""
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetOwner($sid)
$acl.SetAccessRuleProtection($true, $false)
foreach ($id in @($sid.Value, 'S-1-5-18', 'S-1-5-32-544')) {
  $principal = New-Object System.Security.Principal.SecurityIdentifier($id)
  $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($principal, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
  $acl.AddAccessRule($rule)
}
$directory = New-Object System.IO.DirectoryInfo($env:AGENT_BOOTSTRAP_DIRECTORY)
$directory.SetAccessControl($acl)
""", values={"AGENT_BOOTSTRAP_DIRECTORY": str(path)})
    else:
        path.chmod(0o700)
    (path / ".native-bootstrap").touch(exist_ok=True)


def directory_link(target, link):
    target, link = Path(target), Path(link)
    if not target.is_absolute() or not target.is_dir() or not link.is_absolute() or link.exists() or is_link(link):
        raise ValueError("New explicit directory link required")
    if WINDOWS:
        powershell("New-Item -ItemType Junction -Path $env:AGENT_LINK -Target $env:AGENT_TARGET | Out-Null",
                   values={"AGENT_LINK": str(link), "AGENT_TARGET": str(target)})
    else:
        link.symlink_to(target, target_is_directory=True)


def remove_directory_link(path):
    path = Path(path)
    if not is_link(path):
        raise ValueError("Refusing to remove a real directory")
    if WINDOWS and path.is_junction():
        path.rmdir()  # Removes the junction only, never its target.
    else:
        path.unlink()


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3 or sys.argv[1] != "check-private":
            raise ValueError("unsupported_platform_operation")
        assert_private(Path(sys.argv[2]))
        print(json.dumps({"private": True}))
    except Exception as error:
        print(json.dumps({"private": False, "error_type": type(error).__name__}))
        raise SystemExit(1)
