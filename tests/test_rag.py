
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.agents.recipe_agent import (
    RecipeAgent,
    build_semantic_query,
    load_latest_user_state,
)
from src.knowledge.recipe_rag import RecipeRAG

from scripts.candidate_recipe import load_recipe_kb



@pytest.fixture(scope="module")
def user_state():
    state = load_latest_user_state()
    print("\nUSER STATE:")
    print(json.dumps(state, indent=2))
    return state


@pytest.fixture(scope="module")
def rag():
    rag = RecipeRAG()

    index_path = (
        Path(__file__).resolve().parents[1]
        / "data" / "processed" / "recipe_numpy.npz"
    )

    if index_path.exists():
        try:
            rag.load_index(index_path)
            print("\nLoaded real NumPy RAG index")
        except (ValueError, FileNotFoundError):
            rag.build_index()
            rag.save_index(index_path)
            print("\nRebuilt real NumPy RAG index")
    else:
        rag.build_index()
        rag.save_index(index_path)
        print("\nBuilt real NumPy RAG index")

    return rag


@pytest.fixture(scope="module")
def agent(rag):
    return RecipeAgent(rag=rag)


@pytest.fixture(scope="module")
def result(agent, user_state):
    output = agent.run(
        user_state=user_state,
        meal_slot={
            "date": date.today().isoformat(),
            "meal_type": "dinner"
        },
        selected_recipe_ids=[],
        recent_cuisines=[],
        max_candidates=5
    )

    print("\nRECIPE AGENT OUTPUT:")
    print(json.dumps(output, indent=2))

    return output


def test_01_semantic_query(user_state):
    query = build_semantic_query(user_state, "dinner")

    print("\nGenerated query:", query)

    for value in (
        user_state["preferred_cuisines"]
        + user_state["dietary_restrictions"]
        + user_state["preferred_ingredients"]
    ):
        assert value.lower() in query.lower()

    assert "dinner" in query.lower()
    print("PASS: User State converted into RAG query")


def test_02_real_semantic_retrieval(rag, user_state):
    query = build_semantic_query(user_state, "dinner")
    retrieved = rag.retrieve(query, top_k=10)

    print("\nTOP 10 SEMANTIC RESULTS:")
    for recipe_id, score in zip(
        retrieved.candidate_recipe_ids,
        retrieved.scores
    ):
        print(recipe_id, round(score, 4))

    assert retrieved.candidate_recipe_ids
    assert len(retrieved.candidate_recipe_ids) == len(retrieved.scores)
    assert all(
        recipe_id in set(rag.documents["recipe_id"])
        for recipe_id in retrieved.candidate_recipe_ids
    )
    print("PASS: Real semantic retrieval")


def test_03_candidate_limit(result):
    ids = result["candidate_recipe_ids"]

    print("\nReturned candidates:", ids)

    assert len(ids) <= 5
    assert len(ids) > 0
    print("PASS: Candidate limit")


def test_04_no_duplicates(result):
    ids = result["candidate_recipe_ids"]

    assert len(ids) == len(set(ids))
    print("\nPASS: No duplicate recipes")


def test_05_cooking_time(agent, result, user_state):
    kb = agent.repository.to_frame()
    cook_time_hrs = user_state.get("cook_time_preference_hrs")

    if cook_time_hrs is None:
        pytest.skip("No cooking-time preference specified")

    limit = float(cook_time_hrs) * 60
    # limit = float(user_state["cook_time_preference_hrs"]) * 60

    for recipe_id in result["candidate_recipe_ids"]:
        row = kb[kb["recipe_id"] == recipe_id]
        assert not row.empty

        minutes = pd.to_numeric(
            row.iloc[0]["cooking_time_min"],
            errors="coerce"
        )

        print(recipe_id, "Cooking time:", minutes)

        assert pd.notna(minutes)
        assert minutes <= limit

    print("PASS: Cooking-time restriction")


def test_06_no_previously_selected(agent, user_state, result):
    ids = result["candidate_recipe_ids"]

    assert ids, "Need at least one recipe for this test"

    selected = [ids[0]]

    updated = agent.run(
        user_state=user_state,
        meal_slot={
            "date": date.today().isoformat(),
            "meal_type": "dinner"
        },
        selected_recipe_ids=selected,
        recent_cuisines=[],
        max_candidates=5
    )

    print("\nPreviously selected:", selected)
    print("New candidates:", updated["candidate_recipe_ids"])

    assert selected[0] not in updated["candidate_recipe_ids"]
    print("PASS: Previously selected recipe excluded")


