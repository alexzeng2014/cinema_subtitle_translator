"""
上下文感知翻译引擎
动态生成提示词，保持角色语言一致性和情感连贯性
"""

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
import structlog

from ..api.deepseek_client import DeepSeekClient, ChatMessage
from ..intelligence.movie_knowledge import MovieDNA, CharacterProfile, movie_engine
from ..security.config import get_config
from ..storage.cache_manager import cache_manager

logger = structlog.get_logger(__name__)


class TranslationStyle(Enum):
    """翻译风格枚举"""
    LITERAL = "直译"  # 保持原文结构
    CULTURAL = "文化适配"  # 深度文化适配
    CREATIVE = "创意翻译"  # 创意性翻译
    BALANCED = "平衡"  # 平衡准确性和流畅度
    PROFESSIONAL = "专业"  # 专业字幕风格
    CASUAL = "口语化"  # 口语化风格


class QualityLevel(Enum):
    """质量等级枚举"""
    BASIC = "基础"
    STANDARD = "标准"
    HIGH = "高"
    PREMIUM = "精品"


@dataclass
class SubtitleLine:
    """字幕行"""
    index: int
    start_time: str
    end_time: str
    text: str
    character: Optional[str] = None
    context: Optional[str] = None
    translation: Optional[str] = None
    quality_score: float = 0.0
    confidence: float = 0.0


@dataclass
class TranslationContext:
    """翻译上下文"""
    movie_dna: MovieDNA
    current_scene: str
    previous_lines: List[SubtitleLine]
    next_lines: List[SubtitleLine]
    character_dialogue_history: Dict[str, List[str]]
    cultural_references: List[str]
    time_period_context: str
    emotional_tone: str
    style_preferences: Dict[str, Any]


@dataclass
class TranslationResult:
    """翻译结果"""
    original_text: str
    translated_text: str
    confidence: float
    quality_score: float
    style_score: float
    cultural_score: float
    character_score: float
    suggestions: List[str]
    alternative_translations: List[str]


