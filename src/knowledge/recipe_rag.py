"""

Member 2 - Semantic Recipe Retrieval (RAG)



This module is intentionally additive. It does not modify the existing

Recipe Agent, Recipe Repository, or any existing project file.



Responsibilities from the Member 2 sprint:

1. Build searchable recipe text from:

   recipe_name, cuisine_type, meal_type, diet_labels,

   health_labels, ingredients.

2. Generate embeddings with a configurable embedding model.

3. Store/search embeddings with NumPy cosine similarity.

4. Return recipe IDs for natural-language preferences.

5. Apply structured hard-constraint filtering AFTER semantic retrieval.

6. Never treat semantic similarity as a replacement for dietary/allergy/

   meal-type constraints.



Default embedding model:

    sentence-transformers/all-MiniLM-L6-v2



The embedding model can be replaced through the constructor without changing

the retrieval contract.

"""



from __future__ import annotations



import ast

import json

from dataclasses import dataclass

from pathlib import Path

from typing import Any, Iterable, Sequence



import numpy as np

import pandas as pd



from src.knowledge.repository import (

    DEFAULT_KB_PATH,

    RecipeRepository,

    normalize,

)



# Import the optional sentence-transformers package only when needed.
# Some Windows installations block pyarrow DLLs loaded indirectly by that package.

class _TransformersMeanPoolingEncoder:
    """Compatible inference encoder for all-MiniLM-L6-v2 without datasets/pyarrow."""

    def __init__(self, model_name: str):
        if model_name != "sentence-transformers/all-MiniLM-L6-v2":
            raise ImportError(
                "Direct Transformers fallback is validated only for "
                "sentence-transformers/all-MiniLM-L6-v2. "
                "Install/fix sentence-transformers for other models."
            )
        import torch
        from transformers import AutoModel, AutoTokenizer

        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
        self.model.eval()

    def encode(self, sentences, convert_to_numpy=True,
               normalize_embeddings=True, show_progress_bar=False):
        import numpy as np
        if isinstance(sentences, str):
            sentences = [sentences]
        sentences = list(sentences)
        if not sentences:
            return np.empty((0, self.model.config.hidden_size), dtype=np.float32)
        results = []
        # SentenceTransformer's MiniLM model uses mean pooling, 256 tokens.
        with self.torch.inference_mode():
            for start in range(0, len(sentences), 32):
                batch = sentences[start:start + 32]
                inputs = self.tokenizer(
                    batch, padding=True, truncation=True, max_length=256,
                    return_tensors="pt"
                )
                hidden = self.model(**inputs).last_hidden_state
                mask = inputs["attention_mask"].unsqueeze(-1).to(hidden.dtype)
                pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
                if normalize_embeddings:
                    pooled = self.torch.nn.functional.normalize(pooled, p=2, dim=1)
                results.append(pooled.cpu().numpy())
        output = np.concatenate(results, axis=0).astype(np.float32)
        return output if convert_to_numpy else self.torch.from_numpy(output)


DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

DEFAULT_RAW_RECIPE_PATH = DEFAULT_KB_PATH.parents[1] / "raw" / "recipes.csv"



# These are the only recipe fields used to create the semantic document,

# matching the sprint instructions.

SEARCHABLE_FIELDS = (

    "recipe_name",

    "cuisine_type",

    "meal_type",

    "diet_labels",

    "health_labels",

    "ingredients",

)



LIST_LIKE_FIELDS = {

    "cuisine_type",

    "meal_type",

    "diet_labels",

    "health_labels",

    "ingredients",

}





def _parse_list_like(value: Any) -> list[str]:

    """Convert CSV/list-like values into clean strings without inventing data."""

    if value is None:

        return []



    if isinstance(value, (list, tuple, set)):

        values = list(value)

    elif isinstance(value, float) and np.isnan(value):

        return []

    elif isinstance(value, str):

        text = value.strip()

        if not text:

            return []



        try:

            parsed = ast.literal_eval(text)

        except (ValueError, SyntaxError):

            parsed = None



        if isinstance(parsed, (list, tuple, set)):

            values = list(parsed)

        else:

            values = [text]

    else:

        values = [value]



    return [

        str(item).strip()

        for item in values

        if item is not None and str(item).strip()

    ]





