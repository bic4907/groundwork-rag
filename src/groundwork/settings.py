from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
ConfigName = Literal['baseline', 'hybrid', 'bm25', 'sufficient']
CONFIG_NAMES = ('baseline', 'hybrid', 'bm25', 'sufficient')


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore', env_ignore_empty=True)
    generation_provider: Literal['ollama', 'remote'] = 'ollama'
    generation_base_url: str = 'http://127.0.0.1:11434'
    generation_model: str = 'llama3:latest'
    generation_api_key: SecretStr = SecretStr('')
    embedding_provider: Literal['ollama', 'remote'] = 'ollama'
    embedding_base_url: str = 'http://127.0.0.1:11434'
    embedding_model: str = 'nomic-embed-text:latest'
    embedding_api_key: SecretStr = SecretStr('')
    judge_provider: Literal['disabled', 'ollama', 'remote'] = 'disabled'
    judge_base_url: str = ''
    judge_model: str = ''
    judge_api_key: SecretStr = SecretStr('')
    api_timeout_seconds: float = Field(default=180, gt=0)
    max_concurrent_jobs: int = Field(default=1, ge=1, le=4)
    generation_input_price: float | None = Field(default=None, ge=0)
    generation_output_price: float | None = Field(default=None, ge=0)
    embedding_input_price: float | None = Field(default=None, ge=0)
    judge_input_price: float | None = Field(default=None, ge=0)
    judge_output_price: float | None = Field(default=None, ge=0)
    app_access_token: SecretStr = SecretStr('')
    send_remote_seed: bool = False


class ExperimentConfig(BaseModel):
    name: str
    retrieval: Literal['dense', 'bm25', 'hybrid'] = 'dense'
    top_k: int = Field(default=6, ge=1, le=20)
    candidate_k: int = Field(default=24, ge=1, le=100)
    rrf_k: int = Field(default=60, ge=1)
    chunk_words: int = Field(default=180, ge=40, le=1000)
    overlap_sentences: int = Field(default=1, ge=0, le=4)
    max_context_chars: int = Field(default=16000, ge=1000, le=40000)
    temperature: float = Field(default=0, ge=0, le=2)
    seed: int = 42
    max_output_tokens: int = Field(default=650, ge=100, le=3000)
    sufficiency_gate: bool = False
    sufficiency_max_output_tokens: int = Field(default=500, ge=100, le=1500)
    hypothesis: str = ''

    @model_validator(mode='after')
    def candidates_cover_results(self):
        if self.candidate_k < self.top_k:
            raise ValueError('candidate_k must be >= top_k')
        return self


def load_config(name: str) -> ExperimentConfig:
    # User input selects a registered config; it is never an arbitrary path.
    if name not in CONFIG_NAMES:
        raise ValueError('Unknown experiment configuration')
    return ExperimentConfig.model_validate(yaml.safe_load((ROOT / 'configs' / f'{name}.yaml').read_text()))
