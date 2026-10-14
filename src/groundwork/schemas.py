from typing import Literal

from pydantic import BaseModel, Field, StrictBool, field_validator, model_validator

from .settings import ConfigName


class Sentence(BaseModel):
    id: str
    text: str


class Document(BaseModel):
    id: str
    title: str
    url: str
    sentences: list[Sentence]


class Chunk(BaseModel):
    id: str
    document_id: str
    title: str
    url: str
    text: str
    sentence_ids: list[str]


class Evidence(BaseModel):
    chunk_id: str
    quote: str = Field(min_length=1, max_length=2000)


class Claim(BaseModel):
    text: str = Field(min_length=1, max_length=1800)
    evidence: list[Evidence] = Field(min_length=1, max_length=6)


class SufficiencyDecision(BaseModel):
    """Inference-time judgment; never receives gold labels or reference answers."""
    model_config = {'extra': 'forbid'}
    sufficient: StrictBool
    reason: str = Field(min_length=1, max_length=1000)
    missing_facts: list[str] = Field(max_length=8)
    evidence: list[Evidence] = Field(max_length=8)

    @model_validator(mode='after')
    def consistent(self):
        if self.sufficient and (self.missing_facts or not self.evidence):
            raise ValueError('Sufficient context needs evidence and no missing facts')
        if not self.sufficient and not any(f.strip() for f in self.missing_facts):
            raise ValueError('Insufficient context needs an explicit missing fact')
        return self


class GeneratedAnswer(BaseModel):
    status: Literal['answered', 'insufficient_evidence']
    short_answer: str = Field(default='', max_length=500)
    claims: list[Claim] = Field(default_factory=list, max_length=8)
    reason: str = Field(default='', max_length=1000)

    @model_validator(mode='after')
    def consistent(self):
        if self.status == 'answered' and not self.claims:
            raise ValueError('An answer requires evidence-backed claims')
        if self.status == 'insufficient_evidence' and (self.claims or self.short_answer):
            raise ValueError('Abstention must not include an answer')
        return self


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    config: ConfigName = 'hybrid'

    @field_validator('question', mode='before')
    @classmethod
    def trim_question(cls, value):
        return value.strip() if isinstance(value, str) else value


class RetrievalHit(BaseModel):
    chunk: Chunk
    score: float
    dense_score: float
    bm25_score: float


class Citation(Evidence):
    claim_index: int
    document_id: str
    title: str
    url: str
    sentence_ids: list[str]


class QueryResponse(GeneratedAnswer):
    request_id: str
    answer: str
    citations: list[Citation]
    retrieval: list[RetrievalHit]
    config: str
    index_id: str
    prompt_sha256: str
    timings: dict[str, float]
    attempts: list[dict]
    validation: dict
    sufficiency: SufficiencyDecision | None = None
    sufficiency_prompt_sha256: str | None = None


class GoldCase(BaseModel):
    id: str
    source_id: str
    split: Literal['dev', 'test']
    category: Literal['bridge', 'comparison', 'summary', 'unanswerable']
    question: str
    answerable: bool
    answers: list[str]
    required_evidence: list[str]
    acceptance: list[str]
    construction: str
