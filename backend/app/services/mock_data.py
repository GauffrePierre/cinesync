"""Données factices utilisées tant qu'un service n'est pas configuré.

Les ids sont de vrais ids TMDB, pour que tout reste cohérent une fois la clé saisie.
Pas d'images : le frontend affiche un visuel de remplacement.
"""

from datetime import date, timedelta

_MOVIES = [
    (693134, "Dune : Deuxième partie", "Dune: Part Two", "2024-02-27", 8.1, [878, 12], "Paul Atréides s'unit aux Fremen pour se venger des conspirateurs qui ont détruit sa famille."),
    (872585, "Oppenheimer", "Oppenheimer", "2023-07-19", 8.1, [18, 36], "L'histoire du physicien J. Robert Oppenheimer et du projet Manhattan."),
    (496243, "Parasite", "기생충", "2019-05-30", 8.5, [35, 53, 18], "Une famille pauvre s'infiltre peu à peu dans le quotidien d'une famille aisée."),
    (129, "Le Voyage de Chihiro", "千と千尋の神隠し", "2001-07-20", 8.5, [16, 10751, 14], "Chihiro, dix ans, se retrouve piégée dans un monde peuplé d'esprits."),
    (194, "Le Fabuleux Destin d'Amélie Poulain", "Le Fabuleux Destin d'Amélie Poulain", "2001-04-25", 7.9, [35, 10749], "Amélie décide de changer la vie des gens qui l'entourent."),
    (27205, "Inception", "Inception", "2010-07-15", 8.4, [28, 878, 12], "Un voleur qui s'infiltre dans les rêves se voit confier une mission impossible : implanter une idée."),
    (335984, "Blade Runner 2049", "Blade Runner 2049", "2017-10-04", 7.6, [878, 18], "Un blade runner découvre un secret enfoui depuis longtemps."),
    (545611, "Everything Everywhere All at Once", "Everything Everywhere All at Once", "2022-03-24", 7.8, [28, 12, 878], "Une blanchisseuse découvre qu'elle peut accéder aux vies de ses versions parallèles."),
    (466420, "Killers of the Flower Moon", "Killers of the Flower Moon", "2023-10-18", 7.5, [80, 18, 36], "Des meurtres en série frappent la nation Osage dans les années 1920."),
    (915935, "Anatomie d'une chute", "Anatomie d'une chute", "2023-08-23", 7.7, [53, 9648], "Une écrivaine est soupçonnée du meurtre de son mari."),
]

_SHOWS = [
    (1396, "Breaking Bad", "Breaking Bad", "2008-01-20", 8.9, [18, 80], "Un professeur de chimie atteint d'un cancer se lance dans la fabrication de méthamphétamine."),
    (95396, "Severance", "Severance", "2022-02-17", 8.4, [18, 9648, 10765], "Des employés dont les souvenirs professionnels et personnels ont été séparés chirurgicalement."),
    (136315, "The Bear", "The Bear", "2022-06-23", 8.1, [18, 35], "Un jeune chef reprend la sandwicherie familiale à Chicago."),
    (100088, "The Last of Us", "The Last of Us", "2023-01-15", 8.6, [18, 10759], "Joel escorte Ellie à travers une Amérique post-apocalyptique."),
    (87108, "Chernobyl", "Chernobyl", "2019-05-06", 8.7, [18, 36], "La catastrophe nucléaire de 1986 et ceux qui se sont sacrifiés."),
    (76479, "The Boys", "The Boys", "2019-07-25", 8.5, [10765, 10759], "Des justiciers s'attaquent à des super-héros corrompus."),
    (94997, "House of the Dragon", "House of the Dragon", "2022-08-21", 8.4, [10765, 18], "La maison Targaryen, deux siècles avant Game of Thrones."),
    (60574, "Peaky Blinders", "Peaky Blinders", "2013-09-12", 8.5, [18, 80], "Un gang de Birmingham au lendemain de la Première Guerre mondiale."),
]

_PROVIDERS = [
    {"id": 8, "name": "Netflix", "logo": None},
    {"id": 337, "name": "Disney Plus", "logo": None},
    {"id": 119, "name": "Amazon Prime Video", "logo": None},
    {"id": 350, "name": "Apple TV+", "logo": None},
    {"id": 381, "name": "Canal+", "logo": None},
    {"id": 1899, "name": "Max", "logo": None},
    {"id": 531, "name": "Paramount Plus", "logo": None},
    {"id": 691, "name": "Play Suisse", "logo": None},
]

