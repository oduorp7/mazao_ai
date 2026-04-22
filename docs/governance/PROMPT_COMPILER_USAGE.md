# Mazao AI Prompt Compiler

Enforces `docs/governance/EXECUTION_KERNEL.json` rules on task inputs.

## Usage

```bash
python tools/kernel_prompt_compiler.py --input <task_input.json> [--output <compiled_prompt.json>]
```

## Failure
Exits non-zero if:
- Kernel is missing.
- Required fields are missing.
- Previous mandate is not verified complete.
- Scope lock is empty.
- Completion instruction is non-compliant.
