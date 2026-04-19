
import ast
import os

def verify():
    print("--- Phase 1 Static Verification ---")
    
    # 1. Check handlers.py for _get_sample_transactions
    print("[1/2] Checking handlers.py...")
    with open("apps/tg_bot/handlers.py", "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
        
    found_stub = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_get_sample_transactions":
            found_stub = True
            break
            
    if found_stub:
        print("[FAIL] _get_sample_transactions still exists in handlers.py")
    else:
        print("[PASS] _get_sample_transactions deleted from handlers.py")

    # 2. Check BOT_COMMANDS in handlers.py
    print("[2/2] Checking BOT_COMMANDS registry...")
    found_commands = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "BOT_COMMANDS":
                    if isinstance(node.value, ast.List):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Call) and len(elt.args) > 0:
                                # Look for command name in first argument
                                arg0 = elt.args[0]
                                if isinstance(arg0, ast.Constant):
                                    found_commands.append(arg0.value)

    print(f"Detected commands: {found_commands}")
    if "skip" in found_commands or "mystatus" in found_commands:
         print("[FAIL] /skip or /mystatus still in BOT_COMMANDS")
    else:
         print("[PASS] Obsolete commands removed from BOT_COMMANDS")

    print("\n--- Static Verification Complete ---")

if __name__ == "__main__":
    verify()