_GENRES = {
    28: "Action", 12: "Aventure", 16: "Animation", 35: "Comédie", 80: "Crime", 18: "Drame",
    10751: "Familial", 14: "Fantastique", 36: "Histoire", 9648: "Mystère", 10749: "Romance",
    878: "Science-Fiction", 53: "Thriller", 10759: "Action & Aventure", 10765: "Science-Fiction & Fantastique",
}


def _item(row, media_type: str, release: str | None = None) -> dict:
    tid, title, orig, d, vote, genres, overview = row
    d = release or d
    return {
        "id": tid,
        "media_type": media_type,
        "title": title,
        "original_title": orig,
        "overview": overview,
        "poster": None,
        "backdrop": None,
        "release_date": d,
        "year": int(d[:4]),
        "vote_average": vote,
        "vote_count": 10000 + tid % 9000,
        "genre_ids": genres,
        "providers": [],
        "in_plex": False,
        "mock": True,
    }


def mock_movies() -> list[dict]:
    return [_item(r, "movie") for r in _MOVIES]


def mock_shows() -> list[dict]:
    return [_item(r, "tv") for r in _SHOWS]


def mock_all() -> list[dict]:
    m, s = mock_movies(), mock_shows()
    out = []
    for i in range(max(len(m), len(s))):
        out += m[i : i + 1] + s[i : i + 1]
    return out


def _find(media_type: str, tmdb_id: int) -> dict:
    pool = mock_movies() if media_type == "movie" else mock_shows()
    return next((i for i in pool if i["id"] == tmdb_id), pool[0])


def _mock_providers(tmdb_id: int) -> list[dict]:
    n = tmdb_id % len(_PROVIDERS)
    picks = [_PROVIDERS[n]] + ([_PROVIDERS[(n + 3) % len(_PROVIDERS)]] if tmdb_id % 3 == 0 else [])
    return [{**p, "type": "flatrate", "priority": i} for i, p in enumerate(picks)]


class MockTMDB:
    is_mock = True
    country = "CH"

    async def trending(self, media_type="all", page=1):
        return {"all": mock_all, "movie": mock_movies, "tv": mock_shows}[media_type]() if page == 1 else []

    async def search_multi(self, query, page=1):
        q = query.lower()
        return [i for i in mock_all() if q in i["title"].lower() or q in (i["original_title"] or "").lower()]

    async def discover(self, media_type, page=1, **filters):
        return mock_movies() if media_type == "movie" else mock_shows()

    async def upcoming(self, media_type, page=1, days=120, kind="all"):
        if page > 1 or (media_type == "tv" and kind == "cinema"):
            return []
        pool = mock_movies() if media_type == "movie" else mock_shows()
        today = date.today()
        out = []
        for n, i in enumerate(pool):
            rk = "streaming" if media_type == "tv" else (kind if kind != "all" else ("cinema" if n % 2 else "streaming"))
            out.append({**i, "release_date": (today + timedelta(days=4 + 9 * n)).isoformat(), "release_kind": rk})
        return out

    async def now_playing(self, page=1):
        return mock_movies()[:4] if page == 1 else []

    async def on_the_air(self, page=1):
        return mock_shows() if page == 1 else []

    async def recommendations(self, media_type, tmdb_id, page=1):
        pool = mock_movies() if media_type == "movie" else mock_shows()
        return [i for i in pool if i["id"] != tmdb_id] if page == 1 else []

    similar = recommendations

    async def basic(self, media_type, tmdb_id):
        return _find(media_type, tmdb_id)

    async def detail(self, media_type, tmdb_id):
        base = _find(media_type, tmdb_id)
        detail = {
            **base,
            "poster_small": None,
            "tagline": "Données de démonstration — ajoute ta clé TMDB dans le Profil",
            "status": "Released" if media_type == "movie" else "Returning Series",
            "homepage": None,
            "imdb_id": None,
            "runtime": 128 if media_type == "movie" else 52,
            "countries": ["États-Unis"],
            "original_language": "Anglais",
            "spoken_languages": ["Anglais", "Français"],
            "genres": [_GENRES.get(g, "Autre") for g in base["genre_ids"]],
            "keywords": ["démo", "SynCiné"],
            "certification": "12",
            "cast": [{"id": n, "name": f"Acteur·rice {n}", "character": f"Personnage {n}", "photo": None} for n in range(1, 9)],
            "crew": {
                "directors": [{"id": 100, "name": "Réalisateur·rice", "job": "Director", "photo": None}],
                "writers": [{"id": 101, "name": "Scénariste", "job": "Screenplay", "photo": None}],
                "composers": [{"id": 102, "name": "Compositeur·rice", "job": "Original Music Composer", "photo": None}],
                "cinematographers": [],
                "producers": [],
                "creators": [],
            },
            "trailer": None,
            "videos": [],
            "recommendations": await self.recommendations(media_type, tmdb_id),
            "budget": None,
            "revenue": None,
            "collection": None,
        }
        if media_type == "tv":
            detail.update(
                {
                    "seasons": [
                        {"season_number": n, "name": f"Saison {n}", "episode_count": 8, "air_date": f"{2020 + n}-03-01", "poster": None, "overview": "", "vote_average": 8}
                        for n in (1, 2, 3)
                    ],
                    "number_of_seasons": 3,
                    "number_of_episodes": 24,
                    "in_production": True,
                    "first_air_date": base["release_date"],
                    "last_air_date": None,
                    "next_episode": None,
                    "last_episode": None,
                    "networks": [],
                    "type": "Scripted",
                }
            )
        return detail

    async def season(self, tv_id, season_number):
        return {
            "season_number": season_number,
            "name": f"Saison {season_number}",
            "overview": "",
            "episodes": [
                {"episode_number": n, "name": f"Épisode {n}", "overview": "", "air_date": None, "runtime": 50, "still": None, "vote_average": 8}
                for n in range(1, 9)
            ],
        }

    async def collection(self, collection_id):
        return {"id": collection_id, "name": "Collection démo", "overview": "", "parts": mock_movies()[:3]}

    async def providers(self, media_type, tmdb_id, fresh=False):
        return {"link": None, "flatrate": _mock_providers(tmdb_id), "free": [], "ads": [], "rent": [], "buy": []}

    async def provider_catalog(self, media_type="movie"):
        return [{**p, "priority": i} for i, p in enumerate(_PROVIDERS)]

    async def regions(self):
        return []

    async def genres(self, media_type):
        return _GENRES

    async def test(self):
        return {}


