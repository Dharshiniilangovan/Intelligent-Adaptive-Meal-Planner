from src.agents.grocery_agent import GroceryAgent
from src.grocery.grocery_service import GroceryOption
from src.agents.contracts import (
    normalize_agent_result,
)


class FakeGroceryService:

    def __init__(self, options):
        self.options = options
        self.calls = 0

    def get_grocery_list(
        self,
        items,
    ):
        self.calls += 1
        return self.options


def test_grocery_agent_all_items_priced():

    options = [
        GroceryOption(
            ingredient_id="ING01",
            ingredient_name="rice",
            required_quantity=300,
            required_unit="g",
            product_name="FairPrice Jasmine Rice",
            package_quantity=1,
            package_unit="kg",
            packages_needed=1,
            price_per_package=3.80,
            total_cost=3.80,
            currency="SGD",
            store="FairPrice",
            match_status="matched",
        ),

        GroceryOption(
            ingredient_id="ING02",
            ingredient_name="tofu",
            required_quantity=300,
            required_unit="g",
            product_name="Fortune Tofu",
            package_quantity=300,
            package_unit="g",
            packages_needed=1,
            price_per_package=2.50,
            total_cost=2.50,
            currency="SGD",
            store="FairPrice",
            match_status="matched",
        ),
    ]

    service = FakeGroceryService(
        options
    )

    agent = GroceryAgent(
        grocery_service=service
    )

    result = agent.run(
        recipe_id="R001",
        missing_ingredients=[
            {
                "ingredient_id": "ING01",
                "ingredient_name": "rice",
                "quantity": 300,
                "unit": "g",
            },
            {
                "ingredient_id": "ING02",
                "ingredient_name": "tofu",
                "quantity": 300,
                "unit": "g",
            },
        ],
    )

    assert result["agent"] == "grocery"

    assert (
        result["status"]
        == "success"
    )

    assert (
        result["data"][
            "known_cost"
        ]
        == 6.30
    )

    assert (
        result["data"][
            "all_items_priced"
        ]
        is True
    )

    assert (
        result["data"][
            "unpriced_items"
        ]
        == []
    )


def test_grocery_agent_missing_price():

    options = [
        GroceryOption(
            ingredient_id="ING01",
            ingredient_name="rice",
            product_name="FairPrice Jasmine Rice",
            price_per_package=3.80,
            total_cost=3.80,
            currency="SGD",
            store="FairPrice",
            match_status="matched",
        ),

        GroceryOption(
            ingredient_id="ING02",
            ingredient_name="tofu",
            product_name=None,
            price_per_package=None,
            total_cost=None,
            match_status="no_match",
        ),
    ]

    agent = GroceryAgent(
        grocery_service=(
            FakeGroceryService(
                options
            )
        )
    )

    result = agent.run(
        recipe_id="R001",
        missing_ingredients=[
            {
                "ingredient_id": "ING01",
                "ingredient_name": "rice",
                "quantity": 300,
                "unit": "g",
            },
            {
                "ingredient_id": "ING02",
                "ingredient_name": "tofu",
                "quantity": 300,
                "unit": "g",
            },
        ],
    )

    assert (
        result["status"]
        == "partial"
    )

    assert (
        result["data"][
            "known_cost"
        ]
        == 3.80
    )

    assert (
        result["data"][
            "all_items_priced"
        ]
        is False
    )

    assert (
        "tofu"
        in result["data"][
            "unpriced_items"
        ]
    )


def test_grocery_agent_no_missing_ingredients():

    agent = GroceryAgent(
        grocery_service=(
            FakeGroceryService([])
        )
    )

    result = agent.run(
        recipe_id="R001",
        missing_ingredients=[],
    )

    assert (
        result["status"]
        == "success"
    )

    assert (
        result["data"][
            "known_cost"
        ]
        == 0.0
    )

    assert (
        result["data"][
            "all_items_priced"
        ]
        is True
    )


def test_grocery_agent_requires_recipe_id():

    agent = GroceryAgent(
        grocery_service=(
            FakeGroceryService([])
        )
    )

    result = agent.run(
        recipe_id="",
        missing_ingredients=[],
    )

    assert (
        result["status"]
        == "failed"
    )

    assert result["errors"]

def test_grocery_agent_preserves_multiple_package_calculation():

    options = [
        GroceryOption(
            ingredient_id="ING01",
            ingredient_name="rice",

            required_quantity=1300,
            required_unit="g",

            product_name="FairPrice Jasmine Rice",

            package_quantity=1,
            package_unit="kg",

            packages_needed=2,

            price_per_package=3.80,
            total_cost=7.60,

            currency="SGD",
            store="FairPrice",

            match_status="matched",
        )
    ]

    service = FakeGroceryService(
        options
    )

    agent = GroceryAgent(
        grocery_service=service
    )

    result = agent.run(
        recipe_id="R001",

        missing_ingredients=[
            {
                "ingredient_id": "ING01",
                "ingredient_name": "rice",
                "quantity": 1300,
                "unit": "g",
            }
        ],
    )

    assert result["status"] == "success"

    assert (
        result["data"]["known_cost"]
        == 7.60
    )

    item = result["data"]["items"][0]

    assert item["packages_needed"] == 2

    assert item["total_cost"] == 7.60

    assert item["match_status"] == "matched"

