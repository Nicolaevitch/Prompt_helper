import json
from pathlib import Path
import ollama
from query import search

APP_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = APP_ROOT / "config" / "project_config.json"

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

PROJECT_ROOT = Path(config["project_root"]).resolve()

MODEL = "qwen3.5:35b-a3b"


def build_context(results, max_docs=6):
    context_parts = []

    for score, doc in results[:max_docs]:
        text = doc["text"]

        block = f"""
Document type : {doc['doc_type']}
Score retrieval : {score:.3f}
Contenu :
{text}
""".strip()

        context_parts.append(block)

    return "\n\n".join(context_parts)


def build_prompt(question: str, context: str) -> str:
    return f"""
Tu es un expert en architecture logicielle, en analyse de code et en structuration de projet.

Tu analyses un projet logiciel à partir d'un contexte RAG.

Le projet est structuré en blocs logiques.

Définition des blocs :
- Un bloc représente une unité de compréhension du projet.
- Un bloc peut correspondre à un fichier, un dossier, ou un regroupement logique de plusieurs éléments.
- Chaque bloc peut contenir :
  - un nom
  - un contexte explicatif
  - des fichiers ou dossiers liés
  - des relations hiérarchiques parent/enfant
  - des dépendances fonctionnelles amont/aval

Interprétation des relations :
- parent/enfant = relation de hiérarchie, de composition ou d'inclusion logique
- dépendance amont/aval = relation fonctionnelle ou chronologique
- une dépendance ne signifie pas qu'un bloc est contenu dans un autre
- une hiérarchie ne signifie pas forcément qu'il existe une dépendance fonctionnelle

Interprétation du contexte :
- Le champ "Contexte" d'un bloc décrit son rôle, sa finalité, et éventuellement ses entrées/sorties.
- Quand il est présent, il doit être utilisé comme source prioritaire pour expliquer à quoi sert un bloc.
- Quand il est absent, appuie-toi sur les fichiers liés et les extraits de code fournis.

Consignes de réponse :
- Réponds uniquement à partir des informations présentes dans le contexte.
- Si une information manque, dis-le explicitement.
- N'invente pas de fichiers, de blocs, de dépendances ou de comportements.
- Si la question porte sur l'architecture, privilégie :
  1. le résumé global du projet
  2. les blocs structurants
  3. les relations entre blocs
- Si la question porte sur un fichier ou un script :
  1. identifie le bloc correspondant
  2. utilise le contexte du bloc
  3. utilise ensuite les extraits de code liés
- Si la question porte sur les dépendances :
  1. distingue clairement hiérarchie et dépendance
  2. explique les blocs amont et aval
  3. n'assimile jamais une dépendance à une inclusion
- Sois clair, structuré, précis et concis.
- Réponds en français.

Projet analysé :
{PROJECT_ROOT}

Question :
{question}

Contexte :
{context}

Réponse claire et structurée :
""".strip()


def ask_llm(question, context):
    prompt = build_prompt(question, context)

    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}]
    )

    return response["message"]["content"]


def main():
    print("\nRAG + LLM prêt.\n")
    print(f"Projet cible : {PROJECT_ROOT}")
    print(f"Modèle LLM   : {MODEL}\n")

    while True:
        question = input("> ")

        if question.strip().lower() in {"exit", "quit"}:
            break

        results, debug = search(question)

        print("\nAnalyse requête :")
        print("project_root       :", debug.get("project_root"))
        print("docs_file          :", debug.get("docs_file"))
        print("emb_file           :", debug.get("emb_file"))
        print("intent             :", debug.get("intent"))
        print("file_terms         :", debug.get("file_terms"))
        print("matched_file_paths :", debug.get("matched_file_paths"))
        print("seed_blocks        :", debug.get("seed_blocks"))

        context = build_context(results)
        answer = ask_llm(question, context)

        print("\nRéponse :\n")
        print(answer)
        print("\n")


if __name__ == "__main__":
    main()