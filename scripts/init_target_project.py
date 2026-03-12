import json
import shutil
import subprocess
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = APP_ROOT / "config" / "project_config.json"
TEMPLATES_DIR = APP_ROOT / "templates"


def load_project_root() -> Path:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    project_root = config.get("project_root", "").strip()
    if not project_root:
        raise ValueError("project_root est vide dans config/project_config.json")

    path = Path(project_root)
    if not path.exists():
        raise FileNotFoundError(f"Le dossier projet n'existe pas : {path}")

    if not path.is_dir():
        raise NotADirectoryError(f"Le chemin n'est pas un dossier : {path}")

    return path


def ensure_file_from_template(project_root: Path, filename: str):
    target = project_root / filename
    template = TEMPLATES_DIR / filename

    if not target.exists():
        shutil.copyfile(template, target)
        print(f"[OK] Créé : {target}")
    else:
        print(f"[SKIP] Existe déjà : {target}")


def generate_tree_file(project_root: Path):
    tree_file = project_root / "arborescence.txt"

    cmd = [
        "tree",
        "-L", "4",
        "-I", "venv|__pycache__|.git|node_modules",
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=True
        )
        tree_file.write_text(result.stdout, encoding="utf-8")
        print(f"[OK] Généré : {tree_file}")
    except FileNotFoundError:
        print("[ERROR] La commande 'tree' n'est pas installée sur cette machine.")
    except subprocess.CalledProcessError as e:
        print("[ERROR] Impossible de générer arborescence.txt")
        print(e.stderr)


def main():
    project_root = load_project_root()
    print(f"Projet cible : {project_root}")

    ensure_file_from_template(project_root, "project_summary.md")
    ensure_file_from_template(project_root, "blocks_summary.json")
    ensure_file_from_template(project_root, "block_dependencies.json")

    generate_tree_file(project_root)

    print("\nInitialisation terminée.")


if __name__ == "__main__":
    main()
