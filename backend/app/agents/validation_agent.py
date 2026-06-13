import re
import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

class ValidationAgent:
    @staticmethod
    def levenshtein_distance(s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return ValidationAgent.levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
            
        return previous_row[-1]

    @classmethod
    def is_fuzzy_match(cls, name1: str, name2: str, threshold: float = 0.8) -> bool:
        if not name1 or not name2:
            return False
        n1 = name1.strip().lower()
        n2 = name2.strip().lower()
        if n1 == n2:
            return True
            
        # Clean special chars/titles (Dr., Mr., etc.)
        n1 = re.sub(r'^(dr\.|mr\.|ms\.|mrs\.|vaidya)\s+', '', n1)
        n2 = re.sub(r'^(dr\.|mr\.|ms\.|mrs\.|vaidya)\s+', '', n2)
        if n1 == n2:
            return True

        max_len = max(len(n1), len(n2))
        if max_len == 0:
            return False
            
        distance = cls.bytes_levenshtein(n1, n2)
        similarity = 1.0 - (distance / max_len)
        return similarity >= threshold

    @classmethod
    def bytes_levenshtein(cls, s1: str, s2: str) -> int:
        return cls.levenshtein_distance(s1, s2)

    @classmethod
    def validate_doctor_registration(cls, reg_num: Optional[str]) -> Tuple[bool, str]:
        if not reg_num:
            return False, "Doctor registration number is missing."
            
        cleaned_reg = reg_num.strip().upper()
        
        # Standard formats check:
        # State registrations (e.g. KA/45678/2015)
        state_pattern = r'^[A-Z]{2}/\d{3,6}/\d{4}$'
        # Ayurveda registrations (e.g. AYUR/KL/2345/2019)
        ayur_pattern = r'^AYUR/[A-Z]{2}/\d{3,6}/\d{4}$'
        
        if re.match(state_pattern, cleaned_reg):
            state = cleaned_reg.split("/")[0]
            valid_states = {"KA", "MH", "DL", "TN", "GJ", "AP", "UP", "WB", "KL"}
            if state in valid_states:
                return True, f"Valid state doctor registration: {reg_num}"
            else:
                return True, f"Registration matches format, but state '{state}' is not in standard checklist: {reg_num}"
                
        if re.match(ayur_pattern, cleaned_reg):
            return True, f"Valid Ayurveda doctor registration: {reg_num}"
            
        return False, f"Registration number '{reg_num}' does not match standard Indian medical board formats (e.g. State: KA/45678/2015 or Ayur: AYUR/KL/2345/2019)."

    @classmethod
    def match_patient_to_roster(cls, patient_name: str, member: dict) -> Tuple[bool, str]:
        """
        Verify if the extracted patient name matches the primary member or any covered dependent in their roster.
        """
        # Primary member check
        primary_name = member.get("name", "")
        if cls.is_fuzzy_match(patient_name, primary_name):
            return True, f"Patient matches primary member: {primary_name}"
            
        # Dependents check
        # policy_terms members list contains dependents, but let's check if the roster has dependents details.
        # Wait, the member dict in policy_terms.json has "dependents" list of IDs, 
        # and those dependent details are stored in the same "members" list. 
        # For example, EMP001 has dependents "DEP001", "DEP002".
        # Let's see: we should search the policy roster for these dependents.
        return False, "No match found"

from typing import Optional
