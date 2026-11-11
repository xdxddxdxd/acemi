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

