import io,json,tempfile,unittest,wave
from pathlib import Path
from voxcpm2_lab import normalized,split_for,prepare_rows,configuration

class VoxLabTests(unittest.TestCase):
    def test_split_groups_equivalent_transcripts(self):
        self.assertEqual(split_for('오늘도 수고했어!'),split_for('오늘도  수고했어.'))
        self.assertEqual(normalized('가'),normalized('가'))
    def test_preparation_preserves_original_and_holds_out_test_text(self):
        import numpy as np
        import soundfile as sf
        rows=[]
        for i in range(80):
            b=io.BytesIO();sf.write(b,.15*np.sin(np.arange(32000)*2*np.pi*(200+i)/16000),16000,format='WAV',subtype='PCM_16')
            rows.append(dict(audio={'bytes':b.getvalue()},expanded_script='오늘도 수고했어.' if i==0 else f'데이터 검증 문장 {i}'))
        rows.append(rows[1])
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)/'data';r=prepare_rows(rows,output,6,2)
            train={normalized(x['text']) for x in r['items']['train']};val={normalized(x['text']) for x in r['items']['val']}
            self.assertFalse(train&val);self.assertNotIn(normalized('오늘도 수고했어'),train|val)
            for item in r['items']['train']+r['items']['val']:
                self.assertTrue(Path(item['audio']).is_file())
                self.assertTrue((output/'original'/Path(item['audio']).name).is_file())
            c=configuration(Path(d)/'model',output,Path(d)/'run',1)
            self.assertEqual(c['batch_size'],1);self.assertEqual(c['lora']['r'],8);self.assertFalse(c['lora']['enable_dit'])
            with self.assertRaises(ValueError):prepare_rows(rows,output,6,2)
    def test_failed_preparation_removes_only_its_staging_directory(self):
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)/'data'
            with self.assertRaises(ValueError):prepare_rows([],output,1,1)
            self.assertFalse(output.exists());self.assertFalse(output.with_name('data.partial').exists())

if __name__=='__main__':unittest.main()