def _display_value(value: Any, field: str) -> str:

    """Render one KB value as concise searchable text."""

    if field == "ingredients":

        parsed = value



        if isinstance(value, str):

            text = value.strip()

            if not text:

                return ""



            try:

                parsed = ast.literal_eval(text)

            except (ValueError, SyntaxError):

                try:

                    parsed = json.loads(text)

                except (ValueError, TypeError):

                    parsed = text



        if isinstance(parsed, (list, tuple)):

            ingredient_names: list[str] = []



            for item in parsed:

                if isinstance(item, dict):

                    food = item.get("food")

                    ingredient_text = item.get("text")



                    if food:

                        ingredient_names.append(str(food).strip())

                    elif ingredient_text:

                        ingredient_names.append(

                            str(ingredient_text).strip()

                        )

                elif item is not None and str(item).strip():

                    ingredient_names.append(str(item).strip())



            return ", ".join(

                dict.fromkeys(

                    item for item in ingredient_names if item

                )

            )



        return str(parsed).strip()



    if field in LIST_LIKE_FIELDS:

        return ", ".join(_parse_list_like(value))



    if value is None:

        return ""



    if isinstance(value, float) and np.isnan(value):

        return ""



    return str(value).strip()





def build_recipe_description(recipe: pd.Series | dict[str, Any]) -> str:

    """

    Create the semantic document for one recipe.



    Only the six sprint-approved fields are included.

    Empty fields are omitted rather than replaced with guessed values.

    """

    parts: list[str] = []



    for field in SEARCHABLE_FIELDS:

        value = (

            recipe.get(field)

            if isinstance(recipe, dict)

            else recipe.get(field)

        )

        rendered = _display_value(value, field)



        if rendered:

            label = field.replace("_", " ")

            parts.append(f"{label}: {rendered}")



    return ". ".join(parts)





def _load_ingredient_lookup(

    raw_recipe_path: str | Path | None,

) -> dict[str, Any]:

    """

    Load only ingredient information from the existing raw recipe source.



    The current cleaned Recipe KB intentionally does not retain the

    `ingredients` column, so the RAG layer reads that field from the existing

    raw recipe file without modifying or replacing the cleaned KB.

    """

    if raw_recipe_path is None:

        return {}



    path = Path(raw_recipe_path)



    if not path.exists():

        return {}



    raw = pd.read_csv(path)



    id_col = next((c for c in ("recipe_id", "recipie_id") if c in raw.columns), None)
    if id_col is None or "ingredients" not in raw.columns:
        return {}

    lookup: dict[str, Any] = {}



    for _, row in raw[[id_col, "ingredients"]].iterrows():

        recipe_id = str(row[id_col]).strip().upper()

        if not recipe_id:

            continue

        lookup[recipe_id] = row["ingredients"]



    return lookup





