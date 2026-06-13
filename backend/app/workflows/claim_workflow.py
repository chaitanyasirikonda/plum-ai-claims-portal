import logging
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
from langgraph.graph import StateGraph, END

from backend.app.workflows.state import ClaimState
from backend.app.agents.ocr_agent import OCRAgent
from backend.app.agents.validation_agent import ValidationAgent
from backend.app.policy.policy_engine import PolicyEngine
from backend.app.services.claim_store import claim_store

logger = logging.getLogger(__name__)

# Initialize agents
ocr_agent = OCRAgent()
validation_agent = ValidationAgent()

async def claim_intake_node(state: ClaimState) -> ClaimState:
    """Stage 1: Claim Intake & Member verification"""
    req = state["request"]
    policy_terms = state["policy_terms"]
    
    trace_step = {
        "step": "claim_intake",
        "status": "PASSED",
        "details": f"Intake completed for member {req.member_id} under policy {req.policy_id}.",
        "confidence_impact": 0.0
    }
    
    engine = PolicyEngine(policy_terms)
    member = engine.find_member(req.member_id)
    if not member:
        state["member"] = None
        state["stop_processing"] = True
        state["decision"] = "REJECTED"
        state["reasons"].append("MEMBER_NOT_FOUND")
        trace_step["status"] = "FAILED"
        trace_step["details"] = f"Member ID {req.member_id} not found in roster."
        trace_step["confidence_impact"] = -0.5
        state["trace"].append(trace_step)
        state["confidence_score"] = max(0.0, state["confidence_score"] - 0.5)
        return state
        
    state["member"] = member
    
    # Validate general policy date eligibility
    eligible, msg = engine.validate_member_eligibility(req.member_id, req.treatment_date)
    if not eligible:
        state["stop_processing"] = True
        state["decision"] = "REJECTED"
        state["reasons"].append("POLICY_DATE_INVALID")
        trace_step["status"] = "FAILED"
        trace_step["details"] = msg
        trace_step["confidence_impact"] = -0.5
        state["trace"].append(trace_step)
        state["confidence_score"] = max(0.0, state["confidence_score"] - 0.5)
        return state
        
    trace_step["details"] += f" Member: '{member.get('name')}' is active."
    state["trace"].append(trace_step)
    return state


async def document_verification_node(state: ClaimState) -> ClaimState:
    """Stage 2: Validate document existence, formats, and quality"""
    if state.get("stop_processing"):
        return state
        
    req = state["request"]
    policy_terms = state["policy_terms"]
    
    trace_step = {
        "step": "document_verification",
        "status": "PASSED",
        "details": "All required document types present.",
        "confidence_impact": 0.0
    }
    
    # Check category requirements from policy
    category_reqs = policy_terms.get("document_requirements", {}).get(req.claim_category)
    if not category_reqs:
        # Fallback to general
        required_types = ["PRESCRIPTION", "HOSPITAL_BILL"]
    else:
        required_types = category_reqs.get("required", [])

    uploaded_types = [doc.actual_type for doc in req.documents if doc.actual_type]
    
    # 1. Check for missing required types (TC001)
    missing_types = [t for t in required_types if t not in uploaded_types]
    if missing_types:
        state["stop_processing"] = True
        state["decision"] = None  # Stops before making a claim decision as per TC001
        msg = f"Early document rejection: Claim category '{req.claim_category}' requires document types: {required_types}. Uploaded: {uploaded_types}. Missing: {missing_types}."
        state["error_message"] = msg
        
        trace_step["status"] = "FAILED"
        trace_step["details"] = msg
        trace_step["confidence_impact"] = -0.5
        state["trace"].append(trace_step)
        state["confidence_score"] = max(0.0, state["confidence_score"] - 0.5)
        return state
        
    # 2. Check for unreadable documents (TC002)
    for doc in req.documents:
        if doc.quality == "UNREADABLE":
            state["stop_processing"] = True
            state["decision"] = None
            msg = f"Document unreadable: The uploaded '{doc.actual_type}' ({doc.file_name or 'file'}) is unreadable. Please re-upload this specific document."
            state["error_message"] = msg
            
            trace_step["status"] = "FAILED"
            trace_step["details"] = msg
            trace_step["confidence_impact"] = -0.4
            state["trace"].append(trace_step)
            state["confidence_score"] = max(0.0, state["confidence_score"] - 0.4)
            return state

    state["trace"].append(trace_step)
    return state


