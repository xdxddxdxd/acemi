"""Kaggle-only TT diagnostics from frozen games, never new strength matches."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _source_hashes():
    return {name: _sha(ROOT / name) for name in ('tools/tt_stats.py', 'tools/tt_diagnostics.py')}


def prepare(session_id, source_session):
    import chess.pgn
    for value in (session_id, source_session):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', value):
            raise ValueError('Use simple session ids')
    out = ROOT / 'data' / 'tt' / session_id
    if out.exists():
        raise FileExistsError('Diagnostic session exists; use its saved protocol')
    source = ROOT / 'data' / 'ab' / source_session
    original = _read(source / 'protocol.json')
    if _digest({k:v for k,v in original.items() if k != 'protocol_sha256'}) != original['protocol_sha256']:
        raise ValueError('Source protocol identity differs')
    if len(original['chunks']) != 1 or original['games'] != 100:
        raise ValueError('This diagnostic expects one completed 100-game source run')
    checkpoint = _read(source / 'chunks' / 'chunk_01.json')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', checkpoint['run_name']):
        raise ValueError('Invalid source run name')
    run = ROOT / 'data' / 'runs' / checkpoint['run_name']
    if set(checkpoint['file_sha256']) != {'meta.json', 'results.json', 'SUMMARY.md', 'games.pgn.gz', 'moves.jsonl.gz', 'engine.log.gz'}:
        raise ValueError('Incomplete source artifact checkpoint')
    for filename, digest in checkpoint['file_sha256'].items():
        if filename not in ('meta.json', 'results.json', 'SUMMARY.md', 'games.pgn.gz', 'moves.jsonl.gz', 'engine.log.gz'):
            raise ValueError('Unknown source artifact')
        if _sha(run / filename) != digest:
            raise ValueError('Source artifacts changed')
    meta, results = _read(run / 'meta.json'), _read(run / 'results.json')
    expected = {'OwnBook': False, 'NextIterationPct': 150, 'QuiescenceSEE': False}
    if (meta.get('is_demo') or results['games'] != 100 or results.get('aborted_games', 0)
            or meta['opponent']['extra_options'] != expected
            or meta['experiment']['old']['engine_tree'] != _git('rev-parse', 'HEAD:engine')):
        raise ValueError('Source must be the completed default-policy control with the same engine tree')
    by_game = {}
    with gzip.open(run / 'moves.jsonl.gz', 'rt') as stream:
        for line in stream:
            row = json.loads(line)
            if row['player'] == 'opponent':
                if type(row['nodes']) is not int or row['nodes'] < 1:
                    raise ValueError('Recorded node budgets must be positive integers')
                by_game.setdefault(row['game_no'], []).append({k:row[k] for k in ('ply', 'nodes', 'fen', 'move')})
    games = []
    with gzip.open(run / 'games.pgn.gz', 'rt') as stream:
        while (game := chess.pgn.read_game(stream)) is not None:
            if game.errors:
                raise ValueError('Source PGN contains errors')
            number = int(game.headers['Round'])
            rows = sorted(by_game.get(number, []), key=lambda row: row['ply'])
            moves = [move.uci() for move in game.mainline_moves()]
            if not rows or len({r['ply'] for r in rows}) != len(rows) or any(not 1 <= r['ply'] <= len(moves) for r in rows):
                raise ValueError('Source PGN/move stream is incomplete')
            games.append({'game_no': number, 'start_fen': game.board().fen(), 'moves': moves, 'control_rows': rows})
    if sorted(g['game_no'] for g in games) != list(range(1, 101)) or len(by_game) != 100:
        raise ValueError('Expected exactly the 100 recorded games')
    out.mkdir(parents=True)
    _write(out / 'inputs.json', {'schema_version': 1, 'games': sorted(games, key=lambda g:g['game_no'])})
    plan = {'schema_version': 1, 'kind': 'tt_replay_diagnostics', 'id': session_id,
            'session_dir': str(out), 'source_commit': _git('rev-parse', 'HEAD'),
            'engine_tree': _git('rev-parse', 'HEAD:engine'), 'collector_sources': _source_hashes(),
            'source_session': source_session, 'source_run': run.name,
            'source_protocol_sha256': original['protocol_sha256'],
            'source_artifacts': checkpoint['file_sha256'], 'inputs_sha256': _sha(out / 'inputs.json'),
            'games': 100, 'positions': sum(len(g['control_rows']) for g in games),
            'hash_mb': meta['engine_settings']['hash_mb'], 'next_iteration_pct': 150,
            'quiescence_see': False, 'control_seed_base': meta['engine_settings']['random_seed'] + 1_000_003,
            'budget': 'recorded control node count; no wall-clock deadline',
            'concurrency': min(2, os.cpu_count() or 1), 'is_strength_test': False}
    plan['protocol_sha256'] = _digest(plan)
    _write(out / 'protocol.json', plan)
    return plan


def load_plan(out):
    out = Path(out).resolve()
    plan = _read(out / 'protocol.json')
    if (str(out) != plan['session_dir']
            or _digest({k:v for k,v in plan.items() if k != 'protocol_sha256'}) != plan['protocol_sha256']
            or _sha(out / 'inputs.json') != plan['inputs_sha256']
            or _source_hashes() != plan['collector_sources']
            or _git('rev-parse', 'HEAD:engine') != plan['engine_tree']):
        raise ValueError('Diagnostic identity changed; use a new session')
    paths = ('engine', 'tools', 'tests', 'notebooks')
    if (_git('diff', plan['source_commit'], '--', *paths)
            or _git('status', '--porcelain', '--untracked-files=all', '--', *paths)):
        raise ValueError('Diagnostic code changed or is dirty')
    return plan


def _validate(plan):
    out = Path(plan['session_dir'])
    path = out / 'validation.json'
    if path.exists():
        status = _read(path)
        if (not status.get('passed') or status['protocol_sha256'] != plan['protocol_sha256']
                or _sha(out / 'tests.log') != status['tests_sha256']):
            raise ValueError('Validation failed, was interrupted or changed; inspect logs and use a new session')
        return
    _write(path, {'schema_version': 1, 'protocol_sha256': plan['protocol_sha256'], 'passed': False})
    print('Kaggle: running full correctness suite before TT replay.', flush=True)
    with (out / 'tests.log').open('w', encoding='utf-8') as stream:
        result = subprocess.run([sys.executable, '-u', '-m', 'unittest', 'discover', '-s', 'tests', '-t', '.', '-v'],
                                cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    _write(path, {'schema_version': 1, 'protocol_sha256': plan['protocol_sha256'],
                  'passed': result.returncode == 0, 'returncode': result.returncode,
                  'tests_sha256': _sha(out / 'tests.log')})
    if result.returncode:
        raise RuntimeError('Correctness tests failed; replay not started')


def _signature(result):
    return (result.best_move, result.score, result.depth, result.attempted_depth, result.nodes, result.mate)


def _replay_game(game, plan):
    from engine.board import Board
    from engine.movegen import find_legal_move
    from engine.search import Searcher
    from tools.tt_stats import TTDiagnosticSearcher, add_stats, empty_stats
    board = Board(game['start_fen'])
    plain = Searcher(hash_mb=plan['hash_mb'], next_iteration_factor=1.5, quiescence_see=False)
    measured = TTDiagnosticSearcher(hash_mb=plan['hash_mb'], next_iteration_factor=1.5, quiescence_see=False)
    seed = plan['control_seed_base'] + game['game_no'] - 1
    rngs = (random.Random(seed), random.Random(seed))
    by_ply = {r['ply']:r for r in game['control_rows']}
    total, rows = empty_stats(), []
    for ply, uci in enumerate(game['moves'], 1):
        if ply in by_ply:
            source = by_ply[ply]
            before = board.to_fen(), board.zobrist_hash, tuple(board.position_hashes)
            if before[0] != source['fen'] or uci != source['move']:
                raise ValueError(f'Replay source mismatch: game {game["game_no"]}, ply {ply}')
            measured.reset_tt_stats()
            a = plain.search(board, depth=64, nodes_limit=source['nodes'], rng=rngs[0])
            b = measured.search(board, depth=64, nodes_limit=source['nodes'], rng=rngs[1])
            if (_signature(a) != _signature(b)
                    or before != (board.to_fen(), board.zobrist_hash, tuple(board.position_hashes))
                    or plain._tt != measured._tt):
                raise RuntimeError(f'Instrumentation changed search/table/board: game {game["game_no"]}, ply {ply}')
            stats = measured.snapshot_tt_stats()
            add_stats(total, stats)
            rows.append({'ply': ply, 'node_budget': source['nodes'], 'nodes': b.nodes,
                         'depth': b.depth, 'attempted_depth': b.attempted_depth, 'score': b.score,
                         'best_move': b.best_move.uci() if b.best_move else None,
                         'tt_size_after': measured.tt_size, 'tt_capacity': measured.tt_capacity,
                         'equivalent': True, 'tt': stats})
        board.make_move(find_legal_move(board, uci))
    if len(rows) != len(game['control_rows']):
        raise ValueError('Not all source positions were measured')
    doc = {'schema_version': 1, 'protocol_sha256': plan['protocol_sha256'], 'game_no': game['game_no'],
           'positions': len(rows), 'all_searches_equivalent': True, 'tt': total, 'rows': rows}
    path = Path(plan['session_dir']) / 'games' / f'game_{game["game_no"]:03d}.json'
    if path.exists():
        raise FileExistsError('Completed diagnostic game must not be overwritten')
    _write(path, doc)
    return game['game_no']


def _completed(plan, games):
    out = Path(plan['session_dir'])
    manifest_path = out / 'checkpoints.json'
    state = _read(manifest_path) if manifest_path.exists() else {
        'schema_version': 1, 'protocol_sha256': plan['protocol_sha256'], 'games': {}}
    if state['protocol_sha256'] != plan['protocol_sha256']:
        raise ValueError('Checkpoint identity differs')
    expected = {str(g['game_no']):len(g['control_rows']) for g in games}
    if set(state['games']) - set(expected):
        raise ValueError('Unexpected checkpoint game')
    for number in expected:
        path = out / 'games' / f'game_{int(number):03d}.json'
        if not path.exists():
            if number in state['games']:
                raise ValueError('Completed diagnostic artifact is missing')
            continue
        digest = _sha(path)
        if number in state['games'] and state['games'][number] != digest:
            raise ValueError('Completed diagnostic artifact changed')
        doc = _read(path)
        if (doc['protocol_sha256'] != plan['protocol_sha256'] or doc['game_no'] != int(number)
                or doc['positions'] != expected[number] or len(doc['rows']) != expected[number]
                or not doc['all_searches_equivalent']):
            raise ValueError('Diagnostic game identity or completeness differs')
        state['games'][number] = digest
    _write(manifest_path, state)
    return state


def _summarize(plan, state):
    from tools.tt_stats import add_stats, empty_stats, validate_stats
    out = Path(plan['session_dir'])
    total, positions, nodes = empty_stats(), 0, 0
    for number in sorted(state['games'], key=int):
        doc = _read(out / 'games' / f'game_{int(number):03d}.json')
        validate_stats(doc['tt'])
        add_stats(total, doc['tt'])
        positions += doc['positions']
        nodes += sum(row['nodes'] for row in doc['rows'])
    validate_stats(total)
    cutoffs = total['cutoff_exact'] + total['cutoff_lower'] + total['cutoff_upper']
    pct = lambda a,b: round(100*a/b, 3) if b else None
    result = {'schema_version': 1, 'kind': 'tt_replay_diagnostics', 'is_strength_test': False,
              'protocol_sha256': plan['protocol_sha256'], 'games': len(state['games']),
              'requested_games': plan['games'], 'positions': positions, 'nodes': nodes,
              'status': 'completed' if len(state['games']) == plan['games'] else 'in_progress',
              'all_searches_equivalent': True if positions else None, 'tt': total,
              'probe_hit_pct': pct(total['hits'], total['probes']),
              'context_rejected_of_hits_pct': pct(total['context_rejected'], total['hits']),
              'cutoffs_of_probes_pct': pct(cutoffs, total['probes']),
              'cutoffs': cutoffs, 'tt_capacity': plan['hash_mb']*5000}
    _write(out / 'results.json', result)
    (out / 'SUMMARY.md').write_text(
        f'# TT diagnostics: {plan["id"]}\n\n- Status: {result["status"]}\n'
        f'- Replayed existing games: {result["games"]}/{plan["games"]}; positions: {positions}\n'
        f'- Source run: {plan["source_run"]}\n- Source commit: {plan["source_commit"]}\n'
        f'- Budget: {plan["budget"]}\n- New matches: 0; strength test: false\n'
        f'- Plain/instrumented searches and tables equivalent: {result["all_searches_equivalent"]}\n'
        f'- Interior probes/hits: {total["probes"]}/{total["hits"]}\n'
        f'- Context rejections: {total["context_rejected"]}; same-clock history: {total["same_clock_history_mismatch"]}\n'
        f'- Sufficient-depth entries: {total["sufficient_depth"]}; cutoffs: {cutoffs}\n'
        f'- Capacity clears: {total["capacity_clears"]}; max entries: {total["max_occupancy"]}\n\n'
        'Instrumentation times are not speed measurements. No Elo or strength decision is produced.\n', encoding='utf-8')


def run(plan, retry_incomplete=False):
    out = Path(plan['session_dir'])
    lock = out / '.running'
    if retry_incomplete and lock.exists():
        lock.unlink()  # Explicit retry only, after the user stopped the previous Kaggle session.
    with lock.open('x', encoding='utf-8') as stream:
        json.dump({'schema_version': 1, 'pid': os.getpid(), 'started_at': datetime.now(timezone.utc).isoformat()}, stream)
    try:
        _validate(plan)
        games = _read(out / 'inputs.json')['games']
        state = _completed(plan, games)
        pending = [g for g in games if str(g['game_no']) not in state['games']]
        pool = ProcessPoolExecutor(max_workers=plan['concurrency'])
        futures = []
        try:
            futures = [pool.submit(_replay_game, game, plan) for game in pending]
            for future in as_completed(futures):
                number = future.result()
                path = out / 'games' / f'game_{number:03d}.json'
                state['games'][str(number)] = _sha(path)
                _write(out / 'checkpoints.json', state)
                print(f'TT replay {len(state["games"])}/{plan["games"]}: recorded game {number}', flush=True)
        finally:
            for future in futures:
                future.cancel()
            pool.shutdown(wait=True, cancel_futures=True)
            state = _completed(plan, games)
            _summarize(plan, state)
    finally:
        lock.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('--id', required=True)
    prep.add_argument('--source-session', required=True)
    work = commands.add_parser('run')
    work.add_argument('--session', type=Path, required=True)
    work.add_argument('--retry-incomplete', action='store_true')
    verify = commands.add_parser('verify')
    verify.add_argument('--session', type=Path, required=True)
    args = parser.parse_args(argv)
    if not Path('/kaggle/working').is_dir():
        parser.error('TT diagnostics and searches run only in Kaggle')
    if args.command == 'prepare':
        plan = prepare(args.id, args.source_session)
        print(f'Prepared {plan["games"]} recorded games / {plan["positions"]} control positions; no new matches')
    elif args.command == 'verify':
        plan = load_plan(args.session)
        print(f'Verified saved TT protocol: {plan["games"]} recorded games / {plan["positions"]} positions')
    else:
        try:
            run(load_plan(args.session), args.retry_incomplete)
        except Exception:
            if args.session.is_dir():
                (args.session / 'error.log').write_text(traceback.format_exc(), encoding='utf-8')
            raise
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
