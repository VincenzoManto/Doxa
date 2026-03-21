import re
from typing import Dict, Any

class ActionParser:
    # UPDATED Pattern from parser.py
    THOUGHT_PATTERN = re.compile(r'<THOUGHT>(.*?)(?:</THOUGHT>|$)', re.DOTALL | re.IGNORECASE)
    
    @classmethod
    def parse_thought(cls, text: str) -> str:
        match = cls.THOUGHT_PATTERN.search(text)
        if match:
            return match.group(1).strip()
        return ""

# Test Cases
test_cases = [
    ("<THOUGHT>Standard thought</THOUGHT>", "Standard thought"),
    ("<THOUGHT>Unclosed thought at end", "Unclosed thought at end"),
    ("<thought>Lowercase tag</thought>", "Lowercase tag"),
    ("Random text <THOUGHT>Embedded thought</THOUGHT> more text", "Embedded thought"),
    ("No thought here", "")
]

for text, expected in test_cases:
    result = ActionParser.parse_thought(text)
    print(f"Input: {text[:30]}... -> Result: '{result}' | Status: {'PASS' if result == expected else 'FAIL'}")
