"""Strict role DTOs; prompts cannot grant tools or change backend identities."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class OriginalRef(Strict):
    message_id: str
    session_id: str
    content_hash: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)


class Requirement(Strict):
    req_id: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=800)
    mandatory: bool
    established_by: list[OriginalRef]


class Scope(Strict):
    spec_numbers: list[str]
    release: str | None
    document_versions: list[str]
    default_used: bool


class Gap(Strict):
    gap_id: str
    kind: Literal["user_detail", "source", "history", "conflict", "unreadable", "context_limit"]
    requirement_ids: list[str]
    reason: str = Field(min_length=1, max_length=1000)
    source_or_message_ids: list[str]


class Need(Strict):
    topic: str
    requested_task: str
    language: str
    depth: str
    scope: Scope
    requirements: list[Requirement] = Field(min_length=1, max_length=16)
    assumptions: list[str]
    unresolved_gaps: list[Gap]
    original_refs: list[OriginalRef]

    @model_validator(mode="after")
    def unique(self):
        ids = [r.req_id for r in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate requirements")
        return self


class ToolBase(Strict):
    purpose: str = Field(min_length=1, max_length=500)
    requirement_ids: list[str]
    limit: int = Field(ge=1, le=12)


class Search(ToolBase):
    kind: Literal["corpus_search"]
    query: str = Field(min_length=1, max_length=1000)
    filters: Scope


class Expand(ToolBase):
    kind: Literal["expand_passages"]
    passage_ids: list[str] = Field(min_length=1, max_length=12)
    relation: Literal["parent", "previous", "next", "cross_reference"]


class HistorySearch(ToolBase):
    kind: Literal["history_search"]
    query: str = Field(min_length=1, max_length=500)
    cursor: str | None


class HistoryFetch(Strict):
    kind: Literal["history_fetch"]
    purpose: str = Field(min_length=1, max_length=500)
    requirement_ids: list[str]
    refs: list[OriginalRef] = Field(min_length=1, max_length=12)


Tool = Annotated[Search | Expand | HistorySearch | HistoryFetch, Field(discriminator="kind")]


class ABase(Strict):
    intent_relation: Literal["same_need", "correction", "new_topic", "uncertain"]


class Clarification(Strict):
    question: str = Field(min_length=1, max_length=1000)
    missing_requirement_ids: list[str]
    alternatives: list[str]
    gap_key: str = Field(min_length=1, max_length=100)


class AClarify(ABase):
    action: Literal["clarify"]
    need: Need
    clarification: Clarification
    coverage_gaps: list[Gap]


class ACollect(ABase):
    action: Literal["collect"]
    need: Need
    requests: list[Tool] = Field(min_length=1, max_length=4)
    coverage_gaps: list[Gap]


class AReady(ABase):
    action: Literal["ready_for_b"]
    need: Need
    coverage_gaps: list[Gap]


class AOut(ABase):
    action: Literal["out_of_scope"]
    scope_reason: str = Field(min_length=1, max_length=1000)
    need: Need | None


AOutput = Annotated[AClarify | ACollect | AReady | AOut, Field(discriminator="action")]


class Citation(Strict):
    marker: str = Field(pattern=r"^\[[1-9][0-9]?\]$")
    claim_anchor: str = Field(min_length=1, max_length=1000)
    passage_ids: list[str] = Field(min_length=1, max_length=12)


class Unresolved(Strict):
    req_id: str
    reason: str = Field(min_length=1, max_length=1000)


class Revision(Strict):
    finding_id: str
    disposition: Literal["changed", "retained_with_evidence", "unresolved"]
    target: str
    reason: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[str]


class BDraft(Strict):
    action: Literal["submit_draft"]
    answer_markdown: str = Field(min_length=1, max_length=16000)
    citations: list[Citation] = Field(min_length=1, max_length=24)
    covered_requirements: list[str]
    unresolved_requirements: list[Unresolved]
    limitation_statement: str | None
    revision_log: list[Revision]


class Missing(Strict):
    type: Literal["source", "history", "user_detail"]
    item: str = Field(min_length=1, max_length=1000)
    why_material: str = Field(min_length=1, max_length=1000)
    requirement_ids: list[str]


class BMissing(Strict):
    action: Literal["request_missing_info"]
    missing_info: Missing


class BCannot(Strict):
    action: Literal["cannot_answer"]
    cannot_answer_reason: list[Gap] = Field(min_length=1)


BOutput = Annotated[BDraft | BMissing | BCannot, Field(discriminator="action")]


class Binding(Strict):
    candidate_id: str
    candidate_hash: str
    need_id: str
    need_hash: str
    evidence_set_id: str
    evidence_hash: str
    context_id: str
    context_hash: str


class Finding(Strict):
    finding_id: str
    finding_type: Literal["contradicted_claim", "insufficient_support", "missing_user_requirement", "presentation_problem"]
    blocking: bool
    target_claim_or_req: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[str]


class Regression(Strict):
    status: Literal["not_applicable", "checked"]
    compared_candidate_id: str | None
    lost_or_changed_requirement_ids: list[str]
    resulting_finding_ids: list[str]


class COutput(Strict):
    reviewed_binding: Binding
    decision: Literal["accepted", "partial_accepted", "findings"]
    satisfied_requirements: list[str]
    unmet_requirements: list[str]
    findings: list[Finding]
    regression_check: Regression


ADAPTERS = {"A": TypeAdapter(AOutput), "B": TypeAdapter(BOutput), "C": TypeAdapter(COutput)}
