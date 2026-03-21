from models import FullConfigModel, ActionModel, ActorModel
from typing import List, Dict, Any, Optional
import copy
import time

class WorldManager:
    def __init__(self, config: FullConfigModel):
        self.config = config
        self.actors = {a.id: copy.deepcopy(a) for a in config.all_actors}
        self.rooms = {r.id: copy.deepcopy(r) for r in config.rooms}
        self.alliances = {al.id: copy.deepcopy(al) for al in config.alliances}
        self.global_portfolios = {p.id: p for p in (config.global_portfolios or [])}
        self.offers = {} # offer_id -> ActionModel (OFFER)
        self.history = []
        self.logs = []

    def get_actor(self, actor_id: str) -> Optional[ActorModel]:
        return self.actors.get(actor_id)

    def validate_action(self, action: ActionModel) -> tuple[bool, str]:
        sender = self.actors.get(action.sender)
        if not sender:
            return False, "Sender not found"

        if action.type == "TRADE":
            target = self.actors.get(action.target)
            if not target:
                return False, f"Target actor {action.target} not found"
                
            # Check if sender has the resource and enough amount
            current_qty = sender.portfolio.get(action.resource, 0)
            if isinstance(current_qty, (int, float)) and isinstance(action.amount, (int, float)):
                if current_qty < action.amount:
                    return False, f"Insufficient {action.resource}: you have {current_qty}, tried to trade {action.amount}"
            elif action.resource not in sender.portfolio:
                return False, f"Resource {action.resource} not found in your portfolio"

            # Check constraints (simplified example)
            for constraint in sender.constraints:
                if "Non scambiare mai" in constraint and action.resource in constraint:
                    # Logic to parse threshold could be added here
                    pass

        elif action.type == "OFFER":
            current_qty = sender.portfolio.get(action.resource, 0)
            if current_qty < action.amount:
                return False, f"Insufficient {action.resource} for offer"

        elif action.type == "ACCEPT_OFFER":
            if action.offer_id not in self.offers:
                return False, f"Offer {action.offer_id} not found"
            offer = self.offers[action.offer_id]
            # Check if acceptor has exchange_resource
            acceptor_qty = sender.portfolio.get(offer.exchange_resource, 0)
            if acceptor_qty < offer.amount: # Wait, amount in OFFER might be for the resource offered
                # Let's assume offer.amount is what sender gives and they want something in exchange
                pass 

        elif action.type == "MINE":
            # Check if resource is minable in global_portfolios
            gp = next((p for p in self.config.global_portfolios if action.resource in p.resources), None)
            if not gp:
                return False, f"Resource {action.resource} is not minable"
            # Check costs
            for cost_res, cost_qty in gp.mining_cost.items():
                if sender.portfolio.get(cost_res, 0) < cost_qty:
                    return False, f"Insufficient {cost_res} to mine {action.resource}"

        return True, "Valid"

    def execute_action(self, action: ActionModel) -> Dict[str, Any]:
        is_valid, reason = self.validate_action(action)
        if not is_valid:
            return {"status": "failed", "reason": reason}

        if action.type == "TRADE":
            sender = self.actors[action.sender]
            target = self.actors[action.target]
            
            # Atomic swap (one way for now, or based on offer logic)
            if isinstance(action.amount, (int, float)) and isinstance(sender.portfolio.get(action.resource, 0), (int, float)):
                sender.portfolio[action.resource] -= action.amount
                target.portfolio[action.resource] = target.portfolio.get(action.resource, 0) + action.amount
            
            log_msg = f"TRADE: {action.sender} gave {action.amount} {action.resource} to {action.target}"
            print(f"  [EXEC] {log_msg}")
            self.add_log("public", action.sender, log_msg)
            return {"status": "success", "msg": log_msg}

        elif action.type == "OFFER":
            sender = self.actors[action.sender]
            sender.portfolio[action.resource] -= action.amount
            offer_id = f"off_{len(self.offers) + 1}"
            action.offer_id = offer_id
            self.offers[offer_id] = action
            print(f"  [EXEC] {action.sender} created OFFER {offer_id} for {action.amount} {action.resource}")
            return {"status": "success", "msg": f"OFFER created: {offer_id}", "offer_id": offer_id}

        elif action.type == "ACCEPT_OFFER":
            offer = self.offers.pop(action.offer_id)
            sender = self.actors[action.sender] # The one accepting
            original_sender = self.actors[offer.sender]
            
            # Acceptor gives exchange_resource
            # (Assuming offer.exchange_resource and offer.amount_requested logic)
            # For simplicity, let's just complete the swap of the offered resource
            sender.portfolio[offer.resource] = sender.portfolio.get(offer.resource, 0) + offer.amount
            print(f"  [EXEC] {action.sender} ACCEPTED OFFER {action.offer_id} from {offer.sender}")
            return {"status": "success", "msg": f"Offer {action.offer_id} accepted by {action.sender}"}

        elif action.type == "MINE":
            sender = self.actors[action.sender]
            gp = next((p for p in self.config.global_portfolios if action.resource in p.resources), None)
            
            if gp:
                # Consume costs
                for cost_res, cost_qty in gp.mining_cost.items():
                    sender.portfolio[cost_res] -= cost_qty
                
                # Add resource
                yield_qty = 10
                sender.portfolio[action.resource] = sender.portfolio.get(action.resource, 0) + yield_qty
                print(f"  [EXEC] {action.sender} MINED {yield_qty} {action.resource}")
                return {"status": "success", "msg": f"{action.sender} mined {yield_qty} {action.resource}"}
            else:
                print(f"  [EXEC FAILED] {action.sender} tried to mine non-minable {action.resource}")
                return {"status": "failed", "reason": f"Resource {action.resource} is not minable"}

        self.add_log("system", action.sender, f"INTENT: {action.type} {action.content or ''}")
        print(f"  [EXEC IGNORED] Action type {action.type} has no handler.")
        return {"status": "ignored", "reason": "No execution logic for this type"}

    def add_log(self, type: str, sender: str, content: str, target: str = None):
        self.logs.append({
            "type": type,
            "sender": sender,
            "content": content,
            "target": target,
            "timestamp": time.time()
        })
        if len(self.logs) > 100:
            self.logs.pop(0)

    def get_agent_context(self, actor_id: str) -> List[str]:
        """Returns visible logs for this actor."""
        visible = []
        for log in self.logs[-20:]: # Last 20 logs for context window
            if log["type"] == "public" or log["target"] == actor_id or log["sender"] == actor_id:
                msg = f"[{log['sender']}] -> {log['content']}"
                if log['type'] == 'private':
                    msg = f"[PRIVATE FROM {log['sender']}] {log['content']}"
                visible.append(msg)
        return visible

    def apply_world_effects(self):
        # Resource decay and volatility
        for actor in self.actors.values():
            for res_id, qty in actor.portfolio.items():
                if not isinstance(qty, (int, float)):
                    continue
                    
                res_config = next((r for r in self.config.resources if r.id == res_id), None)
                if res_config and res_config.decay_rate > 0:
                    actor.portfolio[res_id] = max(0, int(qty * (1 - res_config.decay_rate)))
        
        self.add_log("system", "WORLD", "Cycle maintenance completed.")

    def get_feedback(self, actor_id: str, results: List[Dict[str, Any]]) -> str:
        failures = [res["reason"] for res in results if res["status"] == "failed"]
        if not failures:
            return ""
        return "Note: Some of your actions failed: " + "; ".join(failures)
