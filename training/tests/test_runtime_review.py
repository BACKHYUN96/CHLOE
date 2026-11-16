import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import runtime_review as review


def packet_fixture():
    row = {'id':'J001','applicable_dimensions':['register','relevance','naturalness'],
           'answers':{'K1':{'presentation':'literal_spoken_field','text':'같은 답'},
                      'K2':{'presentation':'literal_spoken_field','text':'같은 답'}}}
    packet = {'review_id':'synthetic','rubric':{},'situations':[row]}
    judgments = {'J001':{label:{d:'pass' if d in row['applicable_dimensions'] else 'not_applicable'
                                for d in review.DIMENSIONS} for label in row['answers']}}
    return packet,judgments


class RuntimeReviewTests(unittest.TestCase):
    def test_invalid_contract_can_have_literal_diagnostic_text_without_acceptance(self):
        response = {'diagnostic_spoken_text':'그 말은 알겠어.','raw':'original invalid enum JSON',
                    'reply':None,'json_valid':False}
        before = copy.deepcopy(response)
        self.assertEqual(review.review_view(response),{'presentation':'literal_spoken_field','text':'그 말은 알겠어.'})
        self.assertEqual(response,before)

    def test_malformed_json_is_never_repaired_or_regex_extracted(self):
        raw = '{"spoken_text":"incomplete'
        view = review.review_view({'raw':raw,'diagnostic_spoken_text':None})
        self.assertEqual(view,{'presentation':'raw_unrepaired_output','text':raw})

    def test_identical_masked_content_must_receive_identical_judgments(self):
        packet,judgments = packet_fixture()
        review.validate(packet,judgments)
        judgments['J001']['K2']['relevance'] = 'fail'
        with self.assertRaisesRegex(ValueError,'Identical'):
            review.validate(packet,judgments)

    def prepare(self, root, unavailable=False):
        packet,judgments = packet_fixture()
        if unavailable:
            for item in judgments['J001'].values():
                for d in ('register','relevance','naturalness'):item[d]='unassessable'
        key = {'candidates':{'K1':{'condition':'baseline','candidate':'base'},
                             'K2':{'condition':'decoder_off','candidate':'base'}},
               'consumer':{'J001':{'K1':{'contract_valid':True,'eos_reached':True},
                                   'K2':{'contract_valid':False,'eos_reached':True}}}}
        for name,value in [('packet.local.json',packet),('key.local.json',key),
                           ('verdicts.local.json',{'review_id':'synthetic','reviewer_kind':'gpt_session','judgments':judgments})]:
            review.write_json(root/name,value)
        review.write_json(root/'provenance.local.json',{'packet_sha256':review.digest(root/'packet.local.json'),
                           'key_sha256':review.digest(root/'key.local.json'),'summary_sha256':'source'})

    def call(self, root):
        with patch.object(review,'artifact_output',side_effect=lambda value:Path(value)):
            return review.aggregate(root)

    def test_content_pass_and_app_usable_pass_are_different(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.prepare(root)
            result = self.call(root)
            self.assertEqual(result['cells']['baseline:base']['app_usable_strict_pass'],1)
            self.assertEqual(result['cells']['decoder_off:base']['app_usable_strict_pass'],0)
            self.assertEqual(result['cells']['decoder_off:base']['content_strict_pass'],1)
            self.assertFalse(result['human_review'])

    def test_unassessable_is_separate_from_failure_zero_and_not_applicable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.prepare(root,unavailable=True)
            result = self.call(root)
            cell = result['cells']['baseline:base']
            self.assertEqual(cell['fully_assessable_cases'],0)
            self.assertEqual(cell['unassessable_cases'],1)
            self.assertEqual(cell['dimensions']['register']['fail'],0)
            self.assertEqual(cell['dimensions']['register']['unassessable'],1)
            self.assertEqual(cell['content_strict_pass'],0)

    def test_missing_candidate_or_wrong_na_is_rejected(self):
        packet,judgments = packet_fixture()
        missing = copy.deepcopy(judgments)
        del missing['J001']['K2']
        with self.assertRaises(ValueError):review.validate(packet,missing)
        judgments['J001']['K1']['honesty'] = 'pass'
        with self.assertRaises(ValueError):review.validate(packet,judgments)


if __name__ == '__main__':
    unittest.main()
