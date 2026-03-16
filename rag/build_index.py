import json
from pathlib import Path
from sentence_transformers import SentenceTransformer

APP_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = APP_ROOT / "config" / "project_config.json"

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

PROJECT_ROOT = Path(config["project_root"]).resolve()

BLOCKS_FILE = PROJECT_ROOT / "blocks_summary.json"
DEPENDENCIES_FILE = PROJECT_ROOT / "block_dependencies.json"
SUMMARY_FILE = PROJECT_ROOT / "project_summary.md"
TREE_FILE = PROJECT_ROOT / "arborescence.txt"
INDEX_SELECTION_FILE = PROJECT_ROOT / "index_selection.json"

RAG_DIR = APP_ROOT / "rag"
OUTPUT_DOCS = RAG_DIR / "documents.json"
OUTPUT_EMB = RAG_DIR / "embeddings" / "embeddings.json"

ALLOWED_CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".html",
    ".css",
    ".json",
    ".yml",
    ".yaml",
    ".md",
}

STRUCTURED_FILES = {
    "project_summary.md",
    "blocks_summary.json",
    "block_dependencies.json",
    "blocks_summary.txt",
    "block_dependencies.txt",
    "arborescence.txt",
    "documents.json",
    "embeddings.json",
    "index_selection.json",
    "index_selection.txt",
}

CHUNK_SIZE_LINES = 80
MIN_NON_EMPTY_LINES = 4

model = SentenceTransformer("all-MiniLM-L6-v2")
documents = []


def safe_read_text(file_path: Path) -> str:
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return file_path.read_text(encoding="utf-8", errors="replace")


def normalize_path(file_path: Path) -> str:
    rel = file_path.relative_to(PROJECT_ROOT)
    return f"./{rel.as_posix()}"


def rel_string_to_project_path(rel_path: str) -> Path:
    raw = (rel_path or "").strip().replace("\\", "/")

    if raw.startswith("./"):
        raw = raw[2:]

    return (PROJECT_ROOT / raw).resolve()


def load_json(path: Path):
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_index_selection() -> dict:
    if not INDEX_SELECTION_FILE.exists():
        raise FileNotFoundError(
            f"Fichier de sélection introuvable : {INDEX_SELECTION_FILE}\n"
            f"Tu dois d'abord générer la sélection depuis la page index_selection.html."
        )

    with INDEX_SELECTION_FILE.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, dict):
        raise ValueError("index_selection.json invalide : format attendu = objet JSON")

    return payload


def get_selected_index_items(index_selection_payload: dict) -> list[dict]:
    items = index_selection_payload.get("items", [])

    if not isinstance(items, list):
        raise ValueError("index_selection.json invalide : 'items' doit être une liste")

    selected_items = [item for item in items if item.get("selected")]

    return selected_items


def build_file_to_blocks_mapping(blocks_data: dict) -> dict:
    file_to_blocks = {}

    blocks = blocks_data.get("blocks", [])

    for block in blocks:
        block_id = block.get("id")
        if not block_id:
            continue

        for item in block.get("items", []):
            item_path = item.get("path")
            item_type = item.get("type")

            if not item_path:
                continue

            # On ne rattache directement que les fichiers.
            if item_type == "file":
                normalized = normalize_block_item_path(item_path)
                file_to_blocks.setdefault(normalized, set()).add(block_id)

    return file_to_blocks


def normalize_block_item_path(raw_path: str) -> str:
    path = str(raw_path).strip().replace("\\", "/")
    if path.startswith("./"):
        return path
    if path.startswith(PROJECT_ROOT.as_posix() + "/"):
        rel = path[len(PROJECT_ROOT.as_posix()) + 1 :]
        return f"./{rel}"
    return f"./{path.lstrip('/')}"