async def ocr_extraction_node(state: ClaimState) -> ClaimState:
    """Stage 3: Extract structured fields using OCR / Vision LLM"""
    if state.get("stop_processing"):
        return state
        
    req = state["request"]
    
    # Simulate a component failure if requested (TC011)
    if req.simulate_component_failure:
        trace_step = {
            "step": "ocr_extraction",
            "status": "FAILED",
            "details": "Simulated component failure in OCR extraction stage. Skipping detailed parsing.",
            "confidence_impact": -0.3
        }
        state["trace"].append(trace_step)
        state["confidence_score"] = max(0.0, state["confidence_score"] - 0.3)
        state["manual_review_recommended"] = True
        # In a failed OCR state, we fall back to mock extraction but record the failure
        # Let's populate minimal extracted data using mocks to let subsequent stages run
    else:
        trace_step = {
            "step": "ocr_extraction",
            "status": "PASSED",
            "details": "Extracted structured text from documents successfully.",
            "confidence_impact": 0.0
        }
        state["trace"].append(trace_step)

    # Process all documents
    for doc in req.documents:
        try:
            # If component failure is simulated, we will reduce confidence, but we must still extract 
            # some structured content (using our fallback helper) so the policy engine doesn't crash 
            # and can approve the claim in a degraded state.
            extracted, impact = await ocr_agent.extract_document_content(
                file_id=doc.file_id,
                file_name=doc.file_name,
                actual_type=doc.actual_type,
                quality=doc.quality or "GOOD",
                content_mock=doc.content
            )
            if doc.patient_name_on_doc:
                extracted["patient_name"] = doc.patient_name_on_doc
            state["extracted_docs"][doc.file_id] = extracted
            if not req.simulate_component_failure and impact != 0:
                state["confidence_score"] = max(0.0, state["confidence_score"] + impact)
                # Append sub-step details to trace if there was poor quality
                if impact < 0:
                    state["trace"].append({
                        "step": f"ocr_extraction_quality_{doc.file_id}",
                        "status": "WARNING",
                        "details": f"Reduced confidence due to poor quality of {doc.actual_type}: {impact}",
                        "confidence_impact": impact
                    })
        except Exception as e:
            logger.error(f"OCR Node failure on doc {doc.file_id}: {str(e)}")
            state["confidence_score"] = max(0.0, state["confidence_score"] - 0.3)
            state["manual_review_recommended"] = True
            state["trace"].append({
                "step": f"ocr_extraction_error_{doc.file_id}",
                "status": "FAILED",
                "details": f"Error during OCR extraction on {doc.actual_type}: {str(e)}",
                "confidence_impact": -0.3
            })
            
    return state


