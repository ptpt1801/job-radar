"""Optional LLM extraction (EXTRACTOR: claude). Off by default; needs ANTHROPIC_API_KEY.

- Model claude-haiku-5-5 via the Message Batches API (50% price), cached system prompt.
- Only new / changed jobs (the caller passes only non-reused jobs), hard cap MAX_LLM_JOBS_PER_RUN.
- Sends job posting text only. The CV / skill profile is NEVER sent; match stays rule-based.
- Any invalid output falls back to the rule-based values already on the job.
"""
from __future__ import annotations

import json
import re
import time

from .config import ROOT, taxonomy

# Haiku 5.5 list price per 1M tokens (prompts <= 100K), halved for batches.
PRICE_IN, PRICE_OUT = 0.10 * 0.5, 0.50 * 0.5
LEVELS = {"internship", "graduate", "experienced", "manager"}
FUNCS = {"supply_chain", "finance", "sales", "engineering", "it", "hr", "marketing", "operations", "legal", "other"}
LANGS = {"english", "german", "japanese", "french", "chinese", "korean", "vietnamese"}


def _system_prompt() -> str:
    text = (ROOT / "prompts" / "extract_job.md").read_text(encoding="utf-8")
    sysp = text.split("## SYSTEM", 1)[1].split("## USER", 1)[0].strip()
    return sysp.replace("{{taxonomy skill keys, comma separated}}", ", ".join(taxonomy()["skills"].keys()))


def _user_prompt(j: dict) -> str:
    return (f"Company: {j['company']}\nTitle: {j['title']}\nLocation: {j.get('address_raw') or ''}\n"
            f'Posting text (truncated to 6,000 characters):\n"""\n{(j.get("_desc") or "")[:6000]}\n"""')


def _apply(j: dict, out: dict) -> bool:
    skills = set(taxonomy()["skills"].keys())
    if out.get("level") in LEVELS:
        j["level"] = out["level"]
    if out.get("function") in FUNCS:
        j["function"] = out["function"]
    if isinstance(out.get("skills"), list):
        j["skills"] = [s for s in out["skills"] if s in skills][:10] or j.get("skills", [])
    if isinstance(out.get("languages_required"), list):
        j["languages_required"] = [x for x in out["languages_required"] if x in LANGS]
    if isinstance(out.get("experience_min_years"), int) and 0 <= out["experience_min_years"] <= 30:
        j["experience_min_years"] = out["experience_min_years"]
    sal = out.get("salary")
    if isinstance(sal, dict) and sal.get("currency") in ("VND", "USD", "EUR") and (sal.get("min") or sal.get("max")):
        j["salary"] = {"min": sal.get("min"), "max": sal.get("max"), "currency": sal["currency"],
                       "period": sal.get("period") if sal.get("period") in ("month", "year", "hour") else "month",
                       "is_allowance": bool(sal.get("is_allowance")), "raw": str(sal.get("raw") or "")[:160]}
    if isinstance(out.get("benefits"), list) and out["benefits"]:
        j["benefits"] = [str(b)[:120] for b in out["benefits"]][:6]
    if out.get("work_mode") in ("onsite", "hybrid", "remote"):
        j["work_mode"] = out["work_mode"]
    if isinstance(out.get("deadline"), str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", out["deadline"]):
        j["deadline"] = out["deadline"]
    return True


def run(jobs: list[dict], cfg: dict) -> dict:
    stats = {"mode": "claude", "jobs": 0, "input_tokens": 0, "output_tokens": 0, "est_cost_usd": 0.0, "errors": 0}
    todo = [j for j in jobs if j.get("_desc")][: int(cfg.get("MAX_LLM_JOBS_PER_RUN", 150))]
    if not todo:
        return stats
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    client = anthropic.Anthropic()
    system = [{"type": "text", "text": _system_prompt(), "cache_control": {"type": "ephemeral"}}]
    model = cfg.get("LLM_MODEL", "claude-haiku-5-5")
    by_id = {j["id"]: j for j in todo}
    try:
        batch = client.messages.batches.create(requests=[
            Request(custom_id=j["id"], params=MessageCreateParamsNonStreaming(
                model=model, max_tokens=2048, output_config={"effort": "low"}, system=system,
                messages=[{"role": "user", "content": _user_prompt(j)}]))
            for j in todo])
        deadline = time.time() + 50 * 60
        while True:
            batch = client.messages.batches.retrieve(batch.id)
            if batch.processing_status == "ended" or time.time() > deadline:
                break
            time.sleep(30)
        if batch.processing_status != "ended":
            client.messages.batches.cancel(batch.id)
            stats["errors"] += len(todo)
            return stats
        for res in client.messages.batches.results(batch.id):
            if res.result.type != "succeeded":
                stats["errors"] += 1
                continue
            msg = res.result.message
            u = msg.usage
            stats["input_tokens"] += (u.input_tokens or 0) + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0)
            stats["output_tokens"] += u.output_tokens or 0
            if msg.stop_reason == "refusal":
                stats["errors"] += 1
                continue
            text = next((b.text for b in msg.content if b.type == "text"), "")
            m = re.search(r"\{.*\}", text, re.S)
            try:
                out = json.loads(m.group(0)) if m else None
            except json.JSONDecodeError:
                out = None
            if isinstance(out, dict) and res.custom_id in by_id:
                _apply(by_id[res.custom_id], out)  # rules values stay where output is invalid
                stats["jobs"] += 1
            else:
                stats["errors"] += 1
    except anthropic.APIError as e:
        print("enrich_claude: API error, keeping rule-based values:", type(e).__name__)
        stats["errors"] += len(todo)
    stats["est_cost_usd"] = round(stats["input_tokens"] / 1e6 * PRICE_IN + stats["output_tokens"] / 1e6 * PRICE_OUT, 4)
    return stats
