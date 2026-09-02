import json
import base64
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

ALL_CATALOGS = [
    ('movie_trending', '🔥 Filmes em Alta'),
    ('movie_popular', '⭐ Filmes Populares'),
    ('movie_new', '🆕 Lançamentos'),
    ('series_trending', '🔥 Séries em Alta'),
    ('series_popular', '⭐ Séries Populares'),
    ('series_new', '🆕 Séries Recentes'),
    ('anime_seasonal', '🌸 Anime da Temporada'),
    ('anime_trending', '🔥 Anime em Alta'),
    ('anime_popular', '⭐ Anime Populares'),
    ('anime_battle', '⚔️ Anime de Batalha & Poderes'),
    ('anime_isekai', '🌍 Anime Isekai & Fantasia'),
    ('anime_romance', '💖 Anime Romance & Slice of Life'),
]

LANGUAGES = [
    ('pt-BR', 'Português (pt-BR)'),
    ('en-US', 'English (en-US)'),
    ('es-ES', 'Español (es-ES)'),
    ('fr-FR', 'Français (fr-FR)'),
    ('de-DE', 'Deutsch (de-DE)'),
    ('it-IT', 'Italiano (it-IT)'),
    ('ja-JP', '日本語 (ja-JP)'),
]

def render_configure_page(host: str, existing_config: dict = None) -> str:
    existing_config = existing_config or {}
    tmdb_key = existing_config.get('tmdb_api_key', '')
    language = existing_config.get('language', 'pt-BR')
    enabled_catalogs = existing_config.get('enabled_catalogs', [c[0] for c in ALL_CATALOGS])
    
    catalogs_html = ""
    for cat_id, cat_name in ALL_CATALOGS:
        checked = "checked" if cat_id in enabled_catalogs else ""
        catalogs_html += f"""
        <label class="catalog-item">
            <input type="checkbox" name="catalogs" value="{cat_id}" {checked}>
            <span>{cat_name}</span>
        </label>
        """
        
    languages_html = ""
    for lang_code, lang_name in LANGUAGES:
        selected = "selected" if lang_code == language else ""
        languages_html += f'<option value="{lang_code}" {selected}>{lang_name}</option>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Catalog Hub — Configuração</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #0f172a;
            color: #f8fafc;
            margin: 0;
            padding: 2rem;
            display: flex;
            justify-content: center;
        }}
        .container {{
            background: #1e293b;
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
            max-width: 600px;
            width: 100%;
        }}
        h1 {{
            text-align: center;
            color: #38bdf8;
            margin-bottom: 2rem;
        }}
        .form-group {{
            margin-bottom: 1.5rem;
        }}
        label {{
            display: block;
            margin-bottom: 0.5rem;
            font-weight: 600;
        }}
        input[type="text"], select {{
            width: 100%;
            padding: 0.75rem;
            border-radius: 6px;
            border: 1px solid #334155;
            background: #0f172a;
            color: white;
            box-sizing: border-box;
        }}
        input[type="text"]:focus, select:focus {{
            outline: none;
            border-color: #38bdf8;
        }}
        .help-text {{
            font-size: 0.85rem;
            color: #94a3b8;
            margin-top: 0.25rem;
        }}
        .help-text a {{
            color: #38bdf8;
            text-decoration: none;
        }}
        .help-text a:hover {{
            text-decoration: underline;
        }}
        .catalogs-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 0.5rem;
            margin-top: 0.5rem;
        }}
        .catalog-item {{
            display: flex;
            align-items: center;
            background: #0f172a;
            padding: 0.5rem;
            border-radius: 6px;
            cursor: pointer;
            border: 1px solid #334155;
        }}
        .catalog-item input {{
            margin-right: 0.5rem;
        }}
        .actions {{
            display: flex;
            flex-direction: column;
            gap: 1rem;
            margin-top: 2rem;
        }}
        .btn {{
            padding: 0.75rem;
            border: none;
            border-radius: 6px;
            font-weight: bold;
            cursor: pointer;
            text-align: center;
            text-decoration: none;
            font-size: 1rem;
            transition: opacity 0.2s;
        }}
        .btn:hover {{
            opacity: 0.9;
        }}
        .btn-install {{
            background: #0ea5e9;
            color: white;
        }}
        .btn-web {{
            background: #8b5cf6;
            color: white;
        }}
        .btn-copy {{
            background: #475569;
            color: white;
        }}
        .error {{
            color: #ef4444;
            display: none;
            margin-top: 0.5rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>✨ Catalog Hub — Configuração</h1>
        
        <div class="form-group">
            <label for="tmdb_api_key">TMDB API Key (Required)</label>
            <input type="text" id="tmdb_api_key" placeholder="Your TMDB v3 API Key" value="{tmdb_key}">
            <div class="help-text">
                Get yours at <a href="https://www.themoviedb.org/settings/api" target="_blank">TMDB Settings</a>
            </div>
            <div id="tmdb-error" class="error">TMDB API Key is required.</div>
        </div>

        <div class="form-group">
            <label for="language">Idioma</label>
            <select id="language">
                {languages_html}
            </select>
        </div>

        <div class="form-group">
            <label>Catálogos Ativos</label>
            <div class="catalogs-grid">
                {catalogs_html}
            </div>
        </div>

        <div class="actions">
            <button class="btn btn-install" onclick="installAddon('stremio')">Install Addon</button>
            <button class="btn btn-web" onclick="installAddon('web')">Open in Stremio Web</button>
            <button class="btn btn-copy" onclick="copyUrl()">Copy URL</button>
            <button class="btn btn-copy" style="background: #1e293b; margin-top: 10px;" onclick="copyBaseUrl()">Copy Base URL (For Publishing)</button>
        </div>
    </div>

    <script>
        const host = "{host}";

        function getConfig() {{
            const tmdbKey = document.getElementById('tmdb_api_key').value.trim();
            if (!tmdbKey) {{
                document.getElementById('tmdb-error').style.display = 'block';
                return null;
            }}
            document.getElementById('tmdb-error').style.display = 'none';

            const language = document.getElementById('language').value;
            const catalogCheckboxes = document.querySelectorAll('input[name="catalogs"]:checked');
            const enabledCatalogs = Array.from(catalogCheckboxes).map(cb => cb.value);

            return {{
                tmdb_api_key: tmdbKey,
                language: language,
                enabled_catalogs: enabledCatalogs
            }};
        }}

        function buildUrl() {{
            const config = getConfig();
            if (!config) return null;

            const encoded = btoa(JSON.stringify(config));
            return `stremio://${{host}}/${{encoded}}/manifest.json`;
        }}

        function buildWebUrl() {{
            const config = getConfig();
            if (!config) return null;

            const encoded = btoa(JSON.stringify(config));
            const manifestUrl = `https://${{host}}/${{encoded}}/manifest.json`;
            return `https://web.stremio.com/#/addons?addon=${{encodeURIComponent(manifestUrl)}}`;
        }}

        function installAddon(type) {{
            const url = type === 'web' ? buildWebUrl() : buildUrl();
            if (url) {{
                window.location.href = url;
            }}
        }}

        function copyUrl() {{
            const config = getConfig();
            if (!config) return;

            const encoded = btoa(JSON.stringify(config));
            const manifestUrl = `https://${{host}}/${{encoded}}/manifest.json`;
            
            navigator.clipboard.writeText(manifestUrl).then(() => {{
                alert('Manifest URL copied to clipboard!');
            }}).catch(err => {{
                console.error('Failed to copy: ', err);
            }});
        }}

        function copyBaseUrl() {{
            const manifestUrl = `https://${{host}}/manifest.json`;
            navigator.clipboard.writeText(manifestUrl).then(() => {{
                alert('Base Manifest URL copied! (Use this for Stremio community catalog)');
            }}).catch(err => {{
                console.error('Failed to copy: ', err);
            }});
        }}
    </script>
</body>
</html>"""
    return html

@router.get("/configure")
@router.get("/{config}/configure")
async def configure(request: Request, config: str = None):
    host = request.headers.get("host", "")
    existing_config = {}
    
    if config:
        try:
            # Add padding if needed
            padding = len(config) % 4
            padded_config = config + ('=' * (4 - padding) if padding else '')
            decoded_json = base64.b64decode(padded_config).decode('utf-8')
            existing_config = json.loads(decoded_json)
        except Exception:
            pass # ignore invalid config

    html = render_configure_page(host, existing_config)
    return HTMLResponse(content=html)
