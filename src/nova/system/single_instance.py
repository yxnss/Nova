"""Instance unique : relancer Nova réveille la fenêtre existante au lieu d'en ouvrir une autre.

Deux mécanismes de Qt :
- un **verrou de fichier** (``QLockFile``) : seule la première instance l'obtient. Si
  Nova a planté, Qt voit que le processus propriétaire n'existe plus et libère le verrou ;
- un **canal local** (``QLocalServer``) : la nouvelle instance s'y connecte pour
  demander à la première de se montrer, puis se ferme.
"""

import getpass
import hashlib
import logging
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)

_WAKE_UP = b"show"


def channel_name(data_dir: Path) -> str:
    """Nom du canal, propre à l'utilisateur et au dossier de données.

    Deux comptes Windows, ou une copie de développement qui utilise un autre
    dossier, ont ainsi chacun leur propre Nova.
    """
    folder = hashlib.sha1(str(data_dir).casefold().encode("utf-8")).hexdigest()[:8]
    return f"Nova-{getpass.getuser()}-{folder}"


class SingleInstance(QObject):
    activation_requested = Signal()  # une autre instance demande à afficher la fenêtre

    def __init__(self, data_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._name = channel_name(data_dir)
        self._lock = QLockFile(str(data_dir / "nova.lock"))
        # Pas d'expiration à la durée : Nova tourne des jours. Seul un processus mort
        # rend le verrou périmé.
        self._lock.setStaleLockTime(0)
        self._server: QLocalServer | None = None

    def acquire(self) -> bool:
        """Vrai si cette instance est la seule : elle écoute alors les demandes des suivantes."""
        if not self._lock.tryLock(100):
            return False
        QLocalServer.removeServer(self._name)  # canal laissé par une instance plantée
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        if not self._server.listen(self._name):
            log.warning("Canal d'instance unique indisponible : %s", self._server.errorString())
        return True

    def wake_up_running_instance(self) -> bool:
        """Demande à l'instance déjà lancée d'afficher sa fenêtre."""
        socket = QLocalSocket()
        socket.connectToServer(self._name)
        if not socket.waitForConnected(1000):
            return False
        socket.write(_WAKE_UP)
        socket.flush()
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()
        return True

    def release(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
        self._lock.unlock()

    def _on_new_connection(self) -> None:
        while self._server is not None and self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            # La nouvelle instance écrit son message puis se déconnecte aussitôt. On
            # attend donc le message ici même (rare et très court) : avec un simple
            # signal, la connexion pouvait être détruite avant d'avoir été lue.
            if not socket.bytesAvailable():
                socket.waitForReadyRead(500)
            message = bytes(socket.readAll())
            socket.disconnectFromServer()
            socket.deleteLater()
            if message.startswith(_WAKE_UP):
                self.activation_requested.emit()
