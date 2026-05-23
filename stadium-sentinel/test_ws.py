import asyncio
import websockets

async def test():
    try:
        async with websockets.connect("ws://127.0.0.1:8080/v1/ws/directives", origin="http://localhost") as ws:
            print("WS: Connected!")
            msg = await asyncio.wait_for(ws.recv(), timeout=2)
            print(f"WS: Received: {msg}")
    except Exception as e:
        print(f"WS: Error: {e}")

asyncio.run(test())
