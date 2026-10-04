# End-to-End Grocery + Budget Verification

This report verifies the complete flow from recipe ingredients and pantry contents through live FairPrice pricing and the budget constraint.

**Recipe ID:** `R03943`

## 1. Recipe Requirements

| Ingredient | Ingredient ID | Alias | Required Quantity | Unit |
|---|---|---|---:|---|
| cauliflower | ING0614 | ['cauliflower', 'cauliflower, raw', 'cauliflowers', 'frozen cauliflower'] | 0.5 | head |
| mayonnaise | ING2147 | ['mayonnaise', 'low fat mayonnaise', 'low-fat mayonnaise', 'reduced fat mayonnaise', 'reduced-fat mayonnaise'] | 1.5 | tablespoon |
| sour cream | ING3248 | ['sour cream', 'fat free sour cream', 'fat-free sour cream', 'low fat sour cream', 'low-fat sour cream', 'reduced fat sour cream', 'reduced-fat sour cream', 'sour cream, fat free', 'sour cream, reduced fat'] | 1.5 | tablespoon |
| dijon mustard | ING1203 | ['dijon mustard', 'dijon) mustard'] | 1.0 | pinch |
| cheddar cheese | ING0658 | ['cheddar cheese', 'cheddar  cheese', 'cheddar® cheese'] | 1.5 | tablespoon |
| garlic salt | ING1469 | ['garlic salt'] | 1.0 | pinch |
| cilantro | ING0870 | ['cilantro'] | 1.0 | sprig |

## 2. Pantry Contents

| Ingredient | Available Quantity | Unit |
|---|---:|---|
| milk | 1 | liter |
| eggs | 12 | pieces |
| flour | 2 | kilograms |
| sugar | 1 | kilogram |
| butter | 0.5 | kilogram |
| bell pepper | 1 | count |

## 3. Grocery List After Pantry Comparison

| Ingredient | Ingredient ID | Quantity to Buy | Unit | Pantry Status |
|---|---|---:|---|---|
| cauliflower | ING0614 | 0.5 | head | needs_purchase |
| dijon mustard | ING1203 | 1.0 | pinch | needs_purchase |
| sour cream | ING3248 | 1.5 | tablespoon | needs_purchase |
| garlic salt | ING1469 | 1.0 | pinch | needs_purchase |
| cheddar cheese | ING0658 | 1.5 | tablespoon | needs_purchase |
| mayonnaise | ING2147 | 1.5 | tablespoon | needs_purchase |
| cilantro | ING0870 | 1.0 | sprig | needs_purchase |

## 4. Live FairPrice Grocery Results

| Ingredient | Product | Price / Package | Package | Packs | Purchase Cost | Match Status | Match Quality |
|---|---|---:|---|---:|---:|---|---|
| cauliflower | China Green Cauliflower | $1.62 | 280.0 g | 1 | $1.62 | matched_minimum_package | exact |
| dijon mustard | NA | NA | NA | NA | NA | no_match | NA |
| sour cream | Bulla Sour Cream | $4.59 | 200.0 ml | 1 | $4.59 | matched | exact |
| garlic salt | FairPrice Premium Quality Fine Salt | $0.45 | 500.0 g | 1 | $0.45 | matched_minimum_package | approximate |
| cheddar cheese | Chesdale Cheddar Cheese Slices | $10.04 | 500.0 g | 1 | $10.04 | matched_minimum_package | exact |
| mayonnaise | NA | NA | NA | NA | NA | no_match | NA |
| cilantro | China Coriander (Cilantro) | $1.80 | 50.0 g | 1 | $1.80 | matched_minimum_package | exact |

### FairPrice Sources

- **cauliflower:** [China Green Cauliflower](https://www.fairprice.com.sg/product/china-green-cauliflower-530g-11131460)
- **dijon mustard:** No reliable FairPrice product page found.
- **sour cream:** [Bulla Sour Cream](https://www.fairprice.com.sg/product/182668)
- **garlic salt:** [FairPrice Premium Quality Fine Salt](https://www.fairprice.com.sg/product/fairprice-premium-fine-salt-500g-432823)
- **cheddar cheese:** [Chesdale Cheddar Cheese Slices](https://www.fairprice.com.sg/product/chesdale-cheddar-cheese-slices-original-500g-24-per-pack-12369809)
- **mayonnaise:** No reliable FairPrice product page found.
- **cilantro:** [China Coriander (Cilantro)](https://www.fairprice.com.sg/product/china-coriander-cilantro-50g-12393737)

## 5. Basket Summary

- Grocery items requiring purchase: **7**
- Items with known final cost: **5**
- Known subtotal: **$18.50**
- Complete purchase cost known: **No**
- Unknown-cost items: **dijon mustard, mayonnaise**

## 6. Budget Constraint

| Remaining Budget | Known Grocery Cost | Complete Cost Known? | Decision | Budget After Purchase |
|---:|---:|---|---|---:|
| $100.00 | $18.50 | No | **UNCERTAIN** | NA |
| $50.00 | $18.50 | No | **UNCERTAIN** | NA |
| $20.00 | $18.50 | No | **UNCERTAIN** | NA |
| $10.00 | $18.50 | No | **HARD FAIL** | NA |
| $1.00 | $18.50 | No | **HARD FAIL** | NA |

## 7. Decision Reasoning

### Budget $100.00

- Decision: **UNCERTAIN**
- Known purchase cost: **$18.50**
- Complete cost known: **No**
- Budget after purchase: **NA**
- Reason: One or more required grocery costs are unknown.

### Budget $50.00

- Decision: **UNCERTAIN**
- Known purchase cost: **$18.50**
- Complete cost known: **No**
- Budget after purchase: **NA**
- Reason: One or more required grocery costs are unknown.

### Budget $20.00

- Decision: **UNCERTAIN**
- Known purchase cost: **$18.50**
- Complete cost known: **No**
- Budget after purchase: **NA**
- Reason: One or more required grocery costs are unknown.

### Budget $10.00

- Decision: **HARD FAIL**
- Known purchase cost: **$18.50**
- Complete cost known: **No**
- Budget after purchase: **NA**
- Reason: Known purchase cost exceeds remaining budget.

### Budget $1.00

- Decision: **HARD FAIL**
- Known purchase cost: **$18.50**
- Complete cost known: **No**
- Budget after purchase: **NA**
- Reason: Known purchase cost exceeds remaining budget.

## 8. Verified Pipeline

```text
Recipe R03943
        |
        v
Recipe ingredient retrieval
        |
        v
Pantry comparison
        |
        v
Ingredients still requiring purchase
        |
        v
Tavily -> FairPrice
        |
        v
Grocery product + package price
        |
        v
Basket summary
        |
        v
Budget constraint
        |
        v
PASS / HARD FAIL / UNCERTAIN
```