def load_project_summary():
    if not SUMMARY_FILE.exists():
        return

    text = safe_read_text(SUMMARY_FILE)

    documents.append({
        "doc_id": "project_summary",
        "doc_type": "project_summary",
        "title": "Résumé global du projet",
        "text": text,
        "source_path": str(SUMMARY_FILE),
    })


def load_tree_summary():
    if not TREE_FILE.exists():
        return

    text = safe_read_text(TREE_FILE)

    documents.append({
        "doc_id": "project_tree",
        "doc_type": "tree",
        "title": "Arborescence du projet",
        "text": text,
        "source_path": str(TREE_FILE),
    })


def load_blocks(blocks_data: dict, dependencies_data: dict):
    blocks = blocks_data.get("blocks", [])
    dependencies = dependencies_data.get("dependencies", [])

    incoming = {}
    outgoing = {}

    for dep in dependencies:
        from_id = dep.get("from_block_id")
        to_id = dep.get("to_block_id")
        if from_id and to_id:
            outgoing.setdefault(from_id, []).append(to_id)
            incoming.setdefault(to_id, []).append(from_id)

    for block in blocks:
        block_id = block.get("id", "")
        file_paths = [item.get("path") for item in block.get("items", []) if item.get("path")]

        text = f"""Bloc : {block.get("name", "")}
Type : {block.get("type", "block")}

Contexte :
{block.get("context", "")}

Fichiers liés :
{file_paths}

Parents hiérarchiques :
{block.get("parent_block_ids", [])}

Enfants hiérarchiques :
{block.get("child_block_ids", [])}

Dépendances amont :
{incoming.get(block_id, [])}

Dépendances aval :
{outgoing.get(block_id, [])}
"""

        documents.append({
            "doc_id": f"block_{block_id}",
            "doc_type": "block",
            "block_id": block_id,
            "block_name": block.get("name", ""),
            "context": block.get("context", ""),
            "file_paths": file_paths,
            "parent_block_ids": block.get("parent_block_ids", []),
            "child_block_ids": block.get("child_block_ids", []),
            "highest_level": block.get("highest_level"),
            "text": text,
        })


def load_dependencies(dependencies_data: dict, blocks_data: dict):
    blocks = {b.get("id"): b for b in blocks_data.get("blocks", [])}
    dependencies = dependencies_data.get("dependencies", [])

    for i, dep in enumerate(dependencies):
        from_id = dep.get("from_block_id", "")
        to_id = dep.get("to_block_id", "")

        from_name = blocks.get(from_id, {}).get("name", from_id)
        to_name = blocks.get(to_id, {}).get("name", to_id)

        text = f"Le bloc {from_name} ({from_id}) doit être traité avant le bloc {to_name} ({to_id})."

        documents.append({
            "doc_id": f"dependency_{i}_{from_id}_{to_id}",
            "doc_type": "dependency",
            "from_block_id": from_id,
            "to_block_id": to_id,
            "text": text,
        })


def chunk_code(file_path: Path) -> list[dict]:
    text = safe_read_text(file_path)
    lines = text.splitlines()
    chunks = []

    total_lines = len(lines)
    if total_lines == 0:
        return chunks

    for start in range(0, total_lines, CHUNK_SIZE_LINES):
        end = min(start + CHUNK_SIZE_LINES, total_lines)
        chunk_text = "\n".join(lines[start:end])

        non_empty = [line for line in chunk_text.splitlines() if line.strip()]
        if len(non_empty) < MIN_NON_EMPTY_LINES:
            continue

        chunks.append({
            "text": chunk_text,
            "start_line": start + 1,
            "end_line": end,
        })

    return chunks


