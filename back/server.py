#!/usr/bin/env python3
import json
import os
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONT_DIR = os.path.join(PROJECT_DIR, "front")

TREE_FILE = os.path.join(PROJECT_DIR, "arborescence.txt")

BLOCKS_JSON = os.path.join(PROJECT_DIR, "blocks_summary.json")
BLOCKS_TXT = os.path.join(PROJECT_DIR, "blocks_summary.txt")

DEPS_JSON = os.path.join(PROJECT_DIR, "block_dependencies.json")
DEPS_TXT = os.path.join(PROJECT_DIR, "block_dependencies.txt")

HOST = "127.0.0.1"
PORT = 8010


def now_utc_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


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

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

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

        if path == "/api/save-blocks":
            self.handle_save_blocks()
            return

        if path == "/api/save-dependencies":
            self.handle_save_dependencies()
            return

        self.send_json(404, {"ok": False, "error": "Route inconnue"})

    def handle_get_tree(self):
        try:
            if not os.path.exists(TREE_FILE):
                self.send_json(404, {"ok": False, "error": "arborescence.txt introuvable"})
                return

            with open(TREE_FILE, "r", encoding="utf-8") as f:
                content = f.read()

            self.send_json(
                200,
                {
                    "ok": True,
                    "tree_text": content,
                    "tree_file": TREE_FILE,
                },
            )
        except Exception as e:
            self.send_json(500, {"ok": False, "error": str(e)})

    def handle_get_blocks(self):
        try:
            if not os.path.exists(BLOCKS_JSON):
                payload = default_blocks_payload()
                self.send_json(
                    200,
                    {
                        "ok": True,
                        "exists": False,
                        "data": payload,
                        "blocks_file": BLOCKS_JSON,
                    },
                )
                return

            with open(BLOCKS_JSON, "r", encoding="utf-8") as f:
                content = json.load(f)

            self.send_json(
                200,
                {
                    "ok": True,
                    "exists": True,
                    "data": content,
                    "blocks_file": BLOCKS_JSON,
                },
            )
        except Exception as e:
            self.send_json(500, {"ok": False, "error": str(e)})

    def handle_get_dependencies(self):
        try:
            if not os.path.exists(DEPS_JSON):
                payload = default_dependencies_payload()
                self.send_json(
                    200,
                    {
                        "ok": True,
                        "exists": False,
                        "data": payload,
                        "dependencies_file": DEPS_JSON,
                    },
                )
                return

            with open(DEPS_JSON, "r", encoding="utf-8") as f:
                content = json.load(f)

            self.send_json(
                200,
                {
                    "ok": True,
                    "exists": True,
                    "data": content,
                    "dependencies_file": DEPS_JSON,
                },
            )
        except Exception as e:
            self.send_json(500, {"ok": False, "error": str(e)})

    def handle_save_blocks(self):
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            payload = json.loads(raw_body.decode("utf-8"))

            payload["saved_at"] = now_utc_iso()

            with open(BLOCKS_JSON, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            with open(BLOCKS_TXT, "w", encoding="utf-8") as f:
                f.write(build_blocks_text_summary(payload))

            self.send_json(
                200,
                {
                    "ok": True,
                    "message": "Blocs enregistrés sur le serveur",
                    "json_file": BLOCKS_JSON,
                    "txt_file": BLOCKS_TXT,
                },
            )
        except Exception as e:
            self.send_json(500, {"ok": False, "error": str(e)})

    def handle_save_dependencies(self):
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            payload = json.loads(raw_body.decode("utf-8"))

            payload["saved_at"] = now_utc_iso()

            with open(DEPS_JSON, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            with open(DEPS_TXT, "w", encoding="utf-8") as f:
                f.write(build_dependencies_text_summary(payload))

            self.send_json(
                200,
                {
                    "ok": True,
                    "message": "Dépendances enregistrées sur le serveur",
                    "json_file": DEPS_JSON,
                    "txt_file": DEPS_TXT,
                },
            )
        except Exception as e:
            self.send_json(500, {"ok": False, "error": str(e)})


if __name__ == "__main__":
    os.chdir(PROJECT_DIR)
    server = ThreadingHTTPServer((HOST, PORT), PromptHelperHandler)
    print(f"Serveur lancé sur http://{HOST}:{PORT}")
    print(f"Projet : {PROJECT_DIR}")
    print(f"Front servi depuis : {FRONT_DIR}")
    print(f"Arborescence lue depuis : {TREE_FILE}")
    print(f"Blocs JSON : {BLOCKS_JSON}")
    print(f"Dépendances JSON : {DEPS_JSON}")
    server.serve_forever()