class ContextAwareTranslator:
    """上下文感知翻译引擎"""
    
    def __init__(self):
        self.config = get_config()
        self.deepseek_client = DeepSeekClient()
        self.cache_manager = cache_manager
        self.movie_engine = movie_engine
        
        # 翻译统计
        self.translation_stats = {
            "total_lines": 0,
            "avg_quality": 0.0,
            "avg_confidence": 0.0,
            "style_distribution": {},
            "cache_hits": 0
        }
    
    async def translate_subtitle(
        self,
        subtitle: SubtitleLine,
        context: TranslationContext,
        style: TranslationStyle = TranslationStyle.BALANCED,
        quality_level: QualityLevel = QualityLevel.HIGH
    ) -> TranslationResult:
        """翻译单条字幕"""
        
        # 生成缓存键
        cache_key = self._generate_cache_key(subtitle, context, style, quality_level)
        
        # 检查缓存
        cached_result = await self.cache_manager.get(cache_key)
        if cached_result:
            self.translation_stats["cache_hits"] += 1
            return TranslationResult(**cached_result)
        
        # 构建翻译提示词
        prompt = self._build_translation_prompt(subtitle, context, style, quality_level)
        
        try:
            # 调用AI翻译
            response = await self.deepseek_client.chat_completion(
                messages=[
                    {"role": "system", "content": self._get_system_prompt(context)},
                    {"role": "user", "content": prompt}
                ],
                temperature=self._get_temperature(style, quality_level),
                max_tokens=500
            )
            
            # 解析翻译结果
            result = self._parse_translation_response(
                response.choices[0].message.content,
                subtitle,
                style,
                quality_level
            )
            
            # 缓存结果
            await self.cache_manager.set(
                cache_key,
                result.__dict__,
                expire=86400 * 7  # 7天
            )
            
            # 更新统计
            self._update_stats(result)
            
            return result
            
        except Exception as e:
            logger.error("翻译失败", error=str(e), subtitle=subtitle.text)
            # 返回基础翻译结果
            return TranslationResult(
                original_text=subtitle.text,
                translated_text=subtitle.text,  # 原文返回
                confidence=0.0,
                quality_score=0.0,
                style_score=0.0,
                cultural_score=0.0,
                character_score=0.0,
                suggestions=[],
                alternative_translations=[]
            )
    
    def _get_system_prompt(self, context: TranslationContext) -> str:
        """获取系统提示词"""
        
        movie_info = context.movie_dna
        style_guide = self.movie_engine.get_translation_style_guide(movie_info)
        
        system_prompt = f"""你是一位专业的电影字幕翻译专家，精通中英双语和文化转换。

## 核心翻译原则
1. **情感传递优先**: 确保翻译能够传达原文的情感强度和语气
2. **文化适配**: 将西方文化背景转换为中文观众能理解的表达
3. **角色一致性**: 保持每个角色独特的语言风格和说话方式
4. **上下文连贯**: 确保对话在电影整体语境中自然流畅

## 电影背景
{style_guide}

## 翻译要求
- 保持口语化，避免书面语
- 控制字幕长度，适合阅读速度
- 处理俚语、习语和文化典故
- 保持幽默感和戏剧效果
- 注意角色性格特征

请提供高质量的字幕翻译，严格按照JSON格式回复。"""
        
        return system_prompt
    
    def _build_translation_prompt(
        self,
        subtitle: SubtitleLine,
        context: TranslationContext,
        style: TranslationStyle,
        quality_level: QualityLevel
    ) -> str:
        """构建翻译提示词"""
        
        # 获取角色信息
        character_profile = None
        if subtitle.character:
            character_profile = context.movie_dna.characters.get(subtitle.character)
        
        # 构建上下文信息
        context_info = self._build_context_info(subtitle, context, character_profile)
        
        # 构建风格要求
        style_requirements = self._build_style_requirements(style, quality_level)
        
        prompt = f"""请翻译以下电影字幕：

## 原文
**文本**: "{subtitle.text}"
**角色**: {subtitle.character or "未知"}
**时间**: {subtitle.start_time} - {subtitle.end_time}

## 上下文信息
{context_info}

## 翻译风格要求
{style_requirements}

## 输出格式
请以JSON格式回复，包含以下字段：
{{
  "translation": "最佳翻译结果",
  "confidence": 0.95,
  "quality_score": 0.9,
  "style_score": 0.85,
  "cultural_score": 0.8,
  "character_score": 0.9,
  "suggestions": ["建议1", "建议2"],
  "alternative_translations": ["备选翻译1", "备选翻译2"],
  "explanation": "翻译说明"
}}

## 特殊要求
1. 翻译要符合角色性格特征
2. 保持情感表达的准确性
3. 处理文化差异和习语
4. 确保在当前场景中的连贯性
5. 控制翻译长度，适合字幕显示

请开始翻译："""
        
        return prompt
    
    def _build_context_info(
        self,
        subtitle: SubtitleLine,
        context: TranslationContext,
        character_profile: Optional[CharacterProfile]
    ) -> str:
        """构建上下文信息"""
        
        context_parts = []
        
        # 电影信息
        context_parts.append(f"**电影**: {context.movie_dna.title} ({context.movie_dna.year})")
        context_parts.append(f"**类型**: {', '.join([g.value for g in context.movie_dna.genres])}")
        context_parts.append(f"**风格**: {context.movie_dna.primary_style.value}")
        context_parts.append(f"**当前场景**: {context.current_scene}")
        
        # 角色信息
        if character_profile:
            context_parts.append(f"**角色特征**: {', '.join(character_profile.personality_traits)}")
            context_parts.append(f"**语言风格**: {character_profile.speech_style}")
            context_parts.append(f"**教育水平**: {character_profile.education_level}")
        
        # 对话历史
        if subtitle.character and subtitle.character in context.character_dialogue_history:
            history = context.character_dialogue_history[subtitle.character][-3:]  # 最近3句
            if history:
                context_parts.append(f"**角色历史对话**:")
                for i, line in enumerate(history, 1):
                    context_parts.append(f"  {i}. {line}")
        
        # 前后文
        if context.previous_lines:
            context_parts.append(f"**前文**: {context.previous_lines[-1].text if context.previous_lines else '无'}")
        if context.next_lines:
            context_parts.append(f"**后文**: {context.next_lines[0].text if context.next_lines else '无'}")
        
        # 情感和文化
        context_parts.append(f"**情感基调**: {context.emotional_tone}")
        if context.cultural_references:
            context_parts.append(f"**文化引用**: {', '.join(context.cultural_references)}")
        
        return "\n".join(context_parts)
    
    def _build_style_requirements(self, style: TranslationStyle, quality_level: QualityLevel) -> str:
        """构建风格要求"""
        
        style_descriptions = {
            TranslationStyle.LITERAL: "保持原文结构，忠实于原文表达",
            TranslationStyle.CULTURAL: "深度文化适配，让中文观众有相同的观影体验",
            TranslationStyle.CREATIVE: "创意翻译，在保持原意的基础上进行艺术化表达",
            TranslationStyle.BALANCED: "平衡准确性和流畅度，追求最佳观影体验",
            TranslationStyle.PROFESSIONAL: "专业字幕风格，符合行业标准",
            TranslationStyle.CASUAL: "口语化风格，贴近日常对话"
        }
        
        quality_requirements = {
            QualityLevel.BASIC: "基础翻译，确保基本意思准确",
            QualityLevel.STANDARD: "标准翻译，兼顾准确性和流畅度",
            QualityLevel.HIGH: "高质量翻译，注重文化适配和角色一致性",
            QualityLevel.PREMIUM: "精品翻译，追求艺术性和情感传递的完美"
        }
        
        return f"""**翻译风格**: {style_descriptions[style]}
**质量等级**: {quality_requirements[quality_level]}
**特殊要求**: 
- 保持{style.value}的翻译风格
- 达到{quality_level.value}的质量标准
- 确保翻译的准确性和可读性
- 注重文化差异的处理"""
    
    def _get_temperature(self, style: TranslationStyle, quality_level: QualityLevel) -> float:
        """获取翻译温度参数"""
        
        base_temp = {
            TranslationStyle.LITERAL: 0.1,
            TranslationStyle.CULTURAL: 0.4,
            TranslationStyle.CREATIVE: 0.7,
            TranslationStyle.BALANCED: 0.3,
            TranslationStyle.PROFESSIONAL: 0.2,
            TranslationStyle.CASUAL: 0.5
        }
        
        quality_adjustment = {
            QualityLevel.BASIC: 0.1,
            QualityLevel.STANDARD: 0.0,
            QualityLevel.HIGH: -0.1,
            QualityLevel.PREMIUM: -0.2
        }
        
        temp = base_temp[style] + quality_adjustment[quality_level]
        return max(0.0, min(1.0, temp))
    
    def _parse_translation_response(
        self,
        response_text: str,
        subtitle: SubtitleLine,
        style: TranslationStyle,
        quality_level: QualityLevel
    ) -> TranslationResult:
        """解析翻译响应"""
        
        try:
            # 尝试提取JSON
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                # 如果没有JSON，使用简单解析
                data = self._parse_simple_response(response_text)
            
            return TranslationResult(
                original_text=subtitle.text,
                translated_text=data.get("translation", subtitle.text),
                confidence=data.get("confidence", 0.8),
                quality_score=data.get("quality_score", 0.8),
                style_score=data.get("style_score", 0.8),
                cultural_score=data.get("cultural_score", 0.8),
                character_score=data.get("character_score", 0.8),
                suggestions=data.get("suggestions", []),
                alternative_translations=data.get("alternative_translations", [])
            )
            
        except Exception as e:
            logger.error("解析翻译响应失败", error=str(e), response=response_text[:200])
            # 返回基础结果
            return TranslationResult(
                original_text=subtitle.text,
                translated_text=subtitle.text,
                confidence=0.0,
                quality_score=0.0,
                style_score=0.0,
                cultural_score=0.0,
                character_score=0.0,
                suggestions=[],
                alternative_translations=[]
            )
    
    def _parse_simple_response(self, response_text: str) -> Dict[str, Any]:
        """简单解析响应"""
        lines = response_text.split('\n')
        
        # 查找翻译结果
        translation = subtitle.text
        for line in lines:
            if '翻译' in line or 'translation' in line.lower():
                # 提取引号内的内容
                import re
                quotes = re.findall(r'"([^"]*)"', line)
                if quotes:
                    translation = quotes[0]
                    break
        
        return {
            "translation": translation,
            "confidence": 0.7,
            "quality_score": 0.7,
            "style_score": 0.7,
            "cultural_score": 0.7,
            "character_score": 0.7,
            "suggestions": [],
            "alternative_translations": []
        }
    
    def _generate_cache_key(
        self,
        subtitle: SubtitleLine,
        context: TranslationContext,
        style: TranslationStyle,
        quality_level: QualityLevel
    ) -> str:
        """生成缓存键"""
        
        key_parts = [
            subtitle.text,
            subtitle.character or "none",
            context.movie_dna.original_title,
            str(context.movie_dna.year),
            style.value,
            quality_level.value,
            context.current_scene
        ]
        
        import hashlib
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _update_stats(self, result: TranslationResult):
        """更新翻译统计"""
        self.translation_stats["total_lines"] += 1
        
        # 更新平均质量
        current_avg = self.translation_stats["avg_quality"]
        total_lines = self.translation_stats["total_lines"]
        self.translation_stats["avg_quality"] = (
            (current_avg * (total_lines - 1) + result.quality_score) / total_lines
        )
        
        # 更新平均置信度
        current_conf = self.translation_stats.get("avg_confidence", 0.0)
        self.translation_stats["avg_confidence"] = (
            (current_conf * (total_lines - 1) + result.confidence) / total_lines
        )
    
    async def translate_batch(
        self,
        subtitles: List[SubtitleLine],
        context: TranslationContext,
        style: TranslationStyle = TranslationStyle.BALANCED,
        quality_level: QualityLevel = QualityLevel.HIGH,
        batch_size: int = None
    ) -> List[TranslationResult]:
        """批量翻译字幕"""
        
        if batch_size is None:
            batch_size = self.config.performance.batch_size
        
        results = []
        
        # 分批处理
        for i in range(0, len(subtitles), batch_size):
            batch = subtitles[i:i + batch_size]
            
            # 并行翻译
            tasks = []
            for subtitle in batch:
                task = self.translate_subtitle(subtitle, context, style, quality_level)
                tasks.append(task)
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.error("批量翻译中的单条翻译失败", error=str(result))
                    # 创建默认结果
                    subtitle = batch[j]
                    fallback_result = TranslationResult(
                        original_text=subtitle.text,
                        translated_text=subtitle.text,
                        confidence=0.0,
                        quality_score=0.0,
                        style_score=0.0,
                        cultural_score=0.0,
                        character_score=0.0,
                        suggestions=[],
                        alternative_translations=[]
                    )
                    results.append(fallback_result)
                else:
                    results.append(result)
        
        return results
    
    def get_translation_stats(self) -> Dict[str, Any]:
        """获取翻译统计信息"""
        return self.translation_stats.copy()
    
    async def optimize_translation(
        self,
        result: TranslationResult,
        feedback: str,
        context: TranslationContext
    ) -> TranslationResult:
        """基于反馈优化翻译"""
        
        optimization_prompt = f"""基于以下反馈优化翻译：

## 原文
{result.original_text}

## 当前翻译
{result.translated_text}

## 用户反馈
{feedback}

## 上下文
电影: {context.movie_dna.title}
场景: {context.current_scene}

请提供改进后的翻译，并解释改进原因。"""

        try:
            response = await self.deepseek_client.chat_completion(
                messages=[
                    {"role": "system", "content": "你是专业的字幕翻译优化专家。"},
                    {"role": "user", "content": optimization_prompt}
                ],
                temperature=0.3,
                max_tokens=300
            )
            
            # 解析优化结果
            optimized_text = response.choices[0].message.content
            
            # 更新结果
            result.translated_text = optimized_text
            result.quality_score = min(1.0, result.quality_score + 0.1)
            result.suggestions.append(f"基于反馈优化: {feedback}")
            
            return result
            
        except Exception as e:
            logger.error("翻译优化失败", error=str(e))
            return result


# 全局翻译器实例
translator = ContextAwareTranslator()