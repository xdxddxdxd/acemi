"""Pinned Kaggle strength test: one bulk 100-game run per Stockfish level."""
import argparse
import contextlib
import csv
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import platform
import random
import re
import shlex
import subprocess
import sys
import os

from tools import ab_compare as ab, match
from tools.match_openings import load_openings
from tools.uci_client import UciEngine

ROOT = Path(__file__).resolve().parents[1]
ENGINE_COMMIT = '38b0722b084552d8e94eb62e3558d447b641969c'
LEVELS = (1320, 1500)
ENGINE_OPTIONS = {'OwnBook':False, 'TTTwoContexts':True, 'EvalPackedBase':True,
                  'QuiescenceSEE':False, 'NextIterationPct':150, 'NullMove':True,
                  'LMR':True, 'Killers':True, 'PVS':False, 'CheckExtension':False,
                  'LateMovePruning':False, 'Contempt':0, 'EvalPassedPawns':False,
                  'EvalPawnStructure':False, 'EvalBishopPair':False,
                  'EvalKingSafety':False, 'EvalEndgameMate':False}
SF_OPTIONS = {'Ponder':False, 'MultiPV':1}
_read, _write, _sha, _digest, _git = ab._read, ab._write, ab._sha, ab._digest, ab._git


def _code_hashes():
    return {f:_sha(ROOT/'tools'/f) for f in (*ab.RUNNER_SOURCES,'stockfish_strength.py')}


def _probe(stockfish, source):
    """Handshake/configuration only; no go or search command is sent."""
    log=[]
    sf=UciEngine([str(stockfish)],label='Stockfish',log=log)
    try:
        sf.start()
        elo=sf.options.get('uci_elo')
        if elo is None or elo.kind!='spin' or elo.minimum is None or elo.maximum is None:
            raise ValueError('Stockfish must advertise a bounded UCI_Elo option')
        if any(not elo.minimum<=level<=elo.maximum for level in LEVELS):
            raise ValueError(f'Stockfish UCI_Elo range {elo.minimum}..{elo.maximum} does not support {LEVELS}')
        for name,value in {'Hash':16,'Threads':1,'UCI_LimitStrength':True,**SF_OPTIONS}.items():
            sf.set_option(name,value)
        for level in LEVELS:
            sf.set_option('UCI_Elo',level)
            sf.ready()
        opponent=dict(path=str(stockfish),sha256=_sha(stockfish),name=sf.name,elo_option=asdict(elo),
                      limit_strength=True,extra_options=SF_OPTIONS)
    finally:
        sf.close()
    engine=UciEngine([sys.executable,'-u','-m','engine'],label='Acemi',cwd=str(source),log=log)
    try:
        engine.start()
        for name,value in {'Hash':16,'Threads':1,**ENGINE_OPTIONS}.items():
            engine.set_option(name,value)
        engine.ready()
        name=engine.name
    finally:
        engine.close()
    return opponent,name,log


