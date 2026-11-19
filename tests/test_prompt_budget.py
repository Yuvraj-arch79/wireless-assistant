"""Prompt growth eats the evidence preview inside A's fixed 8000-token Groq request.

Live run 44519349731 (19 Nov) stopped the clause 4.2.3 question with CONTEXT_LIMIT after
the A prompt had grown by ~360 tokens. Ceilings: base branch + a small allowance; raising
one needs a live check, not just green tests.
"""
import tiktoken
from wireless_assistant import prompts

CEILING = {'A': 820, 'B': 650, 'C': 950}


def test_role_prompts_stay_within_token_ceilings():
    enc = tiktoken.get_encoding('o200k_harmony')
    used = {r: len(enc.encode(prompts.COMMON + prompts.ROLES[r])) for r in 'ABC'}
    assert all(used[r] <= CEILING[r] for r in 'ABC'), used


def test_clarification_rule_matches_contract():
    # Live run 44519349731: A clarified a vague follow-up with requirements=[] twice
    # (schema minItems 1) and the run stopped with INVALID_CONTRACT.
    assert 'A clarification still needs at least one requirement' in prompts.ROLES['A']
