import pytest
from backend.app.schemas.claim import ClaimProcessRequest, DocumentInput
from backend.app.workflows.claim_workflow import claim_processor
from backend.app.utils.config import Config

@pytest.fixture
def policy_terms():
    return Config.load_policy_terms()

@pytest.mark.asyncio
async def test_workflow_clean_consultation(policy_terms):
    # Setup a clean consultation claim process request
    req = ClaimProcessRequest(
        member_id="EMP001",
        policy_id="PLUM_GHI_2024",
        claim_category="CONSULTATION",
        treatment_date="2024-11-01",
        claimed_amount=1500,
        ytd_claims_amount=5000,
        documents=[
            DocumentInput(
                file_id="F007",
                actual_type="PRESCRIPTION",
                content={
                    "doctor_name": "Dr. Arun Sharma",
                    "doctor_registration": "KA/45678/2015",
                    "patient_name": "Rajesh Kumar",
                    "date": "2024-11-01",
                    "diagnosis": "Viral Fever",
                    "medicines": ["Paracetamol 650mg", "Vitamin C 500mg"]
                }
            ),
            DocumentInput(
                file_id="F008",
                actual_type="HOSPITAL_BILL",
                content={
                    "hospital_name": "City Clinic, Bengaluru",
                    "patient_name": "Rajesh Kumar",
                    "date": "2024-11-01",
                    "line_items": [
                        { "description": "Consultation Fee", "amount": 1000 },
                        { "description": "CBC Test", "amount": 300 },
                        { "description": "Dengue NS1 Test", "amount": 200 }
                    ],
                    "total": 1500
                }
            )
        ]
    )

    state = {
        "request": req,
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

    result = await claim_processor.ainvoke(state)
    assert result["decision"] == "APPROVED"
    assert result["approved_amount"] == 1350.0
    assert result["confidence_score"] >= 0.85
    # Verify trace steps exist
    steps = [t["step"] for t in result["trace"]]
    assert "claim_intake" in steps
    assert "document_verification" in steps
    assert "ocr_extraction" in steps
    assert "entity_validation" in steps
    assert "policy_validation" in steps
    assert "financial_calculation" in steps

@pytest.mark.asyncio
async def test_workflow_missing_document(policy_terms):
    # Consultation requires PRESCRIPTION and HOSPITAL_BILL. Submit only PRESCRIPTION
    req = ClaimProcessRequest(
        member_id="EMP001",
        policy_id="PLUM_GHI_2024",
        claim_category="CONSULTATION",
        treatment_date="2024-11-01",
        claimed_amount=1500,
        documents=[
            DocumentInput(file_id="F001", file_name="rx.jpg", actual_type="PRESCRIPTION")
        ]
    )

    state = {
        "request": req,
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

    result = await claim_processor.ainvoke(state)
    assert result["decision"] is None
    assert result["stop_processing"] is True
    assert "Early document rejection" in result["error_message"]

@pytest.mark.asyncio
async def test_workflow_component_failure(policy_terms):
    # TC011: Component failure mid-processing, pipeline must continue in degraded state
    req = ClaimProcessRequest(
        member_id="EMP006",
        policy_id="PLUM_GHI_2024",
        claim_category="ALTERNATIVE_MEDICINE",
        treatment_date="2024-10-28",
        claimed_amount=4000,
        simulate_component_failure=True,
        documents=[
            DocumentInput(
                file_id="F021",
                actual_type="PRESCRIPTION",
                content={
                    "doctor_name": "Vaidya T. Krishnan",
                    "doctor_registration": "AYUR/KL/2345/2019",
                    "diagnosis": "Chronic Joint Pain",
                    "treatment": "Panchakarma Therapy"
                }
            ),
            DocumentInput(
                file_id="F022",
                actual_type="HOSPITAL_BILL",
                content={
                    "hospital_name": "Ayur Wellness Centre",
                    "total": 4000,
                    "line_items": [
                        { "description": "Panchakarma Therapy (5 sessions)", "amount": 3000 },
                        { "description": "Consultation", "amount": 1000 }
                    ]
                }
            )
        ]
    )

    state = {
        "request": req,
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

    result = await claim_processor.ainvoke(state)
    assert result["decision"] == "APPROVED"
    assert result["approved_amount"] == 4000.0
    assert result["confidence_score"] < 0.8  # Degraded confidence
    assert result["manual_review_recommended"] is True
    # Verify failed step in trace
    steps_status = {t["step"]: t["status"] for t in result["trace"]}
    assert steps_status["ocr_extraction"] == "FAILED"
