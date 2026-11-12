"""Pure eligibility/protocol tests; no searches or benchmarks are executed."""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import tt_pair_experiment as exp


def bench(seconds, nodes=100):
    return {'total_seconds': seconds, 'total_nodes': nodes,
            'positions': [{'name': 'fixture', 'fen': 'fixture', 'score': 0,
                           'depth': 3, 'nodes': nodes, 'best_move': 'fixture'}]}


class TTEligibilityTests(unittest.TestCase):
    def test_replays_share_the_same_fixed_twenty_inputs_and_resume(self):
        td = exp.td
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'data'/'tt'/'tt-usage-node-replay-v1'
            td._write(source/'inputs.json', {'schema_version':1, 'games':[
                {'game_no':n, 'control_rows':[{'ply':1, 'nodes':10}]} for n in range(1,101)]})
            original = {'schema_version':1, 'games':100, 'quiescence_see':False, 'next_iteration_pct':150,
                        'inputs_sha256':td._sha(source/'inputs.json')}
            original['protocol_sha256'] = td._digest(original)
            td._write(source/'protocol.json', original)
            comparison = {'id':'pair-fixture', 'session_dir':str(root/'data'/'ab'/'pair-fixture'),
                          'protocol_sha256':'comparison-fixture'}
            def git(*args):
                return 'new-tree' if args==('rev-parse','HEAD:engine') else 'a'*40 if args==('rev-parse','HEAD') else ''
            with patch.object(td,'ROOT',root), patch.object(td,'_git',side_effect=git), \
                 patch.object(td,'_source_hashes',return_value={'fixture':'sha'}):
                single=exp._prepare_replay(comparison,False)
                pair=exp._prepare_replay(comparison,True)
                self.assertEqual(single['selected_game_numbers'],list(range(1,101,5)))
                self.assertEqual(single['inputs_sha256'],pair['inputs_sha256'])
                self.assertEqual((single['games'],pair['games']), (20,20))
                self.assertEqual(exp._prepare_replay(comparison,True),pair)
                self.assertEqual(td._sha(source/'inputs.json'),original['inputs_sha256'])

    def test_cost_and_actual_secondary_cutoffs_are_both_required(self):
        single = [bench(1.0), bench(1.02), bench(0.99)]
        pair = [bench(0.95, 90), bench(0.94, 90), bench(0.96, 90)]
        self.assertTrue(exp.cost_decision(single, pair, 10)['eligible_to_run_match'])
        self.assertFalse(exp.cost_decision(single, pair, 0)['eligible_to_run_match'])
        self.assertFalse(exp.cost_decision(single, [bench(1.2)]*3, 10)['eligible_to_run_match'])
        self.assertFalse(exp.cost_decision(single, [bench(0.9, 101)]*3, 10)['eligible_to_run_match'])

    def test_non_deterministic_search_does_not_pass(self):
        with self.assertRaisesRegex(ValueError, 'deterministic'):
            exp.cost_decision([bench(1), bench(1, 101), bench(1)], [bench(1)]*3, 1)

    def test_pc_is_rejected_before_any_work(self):
        with patch.object(Path, 'is_dir', return_value=False), patch.object(exp, 'run') as run, \
             contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            exp.main(['--session', 'fixture', '--reference', 'fixture'])
        run.assert_not_called()
