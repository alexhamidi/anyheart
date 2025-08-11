"""Agent for processing single-turn user requests"""

import os
from datetime import datetime
from dataclasses import dataclass
from typing import Optional
from src import llm
from src.utils import get_agent_session, update_session, morph_apply, replacement_apply
from src.logger import get_logger
import config

logger = get_logger(__name__)


@dataclass
class ProcessingResult:
    """Result of processing a user request"""

    status: str  # "success" or "error"
    message: str
    updated_html: Optional[str] = None


class AgentSession:
    """Single-turn agent with session context"""

    def __init__(self, session_id: str):
        self.session_id = session_id

    async def process_user_request(
        self, query: str, screenshot: str = None
    ) -> ProcessingResult:
        """Process a single user request and return the result"""
        logger.info(f"Processing user request for session: {self.session_id}")

        session = get_agent_session(self.session_id)
        if not session:
            logger.error(f"Session {self.session_id} not found")
            return ProcessingResult(status="error", message="Session not found")

        try:
            # Add user message to conversation history
            await self._add_user_message(query, screenshot)

            # Get updated session after adding user message
            updated_session = get_agent_session(self.session_id)
            if not updated_session:
                return ProcessingResult(
                    status="error", message="Session not found after update"
                )

            # Process single LLM call
            result = await self._process_llm_request(updated_session)
            return result

        except Exception as e:
            logger.error(
                f"Session {self.session_id}: Exception: {str(e)}", exc_info=True
            )
            # Save session even on error to capture what went wrong
            await self._save_session_file()
            return ProcessingResult(status="error", message=f"Error: {str(e)}")

    async def _add_user_message(self, query: str, screenshot: str = None):
        """Add user message to conversation history"""
        session = get_agent_session(self.session_id)
        if not session:
            return

        user_message = {
            "role": "user",
            "content": query,
            "timestamp": datetime.now().isoformat(),
        }

        # Save screenshot if provided
        if screenshot:
            screenshot_dir = "screenshots"
            os.makedirs(screenshot_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_filename = f"{self.session_id}_{timestamp}.png"
            image_path = os.path.join(screenshot_dir, image_filename)

            import base64

            image_data = screenshot
            if image_data.startswith("data:image"):
                image_data = image_data.split(",")[1]

            with open(image_path, "wb") as f:
                f.write(base64.b64decode(image_data))

            user_message["image_path"] = image_path

        session["conversation_history"].append(user_message)
        update_session(
            self.session_id,
            {
                "conversation_history": session["conversation_history"],
                "status": "processing",
            },
        )

    async def _process_llm_request(self, session) -> ProcessingResult:
        """Process a single LLM request and apply results"""
        formatted_prompt, image_path = llm.get_prompt(self.session_id)
        generation = llm.forward(formatted_prompt, image_path)

        logger.info(
            f"Session {self.session_id}: LLM returned status: {generation.status}"
        )

        if generation.status == "error":
            logger.error(f"Session {self.session_id}: LLM error: {generation.message}")
            # Save session to capture the error state
            await self._save_session_file()
            return ProcessingResult(status="error", message=generation.message)

        # Apply the edit (both "completed" and "applied_edit" now just apply and return result)
        if generation.edits:
            return await self._apply_edit(session, generation)
        else:
            # No edits, just return response and save session
            await self._save_session_file()
            return ProcessingResult(status="success", message=generation.message)

    async def _apply_edit(self, session, generation) -> ProcessingResult:
        """Apply edit and return result"""
        # Apply edits to HTML
        new_processed_html = morph_apply(
            session["current_processed_html"], generation.edits
        )

        # DEBUG: Log what morph_apply returned
        logger.info(
            f"Session {self.session_id}: Morph returned HTML length: {len(new_processed_html)}"
        )
        logger.info(
            f"Session {self.session_id}: Morph HTML contains <script>: {'<script>' in new_processed_html.lower()}"
        )

        # CRITICAL FIX: Preserve any new script tags that were added by the agent
        # Don't let them get processed/replaced by the replacement system
        import re

        # Extract any new script tags from the processed HTML
        new_scripts = re.findall(
            r"<script[^>]*>[\s\S]*?</script>", new_processed_html, re.IGNORECASE
        )
        logger.info(
            f"Session {self.session_id}: Found {len(new_scripts)} scripts in processed HTML"
        )

        # Apply original replacements
        new_html = replacement_apply(new_processed_html, session["replacements"])
        logger.info(
            f"Session {self.session_id}: After replacement_apply, HTML length: {len(new_html)}"
        )

        # If we lost any script tags during replacement, add them back
        current_scripts = re.findall(
            r"<script[^>]*>[\s\S]*?</script>", new_html, re.IGNORECASE
        )
        logger.info(
            f"Session {self.session_id}: Found {len(current_scripts)} scripts in final HTML"
        )

        # Add any missing scripts at the end of body
        for script in new_scripts:
            if (
                script not in current_scripts
                and script not in session["replacements"].values()
            ):
                # Insert before closing </body> tag
                new_html = new_html.replace("</body>", f"{script}\n</body>")
                logger.info(f"Session {self.session_id}: Preserved new script tag")
            else:
                logger.info(
                    f"Session {self.session_id}: Script already exists or is in replacements"
                )

        # FALLBACK: If no scripts were found but the agent's edits contain <script>, extract and add them directly
        if len(new_scripts) == 0 and "<script>" in generation.edits.lower():
            logger.info(
                f"Session {self.session_id}: No scripts in processed HTML but edits contain <script>, extracting directly"
            )
            direct_scripts = re.findall(
                r"<script[^>]*>[\s\S]*?</script>", generation.edits, re.IGNORECASE
            )
            for script in direct_scripts:
                if script not in new_html:
                    new_html = new_html.replace("</body>", f"{script}\n</body>")
                    logger.info(
                        f"Session {self.session_id}: Added script directly from edits"
                    )

        # Add agent response to conversation history
        agent_message = {
            "role": "agent",
            "content": generation.message,
            "timestamp": datetime.now().isoformat(),
            "edits": generation.edits,
        }

        session["conversation_history"].append(agent_message)

        # Update session with new HTML and conversation
        update_session(
            self.session_id,
            {
                "current_html": new_html,
                "current_processed_html": new_processed_html,
                "conversation_history": session["conversation_history"],
                "status": "ready",  # Ready for next request
                "message": generation.message,
            },
        )

        logger.info(f"Session {self.session_id}: Edit applied successfully")

        # Save complete session to file after successful completion
        await self._save_session_file()

        return ProcessingResult(
            status="success", message=generation.message, updated_html=new_html
        )

    async def _save_session_file(self):
        """Save complete session data to sessions folder"""
        import json
        from datetime import datetime

        try:
            # Get the complete session data
            session = get_agent_session(self.session_id)
            if not session:
                logger.error(
                    f"Cannot save session file: session {self.session_id} not found"
                )
                return

            # Create sessions directory if it doesn't exist
            sessions_dir = "sessions"
            os.makedirs(sessions_dir, exist_ok=True)

            # Create filename with timestamp and session info
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Get the original query for filename context (first 50 chars, safe for filename)
            original_query = session.get("original_query", "unknown")
            safe_query = "".join(
                c for c in original_query[:50] if c.isalnum() or c in (" ", "-", "_")
            ).rstrip()
            safe_query = safe_query.replace(" ", "_")

            filename = f"session_{timestamp}_{self.session_id}_{safe_query}.json"
            filepath = os.path.join(sessions_dir, filename)

            # Add metadata to session before saving
            session_with_metadata = {
                "metadata": {
                    "saved_at": datetime.now().isoformat(),
                    "session_id": self.session_id,
                    "total_messages": len(session.get("conversation_history", [])),
                    "original_query": session.get("original_query", ""),
                    "final_status": session.get("status", "unknown"),
                },
                "session_data": session,
            }

            # Save session data as JSON
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(session_with_metadata, f, indent=2, ensure_ascii=False)

            logger.info(
                f"Session {self.session_id}: Complete session data saved to {filepath}"
            )

        except Exception as e:
            logger.error(f"Failed to save session file for {self.session_id}: {str(e)}")


async def process_user_request(
    session_id: str, query: str, screenshot: str = None
) -> ProcessingResult:
    """Process a single user request in the session"""
    agent = AgentSession(session_id)
    return await agent.process_user_request(query, screenshot)
