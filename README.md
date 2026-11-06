# Web Virgen del Valle · Trekia · Aula Viajera

Sitio público + panel de administración en `/admin`.

## Cómo está armado
- `site/`: las páginas públicas (HTML, CSS, JS y fotos). `site/js/data.js` **no existe**: lo arma el servidor en `/js/data.js` con las salidas de la base.
- `app.py`: servidor Flask (panel, consultas, fotos, links por viaje).
- `contenido.json`: textos fijos (destinos, programas de Aula Viajera, redes).
- `salidas_iniciales.json`: salidas de ejemplo que se cargan solas la primera vez.

## Variables de entorno (en Render)
| Variable | Qué es |
|---|---|
| `DATABASE_URL` | Dirección de la base Postgres (Render la da) |
| `SECRET_KEY` | Texto largo al azar (cierra las sesiones del panel) |
| `ADMIN_USER` | Usuario del panel (por defecto `miriam`) |
| `ADMIN_PASSWORD` | Contraseña del panel. Sin esta variable nadie puede entrar |

## Probar en tu compu
```
pip install -r requirements.txt
ADMIN_PASSWORD=prueba python app.py      # http://localhost:5000  ·  panel: /admin
python -m pytest tests -q
```
