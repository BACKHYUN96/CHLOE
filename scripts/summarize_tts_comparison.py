#!/usr/bin/env python3
"""Publish only fixed-corpus metrics; never copy recordings, native logs or user ratings to Git."""
import argparse,csv,json,re,statistics
from pathlib import Path
from tts_comparison import ROOT, CUSTOM, DESIGN, VOX, COSY, digest,atomic

MODELS={'custom':CUSTOM,'design':DESIGN,'vox':VOX,'cosy':COSY}
FIELDS=['case_id','seed','condition','generation_ms','model_init_ms','audio_seconds','rtf','wav_sha256',
        'sample_rate','samples','pcm_full_scale_samples','precision','runtime_commit','native_binary_sha256',
        'peak_rss_kib','rss_method','model_reused','config_only_initialization','instruction_applied']


def summarize(folder,model,expected):
    path=folder/'comparison-manifest.json'
    if not path.exists():return dict(model_id=model,status='not_run',expected=expected,successful_wavs=0,failures=0,perceptual_evaluation='pending')
    report=json.loads(path.read_text(encoding='utf-8'));rows=[r for r in report['clips'] if r['model_id']==model]
    result=dict(model_id=model,status='complete' if len(rows)==expected else 'incomplete',expected=expected,successful_wavs=len(rows),
                failures=len(report.get('failures',[])),initialization_error=report.get('initialization_error'),perceptual_evaluation='pending')
    result['clips']=[]
    for row in rows:
        if digest(folder/row['file'])!=row['wav_sha256']:raise ValueError('WAV changed before summary')
        item={k:row[k] for k in FIELDS if k in row}
        aux=row.get('asr_auxiliary',{}).get('measurement')
        if aux:item['asr_auxiliary']=aux
        # Native qwen CLI reports snapshots with rounded units, not Android PSS or kernel RSS high water.
        log=folder/(Path(row['file']).stem+'.log')
        if log.is_file():
            match=re.search(r'RSS peak:\s*([^\r\n]+)',log.read_text(encoding='utf-8'))
            if match:item['native_sampled_rss_peak_display']=match.group(1).strip()
        result['clips'].append(item)
    if rows:
        result['median_generation_ms']=statistics.median(r['generation_ms'] for r in rows)
        result['median_rtf']=statistics.median(r['rtf'] for r in rows)
        result['audio_seconds_range']=[min(r['audio_seconds'] for r in rows),max(r['audio_seconds'] for r in rows)]
        init_rows=[r for r in rows if r.get('model_init_ms') is not None and r.get('model_reused') is not True]
        result['independent_model_init_observations']=len(init_rows)
        result['median_model_init_ms']=statistics.median(r['model_init_ms'] for r in init_rows) if init_rows else None
        values=[r['asr_auxiliary']['measurement'] for r in rows if 'asr_auxiliary' in r]
        result['auxiliary_asr_count']=len(values)
        result['auxiliary_micro_cer']=sum(r['edits'] for r in values)/sum(r['reference_characters'] for r in values) if values else None
        groups={}
        for r in rows:groups.setdefault(r['case_id'],[]).append(r)
        result['duration_variation_flags']=[]
        for case,items in groups.items():
            durations=[r['audio_seconds'] for r in items]
            if len(items)>=3 and max(durations)/min(durations)>2:
                result['duration_variation_flags'].append(dict(case_id=case,seeds=[r['seed'] for r in items],seconds=durations,max_min_ratio=max(durations)/min(durations),interpretation='listening required; not an automatic quality score'))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--artifacts',type=Path,default=ROOT/'artifacts')
    p.add_argument('--output',type=Path,default=ROOT/'docs/validation/tts-comparison/host-results.json');p.add_argument('--require-complete',action='store_true')
    a=p.parse_args();result=dict(schema=1,platform='linux-host',device_test=False,human_ratings=None,model_winner=None,
        host='Linux x86_64 AMD EPYC 9V45 virtual CPU; not Windows or S26 Ultra',
        performance_limit='Download/build/other-model smoke or ASR load overlapped some runs; different runtimes and cold/reused lifetimes. Diagnostic timings, not a controlled speed ranking.',
        first_output_ms=None,streaming_first_chunk_ms=None,physical_speaker_first_sound_ms=None,device_temperature=None,gpu_utilization=None,
        models={name:summarize(a.artifacts/f'tts-comparison-{name}',model,60) for name,model in MODELS.items()},
        optimized={name:summarize(a.artifacts/f'tts-optimized-{name}',model,12) for name,model in MODELS.items()})
    if a.require_complete:
        assert all(r['successful_wavs']==60 and r['failures']==0 and r['auxiliary_asr_count']==60 for r in result['models'].values())
        assert all(r['successful_wavs']==12 and r['failures']==0 and r['auxiliary_asr_count']==12 for r in result['optimized'].values())
    atomic(a.output,result)
    print(json.dumps({name:{k:v for k,v in rows.items() if k in ['successful_wavs','failures','median_rtf','auxiliary_micro_cer']} for name,rows in result['models'].items()},ensure_ascii=False))

if __name__=='__main__':main()
