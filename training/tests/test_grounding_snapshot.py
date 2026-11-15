import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prompt_suite import verify_frozen
from data_contract import ROOT,persona
class GroundingSnapshotTests(unittest.TestCase):
 def test_smoke_snapshot_keeps_original_hash_and_personas(self):
  plan=verify_frozen();source=plan['persona_source'];self.assertTrue(source.startswith('training/snapshots/'))
  self.assertEqual(hashlib.sha256((ROOT/source).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),'f2d0d29da78ec1e3c12caa4b5192d46a7ddbbbfc35903e2464f751ac09afc676')
  for polite in (True,False):self.assertNotIn('source_user_message',persona(polite))
 def test_snapshot_tampering_still_fails_closed(self):
  plan=verify_frozen()
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);config=root/'training/configs/evaluation-plan.json';config.parent.mkdir(parents=True);config.write_text(json.dumps(plan),encoding='utf-8')
   for source in plan['sources']:
    p=root/source;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/source).read_bytes())
   source=root/plan['persona_source'];source.write_text(source.read_text(encoding='utf-8')+'tampered',encoding='utf-8')
   with self.assertRaises(ValueError):verify_frozen(root)
if __name__=='__main__':unittest.main()
