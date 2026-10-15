# Nova

Nova est une application Windows qui mesure le temps passé sur vos jeux, sans avoir à les lancer depuis elle. Elle tourne discrètement dans la zone de notifications et présente votre bibliothèque dans une interface inspirée de Steam.

> Projet en cours de développement.

## Développement

Prérequis : Windows 10 ou 11 et Python 3.14.

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m nova
```
