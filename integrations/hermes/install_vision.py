"""Install /vision files only; never restart or recreate a service."""
import argparse
import ast
from datetime import datetime, timezone
from pathlib import Path
import shutil


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--skills-dir', type=Path, required=True,
                   help='Actual skills directory used by the Hermes runtime')
    p.add_argument('--bridge-file', type=Path,
                   help='Optional deployed skylinee_harness/hermes_bridge.py')
    args = p.parse_args()
    source = Path(__file__).resolve().parent
    destination = args.skills_dir.expanduser().resolve() / 'vision'
    if destination.exists():
        raise SystemExit('A vision skill already exists; nothing overwritten.')
    patched = None
    if args.bridge_file:
        bridge = args.bridge_file.expanduser().resolve(strict=True)
        text = bridge.read_text()
        anchor = '    return p\n\n\nasync def _sse_data'
        if text.count(anchor) != 1 or 'prepare_vision_command' in text:
            raise SystemExit('Bridge does not match the tested 0.3.4 insertion point; nothing changed.')
        patched = text.replace(anchor, '    return prepare_vision_command(p)\n\n\nasync def _sse_data')
        patched = 'from .vision_command import prepare_vision_command\n' + patched
        ast.parse(patched)
        if bridge.with_name('vision_command.py').exists():
            raise SystemExit('vision_command.py already exists; nothing changed.')
    args.skills_dir.expanduser().mkdir(parents=True, exist_ok=True)
    shutil.copytree(source / 'vision', destination)
    try:
        if patched is not None:
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            backup = bridge.with_name(bridge.name + '.before-vision-' + stamp)
            shutil.copy2(bridge, backup)
            shutil.copy2(source / 'vision_command.py', bridge.with_name('vision_command.py'))
            bridge.write_text(patched)
            print('Bridge backup:', backup)
    except Exception:
        if patched is not None and 'backup' in locals() and backup.exists():
            shutil.copy2(backup, bridge)
            bridge.with_name('vision_command.py').unlink(missing_ok=True)
        shutil.rmtree(destination)
        raise
    print('Installed skill:', destination)
    print('No services restarted. Configure SKYLINEE_VISION_URL in the Hermes runtime.')
    print('An already-running bridge must reload the changed Python module before /vision dispatch is active.')


if __name__ == '__main__':
    main()