def prepare(session_id, source, stockfish):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,69}',session_id):
        raise ValueError('Use a simple new session id, at most 70 characters')
    out=ROOT/'data'/'strength'/session_id
    source,stockfish=Path(source).resolve(),Path(stockfish).resolve()
    if (out/'protocol.json').exists():
        p=load(out)
        if p['source']['path']!=str(source) or p['stockfish']['path']!=str(stockfish):
            raise ValueError('Saved paths differ; use a new SESSION_ID')
        return p
    if out.exists():
        raise ValueError('Incomplete preparation; use a new SESSION_ID')
    info=ab.source_info(source,ENGINE_COMMIT)
    if _git(ROOT,'rev-parse','HEAD:engine')!=info['engine_tree']:
        raise ValueError('Collector board must match the pinned main engine')
    opening_file=source/'openings'/'acemi-64.txt'
    _,openings=load_openings(opening_file)
    if len({(o.start_fen,o.moves) for o in openings})!=len(openings) or len(openings)<50:
        raise ValueError('Need at least 50 distinct balanced opening lines')
    selected=random.Random(1).sample(openings,50)
    opponent,name,log=_probe(stockfish,source)
    out.mkdir(parents=True)
    lines='\n'.join(o.start_fen or ' '.join(o.moves) for o in selected)+'\n'
    (out/'openings_50.txt').write_text(lines,encoding='utf-8')
    (out/'setup.log').write_text('\n'.join(log)+'\n',encoding='utf-8')
    p=dict(schema_version=1,kind='stockfish_strength',id=session_id,session_dir=str(out),repo_root=str(ROOT),
           collector_commit=_git(ROOT,'rev-parse','HEAD'),runner_sources=_code_hashes(),source=info,
           engine_name=name,engine_options=ENGINE_OPTIONS,stockfish=opponent,
           groups=[dict(number=n,uci_elo=level,games=100,seed=1) for n,level in enumerate(LEVELS,1)],
           games_per_level=100,total_games=200,movetime_ms=500,hash_mb=16,threads_per_engine=1,
           concurrency=min(2,os.cpu_count() or 1),max_plies=400,timeout_grace_ms=1000,
           opening_file='openings_50.txt',opening_sha256=_sha(out/'openings_50.txt'),
           opening_source_sha256=_sha(opening_file),opening_selection_seed=1,
           opening_book=False,sprt_enabled=False,forfeit_policy='loss_for_either_engine',
           draw_policy='python-chess board.outcome(claim_draw=True)',
           python_version=platform.python_version(),
           note='1300-ish uses UCI_Elo=1320. Each opponent gets one bulk 100-game call, 50 colour-swapped pairs. '
                'UCI_Elo is a limiter target, not a measured human/FIDE/online rating.')
    p['protocol_sha256']=_digest(p)
    _write(out/'protocol.json',p)
    summarize(p)
    return load(out)


def load(out):
    out=Path(out).resolve()
    p=_read(out/'protocol.json')
    if (str(out)!=p['session_dir'] or str(ROOT)!=p['repo_root']
            or _digest({k:v for k,v in p.items() if k!='protocol_sha256'})!=p['protocol_sha256']
            or p['runner_sources']!=_code_hashes() or p['engine_options']!=ENGINE_OPTIONS
            or p['source']!=ab.source_info(p['source']['path'],ENGINE_COMMIT)
            or _git(ROOT,'rev-parse','HEAD:engine')!=p['source']['engine_tree']
            or _sha(out/p['opening_file'])!=p['opening_sha256']
            or _sha(Path(p['source']['path'])/'openings/acemi-64.txt')!=p['opening_source_sha256']
            or _sha(p['stockfish']['path'])!=p['stockfish']['sha256']
            or p['stockfish']['extra_options']!=SF_OPTIONS or not p['stockfish']['limit_strength']
            or platform.python_version()!=p['python_version']):
        raise ValueError('Pinned source/runtime/protocol changed; use a new SESSION_ID')
    if (p['groups']!=[dict(number=n,uci_elo=level,games=100,seed=1) for n,level in enumerate(LEVELS,1)]
            or p['movetime_ms']!=500 or p['games_per_level']!=100 or p['total_games']!=200
            or p['hash_mb']!=16 or p['max_plies']!=400 or p['threads_per_engine']!=1
            or p['concurrency'] not in (1,2)
            or p['timeout_grace_ms']!=1000 or p['sprt_enabled'] or p['opening_book']
            or p['forfeit_policy']!='loss_for_either_engine'):
        raise ValueError('Strength settings differ from the fixed protocol')
    return p


def experiment(plan,group):
    return dict(schema_version=1,id=plan['id'],chunk=group['number'],kind='stockfish_strength',
                protocol_sha256=plan['protocol_sha256'],acemi=plan['source'],
                opponent=dict(name=plan['stockfish']['name'],sha256=plan['stockfish']['sha256'],
                              uci_elo=group['uci_elo'],limit_strength=True),
                global_game_start=(group['number']-1)*100+1)


