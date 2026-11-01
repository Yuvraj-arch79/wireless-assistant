"""Strict user-input boundary. Gold labels and fixtures stay in the harness."""
from copy import deepcopy


def user_input(case, variant_id=None):
    """Return only user-visible input; never serialize an entire case to a model.

    Fixture setup and reviewer evidence require separate production-shaped adapters.
    This function is not a live model runner or a fixture executor.
    """
    prompt = case['prompt']
    if variant_id is not None:
        variants = {v['id']: v for v in case.get('variants', [])}
        if variant_id not in variants:
            raise ValueError('Unknown variant')
        prompt = variants[variant_id]['prompt']
    history = []
    for turn in case['history']:
        if turn['role'] not in ('user', 'assistant', 'clarification'):
            raise ValueError('Invalid history role')
        history.append({'role': turn['role'], 'text': turn['text']})
    return deepcopy({'prompt': prompt, 'history': history})