def test_07_numpy_index(rag):
    print("\nIndex type:", type(rag.index))
    print("Index shape:", rag.index.shape)

    assert isinstance(rag.index, __import__("numpy").ndarray)
    assert rag.index.shape[0] == len(rag.documents)

    print("PASS: NumPy index verified")


# ============================================================
# MEMBER 2: EDGE CASES FOR ONE MEAL SLOT
# ============================================================

def test_08_unknown_cooking_times_excluded(agent):
    import pandas as pd
    candidates = pd.DataFrame({
        "recipe_id": ["R00001", "R00002"],
        "cooking_time_min": [None, "unknown"],
    })
    filtered, warnings = agent._apply_cooking_time(candidates, 120)
    print("\nUnknown times ->", filtered["recipe_id"].tolist(), warnings)
    assert filtered.empty
    assert warnings


def test_09_missing_cooking_time_column_excluded(agent):
    import pandas as pd
    candidates = pd.DataFrame({"recipe_id": ["R00001"]})
    filtered, warnings = agent._apply_cooking_time(candidates, 120)
    print("\nMissing column ->", filtered["recipe_id"].tolist(), warnings)
    assert filtered.empty
    assert warnings


def test_10_no_time_limit_keeps_unknown_times(agent):
    import pandas as pd
    candidates = pd.DataFrame({"recipe_id": ["R00001"], "cooking_time_min": [None]})
    filtered, warnings = agent._apply_cooking_time(candidates, None)
    print("\nNo time limit ->", filtered["recipe_id"].tolist())
    assert filtered["recipe_id"].tolist() == ["R00001"]


def test_11_mixed_cooking_times_exclude_unknown(agent):
    import pandas as pd
    candidates = pd.DataFrame({"recipe_id": ["R00001", "R00002"], "cooking_time_min": [None, 30]})
    # Test the policy using a temporary minimal repository to avoid coupling
    # these synthetic IDs to the actual recipe knowledge base.
    class TimeRepo:
        def filter_by_max_time(self, minutes, include_unknown=False):
            assert minutes == 120
            assert include_unknown is False
            return self
        def ids(self):
            return ["R00002"]
    original = agent.repository
    try:
        agent.repository = TimeRepo()
        filtered, _ = agent._apply_cooking_time(candidates, 120)
    finally:
        agent.repository = original
    print("\nMixed times ->", filtered["recipe_id"].tolist())
    assert filtered["recipe_id"].tolist() == ["R00002"]


def test_12_empty_candidates_return_empty(agent):
    import pandas as pd
    candidates = pd.DataFrame(columns=["recipe_id", "cooking_time_min"])
    filtered, _ = agent._apply_cooking_time(candidates, 120)
    print("\nEmpty input ->", filtered["recipe_id"].tolist())
    assert filtered.empty



# ============================================================
# FIXTURES — REAL RECIPE KB AND RECIPE AGENT
# ============================================================

@pytest.fixture(scope="module")
def kb():
    df = load_recipe_kb().copy()

    assert "recipe_id" in df.columns
    assert "cooking_time_min" in df.columns

    df["recipe_id"] = (
        df["recipe_id"].astype(str).str.strip().str.upper()
    )

    print("\nTotal KB recipes:", len(df))
    print(
        "Known cooking times:",
        pd.to_numeric(
            df["cooking_time_min"], errors="coerce"
        ).notna().sum()
    )

    return df


@pytest.fixture(scope="module")
def agent():
    # Real repository and real Recipe Agent.
    # RAG is initialized separately for the full integration test.
    return RecipeAgent(max_candidates=5)


@pytest.fixture(scope="module")
def real_agent():
    rag = RecipeRAG()

    # Uses the actual embedding model and NumPy retrieval.
    # No fake embeddings or fake repository.
    rag.build_index()

    return RecipeAgent(max_candidates=5, rag=rag)


@pytest.fixture(scope="module")
def user_state():
    return load_latest_user_state()


# ============================================================
# TEST 1 — COOKING TIME LOOKUP FROM KB
# ============================================================

def test_01_missing_column_uses_real_kb(agent, kb):

    times = pd.to_numeric(
        kb["cooking_time_min"], errors="coerce"
    )

    valid = kb.loc[
        times.notna() & times.ge(0) & times.le(120)
    ]

    assert not valid.empty, "No valid recipe found in KB"

    recipe_id = valid.iloc[0]["recipe_id"]

    # Intentionally omit cooking_time_min
    candidates = pd.DataFrame({
        "recipe_id": [recipe_id]
    })

    filtered, warnings = agent._apply_cooking_time(
        candidates, 120
    )

    print("\nTEST 1: KB COOKING TIME LOOKUP")
    print("Recipe ID:", recipe_id)
    print("Result:", filtered.to_string(index=False))
    print("Warnings:", warnings)

    assert len(filtered) == 1
    assert filtered.iloc[0]["recipe_id"] == recipe_id
    assert float(filtered.iloc[0]["cooking_time_min"]) <= 120