def should_index_as_code(selected_item: dict, path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False

    if path.suffix.lower() not in ALLOWED_CODE_EXTENSIONS:
        return False

    if path.name in STRUCTURED_FILES:
        return False

    type_hint = selected_item.get("type_hint", "")
    if type_hint in {
        "project_summary",
        "tree",
        "blocks_json",
        "blocks_txt",
        "dependencies_json",
        "dependencies_txt",
    }:
        return False

    return True


def load_selected_code(index_selection_payload: dict, file_to_blocks: dict):
    selected_items = get_selected_index_items(index_selection_payload)

    seen_paths = set()

    for item in selected_items:
        rel_path = item.get("path", "")
        if not rel_path:
            continue

        path = rel_string_to_project_path(rel_path)

        if not should_index_as_code(item, path):
            continue

        normalized_rel_path = normalize_path(path)

        if normalized_rel_path in seen_paths:
            continue
        seen_paths.add(normalized_rel_path)

        chunks = chunk_code(path)
        if not chunks:
            continue

        chunk_total = len(chunks)
        related_block_ids = sorted(list(file_to_blocks.get(normalized_rel_path, set())))

        for i, chunk in enumerate(chunks, start=1):
            documents.append({
                "doc_id": f"code_chunk_{normalized_rel_path.replace('/', '_')}_{i}",
                "doc_type": "code_chunk",
                "file_path": normalized_rel_path,
                "file_name": path.name,
                "language": path.suffix.lower().lstrip("."),
                "block_ids": related_block_ids,
                "selection_reasons": item.get("reasons", []),
                "selection_priority": item.get("priority"),
                "chunk_index": i,
                "chunk_total": chunk_total,
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"],
                "text": chunk["text"],
            })


def save_documents():
    OUTPUT_DOCS.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_DOCS.open("w", encoding="utf-8") as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)


def build_embeddings():
    OUTPUT_EMB.parent.mkdir(parents=True, exist_ok=True)

    if not documents:
        raise ValueError("Aucun document à encoder.")

    texts = [doc["text"] for doc in documents]
    embeddings = model.encode(texts, show_progress_bar=True)

    emb_data = []
    for doc, emb in zip(documents, embeddings):
        emb_data.append({
            "doc_id": doc["doc_id"],
            "doc_type": doc["doc_type"],
            "embedding": emb.tolist(),
        })

    with OUTPUT_EMB.open("w", encoding="utf-8") as f:
        json.dump(emb_data, f, ensure_ascii=False)


def print_selection_summary(index_selection_payload: dict):
    items = index_selection_payload.get("items", [])
    selected_items = [item for item in items if item.get("selected")]

    print(f"Index selection file   : {INDEX_SELECTION_FILE}")
    print(f"Selected files count   : {len(selected_items)}")

    by_reason = {}
    for item in selected_items:
        for reason in item.get("reasons", []):
            by_reason[reason] = by_reason.get(reason, 0) + 1

    if by_reason:
        print("Selected files by reason:")
        for reason, count in sorted(by_reason.items()):
            print(f"  - {reason}: {count}")


def main():
    print(f"Prompt Helper app root : {APP_ROOT}")
    print(f"Projet cible indexé    : {PROJECT_ROOT}")
    print("Loading source files...")

    blocks_data = load_json(BLOCKS_FILE)
    dependencies_data = load_json(DEPENDENCIES_FILE)
    index_selection_payload = load_index_selection()

    print_selection_summary(index_selection_payload)

    file_to_blocks = build_file_to_blocks_mapping(blocks_data)

    print("Loading project summary")
    load_project_summary()

    print("Loading tree summary")
    load_tree_summary()

    print("Loading blocks")
    load_blocks(blocks_data, dependencies_data)

    print("Loading dependencies")
    load_dependencies(dependencies_data, blocks_data)

    print("Loading selected code")
    load_selected_code(index_selection_payload, file_to_blocks)

    print(f"Saving {len(documents)} documents")
    save_documents()

    print("Building embeddings")
    build_embeddings()

    print("Done")
    print(f"Documents saved to  : {OUTPUT_DOCS}")
    print(f"Embeddings saved to : {OUTPUT_EMB}")


if __name__ == "__main__":
    main()