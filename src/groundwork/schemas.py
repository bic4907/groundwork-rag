from typing import Literal

from pydantic import BaseModel, Field, model_validator


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
    question: str = Field(min_length=3, max_length=2000)
    config: Literal['baseline', 'hybrid', 'bm25'] = 'hybrid'


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