async def entity_validation_node(state: ClaimState) -> ClaimState:
    """Stage 4: Entity Validation (Patient Name Matching & Doctor Registration Check)"""
    if state.get("stop_processing"):
        return state
        
    req = state["request"]
    member = state["member"]
    policy_terms = state["policy_terms"]
    
    trace_step = {
        "step": "entity_validation",
        "status": "PASSED",
        "details": "Patient name and doctor registrations validated.",
        "confidence_impact": 0.0
    }

    # 1. Compile valid covered names list (Primary member + dependents)
    all_members = policy_terms.get("members", [])
    primary_member_id = member.get("member_id")
    covered_names = [member.get("name", "").lower()]
    
    for m in all_members:
        if m.get("primary_member_id") == primary_member_id:
            covered_names.append(m.get("name", "").lower())
            
    # 2. Match patient name on all documents
    for file_id, ext_data in state["extracted_docs"].items():
        patient_name = ext_data.get("patient_name")
        doc_input = next((d for d in req.documents if d.file_id == file_id), None)
        
        # If patient name is missing from extracted data, check if it was passed in metadata
        if not patient_name and doc_input:
            patient_name = doc_input.patient_name_on_doc
            
        if patient_name:
            patient_name_clean = patient_name.strip().lower()
            
            # Fuzzy match against all allowed covered names
            matched = False
            for covered_name in covered_names:
                if validation_agent.is_fuzzy_match(patient_name_clean, covered_name):
                    matched = True
                    break
            
            if not matched:
                state["stop_processing"] = True
                state["decision"] = None  # Stop before claim decision (TC003)
                
                # Retrieve primary member name
                primary_name = member.get("name")
                msg = f"Patient mismatch: Document for patient '{patient_name}' does not match policy member '{primary_name}' or any covered dependents."
                state["error_message"] = msg
                
                trace_step["status"] = "FAILED"
                trace_step["details"] = msg
                trace_step["confidence_impact"] = -0.5
                state["trace"].append(trace_step)
                state["confidence_score"] = max(0.0, state["confidence_score"] - 0.5)
                return state

    # 3. Doctor registration format validation (for prescriptions)
    for file_id, ext_data in state["extracted_docs"].items():
        doc_input = next((d for d in req.documents if d.file_id == file_id), None)
        if doc_input and doc_input.actual_type == "PRESCRIPTION":
            doctor_reg = ext_data.get("doctor_registration")
            if doctor_reg:
                valid, reg_msg = validation_agent.validate_doctor_registration(doctor_reg)
                if not valid:
                    state["confidence_score"] = max(0.0, state["confidence_score"] - 0.1)
                    state["trace"].append({
                        "step": "doctor_registration_check",
                        "status": "WARNING",
                        "details": reg_msg,
                        "confidence_impact": -0.1
                    })
            else:
                # No doctor registration on prescription
                state["confidence_score"] = max(0.0, state["confidence_score"] - 0.1)
                state["trace"].append({
                    "step": "doctor_registration_check",
                    "status": "WARNING",
                    "details": "Prescription has no doctor registration number.",
                    "confidence_impact": -0.1
                })

    state["trace"].append(trace_step)
    return state


