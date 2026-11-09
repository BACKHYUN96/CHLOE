import unittest
from tts_comparison import cer, CASES, COMMON, VOICE, ROOT
import re
import json

class ComparisonTests(unittest.TestCase):
    def test_cer_normalizes_nfc_spaces_and_punctuation(self):
        self.assertEqual(0,cer('같이 가실래요?','같이가실래요')['cer'])
        self.assertEqual(1,cer('가나','가다')['edits'])
        self.assertEqual(.5,cer('가나','가다')['cer'])
        self.assertEqual(2,cer('가','가나다')['cer'])  # insertion can exceed 100%
    def test_common_style_and_design_description_match_android(self):
        source=(ROOT/'app/src/main/java/ai/chloe/voicelab/comparison/ComparisonData.kt').read_text()
        self.assertEqual(COMMON,re.search(r'const val COMMON_STYLE = "([^"]+)"',source).group(1))
        self.assertEqual(VOICE,re.search(r'const val DESIGN_VOICE = "([^"]+)"',source).group(1))
    def test_empty_reference_is_not_perfect_score(self):
        with self.assertRaises(ValueError):cer('...','텍스트')
    def test_three_distinct_seeds_and_twenty_cases(self):
        d=json.loads(CASES.read_text());self.assertEqual([42,43,44],d['seeds'])
        self.assertEqual(20,len(d['cases']));self.assertEqual(20,len({c['id'] for c in d['cases']}))

if __name__=='__main__':unittest.main()
