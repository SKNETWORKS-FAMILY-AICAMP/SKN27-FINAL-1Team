import ast
from pathlib import Path


def test_cognito_mcp_scope_bundle_includes_inventory_write():
    stack_path = Path(__file__).parents[1] / "infra" / "bobbeori_stack.py"
    module = ast.parse(stack_path.read_text(encoding="utf-8"))
    assignment = next(
        node
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "MCP_SCOPE_NAMES"
            for target in node.targets
        )
    )
    scopes = ast.literal_eval(assignment.value)

    assert scopes == (
        "inventory.read",
        "recipe.read",
        "guide.read",
        "receipt.write",
        "shopping.write",
        "calendar.write",
        "inventory.write",
    )
