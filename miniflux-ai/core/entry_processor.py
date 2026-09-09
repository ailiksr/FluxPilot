import threading
import traceback
from typing import Any

from cachetools import TTLCache
from common import config
from common.exceptions import LLMResponseError
from common.logger import get_logger
from common.models import Agent, AgentResult

from core.content_helper import (
    build_ordered_content,
    parse_entry_content,
    to_html,
    rewrite_image_urls,
    to_markdown,
)
from core.digest_generator import save_summary
from core.llm_client import chat_completion
from core.miniflux_client import get_miniflux_client
from core.rule_matcher import match_rules
from core.prompt_schema import ENTRY_PROMPT_SCHEMA
from core.article_scorer_v3 import judge_and_score, SCORE_VERSION
from core.score_calibration_v23 import score as calibrated_score
from core.score_store import save_result, get_cached, migrate_entry_hash, content_hash
from core.feed_policy import apply_weight, get_weight

logger = get_logger(__name__)

# Entry processing cache to avoid duplicate processing
_ENTRY_CACHE_LOCK = threading.Lock()
_ENTRY_CACHE = TTLCache[int, bool](maxsize=1000, ttl=300)


def process_entry(entry: dict[str, Any]) -> dict[str, AgentResult]:
    """
    Process a single entry through all configured agents

    Args:
        entry: Entry dictionary to process

    Returns:
        Dictionary of agent_name: agent_result
    """
    try:
        logger.debug_entry(entry, message="Starting processing")

        # Parse entry content once to get original content and existing agent results
        original_content, existing_agent_contents = parse_entry_content(
            entry["content"]
        )

        if not original_content.strip():
            logger.debug_entry(entry, message="Entry content is empty, skipping")
            return {}

        original_entry = entry.copy()
        original_entry["content"] = original_content

        # AI value scoring is intentionally read-only: results go to the worker data store only.
        scoring = {}
        rm = {}
        is_fast_path = False
        try:
            ch = content_hash(original_entry["title"], original_content)
            cached = get_cached(original_entry["id"], ch) or migrate_entry_hash(original_entry["id"], ch)
            if cached and cached.get("score_version") == SCORE_VERSION:
                scoring = {"score": cached.get("recommend_score", cached.get("score")), "base_score": cached.get("base_score", cached.get("score")), "feed_weight": cached.get("feed_weight", 100), "recommend_score": cached.get("recommend_score", cached.get("score")), "judge": cached.get("judge"), "reason": cached.get("reason"), "confidence": cached.get("confidence"), "cached": True, "score_version": SCORE_VERSION, "pipeline_trace": cached.get("pipeline_trace")}
                logger.info_entry(original_entry, message=f"AI score cache hit; skipping LLM (score={scoring.get('score')}, version={SCORE_VERSION})")
            elif cached and isinstance(cached.get("judge"), dict):
                judge = cached["judge"]
                base_score = calibrated_score(judge)
                feed_weight = get_weight(original_entry.get("feed_id"))
                scoring = {"score": apply_weight(base_score, original_entry.get("feed_id")), "base_score": base_score, "feed_weight": feed_weight, "recommend_score": apply_weight(base_score, original_entry.get("feed_id")), "judge": judge, "reason": cached.get("reason"), "confidence": cached.get("confidence"), "cached": True, "score_version": SCORE_VERSION, "calibrated_from": cached.get("score_version"), "pipeline_trace": cached.get("pipeline_trace")}
                save_result(original_entry["id"], original_entry["title"], scoring, original_entry.get("feed_id"), ch)
                logger.info_entry(original_entry, message=f"AI score recalibrated from cached Judge (score={scoring.get('score')}, version={SCORE_VERSION}); skipping LLM")
            else:
                # 1. Pre-LLM Fast-Path Heuristic Evaluation (0 token cost, <1ms)
                from core.fast_filter import evaluate_fast_path
                from core.rules_store import load_rules, match_article_rules
                current_rules = load_rules()
                triggered, fast_scoring = evaluate_fast_path(original_entry, original_content, current_rules, SCORE_VERSION)
                if triggered and fast_scoring:
                    is_fast_path = True
                    scoring = fast_scoring
                    save_result(original_entry["id"], original_entry["title"], scoring, original_entry.get("feed_id"), ch)
                    logger.info_entry(original_entry, message=f"⚡ Fast-path heuristic triggered (0 tokens used): {scoring.get('reason')}")
                else:
                    scoring = judge_and_score(original_entry["title"], original_content)
                    if scoring.get("score") is not None:
                        scoring["base_score"] = scoring["score"]
                        scoring["feed_weight"] = get_weight(original_entry.get("feed_id"))
                        scoring["recommend_score"] = apply_weight(scoring["base_score"], original_entry.get("feed_id"))
                        scoring["score"] = scoring["recommend_score"]
                        save_result(original_entry["id"], original_entry["title"], scoring, original_entry.get("feed_id"), ch)
                        logger.info_entry(original_entry, message=f"AI score recorded: {scoring.get('score')}")
                    else:
                        logger.info_entry(original_entry, message="AI returned no valid score; preserving previous valid score")

            # Native Reactflux / Miniflux integration: auto-star and auto-silence with rule matching
            if scoring.get("score") is not None:
                try:
                    from core.rules_store import load_rules, match_article_rules
                    from core.auto_actions import auto_star_entry, auto_silence_entry
                    current_rules = load_rules()
                    row_for_rules = {"title": original_entry.get("title"), "judge": scoring.get("judge") or {}, "content": original_content}
                    rm = match_article_rules(row_for_rules, current_rules)

                    if current_rules.get("auto_silence", True) and (is_fast_path or rm.get("muted") or scoring["score"] < 25):
                        auto_silence_entry(original_entry["id"], scoring.get("score"), is_muted=rm.get("muted") or is_fast_path, mute_reasons=rm.get("mute_reasons") or [scoring.get("reason", "低质文章")], entry_dict=original_entry)
                    elif current_rules.get("auto_star", True) and (rm.get("boosted") or scoring["score"] >= 75):
                        auto_star_entry(original_entry["id"], scoring.get("score"), is_boosted=rm.get("boosted"), entry_dict=original_entry)
                except Exception as act_exc:
                    logger.warning_entry(original_entry, message=f"Native auto-actions failed: {act_exc}")

        except Exception as score_exc:
            logger.error_entry(original_entry, message=f"AI scoring failed (entry processing continues): {score_exc}")

        if existing_agent_contents:
            logger.debug_entry(
                original_entry,
                message=f"Found existing agent contents: {list(existing_agent_contents.keys())}",
            )

        # process entry with config.agents excluding keys in existing agent contents
        new_agents = {
            k: v for k, v in config.agents.items() if k not in existing_agent_contents
        }

        # Milestone 1 & 2: If fast-path muted, skip LLM summary agent completely (100% token savings!)
        if is_fast_path:
            logger.info_entry(original_entry, message="⚡ Fast-path muted; skipping LLM agent processing")
            new_agent_results = {}
            from core.auto_actions import build_decision_inspector
            inspector_html = build_decision_inspector(scoring, rm, scoring.get("pipeline_trace"), original_entry["id"])
            fast_notice = (
                f'{inspector_html}'
                f'<div class="ai-summary" style="background:#fff1f0;border-left:4px solid #f04438;'
                f'padding:8px 12px;border-radius:6px;font-size:12px;color:#b42318;margin-bottom:12px;">'
                f'<b>🗑️ [前置熔断自动已读]</b> 本文已由本地启发式规则快速判定并静音沉底，跳过大模型调用以节约算力。'
                f'</div>'
            )
            new_agent_contents = {"summary": fast_notice}
        else:
            # Milestone 2: Adaptive Two-Tier AI Summary Prompt
            if "summary" in new_agents and scoring.get("score", 0) >= 75:
                from copy import deepcopy
                deep_agent = deepcopy(new_agents["summary"])
                deep_agent.prompt = (
                    "对本文进行高价值深度萃取，使用清晰简洁的中文输出以下结构化内容（客观准确，简明有力）：\n"
                    "- **🎯 核心命题**：文章试图解答的核心痛点或争议（1-2句）\n"
                    "- **🔍 核心论据与推演**：作者的关键事实依据与逻辑推演（分2-3点，分行罗列）\n"
                    "- **💡 关键启示**：对读者的思维模型或实操有何启发（1句）"
                )
                new_agents["summary"] = deep_agent

            new_agent_results = _process_entry_with_agents(original_entry, new_agents)
            new_agent_contents = {
                k: v.content for k, v in new_agent_results.items() if v.is_success
            }

            # Embed AI Decision Inspector at top of summary for full reader traceability
            if scoring.get("score") is not None:
                try:
                    from core.auto_actions import build_decision_inspector
                    inspector_html = build_decision_inspector(scoring, rm, scoring.get("pipeline_trace"), original_entry["id"])
                    if "summary" in new_agent_contents:
                        new_agent_contents["summary"] = inspector_html + new_agent_contents["summary"]
                    elif inspector_html:
                        new_agent_contents["summary"] = inspector_html
                except Exception:
                    pass

        # Combine existing and new agent contents, then update entry
        if new_agent_contents:
            all_agent_contents = {**existing_agent_contents, **new_agent_contents}
            ordered_content = build_ordered_content(
                all_agent_contents, rewrite_image_urls(original_content)
            )

            get_miniflux_client().update_entry(entry["id"], content=ordered_content)
            logger.info_entry(
                entry,
                message=(
                    f"Updated successfully with new agent contents: "
                    f"{list(new_agent_contents.keys())}"
                ),
            )
        else:
            logger.debug_entry(
                entry, message="No new agent contents generated, entry unchanged"
            )

        return new_agent_results

    except Exception as e:
        logger.error_entry(entry, message=f"Processing failed: {e}")
        raise


