"""
智能模块初始化
"""

from .movie_knowledge import (
    MovieKnowledgeEngine,
    MovieDNA,
    CharacterProfile,
    MovieGenre,
    MovieStyle,
    movie_engine
)

__all__ = [
    'MovieKnowledgeEngine',
    'MovieDNA',
    'CharacterProfile',
    'MovieGenre',
    'MovieStyle',
    'movie_engine'
]