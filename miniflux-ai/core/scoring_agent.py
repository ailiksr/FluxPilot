import json
import re
from typing import Any

from core.llm_client import chat_completion
from core.score_schema import ArticleScore, validate_score

SYSTEM = """你是 RSS 文章价值评估器。只输出一个合法 JSON 对象，不要 Markdown，不要解释文字。\n评分 0-10，confidence 0-1。value_score 是综合判断，不要机械平均。"""

PROMPT = """请评估下面文章，只返回 JSON。\n字段必须完整：value_score, information_density, timeliness, originality, depth, relevance, category, reason, confidence。\nvalue_score、各维度评分为数字，不要字符串。\n\n标题：{title}\n\n正文：{content}"""


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("LLM did not return a JSON object")
    obj = json.loads(match.group(0))
    if not isinstance(obj, dict):
        raise ValueError("extracted JSON is not an object")
    return obj


def score_article(title: str, content: str, retries: int = 1) -> ArticleScore:
    prompts = [("system", SYSTEM), ("user", PROMPT.format(title=title, content=content))]
    last_error = None
    for attempt in range(retries + 1):
        try:
            raw = chat_completion(prompts, temperature=0, retries=1)
            return validate_score(_extract_json(raw))
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                prompts.append(("system", "上一次输出无法通过 JSON Schema 校验。请重新输出严格合法的 JSON 对象，不要 Markdown。"))
    raise ValueError(f"score validation failed after retry: {last_error}")
