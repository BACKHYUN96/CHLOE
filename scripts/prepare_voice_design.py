#!/usr/bin/env python3
"""Package an already converted VoiceDesign GGUF; no downloads, no CustomVoice replacement."""
import argparse,json,os,shutil
from pathlib import Path
from tts_comparison import digest,DESIGN,RUNTIME

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--talker',type=Path,required=True);p.add_argument('--tokenizer',type=Path,required=True)
p.add_argument('--output',type=Path,required=True);p.add_argument('--revision',default='5ecdb67327fd37bb2e042aab12ff7391903235d3')
a=p.parse_args()
if a.output.exists() and any(a.output.iterdir()):p.error('Use empty output')
a.output.mkdir(parents=True,exist_ok=True)
files=[]
for source,name in [(a.talker,'qwen-talker-1.7b-voicedesign-f16-stable.gguf'),(a.tokenizer,'qwen-tokenizer-12hz-f16.gguf')]:
 target=a.output/name
 try:os.link(source,target)
 except OSError:shutil.copyfile(source,target)
 files.append(dict(name=name,size=target.stat().st_size,sha256=digest(target)))
manifest=dict(schema=1,model_id=DESIGN,model_revision=a.revision,runtime_commit=RUNTIME,precision='f16-f32-cp-down',files=files,license='Apache-2.0',speaker=None)
(a.output/'design-pack.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
shutil.copyfile(Path(__file__).resolve().parents[1]/'third_party/licenses/Qwen3-TTS-Apache-2.0.txt',a.output/'LICENSE-Apache-2.0.txt')
print(a.output)
