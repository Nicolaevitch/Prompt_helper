import json
import numpy as np
import re
from pathlib import Path
from sentence_transformers import SentenceTransformer

APP_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = APP_ROOT / "config" / "project_config.json"

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

PROJECT_ROOT = Path(config["project_root"]).resolve()

DOCS_FILE = APP_ROOT / "rag" / "documents.json"
EMB_FILE = APP_ROOT / "rag" / "embeddings" / "embeddings.json"

TOP_K_INITIAL = 8
TOP_K_FINAL = 8

print("Loading embedding model...")
model = SentenceTransformer("all-MiniLM-L6-v2")

print("Loading documents...")
with open(DOCS_FILE, encoding="utf-8") as f:
    documents = json.load(f)

print("Loading embeddings...")
with open(EMB_FILE, encoding="utf-8") as f:
    embeddings_data = json.load(f)

doc_map = {doc["doc_id"]: doc for doc in documents}

embedding_vectors = []
embedding_doc_ids = []

for item in embeddings_data:
    embedding_vectors.append(item["embedding"])
    embedding_doc_ids.append(item["doc_id"])

embedding_vectors = np.array(embedding_vectors)

embedding_index = {
    doc_id: i for i, doc_id in enumerate(embedding_doc_ids)
}

TYPE_WEIGHTS = {
    "block": 1.35,
    "code_chunk": 1.20,
    "project_summary": 1.00,
    "dependency": 0.70,
}

block_docs = [d for d in documents if d["doc_type"] == "block"]
dependency_docs = [d for d in documents if d["doc_type"] == "dependency"]
code_docs = [d for d in documents if d["doc_type"] == "code_chunk"]

block_by_id = {}
block_name_index = {}
file_to_block_ids = {}
block_to_code_docs = {}

parent_to_children = {}
child_to_parents = {}

dep_from_to = {}
dep_to_from = {}

for doc in block_docs:
    block_id = doc["block_id"]
    block_by_id[block_id] = doc

    block_name_index[doc.get("block_name", "").lower()] = block_id

    for path in doc.get("file_paths", []):
        file_to_block_ids.setdefault(path.lower(), set()).add(block_id)

    for parent_id in doc.get("parent_block_ids", []):
        child_to_parents.setdefault(block_id, set()).add(parent_id)
        parent_to_children.setdefault(parent_id, set()).add(block_id)

    for child_id in doc.get("child_block_ids", []):
        parent_to_children.setdefault(block_id, set()).add(child_id)
        child_to_parents.setdefault(child_id, set()).add(block_id)

for doc in dependency_docs:
    from_id = doc.get("from_block_id")
    to_id = doc.get("to_block_id")

    if from_id and to_id:
        dep_from_to.setdefault(from_id, set()).add(to_id)
        dep_to_from.setdefault(to_id, set()).add(from_id)

for doc in code_docs:
    for block_id in doc.get("block_ids", []):
        block_to_code_docs.setdefault(block_id, []).append(doc["doc_id"])


def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def detect_file_terms(query):
    tokens = re.findall(r"[a-zA-Z0-9_\-\.]+", query.lower())
    candidates = []

    for t in tokens:
        if re.search(r"\.[a-z0-9]{2,5}$", t):
            candidates.append(t)
        elif t in {"index", "server", "dependencies", "backend", "front"}:
            candidates.append(t)

    return list(dict.fromkeys(candidates))


def detect_doc_intent(query):
    q = query.lower()

    architecture_terms = [
        "projet",
        "but",
        "objectif",
        "structure",
        "architecture",
        "organisation",
        "résumé",
        "resume",
    ]

    dependency_terms = [
        "dépend",
        "depend",
        "avant",
        "après",
        "ordre",
        "workflow",
        "chaine",
        "chaîne",
    ]

    code_terms = [
        ".py",
        ".html",
        ".js",
        "script",
        "fichier",
        "code",
        "fonction",
        "route",
        "api",
    ]

    if any(term in q for term in dependency_terms):
        return "dependency"

    if any(term in q for term in code_terms):
        return "code_or_file"

    if any(term in q for term in architecture_terms):
        return "architecture"

    return "generic"


