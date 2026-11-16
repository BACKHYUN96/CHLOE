"""Build a disclosed insertion-order compatibility shim; preserve original sources/jar.

Apache-2.0 Android JSON sources from com.vaadin.external.google:android-json
0.0.20131108.vaadin1. Only JSONObject's backing HashMap becomes LinkedHashMap.
Android runtime is not replaced. Validate prepared prompts/consumption separately.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-jar',type=Path,required=True)
    p.add_argument('--jdk',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    source_sha=hashlib.sha256(a.source_jar.read_bytes()).hexdigest()
    assert source_sha=='54c781eea645c450cbbc4a5a1b5a474745465452cec1354cb567b781ea6622c3'
    sources=[]
    with zipfile.ZipFile(a.source_jar) as z:
        for name in z.namelist():
            if not name.startswith('org/json/') or not name.endswith('.java'):continue
            dest=a.output/'src'/Path(name).name;dest.parent.mkdir(exist_ok=True)
            text=z.read(name).decode('utf-8')
            if name.endswith('/JSONObject.java'):
                assert 'java.util.HashMap' in text
                text=text.replace('java.util.HashMap','java.util.LinkedHashMap').replace('HashMap<','LinkedHashMap<')
            dest.write_text(text,encoding='utf-8');sources.append(dest)
    classes=a.output/'classes';classes.mkdir()
    subprocess.run([str(a.jdk/'bin/javac.exe'),'-encoding','UTF-8','--release','8','-d',str(classes),*map(str,sources)],check=True)
    jar=a.output/'android-json-ordered.jar'
    # A classpath jar needs no manifest. Avoid JDK's cross-directory temp move
    # which fails under some Windows restricted filesystem configurations.
    with zipfile.ZipFile(jar,'x',zipfile.ZIP_DEFLATED) as z:
        for path in sorted(classes.rglob('*.class')):z.write(path,path.relative_to(classes).as_posix())
    (a.output/'manifest.json').write_text(json.dumps(dict(source_sha256=source_sha,modification='JSONObject HashMap -> LinkedHashMap only',jar_sha256=hashlib.sha256(jar.read_bytes()).hexdigest()),indent=2)+'\n')
    print(jar)


if __name__=='__main__':main()
