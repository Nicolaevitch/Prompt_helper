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
    except Exception as e:
        print(f"[WARN] Impossible de charger la config projet : {e}")

    server.serve_forever()