"""Download only the pinned non-model build inputs in the checked manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    for item in json.loads(a.manifest.read_text(encoding='utf-8-sig')):
        name=item['filename'];assert Path(name).name==name and item['url'].startswith('https://')
        assert not name.endswith(('.gguf','.safetensors'))
        dest=a.output/name;h=hashlib.sha256();size=0
        with urllib.request.urlopen(item['url'],timeout=60) as source,dest.open('xb') as out:
            while data:=source.read(1024*1024):out.write(data);h.update(data);size+=len(data)
        assert h.hexdigest()==item['sha256'] and size==item['bytes'],name
        print(name,size)


if __name__=='__main__':main()
