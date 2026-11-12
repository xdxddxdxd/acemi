"""Protocol and checkpoint fixtures only; no real search or process pools."""

import contextlib
import gzip
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import tt_diagnostics as td
from tools.tt_stats import empty_stats


class TTProtocolTests(unittest.TestCase):
    def test_cli_rejects_local_execution_before_any_work(self):
        with patch.object(td.Path, 'is_dir', return_value=False), patch.object(td, 'prepare') as prepare, \
             patch.object(td, 'run') as run, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            td.main(['prepare', '--id', 'fixture', '--source-session', 'fixture-source'])
        prepare.assert_not_called()
        run.assert_not_called()

    def test_saved_diagnostic_is_adopted_and_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory).resolve()
            plan = {'session_dir': str(out), 'protocol_sha256': 'fixture'}
            games = [{'game_no': 1, 'control_rows': [{}]}]
            path = out / 'games' / 'game_001.json'
            doc = {'protocol_sha256': 'fixture', 'game_no': 1, 'positions': 1,
                   'all_searches_equivalent': True, 'rows': [{'equivalent': True}], 'tt': empty_stats()}
            td._write(path, doc)
            state = td._completed(plan, games)
            self.assertIn('1', state['games'])
            self.assertEqual(td._completed(plan, games), state)
            doc['positions'] = 2
            td._write(path, doc)
            with self.assertRaisesRegex(ValueError, 'artifact changed'):
                td._completed(plan, games)

    def test_prepare_freezes_all_100_games_without_searching(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            run = root / 'data' / 'runs' / 'fixture-run'
            source = root / 'data' / 'ab' / 'fixture-source'
            run.mkdir(parents=True)
            source.mkdir(parents=True)
            protocol = {'games': 100, 'chunks': [{'number': 1}]}
            protocol['protocol_sha256'] = td._digest(protocol)
            td._write(source / 'protocol.json', protocol)
            td._write(run / 'meta.json', {'is_demo': False,
                'opponent': {'extra_options': {'OwnBook': False, 'NextIterationPct': 150, 'QuiescenceSEE': False}},
                'experiment': {'old': {'engine_tree': 'tree'}},
                'engine_settings': {'hash_mb': 16, 'random_seed': 1}})
            td._write(run / 'results.json', {'games': 100, 'aborted_games': 0})
            (run / 'SUMMARY.md').write_text('fixture')
            (run / 'engine.log.gz').write_bytes(b'fixture')
            with gzip.open(run / 'games.pgn.gz', 'wt') as stream:
                for number in range(1, 101):
                    stream.write(f'[Round "{number}"]\n[Result "*"]\n\n1. e4 e5 *\n\n')
            with gzip.open(run / 'moves.jsonl.gz', 'wt') as stream:
                import json
                for number in range(1, 101):
                    stream.write(json.dumps({'game_no': number, 'player': 'opponent', 'ply': 2,
                                             'nodes': 10, 'fen': 'fixture-fen', 'move': 'e7e5'}) + '\n')
            names = ('meta.json', 'results.json', 'SUMMARY.md', 'engine.log.gz', 'games.pgn.gz', 'moves.jsonl.gz')
            td._write(source / 'chunks' / 'chunk_01.json', {'run_name': 'fixture-run',
                       'file_sha256': {name: td._sha(run / name) for name in names}})
            def git(*args):
                return 'tree' if args == ('rev-parse', 'HEAD:engine') else 'a' * 40 if args == ('rev-parse', 'HEAD') else ''
            with patch.object(td, 'ROOT', root), patch.object(td, '_git', side_effect=git), \
                 patch.object(td, '_source_hashes', return_value={'fixture': 'sha'}), \
                 patch.object(td, '_replay_game') as replay:
                plan = td.prepare('tt-fixture', 'fixture-source')
                self.assertEqual((plan['games'], plan['positions']), (100, 100))
                self.assertFalse(plan['is_strength_test'])
                self.assertEqual(td.load_plan(Path(plan['session_dir'])), plan)
                replay.assert_not_called()
                (Path(plan['session_dir']) / 'inputs.json').write_text('changed')
                with self.assertRaisesRegex(ValueError, 'identity changed'):
                    td.load_plan(Path(plan['session_dir']))
