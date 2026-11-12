"""Exercise notebook preparation with stale imports, without importing the engine."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


class TTPairNotebookTests(unittest.TestCase):
    def test_prepare_and_resume_ignore_cached_tools_and_reject_changed_settings(self):
        notebook = Path(__file__).resolve().parents[1] / 'notebooks/kaggle_tt_two_contexts.ipynb'
        cell = ''.join(json.loads(notebook.read_text(encoding='utf-8'))['cells'][4]['source'])
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / 'tools').mkdir()
            (workspace / 'tools/__init__.py').write_text('', encoding='utf-8')
            # The stand-in writes only metadata; it cannot start a search or a match.
            (workspace / 'tools/ab_compare.py').write_text('''
import json, os
def prepare(session, new_source, old_source, *, new_commit, old_commit, **settings):
    session.mkdir(parents=True)
    settings['selection_seed'] = settings.pop('seed')
    settings['feature_options'] = {'new': settings.pop('new_options'), 'old': settings.pop('old_options')}
    settings['concurrency'] = min(settings['concurrency'], os.cpu_count() or 1)
    settings['sources'] = {'new': str(new_source), 'old': str(old_source)}
    settings['commit'] = new_commit
    (session / 'protocol.json').write_text(json.dumps(settings))
    (session / 'SUMMARY.md').write_text('prepared fixture')
    return settings
def load_plan(session):
    return json.loads((session / 'protocol.json').read_text())
''', encoding='utf-8')
            session = workspace / 'session'
            published = []

            def checked(args, *, cwd):
                return subprocess.run(args, cwd=cwd, text=True, capture_output=True,
                                      check=True, timeout=2).stdout

            scope = dict(workspace=workspace, session=session, new_source=workspace / 'new',
                         old_source=workspace / 'old', CODE_COMMIT='pinned', GAMES=100,
                         CHUNK_GAMES=100, MOVETIME_MS=100, CONCURRENCY=2, HASH_MB=16,
                         MAX_PLIES=400, SEED=1, NEW_OPTIONS={'TTTwoContexts': True},
                         OLD_OPTIONS={'TTTwoContexts': False}, SESSION_ID='fixture',
                         checked=checked, publish_results=published.append,
                         sys=sys, json=json)
            stale_tools = types.ModuleType('tools')
            stale_ab = types.ModuleType('tools.ab_compare')
            stale_ab.__file__ = '/obsolete/checkout/tools/ab_compare.py'
            stale_tools.ab_compare = stale_ab
            with patch.dict(sys.modules, {'tools': stale_tools, 'tools.ab_compare': stale_ab}), \
                 contextlib.redirect_stdout(io.StringIO()):
                exec(compile(cell, str(notebook), 'exec'), scope)
                original = (session / 'protocol.json').read_bytes()
                self.assertEqual(scope['plan']['movetime_ms'], 100)
                self.assertEqual(scope['plan']['commit'], 'pinned')
                self.assertEqual(len(published), 1)
                exec(compile(cell, str(notebook), 'exec'), scope)
                self.assertEqual((session / 'protocol.json').read_bytes(), original)
                self.assertEqual(len(published), 2)
                scope['MOVETIME_MS'] = 500
                with self.assertRaises(subprocess.CalledProcessError) as error:
                    exec(compile(cell, str(notebook), 'exec'), scope)
                self.assertIn('Settings differ', error.exception.stderr)
                self.assertEqual((session / 'protocol.json').read_bytes(), original)
                self.assertEqual(len(published), 2)
