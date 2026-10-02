# building a knowledge base from data/raw/recipes_diverse_subset.csv

import pandas as pd
import os
import ast

raw_recipes_path = os.path.join(os.path.dirname(__file__), '../data/raw/recipes.csv')
list_of_cols_removed = ['source','image_url','ingredient_lines','ingredients','daily_values','digest']
final_kb_path = os.path.join(os.path.dirname(__file__), '../data/processed/recipes_kb.csv')
validation_report_path = os.path.join(os.path.dirname(__file__),"../reports/recipe_kb_validation.txt")

def load_recipes(filename):
    """
    Load recipes from a CSV file and return a DataFrame.
    """
    recipes_df = pd.read_csv(filename)
    
    return recipes_df

def view_recipes(recipes_df):
    """
    Display the first few rows of the recipes DataFrame.
    """
    print(recipes_df.head())
    print(f"Total recipes loaded: {len(recipes_df)}")
    print(f"Columns in the DataFrame: {recipes_df.columns.tolist()}")

    return recipes_df.columns.tolist()

def remove_cols(recipes_df):
    """
    Remove specified columns from the recipes DataFrame.
    """
    recipes_df = recipes_df.drop(columns=list_of_cols_removed)
    return recipes_df

def get_nutrient(nutrients, key):
    if not isinstance(nutrients, dict):
        return None

    nutrient = nutrients.get(key)

    if not isinstance(nutrient, dict):
        return None

    return nutrient.get("quantity")

def parse_nutrients(value):
    """
    Convert total_nutrients from CSV string to Python dictionary.
    """
    if isinstance(value, dict):
        return value

    if pd.isna(value):
        return {}

    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return {}

def building_kb():
     # 1. Load raw data
    df = load_recipes(raw_recipes_path)
    df = df.rename(columns={"recipie_id": "recipe_id"})
    view_recipes(df)

    # 2. Remove unnecessary columns
    cleaned_df = remove_cols(df).copy()

    print(
        f"\nNumber of columns = {len(cleaned_df.columns)}"
        f"\nColumns after removal: {cleaned_df.columns.tolist()}"
    )

    # 3. Convert total_nutrients string -> dictionary
    cleaned_df["total_nutrients"] = (
        cleaned_df["total_nutrients"].apply(parse_nutrients)
    )

    # Quick confirmation
    print(
        "\ntotal_nutrients type:",
        type(cleaned_df["total_nutrients"].iloc[0])
    )

    # 4. Build per-serving nutrition

    cleaned_df["calories_per_serving"] = (
        cleaned_df["calories"]
        / cleaned_df["servings"]
    )

    cleaned_df["weight_g_per_serving"] = (
        cleaned_df["total_weight_g"]
        / cleaned_df["servings"]
    )

    nutrient_mapping = {
        "protein_g_per_serving": "PROCNT",
        "carbs_g_per_serving": "CHOCDF",
        "fat_g_per_serving": "FAT",
        "fiber_g_per_serving": "FIBTG",
        "sugar_g_per_serving": "SUGAR",
        "sodium_mg_per_serving": "NA",
        "calcium_mg_per_serving": "CA",
        "iron_mg_per_serving": "FE"
    }

    for column_name, nutrient_key in nutrient_mapping.items():

        cleaned_df[column_name] = (
            cleaned_df["total_nutrients"]
            .apply(lambda x: get_nutrient(x, nutrient_key))
            / cleaned_df["servings"]
        )

    # 5. Remove raw batch-level fields
    cleaned_df.drop(
        columns=[
            "total_nutrients",
            "calories",
            "total_weight_g"
        ],
        inplace=True
    )

    return cleaned_df

def save_as_csv(df, filename=final_kb_path):
    """
    Save the DataFrame as a CSV file.
    """
    df.to_csv(filename, index=False)
    print(f"DataFrame saved as {filename}")




def validate_kb(df, output_file=validation_report_path):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    nutrient_cols = [
        "calories_per_serving",
        "weight_g_per_serving",
        "protein_g_per_serving",
        "carbs_g_per_serving",
        "fat_g_per_serving",
        "fiber_g_per_serving",
        "sugar_g_per_serving",
        "sodium_mg_per_serving",
        "calcium_mg_per_serving",
        "iron_mg_per_serving"
    ]

    with open(output_file, "w") as f:

        f.write("=== RECIPE KB VALIDATION REPORT ===\n\n")

        f.write(f"Shape: {df.shape}\n")
        f.write(f"Total recipes: {len(df)}\n")
        f.write(f"Duplicate recipe IDs: {df['recipe_id'].duplicated().sum()}\n")
        f.write(f"Missing recipe IDs: {df['recipe_id'].isna().sum()}\n")
        f.write(f"Missing recipe names: {df['recipe_name'].isna().sum()}\n")

        f.write("\n=== MISSING VALUES ===\n")
        f.write(df.isna().sum().to_string())

        f.write("\n\n=== NUTRITION STATISTICS ===\n")
        f.write(df[nutrient_cols].describe().to_string())

        f.write("\n\n=== NEGATIVE VALUES ===\n")

        for col in nutrient_cols:
            negative_count = (df[col] < 0).sum()
            f.write(f"{col}: {negative_count}\n")

        f.write("\n=== TOP 10 CALORIES PER SERVING ===\n")
        f.write(
            df.nlargest(10, "calories_per_serving")[
                [
                    "recipe_id",
                    "recipe_name",
                    "servings",
                    "calories_per_serving"
                ]
            ].to_string(index=False)
        )

        f.write("\n\n=== 10 RANDOM RECIPES ===\n")
        f.write(
            df.sample(10, random_state=42).to_string(index=False)
        )

    print(f"Validation report saved to: {output_file}")

    

# #------ function calls--------


final_df = building_kb()
print("\nFinal DataFrame columns:", final_df.columns.tolist())
validate_kb(final_df)
save_as_csv(final_df)