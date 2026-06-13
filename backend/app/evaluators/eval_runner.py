import os
import json
import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.schemas.claim import ClaimProcessRequest
from backend.app.workflows.claim_workflow import claim_processor
from backend.app.utils.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EvalRunner:
    @staticmethod
    def evaluate_test_case(case_id: str, actual: dict, expected: dict) -> Tuple[bool, str]:
        # Compare actual vs expected
        exp_decision = expected.get("decision")
        act_decision = actual.get("decision")
        
        # 1. Decision check
        # Special check: expected decision can be null (meaning early halt)
        if exp_decision != act_decision:
            return False, f"Decision mismatch. Expected: {exp_decision}, Actual: {act_decision}"
            
        # 2. Approved amount check
        exp_amount = expected.get("approved_amount")
        act_amount = actual.get("approved_amount", 0.0)
        if exp_amount is not None:
            if abs(float(exp_amount) - float(act_amount)) > 0.01:
                return False, f"Approved amount mismatch. Expected: ₹{exp_amount}, Actual: ₹{act_amount}"

        # 3. Rejection reasons check
        exp_reasons = expected.get("rejection_reasons")
        act_reasons = actual.get("reasons", [])
        if exp_reasons:
            for r in exp_reasons:
                if not any(r in str(act_r) for act_r in act_reasons):
                    return False, f"Expected rejection reason '{r}' not found in actual reasons: {act_reasons}"

        # 4. Confidence checks
        exp_conf = expected.get("confidence_score")
        act_conf = actual.get("confidence_score", 1.0)
        if exp_conf:
            if "above" in exp_conf:
                val = float(exp_conf.split("above ")[1])
                if act_conf < val:
                    return False, f"Confidence too low. Expected above {val}, Actual: {act_conf:.2f}"
            elif "lower" in exp_conf or "reduced" in exp_conf:
                # Normal confidence should be 1.0, reduced should be < 0.8
                if act_conf >= 0.9:
                    return False, f"Confidence not degraded as expected. Expected reduced, Actual: {act_conf:.2f}"

        # 5. System must requirements check (check if requirements trace matches)
        trace_str = " ".join([t.get("details", "") for t in actual.get("trace", [])])
        system_must = expected.get("system_must", [])
        for must in system_must:
            # Check key terms in the trace detail
            keywords = []
            if "re-upload" in must.lower():
                keywords = ["re-upload", "unreadable"]
            elif "different people" in must.lower() or "different names" in must.lower():
                keywords = ["mismatch", "different", "patient"]
            elif "network discount" in must.lower():
                keywords = ["discount", "copay", "apollo"]
            elif "per-claim limit" in must.lower():
                keywords = ["limit", "per-claim", "5000"]
            elif "component failed" in must.lower() or "skipped" in must.lower():
                keywords = ["failed", "component", "ocr_extraction"]
            elif "waiting period" in must.lower() or "eligible" in must.lower():
                keywords = ["waiting", "period", "eligible"]
            elif "pre-authorization" in must.lower():
                keywords = ["pre-authorization", "auth", "missing"]

            if keywords:
                found = any(k in trace_str.lower() for k in keywords) or any(k in str(act_reasons).lower() for k in keywords)
                if not found:
                    return False, f"Trace did not explicitly verify expected behavior: '{must}'"

        return True, "All criteria satisfied."

    @classmethod
    async def run_all(cls) -> Dict[str, Any]:
        test_cases_data = Config.load_test_cases()
        policy_terms = Config.load_policy_terms()
        
        results = []
        passed_count = 0
        
        for case in test_cases_data.get("test_cases", []):
            case_id = case["case_id"]
            name = case["case_name"]
            desc = case["description"]
            inp = case["input"]
            expected = case["expected"]
            
            logger.info(f"Running test case {case_id}: {name}")
            
            # Map input to Pydantic model
            request = ClaimProcessRequest(**inp)
            
            # Set initial state
            state = {
                "claim_id": None,
                "request": request,
                "policy_terms": policy_terms,
                "member": None,
                "extracted_docs": {},
                "validation_results": {},
                "fraud_signals": [],
                "financial_calculation": None,
                "decision": None,
                "approved_amount": 0.0,
                "confidence_score": 1.0,
                "reasons": [],
                "trace": [],
                "manual_review_recommended": False,
                "stop_processing": False,
                "error_message": None
            }
            
            try:
                # Run the workflow
                result = await claim_processor.ainvoke(state)
                
                # Format output
                actual = {
                    "claim_id": result.get("claim_id") or "MOCK_CLAIM_ID",
                    "decision": result.get("decision"),
                    "approved_amount": result.get("approved_amount", 0.0),
                    "confidence_score": result.get("confidence_score", 1.0),
                    "reasons": result.get("reasons", []) + ([result.get("error_message")] if result.get("error_message") else []),
                    "trace": result.get("trace", []),
                    "financial_breakdown": result.get("financial_calculation"),
                    "manual_review_recommended": result.get("manual_review_recommended", False)
                }
                
                passed, notes = cls.evaluate_test_case(case_id, actual, expected)
                if passed:
                    passed_count += 1
                    status = "PASSED"
                else:
                    status = "FAILED"
                    
                results.append({
                    "case_id": case_id,
                    "case_name": name,
                    "description": desc,
                    "status": status,
                    "notes": notes,
                    "expected": expected,
                    "actual": actual
                })
                
            except Exception as e:
                logger.error(f"Error running case {case_id}: {str(e)}", exc_info=True)
                results.append({
                    "case_id": case_id,
                    "case_name": name,
                    "description": desc,
                    "status": "ERROR",
                    "notes": f"Pipeline crashed: {str(e)}",
                    "expected": expected,
                    "actual": {"decision": None, "approved_amount": 0.0, "confidence_score": 0.0, "reasons": [str(e)], "trace": []}
                })

        report = {
            "total_cases": len(results),
            "passed_cases": passed_count,
            "failed_cases": len(results) - passed_count,
            "success_rate_percent": (passed_count / len(results)) * 100 if results else 0,
            "results": results
        }
        
        # Save to file
        report_path = Path(__file__).resolve().parent / "eval_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
            
        return report

if __name__ == "__main__":
    res = asyncio.run(EvalRunner.run_all())
    print(f"Evaluations complete! Passed: {res['passed_cases']}/{res['total_cases']} ({res['success_rate_percent']:.1f}%)")
