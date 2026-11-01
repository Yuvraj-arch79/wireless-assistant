"""Offline contract regressions; these do not measure model quality."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from evaluation.inputs import user_input
from evaluation.validate import validate

ROOT = Path(__file__).resolve().parents[1]


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.suite = json.loads((ROOT/'evaluation/cases.json').read_text(encoding='utf-8'))

    def test_suite(self):
        validate()

    def test_no_grader_fields_in_model_input(self):
        for case in self.suite['cases']:
            case = copy.deepcopy(case)
            case['future_secret_field'] = 'DO_NOT_SEND'
            for variant in [None] + [v['id'] for v in case.get('variants', [])]:
                with self.subTest(case=case['id'], variant=variant):
                    payload = user_input(case, variant)
                    self.assertEqual(set(payload), {'prompt', 'history'})
                    for turn in payload['history']:
                        self.assertEqual(set(turn), {'role', 'text'})
                    self.assertNotIn('DO_NOT_SEND', json.dumps(payload))

    def test_unknown_variant_fails_closed(self):
        with self.assertRaises(ValueError):
            user_input(self.suite['cases'][0], 'typo')

    def test_input_is_detached(self):
        case = next(c for c in self.suite['cases'] if c['history'])
        original = copy.deepcopy(case)
        user_input(case)['history'][0]['text'] = 'changed'
        self.assertEqual(case, original)

    def test_source_hint_in_primary_rejected(self):
        self.suite['cases'][0]['prompt'] = 'According to TS 38.201, explain Layer 1.'
        original = json.loads
        def altered(text, *args, **kwargs):
            value = original(text, *args, **kwargs)
            return self.suite if isinstance(value, dict) and 'suite_version' in value else value
        with patch('evaluation.validate.json.loads', side_effect=altered):
            with self.assertRaisesRegex(ValueError, 'Source hint'):
                validate()

    def test_natural_and_hinted_inputs_differ(self):
        for case in self.suite['cases']:
            if any(v['id'] == 'source_hint' for v in case.get('variants', [])):
                self.assertNotEqual(user_input(case)['prompt'], user_input(case, 'source_hint')['prompt'])


if __name__ == '__main__':
    unittest.main()