def boosted_score(base_score, doc, file_terms, intent):
    score = base_score
    doc_type = doc["doc_type"]

    score *= TYPE_WEIGHTS.get(doc_type, 1.0)
    text = doc.get("text", "").lower()

    for term in file_terms:
        if term in text:
            score *= 1.6

    if intent == "architecture":
        if doc_type == "project_summary":
            score *= 3.0
        elif doc_type == "block":
            score *= 1.6
        elif doc_type == "dependency":
            score *= 0.8
        elif doc_type == "code_chunk":
            score *= 0.2

    elif intent == "code_or_file":
        if doc_type == "block":
            score *= 1.6
        elif doc_type == "code_chunk":
            score *= 1.8
        elif doc_type == "dependency":
            score *= 0.6

    elif intent == "dependency":
        if doc_type == "dependency":
            score *= 2.5
        elif doc_type == "block":
            score *= 1.3
        elif doc_type == "code_chunk":
            score *= 0.4

    return score


def initial_search(query, top_k=TOP_K_INITIAL):
    query_emb = model.encode(query)

    file_terms = detect_file_terms(query)
    intent = detect_doc_intent(query)

    scored = []

    for i, emb in enumerate(embedding_vectors):
        base_score = cosine_similarity(query_emb, emb)

        doc_id = embedding_doc_ids[i]
        doc = doc_map.get(doc_id)

        score = boosted_score(base_score, doc, file_terms, intent)
        scored.append((score, doc))

    scored.sort(reverse=True, key=lambda x: x[0])
    return scored[:top_k], file_terms, intent


def find_matching_file_paths(file_terms):
    matched = set()

    for term in file_terms:
        term = term.lower()

        for file_path in file_to_block_ids.keys():
            if term in file_path:
                matched.add(file_path)

    return matched


def find_seed_blocks(query, initial_results, file_terms):
    seed_block_ids = set()
    q = query.lower()

    for _, doc in initial_results:
        if doc["doc_type"] == "block":
            seed_block_ids.add(doc["block_id"])

    for _, doc in initial_results:
        if doc["doc_type"] == "code_chunk":
            for block_id in doc.get("block_ids", []):
                seed_block_ids.add(block_id)

    for block_name, block_id in block_name_index.items():
        if block_name and block_name in q:
            seed_block_ids.add(block_id)

    matched_paths = find_matching_file_paths(file_terms)

    for path in matched_paths:
        seed_block_ids.update(file_to_block_ids.get(path.lower(), set()))

    return seed_block_ids, matched_paths


def expand_with_graph(seed_block_ids, matched_file_paths, intent):
    related_doc_ids = set()

    targeted_file_mode = bool(matched_file_paths) and intent == "code_or_file"

    if targeted_file_mode:
        targeted_block_ids = set()

        for path in matched_file_paths:
            targeted_block_ids.update(file_to_block_ids.get(path.lower(), set()))

        for block_id in targeted_block_ids:
            if block_id in block_by_id:
                related_doc_ids.add(block_by_id[block_id]["doc_id"])

            for parent_id in child_to_parents.get(block_id, set()):
                if parent_id in block_by_id:
                    related_doc_ids.add(block_by_id[parent_id]["doc_id"])

            for code_doc_id in block_to_code_docs.get(block_id, []):
                code_doc = doc_map.get(code_doc_id)

                if not code_doc:
                    continue

                if code_doc.get("file_path", "").lower() in matched_file_paths:
                    related_doc_ids.add(code_doc_id)

        return related_doc_ids

    for block_id in seed_block_ids:
        if block_id in block_by_id:
            related_doc_ids.add(block_by_id[block_id]["doc_id"])

        for parent_id in child_to_parents.get(block_id, set()):
            if parent_id in block_by_id:
                related_doc_ids.add(block_by_id[parent_id]["doc_id"])

        for child_id in list(parent_to_children.get(block_id, set()))[:3]:
            if child_id in block_by_id:
                related_doc_ids.add(block_by_id[child_id]["doc_id"])

        for prev_id in dep_to_from.get(block_id, set()):
            if prev_id in block_by_id:
                related_doc_ids.add(block_by_id[prev_id]["doc_id"])

        for next_id in dep_from_to.get(block_id, set()):
            if next_id in block_by_id:
                related_doc_ids.add(block_by_id[next_id]["doc_id"])

        for code_doc_id in block_to_code_docs.get(block_id, []):
            related_doc_ids.add(code_doc_id)

    return related_doc_ids


