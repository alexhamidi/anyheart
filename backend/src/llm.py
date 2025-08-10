"""
LLM module for handling AI model interactions
"""

import base64
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from src.utils import get_html_updates
from src.prompt import prompt
from google import genai
from google.genai import types
from src.logger import get_logger
import os
import openai
import anthropic
import config

logger = get_logger(__name__)

# Initialize clients
gemini_client = genai.Client()
openai_client = (
    openai.OpenAI(api_key=config.OPENAI_API_KEY) if config.OPENAI_API_KEY else None
)
anthropic_client = (
    anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    if hasattr(config, "ANTHROPIC_API_KEY") and config.ANTHROPIC_API_KEY
    else None
)
openrouter_client = (
    openai.OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=config.OPENROUTER_API_KEY,
    )
    if hasattr(config, "OPENROUTER_API_KEY") and config.OPENROUTER_API_KEY
    else None
)

# Keep backward compatibility
client = gemini_client


class Generation(BaseModel):
    status: str
    message: str
    edits: str | None = None


def get_prompt(session_id: str) -> tuple[str, List[str]]:
    """Build prompt for the current session iteration and return image paths"""
    from src.utils import get_agent_session

    session = get_agent_session(session_id)
    if not session:
        raise Exception(f"Session {session_id} not found")

    # Get the current processed HTML and query
    current_html = session["current_processed_html"]
    query = session["original_query"]

    # Build context from iterations array and collect image paths
    context_parts = []
    image_path = None
    agent_iterations = 0

    # Check if this is the first iteration and we have an initial screenshot
    if len(session["iterations"]) == 0 and session.get("initial_screenshot"):
        # Save initial screenshot to file for the first LLM call
        screenshot_dir = "screenshots"
        os.makedirs(screenshot_dir, exist_ok=True)

        import base64
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_filename = f"{session_id}_initial_{timestamp}.png"
        image_path = os.path.join(screenshot_dir, image_filename)

        image_data = session["initial_screenshot"]
        if image_data.startswith("data:image"):
            image_data = image_data.split(",")[1]

        with open(image_path, "wb") as f:
            f.write(base64.b64decode(image_data))

        context_parts.append("Initial screenshot of the webpage provided for context.")
        logger.info(
            f"Saved initial screenshot for session {session_id} to {image_path}"
        )

    for iteration in session["iterations"]:
        if iteration["role"] == "user":
            if iteration.get("content"):
                context_parts.append(f"User feedback: {iteration['content']}")
            if iteration.get("image_path"):
                image_path = iteration["image_path"]
                context_parts.append(
                    f"User provided screenshot: {iteration['image_path']}"
                )
        elif iteration["role"] == "agent" and iteration.get("edits"):
            agent_iterations += 1
            context_parts.append(
                f"Previous edit {agent_iterations}: {str(iteration['edits'])[:200]}..."
            )

    # Add progress tracking for multi-turn completion
    if agent_iterations >= 1:
        context_parts.append(
            f"\nPROGRESS: You have made {agent_iterations} edit(s) so far. Review the current state - if the user's request is sufficiently completed, use GENERATION_COMPLETE. If meaningful work remains, continue editing."
        )
    if agent_iterations >= 5:
        context_parts.append(
            f"\nIMPORTANT: You've made {agent_iterations} edits. Carefully assess if the original request is now adequately fulfilled. If so, use GENERATION_COMPLETE to avoid unnecessary changes."
        )

    context = "\n".join(context_parts) if context_parts else "No previous iterations."

    # Build image context if screenshot is available
    image_context = ""
    if image_path:
        if agent_iterations == 0:
            # Initial screenshot context
            image_context = """
<image_attached>
You have a screenshot attached showing the initial state of the webpage before any edits.
This image shows the current visual appearance and can help you understand:
- The existing layout and design
- Current styling and visual elements
- What the user is looking at when they made their request
- The baseline state you'll be modifying

Use this visual context to better understand the user's request and plan appropriate changes to achieve their desired outcome.
</image_attached>"""
        else:
            # Feedback screenshot context
            image_context = """
<image_attached>
You have a screenshot attached showing the current state of the webpage after your previous edits. 
This image represents the visual result of your changes and can help you understand:
- How your edits were rendered visually
- Whether the changes achieved the desired effect
- What might need further adjustment
- The current layout and styling state

Use this visual feedback to inform your next edits and ensure they build upon the current state shown in the screenshot.
</image_attached>"""

    # Build the final prompt with JSON output instruction
    # Use string replacement to avoid issues with curly braces in HTML/CSS
    formatted_prompt = (
        prompt.replace("{FILE}", current_html)
        .replace(
            "{QUERY}",
            f"Original request: {query}\n\nContext from previous iterations:\n{context}",
        )
        .replace("{IMAGE_CONTEXT}", image_context)
    )

    return formatted_prompt, image_path


