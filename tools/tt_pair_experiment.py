"""Kaggle-only correctness, retention and cost gates before the TT pair A/B."""

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import traceback

from tools import qsee_validation as qv, tt_diagnostics as td


def _prepare_replay(comparison, pair):
    out = td.ROOT / 'data' / 'tt' / (comparison['id'] + ('-replay-pair' if pair else '-replay-single'))
    if (out / 'protocol.json').exists():
        plan = td.load_plan(out)
        if (plan.get('tt_two_contexts') != pair
                or plan.get('comparison_protocol_sha256') != comparison['protocol_sha256']):
            raise ValueError('Replay belongs to another comparison')
        return plan
    if out.exists():
        raise ValueError('Incomplete replay preparation; use a new comparison id')
    source = td.ROOT / 'data' / 'tt' / 'tt-usage-node-replay-v1'
    original = td._read(source / 'protocol.json')
    if (td._digest({k:v for k,v in original.items() if k != 'protocol_sha256'}) != original['protocol_sha256']
            or td._sha(source / 'inputs.json') != original['inputs_sha256']
            or original['games'] != 100 or original.get('quiescence_see') is not False
            or original.get('next_iteration_pct') != 150):
        raise ValueError('Frozen baseline inputs changed')
    games = td._read(source / 'inputs.json')['games']
    games = sorted(games, key=lambda game:game['game_no'])[::5]  # fixed 20 of 100, not new matches
    if [g['game_no'] for g in games] != list(range(1, 101, 5)):
        raise ValueError('Unexpected recorded game selection')
    out.mkdir(parents=True)
    td._write(out / 'inputs.json', {'schema_version': 1, 'games': games})
    plan = {k:v for k,v in original.items() if k != 'protocol_sha256'}
    plan.update({'id': out.name, 'session_dir': str(out), 'source_commit': td._git('rev-parse', 'HEAD'),
                 'engine_tree': td._git('rev-parse', 'HEAD:engine'), 'collector_sources': td._source_hashes(),
                 'inputs_sha256': td._sha(out / 'inputs.json'), 'games': 20,
                 'positions': sum(len(g['control_rows']) for g in games),
                 'recorded_source_games': 100, 'selected_game_numbers': [g['game_no'] for g in games],
                 'frozen_source_tt_protocol_sha256': original['protocol_sha256'],
                 'frozen_source_inputs_sha256': original['inputs_sha256'],
                 'tt_two_contexts': pair, 'comparison_protocol_sha256': comparison['protocol_sha256'],
                 'comparison_validation': str(Path(comparison['session_dir']) / 'validation'),
                 'preparer_sha256': td._sha(Path(__file__))})
    plan['protocol_sha256'] = td._digest(plan)
    td._write(out / 'protocol.json', plan)
    return plan


def cost_decision(single, pair, secondary_cutoffs):
    """Eligibility to spend matches, not a strength or merge decision."""
    if len(single) != 3 or len(pair) != 3:
        raise ValueError('Need three alternating benchmark passes per policy')
    fields = ('name', 'fen', 'score', 'depth', 'nodes', 'best_move')
    for runs in (single, pair):
        signatures = [tuple(tuple(row[k] for k in fields) for row in run['positions']) for run in runs]
        if len(set(signatures)) != 1:
            raise ValueError('Repeated fixed-depth search is not deterministic')
    times = [statistics.median(run['total_seconds'] for run in runs) for runs in (single, pair)]
    if min(times) <= 0:
        raise ValueError('Invalid benchmark elapsed time')
    nodes = [runs[0]['total_nodes'] for runs in (single, pair)]
    reasons = []
    if secondary_cutoffs <= 0:
        reasons.append('No measured score cutoffs from the second slot')
    if nodes[1] > nodes[0]:
        reasons.append('Candidate searched more nodes at the same fixed depth')
    ratio = times[1] / times[0]
    if ratio > 1.10:
        reasons.append('Candidate median fixed-depth time is over 10% slower')
    return {'eligible_to_run_match': not reasons, 'reasons': reasons,
            'single_median_seconds': times[0], 'pair_median_seconds': times[1],
            'time_ratio': ratio, 'single_nodes': nodes[0], 'pair_nodes': nodes[1],
            'second_slot_cutoffs': secondary_cutoffs, 'slowdown_tolerance': 1.10,
            'note': 'Exploratory cost/retention gate only; no strength or merge decision.'}


def run(comparison, reference, retry_incomplete=False):
    qv.validate(comparison, reference, 'tt-pair')
    plans = [_prepare_replay(comparison, pair) for pair in (False, True)]
    for plan in plans:
        print('Kaggle TT retention replay:', 'pair' if plan['tt_two_contexts'] else 'single', flush=True)
        td.run(td.load_plan(plan['session_dir']), retry_incomplete)
    out = Path(comparison['session_dir'])
    validation = out / 'validation'
    files = [validation / f'bench-{i}-{label}.json' for label in ('single', 'pair') for i in (1, 2, 3)]
    benchmark = [[td._read(validation / f'bench-{i}-{label}.json') for i in (1, 2, 3)] for label in ('single', 'pair')]
    replay_files = [Path(p['session_dir']) / 'results.json' for p in plans]
    results = [td._read(path) for path in replay_files]
    for doc, plan in zip(results, plans):
        if (doc['status'] != 'completed' or doc['games'] != 20
                or doc['protocol_sha256'] != plan['protocol_sha256'] or not doc['all_searches_equivalent']):
            raise ValueError('Retention replay did not complete correctly')
    decision = cost_decision(benchmark[0], benchmark[1], results[1]['tt']['second_slot_cutoffs'])
    doc = {'schema_version': 1, 'protocol_sha256': comparison['protocol_sha256'], **decision,
           'artifacts': {path.relative_to(td.ROOT).as_posix(): td._sha(path) for path in files + replay_files}}
    gate = out / 'eligibility.json'
    if gate.exists() and td._read(gate) != doc:
        raise ValueError('Completed eligibility inputs changed; use a new experiment id')
    td._write(gate, doc)
    print(json.dumps(doc, indent=2), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--retry-incomplete', action='store_true')
    args = parser.parse_args(argv)
    if not Path('/kaggle/working').is_dir():
        parser.error('TT comparison searches run only in Kaggle')
    from tools.ab_compare import load_plan
    try:
        run(load_plan(args.session), args.reference, args.retry_incomplete)
    except Exception:
        if args.session.is_dir():
            (args.session / 'preflight_error.log').write_text(traceback.format_exc(), encoding='utf-8')
        raise
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
