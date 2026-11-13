"""Compatibility shim: exact-clause requests must still pass through A."""

def route(engine, rid, w, state, context, evidence):
    return None, evidence