def _process_entry_with_agents(
    entry: dict[str, Any], agents: dict[str, Agent]
) -> dict[str, AgentResult]:
    """
    Process entry through all applicable agents

    Args:
        entry: Entry dictionary to process
        agents: Dictionary of agent_name: Agent dataclass

    Returns:
        Dictionary of agent_name: agent_result
    """
    if not agents:
        return {}

    # Check if entry was already processed (cache check)
    entry_id = entry["id"]
    with _ENTRY_CACHE_LOCK:
        if entry_id in _ENTRY_CACHE:
            logger.debug_entry(
                entry, message="Entry already processed (cache hit), skipping"
            )
            return {}
        _ENTRY_CACHE[entry_id] = True

    logger.debug_entry(
        entry, message=f"Processing entry with agents: {list(agents.keys())}"
    )
    logger.debug_entry(
        entry,
        message="Processing entry content",
        include_title=False,
        include_content=True,
    )

    agent_results: dict[str, AgentResult] = {}
    # config.agents is ordered, required Python 3.7+
    for agent_name, agent in agents.items():
        agent_results[agent_name] = _process_with_single_agent(agent_name, agent, entry)

    return agent_results


def _process_with_single_agent(
    agent_name: str, agent: Agent, entry: dict[str, Any]
) -> AgentResult:
    """
    Process entry with a single agent

    Args:
        agent_name: Name of the agent
        agent: Agent dataclass instance
        entry: Entry dictionary to process

    Returns:
        AgentResult with status and content/error
    """
    # Check if entry matches agent's rules
    if not match_rules(entry, agent.allow_rules, agent.deny_rules):
        logger.debug_entry(
            entry, agent_name=agent_name, message="Filtered out by rules"
        )
        return AgentResult.filtered()

    logger.debug_entry(entry, agent_name=agent_name, message="Starting processing")

    try:
        agent_content = _get_agent_content(agent_name, agent, entry)
        logger.info_entry(
            entry,
            agent_name=agent_name,
            message=f"Agent output generated ({len(agent_content)} chars)",
            include_title=True,
        )

        if config.digest_schedule and agent_name == "summary":
            # save summary to file for AI digest feature
            save_summary(entry, agent_content)

        formatted_content = _format_agent_content(agent, agent_content)
        logger.debug_entry(
            entry,
            agent_name=agent_name,
            message=f"Formatted content: {formatted_content}",
            include_title=True,
        )

        return AgentResult.success(formatted_content)
    except LLMResponseError as e:
        logger.error_entry(entry, agent_name=agent_name, message=f"LLM error: {e}")
        return AgentResult.from_error(e, message=str(e))
    except Exception as e:
        logger.error_entry(
            entry, agent_name=agent_name, message=f"Processing failed: {e}"
        )
        logger.error(traceback.format_exc())
        return AgentResult.from_error(e, message=str(e))


