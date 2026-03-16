#!/usr/bin/env python3
import json
import os
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONT_DIR = os.path.join(APP_DIR, "front")
CONFIG_FILE = os.path.join(APP_DIR, "config", "project_config.json")

HOST = "127.0.0.1"
PORT = 8010

ALWAYS_INCLUDE_KEYS = [
    "tree_file",
    "blocks_json",
    "blocks_txt",
    "deps_json",
    "deps_txt",
    "project_summary",
]


def now_utc_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def load_project_root() -> str:
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"Config introuvable : {CONFIG_FILE}")

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    project_root = data.get("project_root", "").strip()

    if not project_root:
        raise ValueError("project_root est vide dans project_config.json")

    if not os.path.isdir(project_root):
        raise NotADirectoryError(f"project_root invalide : {project_root}")

    return project_root


def get_project_paths() -> dict:
    project_root = load_project_root()
    return {
        "project_root": project_root,
        "tree_file": os.path.join(project_root, "arborescence.txt"),
        "blocks_json": os.path.join(project_root, "blocks_summary.json"),
        "blocks_txt": os.path.join(project_root, "blocks_summary.txt"),
        "deps_json": os.path.join(project_root, "block_dependencies.json"),
        "deps_txt": os.path.join(project_root, "block_dependencies.txt"),
        "project_summary": os.path.join(project_root, "project_summary.md"),
        "readme_file": os.path.join(project_root, "README.md"),
        "index_selection_json": os.path.join(project_root, "index_selection.json"),
        "index_selection_txt": os.path.join(project_root, "index_selection.txt"),
    }


def build_blocks_text_summary(payload: dict) -> str:
    lines = []
    lines.append(f"Généré le : {payload.get('generated_at', '')}")
    lines.append(f"Sauvegardé le : {payload.get('saved_at', '')}")
    lines.append(f"Racine : {payload.get('source_tree_root') or '-'}")
    lines.append(f"Vue courante : {payload.get('current_view_path') or '-'}")
    lines.append(f"Profondeur affichée : {payload.get('depth_setting')}")
    blocks = payload.get("blocks", [])
    lines.append(f"Nombre de blocs : {len(blocks)}")
    lines.append("")

    for idx, block in enumerate(blocks, start=1):
        lines.append(f"=== Bloc {idx} ===")
        lines.append(f"ID : {block.get('id', '')}")
        lines.append(f"Nom : {block.get('name', '')}")
        lines.append(f"Type : {block.get('type', 'block')}")
        lines.append(f"Création : {block.get('created_at', '')}")
        lines.append(f"Niveau le plus haut : {block.get('highest_level', '-')}")
        lines.append(f"Contexte : {block.get('context', '')}")

        parent_ids = block.get("parent_block_ids", [])
        child_ids = block.get("child_block_ids", [])

        lines.append(
            f"Parents hiérarchiques : {', '.join(parent_ids) if parent_ids else '(aucun)'}"
        )
        lines.append(
            f"Enfants hiérarchiques : {', '.join(child_ids) if child_ids else '(aucun)'}"
        )

        lines.append("Éléments :")
        items = block.get("items", [])
        if not items:
            lines.append("  - (aucun élément)")
        else:
            for item in items:
                lines.append(
                    f"  - [{item.get('type', '')}] {item.get('path', '')} "
                    f"(niveau {item.get('depth', '')})"
                )
        lines.append("")

    return "\n".join(lines)


def build_dependencies_text_summary(payload: dict) -> str:
    lines = []
    lines.append(f"Généré le : {payload.get('generated_at', '')}")
    lines.append(f"Sauvegardé le : {payload.get('saved_at', '')}")
    dependencies = payload.get("dependencies", [])
    lines.append(f"Nombre de dépendances : {len(dependencies)}")
    lines.append("")

    for idx, dep in enumerate(dependencies, start=1):
        lines.append(f"=== Dépendance {idx} ===")
        lines.append(f"from_block_id : {dep.get('from_block_id', '')}")
        lines.append(f"to_block_id   : {dep.get('to_block_id', '')}")
        lines.append(f"created_at    : {dep.get('created_at', '')}")
        lines.append("")

    return "\n".join(lines)


def default_blocks_payload() -> dict:
    return {
        "generated_at": now_utc_iso(),
        "source_tree_root": None,
        "current_view_path": None,
        "depth_setting": 1,
        "blocks": [],
    }


def default_dependencies_payload() -> dict:
    return {
        "generated_at": now_utc_iso(),
        "dependencies": [],
    }


