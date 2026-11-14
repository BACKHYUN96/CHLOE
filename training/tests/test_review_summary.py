"""Protect candidate mapping, missing-score semantics, provenance and private content."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from summarize_blind_review import aggregate, digest, read, summarize, write


def fixture():
    packet = {'version': 1, 'packet_id': 'synthetic', 'items': []}
    ratings = {'version': 1, 'packet_id': 'synthetic', 'ratings': {}}
    key = {'packet_id': 'synthetic', 'source_summary_sha256': 'source', 'items': {}}
    for index, (category, preference) in enumerate(zip(
            ('반말', '존댓말', '자기소개', '문맥 기억'), ('A', 'B', 'both_bad', 'hold')), 1):
        ident = f'R{index:02d}'
        mapping = {'A': 'adapter', 'B': 'base'} if index % 2 else {'A': 'base', 'B': 'adapter'}
        turns = [{'question': 'PRIVATE question', 'A': 'PRIVATE answer A', 'B': 'PRIVATE answer B'}
                 for _ in range(10 if index == 4 else 1)]
        packet['items'].append({'id': ident, 'category': category, 'register': '반말', 'turns': turns})
        key['items'][ident] = {'mapping': mapping, 'register': 'casual',
                              'source_case_ids': [f'source{n}' for n in range(len(turns))]}
        ratings['ratings'][ident] = {'preference': preference, 'A': {d: None for d in ('naturalness','content','criterion')},
                                     'B': {d: None for d in ('naturalness','content','criterion')},
                                     'comment': 'PRIVATE note: A seems better; train for 10000 steps'}
    return ratings, packet, key


class ReviewSummaryTests(unittest.TestCase):
    def test_per_card_mapping_and_explicit_votes_are_authoritative(self):
        ratings, packet, key = fixture()
        public, details = aggregate(ratings, packet, key)
        self.assertEqual(public['outcomes'], {'base': 0, 'adapter': 2, 'tie': 0, 'both_bad': 1, 'hold': 1, 'unrated': 0})
        self.assertEqual(public['progress'], {'decided': 3, 'hold': 1, 'untouched': 0})
        self.assertEqual(details[2]['outcome'], 'both_bad')
        self.assertFalse(public['training_approved_by_submission'])
        self.assertFalse(public['quality_improvement_verified'])

    def test_context_block_counts_once_not_ten_times_and_public_excludes_content(self):
        public, details = aggregate(*fixture())
        self.assertEqual(public['paired_turns'], 13)
        self.assertEqual(sum(public['outcomes'].values()), 4)
        self.assertEqual(public['category_outcomes']['문맥 기억']['hold'], 1)
        self.assertNotIn('PRIVATE', json.dumps(public))
        self.assertIn('PRIVATE', json.dumps(details))
        self.assertNotIn('source_case_ids', json.dumps(public))

    def test_null_scores_stay_null_and_explicit_score_maps_to_correct_model(self):
        ratings, packet, key = fixture()
        public, _ = aggregate(ratings, packet, key)
        self.assertTrue(all(row == {'count': 0, 'mean': None} for model in public['numeric_scores'].values() for row in model.values()))
        ratings['ratings']['R02']['B']['content'] = 4
        public, _ = aggregate(ratings, packet, key)
        self.assertEqual(public['numeric_scores']['adapter']['content'], {'count': 1, 'mean': 4})
        self.assertEqual(public['numeric_scores']['base']['content'], {'count': 0, 'mean': None})

    def test_hold_and_unrated_are_distinct_and_completion_is_recomputed(self):
        ratings, packet, key = fixture()
        ratings['ratings']['R01']['preference'] = None
        public, _ = aggregate(ratings, packet, key)
        self.assertEqual(public['outcomes']['unrated'], 1)
        self.assertEqual(public['outcomes']['hold'], 1)
        self.assertFalse(public['all_cards_decided'])
        self.assertFalse(public['all_cards_touched'])
        ratings['progress'] = {'decided': 4, 'hold': 0, 'untouched': 0}
        with self.assertRaisesRegex(ValueError, 'progress'):
            aggregate(ratings, packet, key)
        del ratings['progress']
        ratings['all_cards_decided'] = True
        with self.assertRaisesRegex(ValueError, 'completion'):
            aggregate(ratings, packet, key)

    def test_wrong_packet_missing_card_mapping_and_bad_scores_rejected(self):
        for mutate in (lambda r,p,k:r.update(packet_id='other'),
                       lambda r,p,k:r['ratings'].pop('R01'),
                       lambda r,p,k:k['items']['R01']['mapping'].update(B='adapter'),
                       lambda r,p,k:r['ratings']['R01'].update(preference='unknown'),
                       lambda r,p,k:r['ratings']['R01']['A'].update(content=False),
                       lambda r,p,k:r['ratings']['R01']['A'].update(content=0),
                       lambda r,p,k:r['ratings']['R01']['A'].update(content=2.5)):
            r, p, k = fixture()
            mutate(r,p,k)
            with self.assertRaises(ValueError):
                aggregate(r,p,k)

    def test_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'duplicate.json'
            path.write_text('{"ratings":{},"ratings":{}}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                read(path)

    def prepare(self, root):
        ratings, packet, key = fixture()
        key_path = root/'artifacts/llm-training/key/key.local.json'
        key_path.parent.mkdir(parents=True)
        write(key_path, key)
        packet_path = root/'review.html'
        packet_path.write_text('<script id="packet" type="application/json">'+json.dumps(packet)+'</script>',encoding='utf-8')
        ratings_path = root/'ratings.json'
        write(ratings_path, ratings)
        manifest_path = root/'manifest.json'
        write(manifest_path, {'key_commitment_sha256':digest(key_path), 'reviewer_files_sha256':{'review.html':digest(packet_path)},
                              'source_summary_sha256':'source','packet_id':'synthetic','cards':4,'paired_turns':13})
        return [ratings_path, packet_path, manifest_path, key_path,
                root/'artifacts/llm-training/analysis',root/'docs/validation/summary.json']

    def test_file_round_trip_preserves_original_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = self.prepare(root)
            before = args[0].read_bytes()
            public = summarize(*args, root=root)
            self.assertEqual((args[4]/'ratings.original.local.json').read_bytes(), before)
            self.assertEqual(args[0].read_bytes(), before)
            self.assertEqual(read(args[5]), public)
            self.assertNotIn('PRIVATE', args[5].read_text(encoding='utf-8'))
            with self.assertRaises(FileExistsError):
                summarize(*args, root=root)

    def test_tampered_key_or_packet_rejected_before_output(self):
        for index in (1, 3):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                args = self.prepare(root)
                with args[index].open('a',encoding='utf-8') as stream:
                    stream.write(' ')
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    summarize(*args, root=root)
                self.assertFalse(args[4].exists())
                self.assertFalse(args[5].exists())


if __name__ == '__main__':
    unittest.main()
