from app.models.catalog import CatalogDefinition, CatalogProvider, ContentType

# TMDB genre lists for the Stremio Discover dropdown filter
MOVIE_GENRES = [
    'Ação', 'Aventura', 'Animação', 'Comédia', 'Crime', 'Documentário',
    'Drama', 'Família', 'Fantasia', 'História', 'Terror', 'Música',
    'Mistério', 'Romance', 'Ficção científica', 'Thriller', 'Guerra', 'Faroeste',
]

SERIES_GENRES = [
    'Ação e Aventura', 'Animação', 'Comédia', 'Crime', 'Documentário',
    'Drama', 'Família', 'Kids', 'Mistério', 'Realidade',
    'Sci-Fi & Fantasia', 'Soap', 'Talk', 'Guerra & Política', 'Faroeste',
]

# Anime genres: AniList official genres + popular tags merged
ANIME_GENRES = [
    # Official AniList genres
    'Action', 'Adventure', 'Comedy', 'Drama', 'Fantasy', 'Horror',
    'Mecha', 'Music', 'Mystery', 'Psychological', 'Romance', 'Sci-Fi',
    'Slice of Life', 'Sports', 'Supernatural', 'Thriller',
    # Popular tags (treated as genres in the filter)
    'Shounen', 'Seinen', 'Shoujo', 'Josei', 'Isekai', 'Mahou Shoujo',
]

FIXED_CATALOGS: list[CatalogDefinition] = [
    # ---- Movies ----
    CatalogDefinition(
        id='movie_trending', content_type=ContentType.MOVIE,
        name='🔥 Filmes em Alta', provider=CatalogProvider.TMDB,
        refresh_interval_seconds=21600,  # 6h
        provider_params={'endpoint': 'trending', 'time_window': 'week'},
        genre_options=MOVIE_GENRES,
    ),
    CatalogDefinition(
        id='movie_popular', content_type=ContentType.MOVIE,
        name='⭐ Filmes Populares', provider=CatalogProvider.TMDB,
        refresh_interval_seconds=43200,  # 12h
        provider_params={'endpoint': 'popular'},
        genre_options=MOVIE_GENRES,
    ),
    CatalogDefinition(
        id='movie_new', content_type=ContentType.MOVIE,
        name='🆕 Lançamentos', provider=CatalogProvider.TMDB,
        refresh_interval_seconds=21600,  # 6h
        provider_params={'endpoint': 'now_playing'},
        genre_options=MOVIE_GENRES,
    ),
    # ---- Series ----
    CatalogDefinition(
        id='series_trending', content_type=ContentType.SERIES,
        name='🔥 Séries em Alta', provider=CatalogProvider.TMDB,
        refresh_interval_seconds=21600,
        provider_params={'endpoint': 'trending', 'time_window': 'week'},
        genre_options=SERIES_GENRES,
    ),
    CatalogDefinition(
        id='series_popular', content_type=ContentType.SERIES,
        name='⭐ Séries Populares', provider=CatalogProvider.TMDB,
        refresh_interval_seconds=43200,
        provider_params={'endpoint': 'popular'},
        genre_options=SERIES_GENRES,
    ),
    CatalogDefinition(
        id='series_new', content_type=ContentType.SERIES,
        name='🆕 Séries Recentes', provider=CatalogProvider.TMDB,
        refresh_interval_seconds=21600,
        provider_params={'endpoint': 'airing_today'},
        genre_options=SERIES_GENRES,
    ),
    # ---- Anime (fixed) ----
    CatalogDefinition(
        id='anime_seasonal', content_type=ContentType.ANIME,
        name='🌸 Anime da Temporada', provider=CatalogProvider.ANILIST,
        refresh_interval_seconds=86400,  # 24h
        provider_params={'endpoint': 'seasonal'},
        genre_options=ANIME_GENRES,
    ),
    CatalogDefinition(
        id='anime_trending', content_type=ContentType.ANIME,
        name='🔥 Anime em Alta', provider=CatalogProvider.ANILIST,
        refresh_interval_seconds=21600,  # 6h (AniList trending updates less frequently but we keep it fresh)
        provider_params={'endpoint': 'trending'},
        genre_options=ANIME_GENRES,
    ),
    CatalogDefinition(
        id='anime_popular', content_type=ContentType.ANIME,
        name='⭐ Anime Populares', provider=CatalogProvider.ANILIST,
        refresh_interval_seconds=86400,
        provider_params={'endpoint': 'popular'},
        genre_options=ANIME_GENRES,
    ),
    # ---- Anime curated genre catalogs ----
    CatalogDefinition(
        id='anime_battle', content_type=ContentType.ANIME,
        name='⚔️ Anime de Batalha & Poderes', provider=CatalogProvider.ANILIST,
        refresh_interval_seconds=86400,
        provider_params={
            'endpoint': 'by_genre',
            'genres': ['Action'],
            'tags': ['Super Power', 'Martial Arts', 'Battle Royale'],
        },
        genre_filter_supported=False,
    ),
    CatalogDefinition(
        id='anime_isekai', content_type=ContentType.ANIME,
        name='🌍 Anime Isekai & Fantasia', provider=CatalogProvider.ANILIST,
        refresh_interval_seconds=86400,
        provider_params={
            'endpoint': 'by_genre',
            'genres': ['Fantasy'],
            'tags': ['Isekai'],
        },
        genre_filter_supported=False,
    ),
    CatalogDefinition(
        id='anime_romance', content_type=ContentType.ANIME,
        name='💖 Anime Romance & Slice of Life', provider=CatalogProvider.ANILIST,
        refresh_interval_seconds=86400,
        provider_params={
            'endpoint': 'by_genre',
            'genres': ['Romance', 'Slice of Life'],
            'tags': [],
        },
        genre_filter_supported=False,
    ),
]
