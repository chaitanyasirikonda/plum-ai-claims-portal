from typing import TypedDict, List, Dict, Any, Optional
from backend.app.schemas.claim import ClaimProcessRequest, TraceStep, FinancialBreakdown

class ClaimState(TypedDict):
    # Inputs
    request: ClaimProcessRequest
    policy_terms: Dict[str, Any]
    
    # Internal State
    member: Optional[Dict[str, Any]]
    extracted_docs: Dict[str, Dict[str, Any]]  # file_id -> extracted data
    validation_results: Dict[str, Any]
    fraud_signals: List[Dict[str, Any]]
    financial_calculation: Optional[Dict[str, Any]]
    
    # Output State
    claim_id: Optional[str]
    decision: Optional[str]  # APPROVED, PARTIAL, REJECTED, MANUAL_REVIEW
    approved_amount: float
    confidence_score: float
    reasons: List[str]
    trace: List[Dict[str, Any]]
    manual_review_recommended: bool
    
    # Pipeline Control
    stop_processing: bool
    error_message: Optional[str]
