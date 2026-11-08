from collections.abc import Iterator

import logging
import secrets

from sqlalchemy import Integer, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker, with_loader_criteria

from app.config import config

config.data_dir.mkdir(parents=True, exist_ok=True)

engine = create_engine(config.database_url, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


log = logging.getLogger(__name__)


class UserScoped:
    """Donnée personnelle d'un compte (watchlist, notes, historique, notifications, demandes).

    Toute requête ORM d'une session liée à un utilisateur (session.info["user_id"]) est filtrée
    automatiquement sur cet utilisateur, et les nouvelles lignes lui sont attribuées.
    Pour lire les données de tous les comptes (admin, tâches globales) :
    .execution_options(all_users=True).
    """

    # DEFAULT 1 : à la migration, les données existantes reviennent au premier compte (l'administrateur)
    user_id: Mapped[int] = mapped_column(Integer, index=True, default=1)


def bind_user(db: Session, user_id: int | None) -> Session:
    db.info["user_id"] = user_id
    return db


@event.listens_for(Session, "do_orm_execute")
def _scope_to_user(state):
    uid = state.session.info.get("user_id")
    if uid is None or state.execution_options.get("all_users"):
        return
    if (state.is_select and not state.is_column_load and not state.is_relationship_load) or state.is_update or state.is_delete:
        state.statement = state.statement.options(
            with_loader_criteria(UserScoped, lambda cls: cls.user_id == uid, include_aliases=True)
        )


@event.listens_for(Session, "before_flush")
def _assign_user(session, _ctx, _instances):
    uid = session.info.get("user_id")
    for obj in session.new:
        if isinstance(obj, UserScoped) and obj.user_id is None:
            if uid is None:
                raise RuntimeError(f"{type(obj).__name__} créé hors d'une session utilisateur")
            obj.user_id = uid


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_missing_columns() -> None:
    """Migration légère : ajoute les colonnes apparues dans les modèles depuis la création de la base.

    create_all() ne modifie jamais une table existante ; sans ceci, une mise à jour
    de CinéSync casserait une base déjà en place.
    """
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                ddl = f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" {col.type.compile(dialect=engine.dialect)}'
                if col.default is not None and getattr(col.default, "is_scalar", False):
                    v = col.default.arg
                    literal = str(int(v)) if isinstance(v, bool) else ("'" + v.replace("'", "''") + "'" if isinstance(v, str) else str(v))
                    ddl += f" DEFAULT {literal}"
                conn.execute(text(ddl))


# Tables dont la contrainte d'unicité inclut désormais l'utilisateur : SQLite ne sait pas
# modifier une contrainte, la table est reconstruite (données existantes -> compte n°1).
_REBUILD_FOR_USERS = ("media_state", "swipe_history", "watch_events")


def _rebuild_for_users() -> None:
    """À lancer après _add_missing_columns() : l'ancienne table a alors toutes les colonnes (dont user_id = 1)."""
    insp = inspect(engine)
    for name in _REBUILD_FOR_USERS:
        if not insp.has_table(name):
            continue
        uniques = insp.get_unique_constraints(name)
        if not uniques or all("user_id" in u["column_names"] for u in uniques):
            continue
        old_cols = [c["name"] for c in insp.get_columns(name)]
        table = Base.metadata.tables[name]
        cols = [c for c in old_cols if c in table.c]
        common = ", ".join(f'"{c}"' for c in cols)
        # Colonnes à valeur par défaut serveur (dates) : une colonne ajoutée après coup peut être vide
        values = ", ".join(
            f'COALESCE("{c}", CURRENT_TIMESTAMP)' if table.c[c].server_default is not None else f'"{c}"' for c in cols
        )
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE "{name}" RENAME TO "{name}__old"'))
            for (idx,) in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=:t AND sql IS NOT NULL"), {"t": f"{name}__old"}
            ).all():
                conn.execute(text(f'DROP INDEX "{idx}"'))
            table.create(conn)
            conn.execute(text(f'INSERT INTO "{name}" ({common}) SELECT {values} FROM "{name}__old"'))
            conn.execute(text(f'DROP TABLE "{name}__old"'))
        log.info("Migration multi-comptes : table %s reconstruite", name)


# Code d'installation (création du compte administrateur), affiché dans les journaux du conteneur
setup_code: str | None = None


def init_db() -> None:
    """Crée les tables, migre une base existante et garantit un compte administrateur."""
    from app import models  # noqa: F401  (enregistre les modèles)
    from app.models import User, UserSettings

    global setup_code
    insp = inspect(engine)
    legacy_events = insp.has_table("watch_events") and "user_id" not in {c["name"] for c in insp.get_columns("watch_events")}
    Base.metadata.create_all(engine)
    _add_missing_columns()
    _rebuild_for_users()
    if legacy_events:
        # Historique Plex d'avant les comptes : seuls les visionnages du propriétaire (accountID 1) sont à l'admin ;
        # ceux des autres comptes Plex attendent que l'admin les autorise (user_id 0)
        with engine.begin() as conn:
            conn.execute(text("UPDATE watch_events SET user_id = 0 WHERE source = 'plex' AND plex_account_id IS NOT NULL AND plex_account_id != 1"))
    with SessionLocal() as db:
        if db.get(User, 1) is None and db.query(User).count() == 0:
            # Premier démarrage (ou base mono-utilisateur d'avant les comptes) : l'admin reprend le n°1
            db.add(User(id=1, username="admin", role="admin"))
        if db.get(UserSettings, 1) is None:
            db.add(UserSettings(id=1))
        db.commit()
        for u in db.query(User).all():
            if db.get(UserSettings, u.id) is None:
                db.add(UserSettings(id=u.id))
        db.commit()
        if setup_required(db):
            setup_code = "-".join(secrets.token_hex(2).upper() for _ in range(3))
            log.warning("Installation de CinéSync : code pour créer le compte administrateur -> %s", setup_code)


def setup_required(db: Session) -> bool:
    """Aucun administrateur ne peut encore se connecter (ni mot de passe, ni compte Plex)."""
    from app.config import config
    from app.models import User

    if config.cinesync_mode == "personal":
        return False
    admins = db.query(User).filter(User.role == "admin", User.active.is_(True)).all()
    return not any(a.password_hash or a.plex_user_id for a in admins)
