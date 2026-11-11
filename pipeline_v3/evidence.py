#!/usr/bin/env python3
"""Fresh-run source snapshots, completion inventory, and read-only verification."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
HERE=Path(__file__).resolve().parent


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def write(path,obj):
    path.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')


def begin(out,args):
    sources=[*HERE.glob('*.py'),*HERE.glob('*.c'),*HERE.glob('*.h'),HERE/'README.md',
             ROOT/'build.py',ROOT/'requirements.txt',ROOT/'Makefile',ROOT/'docs/PIPELINE_V3_SPEC.md']
    hashes={}
    for p in sources:
        relative=p.relative_to(ROOT);hashes[str(relative)]=digest(p)
        target=out/'sources'/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(p,target)
    state=dict(started_utc=datetime.now(timezone.utc).isoformat(),
               status='incomplete unless manifest.json exists and verifies',
               command=sys.argv,arguments={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()},
               source_sha256=hashes)
    write(out/'run.json',state)
    return state


def finish(out,state,compiler,mode):
    for name,expected in state['source_sha256'].items():
        if digest(ROOT/name)!=expected:raise RuntimeError('Source changed during run: '+name)
    versions={p:importlib.metadata.version(p) for p in ('numpy','scipy','matplotlib')}
    compiler_identity=subprocess.run([compiler[0],'--version'],check=True,capture_output=True,text=True).stdout
    binary=out/'bin'/'runner'
    linker=['otool','-L',str(binary)] if sys.platform=='darwin' else ['ldd',str(binary)]
    linked=subprocess.run(linker,capture_output=True,text=True)
    if linked.returncode:raise RuntimeError('Could not record dynamic library identity: '+linked.stderr)
    write(out/'environment.json',dict(python=sys.version,python_executable=sys.executable,
          platform=platform.platform(),machine=platform.machine(),libc=platform.libc_ver(),
          compiler_command=compiler,compiler_version=compiler_identity,linked_libraries=linked.stdout,
          packages=versions,reproducibility='Numerical agreement; cross-platform bitwise identity is not promised.'))
    inventory={str(p.relative_to(out)):dict(sha256=digest(p),bytes=p.stat().st_size)
               for p in sorted(out.rglob('*')) if p.is_file() and p.name!='manifest.json'}
    manifest=dict(status='complete',mode=mode,completed_utc=datetime.now(timezone.utc).isoformat(),
                  source_sha256=state['source_sha256'],artifacts=inventory)
    # Final publication step: no completed manifest exists until every artifact is hashed.
    write(out/'manifest.tmp',manifest)
    (out/'manifest.tmp').replace(out/'manifest.json')
    verify(out)


def verify(out):
    manifest=json.loads((out/'manifest.json').read_text())
    if manifest.get('status')!='complete':raise ValueError('Archive not complete')
    expected=manifest['artifacts']
    actual={str(p.relative_to(out)) for p in out.rglob('*') if p.is_file() and p!=out/'manifest.json'}
    if actual!=set(expected):raise ValueError('Artifact inventory differs: '+str(actual.symmetric_difference(expected)))
    for name,info in expected.items():
        p=out/name
        if p.stat().st_size!=info['bytes'] or digest(p)!=info['sha256']:raise ValueError('Artifact changed: '+name)
    for name,h in manifest['source_sha256'].items():
        if digest(out/'sources'/name)!=h:raise ValueError('Source snapshot mismatch: '+name)
    return len(expected)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('directory',type=Path)
    args=ap.parse_args();print(f'Verified {verify(args.directory.resolve())} artifacts.')
