import re
import warnings

import mistune
try:
    import tiktoken
except Exception:  # pragma: no cover - startup must not depend on network availability
    tiktoken = None
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
from common import config
from markdownify import markdownify as md

MARKER = '<a href="#mfai-{0}" id="mfai-{0}"></a>'
MARKER_PATTERN = r'<a\s+href="#mfai-([^"]+)"\s+id="mfai-[^"]+"[^>]*></a>'
_LEGACY_MARKER_PATTERN = r'<div data-ai-agent="([^"]+)" style="display: none;"></div>'

_TIKTOKEN_ENCODER = None
_CJK_CHAR_PATTERN = re.compile(
    r"[\u2e80-\u2fff\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
)

def _token_count(text: str) -> int:
    """Count tokens when the local tiktoken model is available; otherwise use a stable fallback."""
    global _TIKTOKEN_ENCODER
    if tiktoken is not None:
        try:
            if _TIKTOKEN_ENCODER is None:
                _TIKTOKEN_ENCODER = tiktoken.get_encoding("cl100k_base")
            return len(_TIKTOKEN_ENCODER.encode(text, disallowed_special=()))
        except Exception:
            pass
    # Count CJK characters individually; grouping all text by byte length badly
    # underestimates Chinese articles when the BPE data is unavailable offline.
    if not text:
        return 0
    cjk_count = len(_CJK_CHAR_PATTERN.findall(text))
    remaining = _CJK_CHAR_PATTERN.sub(" ", text)
    other_tokens = re.findall(r"[A-Za-z0-9]+|[^\W\d_]+|[^\w\s]", remaining)
    return cjk_count + len(other_tokens)

_MISTUNE_INSTANCE = mistune.create_markdown(
    escape=False,
    hard_wrap=True,
    plugins=[
        "strikethrough",
        "table",
        "footnotes",
    ],
)

warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)

_CACHE_KEY = "_mfai_cache"


def _get_cache(entry: dict) -> dict:
    """Get or create cache dict for entry (internal use only)"""
    if _CACHE_KEY not in entry:
        entry[_CACHE_KEY] = {}
    return entry[_CACHE_KEY]


def get_clean_content(html_content: str) -> str:
    """
    Get clean content from HTML content.

    Args:
        html_content: HTML formatted content

    Returns:
        Clean content
    """
    soup = BeautifulSoup(html_content, "lxml")

    # Remove invisible content: script, style, noscript, iframe, etc.
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    return soup.get_text(separator=" ", strip=True)


def get_content_text(entry: dict) -> str:
    """
    Get plain text content from entry with caching.

    This function strips HTML tags and caches the result in the entry
    to avoid repeated parsing when multiple rules check the same content.

    Args:
        entry: Entry dictionary (may be modified to add cache)

    Returns:
        Plain text content with HTML tags stripped
    """
    cache = _get_cache(entry)
    cache_key = "content_text"

    if cache_key not in cache:
        html_content = entry.get("content", "")
        cache[cache_key] = get_clean_content(html_content)

    return cache[cache_key]


def get_content_length(entry: dict) -> int:
    """
    Get the token count of entry content using tiktoken (OpenAI's tokenizer).

    This function uses tiktoken to count tokens, which provides:
    - Fair counting across different languages (CJK and Latin scripts)
    - Alignment with LLM processing units
    - Natural word boundary awareness (spaces preserved)

    The result is cached in the entry to avoid repeated tokenization.

    Args:
        entry: Entry dictionary (may be modified to add cache)

    Returns:
        Number of tokens in the content.
    """
    cache = _get_cache(entry)
    cache_key = "content_length"

    if cache_key not in cache:
        content_text = get_content_text(entry)
        content_text = " ".join(content_text.split())
        cache[cache_key] = _token_count(content_text)

    return cache[cache_key]


