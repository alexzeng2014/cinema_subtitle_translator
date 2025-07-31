"""
智能电影知识引擎
基于电影信息构建知识图谱，为翻译提供上下文感知能力
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import structlog

from ..api.deepseek_client import DeepSeekClient
from ..security.config import get_config
from ..storage.cache_manager import CacheManager

logger = structlog.get_logger(__name__)


class MovieGenre(Enum):
    """电影类型枚举"""
    ACTION = "动作"
    COMEDY = "喜剧"
    DRAMA = "剧情"
    HORROR = "恐怖"
    ROMANCE = "爱情"
    SCI_FI = "科幻"
    THRILLER = "惊悚"
    ANIMATION = "动画"
    DOCUMENTARY = "纪录片"
    FANTASY = "奇幻"
    MYSTERY = "悬疑"
    ADVENTURE = "冒险"
    CRIME = "犯罪"
    FAMILY = "家庭"
    MUSICAL = "音乐"
    WAR = "战争"
    WESTERN = "西部"


class MovieStyle(Enum):
    """电影风格枚举"""
    PHILOSOPHICAL = "哲学思辨"
    HUMOROUS = "轻松幽默"
    ROMANTIC = "浪漫深情"
    DARK = "黑暗深沉"
    INSPIRATIONAL = "励志向上"
    NOSTALGIC = "怀旧温情"
    SARCASTIC = "讽刺幽默"
    EPIC = "史诗宏大"
    INTIMATE = "私密细腻"
    EXPERIMENTAL = "实验前卫"


@dataclass
class CharacterProfile:
    """角色语言画像"""
    name: str
    personality_traits: List[str] = field(default_factory=list)
    speech_style: str = "normal"
    education_level: str = "medium"
    emotional_range: List[str] = field(default_factory=list)
    catchphrases: List[str] = field(default_factory=list)
    cultural_background: str = "western"
    age_group: str = "adult"
    profession: Optional[str] = None
    relationship_dynamics: Dict[str, str] = field(default_factory=dict)


@dataclass
class MovieDNA:
    """电影DNA分析结果"""
    title: str
    original_title: str
    year: int
    genres: List[MovieGenre] = field(default_factory=list)
    primary_style: MovieStyle = MovieStyle.PHILOSOPHICAL
    themes: List[str] = field(default_factory=list)
    tone: str = "neutral"
    pacing: str = "medium"
    target_audience: str = "general"
    cultural_context: str = "western"
    language_complexity: str = "medium"
    emotional_intensity: str = "medium"
    characters: Dict[str, CharacterProfile] = field(default_factory=dict)
    key_vocabulary: Set[str] = field(default_factory=set)
    cultural_references: List[str] = field(default_factory=list)
    time_period: Optional[str] = None
    setting: Optional[str] = None
    director: Optional[str] = None
    box_office: Optional[str] = None
    awards: List[str] = field(default_factory=list)
    similar_movies: List[str] = field(default_factory=list)
    translation_challenges: List[str] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)


class MovieKnowledgeEngine:
    """电影知识引擎 - 智能分析电影特征"""
    
    def __init__(self):
        self.config = get_config()
        self.deepseek_client = DeepSeekClient()
        self.cache_manager = CacheManager()
        self._knowledge_base: Dict[str, MovieDNA] = {}
        self._initialized = False
    
    async def initialize(self):
        """初始化知识引擎"""
        if self._initialized:
            return
        
        logger.info("正在初始化电影知识引擎...")
        
        # 加载缓存的电影知识
        await self._load_cached_knowledge()
        
        # 预加载热门电影知识
        await self._preload_popular_movies()
        
        self._initialized = True
        logger.info("电影知识引擎初始化完成")
    
    async def _load_cached_knowledge(self):
        """加载缓存的电影知识"""
        try:
            cached_data = await self.cache_manager.get("movie_knowledge_base")
            if cached_data:
                knowledge_data = json.loads(cached_data)
                for movie_id, data in knowledge_data.items():
                    self._knowledge_base[movie_id] = self._deserialize_movie_dna(data)
                logger.info(f"加载了 {len(self._knowledge_base)} 部电影的知识缓存")
        except Exception as e:
            logger.warning("加载电影知识缓存失败", error=str(e))
    
    async def _preload_popular_movies(self):
        """预加载热门电影知识"""
        popular_movies = [
            ("Inception", 2010),
            ("The Dark Knight", 2008),
            ("Pulp Fiction", 1994),
            ("The Matrix", 1999),
            ("Forrest Gump", 1994),
            ("The Godfather", 1972),
            ("Titanic", 1997),
            ("Avatar", 2009),
            ("Avengers: Endgame", 2019),
            ("Interstellar", 2014)
        ]
        
        for title, year in popular_movies:
            movie_id = f"{title}_{year}"
            if movie_id not in self._knowledge_base:
                try:
                    await self.analyze_movie(title, year)
                except Exception as e:
                    logger.warning(f"预加载电影知识失败: {title} ({year})", error=str(e))
    
    async def analyze_movie(self, title: str, year: Optional[int] = None) -> MovieDNA:
        """分析电影并构建DNA"""
        movie_id = f"{title}_{year}" if year else title
        
        # 检查缓存
        if movie_id in self._knowledge_base:
            return self._knowledge_base[movie_id]
        
        # 检查Redis缓存
        cached_dna = await self.cache_manager.get(f"movie_dna_{movie_id}")
        if cached_dna:
            dna = self._deserialize_movie_dna(json.loads(cached_dna))
            self._knowledge_base[movie_id] = dna
            return dna
        
        logger.info(f"正在分析电影: {title} ({year})")
        
        # 使用AI分析电影
        dna = await self._ai_analyze_movie(title, year)
        
        # 缓存结果
        self._knowledge_base[movie_id] = dna
        await self._cache_movie_dna(movie_id, dna)
        
        return dna
    
    async def _ai_analyze_movie(self, title: str, year: Optional[int] = None) -> MovieDNA:
        """使用AI分析电影特征"""
        
        analysis_prompt = self._build_analysis_prompt(title, year)
        
        try:
            response = await self.deepseek_client.chat_completion(
                messages=[
                    {"role": "system", "content": "你是一位专业的电影分析专家，精通电影理论、文化分析和语言学。"},
                    {"role": "user", "content": analysis_prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            analysis_text = response.choices[0].message.content
            return self._parse_analysis_response(title, year, analysis_text)
            
        except Exception as e:
            logger.error("AI电影分析失败", error=str(e))
            # 返回基础DNA
            return MovieDNA(
                title=title,
                original_title=title,
                year=year or 2023,
                genres=[MovieGenre.DRAMA],
                primary_style=MovieStyle.PHILOSOPHICAL
            )
    
    def _build_analysis_prompt(self, title: str, year: Optional[int]) -> str:
        """构建电影分析提示词"""
        
        prompt = f"""请深入分析电影《{title}》{"(" + str(year) + ")" if year else ""}，提供以下维度的详细分析：