def arguments(plan,group):
    command=[sys.executable,'-u','-m','engine']
    executable=subprocess.list2cmdline(command) if os.name=='nt' else shlex.join(command)
    args=['--games','100','--movetime-ms','500','--uci-elo',str(group['uci_elo']),
          '--stockfish-path',plan['stockfish']['path'],'--engine-cmd',executable,
          '--engine-cwd',plan['source']['path'],'--git-commit',plan['source']['commit'],
          '--hash-mb','16','--concurrency',str(plan['concurrency']),'--max-plies','400',
          '--grace-ms','1000','--seed',str(group['seed']),
          '--openings',str(Path(plan['session_dir'])/plan['opening_file']),'--root',plan['repo_root']]
    for values,flag in [(plan['engine_options'],'--engine-option'),(SF_OPTIONS,'--opponent-option')]:
        for key,value in values.items():
            args.extend([flag,f'{key}={str(value).lower()}'])
    return args


def _runs(plan,group):
    found=[]
    for path in (ROOT/'data'/'runs').glob(f"*_{plan['id']}_c{group['number']:02d}/meta.json"):
        tag=_read(path).get('experiment',{})
        if tag.get('id')==plan['id'] and tag.get('chunk')==group['number']:
            if tag!=experiment(plan,group):
                raise ValueError('Existing run belongs to another protocol')
            found.append(path.parent)
    if len(found)>1:
        raise ValueError('Duplicate runs for one opponent; inspect raw records')
    return found


def _validate_run(plan,group,run):
    meta,result=_read(run/'meta.json'),_read(run/'results.json')
    settings,opponent,match_settings=meta['engine_settings'],meta['opponent'],meta['match_settings']
    if (meta.get('is_demo') or meta['experiment']!=experiment(plan,group)
            or meta['git_commit']!=plan['source']['commit'] or meta['git_dirty'] is not False
            or settings['move_time_ms']!=500 or settings['hash_mb']!=16 or settings['random_seed']!=group['seed']
            or settings['opening_book'] is not False or settings['extra_options']!=ENGINE_OPTIONS
            or opponent['uci_elo']!=group['uci_elo'] or opponent['extra_options']!=SF_OPTIONS
            or ' '.join([opponent['name'],opponent['version']]).strip()!=plan['stockfish']['name']
            or opponent.get('opening_book') is True
            or match_settings['games_requested']!=100 or match_settings['concurrency']!=plan['concurrency']
            or match_settings['max_plies']!=400 or match_settings['timeout_grace_ms']!=1000
            or match_settings['pairing']!='colour_swapped_pairs'
            or match_settings['forfeit_policy']!='loss_for_either_engine'
            or match_settings['command']!=shlex.join(['python','-m','tools.match',*arguments(plan,group)])
            or result['games']!=100 or result.get('aborted_games',0) or result['sprt']['enabled']
            or result['wins']+result['draws']+result['losses']!=100
            or result.get('unpaired_games_excluded',0) or result.get('post_decision_games_excluded',0)):
        raise ValueError('Run is incomplete or does not match the pinned strength protocol')
    with (ROOT/'data'/'index.csv').open(encoding='utf-8',newline='') as stream:
        if not any(row['run_name']==run.name for row in csv.DictReader(stream)):
            raise ValueError('Raw run is missing its finalized index entry')
    return {f:_sha(run/f) for f in ab.ARTIFACTS},result


def _checkpoint(plan,group):
    return Path(plan['session_dir'])/f"sf{group['uci_elo']}.json"


def _save(plan,group,run):
    hashes,_=_validate_run(plan,group,run)
    _write(_checkpoint(plan,group),dict(schema_version=1,protocol_sha256=plan['protocol_sha256'],
                                      uci_elo=group['uci_elo'],run_name=run.name,file_sha256=hashes))


def _verified_result(plan,group):
    state=_read(_checkpoint(plan,group))
    if (state['protocol_sha256']!=plan['protocol_sha256'] or state['uci_elo']!=group['uci_elo']
            or not re.fullmatch(r'[A-Za-z0-9_.-]+',state['run_name'])):
        raise ValueError('Checkpoint identity changed')
    hashes,result=_validate_run(plan,group,ROOT/'data'/'runs'/state['run_name'])
    if hashes!=state['file_sha256']:
        raise ValueError('Completed raw run changed; never replay or overwrite it')
    return result,state['run_name']