def final_rank(query, candidate_doc_ids, matched_file_paths, intent):
    query_emb = model.encode(query)
    ranked = []

    for doc_id in candidate_doc_ids:
        doc = doc_map[doc_id]
        idx = embedding_index.get(doc_id)

        if idx is None:
            continue

        emb = embedding_vectors[idx]
        score = cosine_similarity(query_emb, emb)

        score *= TYPE_WEIGHTS.get(doc["doc_type"], 1.0)

        if doc["doc_type"] == "code_chunk" and intent == "architecture":
            score *= 0.15

        if matched_file_paths:
            if doc["doc_type"] == "code_chunk":
                file_path = doc.get("file_path", "").lower()

                if file_path in matched_file_paths:
                    score *= 3.0
                else:
                    score *= 0.2

            elif doc["doc_type"] == "block":
                file_paths = [p.lower() for p in doc.get("file_paths", [])]

                if any(p in matched_file_paths for p in file_paths):
                    score *= 2.0
                else:
                    score *= 0.6

        if doc["doc_type"] == "code_chunk":
            text = doc.get("text", "").strip()

            if len(text.splitlines()) <= 3:
                score *= 0.4

            if text.strip().startswith("</"):
                score *= 0.3

        ranked.append((score, doc))

    ranked.sort(reverse=True, key=lambda x: x[0])
    return ranked[:TOP_K_FINAL]


def search(query):
    initial_results, file_terms, intent = initial_search(query)

    seed_block_ids, matched_file_paths = find_seed_blocks(
        query,
        initial_results,
        file_terms
    )

    graph_doc_ids = expand_with_graph(
        seed_block_ids,
        matched_file_paths,
        intent
    )

    candidate_doc_ids = {doc["doc_id"] for _, doc in initial_results}
    candidate_doc_ids.update(graph_doc_ids)

    final_results = final_rank(
        query,
        candidate_doc_ids,
        matched_file_paths,
        intent
    )

    return final_results, {
        "intent": intent,
        "file_terms": file_terms,
        "matched_file_paths": sorted(matched_file_paths),
        "seed_blocks": sorted(seed_block_ids),
        "project_root": str(PROJECT_ROOT),
        "docs_file": str(DOCS_FILE),
        "emb_file": str(EMB_FILE),
    }


def format_doc(doc):
    text = doc["text"][:700]

    header = f"""
-------------------------
doc_id : {doc['doc_id']}
type   : {doc['doc_type']}
-------------------------
"""
    return header + text


print("\nSuper RAG + graphe ready.\n")

while True:
    query = input("> ")

    if query.strip().lower() in {"exit", "quit"}:
        break

    results, debug = search(query)

    print("\nAnalyse requête :")
    print("project_root       :", debug["project_root"])
    print("docs_file          :", debug["docs_file"])
    print("emb_file           :", debug["emb_file"])
    print("intent             :", debug["intent"])
    print("file_terms         :", debug["file_terms"])
    print("matched_file_paths :", debug["matched_file_paths"])
    print("seed_blocks        :", debug["seed_blocks"])

    print("\nTop résultats :\n")

    for score, doc in results:
        print(f"score : {score:.3f}")
        print(format_doc(doc))
        print()