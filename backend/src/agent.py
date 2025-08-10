"""Agent state machine with WebSocket-based communication"""

import os
import asyncio
from datetime import datetime
from src import llm
from src.utils import get_agent_session, update_session, morph_apply, replacement_apply
from src.logger import get_logger
from src.websocket_manager import ws_manager
import config

logger = get_logger(__name__)


class AgentStateMachine:
    """Event-driven agent state machine"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.state = "processing"
        self.waiting_for_observation = False

    async def run(self):
        """Main agent execution loop"""
        logger.info(f"Starting agent session: {self.session_id}")

        while True:
            session = get_agent_session(self.session_id)
            if not session:
                logger.error(f"Session {self.session_id} not found")
                await self._send_error("Session not found")
                break

            # --- check exit conditions ---
            if session["status"] == "error":
                logger.info(f"Session {self.session_id}: Status is error, exiting")
                break

            if session["status"] == "completed":
                logger.info(f"Session {self.session_id}: Status is completed, exiting")
                break

            if session["current_iteration"] >= session["max_iterations"]:
                logger.info(
                    f"Session {self.session_id}: Reached max iterations, completing"
                )
                await self._complete_session("Reached maximum iterations")
                break

            # --- wait for observation if needed ---
            if self.waiting_for_observation:
                observation = await self._wait_for_observation()
                if observation:
                    await self._process_observation(observation)
                    self.waiting_for_observation = False
                else:
                    # No observation received (timeout or error)
                    logger.warning(
                        f"Session {self.session_id}: No observation received, continuing without observation"
                    )
                    self.waiting_for_observation = False
                continue

            # --- process llm step ---
            try:
                await self._process_llm_step(session)
            except Exception as e:
                logger.error(
                    f"Session {self.session_id}: Exception: {str(e)}", exc_info=True
                )
                await self._send_error(f"Error: {str(e)}")
                break

    async def _process_llm_step(self, session):
        """Process a single LLM step"""
        formatted_prompt, image_path = llm.get_prompt(self.session_id)
        generation = llm.forward(formatted_prompt, image_path)

        logger.info(
            f"Session {self.session_id}: LLM returned status: {generation.status}"
        )

        if generation.status == "completed":
            await self._complete_session(generation.message)

        elif generation.status == "error":
            logger.error(f"Session {self.session_id}: LLM error: {generation.message}")
            await self._send_error(generation.message)

        elif generation.status == "applied_edit":
            await self._apply_edit(session, generation)

    async def _apply_edit(self, session, generation):
        """Apply edit and request observation"""
        # --- apply edits ---
        new_processed_html = morph_apply(
            session["current_processed_html"], generation.edits
        )
        new_html = replacement_apply(new_processed_html, session["replacements"])

        # --- update session ---
        session["iterations"].append(
            {
                "role": "agent",
                "content": generation.message,
                "timestamp": datetime.now().isoformat(),
                "edits": generation.edits,
            }
        )

        update_session(
            self.session_id,
            {
                "current_html": new_html,
                "current_processed_html": new_processed_html,
                "iterations": session["iterations"],
                "current_iteration": session["current_iteration"] + 1,
                "status": "applied_edit",
                "message": generation.message,
            },
        )

        # --- request frontend to apply edit ---
        await ws_manager.send_message(
            self.session_id,
            {
                "type": "apply_edit",
                "html": new_html,
                "message": generation.message,
                "iteration": session["current_iteration"] + 1,
            },
        )

        self.waiting_for_observation = True
        logger.info(f"Session {self.session_id}: Edit applied, waiting for observation")

    async def _wait_for_observation(self):
        """Wait for observation from frontend with timeout"""
        logger.debug(f"Session {self.session_id}: Waiting for observation")

        try:
            # Wait for observation with timeout
            message = await asyncio.wait_for(
                ws_manager.receive_message(self.session_id),
                timeout=config.FRONTEND_OBSERVATION_TIMEOUT,
            )

            if message and message.get("type") == "observation":
                return message.get("data")
            return None

        except asyncio.TimeoutError:
            logger.warning(
                f"Session {self.session_id}: Observation timeout after {config.FRONTEND_OBSERVATION_TIMEOUT}s"
            )
            return None

    async def _process_observation(self, observation_data):
        """Process received observation"""
        session = get_agent_session(self.session_id)
        if not session:
            return

        user_iteration = {
            "role": "user",
            "content": observation_data.get("summary", ""),
            "timestamp": datetime.now().isoformat(),
        }

        # --- save screenshot if provided ---
        if observation_data.get("screenshot"):
            screenshot_dir = "screenshots"
            os.makedirs(screenshot_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_filename = f"{self.session_id}_{timestamp}.png"
            image_path = os.path.join(screenshot_dir, image_filename)

            import base64

            image_data = observation_data["screenshot"]
            if image_data.startswith("data:image"):
                image_data = image_data.split(",")[1]

            with open(image_path, "wb") as f:
                f.write(base64.b64decode(image_data))

            user_iteration["image_path"] = image_path

        session["iterations"].append(user_iteration)
        update_session(
            self.session_id,
            {
                "iterations": session["iterations"],
                "status": "processing",
            },
        )

        logger.info(f"Session {self.session_id}: Observation processed, continuing")

    async def _complete_session(self, message: str):
        """Complete the agent session"""
        update_session(
            self.session_id,
            {
                "status": "completed",
                "message": message,
                "completed_at": datetime.now().isoformat(),
            },
        )

        # Save complete session data to sessions folder
        await self._save_session_file()

        await ws_manager.send_message(
            self.session_id, {"type": "completed", "message": message}
        )

    async def _send_error(self, message: str):
        """Send error and terminate session"""
        update_session(self.session_id, {"status": "error", "message": message})

        # Save complete session data for debugging failed sessions
        await self._save_session_file()

        await ws_manager.send_message(
            self.session_id, {"type": "error", "message": message}
        )

    async def _save_session_file(self):
        """Save complete session data to sessions folder"""
        import json
        import os

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

            # Create filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"session_{timestamp}_{self.session_id}.json"
            filepath = os.path.join(sessions_dir, filename)

            # Save session data as JSON
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(session, f, indent=2, ensure_ascii=False)

            logger.info(
                f"Session {self.session_id}: Complete session data saved to {filepath}"
            )

        except Exception as e:
            logger.error(f"Failed to save session file for {self.session_id}: {str(e)}")


async def run_agent_session(session_id: str):
    """Start agent state machine for session"""
    agent = AgentStateMachine(session_id)
    await agent.run()
