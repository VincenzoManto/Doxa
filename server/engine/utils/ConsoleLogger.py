
"""
utils.ConsoleLogger
-------------------
ANSI-coloured terminal output used throughout the simulation engine.

All methods accept plain Python data (strings, numbers, dicts) and emit
formatted lines to stdout.  Colour/bold ANSI escape sequences make
simulation logs readable at a glance:

  * Epoch & step banners are printed in bold white/magenta.
  * Successful actions are green; failures are red.
  * Trades are cyan with actor identifiers.
  * Kills are displayed on a red background.
  * Victories are bold yellow.
  * Resource deltas show green triangles (gains) and red inverted-triangles (losses).

The logger is instantiated once by ``SimulationEnvironment`` and shared
with all sub-systems via ``env.log``.
"""

# ==========================================
# 1. UI & LOGGING
# ==========================================

class ConsoleLogger:
    """Stateless ANSI-coloured terminal printer for the Doxa engine."""
    def print_header(self, text): print(f"\n\033[96m{'═'*60}\n{text}\n{'═'*60}\033[0m")
    def print_epoch(self, n): print(f"\n\033[1;35m--- EPOCH {n} STARTING ---\033[0m")
    def print_step(self, step): print(f"\n\033[1;37m{'—'*20} GLOBAL STEP {step} {'—'*20}\033[0m")
    def print_kill(self, agent_id, reason): print(f"\n\033[41mAGENT {agent_id.upper()} KILLED: {reason}\033[0m")
    def print_turn(self, agent_id): print(f"\n\033[1;33m► TURN: {agent_id.upper()}\033[0m")
    def print_think(self, agent_id, thought): print(f"\033[90m[{agent_id}] THINK: {thought}\033[0m")
    def print_action(self, agent_id, action, target, res):
        color = "\033[32m" if "SUCCESS" in res else "\033[31m"
        tgt = f" on {target}" if target else ""
        print(f"  \033[36m└─ [ACTION] {action}{tgt} -> {color}{res}\033[0m")
    def print_delta(self, before, after):
        for res in set(before.keys()) | set(after.keys()):
            diff = after.get(res, 0) - before.get(res, 0)
            if diff > 0: print(f"     \033[92m▲ +{diff} {res}\033[0m")
            elif diff < 0: print(f"     \033[91m▼ {diff} {res}\033[0m")
    def print(self, text): print(f"\033[90m{text}\033[0m")
    def print_communication(self, sender, message, target = "PUBLIC"):
        color = "\033[34m" if target == "PUBLIC" else "\033[35m"
        print(f"{color}[{sender} -> {target}]: {message}\033[0m")
    def print_trade(self, agent_id, target, give_res, give_qty, take_res, take_qty, result):
        color = "\033[32m" if "SUCCESS" in str(result) else "\033[31m"
        print(f"\033[36m[{agent_id} → {target}] TRADE: {give_qty}×{give_res} ↔ {take_qty}×{take_res} → {color}{result}\033[0m")
    def print_victory(self, text): print(f"\n\033[1;93m🏆 VICTORY: {text}\033[0m")
    def print_market_fill(self, buyer, seller, qty, resource, price, currency):
        print(f"\033[96m[MARKET] {buyer} ← {qty}×{resource} ← {seller} @ {price} {currency}\033[0m")