## 电影基本信息
- 中文译名（如果有）
- 导演
- 主要类型
- 上映年份
- 时代背景
- 故事发生地

## 深度特征分析
### 1. 类型与风格
- 主要类型（动作/喜剧/剧情/科幻等）
- 叙事风格（线性/非线性/多线叙事）
- 视觉风格（写实/夸张/艺术化）
- 整体基调（轻松/沉重/悬疑/浪漫）

### 2. 主题与内涵
- 核心主题（3-5个关键词）
- 哲学思考
- 社会议题
- 情感核心

### 3. 角色分析
- 主要角色及其性格特征
- 角色关系动态
- 角色语言风格（正式/随意/幽默/严肃）
- 角色背景和文化特征

### 4. 语言特征
- 对话复杂度
- 专业术语使用频率
- 文化典故和引用
- 幽默风格（讽刺/滑稽/黑色幽默）
- 情感表达方式

### 5. 文化背景
- 主要文化背景
- 历史时代特征
- 地域特色
- 目标观众群体

### 6. 翻译挑战
- 可能的翻译难点
- 文化差异问题
- 特殊术语和典故
- 幽默和情感表达的转换

请以JSON格式回复，结构如下：
{{
  "chinese_title": "中文片名",
  "director": "导演名",
  "genres": ["类型1", "类型2"],
  "year": 年份,
  "time_period": "时代背景",
  "setting": "故事发生地",
  "themes": ["主题1", "主题2"],
  "tone": "整体基调",
  "pacing": "节奏",
  "target_audience": "目标观众",
  "cultural_context": "文化背景",
  "language_complexity": "语言复杂度",
  "emotional_intensity": "情感强度",
  "primary_style": "主要风格",
  "characters": {{
    "角色名": {{
      "personality_traits": ["性格特征1", "性格特征2"],
      "speech_style": "语言风格",
      "education_level": "教育水平",
      "emotional_range": ["情感特征"],
      "cultural_background": "文化背景",
      "age_group": "年龄组",
      "profession": "职业"
    }}
  }},
  "key_vocabulary": ["关键词1", "关键词2"],
  "cultural_references": ["文化引用1", "文化引用2"],
  "translation_challenges": ["翻译挑战1", "翻译挑战2"]
}}"""
        
        return prompt
    
    def _parse_analysis_response(self, title: str, year: Optional[int], response_text: str) -> MovieDNA:
        """解析AI分析响应"""
        
        try:
            # 尝试提取JSON
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                # 如果没有JSON，尝试解析文本
                data = self._parse_text_analysis(response_text)
            
            # 构建MovieDNA对象
            dna = MovieDNA(
                title=data.get("chinese_title", title),
                original_title=title,
                year=year or data.get("year", 2023),
                genres=self._parse_genres(data.get("genres", [])),
                primary_style=self._parse_style(data.get("primary_style", "philosophical")),
                themes=data.get("themes", []),
                tone=data.get("tone", "neutral"),
                pacing=data.get("pacing", "medium"),
                target_audience=data.get("target_audience", "general"),
                cultural_context=data.get("cultural_context", "western"),
                language_complexity=data.get("language_complexity", "medium"),
                emotional_intensity=data.get("emotional_intensity", "medium"),
                director=data.get("director"),
                time_period=data.get("time_period"),
                setting=data.get("setting"),
                key_vocabulary=set(data.get("key_vocabulary", [])),
                cultural_references=data.get("cultural_references", []),
                translation_challenges=data.get("translation_challenges", []),
                characters=self._parse_characters(data.get("characters", {}))
            )
            
            return dna
            
        except Exception as e:
            logger.error("解析AI分析响应失败", error=str(e))
            return MovieDNA(
                title=title,
                original_title=title,
                year=year or 2023,
                genres=[MovieGenre.DRAMA],
                primary_style=MovieStyle.PHILOSOPHICAL
            )
    
    def _parse_genres(self, genres_list: List[str]) -> List[MovieGenre]:
        """解析电影类型"""
        genre_mapping = {
            "动作": MovieGenre.ACTION,
            "喜剧": MovieGenre.COMEDY,
            "剧情": MovieGenre.DRAMA,
            "恐怖": MovieGenre.HORROR,
            "爱情": MovieGenre.ROMANCE,
            "科幻": MovieGenre.SCI_FI,
            "惊悚": MovieGenre.THRILLER,
            "动画": MovieGenre.ANIMATION,
            "纪录片": MovieGenre.DOCUMENTARY,
            "奇幻": MovieGenre.FANTASY,
            "悬疑": MovieGenre.MYSTERY,
            "冒险": MovieGenre.ADVENTURE,
            "犯罪": MovieGenre.CRIME,
            "家庭": MovieGenre.FAMILY,
            "音乐": MovieGenre.MUSICAL,
            "战争": MovieGenre.WAR,
            "西部": MovieGenre.WESTERN
        }
        
        result = []
        for genre in genres_list:
            if genre in genre_mapping:
                result.append(genre_mapping[genre])
        
        return result or [MovieGenre.DRAMA]
    
    def _parse_style(self, style_str: str) -> MovieStyle:
        """解析电影风格"""
        style_mapping = {
            "哲学思辨": MovieStyle.PHILOSOPHICAL,
            "轻松幽默": MovieStyle.HUMOROUS,
            "浪漫深情": MovieStyle.ROMANTIC,
            "黑暗深沉": MovieStyle.DARK,
            "励志向上": MovieStyle.INSPIRATIONAL,
            "怀旧温情": MovieStyle.NOSTALGIC,
            "讽刺幽默": MovieStyle.SARCASTIC,
            "史诗宏大": MovieStyle.EPIC,
            "私密细腻": MovieStyle.INTIMATE,
            "实验前卫": MovieStyle.EXPERIMENTAL
        }
        
        return style_mapping.get(style_str, MovieStyle.PHILOSOPHICAL)
    
    def _parse_characters(self, characters_data: Dict[str, Any]) -> Dict[str, CharacterProfile]:
        """解析角色信息"""
        characters = {}
        
        for name, char_data in characters_data.items():
            profile = CharacterProfile(
                name=name,
                personality_traits=char_data.get("personality_traits", []),
                speech_style=char_data.get("speech_style", "normal"),
                education_level=char_data.get("education_level", "medium"),
                emotional_range=char_data.get("emotional_range", []),
                cultural_background=char_data.get("cultural_background", "western"),
                age_group=char_data.get("age_group", "adult"),
                profession=char_data.get("profession")
            )
            characters[name] = profile
        
        return characters
    
    def _parse_text_analysis(self, text: str) -> Dict[str, Any]:
        """解析文本格式的分析结果"""
        # 简单的文本解析逻辑
        lines = text.split('\n')
        data = {}
        
        for line in lines:
            if '：' in line:
                key, value = line.split('：', 1)
                data[key.strip()] = value.strip()
        
        return data
    
    async def _cache_movie_dna(self, movie_id: str, dna: MovieDNA):
        """缓存电影DNA"""
        try:
            # 序列化DNA
            serialized = self._serialize_movie_dna(dna)
            
            # 缓存到Redis
            await self.cache_manager.set(
                f"movie_dna_{movie_id}",
                json.dumps(serialized),
                expire=86400 * 30  # 30天
            )
            
            # 更新知识库缓存
            knowledge_base_data = {
                movie_id: serialized for movie_id, dna in self._knowledge_base.items()
            }
            await self.cache_manager.set(
                "movie_knowledge_base",
                json.dumps(knowledge_base_data),
                expire=86400 * 7  # 7天
            )
            
        except Exception as e:
            logger.warning("缓存电影DNA失败", error=str(e))
    
    def _serialize_movie_dna(self, dna: MovieDNA) -> Dict[str, Any]:
        """序列化MovieDNA对象"""
        return {
            "title": dna.title,
            "original_title": dna.original_title,
            "year": dna.year,
            "genres": [genre.value for genre in dna.genres],
            "primary_style": dna.primary_style.value,
            "themes": dna.themes,
            "tone": dna.tone,
            "pacing": dna.pacing,
            "target_audience": dna.target_audience,
            "cultural_context": dna.cultural_context,
            "language_complexity": dna.language_complexity,
            "emotional_intensity": dna.emotional_intensity,
            "characters": {
                name: {
                    "name": char.name,
                    "personality_traits": char.personality_traits,
                    "speech_style": char.speech_style,
                    "education_level": char.education_level,
                    "emotional_range": char.emotional_range,
                    "cultural_background": char.cultural_background,
                    "age_group": char.age_group,
                    "profession": char.profession
                }
                for name, char in dna.characters.items()
            },
            "key_vocabulary": list(dna.key_vocabulary),
            "cultural_references": dna.cultural_references,
            "time_period": dna.time_period,
            "setting": dna.setting,
            "director": dna.director,
            "box_office": dna.box_office,
            "awards": dna.awards,
            "similar_movies": dna.similar_movies,
            "translation_challenges": dna.translation_challenges,
            "last_updated": dna.last_updated.isoformat()
        }
    
    def _deserialize_movie_dna(self, data: Dict[str, Any]) -> MovieDNA:
        """反序列化MovieDNA对象"""
        return MovieDNA(
            title=data["title"],
            original_title=data["original_title"],
            year=data["year"],
            genres=[MovieGenre(genre) for genre in data["genres"]],
            primary_style=MovieStyle(data["primary_style"]),
            themes=data["themes"],
            tone=data["tone"],
            pacing=data["pacing"],
            target_audience=data["target_audience"],
            cultural_context=data["cultural_context"],
            language_complexity=data["language_complexity"],
            emotional_intensity=data["emotional_intensity"],
            characters=self._parse_characters(data["characters"]),
            key_vocabulary=set(data["key_vocabulary"]),
            cultural_references=data["cultural_references"],
            time_period=data.get("time_period"),
            setting=data.get("setting"),
            director=data.get("director"),
            box_office=data.get("box_office"),
            awards=data.get("awards", []),
            similar_movies=data.get("similar_movies", []),
            translation_challenges=data.get("translation_challenges", []),
            last_updated=datetime.fromisoformat(data["last_updated"])
        )
    
    async def identify_movie_from_filename(self, filename: str) -> Optional[Tuple[str, int]]:
        """从文件名识别电影信息"""
        
        # 提取可能的标题和年份
        patterns = [
            r'(.+?)\s*\((\d{4})\)',  # Movie Title (2023)
            r'(.+?)\s*\[(\d{4})\]',  # Movie Title [2023]
            r'(.+?)\s*(\d{4})',      # Movie Title 2023
            r'(.+?)\s*BLURAY|BRRIP|WEBRIP|WEB-DL',  # Movie Title Quality
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                year_str = match.group(2) if len(match.groups()) > 1 else None
                
                # 清理标题
                title = re.sub(r'[._-]', ' ', title)
                title = re.sub(r'\s+(?:BluRay|BRRip|WEBRip|WEB-DL|1080p|720p|480p).*$', '', title, flags=re.IGNORECASE)
                
                year = int(year_str) if year_str and year_str.isdigit() else None
                return title, year
        
        return None
    
    def get_translation_style_guide(self, movie_dna: MovieDNA) -> str:
        """根据电影DNA生成翻译风格指南"""
        
        style_guide = f"""
