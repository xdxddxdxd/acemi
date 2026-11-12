"""Kaggle-only, checkpointed position diagnosis from immutable played games."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import traceback

import chess
import chess.engine
import chess.pgn

ROOT = Path(__file__).resolve().parents[1]
ENGINE_COMMIT = '38b0722b084552d8e94eb62e3558d447b641969c'
SOURCE_SESSION = 'packed-eval-100ms-100games-v1'
CODE_PATHS = ('tools/tactical_diagnostics.py', 'tests/test_tactical_diagnostics.py',
              'notebooks/kaggle_tactical_diagnostics.ipynb')
ACEMI_OPTIONS = {'OwnBook': False, 'TTTwoContexts': True, 'EvalPackedBase': True,
                 'QuiescenceSEE': False, 'NextIterationPct': 150, 'Hash': 16,
                 'Threads': 1, 'Seed': 1, 'Contempt': 0, 'PVS': False,
                 'CheckExtension': False, 'LateMovePruning': False}


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _digest(doc):
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True,
                          text=True, capture_output=True).stdout.strip()


def select_games(games):
    """Predeclared: four shortest losses; two shortest wins and draws each."""
    selected = []
    for outcome, count, group in [(0, 4, 'loss'), (1, 2, 'win_comparison'), (.5, 2, 'draw_comparison')]:
        choices = sorted((g for g in games if g['score'] == outcome),
                         key=lambda g: (len(g['moves']), g['game_no']))[:count]
        if len(choices) != count:
            raise ValueError('Source does not have the prescribed outcome groups')
        selected += [{**g, 'group': group} for g in choices]
    return selected


def freeze_positions(games, rows):
    """Retain the complete position history, with recorded candidate moves."""
    positions = []
    for game in select_games(games):
        board = chess.Board(game['start_fen'])
        own = sorted((r for r in rows if r['game_no'] == game['game_no'] and r['player'] == 'engine'),
                     key=lambda r:r['ply'])
        expected = {r['ply']: r for r in own}
        if len(expected) != len(own):
            raise ValueError('Duplicate recorded candidate position')
        candidates = []
        for ply, text in enumerate(game['moves'], 1):
            move = chess.Move.from_uci(text)
            if move not in board.legal_moves:
                raise ValueError('Illegal source PGN move')
            if ply in expected:
                row = expected[ply]
                if row['fen'] != board.fen(en_passant='fen') or row['move'] != text:
                    raise ValueError('PGN and recorded position/move disagree')
                candidates.append(dict(id=f"g{game['game_no']:03d}-p{ply:03d}",
                    game_no=game['game_no'], group=game['group'], ply=ply,
                    start_fen=game['start_fen'], moves_before=game['moves'][:ply-1],
                    fen=board.fen(en_passant='fen'), played_move=text, recorded=row))
            board.push(move)
        if not candidates or len(candidates) != len(own):
            raise ValueError('Candidate move stream is incomplete')
        if game['group'] == 'loss':
            # Include every own move through the end for these early-loss games.
            if len(game['moves']) > 80:
                raise ValueError('Prescribed early losses exceed the 80-ply diagnostic scope')
        else:
            candidates = candidates[:8]
        positions.extend(candidates)
    return positions


def prepare(session_id, engine_source, stockfish):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', session_id):
        raise ValueError('Use a simple new session id')
    out = ROOT/'data'/'tactics'/session_id
    if (out/'protocol.json').exists():
        return load(out)
    if out.exists():
        raise ValueError('Incomplete preparation; use a new id')
    source = ROOT/'data'/'ab'/SOURCE_SESSION
    original, result = _read(source/'protocol.json'), _read(source/'results.json')
    if (_digest({k:v for k,v in original.items() if k!='protocol_sha256'}) != original['protocol_sha256']
            or result['status'] != 'completed' or result['games'] != 100 or result['aborted_games']):
        raise ValueError('Need the immutable completed 100-game packed-eval experiment')
    checkpoint = _read(source/'chunks'/'chunk_01.json')
    run = ROOT/'data'/'runs'/checkpoint['run_name']
    for name, digest in checkpoint['file_sha256'].items():
        if _sha(run/name) != digest:
            raise ValueError('Source run changed: ' + name)
    meta = _read(run/'meta.json')
    required = {'OwnBook':False, 'TTTwoContexts':True, 'EvalPackedBase':True,
                'QuiescenceSEE':False, 'NextIterationPct':150}
    if (meta.get('is_demo') or meta['engine_settings']['extra_options'] != required
            or meta['engine_settings']['move_time_ms'] != 100
            or meta['experiment']['protocol_sha256'] != original['protocol_sha256']):
        raise ValueError('Unexpected recorded source settings')
    games = []
    with gzip.open(run/'games.pgn.gz', 'rt', encoding='utf-8') as stream:
        while (game := chess.pgn.read_game(stream)) is not None:
            if game.errors:
                raise ValueError('Invalid source PGN')
            n = int(game.headers['Round'])
            white = n % 2 == 1
            score = {'1-0':int(white), '0-1':int(not white), '1/2-1/2':.5}[game.headers['Result']]
            games.append(dict(game_no=n, score=score, start_fen=game.board().fen(en_passant='fen'),
                              moves=[m.uci() for m in game.mainline_moves()]))
    if sorted(g['game_no'] for g in games) != list(range(1, 101)):
        raise ValueError('Expected all 100 unique source games')
    with gzip.open(run/'moves.jsonl.gz', 'rt', encoding='utf-8') as stream:
        rows = [json.loads(line) for line in stream]
    positions = freeze_positions(games, rows)
    engine_source, stockfish = engine_source.resolve(), stockfish.resolve()
    if _git(engine_source,'rev-parse','HEAD') != ENGINE_COMMIT:
        raise ValueError('Use the promoted main engine commit')
    out.mkdir(parents=True)
    _write(out/'inputs.json', dict(schema_version=1, positions=positions))
    plan = dict(schema_version=1, kind='tactical_position_diagnostics', id=session_id,
                session_dir=str(out), collector_commit=_git(ROOT,'rev-parse','HEAD'),
                collector_sha256=_sha(__file__), engine_source=str(engine_source),
                engine_commit=ENGINE_COMMIT, engine_tree=_git(engine_source,'rev-parse','HEAD:engine'),
                stockfish=str(stockfish), stockfish_sha256=_sha(stockfish),
                python_chess_version=chess.__version__, inputs_sha256=_sha(out/'inputs.json'),
                source_session=SOURCE_SESSION, source_protocol_sha256=original['protocol_sha256'],
                source_run=run.name, source_artifacts=checkpoint['file_sha256'],
                positions=len(positions), selected_games=[dict(game_no=g['game_no'], group=g['group']) for g in select_games(games)],
                sf_depths=[12,18], sf_nodes=100000, acemi_nodes=12000, acemi_depth=8,
                acemi_options=ACEMI_OPTIONS, sf_options={'Hash':64,'Threads':1,'UCI_LimitStrength':False},
                is_strength_test=False, new_matches=0,
                note='Cold TT at every probe; full played history retained. SF node caps may stop before requested depth.')
    plan['protocol_sha256'] = _digest(plan)
    _write(out/'protocol.json',plan)
    return load(out)


def load(out):
    out = Path(out).resolve()
    p = _read(out/'protocol.json')
    if (p['session_dir'] != str(out) or _digest({k:v for k,v in p.items() if k!='protocol_sha256'}) != p['protocol_sha256']
            or _sha(out/'inputs.json') != p['inputs_sha256'] or _sha(__file__) != p['collector_sha256']
            or chess.__version__ != p['python_chess_version'] or _sha(p['stockfish']) != p['stockfish_sha256']):
        raise ValueError('Diagnostic identity/input/runtime changed; use a new id')
    if (_git(ROOT,'diff',p['collector_commit'],'--',*CODE_PATHS)
            or _git(ROOT,'status','--porcelain','--untracked-files=all','--',*CODE_PATHS)):
        raise ValueError('Diagnostic code is changed or dirty')
    source = Path(p['engine_source'])
    if (_git(source,'rev-parse','HEAD') != p['engine_commit']
            or _git(source,'rev-parse','HEAD:engine') != p['engine_tree']
            or _git(source,'status','--porcelain','--untracked-files=all','--','engine')):
        raise ValueError('Pinned engine differs or is dirty')
    run = ROOT/'data'/'runs'/p['source_run']
    original = _read(ROOT/'data'/'ab'/p['source_session']/'protocol.json')
    if _digest({k:v for k,v in original.items() if k!='protocol_sha256'}) != p['source_protocol_sha256']:
        raise ValueError('Frozen source protocol changed')
    for f,h in p['source_artifacts'].items():
        if _sha(run/f) != h:
            raise ValueError('Frozen source artifact changed')
    return p


def board_for(position):
    board = chess.Board(position['start_fen'])
    for move in position['moves_before']:
        board.push_uci(move)
    if board.fen(en_passant='fen') != position['fen'] or chess.Move.from_uci(position['played_move']) not in board.legal_moves:
        raise ValueError('Frozen position/history mismatch')
    return board


def score_data(info, turn):
    score = info.get('score')
    view = score.pov(turn) if score is not None else None
    return dict(cp=view.score() if view is not None else None,
                mate=view.mate() if view is not None else None,
                lowerbound=bool(info.get('lowerbound')), upperbound=bool(info.get('upperbound')),
                depth=info.get('depth'), seldepth=info.get('seldepth'), nodes=info.get('nodes'),
                time_seconds=info.get('time'), pv=[m.uci() for m in info.get('pv',[])])


def comparison(best, played):
    """Only like-for-like cp scores are subtracted; mate scores stay separate."""
    exact = not any(doc.get(flag,False) for doc in (best,played) for flag in ('lowerbound','upperbound'))
    cp_loss = max(0,best['cp']-played['cp']) if exact and best['cp'] is not None and played['cp'] is not None else None
    new_mate = ((played['mate'] is not None and played['mate'] < 0
                 and not (best['mate'] is not None and best['mate'] < 0)) if exact else None)
    return dict(cp_loss_at_probe=cp_loss, losing_mate_only_in_forced_probe=new_mate,
                both_scores_without_bound_flags=exact,
                note='Bounded Stockfish estimate, not a proof of the first losing move.')


def probe(position, plan, sf, acemi):
    board = board_for(position)
    played = chess.Move.from_uci(position['played_move'])
    sf_cache = {}
    def analyse(depth, move=None):
        key = depth, move.uci() if move else None
        if key not in sf_cache:
            info = sf.analyse(board, chess.engine.Limit(depth=depth, nodes=plan['sf_nodes']),
                              game=object(), root_moves=[move] if move else None)
            doc = score_data(info,board.turn)
            if (doc['cp'] is None and doc['mate'] is None) or not doc['pv']:
                raise ValueError('Stockfish did not report a scored principal variation')
            if move is not None and doc['pv'][0] != move.uci():
                raise ValueError('Stockfish did not honor the forced root move')
            sf_cache[key] = doc
        return sf_cache[key]
    probes = []
    for depth in plan['sf_depths']:
        best, forced = analyse(depth), analyse(depth,played)
        probes.append(dict(requested_depth=depth, best=best, recorded_move=forced,
                           comparison=comparison(best,forced)))
    deeper = {}
    for name, engine in acemi.items():
        result = engine.play(board, chess.engine.Limit(nodes=plan['acemi_nodes'],depth=plan['acemi_depth']),
                             game=object(),info=chess.engine.INFO_ALL)
        if result.move is None or result.move not in board.legal_moves:
            raise ValueError('Acemi returned an invalid diagnostic move')
        judged = analyse(plan['sf_depths'][-1],result.move)
        deeper[name] = dict(move=result.move.uci(), acemi=score_data(result.info,board.turn),
                            stockfish_forced=judged,
                            comparison=comparison(probes[-1]['best'],judged))
    return dict(schema_version=1, protocol_sha256=plan['protocol_sha256'], id=position['id'],
                input_sha256=_digest(position), game_no=position['game_no'], group=position['group'],
                ply=position['ply'], fen=position['fen'], recorded_move=position['played_move'],
                recorded=position['recorded'], stockfish=probes, deeper=deeper)


def completed(plan, positions):
    out = Path(plan['session_dir'])
    path = out/'checkpoints.json'
    state = _read(path) if path.exists() else dict(schema_version=1,protocol_sha256=plan['protocol_sha256'],positions={})
    if state['protocol_sha256'] != plan['protocol_sha256'] or set(state['positions'])- {p['id'] for p in positions}:
        raise ValueError('Checkpoint belongs to another protocol/input')
    for position in positions:
        f = out/'positions'/(position['id']+'.json')
        if not f.exists():
            if position['id'] in state['positions']:
                raise ValueError('Completed position is missing')
            continue
        doc = _read(f)
        if (doc['protocol_sha256'] != plan['protocol_sha256'] or doc['id'] != position['id']
                or doc['input_sha256'] != _digest(position)
                or (position['id'] in state['positions'] and state['positions'][position['id']] != _sha(f))):
            raise ValueError('Completed position changed')
        state['positions'][position['id']] = _sha(f)
    _write(path,state)
    return state


def summarize(plan, state):
    out = Path(plan['session_dir'])
    status = 'completed' if len(state['positions']) == plan['positions'] else 'in_progress'
    result = dict(schema_version=1,protocol_sha256=plan['protocol_sha256'],status=status,
                  positions=len(state['positions']),requested_positions=plan['positions'],
                  is_strength_test=False,new_matches=0,selected_games=plan['selected_games'])
    _write(out/'results.json',result)
    (out/'SUMMARY.md').write_text(f"# Tactical position diagnostics: {plan['id']}\n\n"
        f"- Status: {status}; positions: {len(state['positions'])}/{plan['positions']}\n"
        f"- Selected recorded games: {plan['selected_games']}\n"
        f"- Acemi source: `{plan['engine_commit']}`\n"
        f"- Stockfish requested depths: {plan['sf_depths']}; node cap/probe: {plan['sf_nodes']}\n"
        f"- Acemi normal / NullMove+LMR off: {plan['acemi_nodes']} nodes, depth cap {plan['acemi_depth']}\n"
        "- New matches: 0; strength test: false; no Elo estimate\n"
        "- Recorded game history retained; fresh TT for every diagnostic probe\n"
        "- Read reached depth/nodes and both Stockfish passes; requested depth may not be reached.\n"
        "- Labels are bounded estimates; first-error and causal analysis is performed separately.\n",encoding='utf-8')
    return result


def run(out, retry_incomplete=False):
    plan = load(out)
    out = Path(plan['session_dir'])
    positions = _read(out/'inputs.json')['positions']
    if len(positions) != plan['positions'] or len({p['id'] for p in positions}) != len(positions):
        raise ValueError('Incomplete or duplicate input positions')
    state = completed(plan,positions)
    if len(state['positions']) == len(positions):
        print('All positions verified; no engines started.')
        return summarize(plan,state)
    lock = out/'.running'
    if lock.exists() and not retry_incomplete:
        raise ValueError('Prior run incomplete; stop the old Kaggle session before --retry-incomplete')
    if lock.exists():
        lock.unlink()
    with lock.open('x',encoding='utf-8') as stream:
        json.dump(dict(pid=os.getpid(),started_at=datetime.now(timezone.utc).isoformat()),stream)
    try:
        with ExitStack() as stack:
            sf = stack.enter_context(chess.engine.SimpleEngine.popen_uci(plan['stockfish'],timeout=30))
            sf.configure(plan['sf_options'])
            engines = {}
            for name, pruning in [('normal',True),('no_null_lmr',False)]:
                engine = stack.enter_context(chess.engine.SimpleEngine.popen_uci(
                    [sys.executable,'-u','-m','engine'],cwd=plan['engine_source'],timeout=30))
                engine.configure({**plan['acemi_options'],'NullMove':pruning,'LMR':pruning})
                engines[name] = engine
            runtime = dict(schema_version=1,protocol_sha256=plan['protocol_sha256'],
                           stockfish_id=sf.id,acemi_id={k:v.id for k,v in engines.items()},
                           python=platform.python_version(),cpu_count=os.cpu_count(),
                           stockfish_sha256=plan['stockfish_sha256'])
            if (out/'runtime.json').exists():
                old = _read(out/'runtime.json')
                if old != runtime:
                    raise ValueError('Engine identities or runtime changed across resume')
            else:
                _write(out/'runtime.json',runtime)
            for position in positions:
                if position['id'] in state['positions']:
                    continue
                doc = probe(position,plan,sf,engines)
                f = out/'positions'/(position['id']+'.json')
                _write(f,doc)
                state['positions'][position['id']] = _sha(f)
                _write(out/'checkpoints.json',state)
                summarize(plan,state)
                print(f"{len(state['positions'])}/{len(positions)}: {position['id']}",flush=True)
        lock.unlink()
        return summarize(plan,state)
    except Exception:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        (out/f'error-{stamp}.log').write_text(traceback.format_exc(),encoding='utf-8')
        summarize(plan,state)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('--id',required=True)
    prep.add_argument('--engine-source',type=Path,required=True)
    prep.add_argument('--stockfish',type=Path,required=True)
    execute = commands.add_parser('run')
    execute.add_argument('--session',type=Path,required=True)
    execute.add_argument('--retry-incomplete',action='store_true')
    args = parser.parse_args(argv)
    if not Path('/kaggle/working').is_dir():
        parser.error('All diagnostic preparation and searches are Kaggle-only')
    if args.command == 'prepare':
        plan = prepare(args.id,args.engine_source,args.stockfish)
        print(f"Prepared {plan['positions']} recorded positions; new matches: 0")
    else:
        run(args.session,args.retry_incomplete)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
