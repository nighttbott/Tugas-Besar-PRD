from fastapi import FastAPI, WebSocket
import uvicorn

app = FastAPI()

@app.websocket("/ws/test")
async def ws_test(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_text("ok")
    await websocket.close()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)