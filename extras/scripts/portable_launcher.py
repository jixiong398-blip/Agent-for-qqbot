#!/usr/bin/env python3
"""Entry point executed only by the Python shipped inside a prebuilt package."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
os.environ['AGENT_QQBOT_PROJECT'] = str(ROOT)
os.environ['PYTHONUTF8'] = '1'
# Bundle tools plus OS components only; never require a separately installed toolchain.
core_paths = [str(ROOT / 'runtime/node'), str(ROOT / ('runtime/python' if os.name == 'nt' else 'runtime/python/bin'))]
if os.name == 'nt':
    windows = Path(os.environ['SystemRoot'])
    core_paths += [str(windows), str(windows / 'System32'), str(windows / 'System32/WindowsPowerShell/v1.0')]
os.environ['PATH'] = os.pathsep.join([*core_paths, os.environ.get('PATH', '')])
sys.path.insert(0, str(ROOT / 'hermes/core'))
_dll_handles = []
if os.name == 'nt':
    library = ROOT / 'runtime/python/Lib/site-packages'
    for directory in ('win32', 'win32/lib', 'Pythonwin'):
        sys.path.insert(0, str(library / directory))
    dll = library / 'pywin32_system32'
    if dll.is_dir(): _dll_handles.append(os.add_dll_directory(str(dll)))


def main():
    from soyo.app.config import home_path
    from soyo.app import portable
    from soyo.app.__main__ import main as application
    args = sys.argv[1:] or ['start']; home = home_path()
    if args[0] == 'install':
        portable.install(ROOT, home)
        return application(['--home', str(home), 'start', *args[1:]])
    if args[0] in {'start', 'configure'}: portable.ensure(ROOT, home)
    if args[0] == 'update':
        portable.install(ROOT, home)
        print('Prebuilt runtime selected; no source build, network install or QQ login was performed.')
        return 0
    return application(['--home', str(home), *args])


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as error:
        print('Operation failed: ' + type(error).__name__ + ': ' + str(error)[:300], file=sys.stderr)
        raise SystemExit(1)
