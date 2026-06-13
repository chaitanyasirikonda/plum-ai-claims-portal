import os
import json
from fastapi import APIRouter, HTTPException
from backend.app.evaluators.eval_runner import EvalRunner
from pathlib import Path

router = APIRouter(prefix="/evals", tags=["Evaluations"])

@router.post("/run")
async def run_evaluations():
    try:
        report = await EvalRunner.run_all()
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to run evaluations: {str(e)}")

@router.get("/report")
async def get_evaluation_report():
    report_path = Path(__file__).resolve().parent.parent / "evaluators" / "eval_report.json"
    if not report_path.exists():
        # Trigger run to create it
        try:
            report = await EvalRunner.run_all()
            return report
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Report file not found and failed to auto-run: {str(e)}")
            
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading report: {str(e)}")
