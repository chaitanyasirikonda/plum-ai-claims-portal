import pytest
from backend.app.policy.policy_engine import PolicyEngine
from backend.app.utils.config import Config

@pytest.fixture
def policy_terms():
    return Config.load_policy_terms()

@pytest.fixture
def engine(policy_terms):
    return PolicyEngine(policy_terms)

def test_member_eligibility(engine):
    # EMP001 is a valid employee active from 2024-04-01 to 2025-03-31
    valid, msg = engine.validate_member_eligibility("EMP001", "2024-11-01")
    assert valid is True
    
    # Invalid date
    valid, msg = engine.validate_member_eligibility("EMP001", "2023-11-01")
    assert valid is False
    
    # Unknown member
    valid, msg = engine.validate_member_eligibility("EMP_UNKNOWN", "2024-11-01")
    assert valid is False

def test_waiting_periods_diabetes(engine):
    # Member EMP005 Vikram Joshi joined 2024-09-01. Claim date 2024-10-15 (44 days after join)
    # Diabetes specific condition waiting period is 90 days.
    valid, msg, reasons = engine.check_waiting_periods("EMP005", "2024-10-15", "Type 2 Diabetes Mellitus")
    assert valid is False
    assert "WAITING_PERIOD" in reasons
    assert "2024-11-30" in msg  # join 2024-09-01 + 90 days = 2024-11-30

def test_waiting_periods_passed(engine):
    # Rajesh Kumar EMP001 joined 2024-04-01. Claim date 2024-11-01 (over 200 days after join)
    # Diabetes waiting period should pass
    valid, msg, reasons = engine.check_waiting_periods("EMP001", "2024-11-01", "Type 2 Diabetes Mellitus")
    assert valid is True
    assert not reasons

def test_exclusions_obesity(engine):
    # Obesity treatment is excluded
    valid, msg, reasons = engine.check_exclusions("Morbid Obesity - BMI 37", ["Bariatric Consultation"])
    assert valid is False
    assert "EXCLUDED_CONDITION" in reasons

def test_exclusions_passed(engine):
    # Viral fever is not excluded
    valid, msg, reasons = engine.check_exclusions("Viral Fever", ["Consultation Fee"])
    assert valid is True
    assert not reasons

def test_benefit_calculation_network_discount(engine):
    # Consultation at Apollo Hospitals (Network hospital)
    # Claimed amount 4500. Network discount 20% = 900. Remaining = 3600.
    # Copay 10% on 3600 = 360. Final approved = 3240.
    line_items = [
        {"description": "Consultation Fee", "amount": 1500},
        {"description": "Medicines", "amount": 3000}
    ]
    approved_amount, breakdown, reasons = engine.calculate_benefits(
        category="CONSULTATION",
        claimed_amount=4500,
        hospital_name="Apollo Hospitals",
        line_items=line_items
    )
    assert approved_amount == 3240.0
    assert breakdown["network_discount_amount"] == 900.0
    assert breakdown["copay_amount"] == 360.0
    assert breakdown["final_approved_amount"] == 3240.0
    assert not reasons

def test_benefit_calculation_dental_exclusions(engine):
    # Root canal (covered 8000) and Teeth whitening (excluded 4000)
    line_items = [
        {"description": "Root Canal Treatment", "amount": 8000},
        {"description": "Teeth Whitening", "amount": 4000}
    ]
    approved_amount, breakdown, reasons = engine.calculate_benefits(
        category="DENTAL",
        claimed_amount=12000,
        hospital_name="Smile Dental Clinic",
        line_items=line_items
    )
    assert approved_amount == 8000.0
    assert breakdown["exclusions_deducted"] == 4000.0
    assert breakdown["final_approved_amount"] == 8000.0
