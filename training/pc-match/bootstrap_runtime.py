"""Prepare an isolated WSL toolchain from verified downloads; no apt/pip global install."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile


def run(args, **kwargs):
    return subprocess.run(list(map(str,args)),check=True,**kwargs)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--downloads',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--training-root',type=Path,required=True)
    a=p.parse_args();a.root.mkdir(parents=True,exist_ok=False)
    manifest=json.loads(a.manifest.read_text(encoding='utf-8-sig'))
    (a.root/'training-freeze.before.txt').write_bytes(subprocess.check_output([str(a.training_root/'.venv-llm/bin/python'),'-m','pip','freeze']))
    (a.root/'dpkg.before.txt').write_bytes(subprocess.check_output(['dpkg-query','-W']))
    for item in manifest:
        path=a.downloads/item['filename']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']
    run(['python3','-m','venv',a.root/'tools-env'])
    run([a.root/'tools-env/bin/python','-m','pip','install','--no-index','--no-deps',*[a.downloads/x['filename'] for x in manifest if x['filename'].endswith('.whl')]])
    (a.root/'host-downloads').mkdir();cpp=a.root/'host-tools';cpp.mkdir()
    run(['apt-get','download','g++-13-x86-64-linux-gnu=13.3.0-6ubuntu2~24.04.1','libstdc++-13-dev=13.3.0-6ubuntu2~24.04.1'],cwd=a.root/'host-downloads')
    for deb in (a.root/'host-downloads').glob('*.deb'):run(['dpkg-deb','-x',deb,cpp])
    (cpp/'link').mkdir();(cpp/'link/libstdc++.so').symlink_to('/usr/lib/x86_64-linux-gnu/libstdc++.so.6')
    (a.root/'bin').mkdir();wrapper=a.root/'bin/g++'
    wrapper.write_text('#!/bin/sh\nexec '+str(cpp/'usr/bin/x86_64-linux-gnu-g++-13')+' -B'+str(cpp/'usr/libexec/gcc/x86_64-linux-gnu/13/')+' -B/usr/lib/gcc/x86_64-linux-gnu/13/ -isystem '+str(cpp/'usr/include/c++/13')+' -isystem '+str(cpp/'usr/include/x86_64-linux-gnu/c++/13')+' -isystem '+str(cpp/'usr/include/c++/13/backward')+' -L'+str(cpp/'link')+' "$@"\n');wrapper.chmod(0o755)
    cuda_extract=a.root/'cuda-extracted';cuda_extract.mkdir()
    for item in manifest:
        if item['name'].startswith('cuda-'):run(['dpkg-deb','-x',a.downloads/item['filename'],cuda_extract])
    cuda=cuda_extract/'usr/local/cuda-12.8';(a.root/'cuda').symlink_to(cuda)
    nvidia=a.training_root/'.venv-llm/lib/python3.12/site-packages/nvidia'
    for header in (nvidia/'cublas/include').glob('*.h'):
        dest=cuda/'targets/x86_64-linux/include'/header.name
        if not dest.exists():dest.symlink_to(header)
    for name in ['cublas','cublasLt']:
        (cuda/'targets/x86_64-linux/lib'/('lib'+name+'.so')).symlink_to(nvidia/'cublas/lib'/('lib'+name+'.so.12'))
    sources=a.root/'source';sources.mkdir()
    archive=next(x for x in manifest if x['name']=='llama.cpp-source')
    with tarfile.open(a.downloads/archive['filename']) as t:t.extractall(sources,filter='data')
    run([wrapper,'--version']);run([cuda/'bin/nvcc','--version'])
    (a.root/'download-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    assert (a.root/'training-freeze.before.txt').read_bytes()==subprocess.check_output([str(a.training_root/'.venv-llm/bin/python'),'-m','pip','freeze'])
    assert (a.root/'dpkg.before.txt').read_bytes()==subprocess.check_output(['dpkg-query','-W'])
    print('Isolated toolchain ready; system packages and training venv unchanged.')


if __name__=='__main__':main()
