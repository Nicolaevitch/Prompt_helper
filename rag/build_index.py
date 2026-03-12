import os
import json
from pathlib import Path
from sentence_transformers import SentenceTransformer

PROJECT_ROOT = Path("/data/mdejurquet/test_prompt_helper")

BLOCKS_FILE = PROJECT_ROOT / "blocks_summary.json"
DEPENDENCIES_FILE = PROJECT_ROOT / "block_dependencies.json"
SUMMARY_FILE = PROJECT_ROOT / "project_summary.md"

RAG_DIR = PROJECT_ROOT / "rag"
OUTPUT_DOCS = RAG_DIR / "documents.json"
OUTPUT_EMB = RAG_DIR / "embeddings" / "embeddings.json"

EXCLUDED_DIRS = {
    "venv",
    "__pycache__",
    ".git",
    ".idea",
    ".vscode",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    "embeddings",
}

# Fichiers utiles à chunker comme "code" / contenu technique
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

# Fichiers à ne PAS chunker comme code, même si extension autorisée
EXCLUDED_FILES_FOR_CODE_INDEX = {
    "project_summary.md",
    "blocks_summary.json",
    "block_dependencies.json",
    "blocks_summary.txt",
    "block_dependencies.txt",
    "arborescence.txt",
    "documents.json",
    "embeddings.json",
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


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_block_file_mapping(blocks_data: dict) -> tuple[dict, dict]:
    block_to_files = {}
    file_to_blocks = {}

    blocks = blocks_data.get("blocks", [])

    for block in blocks:
        block_id = block["id"]
        block_to_files.setdefault(block_id, set())

        for item in block.get("items", []):
            path = item.get("path")
            if not path:
                continue

            if item.get("type") == "file":
                block_to_files[block_id].add(path)
                file_to_blocks.setdefault(path, set()).add(block_id)

            elif item.get("type") == "folder":
                block_to_files[block_id].add(path)

    return block_to_files, file_to_blocks


def enrich_folder_blocks_with_real_files(block_to_files: dict, file_to_blocks: dict):
    all_project_files = []

    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

        for file_name in files:
            path = Path(root) / file_name
            if path.name in EXCLUDED_FILES_FOR_CODE_INDEX:
                continue
            if path.suffix.lower() not in ALLOWED_CODE_EXTENSIONS:
                continue
            rel_path = normalize_path(path)
            all_project_files.append(rel_path)

    for block_id, paths in list(block_to_files.items()):
        expanded_paths = set()

        for path in paths:
            expanded_paths.add(path)

            # si c'est un dossier logique (pas d'extension)
            if not Path(path).suffix:
                prefix = path.rstrip("/") + "/"
                for project_file in all_project_files:
                    if project_file.startswith(prefix):
                        expanded_paths.add(project_file)
                        file_to_blocks.setdefault(project_file, set()).add(block_id)

        block_to_files[block_id] = expanded_paths


def load_project_summary():
    if not SUMMARY_FILE.exists():
        return

    text = safe_read_text(SUMMARY_FILE)

    documents.append({
        "doc_id": "project_summary",
        "doc_type": "project_summary",
        "title": "Résumé global du projet",
        "text": text,
        "source_path": str(SUMMARY_FILE.name),
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
        block_id = block["id"]
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
    blocks = {b["id"]: b for b in blocks_data.get("blocks", [])}
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


def load_code(file_to_blocks: dict):
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

        for file_name in files:
            path = Path(root) / file_name
            ext = path.suffix.lower()

            if ext not in ALLOWED_CODE_EXTENSIONS:
                continue

            if path.name in EXCLUDED_FILES_FOR_CODE_INDEX:
                continue

            rel_path = normalize_path(path)

            # sécurité supplémentaire
            if rel_path.startswith("./rag/embeddings"):
                continue

            chunks = chunk_code(path)
            if not chunks:
                continue

            chunk_total = len(chunks)
            related_block_ids = sorted(list(file_to_blocks.get(rel_path, set())))

            for i, chunk in enumerate(chunks, start=1):
                documents.append({
                    "doc_id": f"code_chunk_{rel_path.replace('/', '_')}_{i}",
                    "doc_type": "code_chunk",
                    "file_path": rel_path,
                    "file_name": path.name,
                    "language": ext.lstrip("."),
                    "block_ids": related_block_ids,
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


def main():
    print("Loading source files...")

    blocks_data = load_json(BLOCKS_FILE)
    dependencies_data = load_json(DEPENDENCIES_FILE)

    block_to_files, file_to_blocks = build_block_file_mapping(blocks_data)
    enrich_folder_blocks_with_real_files(block_to_files, file_to_blocks)

    print("Loading project summary")
    load_project_summary()

    print("Loading blocks")
    load_blocks(blocks_data, dependencies_data)

    print("Loading dependencies")
    load_dependencies(dependencies_data, blocks_data)

    print("Loading code")
    load_code(file_to_blocks)

    print(f"Saving {len(documents)} documents")
    save_documents()

    print("Building embeddings")
    build_embeddings()

    print("Done")


if __name__ == "__main__":
    main()