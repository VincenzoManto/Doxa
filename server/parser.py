import re
from typing import List, Dict, Any, Optional
from models import ActionModel

class ActionParser:
    # Regex patterns for XML-like tags
    THOUGHT_PATTERN = re.compile(r'<THOUGHT>(.*?)(?:</THOUGHT>|$)', re.DOTALL | re.IGNORECASE)
    PUBLIC_MSG_PATTERN = re.compile(r'<PUBLIC_MSG>(.*?)</PUBLIC_MSG>', re.DOTALL | re.IGNORECASE)
    PRIVATE_MSG_PATTERN = re.compile(r'<PRIVATE_MSG\s+target="([^"]+)"\s*>(.*?)</PRIVATE_MSG>', re.DOTALL | re.IGNORECASE)
    ACTION_PATTERN = re.compile(r'<ACTION>(.*?)</ACTION>', re.DOTALL | re.IGNORECASE)
    
    # Specific command patterns inside <ACTION> tags
    TRADE_PATTERN = re.compile(r'TRADE\s*\(\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^)]+)\s*\)', re.IGNORECASE)
    # Generic command pattern: CMD(arg1, arg2, ...)
    GENERIC_CMD_PATTERN = re.compile(r'(\w+)\s*\((.*?)\)', re.IGNORECASE)

    @classmethod
    def parse(cls, actor_id: str, text: str) -> Dict[str, Any]:
        results: Dict[str, Any] = {
            "thought": "",
            "public_msg": "",
            "private_msgs": [],
            "actions": []
        }

        # Extract Thought
        thought_match = cls.THOUGHT_PATTERN.search(text)
        if thought_match:
            results["thought"] = thought_match.group(1).strip()

        # Extract Public Message
        public_match = cls.PUBLIC_MSG_PATTERN.search(text)
        if public_match:
            results["public_msg"] = public_match.group(1).strip()

        # Extract Private Messages
        for match in cls.PRIVATE_MSG_PATTERN.finditer(text):
            results["private_msgs"].append({
                "target": match.group(1),
                "content": match.group(2).strip()
            })

        # Extract Actions
        action_matches = list(cls.ACTION_PATTERN.finditer(text))
        
        # If no <ACTION> tags found, look for raw commands (lenient fallback)
        if not action_matches:
             # Look for TRADE
             for match in cls.TRADE_PATTERN.finditer(text):
                  amt_str = match.group(3).strip()
                  try: amt = int(amt_str)
                  except: amt = amt_str
                  results["actions"].append(ActionModel(
                      type="TRADE", sender=actor_id,
                      target=match.group(1).strip(),
                      resource=match.group(2).strip(),
                      amount=amt,
                      exchange_resource=match.group(4).strip()
                  ))
             # Look for generic CMDs (excluding TRADE which we handled)
             for match in cls.GENERIC_CMD_PATTERN.finditer(text):
                  cmd_type = match.group(1).upper()
                  if cmd_type == "TRADE": continue
                  results["actions"].append(ActionModel(
                      type=cmd_type, sender=actor_id,
                      content=match.group(2).strip(),
                      resource=match.group(2).strip().split(',')[0]
                  ))
        else:
            for match in action_matches:
                action_text = match.group(1).strip()
                # ... existing parsing logic ...
                trade_match = cls.TRADE_PATTERN.search(action_text)
                if trade_match:
                    amt_str = trade_match.group(3).strip()
                    try: amt = int(amt_str)
                    except: amt = amt_str
                    results["actions"].append(ActionModel(
                        type="TRADE", sender=actor_id,
                        target=trade_match.group(1).strip(),
                        resource=trade_match.group(2).strip(),
                        amount=amt,
                        exchange_resource=trade_match.group(4).strip()
                    ))
                    continue

                cmd_match = cls.GENERIC_CMD_PATTERN.search(action_text)
                if cmd_match:
                    results["actions"].append(ActionModel(
                        type=cmd_match.group(1).upper(), sender=actor_id,
                        content=cmd_match.group(2).strip(),
                        resource=cmd_match.group(2).strip().split(',')[0]
                    ))
                    continue
                
                results["actions"].append(ActionModel(type="GENERIC", sender=actor_id, content=action_text))

        return results

class ActionValidator:
    @staticmethod
    def validate(action: ActionModel, world_manager) -> bool:
        """Helper to check if an action is broadly valid before execution."""
        if action.sender not in world_manager.actors:
            return False
            
        # Basic validation exists in WorldManager.validate_action
        valid, _ = world_manager.validate_action(action.sender, action)
        return valid
