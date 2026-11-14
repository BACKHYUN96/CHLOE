"""Validate a submitted blind review and publish content-free candidate aggregates.

The ratings, key and per-card responses remain in ignored local artifacts. Explicit
preferences are authoritative; comments never silently change a vote or approve training.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from data_contract import ROOT

DIMENSIONS = ('naturalness', 'content', 'criterion')
OUTCOMES = ('base', 'adapter', 'tie', 'both_bad', 'hold', 'unrated')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def read(path):
    path = Path(path)
    if path.stat().st_size > 1024*1024:
        raise ValueError('Review artifact is too large')
    return json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=unique_object)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def aggregate(ratings, packet, key):
    packet_id = packet['packet_id']
    if (ratings.get('version') != 1 or ratings.get('packet_id') != packet_id
            or key.get('packet_id') != packet_id):
        raise ValueError('Packet ID/version mismatch')
    ids = [item['id'] for item in packet['items']]
    if (len(set(ids)) != len(ids) or not isinstance(ratings.get('ratings'), dict)
            or set(ids) != set(ratings['ratings']) or set(ids) != set(key['items'])):
        raise ValueError('Missing, duplicate or unknown card')
    overall = Counter({outcome: 0 for outcome in OUTCOMES})
    categories, registers, details = {}, {}, []
    scores = {candidate: {dim: [] for dim in DIMENSIONS} for candidate in ('base', 'adapter')}
    comment_count = 0
    for item in packet['items']:
        ident = item['id']
        rating = ratings['ratings'][ident]
        secret = key['items'][ident]
        mapping = secret['mapping']
        if (set(mapping) != {'A', 'B'} or set(mapping.values()) != {'base', 'adapter'}
                or secret['register'] not in ('casual', 'polite')
                or item['register'] != {'casual': '반말', 'polite': '존댓말'}[secret['register']]
                or len(item['turns']) != len(secret['source_case_ids'])):
            raise ValueError('Malformed mapping/context block')
        if not isinstance(rating, dict) or set(rating) != {'preference', 'A', 'B', 'comment'}:
            raise ValueError('Malformed rating')
        pref = rating['preference']
        if pref is not None and pref not in ('A', 'B', 'tie', 'both_bad', 'hold'):
            raise ValueError('Invalid preference')
        comment = rating['comment']
        if not isinstance(comment, str) or len(comment) > 4000:
            raise ValueError('Invalid comment')
        comment_count += bool(comment.strip())
        outcome = mapping[pref] if pref in ('A', 'B') else ('unrated' if pref is None else pref)
        overall[outcome] += 1
        category = categories.setdefault(item['category'], Counter({outcome: 0 for outcome in OUTCOMES}))
        register = registers.setdefault(secret['register'], Counter({outcome: 0 for outcome in OUTCOMES}))
        category[outcome] += 1
        register[outcome] += 1
        model_scores = {}
        for side, candidate in mapping.items():
            values = rating[side]
            if not isinstance(values, dict) or set(values) != set(DIMENSIONS):
                raise ValueError('Invalid score dimensions')
            for dim, value in values.items():
                if value is not None and (type(value) is not int or not 1 <= value <= 5):
                    raise ValueError('Score must be an integer 1..5 or null')
                if value is not None:
                    scores[candidate][dim].append(value)
            model_scores[candidate] = values.copy()
        details.append({'id': ident, 'category': item['category'], 'register': secret['register'],
                        'outcome': outcome, 'scores': model_scores, 'comment': comment,
                        'source_case_ids': secret['source_case_ids'],
                        'turns': [{'question': turn['question'],
                                   **{candidate: turn[side] for side, candidate in mapping.items()}}
                                  for turn in item['turns']]})
    progress = {'decided': sum(overall[o] for o in ('base', 'adapter', 'tie', 'both_bad')),
                'hold': overall['hold'], 'untouched': overall['unrated']}
    all_decided = progress['decided'] == len(ids)
    # Recompute from votes, never trust potentially stale UI progress metadata.
    if 'progress' in ratings and ratings['progress'] != progress:
        raise ValueError('Export progress disagrees with actual votes')
    if 'all_cards_decided' in ratings and ratings['all_cards_decided'] is not all_decided:
        raise ValueError('Export completion flag disagrees with actual votes')
    numeric = {candidate: {dim: {'count': len(values),
                                'mean': sum(values)/len(values) if values else None}
                           for dim, values in dimensions.items()}
               for candidate, dimensions in scores.items()}
    public = {'version': 1, 'packet_id': packet_id, 'review_status': 'submitted_with_holds' if progress['hold']
              else ('submitted_with_unrated' if progress['untouched'] else 'all_cards_decided'),
              'human_review_submitted': True, 'reviewer_count': 1,
              'all_cards_touched': progress['untouched'] == 0, 'all_cards_decided': all_decided,
              'quality_improvement_verified': False, 'unit': 'card; a 10-turn context block counts once',
              'cards': len(ids), 'paired_turns': sum(len(i['turns']) for i in packet['items']),
              'progress': progress, 'outcomes': dict(overall),
              'category_outcomes': {k: dict(v) for k, v in categories.items()},
              'register_outcomes': {k: dict(v) for k, v in registers.items()},
              'exclusive_preferences': {'base': overall['base'], 'adapter': overall['adapter'],
                                        'total': overall['base']+overall['adapter']},
              'numeric_scores': numeric, 'commented_cards': comment_count,
              'comments_included': False, 'card_mapping_included': False,
              'model_responses_included': False, 'training_approved_by_submission': False,
              'export_approval_created': False}
    return public, details


def summarize(ratings_path, packet_html, manifest_path, key_path, private_output, public_output, root=ROOT):
    ratings_path, packet_html, manifest_path, key_path, private_output, public_output = [
        Path(p).resolve() for p in (ratings_path, packet_html, manifest_path, key_path, private_output, public_output)]
    ignored = (root/'artifacts/llm-training').resolve()
    key_path.relative_to(ignored)
    private_output.relative_to(ignored)
    public_output.relative_to((root/'docs/validation').resolve())
    if private_output == ignored or private_output.exists() or public_output.exists():
        raise FileExistsError('Use fresh output destinations; never replace originals')
    manifest = read(manifest_path)
    if digest(key_path) != manifest['key_commitment_sha256']:
        raise ValueError('Key commitment mismatch')
    if digest(packet_html) != manifest['reviewer_files_sha256']['review.html']:
        raise ValueError('Reviewer packet digest mismatch')
    html = packet_html.read_text(encoding='utf-8')
    match = re.search(r'<script id="packet" type="application/json">(.*?)</script>', html, re.S)
    if not match:
        raise ValueError('Missing packet data')
    packet = json.loads(match[1], object_pairs_hook=unique_object)
    key, ratings = read(key_path), read(ratings_path)
    if (key['source_summary_sha256'] != manifest['source_summary_sha256']
            or packet['packet_id'] != manifest['packet_id']):
        raise ValueError('Source provenance mismatch')
    public, details = aggregate(ratings, packet, key)
    if public['cards'] != manifest['cards'] or public['paired_turns'] != manifest['paired_turns']:
        raise ValueError('Packet size mismatch')
    public.update({'aggregated_at': datetime.now(timezone.utc).isoformat(),
                   'ratings_sha256': digest(ratings_path), 'packet_html_sha256': digest(packet_html),
                   'key_commitment_sha256': digest(key_path),
                   'source_summary_sha256': key['source_summary_sha256']})
    private_output.mkdir(parents=True, exist_ok=False)
    # Preserve exact original bytes and leave the user's Downloads file untouched.
    with (private_output/'ratings.original.local.json').open('xb') as stream:
        stream.write(ratings_path.read_bytes())
    write(private_output/'deblinded-details.local.json', {'packet_id': packet['packet_id'], 'cards': details})
    write(private_output/'summary.local.json', public)
    public_output.parent.mkdir(parents=True, exist_ok=True)
    write(public_output, public)
    return public


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('ratings', 'packet-html', 'manifest', 'key', 'private-output', 'public-output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    public = summarize(args.ratings, args.packet_html, args.manifest, args.key,
                       args.private_output, args.public_output)
    print(json.dumps({'cards': public['cards'], 'outcomes': public['outcomes'],
                      'progress': public['progress']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
