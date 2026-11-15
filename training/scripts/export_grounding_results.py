"""Export synthetic direct-review evidence. Never generates quality judgments."""
import argparse,hashlib,json
from collections import Counter
from pathlib import Path
from audit_matched_apps import delivered_contract,fingerprint
from export_matched_app_results import overall,tally,criteria_tally
from matched_app_suite import build_suite

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--artifacts',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a=a.parse_args()
 root=Path(__file__).resolve().parents[2];plan=read(root/'training/configs/grounding-plan.json');suite=build_suite(root);previous=read(root/'docs/validation/matched-apps-20261115/responses.json');baseline={r['id']:r for r in previous}
 rows=[json.loads(x) for x in (a.artifacts/'scoped-final.local.jsonl').read_text(encoding='utf-8').splitlines()];assert len(rows)==len({r['id'] for r in rows})==plan['fresh_final_policy_generations']
 judgments=read(a.artifacts/'gpt-judgments.local.json');assert set(judgments['raw'])==set(judgments['delivered'])==set(baseline)
 policy=root/plan.get('policy_source','app/src/main/java/ai/chloe/voicelab/conversation/GroundedConversationPolicy.java');assert hashlib.sha256(policy.read_bytes().replace(b'\r\n',b'\n')).hexdigest()==plan['policy_source_sha256']
 indexed={r['id']:r for r in rows};output=[];trans=Counter();raw_trans=Counter()
 consumed={r['id']:r for r in read(a.artifacts/'actual-consumer.local.json')}
 audits={r['id']:r for r in read(a.artifacts/'scope-final-audit.local.json')}
 old_native={r['id']:r['result'] for f in ('chloe-main.local.jsonl','chloe-supplement.local.jsonl') for line in (a.artifacts.parent/'apps-match-20261115'/f).read_text(encoding='utf-8').splitlines() for r in [json.loads(line)]}
 for source in suite:
  ident=source['id'];alias='grounded-'+ident not in indexed
  if alias:
   assert audits[ident]['byte_identical'] and audits[ident]['policy_action']=='none'
   r={'result':old_native[ident],'actual_messages':audits[ident]['actual_messages'],'delivered_raw':old_native[ident]['raw'],'policy_action':'none'}
  else:r=indexed['grounded-'+ident]
  native=r['result'];actual=r['actual_messages'];raw=native.get('raw','');final=r['delivered_raw'];before=baseline[ident]
  assert actual[1:]==source['messages'][1:];assert actual[0]['role']=='system'
  assert actual==audits[ident]['actual_messages']
  if alias:assert actual==source['messages']
  else:assert actual[0]['content'].startswith(source['messages'][0]['content']+'\n')
  for key,value in {'runtime_revision':'aa75ff3239f9cc675b081697deda9e1b112345c6','context_tokens':2048,'max_generation_tokens':384,'prefill_threads':4,'decode_threads':4,'backend':'cpu'}.items():assert native[key]==value,(ident,key)
  for j in (judgments['raw'][ident],judgments['delivered'][ident]):assert set(j['criteria'].values()) <= {'pass','partial','fail','not_applicable'}
  rc,fc=delivered_contract(raw),delivered_contract(final)
  assert consumed[ident]['actual_prompt_equal'] and not consumed[ident]['fallback'] and consumed[ident]['failureCode']=='none'
  assert consumed[ident]['spokenText']==fc['spoken_text'].strip()
  if r['policy_action']=='none':assert final==raw and judgments['raw'][ident]==judgments['delivered'][ident]
  trans[(before['chloe']['gpt_overall'],overall(judgments['delivered'][ident]))]+=1;raw_trans[(before['chloe']['gpt_overall'],overall(judgments['raw'][ident]))]+=1
  output.append({'id':ident,'native_output_reused_alias':alias,'question':source['input'],'register':source['register'],'initial_history':source['messages'][1:-1],'baseline_spoken_text':before['chloe']['spoken_text'],'baseline_gpt_quality':before['chloe']['gpt_quality'],'baseline_gpt_overall':before['chloe']['gpt_overall'],'actual_messages_sha256':fingerprint(actual),'system_suffix':actual[0]['content'][len(source['messages'][0]['content']):],'user_assistant_messages_unchanged':True,'actual_consumer_pass':True,'native_parse_status':native.get('native_parse_status'),'truncated':native.get('truncated'),'tokens':native.get('tokens'),'raw_sha256':digest(raw),'raw_contract':rc,'raw_spoken_text':rc['spoken_text'],'raw_gpt_quality':judgments['raw'][ident],'raw_gpt_overall':overall(judgments['raw'][ident]),'policy_action':r['policy_action'],'delivered_sha256':digest(final),'delivered_contract':fc,'delivered_spoken_text':consumed[ident]['spokenText'],'consumer_trim_only':consumed[ident]['spokenText']!=fc['spoken_text'],'delivered_gpt_quality':judgments['delivered'][ident],'delivered_gpt_overall':overall(judgments['delivered'][ident])})
 summary={'comparison_cells':108,'fresh_final_policy_generations':len(rows),'policy_alias_cells':plan['policy_alias_cells'],'excluded_global_policy_completed':plan['excluded_global_policy_completed'],'frozen_baseline_reused':54,'fresh_baseline_references':read(a.artifacts/'baseline-reference-proof.local.json'),'excluded_early_policy_completed':plan['excluded_early_policy_completed'],'training_steps':0,'policy_source_sha256':plan['policy_source_sha256'],'model_sha256':plan['model_sha256'],'unchanged_user_assistant_messages':54,'actual_base_builder_and_final_consumer_pass':54,'fresh_native_parse_ok':sum(x['result'].get('native_parse_status')=='ok' for x in rows),'native_parse_ok':sum(r['native_parse_status']=='ok' for r in output),'truncated':sum(bool(r['truncated']) for r in output),'raw_contract_pass':sum(r['raw_contract']['contract_pass'] for r in output),'delivered_contract_pass':sum(r['delivered_contract']['contract_pass'] for r in output),'policy_actions':dict(Counter(r['policy_action'] for r in output)),'gpt_baseline':tally([r['baseline_gpt_quality'] for r in output]),'gpt_raw':tally([r['raw_gpt_quality'] for r in output]),'gpt_delivered':tally([r['delivered_gpt_quality'] for r in output]),'criteria_delivered':criteria_tally([r['delivered_gpt_quality'] for r in output]),'raw_transitions':{str(k):v for k,v in raw_trans.items()},'delivered_transitions':{str(k):v for k,v in trans.items()},'judge':'GPT direct, known conditions, same author; not blind/independent/human','scope':'App grounding/deterministic decisions, not retrained-model quality. Current source manager unit-compiled; installed alpha15 native plus same policy bridge tested, no full updated product APK/TTS deployment.'}
 a.output.mkdir(parents=True,exist_ok=False)
 for name,value in [('responses.json',output),('summary.json',summary)]: (a.output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
