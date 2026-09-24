import os
import json
import re
from openai import OpenAI

_client = None


def get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("未找到环境变量 DEEPSEEK_API_KEY")
        _client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    return _client


def _extract_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _call(prompt, system="你是生物化学考研辅导老师，只返回 JSON。"):
    client = get_client()
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=800,
    )
    return resp.choices[0].message.content


# ==================== AI 错因诊断（三道） ====================

DIAG_SUMMARY = """学生做错了一道生物化学考研真题。

【题目】{stem}
【答案】{answer}
【知识点】{kp_text}
【回忆自评】{self_rating}
【错因】{error_type}

只返回 JSON，不要多余文字：
{{
  "error_analysis": "100字内分析为什么错",
  "weak_points": ["薄弱知识点1", "薄弱知识点2", "薄弱知识点3"]
}}"""

DIAG_TEACHING = """学生错题：
【题目】{stem}
【答案】{answer}
【知识点】{kp_text}

只返回 JSON：
{{
  "explanation": "300字内以老师口吻讲透这道题涉及的原理",
  "memory_tips": "100字内记忆技巧（口诀/对比/联想）"
}}"""

DIAG_LINK = """学生错题：
【题目】{stem}
【知识点】{kp_text}

只返回 JSON：
{{
  "confused_with": ["容易混淆的概念1", "概念2"],
  "similar_kps": ["相近知识点1", "相近知识点2", "相近知识点3"]
}}"""


def diagnose_summary(stem, answer, kp_text, self_rating, error_type):
    prompt = DIAG_SUMMARY.format(
        stem=stem, answer=answer or "（无）", kp_text=kp_text or "（无）",
        self_rating=self_rating or "未记录", error_type=error_type or "未选择",
    )
    try:
        return _extract_json(_call(prompt))
    except Exception as e:
        return {"error_analysis": f"（解析失败：{e}）"}


def diagnose_teaching(stem, answer, kp_text):
    prompt = DIAG_TEACHING.format(
        stem=stem, answer=answer or "（无）", kp_text=kp_text or "（无）",
    )
    try:
        return _extract_json(_call(prompt))
    except Exception as e:
        return {"explanation": f"（解析失败：{e}）", "memory_tips": ""}


def diagnose_link(stem, kp_text):
    prompt = DIAG_LINK.format(stem=stem, kp_text=kp_text or "（无）")
    try:
        return _extract_json(_call(prompt))
    except Exception as e:
        return {"confused_with": [], "similar_kps": []}


# ==================== AI 老师（全局） ====================

OVERALL_PROMPT = """你是一位考研辅导老师，正在给一位学生做整体学习状态诊断。

【学生当前数据】
{summary}

【你上次给这位学生的建议（如果有）】
{last_advice}

请综合分析，只返回 JSON：
{{
  "overall": "整体状态概述，80字内",
  "weak_chapters": ["薄弱章节1", "薄弱章节2"],
  "weak_kps": ["薄弱知识点1", "2", "3"],
  "suggestions": ["建议1（30字内）", "建议2", "建议3"],
  "next_focus": "接下来一周重点复习方向，50字内"
}}"""


def analyze_overall(summary_text, last_advice_text=""):
    prompt = OVERALL_PROMPT.format(
        summary=summary_text,
        last_advice=last_advice_text or "（无，第一次分析）",
    )
    try:
        return _extract_json(_call(prompt))
    except Exception as e:
        return {"overall": f"（解析失败：{e}）"}