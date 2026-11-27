"""Pure engineering command planner. Execution stays in Hermes' terminal backend."""
import json

# Fixed commands only. No repository paths, shell fragments, or model-supplied
# arguments are interpolated. Commands assume a trusted repository root.
CHECKS = {
    "diff": ("git diff --check HEAD --", "0 = clean; nonzero = inspect error or whitespace finding"),
    "python_lint": ("ruff check .", "0 = clean; 1 = findings; other = tool error"),
    "python_types": ("mypy .", "0 = clean; nonzero = findings or tool error"),
    "python_security": ("bandit -r . -x ./.git,./.venv,./venv,./node_modules", "0 = no findings at configured threshold; nonzero = findings or error"),
    "python_dependencies": ("pip-audit", "0 = no known vulnerabilities in audited environment; nonzero = findings or error"),
    "js_lint": ("./node_modules/.bin/eslint .", "0 = clean; 1 = findings; 2 = configuration/tool error"),
    "js_types": ("./node_modules/.bin/tsc --noEmit", "0 = clean; nonzero = findings or error"),
    "js_dependencies": ("npm audit --json", "0 = no findings at configured threshold; nonzero = inspect JSON or error"),
    "go_static": ("go vet ./...", "0 = clean; nonzero = findings or error"),
    "rust_static": ("cargo clippy --all-targets -- -D warnings", "0 = clean; nonzero = findings or error"),
    "ast_search_help": ("ast-grep run --help", "0 = available; use a separate targeted structural search in terminal"),
}
PROFILES = {
    "python": ("diff", "python_lint", "python_types", "python_security"),
    "javascript": ("diff", "js_lint", "js_types"),
    "go": ("diff", "go_static"),
    "rust": ("diff", "rust_static"),
    "generic": ("diff",),
}
NETWORK_CHECKS = {"python": "python_dependencies", "javascript": "js_dependencies"}

def plan(args, **kwargs):
    """Return suggestions, never execute commands or read host files."""
    if not isinstance(args, dict):
        return json.dumps({"error": "Expected an object"})
    language = args.get("language", "generic")
    network = args.get("network", False)
    if not isinstance(language, str) or language not in PROFILES:
        return json.dumps({"error": "Unsupported language"})
    if type(network) is not bool:
        return json.dumps({"error": "network must be a boolean"})
    names = list(PROFILES[language])
    if network and language in NETWORK_CHECKS:
        names.append(NETWORK_CHECKS[language])
    return json.dumps({
        "status": "planned_not_run",
        "language": language,
        "checks": [{"id": name, "command": CHECKS[name][0],
                    "interpretation": CHECKS[name][1]} for name in names],
        "structural_search": CHECKS["ast_search_help"][0],
        "execution": "Use Hermes terminal in the trusted project environment; never execute through a plugin host subprocess.",
        "cautions": [
            "Prefer repository-defined CI commands and configuration; these are fallback suggestions.",
            "Do not install dependencies or tools automatically. Report unavailable, timed out, and failed checks distinctly.",
            "Build tools, linters and configuration can execute project code; use an approved isolated environment for untrusted repositories.",
            "Go and Rust checks may fetch dependencies. Offline policy must be enforced by the terminal environment.",
            "Dependency audits may transmit package metadata and require explicit authorization.",
            "git diff HEAD excludes untracked files and does not replace the base-to-head review diff.",
            "A clean check is not proof of correctness or security. Run the acceptance suite and retain risk-tier review."
        ],
    })

def register_engineering(ctx):
    ctx.register_tool(
        name="dev_pipeline_engineering_plan",
        toolset="dev-pipeline",
        schema={
            "name": "dev_pipeline_engineering_plan",
            "description": "Plan deterministic engineering checks for a language. Does not run commands or grant network access.",
            "parameters": {"type": "object", "properties": {
                "language": {"type": "string", "enum": list(PROFILES)},
                "network": {"type": "boolean", "description": "Include dependency audit suggestions only if authorized; default false."}
            }, "required": ["language"], "additionalProperties": False}
        },
        handler=plan,
        description="Plan deterministic engineering checks without executing them",
    )
