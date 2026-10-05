import os
from src.models import user
import uuid
import json

PANTRY_PATH = os.getenv("USER_PANTRY", "../../data/sample/pantry_{user_id}.json")

#build user state
def build_user_state(budget: float, cook_frequency: int,cook_time_preference_hrs: float,preferred_cuisines: list[str], dietary_restrictions: list[str], allergies: list[str], preferred_meal_types: list[str], preferred_ingredients: list[str], disliked_ingredients: list[str], budget_flexible: bool, ingredient_availability: dict) -> user.user:
    user_id = str(uuid.uuid4())
    user_state = user.user(user_id)
    user_state.setVals(
        budget=budget,
        cook_frequency=cook_frequency,
        cook_time_preference_hrs=cook_time_preference_hrs,
        preferred_cuisines=preferred_cuisines,
        dietary_restrictions=dietary_restrictions,
        allergies=allergies,
        preferred_meal_types=preferred_meal_types,
        preferred_ingredients=preferred_ingredients,
        disliked_ingredients=disliked_ingredients,
        budget_flexible=budget_flexible,
        ingredient_availability=ingredient_availability
    )
    save_pantry(user_state.ingredient_availability, user_state.user_id)
    save_user_state(user_state)
    return user_state

def save_pantry(ingredient_availability: dict, user_id: str) -> None:

    pantry_file_path = os.path.join(os.path.dirname(__file__), PANTRY_PATH.format(user_id=user_id))
    os.makedirs(
        os.path.dirname(pantry_file_path),
        exist_ok=True
    )
    with open(pantry_file_path, "w") as f:
        json.dump({"user_id": user_id}, f, indent=4)
    add_items(ingredient_availability, pantry_file_path)

def add_items(ingredient_availability: dict, pantry_file_path: str) -> None:
    with open(pantry_file_path, "r+") as f:
        pantry_data = json.load(f)
        pantry_data["items"] = []
        for ingredient, quantity in ingredient_availability.items():
            quantity , unit = quantity.split(" ", 1)
            pantry_data["items"].append({"name": ingredient, "quantity": float(quantity), "unit": unit})
        f.seek(0)
        json.dump(pantry_data, f, indent=4)
        f.truncate()

def save_user_state(user_state: user.user) -> None:
    os.makedirs(os.path.join(os.path.dirname(__file__), "../../data/users"), exist_ok=True)
    user_state_file_path = os.path.join(os.path.dirname(__file__), f"../../data/users/user_state_{user_state.user_id}.json")
    
    with open(user_state_file_path, "w") as f:
        json.dump({
            "user_id": user_state.user_id,
            "budget": user_state.budget,
            "cook_frequency": user_state.cook_frequency,
            "cook_time_preference_hrs": user_state.cook_time_preference_hrs,
            "preferred_cuisines": user_state.preferred_cuisines,
            "dietary_restrictions": user_state.dietary_restrictions,
            "allergies": user_state.allergies,
            "preferred_meal_types": user_state.preferred_meal_types,
            "preferred_ingredients": user_state.preferred_ingredients,
            "disliked_ingredients": user_state.disliked_ingredients,
            "budget_flexible": user_state.budget_flexible,
            "budget_cap": user_state.budget_cap,
            "ingredient_availability": user_state.ingredient_availability
        }, f, indent=4)

if __name__=="__main__":
    user_state = build_user_state(
    budget=120.0,
    cook_frequency=3,
    cook_time_preference_hrs = 2,
    preferred_cuisines=["Italian", "Asian"],
    dietary_restrictions=["Vegetarian"],
    allergies=["Peanuts"],
    preferred_meal_types=["Dinner"],
    preferred_ingredients=["Tomatoes", "Cheese"],
    disliked_ingredients=["Onions"],
    budget_flexible=True,
    ingredient_availability={
        "Tomatoes": "5 counts",
        "Cheese": "200 grams"
    }
    )

    print(user_state.user_id)
    print(user_state.budget)
    print(user_state.dietary_restrictions)