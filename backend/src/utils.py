import requests
import json
import os
import re
import uuid
import threading
import time
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
from config import MORPH_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, GEMINI_API_KEY
from src.prompt import prompt
from src import db
from src.logger import get_logger

logger = get_logger(__name__)

# Core functions for HTML processing and AI model interaction


def get_html_updates(html: str, query: str, model_type="gemini"):
    """Legacy function - kept for backward compatibility"""
    # Build the formatted prompt - use replace to avoid issues with braces in HTML/CSS
    formatted_prompt = prompt.replace("{FILE}", html).replace("{QUERY}", query)

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    api_key = GEMINI_API_KEY

    data = {"contents": [{"parts": [{"text": formatted_prompt}]}]}
    headers = {"Content-Type": "application/json", "X-goog-api-key": api_key}

    try:
        # Log request
        logger.info(
            f"LLM request to {model_type}, prompt length: {len(formatted_prompt)}"
        )

        response = requests.post(
            url, headers=headers, data=json.dumps(data), timeout=30
        )

        if response.status_code != 200:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"LLM error ({model_type}): {error_msg}")
            raise Exception(
                f"LLM API returned status {response.status_code}: {response.text}"
            )

        response_json = response.json()

        # Handle different response formats
        if model_type == "gemini":
            if not response_json or not response_json.get("candidates"):
                logger.error(
                    f"LLM error ({model_type}): No candidates in response: {response_json}"
                )
                return None

            candidate = response_json["candidates"][0]
            if not candidate.get("content") or not candidate["content"].get("parts"):
                logger.error(
                    f"LLM error ({model_type}): Invalid response structure: {candidate}"
                )
                return None

            result = candidate["content"]["parts"][0].get("text")
            if not result:
                logger.error(
                    f"LLM error ({model_type}): No text in response: {candidate}"
                )
                return None

            # Log successful response
            preview = result[:100].replace("\n", " ").strip()
            logger.info(
                f"LLM response ({model_type}): length {len(result)}, preview: {preview}"
            )
            return result
        else:
            if (
                not response_json
                or not response_json.get("choices")
                or not response_json["choices"][0].get("message")
                or not response_json["choices"][0]["message"].get("content")
            ):
                logger.error(
                    f"LLM error ({model_type}): Invalid response: {response_json}"
                )
                raise Exception("No response from LLM API")

            result = response_json["choices"][0]["message"]["content"]
            preview = result[:100].replace("\n", " ").strip()
            logger.info(
                f"LLM response ({model_type}): length {len(result)}, preview: {preview}"
            )
            return result

    except Exception as e:
        logger.error(f"LLM error ({model_type}): {str(e)}")
        raise Exception(f"LLM API error: {str(e)}")


def morph_apply(html: str, update: str):
    base_url = "https://api.morphllm.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {MORPH_API_KEY}",
        "Content-Type": "application/json",
    }

    content = f"""
    <code>{html}</code>
    <update>{update}</update>
    """

    try:
        # Log request
        logger.info(
            f"Morph request: HTML length {len(html)}, update length {len(update)}"
        )

        response = requests.post(
            base_url,
            headers=headers,
            json={
                "model": "morph-v3-fast",
                "messages": [{"role": "user", "content": content}],
            },
            timeout=30,
        )

        if response.status_code != 200:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"Morph error: {error_msg}")
            raise Exception(
                f"Morph API returned status {response.status_code}: {response.text}"
            )

        response_json = response.json()

        if "choices" not in response_json or not response_json["choices"]:
            logger.error(f"Morph error: Invalid response: {response_json}")
            raise Exception(f"Invalid Morph API response: {response_json}")

        result = response_json["choices"][0]["message"]["content"]
        logger.info(f"Morph response: length {len(result)}")
        return result

    except Exception as e:
        logger.error(f"Morph error: {str(e)}")
        raise Exception(f"Morph API error: {str(e)}")


def process_html(html):
    """Process HTML by removing comments and replacing certain tags with placeholders"""
    import re

    replacements = {}
    counters = {}
    tags_to_replace = {
        "svg": r"<svg[^>]*>[\s\S]*?</svg>",
        "script": r"<script[^>]*>[\s\S]*?</script>",
        "style": r"<style[^>]*>[\s\S]*?</style>",
        "meta": r"<meta[^>]*>",
        "link": r"<link[^>]*>",
    }

    processed_html = html

    # First, completely remove all HTML comments
    processed_html = re.sub(r"<!--[\s\S]*?-->", "", processed_html)

    # Replace tags with placeholders
    for tag, pattern in tags_to_replace.items():
        counters[tag] = 1

        def replace_func(match):
            placeholder = f"__{tag[0]}{tag[1]}{counters[tag]}__"
            counters[tag] += 1
            replacements[placeholder] = match.group(0)
            return placeholder

        processed_html = re.sub(
            pattern, replace_func, processed_html, flags=re.IGNORECASE
        )

    return processed_html, replacements


def replacement_apply(processed_html, replacements):
    """Apply replacements back to processed HTML to restore original tags"""
    restored_html = processed_html

    # Replace placeholders with original content
    for placeholder, original_content in replacements.items():
        restored_html = restored_html.replace(placeholder, original_content)

    return restored_html


# Iteration class moved to be defined inline where needed

# Agent session management functions


def create_agent_session(
    session_id: str, html: str, query: str, max_iterations: int = 5
) -> dict:
    """Create a new agent session"""

    # Process HTML to remove comments and replace complex tags with placeholders
    processed_html, replacements = process_html(html)

    now = datetime.now().isoformat()
    session_data = {
        "id": session_id,
        "status": "created",
        "max_iterations": max_iterations,
        "current_iteration": 0,
        "html": html,  # Keep original HTML
        "current_html": html,  # Keep original HTML for final output
        "processed_html": processed_html,  # Processed HTML for LLM
        "current_processed_html": processed_html,  # Current processed HTML
        "replacements": replacements,  # Store replacements for post-processing
        "original_query": query,
        "iterations": [],
        "created_at": now,
        "updated_at": now,
    }

    success = db.set(session_id, session_data)
    if not success:
        raise Exception("Failed to save session to database")

    return session_data


def get_agent_session(session_id: str) -> dict:
    """Get an agent session by ID"""
    return db.get(session_id)


def update_session(session_id: str, updates: dict) -> bool:
    """Update an agent session with new data"""
    session = db.get(session_id)
    if not session:
        return False

    # Update the session data
    session.update(updates)
    session["updated_at"] = datetime.now().isoformat()

    # Save back to database
    return db.set(session_id, session)


# run_agent_session is now implemented in agent.py
