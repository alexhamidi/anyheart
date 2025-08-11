"""
LLM module for handling AI model interactions
"""

import base64
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from src.prompt import prompt
from src.logger import get_logger
import os
import openai
import config

logger = get_logger(__name__)

# Initialize OpenRouter client
openrouter_client = (
    openai.OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=config.OPENROUTER_API_KEY,
    )
    if hasattr(config, "OPENROUTER_API_KEY") and config.OPENROUTER_API_KEY
    else None
)


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

    # Build context from conversation history and collect image paths
    context_parts = []
    image_path = None

    # Check if this is the first request and we have an initial screenshot
    if len(session["conversation_history"]) == 0 and session.get("initial_screenshot"):
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

    # Build conversation context
    for message in session["conversation_history"]:
        if message["role"] == "user":
            if message.get("content"):
                context_parts.append(f"User: {message['content']}")
            if message.get("image_path"):
                image_path = message["image_path"]
                context_parts.append(
                    f"User provided screenshot: {message['image_path']}"
                )
        elif message["role"] == "agent":
            if message.get("content"):
                context_parts.append(f"Assistant: {message['content']}")
            if message.get("edits"):
                context_parts.append(
                    f"Previous changes made: {str(message['edits'])[:200]}..."
                )

    # Add instruction for single-turn completion
    if len(session["conversation_history"]) > 0:
        context_parts.append(
            "\nIMPORTANT: This is a follow-up request. Consider the previous conversation context when making your changes."
        )

    context = "\n".join(context_parts) if context_parts else "No previous iterations."

    # Build image context if screenshot is available
    image_context = ""
    if image_path:
        # Check if this is the first message in conversation (initial screenshot)
        is_initial_request = len(session["conversation_history"]) == 0

        if is_initial_request:
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
    """Forward the prompt to the OpenRouter API and return a Generation object"""

    # Only OpenRouter is supported now
    if openrouter_client is None:
        logger.error("OpenRouter client not initialized")
        return Generation(
            status="error",
            message="OpenRouter client not initialized. Check OPENROUTER_API_KEY.",
            edits=None,
        )

    selected_client = openrouter_client

    try:
        import json

        logger.info(f"Starting LLM forward call with {model_type}")

        # Call OpenRouter API
        text = _call_openrouter(selected_client, formatted_prompt, image_path)

        logger.info(f"Received response from OpenRouter: {text[:200]}...")

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

        # Always return applied_edit status for single-turn responses
        return Generation(status="applied_edit", message=reasoning, edits=edits)

    except Exception as e:
        logger.error(f"Error in LLM forward: {str(e)}", exc_info=True)
        return Generation(
            status="error", message=f"Error processing request: {str(e)}", edits=None
        )


def _call_openrouter(client, formatted_prompt: str, image_path: str | None) -> str:
    """Call OpenRouter API with optional image support using configurable model"""
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

    logger.info(f"Calling OpenRouter API with model: {config.OPENROUTER_MODEL}")
    response = client.chat.completions.create(
        model=config.OPENROUTER_MODEL, messages=messages, max_tokens=4000
    )
    return response.choices[0].message.content
