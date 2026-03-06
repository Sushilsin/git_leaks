#!/usr/bin/env python3
"""
MCP-Ollama Portal
A web interface to interact with the Gitleaks MCP server using Ollama models
"""

import asyncio
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS
import ollama
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration
MCP_SERVER_PATH = Path(__file__).parent / "server.py"
PYTHON_PATH = Path(__file__).parent / ".venv" / "bin" / "python"
OUTPUT_DIR = Path(__file__).parent / "output"

# Ollama configuration
import os

class Config:
    """Dynamic configuration"""
    def __init__(self):
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.ollama_default_model = os.getenv("OLLAMA_DEFAULT_MODEL", "llama3.2")
        self._client = None
    
    @property
    def client(self):
        if not self._client or self._client._client.base_url != self.ollama_host:
            self._client = ollama.Client(host=self.ollama_host)
        return self._client
    
    def update_host(self, host):
        self.ollama_host = host
        self._client = None  # Force recreation

config = Config()

# Legacy variables for compatibility
OLLAMA_HOST = config.ollama_host
OLLAMA_DEFAULT_MODEL = config.ollama_default_model

# Configure Ollama client
ollama_client = config.client

# Global MCP session and event loop
mcp_session = None
mcp_tools = []
mcp_loop = None
mcp_thread = None

