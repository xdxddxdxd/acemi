"""Kaggle-only gates for the SEE ordering experiment; no implicit local searches."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

REFERENCE_COMMIT = "4068a0459f8119274014cd466270a2ffd3cd30c3"


def _git(source, *args):
    return subprocess.run(['git', '-C', str(source), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def _worker(source, out, enabled):
    # Fresh process: even the baseline imports its own engine and benchmark positions.
    sys.path.insert(0, str(source))
    import engine
    from engine.board import Board
    from engine.search import Searcher
    from tools.bench import POSITIONS
    if Path(engine.__file__).resolve().parents[1] != source:
        raise RuntimeError('Wrong source imported')
    rows = []
    for name, fen in POSITIONS:
        board = Board(fen)
        before = board.to_fen(), board.zobrist_hash, list(board.position_hashes)
        searcher = Searcher(quiescence_see=True) if enabled else Searcher()
        started = time.perf_counter()
        result = searcher.search(board, depth=3)
        elapsed = time.perf_counter() - started
        if before != (board.to_fen(), board.zobrist_hash, board.position_hashes):
            raise RuntimeError(f'Board was not restored: {name}')
        rows.append({'name': name, 'fen': fen, 'score': result.score, 'depth': result.depth,
                     'nodes': result.nodes, 'best_move': result.best_move.uci() if result.best_move else None,
                     'seconds': elapsed})
    _write(out, {'schema_version': 1, 'source_commit': _git(source, 'rev-parse', 'HEAD'),
                 'engine_tree': _git(source, 'rev-parse', 'HEAD:engine'),
                 'quiescence_see': enabled, 'depth': 3, 'positions': rows,
                 'total_nodes': sum(r['nodes'] for r in rows),
                 'total_seconds': sum(r['seconds'] for r in rows)})


def _command(args, cwd, log):
    with log.open('w', encoding='utf-8') as stream:
        result = subprocess.run(args, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Validation failed (exit {result.returncode}); inspect {log}')


def validate(plan, reference):
    source = Path(plan['sources']['new']['path']).resolve()
    reference = reference.resolve()
    for label, checkout, expected in (('candidate', source, plan['sources']['new']['commit']),
                                       ('reference', reference, REFERENCE_COMMIT)):
        if _git(checkout, 'rev-parse', 'HEAD') != expected:
            raise ValueError(f'{label} source commit differs')
        if _git(checkout, 'status', '--porcelain', '--untracked-files=all', '--', 'engine', 'tests', 'tools'):
            raise ValueError(f'{label} source is dirty')
    out = Path(plan['session_dir']) / 'validation'
    out.mkdir(exist_ok=True)
    identity = {'protocol_sha256': plan['protocol_sha256'],
                'validator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'candidate_commit': plan['sources']['new']['commit'], 'reference_commit': REFERENCE_COMMIT}
    status = out / 'status.json'
    if status.exists():
        saved = json.loads(status.read_text())
        if saved.get('identity') != identity:
            raise ValueError('Validation identity changed; use a new experiment id')
        if saved.get('passed'):
            for name, digest in saved['artifacts'].items():
                if hashlib.sha256((out / name).read_bytes()).hexdigest() != digest:
                    raise ValueError('Completed validation artifact changed')
            print('Verified completed validation; searches are not repeated.', flush=True)
            return
        raise ValueError('Prior validation failed or was interrupted; inspect logs and use a new SESSION_ID')
    _write(status, {'schema_version': 1, 'identity': identity, 'passed': False, 'state': 'started'})
    try:
        print('Kaggle: running full correctness suite before any match.', flush=True)
        _command([sys.executable, '-u', '-m', 'unittest', 'discover', '-s', 'tests', '-t', '.', '-v'],
                 source, out / 'tests.log')
        for label, checkout, enabled in (('reference', reference, False), ('see-off', source, False), ('see-on', source, True)):
            print('Kaggle fixed-depth diagnostic:', label, flush=True)
            _command([sys.executable, str(Path(__file__).resolve()), '--worker', '--source', str(checkout),
                      '--out', str(out / (label + '.json')), *(['--see'] if enabled else [])],
                     checkout, out / (label + '.log'))
        base = json.loads((out / 'reference.json').read_text())
        off = json.loads((out / 'see-off.json').read_text())
        keys = ('name', 'fen', 'score', 'depth', 'nodes', 'best_move')
        if ([tuple(r[k] for k in keys) for r in base['positions']]
                != [tuple(r[k] for k in keys) for r in off['positions']]):
            raise RuntimeError('SEE-off no longer matches the validated reference search')
        artifacts = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in out.iterdir() if p.name != 'status.json'}
        _write(status, {'schema_version': 1, 'identity': identity, 'passed': True,
                        'state': 'completed', 'see_off_matches_reference': True, 'artifacts': artifacts,
                        'note': 'SEE-on nodes/timing may differ. Diagnostic timing is not an Elo decision.'})
    except Exception as error:
        _write(status, {'schema_version': 1, 'identity': identity, 'passed': False,
                        'state': 'failed', 'error': str(error)})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--see', action='store_true')
    parser.add_argument('--session', type=Path)
    parser.add_argument('--reference', type=Path)
    args = parser.parse_args(argv)
    # Check before any import of engine code or subprocess that can run a search.
    if not Path('/kaggle/working').is_dir():
        parser.error('Validation searches run only in Kaggle')
    if args.worker:
        if args.source is None or args.out is None:
            parser.error('Worker requires --source and --out')
        _worker(args.source.resolve(), args.out, args.see)
    else:
        if args.session is None or args.reference is None:
            parser.error('Use --session and --reference')
        from tools.ab_compare import load_plan
        validate(load_plan(args.session), args.reference)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
