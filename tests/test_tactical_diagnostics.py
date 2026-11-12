"""Parsing, score perspective and resume fixtures only; no engine processes."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import chess
import chess.engine
from tools import tactical_diagnostics as td


class TacticalDiagnosticTests(unittest.TestCase):
    def position(self):
        board = chess.Board()
        moves = ['g1f3','g8f6','f3g1','f6g8']
        for move in moves:
            board.push_uci(move)
        return dict(id='g019-p005',game_no=19,group='loss',ply=5,
                    start_fen=chess.STARTING_FEN,moves_before=moves,fen=board.fen(),
                    played_move='e2e4',recorded={'move':'e2e4'})

    def test_history_is_preserved_instead_of_loading_only_fen(self):
        position = self.position()
        board = td.board_for(position)
        self.assertEqual(len(board.move_stack),4)
        self.assertTrue(board.is_repetition(2))
        position['fen'] = chess.STARTING_FEN
        with self.assertRaisesRegex(ValueError,'history mismatch'):
            td.board_for(position)

    def test_score_perspective_and_mates_are_not_fake_cp_values(self):
        info = {'score':chess.engine.PovScore(chess.engine.Cp(80),chess.WHITE)}
        self.assertEqual(td.score_data(info,chess.BLACK)['cp'],-80)
        mate = td.score_data({'score':chess.engine.PovScore(chess.engine.Mate(3),chess.WHITE)},chess.BLACK)
        self.assertEqual(mate['mate'],-3)
        self.assertIsNone(mate['cp'])
        self.assertEqual(td.comparison({'cp':30,'mate':None},{'cp':-120,'mate':None})['cp_loss_at_probe'],150)
        result = td.comparison({'cp':30,'mate':None},mate)
        self.assertIsNone(result['cp_loss_at_probe'])
        self.assertTrue(result['losing_mate_only_in_forced_probe'])
        self.assertFalse(td.comparison({'cp':None,'mate':-5},mate)['losing_mate_only_in_forced_probe'])
        bound = td.comparison({'cp':30,'mate':None,'lowerbound':True},{'cp':-120,'mate':None})
        self.assertIsNone(bound['cp_loss_at_probe'])
        self.assertIsNone(bound['losing_mate_only_in_forced_probe'])

    def test_game_selection_is_deterministic_and_stratified(self):
        games = [dict(game_no=n,score=score,moves=['fixture']*(n+2))
                 for n,score in enumerate([0,1,.5,0,1,.5,0,0,1,.5],1)]
        selected = td.select_games(list(reversed(games)))
        self.assertEqual([v['game_no'] for v in selected],[1,4,7,8,2,5,3,6])
        with self.assertRaises(ValueError):
            td.select_games(games[:3])

    def test_source_rows_and_move_prefix_are_cross_checked(self):
        game = dict(game_no=19,score=0,group='loss',start_fen=chess.STARTING_FEN,
                    moves=['e2e4','e7e5','g1f3','b8c6'])
        board = chess.Board()
        board.push_uci('e2e4'); board.push_uci('e7e5')
        row = dict(game_no=19,player='engine',ply=3,fen=board.fen(en_passant='fen'),move='g1f3')
        with patch.object(td,'select_games',return_value=[game]):
            positions=td.freeze_positions([game],[row])
            self.assertEqual(positions[0]['moves_before'],['e2e4','e7e5'])
            self.assertIn(' e6 ',positions[0]['fen'])  # preserve raw, uncapturable EP targets too
            self.assertEqual(td.board_for(positions[0]).fen(en_passant='fen'),row['fen'])
            row['move']='f1c4'
            with self.assertRaisesRegex(ValueError,'disagree'):
                td.freeze_positions([game],[row])

    def test_probe_uses_forced_root_moves_and_same_perspective(self):
        position = self.position()
        calls=[]
        class Stockfish:
            def analyse(self,board,limit,*,game,root_moves):
                move=root_moves[0] if root_moves else chess.Move.from_uci('d2d4')
                calls.append((len(board.move_stack),limit.depth,limit.nodes,root_moves))
                return dict(score=chess.engine.PovScore(chess.engine.Cp(20 if root_moves else 100),board.turn),
                            pv=[move],depth=7,nodes=40)
        class Engine:
            def play(self,board,limit,*,game,info):
                self.limit=limit
                return chess.engine.PlayResult(chess.Move.from_uci('d2d4'),None,
                    info={'score':chess.engine.PovScore(chess.engine.Cp(15),board.turn),'depth':3,'nodes':100})
        plan=dict(protocol_sha256='fixture',sf_depths=[12,18],sf_nodes=1000,acemi_nodes=200,acemi_depth=8)
        engine=Engine()
        result=td.probe(position,plan,Stockfish(),{'normal':engine,'no_null_lmr':engine})
        self.assertEqual(len(calls),5)  # shared SF judgement for identical diagnostic moves
        self.assertTrue(all(c[0]==4 and c[2]==1000 for c in calls))
        self.assertEqual(result['stockfish'][0]['best']['depth'],7)  # never claim requested 12 was reached
        self.assertEqual(result['stockfish'][0]['comparison']['cp_loss_at_probe'],80)
        self.assertEqual(engine.limit.nodes,200)
        self.assertEqual(set(result['deeper']),{'normal','no_null_lmr'})

    def test_checkpoints_adopt_orphans_then_reject_tampering_and_missing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            position=self.position()
            plan=dict(session_dir=str(root),protocol_sha256='fixture')
            path=root/'positions'/(position['id']+'.json')
            doc=dict(schema_version=1,protocol_sha256='fixture',id=position['id'],input_sha256=td._digest(position))
            td._write(path,doc)
            first=td.completed(plan,[position])
            self.assertEqual(td.completed(plan,[position]),first)
            path.write_text('{}',encoding='utf-8')
            with self.assertRaises((KeyError,ValueError)):
                td.completed(plan,[position])
            path.unlink()
            with self.assertRaisesRegex(ValueError,'missing'):
                td.completed(plan,[position])

    def test_completed_run_starts_no_engines(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            position=self.position()
            plan=dict(session_dir=str(root),protocol_sha256='fixture',positions=1,selected_games=[],id='fixture',
                      engine_commit='fixture',sf_depths=[12,18],sf_nodes=1000,acemi_nodes=200,acemi_depth=8)
            td._write(root/'inputs.json',{'positions':[position]})
            td._write(root/'positions'/(position['id']+'.json'),dict(protocol_sha256='fixture',
                       id=position['id'],input_sha256=td._digest(position)))
            with patch.object(td,'load',return_value=plan), patch.object(chess.engine.SimpleEngine,'popen_uci') as start, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(td.run(root)['status'],'completed')
            start.assert_not_called()

    def test_failed_position_resumes_without_repeating_completed_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            first=self.position()
            second={**first,'id':'g019-p007','ply':7}
            plan=dict(session_dir=str(root),protocol_sha256='fixture',positions=2,selected_games=[],id='fixture',
                      engine_commit='fixture',sf_depths=[12,18],sf_nodes=1000,acemi_nodes=200,acemi_depth=8,
                      stockfish='fixture',stockfish_sha256='fixture',engine_source='fixture',sf_options={},acemi_options={})
            td._write(root/'inputs.json',{'positions':[first,second]})
            class Engine:
                id={'name':'fixture'}
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def configure(self,options):pass
            seen=[]
            failed=[False]
            def probe(position,*args):
                seen.append(position['id'])
                if position['id']==second['id'] and not failed[0]:
                    failed[0]=True
                    raise RuntimeError('fixture interruption')
                return dict(protocol_sha256='fixture',id=position['id'],input_sha256=td._digest(position))
            with patch.object(td,'load',return_value=plan),patch.object(td,'probe',side_effect=probe), \
                 patch.object(chess.engine.SimpleEngine,'popen_uci',side_effect=lambda *a,**k:Engine()) as start, \
                 contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError,'interruption'):td.run(root)
                digest=td._sha(root/'positions'/(first['id']+'.json'))
                with self.assertRaisesRegex(ValueError,'Prior run incomplete'):td.run(root)
                self.assertEqual(td.run(root,retry_incomplete=True)['status'],'completed')
                self.assertEqual(td._sha(root/'positions'/(first['id']+'.json')),digest)
                self.assertEqual(start.call_count,6)
            self.assertEqual(seen,[first['id'],second['id'],second['id']])
            self.assertFalse((root/'.running').exists())
            self.assertEqual(len(list(root.glob('error-*.log'))),1)

    def test_pc_guard_blocks_prepare_and_run(self):
        for args in [['prepare','--id','fixture','--engine-source','fixture','--stockfish','fixture'],
                     ['run','--session','fixture']]:
            with patch.object(Path,'is_dir',return_value=False),patch.object(td,'prepare') as prepare, \
                 patch.object(td,'run') as run,contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                td.main(args)
            prepare.assert_not_called();run.assert_not_called()
