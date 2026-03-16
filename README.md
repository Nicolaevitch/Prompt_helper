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

## Installation

```bash
git clone https://github.com/Nicolaevitch/Prompt_helper.git
cd Prompt_helper

python3 -m venv venv 
source venv/bin/activate

pip install -r requirements.txt

sudo apt update 

sudo apt install tree –y
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3.5:35b-a3b

 

## Changement config :  

{ 

  "project_root": "/data/mdejurquet/mon_projet" 

} 

 

sudo chown -R mdejurquet:mdejurquet /data/mdejurquet/mon_projet 

Si le projet n'a pas de documentation (summary, dependancies, arborescences..) initialisé avec :
python3 scripts/init_target_project.py 

## Lancement server: 
python3 back/server.py  

 
## SSH  

En local :  
ssh -N -L 9010:127.0.0.1:8010 mdejurquet@ma-machine 

Page :  

http://127.0.0.1:9010/

##  créer/relancer les fichiers d'informaiton pour le rag 

python rag/build_index.py


##  lancer le chat :  

python rag/query.py 
python rag/ask.py 
