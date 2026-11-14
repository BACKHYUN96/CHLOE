"""Download only the pinned original checkpoint/tokenizer; verify without replacing existing files."""
import argparse
import os

from llm_runtime import artifact_output, read_config, sha256, write_json


HASHES={
    'model.safetensors-00001-of-00001.safetensors':'aa33250c4fc64891ddfaba3a314fd9542ea371843c387178b425fbcc5ed680b1',
    'config.json':'ed1c1723241f23f7f4e23430759cbd7dcfb4103cbdfe052bfe7626b57c2615b4',
    'chat_template.jinja':'273d8e0e683b885071fb17e08d71e5f2a5ddfb5309756181681de4f5a1822d80',
    'tokenizer_config.json':'49e2b6e395f959f077f1e992b338919c0d4a9732fc6e613995e06557f843500c',
    'LICENSE':'bbedc3fda3305820b977265f01b8619d87570a6739de3a5582c3464840f1e57a'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    args=parser.parse_args()
    cfg=read_config(args.config)
    base=artifact_output(cfg['base_dir'])
    existed=base.exists()
    if not existed:
        os.environ['HF_HUB_DISABLE_XET']='1'
        from huggingface_hub import snapshot_download
        base.mkdir(parents=True,exist_ok=False)
        snapshot_download(cfg['model_id'],revision=cfg['revision'],local_dir=str(base),
            allow_patterns=['*.json','*.jinja','*.safetensors','LICENSE','README.md'],max_workers=2,token=False)
    # A partial pre-existing folder is never resumed or overwritten implicitly.
    for name,expected in HASHES.items():
        if not (base/name).is_file() or sha256(base/name)!=expected:
            raise ValueError('Pinned file missing/hash mismatch; preserve folder and choose a fresh base_dir')
    if not existed:
        write_json(base/'verified-manifest.json',{'model_id':cfg['model_id'],'revision':cfg['revision'],
            'license':'Apache-2.0','sha256':HASHES,'remote_code_executed':False})
    print('Pinned original checkpoint and metadata hashes verified; existing files preserved')


if __name__=='__main__':
    main()
