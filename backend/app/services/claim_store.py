import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

class ClaimStore:
    def __init__(self):
        self.claims: Dict[str, Dict[str, Any]] = {}
        # Pre-seed history for specific member fraud test cases (e.g. EMP008 same-day claims)
        self.mock_history: Dict[str, List[Dict[str, Any]]] = {
            "EMP008": [
                { "claim_id": "CLM_0081", "date": "2024-10-30", "amount": 1200, "provider": "City Clinic A" },
                { "claim_id": "CLM_0082", "date": "2024-10-30", "amount": 1800, "provider": "City Clinic B" },
                { "claim_id": "CLM_0083", "date": "2024-10-30", "amount": 2100, "provider": "Wellness Center" }
            ]
        }

    def save_claim(self, claim_data: Dict[str, Any]) -> str:
        claim_id = claim_data.get("claim_id") or f"CLM_{uuid.uuid4().hex[:8].upper()}"
        claim_data["claim_id"] = claim_id
        claim_data["created_at"] = datetime.utcnow().isoformat()
        self.claims[claim_id] = claim_data
        
        # Add to history
        member_id = claim_data.get("member_id")
        if member_id:
            history_item = {
                "claim_id": claim_id,
                "date": claim_data.get("treatment_date"),
                "amount": claim_data.get("claimed_amount"),
                "provider": claim_data.get("hospital_name") or "Unknown Provider"
            }
            if member_id not in self.mock_history:
                self.mock_history[member_id] = []
            self.mock_history[member_id].append(history_item)
            
        return claim_id

    def get_claim(self, claim_id: str) -> Optional[Dict[str, Any]]:
        return self.claims.get(claim_id)

    def get_member_history(self, member_id: str) -> List[Dict[str, Any]]:
        return self.mock_history.get(member_id, [])

    def get_all_claims(self) -> List[Dict[str, Any]]:
        return list(self.claims.values())

# Global in-memory instance
claim_store = ClaimStore()
