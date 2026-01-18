from flask import Flask, render_template, request, jsonify
import asyncio
import websockets
import json

app = Flask(__name__)

# Your Xiaozhi endpoint
XIAOZHI_ENDPOINT = "wss://api.xiaozhi.me/mcp/?token=eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOjc3NDE4MiwiYWdlbnRJZCI6MTM0NzIzMSwiZW5kcG9pbnRJZCI6ImFnZW50XzEzNDcyMzEiLCJwdXJwb3NlIjoibWNwLWVuZHBvaW50IiwiaWF0IjoxNzY4NzUwOTY3LCJleHAiOjE4MDAzMDg1Njd9.CLe93UBucaXs46onS5PCVgjcTFg7j4sOIyTuYSObBUL5sh8UTIxJME0BNLtd2F6Abn8_FkrKjVqKpboREiQtPA"


async def send_to_xiaozhi(message):
    """Send message to Xiaozhi MCP endpoint"""
    try:
        async with websockets.connect(XIAOZHI_ENDPOINT) as ws:
            # Initialize
            await ws.send(json.dumps({
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "Web Client"}
                },
                "id": 1
            }))
            await ws.recv()

            # Send user message as calculation
            calc_request = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "calculate",
                    "arguments": {
                        "expression": message
                    }
                },
                "id": 2
            }

            await ws.send(json.dumps(calc_request))
            response = await ws.recv()

            # Parse response
            data = json.loads(response)
            if "result" in data:
                return data["result"]["content"][0]["text"]
            else:
                return f"Error: {data.get('error', 'Unknown error')}"

    except Exception as e:
        return f"Connection error: {str(e)}"


@app.route('/')
def index():
    return render_template('chat.html')


@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '')

    # Run async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    response = loop.run_until_complete(send_to_xiaozhi(user_message))
    loop.close()

    return jsonify({"response": response})


if __name__ == '__main__':
    app.run(debug=True, port=5000)