async def policy_validation_node(state: ClaimState) -> ClaimState:
    """Stage 5: Policy Validation (Exclusions, Waiting periods, Pre-authorization)"""
    if state.get("stop_processing"):
        return state
        
    req = state["request"]
    policy_terms = state["policy_terms"]
    engine = PolicyEngine(policy_terms)
    
    trace_step = {
        "step": "policy_validation",
        "status": "PASSED",
        "details": "Policy coverage, exclusions, waiting periods, and pre-auth checked.",
        "confidence_impact": 0.0
    }
    
    # 1. Determine diagnosis
    diagnosis = None
    tests_ordered = []
    line_item_descriptions = []
    line_item_amounts = []
    
    for file_id, ext in state["extracted_docs"].items():
        if ext.get("diagnosis"):
            diagnosis = ext["diagnosis"]
        if ext.get("tests_ordered"):
            tests_ordered.extend(ext["tests_ordered"])
        if ext.get("line_items"):
            for item in ext["line_items"]:
                line_item_descriptions.append(item.get("description", ""))
                line_item_amounts.append(float(item.get("amount", 0.0)))
        elif ext.get("total") and not ext.get("line_items"):
            line_item_descriptions.append(req.claim_category)
            line_item_amounts.append(float(ext.get("total")))

    # 2. Check exclusions (diagnosis level exclusions reject the entire claim, while procedure level exclusions are handled at line-item level in financial calculation)
    valid_exclusions, excl_msg, excl_reasons = engine.check_exclusions(diagnosis, [])
    if not valid_exclusions:
        state["decision"] = "REJECTED"
        state["reasons"].extend(excl_reasons)
        state["stop_processing"] = True
        
        trace_step["status"] = "FAILED"
        trace_step["details"] = excl_msg
        state["trace"].append(trace_step)
        return state

    # 3. Check waiting periods (TC005)
    valid_wp, wp_msg, wp_reasons = engine.check_waiting_periods(req.member_id, req.treatment_date, diagnosis)
    if not valid_wp:
        state["decision"] = "REJECTED"
        state["reasons"].extend(wp_reasons)
        state["stop_processing"] = True
        
        trace_step["status"] = "FAILED"
        trace_step["details"] = wp_msg
        state["trace"].append(trace_step)
        return state

    # 4. Check pre-authorization (TC007)
    # Check if pre-auth was submitted (or simulated in mock/claims_history)
    pre_auth_submitted = False
    # If the request contains manual claim history indicating pre-auth was approved, check it:
    if req.claims_history:
        for history in req.claims_history:
            if history.get("pre_auth_approved") or history.get("pre_auth"):
                pre_auth_submitted = True
                
    valid_pre_auth, pre_auth_msg, pre_auth_reasons = engine.check_pre_authorization(
        req.claim_category, line_item_descriptions, line_item_amounts, pre_auth_submitted
    )
    if not valid_pre_auth:
        state["decision"] = "REJECTED"
        state["reasons"].extend(pre_auth_reasons)
        state["stop_processing"] = True
        
        trace_step["status"] = "FAILED"
        trace_step["details"] = f"{pre_auth_msg} Please obtain pre-authorization from the insurer and resubmit."
        state["trace"].append(trace_step)
        return state

    state["trace"].append(trace_step)
    return state


async def fraud_detection_node(state: ClaimState) -> ClaimState:
    """Stage 6: Fraud Signals detection (Same day claim count, limits, etc.)"""
    if state.get("stop_processing"):
        return state
        
    req = state["request"]
    policy_terms = state["policy_terms"]
    
    trace_step = {
        "step": "fraud_detection",
        "status": "PASSED",
        "details": "Fraud check completed. No anomalies found.",
        "confidence_impact": 0.0
    }

    # Retrieve fraud configuration limits
    fraud_config = policy_terms.get("fraud_thresholds", {})
    same_day_limit = fraud_config.get("same_day_claims_limit", 2)
    monthly_limit = fraud_config.get("monthly_claims_limit", 6)
    high_value_limit = fraud_config.get("high_value_claim_threshold", 25000)

    # 1. Build claims list
    # Use claims_history passed in request (TC009) or claim_store database
    history = req.claims_history or claim_store.get_member_history(req.member_id)
    
    same_day_claims = 0
    monthly_claims = 0
    treatment_dt = datetime.strptime(req.treatment_date, "%Y-%m-%d")

    for clm in history:
        clm_date_str = clm.get("date") or clm.get("treatment_date")
        if not clm_date_str:
            continue
            
        clm_dt = datetime.strptime(clm_date_str, "%Y-%m-%d")
        if clm_dt.date() == treatment_dt.date():
            same_day_claims += 1
        if clm_dt.month == treatment_dt.month and clm_dt.year == treatment_dt.year:
            monthly_claims += 1

    # 2. Evaluate same day limits (TC009)
    # Note: if there are 3 history items on the same day, this is the 4th, which is > limit of 2.
    if same_day_claims >= same_day_limit:
        state["decision"] = "MANUAL_REVIEW"
        state["reasons"].append("FRAUD_SIGNAL")
        state["manual_review_recommended"] = True
        
        msg = f"Fraud Alert: Member has submitted {same_day_claims} other claims on the same day ({req.treatment_date}). Same-day limit is {same_day_limit}. Routing to manual review."
        state["error_message"] = msg
        trace_step["status"] = "WARNING"
        trace_step["details"] = msg
        trace_step["confidence_impact"] = -0.25
        state["confidence_score"] = max(0.0, state["confidence_score"] - 0.25)
        state["trace"].append(trace_step)
        return state

    # 3. Evaluate monthly limits
    if monthly_claims >= monthly_limit:
        state["decision"] = "MANUAL_REVIEW"
        state["reasons"].append("FRAUD_SIGNAL")
        state["manual_review_recommended"] = True
        
        msg = f"Fraud Alert: Member has submitted {monthly_claims} claims this month, exceeding the monthly limit of {monthly_limit}. Routing to manual review."
        state["error_message"] = msg
        trace_step["status"] = "WARNING"
        trace_step["details"] = msg
        trace_step["confidence_impact"] = -0.15
        state["confidence_score"] = max(0.0, state["confidence_score"] - 0.15)
        state["trace"].append(trace_step)
        return state

    # 4. Evaluate high-value auto review thresholds
    if req.claimed_amount >= high_value_limit:
        state["decision"] = "MANUAL_REVIEW"
        state["reasons"].append("HIGH_VALUE_CLAIM")
        state["manual_review_recommended"] = True
        msg = f"Audit Note: Claimed amount ₹{req.claimed_amount} exceeds the auto-review threshold of ₹{high_value_limit}. Routing to manual review."
        trace_step["status"] = "WARNING"
        trace_step["details"] = msg
        state["trace"].append(trace_step)
        return state

    state["trace"].append(trace_step)
    return state