def normalize_rel_path(project_root: str, raw_path: str) -> str:
    if not raw_path:
        return ""
    raw_path = raw_path.strip().replace("\\", "/")

    if raw_path.startswith("./"):
        raw_path = raw_path[2:]

    abs_project_root = os.path.abspath(project_root)
    abs_raw = os.path.abspath(raw_path)

    if abs_raw.startswith(abs_project_root + os.sep):
        rel = os.path.relpath(abs_raw, abs_project_root)
        return rel.replace("\\", "/")

    if raw_path.startswith(abs_project_root.replace("\\", "/") + "/"):
        rel = raw_path[len(abs_project_root.replace("\\", "/")) + 1 :]
        return rel.replace("\\", "/")

    if raw_path.startswith(project_root.replace("\\", "/") + "/"):
        rel = raw_path[len(project_root.replace("\\", "/")) + 1 :]
        return rel.replace("\\", "/")

    if "/" in raw_path:
        root_name = os.path.basename(abs_project_root).replace("\\", "/")
        prefix = root_name + "/"
        if raw_path.startswith(prefix):
            return raw_path[len(prefix):]

    return raw_path


def safe_rel_to_abs(project_root: str, rel_path: str) -> str:
    rel_path = normalize_rel_path(project_root, rel_path)
    return os.path.abspath(os.path.join(project_root, rel_path))


def detect_type_hint(rel_path: str) -> str:
    lower = rel_path.lower()
    base = os.path.basename(lower)

    if base == "project_summary.md":
        return "project_summary"
    if base == "arborescence.txt":
        return "tree"
    if base == "blocks_summary.json":
        return "blocks_json"
    if base == "blocks_summary.txt":
        return "blocks_txt"
    if base == "block_dependencies.json":
        return "dependencies_json"
    if base == "block_dependencies.txt":
        return "dependencies_txt"
    if base == "readme.md":
        return "readme"
    return "source_code"


def make_candidate(rel_path: str, abs_path: str, selected: bool, locked: bool, reasons=None,
                   block_ids=None, block_names=None, dependency_pairs=None, priority=50):
    return {
        "path": rel_path.replace("\\", "/"),
        "abs_path": abs_path,
        "exists": os.path.isfile(abs_path),
        "selected": selected,
        "locked": locked,
        "reasons": sorted(set(reasons or [])),
        "block_ids": sorted(set(block_ids or [])),
        "block_names": sorted(set(block_names or [])),
        "dependency_pairs": sorted(set(dependency_pairs or [])),
        "priority": priority,
        "type_hint": detect_type_hint(rel_path),
    }


def add_candidate_entry(candidates_map: dict, rel_path: str, abs_path: str, *,
                        selected=False, locked=False, reason=None,
                        block_id=None, block_name=None, dependency_pair=None, priority=50):
    key = rel_path.replace("\\", "/")

    if key not in candidates_map:
        candidates_map[key] = make_candidate(
            rel_path=key,
            abs_path=abs_path,
            selected=selected,
            locked=locked,
            reasons=[reason] if reason else [],
            block_ids=[block_id] if block_id else [],
            block_names=[block_name] if block_name else [],
            dependency_pairs=[dependency_pair] if dependency_pair else [],
            priority=priority,
        )
        return

    entry = candidates_map[key]
    entry["selected"] = entry["selected"] or selected
    entry["locked"] = entry["locked"] or locked
    entry["priority"] = max(entry["priority"], priority)

    if reason:
        entry["reasons"] = sorted(set(entry["reasons"] + [reason]))
    if block_id:
        entry["block_ids"] = sorted(set(entry["block_ids"] + [block_id]))
    if block_name:
        entry["block_names"] = sorted(set(entry["block_names"] + [block_name]))
    if dependency_pair:
        entry["dependency_pairs"] = sorted(set(entry["dependency_pairs"] + [dependency_pair]))


def load_json_file(path: str, default_value):
    if not os.path.exists(path):
        return default_value
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_blocks_payload(paths: dict) -> dict:
    return load_json_file(paths["blocks_json"], default_blocks_payload())


def load_dependencies_payload(paths: dict) -> dict:
    return load_json_file(paths["deps_json"], default_dependencies_payload())


def load_saved_index_selection(paths: dict) -> dict:
    if not os.path.exists(paths["index_selection_json"]):
        return {
            "generated_at": now_utc_iso(),
            "saved_at": None,
            "project_root": paths["project_root"],
            "selected_paths": [],
            "items": [],
        }

    with open(paths["index_selection_json"], "r", encoding="utf-8") as f:
        return json.load(f)


