"""Run Chrome checks against an ephemeral database; never uses the user's songs."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='songhymn-browser-') as folder:
    temporary = Path(folder)
    (temporary / 'browser_settings.py').write_text(
        'from config.settings import *\n'
        f"DATABASES = {{'default': {{'ENGINE':'django.db.backends.sqlite3','NAME':{str(temporary / 'db.sqlite3')!r},'OPTIONS':{{'timeout':10}}}}}}\n"
        f"MEDIA_ROOT = {str(temporary / 'media')!r}\n"
        "PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']\n"
    )
    env = dict(os.environ, DJANGO_SETTINGS_MODULE='browser_settings',
               PYTHONPATH=os.pathsep.join([folder, str(ROOT)]))
    def manage(*args):
        subprocess.run([sys.executable, 'manage.py', *args], cwd=ROOT, env=env, check=True,
                       stdout=subprocess.DEVNULL)
    manage('migrate', '--noinput')
    manage('shell', '-c', '''
from django.contrib.auth.models import User
from django.utils import timezone
from songs.models import Membership, Song, Part
from songs.policy import AGREEMENT_VERSION
for name, role in [('browserauthor','contributor'),('browserreviewer','reviewer')]:
    user=User.objects.create_user(name,password='browser-only-password')
    Membership.objects.create(user=user,role=role,agreement_version=AGREEMENT_VERSION,agreement_accepted_at=timezone.now())
song=Song.objects.create(title='Browser test song',author=User.objects.get(username='browserauthor'))
for kind in ('concept','lyrics','tune'):
    Part.objects.create(song=song,kind=kind,content='First shared words' if kind!='tune' else '',license_code='CC-BY-4.0')
''')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    server = subprocess.Popen([sys.executable, 'manage.py', 'runserver', f'127.0.0.1:{port}', '--noreload'],
                              cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for attempt in range(50):
            try:
                with urlopen(base, timeout=1): break
            except OSError:
                if server.poll() is not None: raise RuntimeError('Test server exited')
                time.sleep(.2)
        else: raise RuntimeError('Test server did not start')
        subprocess.run(['node', 'scripts/browser-smoke.cjs'], cwd=ROOT,
                       env=dict(env, BROWSER_TEST_URL=base, BROWSER_OUTPUT_DIR=folder), check=True)
    finally:
        server.terminate()
        server.wait(timeout=10)
