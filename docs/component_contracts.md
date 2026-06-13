# Component Contracts - Health Insurance Claims Processing System

This document defines the interface specifications, schemas, error expectations, and boundary guarantees for the system's core components.

---

## 1. REST API Router Endpoints

### 1.1 Claims Processing Endpoint
- **URL Path**: `POST /claims/process`
- **Request Input (JSON)**: `ClaimProcessRequest`
  - `member_id`: String (Roster key e.g., `EMP001`)
  - `policy_id`: String (Policy identification e.g., `PLUM_GHI_2024`)
  - `claim_category`: Enum (`CONSULTATION`, `DIAGNOSTIC`, `PHARMACY`, `DENTAL`, `VISION`, `ALTERNATIVE_MEDICINE`)
  - `treatment_date`: String in ISO date format (`YYYY-MM-DD`)
  - `claimed_amount`: Float (value >= 500)
  - `documents`: Array of `DocumentInput` objects
    - `file_id`: String
    - `file_name`: String (optional)
    - `actual_type`: String (`PRESCRIPTION`, `HOSPITAL_BILL`, `PHARMACY_BILL`, `LAB_REPORT`, etc.)
    - `quality`: String (`GOOD`, `UNREADABLE`, `POOR`)
    - `patient_name_on_doc`: String (optional)
    - `content`: Object (optional mock metadata extraction values)
- **Response Output (JSON)**: `ClaimProcessResponse`
  - `claim_id`: String (Unique claim transaction key)
  - `decision`: String/Null (`APPROVED`, `PARTIAL`, `REJECTED`, `MANUAL_REVIEW`)
  - `approved_amount`: Float (Calculated benefits approved)
  - `confidence_score`: Float (Bounded `0.0` to `1.0`)
  - `reasons`: Array of Strings (Rejection/review reason flags)
  - `trace`: Array of `TraceStep` records
  - `financial_breakdown`: `FinancialBreakdown` object or null
  - `manual_review_recommended`: Boolean
- **Validation Guarantees**:
  - Rejects category types that do not match the standard OPD category list.
  - Ensures a date format of `YYYY-MM-DD` is supplied.
  - Halts early with `null` decision if critical documents are missing or marked as `UNREADABLE`.

### 1.2 Evaluation Dashboard Endpoint
- **URL Path**: `POST /evals/run`
- **Request Input**: None
- **Response Output (JSON)**:
  - `total_cases`: Integer
  - `passed_cases`: Integer
  - `failed_cases`: Integer
  - `success_rate_percent`: Float
  - `results`: Array of evaluation records containing expected vs actual decisions and outputs.

---

## 2. OCR Agent
- **Interface**: `ocr_agent.py`
- **Method**: `async def extract_document_content(file_id, file_name, actual_type, quality, content_mock) -> Tuple[dict, float]`
- **Inputs**:
  - Document registration info, filename, and type configuration.
  - Quality setting (e.g. `UNREADABLE`).
- **Outputs**:
  - Dict containing extracted data elements (doctor registration numbers, medicine names, bill itemized amounts).
  - Confidence impact score offset (e.g. `-0.4` for unreadable or `-0.15` for poor quality).
- **Error Contract**:
  - Does not throw an exception on invalid file data; logs the error, reduces confidence, and returns default structures to allow the pipeline to proceed in a degraded state.

---

## 3. Entity Validation Agent
- **Interface**: `validation_agent.py`
- **Method 1**: `def is_fuzzy_match(name1, name2, threshold=0.8) -> bool`
  - Computes edit similarity between two patient names, stripping clinical prefixes (Dr., Vaidya, etc.).
- **Method 2**: `def validate_doctor_registration(reg_num) -> Tuple[bool, str]`
  - Validates a registration number against standard Indian formats: e.g. state pattern `^[A-Z]{2}/\d{3,6}/\d{4}$` or ayurveda national pattern `^AYUR/[A-Z]{2}/\d{3,6}/\d{4}$`.
- **Validation Guarantees**:
  - Ensures the patient's name matches either the primary employee or a registered family dependent listed in the active group roster. Mismatches block approval.

---

## 4. Policy Engine
- **Interface**: `policy_engine.py`
- **Inputs**:
  - Loaded terms dictionary from `policy_terms.json`.
- **Method**: `calculate_benefits(category, claimed_amount, hospital_name, line_items, ytd_claims_amount) -> Tuple[float, dict, list]`
- **Outputs**:
  - Approved financial amount (float).
  - Financial breakdown details containing network hospital discount applied first, category co-pay percentage applied second, exclusions deducted, and sub-limit capping.
  - List of rule violation tags (e.g. `PER_CLAIM_EXCEEDED`, `SUB_LIMIT_EXCEEDED`).
- **Validation Guarantees**:
  - Dynamically enforces category-specific caps and exclusions.
  - Performs waiting period math against the member join date.
  - Performs pre-authorization checks for high-value diagnostic procedures (MRI / CT scans > ₹10,000).