def to_markdown(content: str) -> str:
    """
    Convert content to markdown format

    Args:
        content: Raw content (HTML or plain text)

    Returns:
        Markdown formatted content
    """
    return md(content)


def to_html(content: str) -> str:
    """
    Convert markdown formatted content to HTML format

    Args:
        content: Markdown formatted content

    Returns:
        HTML formatted content
    """
    return _MISTUNE_INSTANCE(content)


def parse_entry_content(content: str) -> tuple[str, dict[str, str]]:
    """
    Parse entry content to extract original content and existing agent results

    Args:
        content: Full content including agent results and markers

    Returns:
        Tuple of (original_content, existing_agent_content_dict)
    """
    # Combined pattern to match both new and legacy markers
    combined_pattern = f"(?:{MARKER_PATTERN})|(?:{_LEGACY_MARKER_PATTERN})"
    matches = list(re.finditer(combined_pattern, content))

    if not matches:
        return content, {}

    agent_contents = {}

    for i, match in enumerate(matches):
        agent_name = match.group(1) or match.group(2)
        start_pos = match.start()

        # Extract content before this marker
        if i == 0:
            # First agent - content is from beginning to marker
            agent_content = content[:start_pos].strip()
        else:
            # Other agents - content is from previous marker end to current marker
            prev_marker_end = matches[i - 1].end()
            agent_content = content[prev_marker_end:start_pos].strip()

        if agent_content:
            agent_contents[agent_name] = agent_content

    # Extract original content (after the last marker)
    last_marker_end = matches[-1].end()
    original_content = content[last_marker_end:].strip()

    return original_content, agent_contents


def build_ordered_content(agent_contents: dict[str, str], original_content: str) -> str:
    """
    Build final content with agent contents in proper order

    Args:
        agent_contents: Dictionary of agent_name to content
        original_content: Original article content

    Returns:
        Final ordered content string
    """
    if not agent_contents:
        return original_content

    ordered_parts = []

    for agent_name in config.agents:
        if agent_name in agent_contents:
            ordered_parts.append(agent_contents[agent_name])
            ordered_parts.append(MARKER.format(agent_name))

    ordered_parts.append(original_content)

    return "".join(ordered_parts)




def rewrite_image_urls(html_content: str) -> str:
    """Rewrite external article images to the self-hosted RSS Image Gateway.

    Existing Miniflux /proxy URLs are decoded back to their origin first, so
    changing proxy configuration never nests proxies. Gateway URLs are left
    untouched. Non-http(s) and relative image URLs are preserved.
    """
    import base64
    from urllib.parse import quote, urlparse
    from common import config

    soup = BeautifulSoup(html_content or "", "lxml")
    gateway = config.image_proxy_url.rstrip("/")
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src:
            continue
        # If this is already a gateway URL, inspect its payload. Older migrations
        # may have wrapped a legacy Miniflux proxy URL inside the gateway.
        if src.startswith(gateway + "/"):
            try:
                encoded = src.rstrip("/").rsplit("/", 1)[-1]
                candidate = base64.urlsafe_b64decode(encoded + "=" * ((4-len(encoded)%4)%4)).decode("utf-8")
                if "/18080/proxy/" not in candidate:
                    continue
                src = candidate
            except Exception:
                continue
        # Decode Miniflux signed proxy URLs back to their original URL.
        for _ in range(3):
            if "/proxy/" not in src or "/18080/proxy/" not in src:
                break
            try:
                encoded = src.rstrip("/").split("/proxy/", 1)[1].rsplit("/", 1)[-1]
                src = base64.urlsafe_b64decode(encoded + "=" * ((4-len(encoded)%4)%4)).decode("utf-8")
            except Exception:
                src = ""
                break
        if not src:
            continue
        if urlparse(src).scheme not in ("http", "https"):
            continue
        token = base64.urlsafe_b64encode(src.encode("utf-8")).decode("ascii").rstrip("=")
        img["src"] = gateway + "/" + token
    return str(soup)
