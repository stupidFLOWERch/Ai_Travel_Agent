"""
Evaluation script for multi-agent travel assistant.

Evaluates:
1. Supervisor Routing — did supervisor produce correct task list?
2. Tool Selection — did agent call correct tools? (optional tools are skipped if not called)
3. Argument Extraction — did agent pass correct args?

Usage:
    python evaluate.py --test-cases test_cases.json --output report.json --delay 5
"""

import json
import argparse
import asyncio
from typing import Any
from mcp_client import MCPLangGraphAgent


# ============================================================
# Load test cases
# ============================================================

def load_test_cases(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["test_cases"]


# ============================================================
# Comparison helpers
# ============================================================

def normalize_value(value):
    """Normalize values for comparison."""
    if isinstance(value, str):
        return value.replace("-", "_")
    return value


def match_value(actual: Any, expected: Any, tolerance=None) -> bool:
    """Check if scalar actual matches expected, with optional tolerance."""
    if actual is None and expected is None:
        return True

    # Float/numeric comparison
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        # Range tolerance: {"min": x, "max": y}
        if isinstance(tolerance, dict) and "min" in tolerance and "max" in tolerance:
            return tolerance["min"] <= actual <= tolerance["max"]
        
        # List tolerance: check if actual is close to any value in list
        if isinstance(tolerance, list):
            for t in tolerance:
                if isinstance(t, (int, float)) and abs(actual - t) <= 0.05:
                    return True
        
        # Exact match (with tiny float epsilon)
        return abs(actual - expected) < 1e-6

    # String comparison
    actual_norm = normalize_value(actual)
    expected_norm = normalize_value(expected)

    if actual_norm == expected_norm:
        return True

    if tolerance and isinstance(tolerance, list):
        tolerance_norm = [normalize_value(t) for t in tolerance]
        if actual_norm in tolerance_norm:
            return True

    return False

def match_value_recursive(actual, expected, tolerance=None) -> bool:
    """Recursively match actual vs expected with nested tolerance."""
    if actual is None and expected is None:
        return True

    # Expected is dict → recurse per field
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        for key, expected_val in expected.items():
            actual_val = actual.get(key)
            tol = tolerance.get(key) if isinstance(tolerance, dict) else None
            if not match_value_recursive(actual_val, expected_val, tol):
                return False
        return True

    # Expected is list → recurse per index
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return False
        for i, expected_item in enumerate(expected):
            actual_item = actual[i]
            tol_item = tolerance[i] if isinstance(tolerance, list) else None
            if not match_value_recursive(actual_item, expected_item, tol_item):
                return False
        return True

    # Scalar → use match_value
    return match_value(actual, expected, tolerance)

def match_args(actual_args: dict, expected_args: dict, tolerance: dict = None) -> dict:
    """Compare args field by field, with recursive support."""
    tolerance = tolerance or {}
    field_matches = {}
    mismatched = {}

    for field, expected_value in expected_args.items():
        if expected_value is None:
            continue

        actual_value = actual_args.get(field)
        tol = tolerance.get(field)

        # ← 改这里
        if match_value_recursive(actual_value, expected_value, tol):
            field_matches[field] = True
        else:
            field_matches[field] = False
            mismatched[field] = (actual_value, expected_value)

    missing = [f for f in expected_args if f not in actual_args]
    extra = [f for f in actual_args if f not in expected_args]

    return {
        "match": all(field_matches.values()) if field_matches else False,
        "field_matches": field_matches,
        "missing_fields": missing,
        "extra_fields": extra,
        "mismatched_fields": mismatched,
    }

# ============================================================
# Evaluation layers
# ============================================================

def evaluate_supervisor_routing(
    actual_supervisor: dict,
    expected_supervisor: dict,
) -> dict:
    """Layer 1: Did supervisor produce correct agent + task_type?"""
    if not actual_supervisor or not actual_supervisor.get("tasks"):
        return {"match": False, "reason": "No supervisor output"}

    actual_task = actual_supervisor["tasks"][0]

    agent_match = actual_task.get("agent") == expected_supervisor.get("agent")
    type_match = actual_task.get("task_type") == expected_supervisor.get("task_type")

    return {
        "match": agent_match and type_match,
        "agent_match": agent_match,
        "task_type_match": type_match,
        "actual": {
            "agent": actual_task.get("agent"),
            "task_type": actual_task.get("task_type"),
        },
        "expected": expected_supervisor,
    }


def evaluate_tool_selection(
    actual_tool: str,
    expected_tool: str,
) -> dict:
    """Layer 2: Did agent call the correct tool?"""
    return {
        "match": actual_tool == expected_tool,
        "actual": actual_tool,
        "expected": expected_tool,
    }


def evaluate_arg_extraction(
    actual_args: dict,
    expected_args: dict,
    tolerance: dict,
) -> dict:
    """Layer 3: Did agent pass correct args?"""
    return match_args(actual_args, expected_args, tolerance)


# ============================================================
# Main evaluation loop
# ============================================================

def evaluate_case(test_case: dict, agent_output: dict) -> dict:
    result = {
        "id": test_case["id"],
        "category": test_case["category"],
        "query": test_case["query"],
    }

    # Layer 1: Supervisor routing
    result["supervisor_routing"] = evaluate_supervisor_routing(
        agent_output.get("supervisor"),
        test_case["expected_supervisor"],
    )

    # Layer 2 & 3: Multi-tool evaluation
    expected_tools = test_case.get("expected_tools", [])
    actual_tool_calls = agent_output.get("tool_calls", [])

    # Case A: no expected tools (out_of_scope)
    if not expected_tools:
        result["tool_selection"] = {
            "match": True,
            "reason": "No expected tools (out of scope)",
        }
        result["arg_extraction"] = {
            "match": True,
            "reason": "No expected tools (out of scope)",
        }
        return result

    # Case B: no tool called by agent
    if not actual_tool_calls:
        result["tool_selection"] = {"match": False, "reason": "No tool called"}
        result["arg_extraction"] = {"match": False, "reason": "No tool called"}
        return result

    # Case C: evaluate each expected tool
    tool_results = []

    for expected in expected_tools:
        tool_name = expected["tool_name"]
        expected_args = expected.get("args", {}) or {}
        tolerance = expected.get("tolerance", {}) or {}
        is_optional = expected.get("optional", False)

        # Find matching calls
        matching_calls = [
            tc for tc in actual_tool_calls
            if tc["tool_name"] == tool_name
        ]

        if not matching_calls:
            tool_results.append({
                "tool_name": tool_name,
                "optional": is_optional,
                "called": False,
                "args_match": False,
                "args_detail": None,
                "reason": "Tool not called",
            })
            continue

        # Check if ANY matching call has correct args
        args_match = False
        args_detail = None
        for tc in matching_calls:
            args_result = evaluate_arg_extraction(
                tc.get("args", {}),
                expected_args,
                tolerance,
            )
            if args_result["match"]:
                args_match = True
                args_detail = args_result
                break
            elif args_detail is None:
                args_detail = args_result

        tool_results.append({
            "tool_name": tool_name,
            "optional": is_optional,
            "called": True,
            "call_count": len(matching_calls),
            "args_match": args_match,
            "args_detail": args_detail,
        })

    # Aggregate — ignore optional tools that weren't called
    required_tools = [r for r in tool_results if not r["optional"]]
    optional_tools = [r for r in tool_results if r["optional"]]

    # Tool selection: all required tools must be called
    tools_all_called = all(r["called"] for r in required_tools) if required_tools else True

    # Args extraction: all required tools must have matching args
    # For optional tools: only check if they WERE called
    required_args_match = all(
        r["called"] and r["args_match"]
        for r in required_tools
    ) if required_tools else True

    optional_args_match = all(
        r["args_match"] for r in optional_tools if r["called"]
    )

    result["tool_selection"] = {
        "match": tools_all_called,
        "expected_tools": [t["tool_name"] for t in expected_tools],
        "actual_tools": [tc["tool_name"] for tc in actual_tool_calls],
        "per_tool": tool_results,
    }

    result["arg_extraction"] = {
        "match": required_args_match and optional_args_match,
        "per_tool": [
            {
                "tool_name": r["tool_name"],
                "optional": r["optional"],
                "called": r["called"],
                "args_match": r["args_match"],
                "args_detail": r.get("args_detail"),
            }
            for r in tool_results
        ],
    }

    return result


# ============================================================
# Report generation
# ============================================================

def generate_report(results: list[dict]) -> dict:
    """Aggregate results into a report."""
    total = len(results)

    supervisor_correct = sum(1 for r in results if r["supervisor_routing"].get("match"))
    tool_correct = sum(1 for r in results if r["tool_selection"].get("match"))
    args_correct = sum(1 for r in results if r["arg_extraction"].get("match"))

    # Per-category breakdown
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {
                "total": 0,
                "supervisor_correct": 0,
                "tool_correct": 0,
                "args_correct": 0,
            }
        categories[cat]["total"] += 1
        if r["supervisor_routing"].get("match"):
            categories[cat]["supervisor_correct"] += 1
        if r["tool_selection"].get("match"):
            categories[cat]["tool_correct"] += 1
        if r["arg_extraction"].get("match"):
            categories[cat]["args_correct"] += 1

    return {
        "summary": {
            "total_cases": total,
            "supervisor_routing_accuracy": supervisor_correct / total if total else 0,
            "tool_selection_accuracy": tool_correct / total if total else 0,
            "arg_extraction_accuracy": args_correct / total if total else 0,
        },
        "per_category": categories,
        "failed_cases": [
            {
                "id": r["id"],
                "query": r["query"],
                "supervisor_match": r["supervisor_routing"].get("match"),
                "tool_match": r["tool_selection"].get("match"),
                "args_match": r["arg_extraction"].get("match"),
                "tool_detail": r["tool_selection"],
                "args_detail": r["arg_extraction"],
                "supervisor_detail": r["supervisor_routing"],
            }
            for r in results
            if not (
                r["supervisor_routing"].get("match")
                and r["tool_selection"].get("match")
                and r["arg_extraction"].get("match")
            )
        ],
    }


# ============================================================
# Async query with retry
# ============================================================

async def query_with_retry(agent, query, max_retries=3):
    """Call agent.query with retry on 429."""
    for attempt in range(max_retries):
        try:
            return await agent.query(query)
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                if attempt < max_retries - 1:
                    wait = 60 * (attempt + 1)
                    print(f"⚠️ 429 rate limit, waiting {wait}s (attempt {attempt+1}/{max_retries})...")
                    await asyncio.sleep(wait)
                    continue
            raise


# ============================================================
# Entry point
# ============================================================

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-cases", default="test_cases.json")
    parser.add_argument("--output", default="report.json")
    parser.add_argument("--limit", type=int, default=None, help="Only run first N test cases")
    parser.add_argument("--delay", type=float, default=5.0, help="Delay between test cases (seconds)")
    args = parser.parse_args()

    test_cases = load_test_cases(args.test_cases)
    test_cases = test_cases[25:30]

    if args.limit:
        test_cases = test_cases[:args.limit]

    print(f"Loaded {len(test_cases)} test cases")

    agent = MCPLangGraphAgent()
    await agent.setup()

    try:
        results = []
        for i, tc in enumerate(test_cases):
            print(f"\nRunning {tc['id']}: {tc['query'][:60]}...")

            try:
                agent_output = await query_with_retry(agent, tc["query"])
            except Exception as e:
                print(f"❌ Query failed: {e}")
                agent_output = {
                    "supervisor": None,
                    "tool_calls": [],
                    "final_answer": None,
                    "error": str(e),
                }

            result = evaluate_case(tc, agent_output)
            results.append(result)

            # Print per-case summary
            sup = "✅" if result["supervisor_routing"].get("match") else "❌"
            tool = "✅" if result["tool_selection"].get("match") else "❌"
            ar = "✅" if result["arg_extraction"].get("match") else "❌"
            print(f"  Supervisor: {sup}  Tool: {tool}  Args: {ar}")

            if i < len(test_cases) - 1 and args.delay > 0:
                await asyncio.sleep(args.delay)

        report = generate_report(results)

        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)

        print("\n" + "=" * 60)
        print("EVALUATION REPORT")
        print("=" * 60)
        print(f"Total cases: {report['summary']['total_cases']}")
        print(f"Supervisor Routing Accuracy: {report['summary']['supervisor_routing_accuracy']:.2%}")
        print(f"Tool Selection Accuracy: {report['summary']['tool_selection_accuracy']:.2%}")
        print(f"Argument Extraction Accuracy: {report['summary']['arg_extraction_accuracy']:.2%}")
        print(f"\nFailed cases: {len(report['failed_cases'])}")
        for fc in report["failed_cases"]:
            print(f"  - {fc['id']}: {fc['query'][:60]}...")
        print(f"\nFull report saved to {args.output}")

    finally:
        await agent.teardown()


if __name__ == "__main__":
    asyncio.run(main())