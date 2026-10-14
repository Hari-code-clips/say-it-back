"""Output schemas for the ADK agents (`output_schema`). Every field is required.

Field names are snake_case and plain: the model sees them in the JSON schema. The pipeline maps
them to the camelCase wire models in models.py.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Verdict = Literal["covered", "missed", "contradicted", "unclear"]


class Output(BaseModel):
    """Root of every `output_schema`. A validation error must not echo the model's output: ADK's
    Workflow logs a failed node with the exception text, and for the check that output holds the
    worker's transcript. Nested models inherit the root's setting."""

    model_config = ConfigDict(hide_input_in_errors=True)


class ExtractedStep(BaseModel):
    text: str
    hazard: str
    essential: list[str]
    source: Literal["instruction", "sop", "both"]
    sop_quote: str
    speakable: bool


class ExtractedConflict(BaseModel):
    step_number: int
    message: str


class ExtractOut(Output):
    steps: list[ExtractedStep]
    conflicts: list[ExtractedConflict]


class StepSentences(BaseModel):
    step_id: str
    sentence_indices: list[int]


class ScriptQuestion(BaseModel):
    text: str
    step_ids: list[str]


class ScriptOut(Output):
    sentences: list[str]
    step_map: list[StepSentences]
    questions: list[ScriptQuestion]
    closing: str


class BackQuestion(BaseModel):
    id: str
    text: str


class BackOut(Output):
    sentences: list[str]
    questions: list[BackQuestion]


class ReExplainOut(Output):
    explanation: str


class SpokenText(Output):
    text: str


class TranscriptItem(BaseModel):
    question_id: str
    original: str
    detected_lang: str
    translation: str
    flags: list[str]


class TranscribeOut(Output):
    transcripts: list[TranscriptItem]


class JudgeRating(BaseModel):
    step_id: str
    verdict: Verdict
    quote: str
    quote_translation: str
    reason: str
    confidence: float


class JudgeOut(Output):
    ratings: list[JudgeRating]
