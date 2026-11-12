"""Validation gates with fixture artifacts only; never launch an engine."""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import qsee_validation as qv


class ValidationGateTests(unittest.TestCase):
    def test_time_policy_gate_records_alternating_timed_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, reference, session = root / 'new', root / 'reference', root / 'session'
            session.mkdir()
            plan = {'session_dir': str(session), 'protocol_sha256': 'time-fixture', 'movetime_ms': 100,
                    'sources': {side: {'path': str(source), 'commit': 'a' * 40} for side in ('new', 'old')},
                    'feature_options': {'new': {'NextIterationPct': 100, 'QuiescenceSEE': False},
                                        'old': {'NextIterationPct': 150, 'QuiescenceSEE': False}}}
            def git(path, *args):
                if args[0] == 'status':
                    return ''
                return 'a' * 40 if path == source else qv.REFERENCE_COMMIT
            def command(args, cwd, log):
                log.write_text('fixture: no search ran\n')
                if '--out' in args:
                    qv._write(Path(args[args.index('--out')+1]), {'positions': [
                        {'name': 'fixture', 'fen': 'fixture', 'score': 7, 'depth': 3,
                         'nodes': 1, 'best_move': 'fixture'}]})
            with patch.object(qv, '_git', side_effect=git), patch.object(qv, '_command', side_effect=command) as run, \
                 contextlib.redirect_stdout(io.StringIO()):
                qv.validate(plan, reference, 'time-policy')
                self.assertEqual(run.call_count, 8)
                timed = [call.args[0] for call in run.call_args_list if '--movetime-ms' in call.args[0]]
                self.assertEqual([args[args.index('--next-iteration-pct')+1] for args in timed], ['100', '150', '150', '100'])
                self.assertTrue(all(args[args.index('--movetime-ms')+1] == '100' and '--see' not in args for args in timed))
                status = json.loads((session / 'validation' / 'status.json').read_text())
                self.assertTrue(status['passed'] and status['fixed_depth_candidate_matches_reference'])
                qv.validate(plan, reference, 'time-policy')
                self.assertEqual(run.call_count, 8)

            failed_session = root / 'failed-session'
            failed_session.mkdir()
            failed_plan = {**plan, 'session_dir': str(failed_session)}
            def mismatch(args, cwd, log):
                command(args, cwd, log)
                if '--out' in args:
                    out = Path(args[args.index('--out')+1])
                    if out.name == 'candidate.json':
                        data = json.loads(out.read_text())
                        data['positions'][0]['nodes'] = 2
                        qv._write(out, data)
            with patch.object(qv, '_git', side_effect=git), patch.object(qv, '_command', side_effect=mismatch) as run, \
                 contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, 'without a time limit'):
                    qv.validate(failed_plan, reference, 'time-policy')
                self.assertEqual(run.call_count, 4)
                self.assertFalse(json.loads((failed_session / 'validation' / 'status.json').read_text())['passed'])

    def test_time_policy_gate_rejects_accidentally_enabled_see(self):
        plan = {'feature_options': {'new': {'NextIterationPct': 100, 'QuiescenceSEE': True},
                                    'old': {'NextIterationPct': 150, 'QuiescenceSEE': False}}}
        with patch.object(qv, '_command') as run, self.assertRaisesRegex(ValueError, 'SEE disabled'):
            qv.validate(plan, Path('.'), 'time-policy')
        run.assert_not_called()

    def test_local_cli_rejects_worker_before_imports_or_subprocesses(self):
        with patch.object(qv.Path, 'is_dir', return_value=False), \
             patch.object(qv, '_worker') as worker, patch.object(qv.subprocess, 'run') as run, \
             contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            qv.main(['--worker', '--source', '.', '--out', 'unused'])
        self.assertEqual(raised.exception.code, 2)
        worker.assert_not_called()
        run.assert_not_called()

    def test_passed_validation_is_verified_and_not_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, reference = root / 'new', root / 'reference'
            session = root / 'session'
            session.mkdir()
            plan = {'session_dir': str(session), 'protocol_sha256': 'fixture-protocol',
                    'sources': {'new': {'path': str(source), 'commit': 'a' * 40}}}
            def git(path, *args):
                if args[0] == 'status':
                    return ''
                return 'a' * 40 if path == source else qv.REFERENCE_COMMIT
            def command(args, cwd, log):
                log.write_text('fixture: no search ran\n')
                if '--out' in args:
                    out = Path(args[args.index('--out')+1])
                    qv._write(out, {'positions': [{'name': 'fixture', 'fen': 'fixture', 'score': 7,
                                                  'depth': 3, 'nodes': 1, 'best_move': 'fixture'}]})
            with patch.object(qv, '_git', side_effect=git), patch.object(qv, '_command', side_effect=command) as run, \
                 contextlib.redirect_stdout(io.StringIO()):
                qv.validate(plan, reference)
                self.assertEqual(run.call_count, 4)
                qv.validate(plan, reference)
                self.assertEqual(run.call_count, 4)
                (session / 'validation' / 'see-on.json').write_text('tampered')
                with self.assertRaisesRegex(ValueError, 'artifact changed'):
                    qv.validate(plan, reference)
                self.assertEqual(run.call_count, 4)
