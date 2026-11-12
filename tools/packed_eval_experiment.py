"""Kaggle-only equivalence and speed gates before the packed base-eval A/B."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import traceback

REFERENCE_COMMIT = 'b22b8597dcdf40fa632d9585cd4901c87d97b306'
SIGNATURE = ('name', 'fen', 'score', 'depth', 'nodes', 'best_move', 'mate', 'attempted_depth')


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git(source, *args):
    return subprocess.run(['git', '-C', str(source), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _worker(source, out, packed):
    # No parent-kernel modules or imports from the collector's engine are reused.
    source = source.resolve()
    sys.path.insert(0, str(source))
    import engine
    from engine.board import Board
    from engine.eval.classic import EvalFlags
    from engine.search import Searcher
    from tools.bench import POSITIONS
    if Path(engine.__file__).resolve().parents[1] != source:
        raise ValueError('Wrong engine source imported')
    flags = EvalFlags()
    if packed:
        flags.packed_base = True
    rows = []
    for name, fen in POSITIONS:
        board = Board(fen)
        before = board.to_fen(), board.zobrist_hash, list(board.position_hashes)
        searcher = Searcher(hash_mb=16, eval_flags=flags, tt_two_contexts=True)
        started = time.perf_counter()
        result = searcher.search(board, depth=4)
        seconds = time.perf_counter() - started
        if before != (board.to_fen(), board.zobrist_hash, board.position_hashes):
            raise ValueError('Board not restored: ' + name)
        rows.append(dict(name=name, fen=fen, score=result.score, depth=result.depth,
                         nodes=result.nodes, best_move=result.best_move.uci() if result.best_move else None,
                         mate=result.mate, attempted_depth=result.attempted_depth, seconds=seconds))
    _write(out, dict(schema_version=1, source_commit=_git(source, 'rev-parse', 'HEAD'),
                     engine_tree=_git(source, 'rev-parse', 'HEAD:engine'), packed_base=packed,
                     tt_two_contexts=True, depth=4, positions=rows,
                     total_nodes=sum(r['nodes'] for r in rows),
                     total_seconds=sum(r['seconds'] for r in rows)))


def decision(reference, plain, packed):
    if len(plain) != 3 or len(packed) != 3:
        raise ValueError('Three alternating passes per policy are required')
    signature = lambda run: [[row[k] for k in SIGNATURE] for row in run['positions']]
    expected = signature(reference)
    if not expected or any(signature(run) != expected for run in [*plain, *packed]):
        raise ValueError('Fixed-depth score/move/depth/node equivalence failed')
    for run in [reference, *plain, *packed]:
        if (run['total_seconds'] <= 0 or run['total_nodes'] != sum(r['nodes'] for r in run['positions'])
                or run['depth'] != 4 or not run['tt_two_contexts']):
            raise ValueError('Invalid fixed-depth benchmark')
    a, b = [statistics.median(run['total_seconds'] for run in group) for group in (plain, packed)]
    ratio = b / a
    eligible = ratio <= .98
    return dict(eligible_to_run_match=eligible,
                reasons=[] if eligible else ['Packed evaluation did not reduce median search time by at least 2%'],
                plain_median_seconds=a, packed_median_seconds=b, time_ratio=ratio,
                required_time_ratio=.98, all_search_signatures_equal=True,
                note='Exploratory speed gate, not proof of strength or a merge decision.')


def _command(args, cwd, log):
    with Path(log).open('w', encoding='utf-8') as stream:
        result = subprocess.run(args, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Validation failed; inspect {log}')


def validate(session, reference):
    from tools import ab_compare as ab
    plan = ab.load_plan(session)
    source = Path(plan['sources']['new']['path']).resolve()
    reference = reference.resolve()
    common = {'TTTwoContexts': True, 'QuiescenceSEE': False, 'NextIterationPct': 150}
    expected = {side: {**common, 'EvalPackedBase': enabled} for side, enabled in [('new', True), ('old', False)]}
    if (plan['feature_options'] != expected or plan['sources']['new']['commit'] != plan['sources']['old']['commit']
            or plan['games'] != 100 or plan['chunk_games'] != 100 or plan['movetime_ms'] != 100):
        raise ValueError('Experiment must isolate packed evaluation at 100 ms, one bulk 100-game run')
    for root, commit in [(source, plan['sources']['new']['commit']), (reference, REFERENCE_COMMIT)]:
        if (_git(root, 'rev-parse', 'HEAD') != commit
                or _git(root, 'status', '--porcelain', '--untracked-files=all', '--', 'engine', 'tools', 'tests')):
            raise ValueError('Pinned source differs or is dirty')
    out = Path(session) / 'validation'
    out.mkdir(exist_ok=True)
    identity = dict(protocol_sha256=plan['protocol_sha256'], experiment='packed-eval',
                    validator_sha256=_sha(__file__), candidate_commit=plan['sources']['new']['commit'],
                    reference_commit=REFERENCE_COMMIT)
    status_path = out / 'status.json'
    if status_path.exists():
        status = _read(status_path)
        if status['identity'] != identity or not status.get('passed'):
            raise ValueError('Previous validation differs or is incomplete; use a new SESSION_ID')
        for path, digest in status['artifacts'].items():
            if _sha(out / path) != digest:
                raise ValueError('Saved validation artifact changed')
        gate = _read(Path(session) / 'eligibility.json')
        if gate['protocol_sha256'] != plan['protocol_sha256']:
            raise ValueError('Saved eligibility belongs to another protocol')
        for path, digest in gate['artifacts'].items():
            if _sha(ab.ROOT / path) != digest:
                raise ValueError('Saved eligibility artifact changed')
        # Recompute the cost decision; a hand-edited eligibility boolean cannot bypass it.
        current = decision(_read(out/'reference.json'),
                           [_read(out/f'bench-{i}-plain.json') for i in (1, 2, 3)],
                           [_read(out/f'bench-{i}-packed.json') for i in (1, 2, 3)])
        if any(gate.get(k) != v for k, v in current.items()):
            raise ValueError('Saved eligibility decision changed')
        print('Verified completed preflight; no searches repeated.', flush=True)
        return
    _write(status_path, dict(schema_version=1, identity=identity, passed=False, state='started'))
    try:
        print('Kaggle: full correctness suite, then seven depth-4 benchmark passes.', flush=True)
        _command([sys.executable, '-u', '-m', 'unittest', 'discover', '-s', 'tests', '-t', '.', '-v'], source, out/'tests.log')
        tasks = [('reference', reference, False)]
        for i in (1, 2, 3):
            tasks += [(f'bench-{i}-{label}', source, label == 'packed')
                      for label in (('plain', 'packed') if i % 2 else ('packed', 'plain'))]
        for label, root, packed in tasks:
            print('Kaggle fixed-depth:', label, flush=True)
            _command([sys.executable, str(Path(__file__).resolve()), '--worker', '--source', str(root),
                      '--out', str(out/(label+'.json')), *(['--packed'] if packed else [])], root, out/(label+'.log'))
        gate = decision(_read(out/'reference.json'), [_read(out/f'bench-{i}-plain.json') for i in (1, 2, 3)],
                        [_read(out/f'bench-{i}-packed.json') for i in (1, 2, 3)])
        artifacts = {p.name: _sha(p) for p in out.iterdir() if p.suffix in ('.log', '.json') and p != status_path}
        _write(status_path, dict(schema_version=1, identity=identity, passed=True, state='completed', artifacts=artifacts))
        gate.update(schema_version=1, protocol_sha256=plan['protocol_sha256'],
                    artifacts={str(p.relative_to(ab.ROOT)): _sha(p) for p in out.iterdir() if p.is_file()})
        _write(Path(session)/'eligibility.json', gate)
        print(json.dumps(gate, indent=2), flush=True)
    except Exception as error:
        _write(status_path, dict(schema_version=1, identity=identity, passed=False, state='failed', error=str(error)))
        (out/'preflight_error.log').write_text(traceback.format_exc(), encoding='utf-8')
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--packed', action='store_true')
    parser.add_argument('--session', type=Path)
    parser.add_argument('--reference', type=Path)
    args = parser.parse_args(argv)
    if not Path('/kaggle/working').is_dir():
        parser.error('Searches, benchmarks and matches are Kaggle-only')
    if args.worker:
        if not args.source or not args.out:
            parser.error('Worker needs --source and --out')
        _worker(args.source, args.out, args.packed)
    else:
        if not args.session or not args.reference:
            parser.error('Need --session and --reference')
        validate(args.session, args.reference)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