def _get_agent_content(agent_name: str, agent: Agent, entry: dict[str, Any]) -> str:
    """
    Get processed content from LLM for a specific agent

    Args:
        agent_name: Name of the agent
        agent: Agent dataclass instance
        entry: Entry dictionary to process

    Returns:
        str: Processed content from LLM
    """
    title = entry["title"]
    content_markdown = to_markdown(entry["content"])

    user_prompt = ENTRY_PROMPT_SCHEMA.render(title=title, content=content_markdown)
    prompts = [
        ("system", ENTRY_PROMPT_SCHEMA.format_description),
        ("system", agent.prompt),
        ("user", user_prompt),
    ]

    logger.debug_entry(
        entry,
        agent_name=agent_name,
        message=f"LLM request sent ({len(prompts)} messages, {sum(len(text) for _, text in prompts)} chars)",
    )

    agent_content = chat_completion(prompts)

    logger.debug_entry(
        entry,
        agent_name=agent_name,
        message=f"LLM response received ({len(agent_content)} chars)",
    )
    return agent_content


def _format_agent_content(agent: Agent, agent_content: str) -> str:
    """
    Format agent content based on style configuration

    Args:
        agent: Agent dataclass instance
        agent_content: Raw content from LLM

    Returns:
        Formatted content string
    """
    template = agent.template
    html_content = to_html(agent_content)

    if template:
        return template.replace("{content}", html_content)
    else:
        return html_content