def build_recipe_documents(

    recipe_kb: pd.DataFrame,

    ingredient_lookup: dict[str, Any] | None = None,

) -> pd.DataFrame:

    """

    Build semantic documents from the existing Recipe KB.



    The cleaned KB supplies recipe_name, cuisine_type, meal_type,

    diet_labels and health_labels. The existing raw recipe source supplies

    ingredients because the cleaned KB does not retain that column.



    Returns a copy containing:

        recipe_id

        recipe_text

    """

    required = {

        "recipe_id",

        "recipe_name",

        "cuisine_type",

        "meal_type",

        "diet_labels",

        "health_labels",

    }

    missing = required.difference(recipe_kb.columns)



    if missing:

        raise ValueError(

            "Recipe KB is missing required RAG fields: "

            + ", ".join(sorted(missing))

        )



    result = recipe_kb[

        [

            "recipe_id",

            "recipe_name",

            "cuisine_type",

            "meal_type",

            "diet_labels",

            "health_labels",

        ]

    ].copy()



    result["recipe_id"] = (

        result["recipe_id"]

        .astype(str)

        .str.strip()

        .str.upper()

    )



    if ingredient_lookup:

        result["ingredients"] = result["recipe_id"].map(

            ingredient_lookup

        )

    else:

        result["ingredients"] = ""



    result["recipe_text"] = result.apply(

        build_recipe_description,

        axis=1,

    )



    result = result[

        result["recipe_id"].ne("")

        & result["recipe_text"].ne("")

    ]



    result = result.drop_duplicates(

        subset=["recipe_id"],

        keep="first",

    ).reset_index(drop=True)



    return result[["recipe_id", "recipe_text"]]





@dataclass(frozen=True)

class RetrievalResult:

    """Stable result object for semantic recipe retrieval."""



    candidate_recipe_ids: list[str]

    scores: list[float]

    query: str



    def to_dict(self) -> dict[str, Any]:

        return {

            "candidate_recipe_ids": self.candidate_recipe_ids,

            "scores": self.scores,

            "query": self.query,

        }





