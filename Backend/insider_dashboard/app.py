from fastapi import FastAPI
from fastapi.responses import JSONResponse
import os
from dotenv import load_dotenv

load_dotenv()  # Load .env from root
app = FastAPI()

@app.get("/")
def root():
    return {"message": "Insider Trading Dashboard API is running."}

@app.get("/token-test")
def show_token():
    token = os.getenv("QAPI_TOKEN")
    if not token:
        return JSONResponse(status_code=500, content={"error": "Token not found"})
    return {"token": token[:5] + "... (hidden)"}