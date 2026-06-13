from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class DocumentInput(BaseModel):
    file_id: str
    file_name: Optional[str] = None
    actual_type: Optional[str] = None  # e.g., "PRESCRIPTION", "HOSPITAL_BILL", "PHARMACY_BILL", "LAB_REPORT"
    quality: Optional[str] = "GOOD"   # e.g., "GOOD", "UNREADABLE", "POOR"
    patient_name_on_doc: Optional[str] = None
    content: Optional[Dict[str, Any]] = None  # Mock content for extraction testing

class ClaimProcessRequest(BaseModel):
    member_id: str
    policy_id: str
    claim_category: str  # e.g., "CONSULTATION", "DIAGNOSTIC", "PHARMACY", "DENTAL", "VISION", "ALTERNATIVE_MEDICINE"
    treatment_date: str  # "YYYY-MM-DD"
    claimed_amount: float
    documents: List[DocumentInput]
    ytd_claims_amount: Optional[float] = 0.0
    hospital_name: Optional[str] = None
    simulate_component_failure: Optional[bool] = False
    claims_history: Optional[List[Dict[str, Any]]] = None

class TraceStep(BaseModel):
    step: str
    status: str  # "PASSED", "WARNING", "FAILED", "SKIPPED"
    details: str
    confidence_impact: float = 0.0

class FinancialBreakdown(BaseModel):
    claimed_amount: float
    network_discount_amount: float = 0.0
    copay_amount: float = 0.0
    sub_limit_applied: Optional[str] = None
    capped_amount: float
    final_approved_amount: float
    exclusions_deducted: float = 0.0
    itemized_lines: List[Dict[str, Any]] = []

class ClaimProcessResponse(BaseModel):
    claim_id: str
    member_id: str
    claim_category: str
    treatment_date: str
    claimed_amount: float
    decision: Optional[str]  # "APPROVED", "PARTIAL", "REJECTED", "MANUAL_REVIEW" (can be null if early stop)
    approved_amount: float
    confidence_score: float
    reasons: List[str]
    trace: List[TraceStep]
    financial_breakdown: Optional[FinancialBreakdown] = None
    manual_review_recommended: bool = False
