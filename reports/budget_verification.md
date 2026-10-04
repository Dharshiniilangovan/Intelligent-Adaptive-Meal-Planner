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
| cheddar cheese | ING0658 | 1.5 | tablespoon | needs_purchase |
| garlic salt | ING1469 | 1.0 | pinch | needs_purchase |
| dijon mustard | ING1203 | 1.0 | pinch | needs_purchase |
| sour cream | ING3248 | 1.5 | tablespoon | needs_purchase |
| cauliflower | ING0614 | 0.5 | head | needs_purchase |
| mayonnaise | ING2147 | 1.5 | tablespoon | needs_purchase |
| cilantro | ING0870 | 1.0 | sprig | needs_purchase |

## 4. Live FairPrice Grocery Results

| Ingredient | Product | Price / Package | Package | Packs | Purchase Cost | Match Status | Match Quality |
|---|---|---:|---|---:|---:|---|---|
| cheddar cheese | Chesdale Cheddar Cheese Slices | $10.04 | 500.0 g | NA | NA | matched_no_quantity | exact |
| garlic salt | FairPrice Premium Quality Fine Salt | $0.45 | 500.0 g | NA | NA | matched_no_quantity | approximate |
| dijon mustard | Maille Dijon Mustard | $5.60 | 215.0 g | NA | NA | matched_no_quantity | exact |
| sour cream | Bulla Sour Cream | $5.55 | 50.0 ml | 1 | $5.55 | matched | exact |
| cauliflower | China Green Cauliflower | $1.62 | 280.0 g | NA | NA | matched_no_quantity | exact |
| mayonnaise | Best Foods Mayonnaise | $3.16 | 220.0 ml | 1 | $3.16 | matched | exact |
| cilantro | China Coriander (Cilantro) | $1.80 | 50.0 g | NA | NA | matched_no_quantity | exact |

### FairPrice Sources

- **cheddar cheese:** [Chesdale Cheddar Cheese Slices](https://www.fairprice.com.sg/product/chesdale-cheddar-cheese-slices-original-500g-24-per-pack-12369809)
- **garlic salt:** [FairPrice Premium Quality Fine Salt](https://www.fairprice.com.sg/product/fairprice-premium-fine-salt-500g-432823)
- **dijon mustard:** [Maille Dijon Mustard](https://www.fairprice.com.sg/product/la-maison-maille-dijon-mustard-original-215ml-13034962)
- **sour cream:** [Bulla Sour Cream](https://www.fairprice.com.sg/product/bulla-sour-cream-original-200ml-13042062)
- **cauliflower:** [China Green Cauliflower](https://www.fairprice.com.sg/product/china-green-cauliflower-530g-11131460)
- **mayonnaise:** [Best Foods Mayonnaise](https://www.fairprice.com.sg/product/best-foods-real-mayonnaise-220ml-77554)
- **cilantro:** [China Coriander (Cilantro)](https://www.fairprice.com.sg/product/china-coriander-cilantro-50g-12393737)

## 5. Basket Summary

- Grocery items requiring purchase: **7**
- Items with known final cost: **2**
- Known subtotal: **$8.71**
- Complete purchase cost known: **No**
- Unknown-cost items: **cheddar cheese, garlic salt, dijon mustard, cauliflower, cilantro**

## 6. Budget Constraint

| Remaining Budget | Known Grocery Cost | Complete Cost Known? | Decision | Budget After Purchase |
|---:|---:|---|---|---:|
| $100.00 | $8.71 | No | **UNCERTAIN** | NA |
| $50.00 | $8.71 | No | **UNCERTAIN** | NA |
| $20.00 | $8.71 | No | **UNCERTAIN** | NA |
| $10.00 | $8.71 | No | **UNCERTAIN** | NA |
| $1.00 | $8.71 | No | **HARD FAIL** | NA |

## 7. Decision Reasoning

### Budget $100.00

- Decision: **UNCERTAIN**
- Known purchase cost: **$8.71**
- Complete cost known: **No**
- Budget after purchase: **NA**
- Reason: One or more required grocery costs are unknown.

### Budget $50.00

- Decision: **UNCERTAIN**
- Known purchase cost: **$8.71**
- Complete cost known: **No**
- Budget after purchase: **NA**
- Reason: One or more required grocery costs are unknown.

### Budget $20.00

- Decision: **UNCERTAIN**
- Known purchase cost: **$8.71**
- Complete cost known: **No**
- Budget after purchase: **NA**
- Reason: One or more required grocery costs are unknown.

### Budget $10.00

- Decision: **UNCERTAIN**
- Known purchase cost: **$8.71**
- Complete cost known: **No**
- Budget after purchase: **NA**
- Reason: One or more required grocery costs are unknown.

### Budget $1.00

- Decision: **HARD FAIL**
- Known purchase cost: **$8.71**
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
