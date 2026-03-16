# Prompt Helper

Prompt Helper est un outil d'analyse de projet logiciel.

Il permet de :
- visualiser l'arborescence d'un projet
- créer des blocs logiques
- définir des dépendances entre blocs
- construire un index RAG
- interroger un projet avec un LLM

## Structure

- `back/` : backend HTTP
- `front/` : interface web
- `rag/` : moteur RAG
- `config/project_config.json` : projet cible analysé
- `templates/` : fichiers par défaut
- `scripts/init_target_project.py` : initialise un projet cible
- `scripts/run_prompt_helper.sh` : initialise et lance le serveur