import os
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn
import db

app = FastAPI()

# Make sure static directory exists
os.makedirs("static", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
def startup_event():
    db.init_db()

@app.get("/")
def read_root():
    return FileResponse("static/index.html")

@app.get("/api/search")
def search(q: str = "", type: str = Query("all", alias="type")):
    if not q:
        return {"results": []}
    
    results = db.search_files(q, file_type=type, limit=100)
    return {"results": results}

class OpenRequest(BaseModel):
    filepath: str

@app.post("/api/open")
def open_file(req: OpenRequest):
    try:
        print(f"Attempting to open: {req.filepath}")
        # Use os.startfile on Windows
        os.startfile(req.filepath)
        print("Opened successfully.")
        return {"status": "success"}
    except Exception as e:
        print(f"Error opening {req.filepath}: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
