class user:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.budget = 0.0
        self.cook_frequency = 0
        self.preferred_cuisines = []
        self.dietary_restrictions = []
        self.allergies = []
        self.preferred_meal_types = []
        self.preferred_ingredients = []
        self.disliked_ingredients = []
        self.budget_flexible = False
        self.budget_cap = None
        self.ingredient_availability = {}
    def setVals(self, budget: float, cook_frequency: int, preferred_cuisines: list[str], dietary_restrictions: list[str], allergies: list[str], preferred_meal_types: list[str], preferred_ingredients: list[str], disliked_ingredients: list[str], budget_flexible: bool, ingredient_availability: dict) -> None:
        self.budget = budget
        self.cook_frequency = cook_frequency
        self.preferred_cuisines = preferred_cuisines
        self.dietary_restrictions = dietary_restrictions
        self.allergies = allergies
        self.preferred_meal_types = preferred_meal_types
        self.preferred_ingredients = preferred_ingredients
        self.disliked_ingredients = disliked_ingredients
        self.budget_flexible = budget_flexible
        self.budget_cap = budget+5 if budget_flexible else None
        self.ingredient_availability = ingredient_availability
        
    
# {
#     "user_id": "12345",
#     "budget": 100.0,
#     "cook_frquency": 1,
#     "preferred_cuisines": ["Italian", "Mexican"],
#     "dietary_restrictions": ["Vegetarian"],
#     "allergies": ["Peanuts"],
#     "preferred_meal_types": ["Dinner", "Lunch"],
#     "preferred_ingredients": ["Tomatoes", "Cheese"],
#     "disliked_ingredients": ["Onions", "Garlic"],
#     "budget_flexibile": False,
#     "ingredient_availability": {
#         "Tomatoes": "5 counts",
#         "Cheese": "200 grams",
#         "Onions": "2 counts",
#         "Garlic": "3 cloves"
#     }
# }
    

    

