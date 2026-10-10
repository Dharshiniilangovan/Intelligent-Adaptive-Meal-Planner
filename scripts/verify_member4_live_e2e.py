"""Live Member 4 integration: Tavily -> Ollama -> basket -> incremental -> budget.
Run from repository root: python -m scripts.verify_member4_live_e2e
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from unittest.mock import patch

from src.agents.grocery_agent import build_plan_grocery_basket, calculate_incremental_basket_cost
from src.grocery.grocery_service import GroceryOption, GroceryService
from src.grocery.ollama_fallback_service import OllamaFallbackGroceryService
from src.reasoning.budget_service import check_provisional_grocery_budget

BUDGET = float(os.getenv('MEMBER4_TEST_BUDGET', '50'))
REQUIREMENTS = [
    ('cucumber', 660, 'g'),
    ('tofu', 56.5, 'g'),
    ('olive oil', 30, 'ml'),
    ('butter lettuce', 0.5, 'head'),
    ('hoisin sauce', 1, 'tablespoon'),
]


def recipe(recipe_id, rows):
    return {'recipe_id': recipe_id, 'ingredients': [
        {'ingredient_name': name, 'quantity': qty, 'unit': unit}
        for name, qty, unit in rows
    ]}


def classify(option):
    if option.total_cost is not None:
        return 'RETAIL_KNOWN'
    if option.estimated_total_cost is not None:
        return 'ESTIMATED'
    return 'UNKNOWN'


def catalog_entry(option):
    return {
        'ingredient_name': option.ingredient_name,
        'package_quantity': option.package_quantity,
        'package_unit': option.package_unit,
        'price': option.price_per_package,
        'total_cost': option.total_cost,
        'estimated_total_cost': option.estimated_total_cost,
        'purchase_basis': option.purchase_basis,
        'match_status': option.match_status,
        'quantity_estimated': option.quantity_estimated,
        'source_url': option.source_url,
        'store': option.store,
    }


def close(a, b):
    return math.isclose(float(a), float(b), abs_tol=0.01, rel_tol=0)


def main():
    if os.getenv('ENABLE_OLLAMA_GROCERY_FALLBACK', '1') != '1':
        raise SystemExit('FAIL: enable ENABLE_OLLAMA_GROCERY_FALLBACK=1')
    service = OllamaFallbackGroceryService()
    options = []
    print('LIVE MEMBER 4 GROCERY / BUDGET E2E')
    for name, qty, unit in REQUIREMENTS:
        if name == 'hoisin sauce':
            # Force only the Tavily layer to miss. Real local Ollama still runs.
            blank = GroceryOption(ingredient_id=None, ingredient_name=name,
                                  required_quantity=qty, required_unit=unit,
                                  match_status='no_match')
            with patch.object(GroceryService, 'get_grocery_option', return_value=blank):
                option = service.get_grocery_option(name, qty, unit)
        else:
            option = service.get_grocery_option(name, qty, unit)
        options.append(option)
        print(f'{name}: {classify(option)} | {option.product_name} | '
              f'{option.package_quantity} {option.package_unit} | '
              f'package SGD {option.price_per_package} | '
              f'cost SGD {option.total_cost if option.total_cost is not None else option.estimated_total_cost}')

    counts = {key: sum(classify(o) == key for o in options)
              for key in ('RETAIL_KNOWN', 'ESTIMATED', 'UNKNOWN')}
    if counts['RETAIL_KNOWN'] == 0:
        raise AssertionError('No usable Tavily retail prices; cannot validate live retail path')
    hoisin = next(o for o in options if o.ingredient_name == 'hoisin sauce')
    if hoisin.purchase_basis != 'llm_estimated_package' or hoisin.estimated_total_cost is None:
        raise AssertionError('Forced Tavily miss did not yield usable real Ollama estimate')
    if hoisin.total_cost is not None or hoisin.source_url is not None:
        raise AssertionError('Ollama result was incorrectly promoted to verified retail')

    catalog = [catalog_entry(o) for o in options]
    lunch = recipe('LIVE_LUNCH', [REQUIREMENTS[0], REQUIREMENTS[1], REQUIREMENTS[2]])
    dinner = recipe('LIVE_DINNER', [REQUIREMENTS[2], REQUIREMENTS[3], REQUIREMENTS[4]])
    original_inventory = []
    first = calculate_incremental_basket_cost([], lunch, original_inventory, catalog)
    second = calculate_incremental_basket_cost([lunch], dinner, original_inventory, catalog)
    final = build_plan_grocery_basket([lunch, dinner], original_inventory, catalog)
    print('\nBASKET')
    print('First increment:', first['projected_incremental_cost'])
    print('Second increment:', second['projected_incremental_cost'])
    print('Final known:', final['known_cost'])
    print('Final projected:', final['projected_cost'])
    print('Projection missing:', final['projection_missing'])
    print('Sources:', [(x['name'], x.get('price_source'), x.get('pricing_status'))
                       for x in final['items']])

    complete = bool(final['projected_cost_complete'])
    if complete != bool(first['projected_cost_complete'] and second['projected_cost_complete']):
        raise AssertionError('Inconsistent projection completeness')
    if complete:
        increments = (first['projected_incremental_cost'] +
                      second['projected_incremental_cost'])
        if not close(increments, final['projected_cost']):
            raise AssertionError(f'RECONCILIATION FAILURE: increments={increments} final={final["projected_cost"]}')
        print('PASS: cumulative incremental projected cost reconciles')
    else:
        print('INCOMPLETE: projected basket cannot be reconciled; unknown items are not zero-cost')

    olive = next(x for x in second['additional_items'] if x['name'] == 'olive oil')
    if olive['additional_packages'] != 0:
        raise AssertionError('Shared olive oil charged an extra package')
    print('PASS: shared olive oil is not purchased twice')

    for item in final['items']:
        source = next(o for o in options if o.ingredient_name == item['name'])
        if source.total_cost is None and item.get('pricing_status') == 'priced':
            raise AssertionError(f'Estimate incorrectly verified: {item["name"]}')
    print('PASS: estimated source prices are not promoted to verified cost')

    budget_result = check_provisional_grocery_budget(
        projected_cost=final['projected_cost'],
        projected_cost_complete=complete,
        remaining_budget=BUDGET,
        safety_margin=0.20,
    )
    print('Budget decision:', budget_result['budget_status'])
    if not complete and budget_result['budget_status'] == 'pass':
        raise AssertionError('Incomplete basket was incorrectly accepted')
    report = {'counts': counts, 'budget': budget_result, 'basket': final,
              'first_increment': first['projected_incremental_cost'],
              'second_increment': second['projected_incremental_cost']}
    out = Path('reports/member4_live_e2e.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
    print('Report:', out)
    if not complete:
        raise AssertionError('LIVE E2E INCOMPLETE: some grocery costs could not be projected')
    print('PASS: LIVE MEMBER 4 GROCERY / BUDGET E2E')


if __name__ == '__main__':
    main()
