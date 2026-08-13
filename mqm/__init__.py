"""math-question-matcher：字段级加权的数学题相似检索。"""

from .encoders import Encoder, HashingEncoder, SentenceTransformerEncoder, get_encoder
from .index import Match, QuestionIndex, aliases_from_config, build_index, load_config
from .schema import Question, load_aliases, load_question, load_questions, question_from_dict
from .scoring import DEFAULT_WEIGHTS, FIELD_LABELS, FieldScore, ScoreResult, score_pair
from .similarity import (
    difficulty_similarity,
    set_similarity,
    structure_similarity,
    text_similarity,
)
from .structure import StructureSignature, parse_structure

__all__ = [
    "Encoder",
    "HashingEncoder",
    "SentenceTransformerEncoder",
    "get_encoder",
    "Match",
    "QuestionIndex",
    "build_index",
    "load_config",
    "aliases_from_config",
    "Question",
    "load_aliases",
    "load_question",
    "load_questions",
    "question_from_dict",
    "DEFAULT_WEIGHTS",
    "FIELD_LABELS",
    "FieldScore",
    "ScoreResult",
    "score_pair",
    "set_similarity",
    "text_similarity",
    "structure_similarity",
    "difficulty_similarity",
    "StructureSignature",
    "parse_structure",
]
__version__ = "0.1.0"