def test_grocery_agent_preserves_minimum_package_result():

    options = [
        GroceryOption(
            ingredient_id="ING02",
            ingredient_name="cheddar cheese",

            required_quantity=1.5,
            required_unit="tablespoon",

            product_name="Cheddar Cheese",

            package_quantity=500,
            package_unit="g",

            packages_needed=1,

            price_per_package=10.04,
            total_cost=10.04,

            currency="SGD",
            store="FairPrice",

            match_status="matched_minimum_package",

            note=(
                "unit mismatch; using one retail "
                "package as the minimum purchase."
            ),
        )
    ]

    agent = GroceryAgent(
        grocery_service=(
            FakeGroceryService(options)
        )
    )

    result = agent.run(
        recipe_id="R001",

        missing_ingredients=[
            {
                "ingredient_id": "ING02",
                "ingredient_name": "cheddar cheese",
                "quantity": 1.5,
                "unit": "tablespoon",
            }
        ],
    )

    assert result["status"] == "success"

    item = result["data"]["items"][0]

    assert item["packages_needed"] == 1

    assert item["total_cost"] == 10.04

    assert (
        item["match_status"]
        == "matched_minimum_package"
    )

def test_grocery_agent_partial_when_product_missing():

    options = [
        GroceryOption(
            ingredient_id="ING01",
            ingredient_name="rice",
            required_quantity=300,
            required_unit="g",
            product_name="FairPrice Jasmine Rice",
            package_quantity=1,
            package_unit="kg",
            packages_needed=1,
            price_per_package=3.80,
            total_cost=3.80,
            currency="SGD",
            store="FairPrice",
            match_status="matched",
        ),

        GroceryOption(
            ingredient_id="ING02",
            ingredient_name="tofu",
            required_quantity=300,
            required_unit="g",
            product_name=None,
            price_per_package=None,
            total_cost=None,
            match_status="no_match",
        ),
    ]

    agent = GroceryAgent(
        grocery_service=FakeGroceryService(
            options
        )
    )

    result = agent.run(
        recipe_id="R001",
        missing_ingredients=[
            {
                "ingredient_id": "ING01",
                "ingredient_name": "rice",
                "quantity": 300,
                "unit": "g",
            },
            {
                "ingredient_id": "ING02",
                "ingredient_name": "tofu",
                "quantity": 300,
                "unit": "g",
            },
        ],
    )

    assert result["status"] == "partial"

    assert (
        result["data"]["known_cost"]
        == 3.80
    )

    assert (
        result["data"]["all_items_priced"]
        is False
    )

    assert (
        "tofu"
        in result["data"]["unpriced_items"]
    )

    assert result["warnings"]

class FailingGroceryService:

    def get_grocery_list(
        self,
        items,
    ):
        raise RuntimeError(
            "test grocery failure"
        )


def test_grocery_agent_handles_service_failure():

    agent = GroceryAgent(
        grocery_service=FailingGroceryService()
    )

    result = agent.run(
        recipe_id="R001",
        missing_ingredients=[
            {
                "ingredient_id": "ING01",
                "ingredient_name": "rice",
                "quantity": 300,
                "unit": "g",
            }
        ],
    )

    assert result["status"] == "failed"

    assert result["data"]["recipe_id"] == "R001"

    assert result["warnings"] == []

    assert result["errors"]

    assert (
        "Grocery lookup failed"
        in result["errors"][0]
    )

class FailingGroceryService:

    def get_grocery_list(
        self,
        items,
    ):
        raise RuntimeError(
            "test grocery failure"
        )


def test_grocery_agent_handles_service_failure():

    agent = GroceryAgent(
        grocery_service=FailingGroceryService()
    )

    result = agent.run(
        recipe_id="R001",
        missing_ingredients=[
            {
                "ingredient_id": "ING01",
                "ingredient_name": "rice",
                "quantity": 300,
                "unit": "g",
            }
        ],
    )

    assert result["status"] == "failed"
    assert result["data"]["recipe_id"] == "R001"
    assert result["warnings"] == []
    assert result["errors"]

    assert (
        "Grocery lookup failed"
        in result["errors"][0]
    )


def test_grocery_agent_rejects_invalid_missing_ingredients():

    agent = GroceryAgent(
        grocery_service=FakeGroceryService([])
    )

    result = agent.run(
        recipe_id="R001",
        missing_ingredients="rice",
    )

    assert result["status"] == "failed"
    assert result["errors"]

    assert (
        "missing_ingredients"
        in result["errors"][0]
    )

def test_grocery_agent_matches_shared_contract():

    options = [
        GroceryOption(
            ingredient_id="ING01",
            ingredient_name="rice",
            required_quantity=300,
            required_unit="g",
            product_name="FairPrice Jasmine Rice",
            package_quantity=500,
            package_unit="g",
            packages_needed=1,
            price_per_package=2.00,
            total_cost=2.00,
            currency="SGD",
            store="FairPrice",
            match_status="matched",
        )
    ]

    agent = GroceryAgent(
        grocery_service=FakeGroceryService(
            options
        )
    )

    result = agent.run(
        recipe_id="R001",
        missing_ingredients=[
            {
                "ingredient_id": "ING01",
                "ingredient_name": "rice",
                "quantity": 300,
                "unit": "g",
            }
        ],
    )

    # This is exactly what Manager does.
    normalized = normalize_agent_result(
        result,
        "grocery",
    )

    assert normalized["agent"] == "grocery"
    assert normalized["status"] == "success"

    assert isinstance(
        normalized["data"],
        dict,
    )

    assert normalized["data"]["recipe_id"] == "R001"
    assert normalized["data"]["known_cost"] == 2.00

    assert (
        normalized["data"]["all_items_priced"]
        is True
    )

    assert (
        normalized["data"]["unpriced_items"]
        == []
    )

    assert normalized["warnings"] == []
    assert normalized["errors"] == []
