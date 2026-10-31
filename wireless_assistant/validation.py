"""Backend release checks: identities and consistency, not a truth oracle."""
from .common import AppError, digest


def require(condition, message):
    if not condition:
        raise AppError('INVALID_CONTRACT',message,502)


def partition(left, right, expected):
    require(len(left)==len(set(left)) and len(right)==len(set(right)), 'Coverage contains duplicates.')
    require(not set(left)&set(right) and set(left)|set(right)==set(expected),'Coverage must exactly partition current requirements.')


def validate_need(need, originals):
    allowed={digest(o['ref']) for o in originals}
    require(bool(need['original_refs']),'Original query references are required.')
    refs=need['original_refs']+[ref for req in need['requirements'] for ref in req['established_by']]
    require(all(digest(ref) in allowed for ref in refs),'Need references unavailable original messages.')
    require(all(req['established_by'] for req in need['requirements']),'Each requirement must reference an original message.')
    ids={r['req_id'] for r in need['requirements']}
    require(all(set(g['requirement_ids'])<=ids for g in need['unresolved_gaps']),'Gap references unknown requirements.')


def validate_draft(candidate, need, evidence, previous_review):
    expected={r['req_id'] for r in need['requirements']}
    unresolved=[r['req_id'] for r in candidate['unresolved_requirements']]
    partition(candidate['covered_requirements'],unresolved,expected)
    if unresolved:
        require(bool(candidate['limitation_statement']) and candidate['limitation_statement'] in candidate['answer_markdown'], 'Partial answer must contain its exact limitation statement.')
    allowed={p['passage_id']:p for p in evidence}
    markers=[]
    for c in candidate['citations']:
        markers.append(c['marker'])
        require(candidate['answer_markdown'].count(c['marker'])>=2 and c['claim_anchor'] in candidate['answer_markdown'],'Citations need an inline marker, an end reference and a matching claim anchor.')
        require(len(c['passage_ids'])==len(set(c['passage_ids'])),'Duplicate citation sources.')
        require(all(pid in allowed and not allowed[pid]['unreadable'] for pid in c['passage_ids']),'Citation references missing or unreadable evidence.')
        for pid in c['passage_ids']:
            p=allowed[pid]
            require(p['spec_number'] in candidate['answer_markdown'] and p['document_version'] in candidate['answer_markdown'] and p['clause_id'] in candidate['answer_markdown'],'End references must identify specification, version and clause.')
    require(len(markers)==len(set(markers)),'Duplicate citation markers.')
    import re
    require(set(re.findall(r'\[[1-9][0-9]?\]',candidate['answer_markdown']))==set(markers),'Answer contains unbound citation markers.')
    for p in evidence:
        require(not need['scope']['release'] or p['release']==need['scope']['release'],'Wrong release in evidence.')
        require(not need['scope']['spec_numbers'] or p['spec_number'] in need['scope']['spec_numbers'],'Wrong specification in evidence.')
        require(not need['scope']['document_versions'] or p['document_version'] in need['scope']['document_versions'],'Wrong document version in evidence.')
    previous={f['finding_id'] for f in (previous_review or {}).get('findings',[])}
    revisions=candidate['revision_log']
    require({r['finding_id'] for r in revisions}==previous and len(revisions)==len(previous),'Revision log must address every prior finding exactly once.')
    for entry in revisions:
        require(set(entry['evidence_ids'])<=set(allowed),'Revision cites unknown evidence.')
        if entry['disposition']=='retained_with_evidence':
            require(bool(entry['evidence_ids']),'Disagreement needs evidence.')


def validate_review(review, binding, candidate, need, evidence, prior_candidate, round_number):
    require(review['reviewed_binding']==binding,'Review binding does not match exact candidate and inputs.')
    ids={r['req_id'] for r in need['requirements']}
    partition(review['satisfied_requirements'],review['unmet_requirements'],ids)
    findings=review['findings'];blocking=[f for f in findings if f['blocking']]
    require(len({f['finding_id'] for f in findings})==len(findings),'Duplicate finding IDs.')
    allowed={p['passage_id'] for p in evidence}
    require(all(set(f['evidence_ids'])<=allowed for f in findings),'Review references unknown evidence.')
    regression=review['regression_check']
    if round_number:
        require(regression['status']=='checked' and regression['compared_candidate_id']==prior_candidate['candidate_id'],'Revision must check the prior candidate for regressions.')
    else:
        require(regression['status']=='not_applicable' and regression['compared_candidate_id'] is None,'First review must not claim a previous candidate.')
    require(set(regression['lost_or_changed_requirement_ids'])<=ids,'Regression references unknown requirements.')
    require(set(regression['resulting_finding_ids'])<={f['finding_id'] for f in findings},'Regression references unknown findings.')
    if regression['lost_or_changed_requirement_ids']:
        require(bool(regression['resulting_finding_ids']),'Losses need concrete findings.')
    decision=review['decision']
    if decision=='findings':
        require(bool(blocking),'Findings decision requires actionable blocking findings.')
    else:
        require(not blocking,'An accepted review cannot have blocking findings.')
        require(set(review['satisfied_requirements'])==set(candidate['covered_requirements']) and set(review['unmet_requirements'])=={r['req_id'] for r in candidate['unresolved_requirements']},'Reviewer and writer disagree on coverage.')
        if decision=='accepted':
            require(not review['unmet_requirements'],'A full acceptance cannot omit requirements.')
        else:
            require(bool(review['satisfied_requirements']) and bool(review['unmet_requirements']) and bool(candidate['limitation_statement']),'Partial acceptance needs useful coverage and explicit limitations.')
