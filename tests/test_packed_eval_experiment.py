"""Gate fixtures only: never run the real suite, benchmark or engine here."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import ab_compare as ab
from tools import packed_eval_experiment as exp


def bench(seconds=10, score=7):
    return dict(depth=4, tt_two_contexts=True, total_nodes=100, total_seconds=seconds,
                positions=[dict(name='fixture', fen='fixture', score=score, depth=4, nodes=100,
                                best_move='fixture', mate=None, attempted_depth=4)])


class PackedEvalExperimentTests(unittest.TestCase):
    def test_speed_and_exact_search_equivalence_are_required(self):
        self.assertTrue(exp.decision(bench(), [bench()]*3, [bench(9)]*3)['eligible_to_run_match'])
        self.assertFalse(exp.decision(bench(), [bench()]*3, [bench(9.9)]*3)['eligible_to_run_match'])
        with self.assertRaisesRegex(ValueError, 'equivalence'):
            exp.decision(bench(), [bench()]*3, [bench(9, 8)]*3)
        with self.assertRaises(ValueError):
            exp.decision(bench(), [bench()]*2, [bench(9)]*3)

    def test_fresh_validation_resume_and_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, reference, session = root/'candidate', root/'reference', root/'session'
            session.mkdir()
            common = {'TTTwoContexts':True, 'QuiescenceSEE':False, 'NextIterationPct':150}
            plan = dict(session_dir=str(session), protocol_sha256='fixture', games=100,
                        chunk_games=100, movetime_ms=100,
                        sources={side:dict(path=str(source), commit='a'*40) for side in ['new','old']},
                        feature_options={side:{**common, 'EvalPackedBase':v} for side,v in [('new',True),('old',False)]})
            def git(path, *args):
                return '' if args[0]=='status' else 'a'*40 if path==source else exp.REFERENCE_COMMIT
            def command(args, cwd, log):
                log.write_text('fixture; no engine or real tests ran')
                if '--out' in args:
                    exp._write(Path(args[args.index('--out')+1]), bench(9 if '--packed' in args else 10))
            with patch.object(ab, 'ROOT', root), patch.object(ab,'load_plan',return_value=plan), \
                 patch.object(exp,'_git',side_effect=git), patch.object(exp,'_command',side_effect=command) as run, \
                 contextlib.redirect_stdout(io.StringIO()):
                exp.validate(session, reference)
                self.assertEqual(run.call_count, 8)
                self.assertEqual(sum('--packed' in c.args[0] for c in run.call_args_list), 3)
                status=exp._read(session/'validation/status.json')
                self.assertTrue(status['passed'])
                exp.validate(session, reference)
                self.assertEqual(run.call_count, 8)
                gate=exp._read(session/'eligibility.json')
                gate['eligible_to_run_match']=False
                exp._write(session/'eligibility.json',gate)
                with self.assertRaisesRegex(ValueError,'decision changed'):
                    exp.validate(session,reference)
                gate['eligible_to_run_match']=True
                exp._write(session/'eligibility.json',gate)
                (session/'validation/bench-1-packed.json').write_text('{}')
                with self.assertRaisesRegex(ValueError,'artifact changed'):
                    exp.validate(session,reference)
                self.assertEqual(run.call_count,8)

    def test_pc_guard_blocks_workers_and_validation(self):
        for args in [[], ['--worker', '--source','fixture','--out','fixture']]:
            with patch.object(Path,'is_dir',return_value=False), patch.object(exp,'_worker') as worker, \
                 patch.object(exp,'validate') as validate, contextlib.redirect_stderr(io.StringIO()), \
                 self.assertRaises(SystemExit):
                exp.main(args)
            worker.assert_not_called()
            validate.assert_not_called()
