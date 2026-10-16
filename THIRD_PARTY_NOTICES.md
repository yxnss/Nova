# Composants tiers

Nova (licence MIT, voir `LICENSE`) s'appuie sur les composants suivants, distribués
avec `Nova.exe` sous leurs propres licences.

| Composant | Rôle dans Nova | Licence |
|---|---|---|
| [Qt 6](https://www.qt.io/) et [PySide6 / Shiboken6](https://doc.qt.io/qtforpython-6/) | Interface graphique | [LGPL v3](https://www.gnu.org/licenses/lgpl-3.0.html) |
| [psutil](https://github.com/giampaolo/psutil) | Détection des processus | [BSD 3-Clause](https://github.com/giampaolo/psutil/blob/master/LICENSE) |
| [Python](https://www.python.org/) et [SQLite](https://www.sqlite.org/) | Langage et base de données | [PSF License](https://docs.python.org/3/license.html), domaine public |

## Qt et la licence LGPL v3

Qt est utilisé sans modification, sous forme de bibliothèques dynamiques (fichiers
`.dll` du dossier `_internal\PySide6`). Conformément à la LGPL v3, vous pouvez les
remplacer par une autre version compatible de Qt. Le code source de Qt et de PySide6
est disponible sur [code.qt.io](https://code.qt.io/).
