# -*- coding: utf-8 -*-
"""main.py · 赛博评审厅 FastAPI 入口

对齐 README "方式二 完整项目（后端 + 前端）"：
    pip install fastapi uvicorn
    cd backend
    python -m uvicorn main:app --reload --port 8000

前端从 /api/analyze 拉数据；离线回退到 window.DEMO_DATA（demo-data.js）。"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from engine.rule_engine import analyze
from engine.data_provider import DataProvider

app = FastAPI(title="赛博评审厅 API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
provider = DataProvider()

@app.get("/api/health")
def health():
    return {"status": "ok", "stocks": list(provider.supported)}

@app.get("/api/analyze")
def analyze_stock(code: str = Query(..., description="股票代码（20 只预设标的，覆盖 10 大板块）")):
    code = code.strip().split(".")[0] if "." in code else code.strip()
    if code not in provider.supported:
        raise HTTPException(status_code=404, detail=f"代码 {code} 不在预设演示数据（{' / '.join(provider.supported)}）")
    return analyze(code, provider)

_frontend = Path(__file__).resolve().parent.parent / "frontend"
if _frontend.exists():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)