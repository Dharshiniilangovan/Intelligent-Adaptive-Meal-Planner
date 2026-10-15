"""Deterministic planning harness over the real Recipe KB.

Real: MultiMealPlanner, ManagerAgent (dietary, feasibility and
reasoning evaluators), IngredientAgent (normalized Ingredient KB),
GroceryAgent and the final basket / inventory / nutrition logic.

Mocked: the recipe candidate ranking (a fixed list of real KB recipe
IDs) and retail prices (a fixed catalog instead of live Tavily/Ollama).
"""
from functools import lru_cache

from src.agents.grocery_agent import GroceryAgent
from src.agents.ingredient_agent import IngredientAgent
from src.agents.manager import ManagerAgent
from src.grocery.grocery_service import GroceryOption
from src.grocery.units import to_base
from src.knowledge.repository import RecipeRepository
from src.planning.multi_meal_planner import MultiMealPlanner

# name -> (package quantity, package unit, price per package), SGD.
# Realistic retail units: many KB requirements are volumes of solids
# with no density (e.g. tahini, olives), so those package conversions
# are expected to stay unresolved.
CATALOG = {
    "basil": (1, "bunch", 1.80),
    "basil pesto": (190, "g", 4.20),
    "black olive": (300, "g", 3.60),
    "broccoli": (1, "head", 3.50),
    "bulgur": (500, "g", 3.30),
    "carrot": (500, "g", 1.60),
    "cashew nut": (150, "g", 4.50),
    "cauliflower": (1, "head", 3.80),
    "chickpea": (400, "g", 1.90),
    "curry powder": (100, "g", 2.40),
    "extra virgin olive oil": (500, "ml", 11.50),
    "feta cheese": (200, "g", 5.20),
    "garlic": (300, "g", 2.50),
    "green lentils": (500, "g", 2.90),
    "green onion": (1, "bunch", 1.20),
    "honey": (400, "g", 7.50),
    "kalamata olive": (300, "g", 4.80),
    "lemon juice": (250, "ml", 2.80),
    "mint": (1, "bunch", 1.50),
    "mushroom": (250, "g", 3.20),
    "olive oil": (500, "ml", 8.90),
    "onion": (1, "kg", 2.20),
    "oregano": (20, "g", 2.10),
    "parmesan": (200, "g", 6.50),
    "parmesan cheese": (200, "g", 6.50),
    "parsley": (1, "bunch", 1.50),
    "pasta": (500, "g", 1.45),
    "plum tomato": (500, "g", 2.60),
    "rosemary": (1, "bunch", 1.80),
    "salt": (500, "g", 0.90),
    "sesame oil": (150, "ml", 4.50),
    "spaghetti squash": (1, "pcs", 3.90),
    "sugar": (1, "kg", 2.10),
    "sun tomato in oil": (280, "g", 4.60),
    "sweet potato": (1, "kg", 3.40),
    "tahini": (250, "g", 5.90),
    "tomato": (500, "g", 2.60),
    "water": (1500, "ml", 1.00),
    "wheat": (1, "kg", 3.50),
}


def _default_package(unit):
    base = to_base(1.0, str(unit or "").strip().lower())
    family = base[1] if base else None
    if family == "g":
        return 500, "g", 3.00
    if family == "ml":
        return 500, "ml", 3.00
    if family == "pcs":
        return 6, "pcs", 3.00
    return 100, "g", 2.00


class CatalogGroceryService:
    """GroceryService stand-in: one fixed product per ingredient."""

    def __init__(self, unavailable=()):
        self.unavailable = set(unavailable)
        self.requests = []

    def get_grocery_list(self, items, recipe_id=None):
        options = []
        for item in items:
            name = item.get("ingredient_name") or item.get("ingredient")
            self.requests.append((recipe_id, name, item.get("quantity"), item.get("unit")))
            if name in self.unavailable:
                options.append(GroceryOption(
                    ingredient_id=item.get("ingredient_id"), ingredient_name=name,
                    required_quantity=item.get("quantity"),
                    required_unit=item.get("unit"), match_status="no_match"))
                continue
            quantity, unit, price = CATALOG.get(name) or _default_package(item.get("unit"))
            options.append(GroceryOption(
                ingredient_id=item.get("ingredient_id"), ingredient_name=name,
                required_quantity=item.get("quantity"), required_unit=item.get("unit"),
                product_name=f"Catalog {name}", package_quantity=float(quantity),
                package_unit=unit, packages_needed=1, price_per_package=price,
                total_cost=price, currency="SGD", store="Catalog",
                match_status="matched", match_quality="exact"))
        return options


class FixedRecipeAgent:
    """Offers a fixed list of real KB recipe IDs per meal type."""

    def __init__(self, candidates):
        self.candidates = candidates

    def run(self, user_state, meal_slot, selected_recipe_ids=None,
            recent_cuisines=None, max_candidates=None):
        excluded = set(selected_recipe_ids or [])
        ids = [r for r in self.candidates[meal_slot["meal_type"]] if r not in excluded]
        return {"agent": "recipe", "status": "success",
                "data": {"candidate_recipe_ids": ids[:max_candidates]},
                "warnings": [], "errors": []}


@lru_cache(maxsize=1)
def repository():
    return RecipeRepository.from_csv()


def build_planner(candidates, unavailable=(), max_candidates=8):
    service = CatalogGroceryService(unavailable=unavailable)
    manager = ManagerAgent(
        recipe_agent=FixedRecipeAgent(candidates),
        ingredient_agent=IngredientAgent(),
        grocery_agent=GroceryAgent(grocery_service=service),
        recipe_lookup=repository().get_recipe,
        allow_provisional_budget=True,
    )
    return MultiMealPlanner(manager=manager, max_candidates_per_slot=max_candidates), service


def user_state(pantry, budget=100.0, **extra):
    state = {
        "user_id": "INTEGRATION_USER",
        "budget": budget,
        "remaining_budget": budget,
        "dietary_restrictions": ["vegetarian"],
        "allergies": ["peanut"],
        "preferred_cuisines": ["asian", "mediterranean"],
        "preferred_meal_types": ["lunch", "dinner"],
        "disliked_ingredients": [],
        "cook_time_preference_hrs": 0.5,
        "pantry": pantry,
        "nutrition_targets": {"calories": 1800, "protein_g": 70},
    }
    state.update(extra)
    return state


def selected_ids(plan):
    return [(m["slot"]["slot_id"], m["recipe_id"]) for m in plan["selected_meals"]]


def reconciliation_event(plan):
    events = [e for e in plan["execution_trace"]
              if str(e.get("event", "")).startswith("inventory_reconcil")]
    return events[-1] if events else None