class MockPlex:
    is_mock = True

    def _items(self) -> list[dict]:
        rows = [(r, "movie") for r in _MOVIES[:6]] + [(r, "tv") for r in _SHOWS[:4]]
        out = []
        for n, (r, mt) in enumerate(rows):
            i = _item(r, mt)
            i.update(
                {
                    "rating_key": str(1000 + n),
                    "added_at": (date.today() - timedelta(days=n * 5)).isoformat(),
                    "section": "Films" if mt == "movie" else "Séries",
                    "plex_url": None,
                    "in_plex": True,
                    "view_count": n % 2,
                    "duration_min": 120 if mt == "movie" else None,
                    "episodes": 30 if mt == "tv" else None,
                }
            )
            out.append(i)
        return out

    async def sections(self):
        return [{"id": "1", "title": "Films", "type": "movie"}, {"id": "2", "title": "Séries", "type": "tv"}]

    async def library(self):
        return self._items()

    async def index(self):
        return {(i["media_type"], i["id"]): i for i in self._items()}

    async def search(self, query, limit=20):
        q = query.lower()
        return [i for i in self._items() if q in i["title"].lower()][:limit]


class MockTrakt:
    is_mock = True
    connected = False

    async def watchlist(self):
        rows = [(r, "movie") for r in _MOVIES[6:]] + [(r, "tv") for r in _SHOWS[4:]]
        return [
            {"tmdb_id": r[0], "media_type": mt, "title": r[1], "year": int(r[3][:4]), "listed_at": None, "trakt_id": None, "slug": None}
            for r, mt in rows
        ]

    async def history(self, limit=50):
        rows = [(r, "movie") for r in _MOVIES[:4]] + [(r, "tv") for r in _SHOWS[:2]]
        return [{"tmdb_id": r[0], "media_type": mt, "title": r[1], "year": int(r[3][:4]), "watched_at": None} for r, mt in rows]

    async def ratings(self):
        return [{"tmdb_id": _MOVIES[2][0], "media_type": "movie", "title": _MOVIES[2][1], "rating": 9, "rated_at": None}]

    async def watched_keys(self):
        return set()

    async def recommendations(self, media_type, limit=30):
        return []

    async def stats(self):
        return {
            "movies": {"watched": 412, "minutes": 51240},
            "shows": {"watched": 63},
            "episodes": {"watched": 2380, "minutes": 104600},
        }

    async def lookup(self, media_type, tmdb_id):
        return {"rating": 8.2, "votes": 1234, "slug": None, "url": None}
