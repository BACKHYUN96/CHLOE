import json
from pathlib import Path
import tempfile
import unittest
from compare_situational_styles import load_custom_plan

class VoicePlanTest(unittest.TestCase):
    def load(self, cases):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'plan.json'
            p.write_text(json.dumps(dict(study='test-study',cases=cases)),encoding='utf-8')
            return load_custom_plan(p)

    def test_output_path_escape_is_rejected(self):
        with self.assertRaises(ValueError):
            self.load([dict(id='../outside',text='안녕',instructions={'E':'자연스럽게'})])

    def test_distinct_cases_cannot_overwrite_each_others_wav(self):
        with self.assertRaises(ValueError):
            self.load([dict(id='a_b',text='안녕',instructions={'c':'자연스럽게'}),
                       dict(id='a',text='안녕',instructions={'b_c':'자연스럽게'})])

    def test_instruction_length_matches_android_limit(self):
        self.load([dict(id='case',text='안녕',instructions={'E':'가'*240})])
        with self.assertRaises(ValueError):
            self.load([dict(id='case',text='안녕',instructions={'E':'가'*241})])

if __name__=='__main__':unittest.main()