def build_index_selection_txt(payload: dict) -> str:
    lines = []
    lines.append(f"Généré le : {payload.get('generated_at', '')}")
    lines.append(f"Sauvegardé le : {payload.get('saved_at', '')}")
    lines.append(f"Projet : {payload.get('project_root', '')}")
    lines.append("")

    items = payload.get("items", [])
    selected_items = [x for x in items if x.get("selected")]

    lines.append(f"Nombre de fichiers sélectionnés : {len(selected_items)}")
    lines.append("")

    for idx, item in enumerate(sorted(selected_items, key=lambda x: x.get("path", "")), start=1):
        lines.append(f"{idx}. {item.get('path', '')}")
        reasons = item.get("reasons", [])
        if reasons:
            lines.append(f"   raisons : {', '.join(reasons)}")
        if item.get("block_names"):
            lines.append(f"   blocs : {', '.join(item['block_names'])}")
        if item.get("dependency_pairs"):
            lines.append(f"   dépendances : {', '.join(item['dependency_pairs'])}")
        lines.append("")

    return "\n".join(lines)


def build_index_candidates(paths: dict) -> dict:
    project_root = paths["project_root"]
    blocks_payload = load_blocks_payload(paths)
    dependencies_payload = load_dependencies_payload(paths)
    saved_selection = load_saved_index_selection(paths)

    saved_selected_paths = set(saved_selection.get("selected_paths", []))
    saved_items_by_path = {
        item.get("path"): item for item in saved_selection.get("items", []) if item.get("path")
    }

    blocks = blocks_payload.get("blocks", []) if isinstance(blocks_payload, dict) else []
    dependencies = dependencies_payload.get("dependencies", []) if isinstance(dependencies_payload, dict) else []

    blocks_by_id = {}
    for block in blocks:
        block_id = block.get("id")
        if block_id:
            blocks_by_id[block_id] = block

    candidates_map = {}

    # always include générés par Prompt Helper
    for key in ALWAYS_INCLUDE_KEYS:
        abs_path = paths.get(key)
        if not abs_path:
            continue
        rel_path = normalize_rel_path(project_root, abs_path)
        add_candidate_entry(
            candidates_map,
            rel_path,
            abs_path,
            selected=True,
            locked=True,
            reason="always_include",
            priority=100,
        )

    # README du projet s'il existe
    readme_abs = paths["readme_file"]
    if os.path.isfile(readme_abs):
        readme_rel = normalize_rel_path(project_root, readme_abs)
        add_candidate_entry(
            candidates_map,
            readme_rel,
            readme_abs,
            selected=True,
            locked=False,
            reason="always_include",
            priority=95,
        )

    # fichiers liés aux blocs
    for block in blocks:
        block_id = block.get("id", "")
        block_name = block.get("name", "")
        for item in block.get("items", []) or []:
            item_type = item.get("type")
            item_path = item.get("path", "")
            if item_type != "file" or not item_path:
                continue

            rel_path = normalize_rel_path(project_root, item_path)
            abs_path = safe_rel_to_abs(project_root, rel_path)

            add_candidate_entry(
                candidates_map,
                rel_path,
                abs_path,
                selected=False,
                locked=False,
                reason="block_linked",
                block_id=block_id,
                block_name=block_name,
                priority=70,
            )

    # fichiers liés aux dépendances (via les blocs source/cible)
    for dep in dependencies:
        from_id = dep.get("from_block_id")
        to_id = dep.get("to_block_id")
        if not from_id or not to_id:
            continue

        dep_label = f"{from_id} -> {to_id}"

        from_block = blocks_by_id.get(from_id)
        to_block = blocks_by_id.get(to_id)

        for block in [from_block, to_block]:
            if not block:
                continue
            block_id = block.get("id", "")
            block_name = block.get("name", "")
            for item in block.get("items", []) or []:
                item_type = item.get("type")
                item_path = item.get("path", "")
                if item_type != "file" or not item_path:
                    continue

                rel_path = normalize_rel_path(project_root, item_path)
                abs_path = safe_rel_to_abs(project_root, rel_path)

                add_candidate_entry(
                    candidates_map,
                    rel_path,
                    abs_path,
                    selected=False,
                    locked=False,
                    reason="dependency_linked",
                    block_id=block_id,
                    block_name=block_name,
                    dependency_pair=dep_label,
                    priority=65,
                )

    # réinjecter sélection sauvegardée
    for rel_path, entry in candidates_map.items():
        saved_item = saved_items_by_path.get(rel_path)
        if entry["locked"]:
            entry["selected"] = True
        elif saved_item is not None:
            entry["selected"] = bool(saved_item.get("selected", False))
        elif rel_path in saved_selected_paths:
            entry["selected"] = True

    items = list(candidates_map.values())
    items.sort(key=lambda x: (-x["priority"], x["path"]))

    selected_count = len([x for x in items if x.get("selected")])
    always_include_count = len([x for x in items if "always_include" in x.get("reasons", [])])
    block_linked_count = len([x for x in items if "block_linked" in x.get("reasons", [])])
    dependency_linked_count = len([x for x in items if "dependency_linked" in x.get("reasons", [])])

    return {
        "generated_at": now_utc_iso(),
        "project_root": project_root,
        "index_selection_json": paths["index_selection_json"],
        "index_selection_txt": paths["index_selection_txt"],
        "summary": {
            "total_candidates": len(items),
            "selected_count": selected_count,
            "always_include_count": always_include_count,
            "block_linked_count": block_linked_count,
            "dependency_linked_count": dependency_linked_count,
        },
        "items": items,
    }


class PromptHelperHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONT_DIR, **kwargs)

    def send_json(self, status_code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        if not raw_body:
            return {}
        return json.loads(raw_body.decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/project-config":
            self.handle_get_project_config()
            return

        if path == "/api/tree":
            self.handle_get_tree()
            return

        if path == "/api/blocks":
            self.handle_get_blocks()
            return

        if path == "/api/dependencies":
            self.handle_get_dependencies()
            return

        if path == "/api/index-selection/candidates":
            self.handle_get_index_selection_candidates()
            return

        if path == "/api/index-selection":
            self.handle_get_saved_index_selection()
            return

        if path == "/":
            self.path = "/index.html"
            return super().do_GET()

        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/project-config":
            self.handle_set_project_config()
            return

        if path == "/api/save-blocks":
            self.handle_save_blocks()
            return

        if path == "/api/save-dependencies":
            self.handle_save_dependencies()
            return

        if path == "/api/save-index-selection":
            self.handle_save_index_selection()
            return

        self.send_json(404, {"ok": False, "error": "Route inconnue"})

    def handle_get_project_config(self):
        try:
            project_root = load_project_root()
            self.send_json(200, {"ok": True, "project_root": project_root})
        except Exception as e:
            self.send_json(500, {"ok": False, "error": str(e)})

    def handle_set_project_config(self):
        try:
            payload = self._read_json_body()
            project_root = payload.get("project_root", "").strip()

            if not project_root:
                self.send_json(400, {"ok": False, "error": "project_root vide"})
                return

            if not os.path.isdir(project_root):
                self.send_json(400, {"ok": False, "error": f"Dossier introuvable : {project_root}"})
                return

            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"project_root": project_root}, f, ensure_ascii=False, indent=2)

            self.send_json(200, {"ok": True, "project_root": project_root})
        except Exception as e:
            self.send_json(500, {"ok": False, "error": str(e)})

    def handle_get_tree(self):
        try:
            paths = get_project_paths()
            tree_file = paths["tree_file"]

            if not os.path.exists(tree_file):
                self.send_json(404, {"ok": False, "error": f"arborescence.txt introuvable dans {paths['project_root']}"})
                return

            with open(tree_file, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            self.send_json(
                200,
                {
                    "ok": True,
                    "tree_text": content,
                    "tree_file": tree_file,
                    "project_root": paths["project_root"],
                },
            )
        except Exception as e:
            self.send_json(500, {"ok": False, "error": str(e)})

    def handle_get_blocks(self):
        try:
            paths = get_project_paths()
            blocks_json = paths["blocks_json"]

            if not os.path.exists(blocks_json):
                payload = default_blocks_payload()
                self.send_json(
                    200,
                    {
                        "ok": True,
                        "exists": False,
                        "data": payload,
                        "blocks_file": blocks_json,
                        "project_root": paths["project_root"],
                    },
                )
                return

            with open(blocks_json, "r", encoding="utf-8") as f:
                content = json.load(f)

            self.send_json(
                200,
                {
                    "ok": True,
                    "exists": True,
                    "data": content,
                    "blocks_file": blocks_json,
                    "project_root": paths["project_root"],
                },
            )
        except Exception as e:
            self.send_json(500, {"ok": False, "error": str(e)})

    def handle_get_dependencies(self):
        try:
            paths = get_project_paths()
            deps_json = paths["deps_json"]

            if not os.path.exists(deps_json):
                payload = default_dependencies_payload()
                self.send_json(
                    200,
                    {
                        "ok": True,
                        "exists": False,
                        "data": payload,
                        "dependencies_file": deps_json,
                        "project_root": paths["project_root"],
                    },
                )
                return

            with open(deps_json, "r", encoding="utf-8") as f:
                content = json.load(f)

            self.send_json(
                200,
                {
                    "ok": True,
                    "exists": True,
                    "data": content,
                    "dependencies_file": deps_json,
                    "project_root": paths["project_root"],
                },
            )
        except Exception as e:
            self.send_json(500, {"ok": False, "error": str(e)})

    def handle_get_index_selection_candidates(self):
        try:
            paths = get_project_paths()
            payload = build_index_candidates(paths)
            self.send_json(200, {"ok": True, "data": payload})
        except Exception as e:
            self.send_json(500, {"ok": False, "error": str(e)})

    def handle_get_saved_index_selection(self):
        try:
            paths = get_project_paths()
            payload = load_saved_index_selection(paths)
            self.send_json(
                200,
                {
                    "ok": True,
                    "data": payload,
                    "json_file": paths["index_selection_json"],
                    "txt_file": paths["index_selection_txt"],
                },
            )
        except Exception as e:
            self.send_json(500, {"ok": False, "error": str(e)})

    def handle_save_blocks(self):
        try:
            payload = self._read_json_body()
            paths = get_project_paths()

            payload["saved_at"] = now_utc_iso()

            with open(paths["blocks_json"], "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            with open(paths["blocks_txt"], "w", encoding="utf-8") as f:
                f.write(build_blocks_text_summary(payload))

            self.send_json(
                200,
                {
                    "ok": True,
                    "message": "Blocs enregistrés sur le serveur",
                    "json_file": paths["blocks_json"],
                    "txt_file": paths["blocks_txt"],
                    "project_root": paths["project_root"],
                },
            )
        except Exception as e:
            self.send_json(500, {"ok": False, "error": str(e)})

    def handle_save_dependencies(self):
        try:
            payload = self._read_json_body()
            paths = get_project_paths()

            payload["saved_at"] = now_utc_iso()

            with open(paths["deps_json"], "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            with open(paths["deps_txt"], "w", encoding="utf-8") as f:
                f.write(build_dependencies_text_summary(payload))

            self.send_json(
                200,
                {
                    "ok": True,
                    "message": "Dépendances enregistrées sur le serveur",
                    "json_file": paths["deps_json"],
                    "txt_file": paths["deps_txt"],
                    "project_root": paths["project_root"],
                },
            )
        except Exception as e:
            self.send_json(500, {"ok": False, "error": str(e)})

    def handle_save_index_selection(self):
        try:
            request_payload = self._read_json_body()
            paths = get_project_paths()
            candidates_payload = build_index_candidates(paths)

            requested_paths = set(request_payload.get("selected_paths", []))
            candidate_items = candidates_payload.get("items", [])

            final_items = []
            final_selected_paths = []

            for item in candidate_items:
                entry = dict(item)
                path = entry["path"]

                if entry.get("locked"):
                    entry["selected"] = True
                else:
                    entry["selected"] = path in requested_paths

                if entry["selected"]:
                    final_selected_paths.append(path)

                final_items.append(entry)

            saved_payload = {
                "generated_at": candidates_payload.get("generated_at"),
                "saved_at": now_utc_iso(),
                "project_root": paths["project_root"],
                "selected_paths": sorted(final_selected_paths),
                "items": final_items,
            }

            with open(paths["index_selection_json"], "w", encoding="utf-8") as f:
                json.dump(saved_payload, f, ensure_ascii=False, indent=2)

            with open(paths["index_selection_txt"], "w", encoding="utf-8") as f:
                f.write(build_index_selection_txt(saved_payload))

            self.send_json(
                200,
                {
                    "ok": True,
                    "message": "Sélection d'index enregistrée sur le serveur",
                    "json_file": paths["index_selection_json"],
                    "txt_file": paths["index_selection_txt"],
                    "selected_count": len(final_selected_paths),
                    "project_root": paths["project_root"],
                },
            )
        except Exception as e:
            self.send_json(500, {"ok": False, "error": str(e)})


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), PromptHelperHandler)
    print(f"Serveur lancé sur http://{HOST}:{PORT}")
    print(f"App : {APP_DIR}")
    print(f"Front servi depuis : {FRONT_DIR}")

    try:
        paths = get_project_paths()
        print(f"Projet cible : {paths['project_root']}")
        print(f"Arborescence lue depuis : {paths['tree_file']}")
        print(f"Blocs JSON : {paths['blocks_json']}")
        print(f"Dépendances JSON : {paths['deps_json']}")
        print(f"Sélection index JSON : {paths['index_selection_json']}")
        print(f"Sélection index TXT : {paths['index_selection_txt']}")
    except Exception as e:
        print(f"[WARN] Impossible de charger la config projet : {e}")

    server.serve_forever()