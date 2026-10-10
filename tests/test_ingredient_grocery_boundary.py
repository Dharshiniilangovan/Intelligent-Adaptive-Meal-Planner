from src.agents.ingredient_agent import IngredientAgent
from src.agents.grocery_agent import GroceryAgent
from src.grocery.grocery_service import GroceryOption


class TestGroceryService:
    """Deterministic service for boundary testing."""

    def get_grocery_list(self, items,  recipe_id=None):
        return [
            GroceryOption(
                ingredient_id=item["ingredient_id"],
                ingredient_name=item["ingredient_name"],
                required_quantity=float(item["quantity"]),
                required_unit=item["unit"],
                product_name=f"Test product - {item['ingredient_name']}",
                package_quantity=500,
                package_unit="g",
                packages_needed=1,
                price_per_package=2.00,
                total_cost=2.00,
                currency="SGD",
                store="Test Store",
                match_status="matched",
                match_quality="exact",
            )
            for item in items
        ]


def test_ingredient_to_grocery_boundary():
    """Usable Ingredient Agent records can be consumed by Grocery Agent."""

    ingredient_agent = IngredientAgent()

    result = ingredient_agent.run(
        recipe_id="R03943",
        pantry={},
    )

    assert result["status"] in {"success", "partial"}

    ingredients = result["data"]["required_ingredients"]

    # Keep only ingredients that are usable by feasibility rules.
    from src.reasoning.feasibility import check_ingredient_feasibility

    usable = []

    for ingredient in ingredients:
        feasibility = check_ingredient_feasibility([ingredient])

        if feasibility["status"] == "pass":
            usable.append(ingredient)

    assert len(usable) > 0

    grocery_agent = GroceryAgent(
        grocery_service=TestGroceryService()
    )

    grocery_result = grocery_agent.run(
        recipe_id="R03943",
        missing_ingredients=usable,
    )

    assert grocery_result["agent"] == "grocery"
    assert grocery_result["status"] == "success"

    data = grocery_result["data"]

    assert data["recipe_id"] == "R03943"
    assert len(data["items"]) == len(usable)

    for item in data["items"]:
       assert item["ingredient_id"] is not None
       assert item["ingredient"] is not None
       assert item["required_quantity"] is not None
       assert item["required_unit"] is not None