def forward(
    formatted_prompt: str, image_path: str | None, model_type: str = "openrouter"
) -> Generation:
    """Forward the prompt to the AI model with optional images and return a Generation object"""

    # Select the appropriate client based on model_type
    if model_type == "gemini":
        if gemini_client is None:
            logger.error("Gemini client not initialized")
            return Generation(
                status="error",
                message="Gemini client not initialized. Check GEMINI_API_KEY.",
                edits=None,
            )
        selected_client = gemini_client
    elif model_type == "openai":
        if openai_client is None:
            logger.error("OpenAI client not initialized")
            return Generation(
                status="error",
                message="OpenAI client not initialized. Check OPENAI_API_KEY.",
                edits=None,
            )
        selected_client = openai_client
    elif model_type == "anthropic":
        if anthropic_client is None:
            logger.error("Anthropic client not initialized")
            return Generation(
                status="error",
                message="Anthropic client not initialized. Check ANTHROPIC_API_KEY.",
                edits=None,
            )
        selected_client = anthropic_client
    elif model_type == "openrouter":
        if openrouter_client is None:
            logger.error("OpenRouter client not initialized")
            return Generation(
                status="error",
                message="OpenRouter client not initialized. Check OPENROUTER_API_KEY.",
                edits=None,
            )
        selected_client = openrouter_client
    else:
        logger.error(f"Unsupported model type: {model_type}")
        return Generation(
            status="error",
            message=f"Unsupported model type: {model_type}. Supported types: gemini, openai, anthropic, openrouter",
            edits=None,
        )

    try:
        import json

        logger.info(f"Starting LLM forward call with {model_type}")

        # Handle different model types
        if model_type == "gemini":
            text = _call_gemini(selected_client, formatted_prompt, image_path)
        elif model_type == "openai":
            text = _call_openai(selected_client, formatted_prompt, image_path)
        elif model_type == "anthropic":
            text = _call_anthropic(selected_client, formatted_prompt, image_path)
        elif model_type == "openrouter":
            text = _call_openrouter(selected_client, formatted_prompt, image_path)

        logger.info(f"Received response from {model_type}: {text[:200]}...")

        # Parse JSON response - handle markdown code blocks
        try:
            # Remove markdown code block wrapper if present
            json_text = text.strip()
            if json_text.startswith("```json"):
                json_text = json_text[7:]  # Remove ```json
            if json_text.startswith("```"):
                json_text = json_text[3:]  # Remove ```
            if json_text.endswith("```"):
                json_text = json_text[:-3]  # Remove closing ```
            json_text = json_text.strip()

            # Parse JSON response
            try:
                result = json.loads(json_text)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parsing failed, attempting to fix: {e}")
                # Try to clean up the JSON
                import re

                cleaned_json = json_text

                # Fix common LLM JSON escaping errors

                # Fix double-escaped quotes: \\\" -> \"
                cleaned_json = re.sub(r"\\\\\"", r"\"", cleaned_json)
                # Fix double-escaped single quotes: \\\' -> \'
                cleaned_json = re.sub(r"\\\\\'", r"\'", cleaned_json)

                # Fix invalid escape sequences in JSON strings
                # Remove backslashes before characters that don't need escaping in JSON
                # Valid JSON escape sequences are: \" \\ \/ \b \f \n \r \t \uXXXX
                # Everything else should not have a backslash

                # This regex finds strings and fixes invalid escapes within them
                def fix_string_escapes(match):
                    string_content = match.group(1)
                    # Fix invalid escapes - remove backslashes before characters that don't need them
                    # Keep valid escapes: \" \\ \/ \b \f \n \r \t \u
                    fixed = re.sub(r'\\([^"\\\/bfnrtu])', r"\1", string_content)
                    return f'"{fixed}"'

                # Apply the fix to all JSON string values
                cleaned_json = re.sub(
                    r'"((?:[^"\\]|\\.)*)\"', fix_string_escapes, cleaned_json
                )

                # Check if the model tried to use JavaScript methods or generated multiple JSON objects
                if (
                    ".replace(" in cleaned_json
                    or ".split(" in cleaned_json
                    or ".join(" in cleaned_json
                    or cleaned_json.count("{") > 1
                ):
                    logger.warning(
                        "Model used JavaScript methods or multiple JSON objects, cleaning..."
                    )

                    # First, if there are multiple JSON objects, take only the first complete one
                    lines = cleaned_json.split("\n")
                    json_lines = []
                    brace_count = 0
                    found_first_object = False

                    for line in lines:
                        if not found_first_object and line.strip().startswith("{"):
                            found_first_object = True

                        if found_first_object:
                            json_lines.append(line)
                            brace_count += line.count("{") - line.count("}")

                            # If we've closed the first JSON object, stop
                            if brace_count == 0 and len(json_lines) > 1:
                                break

                    cleaned_json = "\n".join(json_lines)

                    # Remove JavaScript method calls
                    # Pattern to match: "string".replace("old", "new") -> just "string"
                    cleaned_json = re.sub(
                        r'"([^"\\]*(?:\\.[^"\\]*)*)"\.replace\([^)]+\)',
                        r'"\1"',
                        cleaned_json,
                    )
                    # Pattern to match: "string".split().join() -> just "string"
                    cleaned_json = re.sub(
                        r'"([^"\\]*(?:\\.[^"\\]*)*)"\.split\([^)]+\)\.join\([^)]+\)',
                        r'"\1"',
                        cleaned_json,
                    )

                # Try parsing the cleaned JSON
                try:
                    result = json.loads(cleaned_json)
                    logger.info("Successfully cleaned malformed JSON")
                except json.JSONDecodeError as parse_error:
                    logger.error(
                        f"Still unable to parse JSON after cleaning: {parse_error}"
                    )

                    raise e  # Re-raise original error
            edits = result.get("edits", "")
            reasoning = result.get("reasoning", "")

            if not edits and not reasoning:
                raise ValueError("Response missing both 'edits' and 'reasoning' fields")

            logger.info("Successfully parsed JSON response")
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Raw response (first 500 chars): {text[:500]}")

            # Save debug information for troubleshooting
            import datetime

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_file = f"debug_json_parse_error_{timestamp}.txt"
            try:
                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write(f"JSON Parse Error: {e}\n")
                    f.write(f"Timestamp: {timestamp}\n")
                    f.write(f"Model Type: {model_type}\n")
                    f.write(f"Raw Response:\n{text}\n")
                    f.write(f"Processed JSON Text:\n{json_text}\n")
                logger.info(f"Debug information saved to {debug_file}")
            except Exception as debug_e:
                logger.error(f"Failed to save debug file: {debug_e}")

            return Generation(
                status="error",
                message=f"Invalid JSON response from AI: {str(e)}",
                edits=None,
            )

        if "GENERATION_COMPLETE" in edits:
            return Generation(status="completed", message=reasoning, edits=None)
        else:
            return Generation(status="applied_edit", message=reasoning, edits=edits)

    except Exception as e:
        logger.error(f"Error in LLM forward: {str(e)}", exc_info=True)
        return Generation(
            status="error", message=f"Error processing request: {str(e)}", edits=None
        )


