#!/bin/sh
# Démarre CinéSync sans les droits root : le dossier de données appartient à PUID:PGID
# (99:100 = nobody:users, l'usage sur Unraid), puis le serveur tourne sous cet utilisateur.
# La base contient les jetons des services : elle n'est lisible que par ce propriétaire.
set -e
DATA_DIR="${DATA_DIR:-/app/data}"
umask 077
mkdir -p "$DATA_DIR"
if [ "$(id -u)" = "0" ]; then
    chown -R "${PUID}:${PGID}" "$DATA_DIR"
    chmod 700 "$DATA_DIR"
    find "$DATA_DIR" -type f -exec chmod 600 {} +
    exec setpriv --reuid="${PUID}" --regid="${PGID}" --clear-groups "$@"
fi
exec "$@"
