"""Protocol and resume fixtures only: no real engine, search or match."""
import contextlib
from dataclasses import asdict
import io
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

from tools import stockfish_strength as sf
from tools.uci_client import UciOption

PROBE_FUNCTION = sf._probe

class StockfishStrengthTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        self.source=self.root/'main'
        (self.source/'openings').mkdir(parents=True)
        (self.source/'openings/acemi-64.txt').write_bytes((sf.ROOT/'openings/acemi-64.txt').read_bytes())
        self.binary=self.root/'stockfish'
        self.binary.write_bytes(b'fixture, never executable')
        def source_info(path,expected):
            self.assertEqual(expected,sf.ENGINE_COMMIT)
            return dict(path=str(Path(path).resolve()),commit=expected,engine_tree='engine-fixture')
        def probe(binary,source):
            return (dict(path=str(binary),sha256=sf._sha(binary),name='Stockfish 16',limit_strength=True,
                         extra_options=sf.SF_OPTIONS,elo_option=asdict(UciOption('UCI_Elo','spin','1320',1320,3190))),
                    'Acemi 0.8.2',['fixture handshake, no go command'])
        for item in [patch.object(sf,'ROOT',self.root),patch.object(sf.ab,'source_info',side_effect=source_info),
                     patch.object(sf,'_git',side_effect=lambda path,*a:'engine-fixture' if a[-1]=='HEAD:engine' else 'collector'),
                     patch.object(sf,'_code_hashes',return_value={'fixture':'sha'}),patch.object(sf,'_probe',side_effect=probe)]:
            item.start();self.addCleanup(item.stop)

    def plan(self):
        return sf.prepare('strength-fixture',self.source,self.binary)

    def fake_run(self,p,g):
        run=self.root/'data/runs'/f"fixture_{p['id']}_c{g['number']:02d}"
        run.mkdir(parents=True)
        meta=dict(schema_version=1,is_demo=False,experiment=sf.experiment(p,g),git_commit=sf.ENGINE_COMMIT,git_dirty=False,
                  engine_settings=dict(move_time_ms=500,hash_mb=16,random_seed=1,opening_book=False,extra_options=sf.ENGINE_OPTIONS),
                  opponent=dict(name='Stockfish',version='16',uci_elo=g['uci_elo'],extra_options=sf.SF_OPTIONS,opening_book=None),
                  match_settings=dict(games_requested=100,concurrency=p['concurrency'],max_plies=400,timeout_grace_ms=1000,
                                      pairing='colour_swapped_pairs',forfeit_policy='loss_for_either_engine',
                                      command=shlex.join(['python','-m','tools.match',*sf.arguments(p,g)])))
        result=dict(schema_version=1,games=100,wins=40,draws=30,losses=30,aborted_games=0,
                    score_pct=55.,elo_diff=34.9,elo_confidence_interval=[-30.,100.],sprt={'enabled':False})
        for f in sf.ab.ARTIFACTS:(run/f).write_text('fixture',encoding='utf-8')
        sf._write(run/'meta.json',meta);sf._write(run/'results.json',result)
        index=self.root/'data/index.csv'
        if not index.exists():index.write_text('run_name\n',encoding='utf-8')
        with index.open('a',encoding='utf-8') as stream:stream.write(run.name+'\n')
        return run

    def test_exact_two_bulk_groups_and_latest_main_with_same_fifty_openings(self):
        p=self.plan()
        self.assertEqual([(g['uci_elo'],g['games']) for g in p['groups']],[(1320,100),(1500,100)])
        self.assertEqual(p['source']['commit'],sf.ENGINE_COMMIT)
        _,openings=sf.load_openings(Path(p['session_dir'])/p['opening_file'])
        self.assertEqual(len(openings),50)
        self.assertEqual(len({o.moves for o in openings}),50)
        for g in p['groups']:
            args=sf.match._parse_args(sf.arguments(p,g))
            self.assertEqual((args.games,args.movetime_ms,args.uci_elo),(100,500,g['uci_elo']))
            self.assertFalse(args.sprt)
            self.assertIsNone(args.opponent_cmd)
            self.assertIn('TTTwoContexts=true',args.engine_option)
            self.assertIn('EvalPackedBase=true',args.engine_option)
            self.assertEqual(args.openings,str(Path(p['session_dir'])/p['opening_file']))
        self.assertEqual(sf.load(Path(p['session_dir'])),p)

    def test_resume_completed_groups_and_keep_the_two_results_separate(self):
        p=self.plan()
        def play(args,*,experiment):
            g=next(g for g in p['groups'] if g['number']==experiment['chunk'])
            self.fake_run(p,g);return 0
        with patch.object(sf.match,'main',side_effect=play) as run,contextlib.redirect_stdout(io.StringIO()):
            a=sf.run_group(Path(p['session_dir']),1320)
            self.assertEqual(a['completed_games'],100)
            sf.run_group(Path(p['session_dir']),1320)
            b=sf.run_group(Path(p['session_dir']),1500)
            self.assertEqual(b['completed_games'],200)
            self.assertEqual(b['status'],'completed')
            self.assertEqual(len(b['groups']),2)
            self.assertEqual(run.call_count,2)
            sf.run_group(Path(p['session_dir']),1500)
            self.assertEqual(run.call_count,2)
        checkpoint=sf._read(sf._checkpoint(p,p['groups'][0]))
        path=self.root/'data/runs'/checkpoint['run_name']/'games.pgn.gz'
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'raw run changed'):
            sf.run_group(Path(p['session_dir']),1320)

    def test_finalized_raw_run_is_adopted_after_lost_checkpoint(self):
        p=self.plan();self.fake_run(p,p['groups'][0])
        with patch.object(sf.match,'main') as run,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sf.run_group(Path(p['session_dir']),1320)['completed_games'],100)
        run.assert_not_called()

    def test_interrupted_group_requires_explicit_retry(self):
        p=self.plan();out=Path(p['session_dir'])
        (out/'sf1320.started.json').write_text('{}',encoding='utf-8')
        with patch.object(sf.match,'main') as run,self.assertRaisesRegex(ValueError,'interrupted'):
            sf.run_group(out,1320)
        run.assert_not_called()
        def play(args,*,experiment):
            self.fake_run(p,p['groups'][0]);return 0
        with patch.object(sf.match,'main',side_effect=play) as run,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sf.run_group(out,1320,retry_incomplete=True)['completed_games'],100)
            self.assertEqual(run.call_count,1)

    def test_settings_or_incomplete_results_cannot_be_checkpointed(self):
        p=self.plan();g=p['groups'][0];run=self.fake_run(p,g)
        original=sf._read(run/'meta.json')
        import copy
        for section,key,value in [('opponent','uci_elo',1500),('engine_settings','move_time_ms',100),
                                  ('engine_settings','extra_options',{'OwnBook':False})]:
            meta=copy.deepcopy(original);meta[section][key]=value;sf._write(run/'meta.json',meta)
            with self.assertRaisesRegex(ValueError,'does not match'):
                sf._save(p,g,run)
        sf._write(run/'meta.json',original)
        result=sf._read(run/'results.json');result.update(games=99,aborted_games=1);sf._write(run/'results.json',result)
        with self.assertRaisesRegex(ValueError,'incomplete'):
            sf._save(p,g,run)
        self.assertFalse(sf._checkpoint(p,g).exists())

    def test_binary_or_opening_changes_reject_resume(self):
        p=self.plan();self.binary.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):
            sf.load(Path(p['session_dir']))
        self.binary.write_bytes(b'fixture, never executable')
        (Path(p['session_dir'])/p['opening_file']).write_text('changed',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'changed'):
            sf.load(Path(p['session_dir']))

    def test_probe_checks_both_ratings_without_searching(self):
        class Probe:
            minimum=1320
            calls=[]
            def __init__(self,command,*,label,**kwargs):
                self.name='Stockfish 16' if label=='Stockfish' else 'Acemi 0.8.2'
                self.options={'uci_elo':UciOption('UCI_Elo','spin','1320',self.minimum,3190)}
            def start(self):pass
            def close(self):pass
            def ready(self):pass
            def set_option(self,key,value):self.calls.append((key,value))
        with patch.object(sf,'UciEngine',Probe):
            PROBE_FUNCTION(self.binary,self.source)
            self.assertIn(('UCI_LimitStrength',True),Probe.calls)
            self.assertIn(('UCI_Elo',1320),Probe.calls)
            self.assertIn(('UCI_Elo',1500),Probe.calls)
            Probe.minimum=1400
            Probe.calls.clear()
            with self.assertRaisesRegex(ValueError,'does not support'):
                PROBE_FUNCTION(self.binary,self.source)
            self.assertEqual(Probe.calls,[])

    def test_pc_guard_blocks_preparation_and_matches(self):
        for args in [['prepare','--id','fixture','--source','fixture','--stockfish','fixture'],
                     ['run','--session','fixture','--elo','1320']]:
            with patch.object(Path,'is_dir',return_value=False),patch.object(sf,'prepare') as prep, \
                 patch.object(sf,'run_group') as run,contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                sf.main(args)
            prep.assert_not_called();run.assert_not_called()
