"""
dashboard/backend/routers/ai_analytics.py
GET /api/ai-analytics

Map-reduce AI analytics pipeline:
1. Fetch ALL comments and posts matching filters from MySQL
2. Chunk them into batches of 60 comments / 50 posts
3. MAP: For each batch, call the LLM to extract partial insights
4. REDUCE: Synthesize all partial insights into final structured output

Two perspectives:
- Customer Intelligence (demands, likes, dislikes, trends) — from comments + engagement
- Company Intelligence (launches, announcements, focus_areas, campaigns) — from post content

Model: qwen2.5:7b (32K context, runs locally via Ollama)
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import date, datetime, timezone
from typing import Optional

import requests as http
from fastapi import APIRouter, BackgroundTasks, HTTPException

from dashboard.backend.db import get_conn
from dashboard.backend.schemas import AIInsightsResponse

router = APIRouter()
logger = logging.getLogger(__name__)

_JOBS: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_HOST  = "http://localhost:11434"
_DEFAULT_MODEL = "qwen2.5:7b"

# Cerebras (fast cloud inference, OpenAI-compatible). Used first when
# CEREBRAS_API_KEY is set; falls back to local Ollama on limit/error.
_CEREBRAS_URL   = "https://api.cerebras.ai/v1/chat/completions"
_CEREBRAS_MODEL = "llama-3.3-70b"   # override via CEREBRAS_MODEL

# Batch sizes per LLM call (tuned for 32K context window)
_COMMENT_BATCH = 60
_POST_BATCH    = 50
_MAX_COMMENT_CHARS = 200
_MAX_POST_CHARS    = 300

# ---------------------------------------------------------------------------
# Prompts — MAP phase (per-batch extraction)
# ---------------------------------------------------------------------------

_CUSTOMER_MAP_PROMPT = """\
You are a customer intelligence analyst. Read the customer comments below \
and extract insights as a JSON object with EXACTLY these four keys: \
demands, likes, dislikes, trends.

Content may be in ANY language (Hindi, Marathi, Hinglish, English). \
Understand all, respond in ENGLISH.

- demands: things customers request or expect
- likes: what they praise or appreciate
- dislikes: complaints, frustrations, criticism
- trends: frequently discussed topics

RULES: 3-8 items per array. [] if no signal. ONLY output JSON. \
Use engagement hints [HIGH ENGAGEMENT] to weight importance.

Example: {"demands":["More SIP videos"],"likes":["Clear explanations"],"dislikes":["Too long"],"trends":["Mutual funds"]}

Analyze and return ONLY JSON:"""

_COMPANY_MAP_PROMPT = """\
You are a business intelligence analyst. Read the company video titles and \
descriptions below and extract insights as a JSON object with EXACTLY these \
four keys: launches, announcements, focus_areas, campaigns.

Content may be in ANY language. Respond in ENGLISH.

- launches: new products, services, features, tools introduced
- announcements: partnerships, acquisitions, strategic initiatives
- focus_areas: key themes, technologies, markets being emphasized
- campaigns: events, promotions, series, marketing activities

RULES: 3-8 items per array. [] if no signal. ONLY output JSON.

Example: {"launches":["New SIP calculator"],"announcements":["NSE partnership"],"focus_areas":["Digital literacy"],"campaigns":["Free demat drive"]}

Analyze and return ONLY JSON:"""

# ---------------------------------------------------------------------------
# Prompts — REDUCE phase (synthesize all batch results)
# ---------------------------------------------------------------------------

_CUSTOMER_REDUCE_PROMPT = """\
You are a senior customer intelligence analyst. Below are partial insights \
extracted from multiple batches of customer comments. Synthesize them into \
ONE final JSON object with keys: demands, likes, dislikes, trends.

