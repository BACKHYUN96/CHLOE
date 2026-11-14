import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import gpt_prompt_review as review


class GptPromptReviewTests(unittest.TestCase):
    def test_applicability_excludes_untested_dimensions(self):
        basic = {'case_id':'conv01','id':'fixed:casual:conv01'}
        self.assertEqual(review.applicable(basic),['register','relevance','naturalness'])
        self.assertIn('memory',review.applicable({'case_id':'conv30','id':'summary:casual:conv30'}))
        self.assertNotIn('memory',review.applicable({'case_id':'conv30','id':'fixed:casual:conv30'}))
        self.assertIn('honesty',review.applicable({'case_id':'register01','id':'fixed:casual:register01'}))

    def create(self, root):
        labels = {'K1':{'variant':'original','candidate':'base'},'K2':{'variant':'original','candidate':'adapter'},
                  'K3':{'variant':'revised','candidate':'base'},'K4':{'variant':'revised','candidate':'adapter'}}
        row = {'id':'J001','applicable_dimensions':['register','relevance','naturalness']}
        packet = {'review_id':'synthetic','rubric':{'test':True},'situations':[row]}
        key = {'review_id':'synthetic','candidates':labels}
        judgments = {'J001':{label:{dim:'pass' if dim in row['applicable_dimensions'] else 'not_applicable'
                                  for dim in review.DIMENSIONS} for label in labels}}
        verdicts = {'review_id':'synthetic','reviewer_kind':'gpt_session','judgments':judgments}
        for name, value in [('packet.local.json',packet),('key.local.json',key),('verdicts.local.json',verdicts)]:
            review.write_json(root/name,value)
        review.write_json(root/'provenance.local.json',{'packet_sha256':review.digest(root/'packet.local.json'),
                           'key_sha256':review.digest(root/'key.local.json'),'summary_sha256':'source'})
        return verdicts

    def call(self, root):
        with patch.object(review,'artifact_output',side_effect=lambda value:Path(value)):
            return review.aggregate(root)

    def test_explicit_gpt_judgments_aggregate_without_fabricated_human_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.create(root)
            result = self.call(root)
            self.assertFalse(result['human_review'])
            self.assertTrue(result['gpt_review_completed'])
            self.assertEqual(result['strict_all_applicable_pass']['revised:adapter'],1)
            self.assertEqual(result['dimension_counts']['original:base']['identity']['not_applicable'],1)
            self.assertNotIn('K1',json.dumps(result))
            self.assertFalse(result['model_promotion_approved'])

    def test_partial_does_not_count_as_strict_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            verdicts = self.create(root)
            verdicts['judgments']['J001']['K4']['naturalness'] = 'partial'
            (root/'verdicts.local.json').write_text(json.dumps(verdicts),encoding='utf-8')
            result = self.call(root)
            self.assertEqual(result['strict_all_applicable_pass']['revised:adapter'],0)
            self.assertEqual(result['dimension_counts']['revised:adapter']['naturalness']['partial'],1)

    def test_missing_applicable_verdict_or_scored_na_is_rejected(self):
        for dim, value in [('register','not_applicable'),('identity','pass')]:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                verdicts = self.create(root)
                verdicts['judgments']['J001']['K1'][dim] = value
                (root/'verdicts.local.json').write_text(json.dumps(verdicts),encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'Applicable'):
                    self.call(root)

    def test_missing_candidate_or_wrong_review_id_is_rejected(self):
        for change in ('candidate','identity'):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                verdicts = self.create(root)
                if change == 'candidate':
                    del verdicts['judgments']['J001']['K1']
                else:
                    verdicts['review_id'] = 'other'
                (root/'verdicts.local.json').write_text(json.dumps(verdicts),encoding='utf-8')
                with self.assertRaises(ValueError):
                    self.call(root)

    def test_changed_packet_is_rejected_before_aggregation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.create(root)
            with (root/'packet.local.json').open('a') as stream:
                stream.write(' ')
            with self.assertRaisesRegex(ValueError,'changed'):
                self.call(root)
            self.assertFalse((root/'aggregate.local.json').exists())

    def test_two_candidate_followup_does_not_invent_four_candidate_results(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            verdicts = self.create(root)
            key = review.read(root/'key.local.json')
            key['candidates'] = {'K1':{'variant':'concise','candidate':'base'},
                                 'K2':{'variant':'concise','candidate':'adapter'}}
            (root/'key.local.json').write_text(json.dumps(key),encoding='utf-8')
            provenance = review.read(root/'provenance.local.json')
            provenance['key_sha256'] = review.digest(root/'key.local.json')
            (root/'provenance.local.json').write_text(json.dumps(provenance),encoding='utf-8')
            verdicts['judgments']['J001'] = {k:v for k,v in verdicts['judgments']['J001'].items() if k in ('K1','K2')}
            (root/'verdicts.local.json').write_text(json.dumps(verdicts),encoding='utf-8')
            result = self.call(root)
            self.assertEqual(result['judgment_count'],2)
            self.assertEqual(set(result['dimension_counts']),{'concise:base','concise:adapter'})


if __name__ == '__main__':
    unittest.main()
