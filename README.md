# Anyheart

An AI-powered browser extension that lets you modify any website using natural language commands. Simply describe what you want to change, and Anyheart will apply the modifications in real-time.

## Setup Instructions

### Backend

1. **Clone the repo**
   ```bash
   git clone <repository-url>
   cd anyheart
   ```

2. **Install deps**
   ```bash
   cd backend
   pip install pipenv
   pipenv install
   pipenv shell
   ```

3. **Configure envs**
   
   Create a `.env` file in the `backend` directory:
   ```bash
   # Required APIs
   OPENROUTER_API_KEY=your_openrouter_api_key_here # note - you can make slight code changes to use any model (or ask cursor or claude code or smth lol)
   MORPH_API_KEY=your_morph_api_key_here
   
   # Optional Configuration
   PORT=8008
   OPENROUTER_MODEL=meta-llama/llama-4-maverick
   ```

   **Getting API Keys:**
   - **OpenRouter**: Sign up at [openrouter.ai](https://openrouter.ai) for AI model access
   - **Morph**: Get your key from [morphllm.com](https://morphllm.com) for HTML processing

4. **Start the backend server**
   ```bash
   pipenv run python main.py
   ```
   
   The server will run on `http://localhost:8008` (or your configured PORT)

### Part 2: Extension Setup

1. **Configure the backend URL**
   
   Edit `extension/constants.js`:
   ```javascript
   BACKEND_URL = "http://localhost:8008"  // Use your backend URL
   ```

2. **Load the extension in Chrome**
   - Open Chrome and go to `chrome://extensions/`
   - Enable "Developer mode" (top right toggle)
   - Click "Load unpacked"
   - Select the `extension` folder from this project
   - The Anyheart extension should now appear in your extensions

3. **Start using Anyheart**
   - Navigate to any website
   - Click the Anyheart extension icon
   - Type your modification request (e.g., "Change the background to dark gray")
   - Click "Submit" and watch the magic happen!

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | ✅ Yes | - | API key for OpenRouter AI models |
| `MORPH_API_KEY` | ✅ Yes | - | API key for Morph HTML processing |
| `PORT` | ❌ No | `8000` | Backend server port |
| `OPENROUTER_MODEL` | ❌ No | `meta-llama/llama-4-maverick` | AI model to use for processing |

## Potential Use Cases
- "Make this website dark mode"
- "Change all buttons to have rounded corners"
- "Remove all advertisements"
- "Make images clickable to view full size"
- "Add a word count to this article"

## Limitations
- **Large pages (80k+ tokens) won't work** due to Morph API limits
- AI responses can be inconsistent 
- Not THAT good yet (still in the works)

## License
MIT