def summarize(plan):
    out=Path(plan['session_dir']);groups=[]
    lines=[f"# Stockfish strength test: {plan['id']}",'',f"- Acemi: `{plan['source']['commit']}`",
           f"- Opponent: {plan['stockfish']['name']}; UCI_LimitStrength=true",
           '- 500 ms/move for BOTH sides; one bulk 100-game run per level',
           '- Same 50 colour-swapped opening pairs; book off; Hash 16; Threads 1; SPRT off','']
    for group in plan['groups']:
        if _checkpoint(plan,group).exists():
            result,run_name=_verified_result(plan,group)
            groups.append(dict(uci_elo=group['uci_elo'],status='completed',run_name=run_name,results=result))
            lines.append(f"- SF {group['uci_elo']}: {result['wins']}/{result['draws']}/{result['losses']}; "
                         f"score {result['score_pct']}%; Elo difference {result.get('elo_diff')}; "
                         f"95% interval {result.get('elo_confidence_interval')}")
        else:
            groups.append(dict(uci_elo=group['uci_elo'],status='not_completed'))
            lines.append(f"- SF {group['uci_elo']}: not completed")
    complete=all(g['status']=='completed' for g in groups)
    summary=dict(schema_version=1,id=plan['id'],protocol_sha256=plan['protocol_sha256'],
                 status='completed' if complete else 'in_progress',groups=groups,
                 completed_games=sum(g.get('results',{}).get('games',0) for g in groups),requested_games=200)
    _write(out/'results.json',summary)
    lines+=['','Forfeits are losses for either side; technical errors remain in raw results.',
            'UCI_Elo is a limiter target. These separate samples do not establish a FIDE/online rating.',
            'Stockfish weak-move randomness is not guaranteed reproducible by the Acemi Seed option.']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return summary


def run_group(out,level,retry_incomplete=False):
    plan=load(out)
    group=next((g for g in plan['groups'] if g['uci_elo']==level),None)
    if group is None:
        raise ValueError('Choose one of the two frozen Stockfish levels')
    if _checkpoint(plan,group).exists():
        _verified_result(plan,group)
        print(f'SF {level} already completed; no games repeated.')
        return summarize(plan)
    found=_runs(plan,group)
    if found:
        _save(plan,group,found[0])
        print(f'Adopted the finalized SF {level} run; no games repeated.')
        return summarize(plan)
    out=Path(plan['session_dir'])
    marker=out/f'sf{level}.started.json'
    if marker.exists() and not retry_incomplete:
        raise ValueError('Prior 100-game group was interrupted; stop the old Kaggle session before --retry-incomplete')
    if not marker.exists():
        with marker.open('x',encoding='utf-8') as stream:
            import json
            json.dump(dict(schema_version=1,uci_elo=level,pid=os.getpid(),protocol_sha256=plan['protocol_sha256']),stream)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    log=out/f'sf{level}-{stamp}.log'
    try:
        with log.open('x',encoding='utf-8') as stream,contextlib.redirect_stdout(ab._Tee(sys.stdout,stream)), \
             contextlib.redirect_stderr(ab._Tee(sys.stderr,stream)):
            code=match.main(arguments(plan,group),experiment=experiment(plan,group))
        found=_runs(plan,group)
        if code or len(found)!=1:
            raise RuntimeError(f'SF {level} group failed; inspect {log}')
        _save(plan,group,found[0])
    finally:
        summarize(plan)
    return summarize(plan)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='command',required=True)
    prep=subs.add_parser('prepare');prep.add_argument('--id',required=True)
    prep.add_argument('--source',type=Path,required=True);prep.add_argument('--stockfish',type=Path,required=True)
    run=subs.add_parser('run');run.add_argument('--session',type=Path,required=True)
    run.add_argument('--elo',type=int,choices=LEVELS,required=True);run.add_argument('--retry-incomplete',action='store_true')
    args=parser.parse_args(argv)
    if not Path('/kaggle/working').is_dir():
        parser.error('Preparation and all engine/match execution are Kaggle-only')
    if args.command=='prepare':
        p=prepare(args.id,args.source,args.stockfish);print((Path(p['session_dir'])/'SUMMARY.md').read_text(encoding='utf-8'))
    else:
        run_group(args.session,args.elo,args.retry_incomplete)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
