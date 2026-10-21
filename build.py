"""Build a portable source archive and single-file interactive installer."""
from pathlib import Path
import io
import tarfile

ROOT = Path(__file__).resolve().parent
FILES = ['bot.py', 'configure.py', 'requirements.txt', 'wg-telegram.service',
         'install.sh', '.env.example', '.gitignore', 'README.md', 'README.en.md', 'README.fr.md', 'build.py',
         'tests/test_bot.py', '.github/workflows/check.yml']


def build():
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w:gz') as tar:
        for name in FILES:
            data = (ROOT / name).read_bytes()
            info = tarfile.TarInfo('wg-telegram/' + name)
            info.size = len(data)
            info.mode = 0o755 if name.endswith('.sh') else 0o644
            info.mtime = 0
            tar.addfile(info, io.BytesIO(data))
    (output / 'wg-telegram.tar.gz').write_bytes(archive.getvalue())
    # No download of executable code at install time: sources are embedded here.
    shell = '''#!/usr/bin/env bash
set -euo pipefail
umask 077
if [ "$(id -u)" -ne 0 ]; then echo 'Запусти от root: sudo bash setup-wg-telegram.sh'; exit 1; fi
task_tmp="$(mktemp -d)"
trap 'rm -rf -- "$task_tmp"' EXIT
'''
    for name in ['bot.py', 'configure.py', 'requirements.txt', 'wg-telegram.service', 'install.sh']:
        marker = 'WG_TELEGRAM_EMBED_' + name.replace('.', '_').replace('-', '_')
        text = (ROOT / name).read_text()
        assert marker not in text
        shell += f"cat > \"$task_tmp/{name}\" <<'{marker}'\n{text}\n{marker}\n"
    shell += 'bash "$task_tmp/install.sh"\n'
    (output / 'setup-wg-telegram.sh').write_text(shell)
    print(output / 'setup-wg-telegram.sh')
    print(output / 'wg-telegram.tar.gz')


if __name__ == '__main__':
    build()
