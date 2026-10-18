"""Rebuild the independent BarMaker checkout and copy its browser distribution."""
import hashlib
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'BarMaker'
DESTINATION=ROOT/'songs/static/songs/barmaker'
if not (SOURCE/'package.json').exists():
    raise SystemExit('Place the independent BarMaker repository in ./BarMaker first.')
subprocess.run(['npm','run','build'],cwd=SOURCE,check=True)
DESTINATION.mkdir(exist_ok=True,parents=True)
script=(SOURCE/'dist/bar-maker.iife.js').read_text()
script='\n'.join(line for line in script.splitlines() if not line.startswith('//# sourceMappingURL='))+'\n'
(DESTINATION/'bar-maker.iife.js').write_text(script)
for name in ('LICENSE','THIRD_PARTY.md'):
    (DESTINATION/name).write_text((SOURCE/name).read_text())
try:
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True,stderr=subprocess.DEVNULL).strip()
    dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=SOURCE,text=True).strip())
except subprocess.CalledProcessError:
    commit=None;dirty=True
metadata={'component':'BarMaker','version':json.loads((SOURCE/'package.json').read_text())['version'],
          'source_commit':commit,'source_has_uncommitted_changes':dirty,
          'sha256':hashlib.sha256(script.encode()).hexdigest()}
(DESTINATION/'build.json').write_text(json.dumps(metadata,indent=2)+'\n')
print('BarMaker browser assets refreshed.')