# ============================================================
# TEST 2 — EXCESSIVE COOKING TIMES EXCLUDED
# ============================================================

def test_02_excessive_cooking_times(agent, kb):

    times = pd.to_numeric(
        kb["cooking_time_min"], errors="coerce"
    )

    excessive = kb.loc[times > 120]

    assert not excessive.empty, (
        "No recipe exceeding 120 minutes exists in KB"
    )

    recipe_id = excessive.iloc[0]["recipe_id"]

    candidates = pd.DataFrame({
        "recipe_id": [recipe_id]
    })

    filtered, warnings = agent._apply_cooking_time(
        candidates, 120
    )

    print("\nTEST 2: EXCESSIVE COOKING TIME")
    print("Recipe ID:", recipe_id)
    print("Filtered IDs:", filtered["recipe_id"].tolist())
    print("Warnings:", warnings)

    assert filtered.empty


# ============================================================
# TEST 3 — NO MATCH RETURNS EMPTY LIST
# ============================================================

def test_03_no_matching_recipes(agent, kb):

    times = pd.to_numeric(
        kb["cooking_time_min"], errors="coerce"
    )

    excessive = kb.loc[times > 120]

    assert not excessive.empty

    recipe_ids = excessive["recipe_id"].head(3).tolist()

    candidates = pd.DataFrame({
        "recipe_id": recipe_ids
    })

    filtered, warnings = agent._apply_cooking_time(
        candidates, 120
    )

    candidate_recipe_ids = filtered["recipe_id"].tolist()

    print("\nTEST 3: NO MATCHING RECIPES")
    print("Input IDs:", recipe_ids)
    print("Output IDs:", candidate_recipe_ids)

    assert candidate_recipe_ids == []


# ============================================================
# TEST 4 — REAL RAG + RECIPE AGENT
# ============================================================

def test_04_real_rag_one_meal_slot(real_agent, user_state, kb):

    result = real_agent.run(
        user_state=user_state,
        meal_slot={
            "date": date.today().isoformat(),
            "meal_type": "dinner"
        },
        selected_recipe_ids=[],
        recent_cuisines=[],
        max_candidates=5
    )

    print("\nTEST 4: REAL RAG + RECIPE AGENT")
    print(json.dumps(result, indent=2))

    ids = result["candidate_recipe_ids"]

    assert isinstance(ids, list)
    assert 0 < len(ids) <= 5
    assert len(ids) == len(set(ids))

    kb_ids = set(kb["recipe_id"])
    assert all(recipe_id in kb_ids for recipe_id in ids)

    # limit = float(
    #     user_state["cook_time_preference_hrs"]
    # ) * 60
    cook_time_hrs = user_state.get("cook_time_preference_hrs")

    if cook_time_hrs is None:
         pytest.skip("No cooking-time preference specified")

    limit = float(cook_time_hrs) * 60
    selected = kb[kb["recipe_id"].isin(ids)].copy()

    selected_times = pd.to_numeric(
        selected["cooking_time_min"],
        errors="coerce"
    )

    assert selected_times.notna().all()
    assert selected_times.between(0, limit).all()

    print("PASS: Real RAG and cooking-time integration")


# ============================================================
# TEST 5 — PREVIOUSLY SELECTED RECIPES
# ============================================================

def test_05_alternative_candidates(real_agent, user_state):

    meal_slot = {
        "date": date.today().isoformat(),
        "meal_type": "dinner"
    }

    first = real_agent.run(
        user_state=user_state,
        meal_slot=meal_slot,
        selected_recipe_ids=[],
        recent_cuisines=[],
        max_candidates=5
    )

    first_ids = first["candidate_recipe_ids"]

    assert first_ids, "No initial recipes available"

    second = real_agent.run(
        user_state=user_state,
        meal_slot=meal_slot,
        selected_recipe_ids=first_ids,
        recent_cuisines=[],
        max_candidates=5
    )

    second_ids = second["candidate_recipe_ids"]

    print("\nTEST 5: ALTERNATIVE CANDIDATES")
    print("Previously selected:", first_ids)
    print("Alternatives:", second_ids)

    assert second_ids
    assert set(first_ids).isdisjoint(second_ids)

    print("PASS: Alternative candidates retrieved")
