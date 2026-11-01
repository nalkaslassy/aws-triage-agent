import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from aws_triage.evaluation import load_suite
from aws_triage.pilot import (BasicBedrockPlanner, execute_plan, recorded_run, run_plan,
                              rules_baselines, validate_basic)
from aws_triage.planner import BedrockPlanner, ReplayPlanner
from aws_triage.model import Bundle

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / 'pilot'


def finish(candidates=None):
    return {'action': 'finish', 'candidates': candidates or [], 'next_steps': ['collect_missing']}


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.packets, self.rubric = load_suite(SUITE)

    def test_twelve_cases_and_seventy_two_runs(self):
        plan = run_plan(SUITE)
        self.assertEqual(len(self.packets), 12)
        self.assertEqual(len(plan['jobs']), 72)
        self.assertEqual(plan['max_model_calls'], 432)
        self.assertEqual(plan, run_plan(SUITE))
        self.assertNotEqual(plan['jobs'], run_plan(SUITE, seed=1)['jobs'])

    def test_both_arms_receive_identical_unlabelled_inputs(self):
        packet = self.packets[0][1]
        states = []
        class Recording:
            def next(self, state):
                states.append(copy.deepcopy(state)); return finish()
        for arm in ('basic', 'constrained'):
            recorded_run(packet, Recording(), arm)
        self.assertEqual(states[0], states[1])
        self.assertNotIn('allowed_causes', json.dumps(states))
        self.assertNotIn('case01', json.dumps(states))

    def test_basic_retains_unsupported_proposal_constrained_rejects_it(self):
        packet = copy.deepcopy(self.packets[4][1])
        packet['bundle']['evidence'] = copy.deepcopy(self.packets[0][1]['followups']['permissions'][1:])
        packet['bundle']['evidence'][0]['id'] = 'E001'
        candidate = {'cause': 'authorization', 'supporting': ['E001'], 'contradicting': []}
        decision = finish([candidate])
        basic = recorded_run(packet, ReplayPlanner([decision]), 'basic')
        strict = recorded_run(packet, ReplayPlanner([decision]), 'constrained')
        self.assertEqual(basic['stop_reason'], 'finished')
        self.assertEqual(strict['stop_reason'], 'invalid_decision')
        self.assertEqual(strict['raw_proposals'], [decision])
        self.assertEqual(strict['assessment']['candidates'], [])

    def test_basic_still_rejects_unknown_refs_and_unsafe_checks(self):
        packet = self.packets[0][1]
        for d in ({'action': 'check', 'check': 'delete'}, finish([{'cause': 'authorization', 'supporting': ['unknown'], 'contradicting': []}])):
            self.assertEqual(recorded_run(packet, ReplayPlanner([d]), 'basic')['stop_reason'], 'invalid_decision')

    def test_production_and_pilot_strict_agree_on_valid_case(self):
        from aws_triage.agent import run_agent
        from aws_triage.followups import ReplayFollowups
        p = self.packets[0][1]
        decisions = [{'action':'check','check':'permissions'}, finish([{'cause':'authorization','supporting':['E001','F002'],'contradicting':[]}])]
        strict = recorded_run(p, ReplayPlanner(decisions), 'constrained')
        production = run_agent(Bundle.from_dict(p['bundle']), p['manifest'], p['function'], p['symptom'], ReplayPlanner(decisions), ReplayFollowups(p['followups']))
        self.assertEqual(strict['assessment'], production['assessment'])
        self.assertEqual(strict['journal'], production['journal'])

    def test_budget_and_cached_checks(self):
        p = self.packets[0][1]
        r = recorded_run(p, ReplayPlanner([{'action':'check','check':'permissions'}] * 10), 'basic')
        self.assertEqual(r['stop_reason'], 'step_budget')
        self.assertEqual(r['metrics']['planner_turns'], 6)
        self.assertEqual(r['metrics']['check_attempts'], 1)

    def test_resume_and_changed_config(self):
        config = {'plan': run_plan(SUITE, 1, 1), 'model_id': 'fake'}
        calls = []
        def factory(arm):
            calls.append(arm);return ReplayPlanner([finish()])
        with tempfile.TemporaryDirectory() as out:
            summary = execute_plan(SUITE, out, config, factory)
            self.assertEqual(summary['completed_runs'], 2)
            execute_plan(SUITE, out, config, factory)
            self.assertEqual(len(calls), 2)
            with self.assertRaises(ValueError):
                execute_plan(SUITE, out, {**config, 'model_id':'changed'}, factory)

    def test_provider_failure_stops_batch_without_error_body(self):
        class Broken:
            def next(self, state): raise RuntimeError('SECRET_ERROR_BODY')
        config = {'plan': run_plan(SUITE, 1, 1)}
        with tempfile.TemporaryDirectory() as out:
            result = execute_plan(SUITE, out, config, lambda arm: Broken())
            self.assertEqual(result['completed_runs'], 1)
            self.assertNotIn('SECRET_ERROR_BODY', ''.join(p.read_text() for p in Path(out).glob('*.json')))

    def test_baselines_are_separately_identified(self):
        result = rules_baselines(self.packets[0][1])
        self.assertIn('initial_only', result)
        self.assertIn('all_recorded_observations', result)
        self.assertIn('not equal tool-cost', result['limits'])

    def test_arm_blinded_review_export(self):
        spec = importlib.util.spec_from_file_location('export_review', ROOT/'sandbox/export_pilot_review.py')
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp)/'runs'
            execute_plan(SUITE, runs, {'plan':run_plan(SUITE,1,1)}, lambda arm:ReplayPlanner([finish()]))
            output=Path(tmp)/'review'
            self.assertEqual(module.export_review(runs, output), 2)
            packets = json.loads((output/'packets.json').read_text())
            self.assertTrue(all('arm' not in p and 'case' not in p for p in packets))
            self.assertEqual(len(json.loads((output/'PRIVATE-key.json').read_text())), 2)
            self.assertIn('accepted_unsupported', (output/'scoring.csv').read_text())

    def test_basic_prompt_does_not_contain_strict_requirements(self):
        self.assertNotIn('Authorization candidates require', BasicBedrockPlanner.system_prompt)
        self.assertIn('Authorization candidates require', BedrockPlanner.system_prompt)