def _call_gemini(client, formatted_prompt: str, image_path: str | None) -> str:
    """Call Gemini API with optional image support"""
    contents = []

    if image_path:
        logger.info(f"Loading image from path: {image_path}")
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        contents.append(
            types.Part.from_bytes(
                data=image_bytes,
                mime_type="image/png",
            )
        )
    contents.append(formatted_prompt)

    logger.info("Calling Gemini API")
    response = client.models.generate_content(
        model="gemini-2.0-flash-exp", contents=contents
    )
    return response.text


def _call_openai(client, formatted_prompt: str, image_path: str | None) -> str:
    """Call OpenAI API with optional image support"""
    messages = []

    if image_path:
        logger.info(f"Loading image from path: {image_path}")
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": formatted_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_data}"},
                    },
                ],
            }
        )
    else:
        messages.append({"role": "user", "content": formatted_prompt})

    logger.info("Calling OpenAI API")
    response = client.chat.completions.create(model="gpt-4o-mini", messages=messages)
    return response.choices[0].message.content


def _call_anthropic(client, formatted_prompt: str, image_path: str | None) -> str:
    """Call Anthropic API with optional image support"""
    if image_path:
        logger.info(f"Loading image from path: {image_path}")
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        content = [
            {"type": "text", "text": formatted_prompt},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": image_data,
                },
            },
        ]
    else:
        content = formatted_prompt

    logger.info("Calling Anthropic API")
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=4000,
        messages=[{"role": "user", "content": content}],
    )
    return response.content[0].text


def _call_openrouter(client, formatted_prompt: str, image_path: str | None) -> str:
    """Call OpenRouter API with optional image support using the openai/gpt-oss-20b model"""
    messages = []

    if image_path:
        logger.info(f"Loading image from path: {image_path}")
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": formatted_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_data}"},
                    },
                ],
            }
        )
    else:
        messages.append({"role": "user", "content": formatted_prompt})

    logger.info("Calling OpenRouter API with openai/gpt-oss-20b model")
    response = client.chat.completions.create(
        model="meta-llama/llama-4-maverick", messages=messages, max_tokens=4000
    )
    return response.choices[0].message.content