async def financial_calculation_node(state: ClaimState) -> ClaimState:
    """Stage 7: Financial Calculation (Network discounts, Copays, sub-limits)"""
    if state.get("stop_processing") and state["decision"] == "REJECTED":
        state["approved_amount"] = 0.0
        return state
        
    req = state["request"]
    policy_terms = state["policy_terms"]
    engine = PolicyEngine(policy_terms)
    
    trace_step = {
        "step": "financial_calculation",
        "status": "PASSED",
        "details": "Calculated final approved amount.",
        "confidence_impact": 0.0
    }

    # Assemble line items from extracted docs
    line_items = []
    for file_id, ext in state["extracted_docs"].items():
        if ext.get("line_items"):
            line_items.extend(ext["line_items"])
            
    # If no line items were extracted, fallback to single total line item
    if not line_items:
        line_items = [{"description": req.claim_category, "amount": req.claimed_amount}]

    # Compute
    approved_amt, breakdown, calc_reasons = engine.calculate_benefits(
        category=req.claim_category,
        claimed_amount=req.claimed_amount,
        hospital_name=req.hospital_name or next((ext.get("hospital_name") for ext in state["extracted_docs"].values() if ext.get("hospital_name")), None),
        line_items=line_items,
        ytd_claims_amount=req.ytd_claims_amount or 0.0
    )

    state["approved_amount"] = approved_amt
    state["financial_calculation"] = breakdown
    
    if "PER_CLAIM_EXCEEDED" in calc_reasons:
        state["decision"] = "REJECTED"
        state["reasons"].append("PER_CLAIM_EXCEEDED")
        state["stop_processing"] = True
        
        trace_step["status"] = "FAILED"
        trace_step["details"] = breakdown.get("notes")
        state["trace"].append(trace_step)
        return state
        
    if "SUB_LIMIT_EXCEEDED" in calc_reasons:
        trace_step["status"] = "WARNING"
        trace_step["details"] = f"Claim partially approved: {breakdown.get('notes')}"
        state["trace"].append(trace_step)
        return state

    trace_step["details"] = f"Claim approved: {breakdown.get('notes') or 'Full approval.'}"
    state["trace"].append(trace_step)
    return state