RULES:
- Merge similar items (don't repeat the same insight in different words)
- Keep 4-8 of the MOST important/frequent items per category
- Rank by how often an insight appeared across batches
- Output ONLY the final JSON object
- Respond in ENGLISH

Partial insights from batches:
{batch_results}

Return the FINAL synthesized JSON:"""

_COMPANY_REDUCE_PROMPT = """\
You are a senior business intelligence analyst. Below are partial insights \
extracted from multiple batches of company content. Synthesize them into \
ONE final JSON object with keys: launches, announcements, focus_areas, campaigns.

RULES:
- Merge similar items (don't repeat the same insight in different words)
- Keep 4-8 of the MOST important/frequent items per category
- Rank by how often an insight appeared across batches
- Output ONLY the final JSON object
- Respond in ENGLISH

Partial insights from batches:
{batch_results}

Return the FINAL synthesized JSON:"""

# ---------------------------------------------------------------------------
# SQL — fetch ALL matching content (no LIMIT)
# ---------------------------------------------------------------------------

_ALL_COMMENTS_SQL = """
SELECT cm.comment_text,
       COALESCE(em.likes_count, 0) AS post_likes,
       COALESCE(em.views_count, 0) AS post_views
FROM comments cm
JOIN posts p      ON p.id          = cm.post_id
JOIN handles h    ON p.handle_id   = h.id
JOIN categories c ON h.category_id = c.id
JOIN platforms pl ON p.platform_id = pl.id
LEFT JOIN (
    SELECT source_record_id, likes_count, views_count
    FROM engagement_metrics em1
    WHERE source_table = 'post'
      AND snapshot_timestamp = (
          SELECT MAX(snapshot_timestamp)
          FROM engagement_metrics em2
          WHERE em2.source_record_id = em1.source_record_id
            AND em2.source_table = 'post'
      )
) em ON em.source_record_id = p.id
WHERE cm.comment_text IS NOT NULL
  AND LENGTH(TRIM(cm.comment_text)) > 20
  {filters}
ORDER BY COALESCE(em.views_count, 0) DESC, cm.publish_timestamp DESC
"""

_ALL_POSTS_SQL = """
SELECT p.title, COALESCE(p.body, '') AS body,
       COALESCE(em.likes_count, 0) AS likes,
       COALESCE(em.views_count, 0) AS views
FROM posts p
JOIN handles h    ON p.handle_id   = h.id
JOIN categories c ON h.category_id = c.id
JOIN platforms pl ON p.platform_id = pl.id
LEFT JOIN (
    SELECT source_record_id, likes_count, views_count
    FROM engagement_metrics em1
    WHERE source_table = 'post'
      AND snapshot_timestamp = (
          SELECT MAX(snapshot_timestamp)
          FROM engagement_metrics em2
          WHERE em2.source_record_id = em1.source_record_id
            AND em2.source_table = 'post'
      )
) em ON em.source_record_id = p.id
WHERE (p.body IS NOT NULL OR p.title IS NOT NULL)
  {filters}
ORDER BY p.publish_timestamp DESC
"""

# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

def _get_active_job_file() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "..", "..", "storage", "active_job.json")

def _set_active_job(job_id: str) -> None:
    try:
        fpath = _get_active_job_file()
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump({"job_id": job_id}, f)
    except Exception as exc:
        logger.warning("Failed to write active job: %s", exc)

def _clear_active_job() -> None:
    try:
        fpath = _get_active_job_file()
        if os.path.exists(fpath):
            os.remove(fpath)
    except Exception as exc:
        logger.warning("Failed to remove active job: %s", exc)

@router.post("/ai-analytics/job")
def start_ai_analytics_job(
    background_tasks: BackgroundTasks,
    category: Optional[str] = None,
    platform: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to:   Optional[date] = None,
):
    """Start map-reduce AI analysis in the background."""
    job_id = str(uuid.uuid4())
    _JOBS[job_id] = {
        "status": "generating",
        "result": None,
        "error": None,
        "metadata": {
            "category": category or "All Brands",
            "date_from": str(date_from) if date_from else None,
            "date_to": str(date_to) if date_to else None,
            "started_at": _now_str()
        }
    }
    _set_active_job(job_id)
    background_tasks.add_task(_run_ai_job, job_id, category, platform, date_from, date_to)
    return {"job_id": job_id}

@router.get("/ai-analytics/active-job")
def get_active_job():
    fpath = _get_active_job_file()
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            job_id = data.get("job_id")
            if job_id in _JOBS:
                status = _JOBS[job_id]["status"]
                res = {"job_id": job_id, "status": status}
                if status == "failed":
                    res["error"] = _JOBS[job_id].get("error")
                    _clear_active_job()
                elif status == "completed":
                    _clear_active_job()
                return res
            else:
                # Backend restarted, job is lost
                _clear_active_job()
        except Exception:
            pass
    return {"status": "none"}

@router.get("/ai-analytics/job/{job_id}")
def get_ai_analytics_job_status(job_id: str):
    if job_id not in _JOBS:
        raise HTTPException(404, "Job not found")
    return _JOBS[job_id]

@router.get("/ai-analytics/last")
def get_last_ai_analytics():
    cache_file = os.path.join(os.path.dirname(__file__), "..", "..", "..", "storage", "last_ai_analysis.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Failed to read last AI analysis: %s", exc)
    return {}

@router.post("/ai-analytics/clear")
def clear_last_ai_analytics():
    cache_file = os.path.join(os.path.dirname(__file__), "..", "..", "..", "storage", "last_ai_analysis.json")
    if os.path.exists(cache_file):
        try:
            os.remove(cache_file)
        except Exception as exc:
            logger.warning("Failed to clear last AI analysis: %s", exc)
    return {"status": "success"}

def _run_ai_job(
    job_id: str,
    category: Optional[str],
    platform: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
):
    """Run map-reduce AI analysis on ALL matching content."""
    try:
        # If Cerebras isn't configured, require local Ollama to be reachable.
        cerebras_key = os.environ.get("CEREBRAS_API_KEY", "").strip()
        if not cerebras_key:
            ollama_host = os.environ.get("OLLAMA_HOST", _DEFAULT_HOST).rstrip("/")
            try:
                http.get(f"{ollama_host}/api/tags", timeout=5).raise_for_status()
            except Exception:
                _JOBS[job_id]["status"] = "failed"
                _JOBS[job_id]["error"] = f"Cannot reach Ollama at {ollama_host}. Run: ollama serve"
                return

        # ── Fetch ALL content from MySQL ──────────────────────────────────────
        with get_conn() as conn:
            cursor = conn.cursor(dictionary=True)

            clauses: list[str] = []
            params:  list      = []

            if category:
                clauses.append("c.name = %s")
                params.append(category)
            if platform:
                clauses.append("pl.platform_code = %s")
                params.append(platform)
            if date_from:
                clauses.append("DATE(p.publish_timestamp) >= %s")
                params.append(date_from)
            if date_to:
                clauses.append("DATE(p.publish_timestamp) <= %s")
                params.append(date_to)

            filter_sql = ("AND " + " AND ".join(clauses)) if clauses else ""

            cursor.execute(_ALL_COMMENTS_SQL.format(filters=filter_sql), params)
            all_comments = cursor.fetchall()

            cursor.execute(_ALL_POSTS_SQL.format(filters=filter_sql), params)
            all_posts = cursor.fetchall()

        if not all_comments and not all_posts:
            _JOBS[job_id]["status"] = "failed"
            _JOBS[job_id]["error"] = "No content available to analyze. Try broadening your filters."
            return

        logger.info(
            "AI Analytics: processing %d comments + %d posts via map-reduce",
            len(all_comments), len(all_posts),
        )

        # ── MAP phase: Customer Intelligence (from comments) ──────────────────
        customer_batch_results: list[dict] = []
        comment_batches = _chunk_list(all_comments, _COMMENT_BATCH)

        for i, batch in enumerate(comment_batches):
            lines: list[str] = []
            for row in batch:
                text = str(row["comment_text"]).strip().replace("\n", " ")[:_MAX_COMMENT_CHARS]
                views = row.get("post_views", 0)
                hint = " [HIGH ENGAGEMENT]" if views > 10000 else (" [POPULAR]" if views > 1000 else "")
                lines.append(f"{text}{hint}")

            content = "\n".join(lines)
            content += '\n\nReturn ONLY {"demands":[...],"likes":[...],"dislikes":[...],"trends":[...]}'

            result = _call_llm(_CUSTOMER_MAP_PROMPT, content)
            if result:
                customer_batch_results.append(result)
                logger.info("Customer batch %d/%d: extracted %d keys", i+1, len(comment_batches), len(result))

        # ── MAP phase: Company Intelligence (from posts) ──────────────────────
        company_batch_results: list[dict] = []
        post_batches = _chunk_list(all_posts, _POST_BATCH)

        for i, batch in enumerate(post_batches):
            lines: list[str] = []
            for row in batch:
                title = (row.get("title") or "").strip()
                body  = (row.get("body") or "").strip().replace("\n", " ")[:_MAX_POST_CHARS]
                views = row.get("views", 0)
                if title:
                    line = f"TITLE: {title}"
                    if body and body != title:
                        line += f" | DESC: {body}"
                    if views > 10000:
                        line += " [HIGH VIEWS]"
                    lines.append(line)

            content = "\n".join(lines)
            content += '\n\nReturn ONLY {"launches":[...],"announcements":[...],"focus_areas":[...],"campaigns":[...]}'

            result = _call_llm(_COMPANY_MAP_PROMPT, content)
            if result:
                company_batch_results.append(result)
                logger.info("Company batch %d/%d: extracted %d keys", i+1, len(post_batches), len(result))

        # ── REDUCE phase: synthesize Customer insights ────────────────────────
        if len(customer_batch_results) == 1:
            customer_final = customer_batch_results[0]
        elif len(customer_batch_results) > 1:
            batch_json = "\n".join(json.dumps(r) for r in customer_batch_results)
            reduce_input = _CUSTOMER_REDUCE_PROMPT.format(batch_results=batch_json)
            customer_final = _call_llm(reduce_input, "")
        else:
            customer_final = {}

        # ── REDUCE phase: synthesize Company insights ─────────────────────────
        if len(company_batch_results) == 1:
            company_final = company_batch_results[0]
        elif len(company_batch_results) > 1:
            batch_json = "\n".join(json.dumps(r) for r in company_batch_results)
            reduce_input = _COMPANY_REDUCE_PROMPT.format(batch_results=batch_json)
            company_final = _call_llm(reduce_input, "")
        else:
            company_final = {}

        # ── Build response ────────────────────────────────────────────────────
        result = AIInsightsResponse(
            demands=_to_str_list(customer_final.get("demands")),
            likes=_to_str_list(customer_final.get("likes")),
            dislikes=_to_str_list(customer_final.get("dislikes")),
            trends=_to_str_list(customer_final.get("trends")),
            launches=_to_str_list(company_final.get("launches")),
            announcements=_to_str_list(company_final.get("announcements")),
            focus_areas=_to_str_list(company_final.get("focus_areas")),
            campaigns=_to_str_list(company_final.get("campaigns")),
            analyzed_comments=len(all_comments),
            analyzed_posts=len(all_posts),
            generated_at=_now_str(),
        )

        _JOBS[job_id]["status"] = "completed"
        _JOBS[job_id]["result"] = result.model_dump()

        # Save to persistent cache
        cache_file = os.path.join(os.path.dirname(__file__), "..", "..", "..", "storage", "last_ai_analysis.json")
        try:
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({
                    "metadata": _JOBS[job_id]["metadata"],
                    "result": _JOBS[job_id]["result"]
                }, f)
        except Exception as exc:
            logger.warning("Failed to write AI analysis cache: %s", exc)

    except Exception as exc:
        logger.error("AI Analysis job failed: %s", exc, exc_info=True)
        _JOBS[job_id]["status"] = "failed"
        _JOBS[job_id]["error"] = str(exc)
        _clear_active_job()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chunk_list(lst: list, size: int) -> list[list]:
    """Split a list into chunks of at most `size` items."""
    return [lst[i:i + size] for i in range(0, len(lst), size)]


def _call_llm(system_prompt: str, user_content: str) -> dict:
    """Single chat call returning parsed JSON, or {} on failure.

    Tries Cerebras first (fast, free tier) when CEREBRAS_API_KEY is set, then
    automatically falls back to the local Ollama model on rate-limit / quota /
    any error so the map-reduce pipeline keeps working when the daily Cerebras
    allowance is exhausted.
    """
    if user_content:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content},
        ]
    else:
        # Reduce phase — the whole prompt is one user message
        messages = [{"role": "user", "content": system_prompt}]

    # ── Primary: Cerebras ─────────────────────────────────────────────────
    cerebras_key = os.environ.get("CEREBRAS_API_KEY", "").strip()
    if cerebras_key:
        try:
            resp = http.post(
                _CEREBRAS_URL,
                headers={
                    "Authorization": f"Bearer {cerebras_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": os.environ.get("CEREBRAS_MODEL", _CEREBRAS_MODEL),
                    "messages": messages,
                    "temperature": 0.15,
                    "max_tokens": 800,
                    "response_format": {"type": "json_object"},
                    "stream": False,
                },
                timeout=60,
            )
            if resp.status_code == 200:
                raw = resp.json()["choices"][0]["message"]["content"]
                data = _parse_json(raw)
                if data is not None:
                    return data
                logger.warning("Cerebras returned unparseable JSON — falling back to Ollama")
            elif resp.status_code in (402, 429):
                logger.warning("Cerebras limit hit (HTTP %s) — falling back to Ollama", resp.status_code)
            else:
                logger.warning(
                    "Cerebras error (HTTP %s: %s) — falling back to Ollama",
                    resp.status_code, resp.text[:200],
                )
        except Exception as exc:
            logger.warning("Cerebras call failed (%s) — falling back to Ollama", exc)

    # ── Fallback: local Ollama ────────────────────────────────────────────
    host  = os.environ.get("OLLAMA_HOST",  _DEFAULT_HOST).rstrip("/")
    model = os.environ.get("OLLAMA_MODEL", _DEFAULT_MODEL)
    try:
        resp = http.post(
            f"{host}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.15, "num_predict": 800, "num_ctx": 16384},
            },
            timeout=180,
        )
        resp.raise_for_status()
        raw = resp.json()["message"]["content"]
    except Exception as exc:
        logger.error("Ollama call failed: %s", exc)
        return {}

    data = _parse_json(raw)
    if data is None:
        logger.warning("Failed to parse LLM response: %r", raw[:300])
        return {}
    return data


def _parse_json(text: str) -> dict | None:
    """Extract a JSON dict from model output."""
    text = text.strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            if list(parsed.keys()) == ["text"] and isinstance(parsed.get("text"), str):
                inner = _parse_json(parsed["text"])
                if inner is not None:
                    return inner
            return parsed
    except json.JSONDecodeError:
        pass

    fenced = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    fenced = re.sub(r"\s*```$",          "", fenced, flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(fenced)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    return None


def _to_str_list(val: object) -> list[str]:
    if isinstance(val, list):
        return [str(x).strip() for x in val if x]
    return []


def _now_str() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
