import logging
import uuid
from fastapi import APIRouter, HTTPException, Depends
from backend.app.schemas.claim import ClaimProcessRequest, ClaimProcessResponse
from backend.app.workflows.claim_workflow import claim_processor
from backend.app.services.claim_store import claim_store
from backend.app.utils.config import Config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/claims", tags=["Claims"])

@router.post("/process", response_model=ClaimProcessResponse)
async def process_claim(request: ClaimProcessRequest):
    try:
        # Load policy terms
        policy_terms = Config.load_policy_terms()
        
        # Initialize LangGraph State
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
        
        # Run workflow
        result = await claim_processor.ainvoke(state)
        
        # Compile response
        response = ClaimProcessResponse(
            claim_id=result.get("claim_id") or f"CLM_{uuid.uuid4().hex[:8].upper()}",
            member_id=request.member_id,
            claim_category=request.claim_category,
            treatment_date=request.treatment_date,
            claimed_amount=request.claimed_amount,
            decision=result.get("decision"),
            approved_amount=result.get("approved_amount", 0.0),
            confidence_score=result.get("confidence_score", 1.0),
            reasons=result.get("reasons", []),
            trace=result.get("trace", []),
            financial_breakdown=result.get("financial_calculation"),
            manual_review_recommended=result.get("manual_review_recommended", False)
        )
        
        # If stopped early, we can return the error message in the reasons or trace
        if result.get("error_message") and not response.reasons:
            response.reasons.append(result.get("error_message"))
            
        return response
        
    except Exception as e:
        logger.error(f"Error processing claim: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.get("/all")
async def get_all_claims():
    return claim_store.get_all_claims()

@router.get("/{id}", response_model=ClaimProcessResponse)
async def get_claim(id: str):
    claim = claim_store.get_claim(id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim with ID {id} not found.")
        
    # Build ClaimProcessResponse from stored state
    req = claim["request"]
    response = ClaimProcessResponse(
        claim_id=claim["claim_id"],
        member_id=req.member_id,
        claim_category=req.claim_category,
        treatment_date=req.treatment_date,
        claimed_amount=req.claimed_amount,
        decision=claim.get("decision"),
        approved_amount=claim.get("approved_amount", 0.0),
        confidence_score=claim.get("confidence_score", 1.0),
        reasons=claim.get("reasons", []),
        trace=claim.get("trace", []),
        financial_breakdown=claim.get("financial_calculation"),
        manual_review_recommended=claim.get("manual_review_recommended", False)
    )
    return response
