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
| dijon mustard | ING1203 | 1.0 | pinch | needs_purchase |
| garlic salt | ING1469 | 1.0 | pinch | needs_purchase |
| cilantro | ING0870 | 1.0 | sprig | needs_purchase |
| sour cream | ING3248 | 1.5 | tablespoon | needs_purchase |
| cheddar cheese | ING0658 | 1.5 | tablespoon | needs_purchase |
| cauliflower | ING0614 | 0.5 | head | needs_purchase |
| mayonnaise | ING2147 | 1.5 | tablespoon | needs_purchase |

## 4. Live FairPrice Grocery Results

| Ingredient | Product | Price / Package | Package | Packs | Purchase Cost | Match Status | Match Quality |
|---|---|---:|---|---:|---:|---|---|
| dijon mustard | Maille Dijon Mustard | $5.60 | 215.0 g | NA | NA | matched_no_quantity | exact |
| garlic salt | FairPrice Premium Quality Fine Salt | $0.45 | 500.0 g | NA | NA | matched_no_quantity | approximate |
| cilantro | China Coriander (Cilantro) | $1.80 | 50.0 g | NA | NA | matched_no_quantity | exact |
| sour cream | Emborg Sour Cream | $12.95 | 1.0 kg | NA | NA | matched_no_quantity | exact |
| cheddar cheese | Mainland Natural Cheddar Cheese Slice | $8.52 | 210.0 g | NA | NA | matched_no_quantity | exact |
| cauliflower | China Cauliflower | $1.86 | 620.0 g | NA | NA | matched_no_quantity | exact |
| mayonnaise | Ayam Brand Tuna Mayonnaise | $3.28 | 160.0 g | NA | NA | matched_no_quantity | exact |

### FairPrice Sources

- **dijon mustard:** [Maille Dijon Mustard](https://www.fairprice.com.sg/product/la-maison-maille-dijon-mustard-original-215ml-13034962)
- **garlic salt:** [FairPrice Premium Quality Fine Salt](https://www.fairprice.com.sg/product/fairprice-premium-fine-salt-500g-432823)
- **cilantro:** [China Coriander (Cilantro)](https://www.fairprice.com.sg/product/china-coriander-cilantro-50g-12393737)
- **sour cream:** [Emborg Sour Cream](https://www.fairprice.com.sg/product/emborg-sour-cream-1-kg-90179874)
- **cheddar cheese:** [Mainland Natural Cheddar Cheese Slice](https://www.fairprice.com.sg/product/mainland-natural-cheddar-cheese-slice-extra-tasty-210g-13207895)
- **cauliflower:** [China Cauliflower](https://www.fairprice.com.sg/product/12120704)
- **mayonnaise:** [Ayam Brand Tuna Mayonnaise](https://www.fairprice.com.sg/product/ayam-brand-deli-tuna-mayonnaise-160g-13057934)

## 5. Basket Summary

- Grocery items requiring purchase: **7**
- Items with known final cost: **0**
- Known subtotal: **$0.00**
- Complete purchase cost known: **No**
- Unknown-cost items: **dijon mustard, garlic salt, cilantro, sour cream, cheddar cheese, cauliflower, mayonnaise**

## 6. Budget Constraint

| Remaining Budget | Known Grocery Cost | Complete Cost Known? | Decision | Budget After Purchase |
|---:|---:|---|---|---:|
| $100.00 | $0.00 | No | **UNCERTAIN** | NA |
| $50.00 | $0.00 | No | **UNCERTAIN** | NA |
| $20.00 | $0.00 | No | **UNCERTAIN** | NA |
| $10.00 | $0.00 | No | **UNCERTAIN** | NA |
| $1.00 | $0.00 | No | **UNCERTAIN** | NA |

## 7. Decision Reasoning

### Budget $100.00

- Decision: **UNCERTAIN**
- Known purchase cost: **$0.00**
- Complete cost known: **No**
- Budget after purchase: **NA**
- Reason: One or more required grocery costs are unknown.

### Budget $50.00

- Decision: **UNCERTAIN**
- Known purchase cost: **$0.00**
- Complete cost known: **No**
- Budget after purchase: **NA**
- Reason: One or more required grocery costs are unknown.

### Budget $20.00

- Decision: **UNCERTAIN**
- Known purchase cost: **$0.00**
- Complete cost known: **No**
- Budget after purchase: **NA**
- Reason: One or more required grocery costs are unknown.

### Budget $10.00

- Decision: **UNCERTAIN**
- Known purchase cost: **$0.00**
- Complete cost known: **No**
- Budget after purchase: **NA**
- Reason: One or more required grocery costs are unknown.

### Budget $1.00

- Decision: **UNCERTAIN**
- Known purchase cost: **$0.00**
- Complete cost known: **No**
- Budget after purchase: **NA**
- Reason: One or more required grocery costs are unknown.

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
