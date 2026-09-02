import random
from dataclasses import dataclass, field

@dataclass
class Theme:
    """A thematic catalog definition."""
    id: str  # unique identifier like 'halloween_horror'
    name: str  # display name like '🎃 Halloween: Terror & Suspense'
    genre_ids: list[int] = field(default_factory=list)  # TMDB genre IDs
    keywords: list[str] = field(default_factory=list)  # TMDB keyword filters  
    vote_average_gte: float | None = None  # minimum vote average
    release_year_range: tuple[int, int] | None = None  # (start_year, end_year)
    with_original_language: list[str] | None = None  # language codes
    exclude_original_language: list[str] | None = None
    content_types: list[str] = field(default_factory=lambda: ['movie', 'series'])  # which types this theme applies to

# Seasonal themes by month (1-12)
SEASONAL_THEMES: dict[int, list[Theme]] = {
    1: [Theme(id='new_year_fresh', name='🌟 Novo Ano, Novos Começos', genre_ids=[18, 10751], content_types=['movie', 'series'])],
    2: [Theme(id='valentines_romance', name='💕 Românticos para Dois', genre_ids=[10749], content_types=['movie', 'series'])],
    3: [Theme(id='women_power', name='💪 Protagonistas Femininas', keywords=['female protagonist', 'strong woman'], content_types=['movie', 'series'])],
    4: [Theme(id='spring_adventure', name='🌼 Aventuras de Primavera', genre_ids=[12, 14], content_types=['movie', 'series'])],
    5: [Theme(id='family_bonds', name='👨\u200d👩\u200d👧 Laços de Família', genre_ids=[10751, 18], content_types=['movie', 'series'])],
    6: [Theme(id='pride_diversity', name='🏳️\u200d🌈 Orgulho & Diversidade', keywords=['lgbtq'], content_types=['movie', 'series'])],
    7: [Theme(id='summer_blockbusters', name='☀️ Blockbusters de Verão', genre_ids=[28, 878, 12], vote_average_gte=7.0, content_types=['movie'])],
    8: [Theme(id='suspense_summer', name='🕶️ Suspense de Verão', genre_ids=[53, 9648], content_types=['movie', 'series'])],
    9: [Theme(id='back_to_school', name='🎒 De Volta à Escola', keywords=['school', 'college', 'teacher'], content_types=['movie', 'series'])],
    10: [Theme(id='halloween_horror', name='🎃 Halloween: Terror & Suspense', genre_ids=[27, 53], content_types=['movie', 'series'])],
    11: [Theme(id='war_history', name='⚔️ Guerra & História', genre_ids=[10752, 36], content_types=['movie', 'series'])],
    12: [Theme(id='christmas_family', name='🎄 Natal & Família', genre_ids=[10751, 35], keywords=['christmas'], content_types=['movie', 'series'])],
}

# Random thematic themes for the 3 rotating slots
RANDOM_THEMES: list[Theme] = [
    Theme(id='epic_worlds', name='🌍 Mundos Épicos', genre_ids=[14, 878], vote_average_gte=7.0, content_types=['movie', 'series']),
    Theme(id='cozy_couch', name='🛋️ De Conchinha no Sofá', genre_ids=[35, 10749, 10751], content_types=['movie', 'series']),
    Theme(id='action_nonstop', name='💥 Ação Non-Stop', genre_ids=[28], vote_average_gte=6.5, content_types=['movie']),
    Theme(id='award_dramas', name='🏆 Dramas Premiados', genre_ids=[18], vote_average_gte=8.0, content_types=['movie', 'series']),
    Theme(id='mystery_crime', name='🕵️ Mistério & Crime', genre_ids=[9648, 80], content_types=['movie', 'series']),
    Theme(id='90s_classics', name='📼 Clássicos dos Anos 90', genre_ids=[], release_year_range=(1990, 1999), vote_average_gte=7.0, content_types=['movie']),
    Theme(id='2000s_hits', name='📀 Hits dos Anos 2000', genre_ids=[], release_year_range=(2000, 2009), vote_average_gte=7.0, content_types=['movie']),
    Theme(id='international_cinema', name='🌎 Cinema Internacional', genre_ids=[18], exclude_original_language=['en'], vote_average_gte=7.5, content_types=['movie']),
    Theme(id='scifi_future', name='🚀 Ficção Científica', genre_ids=[878], content_types=['movie', 'series']),
    Theme(id='animation_gems', name='🎨 Animações Incríveis', genre_ids=[16], vote_average_gte=7.0, content_types=['movie']),
    Theme(id='true_stories', name='📰 Baseado em Fatos Reais', keywords=['based on true story', 'biography'], content_types=['movie']),
    Theme(id='psychological_mind', name='🧠 Psicológicos de Tirar o Fôlego', genre_ids=[53], keywords=['psychological'], content_types=['movie', 'series']),
    Theme(id='comedy_laugh', name='😂 Rir até Não Poder Mais', genre_ids=[35], vote_average_gte=7.0, content_types=['movie', 'series']),
    Theme(id='documentary_world', name='🌍 Documentários Reveladores', genre_ids=[99], content_types=['movie', 'series']),
    Theme(id='fantasy_magic', name='✨ Fantasia & Magia', genre_ids=[14], content_types=['movie', 'series']),
]

def get_seasonal_theme(month: int) -> Theme | None:
    """Returns a random seasonal theme for the given month (1-12)."""
    themes = SEASONAL_THEMES.get(month)
    if themes:
        return random.choice(themes)
    return None

def get_random_themes(count: int, exclude_ids: list[str] | None = None) -> list[Theme]:
    """Picks random themes without repetition, excluding given ids."""
    if exclude_ids is None:
        exclude_ids = []
    
    available_themes = [t for t in RANDOM_THEMES if t.id not in exclude_ids]
    if len(available_themes) < count:
        return available_themes
        
    return random.sample(available_themes, count)