class RecipeRAG:

    """

    Semantic Recipe Retrieval layer for Member 2.



    The class is additive to the existing RecipeAgent.



    Typical flow:

        User preference

            -> RecipeRAG semantic retrieval

            -> hard-constraint filtering

            -> candidate_recipe_ids

            -> existing RecipeAgent / Manager contract



    Hard constraints are applied after semantic retrieval. Therefore a

    semantically similar recipe can never override a supplied hard constraint.

    """



    def __init__(

        self,

        kb_path: str | Path = DEFAULT_KB_PATH,

        embedding_model: str = DEFAULT_EMBEDDING_MODEL,

        model: Any | None = None,

        repository: RecipeRepository | None = None,

        raw_recipe_path: str | Path = DEFAULT_RAW_RECIPE_PATH,

    ) -> None:

        self.kb_path = Path(kb_path)

        self.embedding_model_name = embedding_model



        self.repository = (

            repository

            if repository is not None

            else RecipeRepository.from_csv(self.kb_path)

        )



        self.recipe_kb = self.repository.to_frame()

        self.raw_recipe_path = Path(raw_recipe_path)

        ingredient_lookup = _load_ingredient_lookup(

            self.raw_recipe_path

        )

        self.documents = build_recipe_documents(

            self.recipe_kb,

            ingredient_lookup=ingredient_lookup,

        )



        self.model = model

        self.index = None

        self._dimension: int | None = None



    # ------------------------------------------------------------------

    # Dependency handling

    # ------------------------------------------------------------------



    def _get_model(self):
        if self.model is not None:
            return self.model

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as original_error:
            try:
                self.model = _TransformersMeanPoolingEncoder(self.embedding_model_name)
            except (ImportError, OSError, RuntimeError) as fallback_error:
                raise ImportError(
                    "SentenceTransformer import failed, and the direct Transformers "
                    "fallback could not initialize. Original error: "
                    f"{original_error}. Fallback error: {fallback_error}"
                ) from fallback_error
        else:
            self.model = SentenceTransformer(self.embedding_model_name)
        return self.model

    # ------------------------------------------------------------------

    # Embedding

    # ------------------------------------------------------------------



    def embed_texts(

        self,

        texts: Sequence[str],

    ) -> np.ndarray:

        """

        Generate normalized float32 embeddings.



        Normalization makes dot-product search equivalent to cosine

        similarity for this retrieval use case.

        """

        if len(texts) == 0:

            return np.empty((0, 0), dtype=np.float32)



        model = self._get_model()



        embeddings = model.encode(

            list(texts),

            convert_to_numpy=True,

            normalize_embeddings=True,

            show_progress_bar=False,

        )



        embeddings = np.asarray(

            embeddings,

            dtype=np.float32,

        )



        if embeddings.ndim != 2:

            raise ValueError(

                "Embedding model must return a 2-D embedding matrix."

            )



        return embeddings



    # ------------------------------------------------------------------

    # Index construction / persistence

    # ------------------------------------------------------------------



    def build_index(self) -> None:
        """Build an exact NumPy cosine-similarity index."""
        if self.documents.empty:
            raise ValueError("No recipe documents available to index.")
        embeddings = self.embed_texts(self.documents["recipe_text"].tolist())
        if embeddings.ndim != 2 or embeddings.shape[0] != len(self.documents) or embeddings.shape[1] == 0:
            raise ValueError("Embedding matrix shape does not match recipe documents.")
        if not np.all(np.isfinite(embeddings)):
            raise ValueError("Embeddings must be finite.")
        # Accumulate norms in float64 to avoid float32 overflow/underflow.
        embeddings64 = embeddings.astype(np.float64)
        norms = np.linalg.norm(embeddings64, axis=1, keepdims=True)
        if not np.all(np.isfinite(norms)) or np.any(norms <= 0):
            raise ValueError("Embeddings must have finite, nonzero norms.")
        normalized = embeddings64 / norms
        if not np.all(np.isfinite(normalized)):
            raise ValueError("Normalized embeddings contain invalid values.")
        self.index = np.ascontiguousarray(normalized, dtype=np.float32)
        self._dimension = int(self.index.shape[1])

    def _document_hash(self) -> str:
        import hashlib
        content = self.documents[["recipe_id", "recipe_text"]].to_json(orient="records")
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def save_index(self, index_path: str | Path, metadata_path: str | Path | None = None) -> None:
        """Save embeddings as .npz and the recipe mapping as JSON."""
        if self.index is None:
            raise RuntimeError("Build the vector index before saving it.")
        index_path = Path(index_path)
        if index_path.suffix.lower() != ".npz":
            raise ValueError("NumPy index path must end in .npz (not .index).")
        index_path.parent.mkdir(parents=True, exist_ok=True)
        with index_path.open("wb") as f:
            np.savez_compressed(f, embeddings=self.index)
        metadata_path = Path(metadata_path) if metadata_path is not None else index_path.with_suffix(".json")
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata = {
            "backend": "numpy-cosine-v1",
            "embedding_model": self.embedding_model_name,
            "dimension": self._dimension,
            "recipe_ids": self.documents["recipe_id"].tolist(),
            "document_hash": self._document_hash(),
        }
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    def load_index(self, index_path: str | Path, metadata_path: str | Path | None = None) -> None:
        """Load a saved NumPy index, rejecting stale or mismatched metadata."""
        index_path = Path(index_path)
        if index_path.suffix.lower() != ".npz":
            raise ValueError("NumPy index path must end in .npz (not .index).")
        metadata_path = Path(metadata_path) if metadata_path is not None else index_path.with_suffix(".json")
        if not index_path.exists():
            raise FileNotFoundError(f"NumPy index not found: {index_path}")
        if not metadata_path.exists():
            raise FileNotFoundError(f"RAG metadata not found: {metadata_path}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("backend") != "numpy-cosine-v1":
            raise ValueError("Index backend mismatch; rebuild the index.")
        if metadata.get("recipe_ids") != self.documents["recipe_id"].tolist():
            raise ValueError("Recipe ID mapping changed; rebuild the index.")
        if metadata.get("embedding_model") != self.embedding_model_name:
            raise ValueError("Embedding model changed; rebuild the index.")
        if metadata.get("document_hash") != self._document_hash():
            raise ValueError("Recipe documents changed; rebuild the index.")
        with np.load(index_path, allow_pickle=False) as data:
            embeddings = np.asarray(data["embeddings"], dtype=np.float32)
        if embeddings.ndim != 2 or embeddings.shape[0] != len(self.documents) or embeddings.shape[1] == 0:
            raise ValueError("Saved embeddings do not match recipe documents.")
        if metadata.get("dimension") != embeddings.shape[1]:
            raise ValueError("Saved embedding dimension mismatch.")
        norms = np.linalg.norm(embeddings, axis=1)
        if not np.all(np.isfinite(embeddings)) or not np.allclose(norms, 1.0, atol=1e-3):
            raise ValueError("Saved embeddings are invalid or not normalized.")
        self.index = np.ascontiguousarray(embeddings)
        self._dimension = int(embeddings.shape[1])

    def _ensure_index(self) -> None:

        if self.index is None:

            self.build_index()



    def retrieve(

        self,

        query: str,

        top_k: int = 10,

    ) -> RetrievalResult:

        """

        Retrieve semantically similar recipe IDs.



        This method performs semantic retrieval only. Use

        retrieve_with_constraints() when hard constraints must be enforced.

        """

        if not isinstance(query, str) or not query.strip():

            raise ValueError(

                "query must be a non-empty string."

            )



        if (

            not isinstance(top_k, int)

            or isinstance(top_k, bool)

            or top_k <= 0

        ):

            raise ValueError(

                "top_k must be a positive integer."

            )



        self._ensure_index()



        query_embedding = self.embed_texts(

            [query.strip()]

        )



        k = min(

            top_k,

            len(self.documents),

        )



        if query_embedding.shape[1] != self._dimension:
            raise ValueError("Query embedding dimension differs from saved index.")
        query_vector = query_embedding[0]
        if not np.all(np.isfinite(query_vector)):
            raise ValueError("Query embedding contains NaN or infinity.")
        query64 = query_vector.astype(np.float64)
        query_norm = np.linalg.norm(query64)
        if not np.isfinite(query_norm) or query_norm <= 0:
            raise ValueError("Invalid query embedding norm.")
        normalized_query = query64 / query_norm
        if not np.all(np.isfinite(normalized_query)):
            raise ValueError("Normalized query contains invalid values.")
        if self.index is None or not np.all(np.isfinite(self.index)):
            raise ValueError("Recipe index contains invalid values.")
        # Compute dot products without BLAS-backed matrix multiplication.
        # Process in batches to avoid allocating a full index-sized temporary.
        # This isolates the macOS matmul warnings while retaining cosine ranking.
        similarities = np.empty(self.index.shape[0], dtype=np.float64)
        batch_size = 1024
        for start in range(0, self.index.shape[0], batch_size):
            end = min(start + batch_size, self.index.shape[0])
            batch = self.index[start:end].astype(np.float64)
            with np.errstate(divide="raise", over="raise", invalid="raise"):
                try:
                    similarities[start:end] = np.sum(
                        batch * normalized_query[None, :],
                        axis=1,
                        dtype=np.float64,
                    )
                except FloatingPointError as error:
                    raise ValueError(
                        "Numerical failure during recipe similarity calculation."
                    ) from error
        if not np.all(np.isfinite(similarities)):
            raise ValueError("Similarity scores contain NaN or infinity.")
        if np.any(similarities < -1.001) or np.any(similarities > 1.001):
            raise ValueError("Cosine similarity scores are outside the valid range.")
        positions = np.argsort(-similarities, kind="stable")[:k]
        scores = similarities[positions]

        ids: list[str] = []

        similarities: list[float] = []



        for score, position in zip(

            scores,

            positions,

        ):

            if position < 0:

                continue



            ids.append(

                self.documents.iloc[position]["recipe_id"]

            )

            similarities.append(

                float(score)

            )



        return RetrievalResult(

            candidate_recipe_ids=ids,

            scores=similarities,

            query=query.strip(),

        )



    # ------------------------------------------------------------------

    # Hard constraints

    # ------------------------------------------------------------------



    @staticmethod

    def _normalize_values(

        values: str | Iterable[str] | None,

    ) -> list[str]:

        if values is None:

            return []



        if isinstance(values, str):

            values = [values]



        return [

            normalize(value)

            for value in values

            if value is not None

            and normalize(value)

        ]



    def _filter_ids_by_constraints(

        self,

        recipe_ids: Sequence[str],

        *,

        dietary_restrictions: str | Iterable[str] | None = None,

        allergies: str | Iterable[str] | None = None,

        meal_type: str | None = None,

        cuisines: str | Iterable[str] | None = None,

    ) -> list[str]:

        """

        Apply structured hard constraints to semantically retrieved IDs.



        Constraint behavior:

        - dietary_restrictions: existing RecipeRepository diet filters

        - allergies: existing RecipeRepository caution exclusion

        - meal_type: existing meal-type filter

        - cuisines: soft preference, left to Recipe Agent ranking



        Caution labels alone do not guarantee allergen safety.
        The Ingredient Agent must verify ingredients before selection.
        This method intentionally does not invent allergy mappings. It

        normalizes the supplied allergy names and excludes recipes whose

        existing KB caution labels match those normalized names.

        """

        ordered_ids = [

            str(recipe_id).strip().upper()

            for recipe_id in recipe_ids

            if str(recipe_id).strip()

        ]



        if not ordered_ids:

            return []



        allowed = set(ordered_ids)



        dietary = self._normalize_values(

            dietary_restrictions

        )



        for diet in dietary:

            allowed &= set(

                self.repository.filter_by_diet(

                    diet

                ).ids()

            )



        if meal_type:

            allowed &= set(

                self.repository.filter_by_meal_type(

                    meal_type

                ).ids()

            )



        # Cuisine is a soft preference in the existing Recipe Agent.
        # Do not reject candidates solely because of cuisine here.
        # The Agent may use cuisines to prioritize candidates.

        allergy_values = self._normalize_values(

            allergies

        )



        if allergy_values:

            safe_ids = set(

                self.repository.exclude_cautions(

                    *allergy_values

                ).ids()

            )

            allowed &= safe_ids



        # Preserve semantic ranking while applying the hard-filter result.

        return [

            recipe_id

            for recipe_id in ordered_ids

            if recipe_id in allowed

        ]



    def retrieve_with_constraints(

        self,

        query: str,

        *,

        top_k: int = 20,

        dietary_restrictions: str | Iterable[str] | None = None,

        allergies: str | Iterable[str] | None = None,

        meal_type: str | None = None,

        cuisines: str | Iterable[str] | None = None,

    ) -> RetrievalResult:

        """

        Semantic retrieval followed by structured hard-constraint filtering.



        top_k should normally be larger than the final candidate count because

        filtering can remove semantically relevant results.

        """

        semantic_result = self.retrieve(

            query=query,

            top_k=top_k,

        )



        safe_ids = self._filter_ids_by_constraints(

            semantic_result.candidate_recipe_ids,

            dietary_restrictions=dietary_restrictions,

            allergies=allergies,

            meal_type=meal_type,

            cuisines=cuisines,

        )



        score_by_id = dict(

            zip(

                semantic_result.candidate_recipe_ids,

                semantic_result.scores,

            )

        )



        return RetrievalResult(

            candidate_recipe_ids=safe_ids,

            scores=[

                score_by_id[recipe_id]

                for recipe_id in safe_ids

            ],

            query=semantic_result.query,

        )





def build_and_save_recipe_index(

    index_path: str | Path,

    metadata_path: str | Path | None = None,

    *,

    kb_path: str | Path = DEFAULT_KB_PATH,

    embedding_model: str = DEFAULT_EMBEDDING_MODEL,

) -> RecipeRAG:

    """

    Convenience function for the Member 2 embedding/index pipeline.

    """

    rag = RecipeRAG(

        kb_path=kb_path,

        embedding_model=embedding_model,

    )

    rag.build_index()

    rag.save_index(

        index_path=index_path,

        metadata_path=metadata_path,

    )

    return rag
