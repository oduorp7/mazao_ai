import json
import argparse
import sys
import os

KERNEL_PATH = "docs/governance/EXECUTION_KERNEL.json"
REQUIRED_FIELDS = ["prompt_id", "previous_mandate_gate", "objective", "scope_lock", "completion_instruction"]
EXPECTED_COMPLETION = "return under 120 lines machine readable report for supervisors"

def load_kernel():
    if not os.path.exists(KERNEL_PATH):
        print(f"ERROR: Kernel not found at {KERNEL_PATH}")
        sys.exit(1)
    with open(KERNEL_PATH, 'r') as f:
        return json.load(f)

def validate_task_input(data):
    # 1. Check required fields
    for field in REQUIRED_FIELDS:
        if field not in data or not data[field]:
            print(f"ERROR: Missing or empty required field: {field}")
            return False
            
    # 2. Validate completion instruction
    if data["completion_instruction"] != EXPECTED_COMPLETION:
        print(f"ERROR: Invalid completion_instruction. Must be: '{EXPECTED_COMPLETION}'")
        return False
        
    # 3. Validate previous mandate gate
    gate = data["previous_mandate_gate"]
    if not gate.get("verified_complete"):
        print("ERROR: Previous mandate must be verified_complete: true")
        return False
        
    # 4. Validate scope lock
    scope = data["scope_lock"]
    if not scope.get("allowed_files") or len(scope["allowed_files"]) == 0:
        print("ERROR: allowed_files must be provided and non-empty")
        return False
        
    return True

def compile_prompt(input_path, output_path=None):
    kernel = load_kernel()
    
    with open(input_path, 'r') as f:
        task_data = json.load(f)
        
    if not validate_task_input(task_data):
        sys.exit(1)
        
    # Inject kernel reference and roles if missing
    task_data["kernel_reference"] = {
        "file": KERNEL_PATH,
        "enforcement": kernel.get("status", "ACTIVE_MANDATORY")
    }
    
    if "roles" not in task_data:
        task_data["roles"] = kernel.get("identity", {}).get("supervisory_model_roles", [])

    if output_path:
        with open(output_path, 'w') as f:
            json.dump(task_data, f, indent=2)
        print(f"SUCCESS: Compiled prompt saved to {output_path}")
    else:
        print(json.dumps(task_data, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mazao AI Kernel Prompt Compiler")
    parser.add_argument("--input", required=True, help="Path to task input JSON")
    parser.add_argument("--output", help="Optional path for compiled output JSON")
    args = parser.parse_args()
    
    compile_prompt(args.input, args.output)