## 电影翻译风格指南：《{movie_dna.title}》

### 电影特征
- **类型**: {', '.join([genre.value for genre in movie_dna.genres])}
- **风格**: {movie_dna.primary_style.value}
- **基调**: {movie_dna.tone}
- **目标观众**: {movie_dna.target_audience}
- **文化背景**: {movie_dna.cultural_context}

### 翻译策略
1. **整体风格**: 采用{movie_dna.primary_style.value}的翻译风格
2. **语言复杂度**: 保持{movie_dna.language_complexity}的复杂度
3. **情感表达**: 体现{movie_dna.emotional_intensity}的情感强度
4. **文化适配**: 针对{movie_dna.cultural_context}文化背景进行适配

### 角色语言特征
"""
        
        for char_name, profile in movie_dna.characters.items():
            style_guide += f"""
#### {char_name}
- **性格特征**: {', '.join(profile.personality_traits)}
- **语言风格**: {profile.speech_style}
- **教育水平**: {profile.education_level}
- **情感特征**: {', '.join(profile.emotional_range)}
- **文化背景**: {profile.cultural_background}
"""
        
        if movie_dna.translation_challenges:
            style_guide += f"""
### 翻译注意事项
{chr(10).join(f'- {challenge}' for challenge in movie_dna.translation_challenges)}
"""
        
        return style_guide
    
    async def get_character_context(self, movie_dna: MovieDNA, character_name: str) -> Optional[CharacterProfile]:
        """获取角色上下文信息"""
        return movie_dna.characters.get(character_name)
    
    async def search_similar_movies(self, movie_dna: MovieDNA) -> List[str]:
        """搜索相似电影"""
        # 基于类型、风格、主题等特征搜索相似电影
        similar = []
        
        # 简单的相似度匹配逻辑
        for movie_id, other_dna in self._knowledge_base.items():
            if movie_id == f"{movie_dna.original_title}_{movie_dna.year}":
                continue
            
            # 计算类型重叠度
            genre_overlap = len(set(movie_dna.genres) & set(other_dna.genres))
            if genre_overlap >= 2:
                similar.append(other_dna.title)
        
        return similar[:5]  # 返回前5个相似电影


# 全局电影知识引擎实例
movie_engine = MovieKnowledgeEngine()