async def decision_composition_node(state: ClaimState) -> ClaimState:
    """Stage 8: Synthesize the final decision status and trace mapping"""
    req = state["request"]
    
    # 1. Determine decision value
    if state.get("stop_processing") and state.get("decision") is None:
        # Keep it as None or whatever was set (early halt)
        pass
    elif state["decision"] == "REJECTED":
        state["approved_amount"] = 0.0
    elif state["decision"] == "MANUAL_REVIEW":
        # Financial breakdown should still be computed if possible
        pass
    else:
        # If any items were rejected at the line level or sub-limit applied, it's a PARTIAL decision
        # Let's verify line level rejection (e.g. TC006 Cosmetic exclusion)
        calc = state["financial_calculation"]
        if calc:
            has_rejected_lines = any(l.get("rejected", False) for l in calc.get("itemized_lines", []))
            has_sublimit_cap = calc.get("sub_limit_applied") is not None
            
            if has_rejected_lines or has_sublimit_cap:
                state["decision"] = "PARTIAL"
                if has_rejected_lines:
                    state["reasons"].append("EXCLUDED_TREATMENT")
                if has_sublimit_cap:
                    state["reasons"].append("SUB_LIMIT_EXCEEDED")
            else:
                state["decision"] = "APPROVED"
        else:
            state["decision"] = "APPROVED"

    # Make sure we bound the confidence score between 0.0 and 1.0
    state["confidence_score"] = min(1.0, max(0.0, state["confidence_score"]))

    # Save claim in store
    claim_id = claim_store.save_claim(state)
    
    trace_step = {
        "step": "decision_composition",
        "status": "PASSED",
        "details": f"Composed final decision: {state['decision']}. Approved amount: ₹{state['approved_amount']:.2f}. Confidence: {state['confidence_score']:.2f}",
        "confidence_impact": 0.0
    }
    state["trace"].append(trace_step)
    return state

# Define state graph transitions and routing
def route_graph(state: ClaimState):
    if state.get("stop_processing") and state.get("decision") is None:
        # Halt early before claim decision
        return "decision_composition"
    return None

def build_claim_workflow():
    workflow = StateGraph(ClaimState)
    
    # Add nodes
    workflow.add_node("claim_intake", claim_intake_node)
    workflow.add_node("document_verification", document_verification_node)
    workflow.add_node("ocr_extraction", ocr_extraction_node)
    workflow.add_node("entity_validation", entity_validation_node)
    workflow.add_node("policy_validation", policy_validation_node)
    workflow.add_node("fraud_detection", fraud_detection_node)
    workflow.add_node("financial_calculation", financial_calculation_node)
    workflow.add_node("decision_composition", decision_composition_node)
    
    # Set entry point
    workflow.set_entry_point("claim_intake")
    
    # Simple sequential flow with early exit checks
    # LangGraph allows conditional edges to halt early
    def check_early_exit(state: ClaimState):
        if state.get("stop_processing"):
            return "decision_composition"
        return "continue"

    # Add edges
    workflow.add_conditional_edges(
        "claim_intake",
        check_early_exit,
        {"decision_composition": "decision_composition", "continue": "document_verification"}
    )
    
    workflow.add_conditional_edges(
        "document_verification",
        check_early_exit,
        {"decision_composition": "decision_composition", "continue": "ocr_extraction"}
    )
    
    workflow.add_conditional_edges(
        "ocr_extraction",
        check_early_exit,
        {"decision_composition": "decision_composition", "continue": "entity_validation"}
    )
    
    workflow.add_conditional_edges(
        "entity_validation",
        check_early_exit,
        {"decision_composition": "decision_composition", "continue": "policy_validation"}
    )
    
    workflow.add_conditional_edges(
        "policy_validation",
        check_early_exit,
        {"decision_composition": "decision_composition", "continue": "fraud_detection"}
    )
    
    workflow.add_conditional_edges(
        "fraud_detection",
        check_early_exit,
        {"decision_composition": "decision_composition", "continue": "financial_calculation"}
    )
    
    workflow.add_edge("financial_calculation", "decision_composition")
    workflow.add_edge("decision_composition", END)
    
    return workflow.compile()

# Global compiled workflow graph
claim_processor = build_claim_workflow()