class MCPClient:
    """Client for interacting with MCP server with dedicated event loop"""
    
    def __init__(self):
        self.session = None
        self.read_stream = None
        self.write_stream = None
        self.server_params = None
        self.stdio_context = None
        self.loop = None
        self.loop_thread = None
        
    def start_loop(self):
        """Start a dedicated event loop in a separate thread"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
        
    def run_coroutine(self, coro):
        """Run a coroutine in the dedicated event loop"""
        if not self.loop or not self.loop.is_running():
            raise RuntimeError("Event loop is not running")
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=600)  # 10 minute timeout
        
    async def connect(self):
        """Connect to the MCP server"""
        self.server_params = StdioServerParameters(
            command=str(PYTHON_PATH),
            args=[str(MCP_SERVER_PATH)],
            env={
                "GITLEAKS_OUTPUT_DIR": str(OUTPUT_DIR),
                "GITLEAKS_TIMEOUT": "300",
                "GITLEAKS_MAX_CONCURRENT": "2",
            }
        )
        
        self.stdio_context = stdio_client(self.server_params)
        self.read_stream, self.write_stream = await self.stdio_context.__aenter__()
        
        self.session = ClientSession(self.read_stream, self.write_stream)
        await self.session.__aenter__()
        await self.session.initialize()
        logger.info("Connected to MCP server")
        
        # List available tools
        tools_response = await self.session.list_tools()
        return tools_response.tools
    
    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Call a tool on the MCP server"""
        try:
            result = await self.session.call_tool(tool_name, arguments)
            return result
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from MCP server"""
        if self.session:
            await self.session.__aexit__(None, None, None)
        if self.stdio_context:
            await self.stdio_context.__aexit__(None, None, None)
    
    def stop(self):
        """Stop the event loop and thread"""
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self.loop_thread:
            self.loop_thread.join(timeout=5)

mcp_client = MCPClient()

def format_tool_for_ollama(tools):
    """Format MCP tools for Ollama function calling"""
    formatted_tools = []
    for tool in tools:
        formatted_tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            }
        })
    return formatted_tools

async def chat_with_ollama(messages, model="llama3.2", tools=None):
    """Chat with Ollama model with optional tool calling"""
    try:
        if tools:
            response = config.client.chat(
                model=model,
                messages=messages,
                tools=tools,
                stream=False
            )
        else:
            response = config.client.chat(
                model=model,
                messages=messages,
                stream=False
            )
        return response
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        return {"message": {"content": f"Error: {str(e)}. Make sure Ollama is running and the model '{model}' is available."}}

def process_tool_calls(message, tools_data):
    """Process tool calls from Ollama response (synchronous wrapper)"""
    results = []
    
    if not message.get("tool_calls"):
        return results
    
    for tool_call in message["tool_calls"]:
        function = tool_call.get("function", {})
        tool_name = function.get("name")
        arguments = function.get("arguments", {})
        
        logger.info(f"Calling MCP tool: {tool_name} with args: {arguments}")
        
        # Call the MCP tool using the dedicated event loop
        try:
            result = mcp_client.run_coroutine(
                mcp_client.call_tool(tool_name, arguments)
            )
            
            # Extract text content from MCP result
            if hasattr(result, 'content') and result.content:
                content_text = result.content[0].text if hasattr(result.content[0], 'text') else str(result.content[0])
            else:
                content_text = str(result)
            
            # Format result for Ollama
            results.append({
                "role": "tool",
                "content": content_text,
                "name": tool_name
            })
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            results.append({
                "role": "tool",
                "content": f"Error: {str(e)}",
                "name": tool_name
            })
    
    return results

def sanitize_message_for_json(msg):
    """Ensure message is JSON serializable"""
    if isinstance(msg, dict):
        # Already a dict, ensure nested values are serializable
        result = {}
        for key, value in msg.items():
            if isinstance(value, (str, int, float, bool, type(None))):
                result[key] = value
            elif isinstance(value, (list, tuple)):
                result[key] = [sanitize_message_for_json(item) for item in value]
            elif isinstance(value, dict):
                result[key] = sanitize_message_for_json(value)
            else:
                result[key] = str(value)
        return result
    elif isinstance(msg, (list, tuple)):
        return [sanitize_message_for_json(item) for item in msg]
    elif isinstance(msg, (str, int, float, bool, type(None))):
        return msg
    else:
        # For any other object type, convert to string
        return str(msg)

@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')

@app.route('/api/models', methods=['GET'])
def list_models():
    """List available Ollama models"""
    try:
        response = config.client.list()
        
        # Handle ListResponse object from ollama library
        if hasattr(response, 'models'):
            models_list = response.models
        elif isinstance(response, dict):
            models_list = response.get('models', [])
        else:
            models_list = []
        
        # Extract model names - handle both dict and object formats
        model_names = []
        for model in models_list:
            if hasattr(model, 'model'):
                # Object with model attribute
                model_names.append(model.model)
            elif isinstance(model, dict):
                # Try different possible keys
                name = model.get('name') or model.get('model') or model.get('id')
                if name:
                    model_names.append(name)
            elif isinstance(model, str):
                model_names.append(model)
        
        logger.info(f"Found {len(model_names)} models: {model_names}")
        
        # Set default model
        default_model = config.ollama_default_model
        if default_model not in model_names and model_names:
            default_model = model_names[0]
        
        return jsonify({
            "success": True,
            "models": model_names,
            "default": default_model,
            "host": config.ollama_host
        })
    except Exception as e:
        logger.error(f"Failed to list models: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "Make sure Ollama is running. Try: ollama serve"
        })

@app.route('/api/tools', methods=['GET'])
def list_tools():
    """List available MCP tools"""
    try:
        return jsonify({
            "success": True,
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "schema": tool.inputSchema
                }
                for tool in mcp_tools
            ]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle chat requests with tool calling"""
    try:
        data = request.json
        user_message = data.get('message', '')
        model = data.get('model', 'llama3.2')
        conversation_history = data.get('history', [])
        
        # Filter and clean conversation history - only keep valid message formats
        clean_history = []
        for msg in conversation_history:
            if isinstance(msg, dict) and 'role' in msg and 'content' in msg:
                # Only keep essential fields for Ollama
                clean_msg = {
                    "role": msg["role"],
                    "content": msg["content"]
                }
                # Include tool_calls if present and valid
                if msg.get("tool_calls"):
                    clean_msg["tool_calls"] = msg["tool_calls"]
                clean_history.append(clean_msg)
        
        # Add user message to history
        clean_history.append({
            "role": "user",
            "content": user_message
        })
        
        # Prepare tools for Ollama
        ollama_tools = format_tool_for_ollama(mcp_tools)
        
        # Initial chat with tools
        response = config.client.chat(
            model=model,
            messages=clean_history,
            tools=ollama_tools,
            stream=False
        )
        
        assistant_message = response.get('message', {})
        clean_history.append(assistant_message)
        
        # Process tool calls if any
        if assistant_message.get('tool_calls'):
            tool_results = process_tool_calls(assistant_message, mcp_tools)
            
            # Add tool results to conversation
            clean_history.extend(tool_results)
            
            # Get final response from model
            final_response = config.client.chat(
                model=model,
                messages=clean_history,
                stream=False
            )
            
            assistant_message = final_response.get('message', {})
            clean_history.append(assistant_message)
        
        # Sanitize conversation history for JSON serialization
        safe_history = [sanitize_message_for_json(msg) for msg in clean_history]
        
        return jsonify({
            "success": True,
            "response": assistant_message.get('content', ''),
            "history": safe_history
        })
        
    except Exception as e:
        logger.exception("Chat error")
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/scan', methods=['POST'])
def direct_scan():
    """Direct scan endpoint without AI"""
    try:
        data = request.json
        tool_name = data.get('tool')
        arguments = data.get('arguments', {})
        
        result = mcp_client.run_coroutine(
            mcp_client.call_tool(tool_name, arguments)
        )
        
        return jsonify({
            "success": True,
            "result": result.content[0].text if hasattr(result, 'content') else str(result)
        })
        
    except Exception as e:
        logger.exception("Scan error")
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get portal configuration"""
    return jsonify({
        "success": True,
        "ollama_host": config.ollama_host,
        "ollama_default_model": config.ollama_default_model,
        "output_dir": str(OUTPUT_DIR),
        "mcp_server_path": str(MCP_SERVER_PATH)
    })

@app.route('/api/config', methods=['POST'])
def update_config():
    """Update portal configuration"""
    try:
        data = request.json
        
        if 'ollama_host' in data:
            config.update_host(data['ollama_host'])
        
        if 'ollama_default_model' in data:
            config.ollama_default_model = data['ollama_default_model']
        
        return jsonify({
            "success": True,
            "message": "Configuration updated",
            "config": {
                "ollama_host": config.ollama_host,
                "ollama_default_model": config.ollama_default_model
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/test-ollama', methods=['POST'])
def test_ollama():
    """Test Ollama connection"""
    try:
        data = request.json
        host = data.get('host', config.ollama_host)
        
        # Create temporary client to test
        test_client = ollama.Client(host=host)
        response = test_client.list()
        
        models_data = response if isinstance(response, dict) else {}
        models_list = models_data.get('models', [])
        
        return jsonify({
            "success": True,
            "message": "Connection successful",
            "models_count": len(models_list),
            "host": host
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "message": f"Failed to connect to {host}"
        })

@app.route('/api/status', methods=['GET'])
def status():
    """Get server status"""
    # Check Ollama availability
    ollama_available = False
    try:
        config.client.list()
        ollama_available = True
    except:
        pass
    
    return jsonify({
        "success": True,
        "status": "running",
        "mcp_connected": mcp_client.session is not None,
        "ollama_available": ollama_available,
        "ollama_host": config.ollama_host,
        "output_dir": str(OUTPUT_DIR),
        "server_path": str(MCP_SERVER_PATH),
    })

def init_mcp():
    """Initialize MCP connection with dedicated event loop"""
    global mcp_tools
    
    try:
        # Start the event loop in a separate thread
        mcp_client.loop_thread = threading.Thread(target=mcp_client.start_loop, daemon=True)
        mcp_client.loop_thread.start()
        
        # Give the loop time to start
        import time
        time.sleep(0.5)
        
        # Connect to MCP server
        mcp_tools = mcp_client.run_coroutine(mcp_client.connect())
        logger.info(f"Loaded {len(mcp_tools)} MCP tools")
    except Exception as e:
        logger.error(f"Failed to connect to MCP server: {e}")
        raise

if __name__ == '__main__':
    # Initialize MCP connection
    init_mcp()
    
    # Run Flask app
    logger.info("Starting MCP-Ollama Portal on http://localhost:5001")
    try:
        app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)
    finally:
        # Clean up
        try:
            mcp_client.run_coroutine(mcp_client.disconnect())
        except:
            pass
        mcp_client.stop()

