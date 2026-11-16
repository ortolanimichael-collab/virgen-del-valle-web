"""Google Drive como depósito de fotos y videos (la base Postgres guarda solo la referencia).

Cómo se usa
-----------
1. En Google Cloud se crea un «ID de cliente OAuth» (tipo Aplicación web) y se cargan en Render:
   GOOGLE_CLIENT_ID y GOOGLE_CLIENT_SECRET. URI de redirección autorizada: https://<la-web>/admin/drive/vuelta
2. En el panel → Drive → «Conectar Google Drive» y se elige el Gmail de la agencia (una sola vez).
3. Desde ahí, todo lo que se sube (fotos de salidas, portada, escuelas, flyers y videos) va a una carpeta
   «Virgen del Valle - Web» de ese Drive, ordenado en subcarpetas. Si Drive no está conectado o falla,
   se guarda en la base como antes, así nunca se pierde una subida.

Permiso que pide: drive.file → la web solo ve y toca los archivos que ella misma creó, nada más del Drive.
El visitante nunca ve un link de Drive: las fotos se sirven desde /media/<id> (con caché) y los videos
cortos desde /media/video/<id>. Solo los videos largos usan el reproductor de Drive incrustado.
"""
import os
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests

from extensiones import db

SCOPE = "https://www.googleapis.com/auth/drive.file openid email"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
RAIZ = "Virgen del Valle - Web"
CACHE = os.environ.get("MEDIA_CACHE_DIR", "/tmp/vdv-media")
TROZO_MAX = 4 * 1024 * 1024          # cada respuesta de video por la web manda como mucho 4 MB (el navegador pide el resto solo)
_token = {"valor": "", "vence": 0.0}


class DriveCuenta(db.Model):
    """La cuenta conectada. Prefijo vdvx_: no va al respaldo .json (tiene el permiso de acceso)."""
    __tablename__ = "vdvx_drive_cuenta"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(160), default="")
    refresh_token = db.Column(db.String(512), nullable=False)
    raiz_id = db.Column(db.String(80), default="")
    conectada = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class DriveCarpeta(db.Model):
    __tablename__ = "vdvx_drive_carpeta"
    id = db.Column(db.Integer, primary_key=True)
    ruta = db.Column(db.String(400), unique=True, nullable=False)
    drive_id = db.Column(db.String(80), nullable=False)


class DriveSubida(db.Model):
    """Subidas de video en curso (se mandan en trozos de 8 MB a través de la web)."""
    __tablename__ = "vdvx_drive_subida"
    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(64), unique=True, nullable=False)
    url = db.Column(db.String(2000), nullable=False)
    viaje_id = db.Column(db.Integer, nullable=False)
    tamano = db.Column(db.BigInteger, nullable=False)
    tipo = db.Column(db.String(60), default="video/mp4")
    nombre = db.Column(db.String(160), default="")
    titulo = db.Column(db.String(120), default="")
    creada = db.Column(db.Float, default=time.time)


class DriveError(Exception):
    pass


# ---------------------------------------------------------------- conexión

def configurado():
    return bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))


def cuenta():
    try:
        return DriveCuenta.query.first()
    except Exception:
        return None


def conectado():
    return configurado() and cuenta() is not None


def url_autorizar(redirect_uri, estado):
    return AUTH_URL + "?" + urlencode({
        "client_id": os.environ["GOOGLE_CLIENT_ID"], "redirect_uri": redirect_uri, "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true", "state": estado})


def terminar_autorizacion(code, redirect_uri):
    r = requests.post(TOKEN_URL, data={"code": code, "client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                                       "redirect_uri": redirect_uri, "grant_type": "authorization_code"}, timeout=20)
    if r.status_code != 200:
        raise DriveError(f"Google no aceptó la conexión ({r.status_code}).")
    d = r.json()
    if not d.get("refresh_token"):
        raise DriveError("Google no devolvió el permiso permanente. Quitá el acceso de la app en tu cuenta de Google y conectá de nuevo.")
    email = ""
    try:
        email = requests.get("https://openidconnect.googleapis.com/v1/userinfo", headers={"Authorization": f"Bearer {d['access_token']}"}, timeout=15).json().get("email", "")
    except Exception:
        pass
    DriveCuenta.query.delete()
    DriveCarpeta.query.delete()
    db.session.add(DriveCuenta(email=email[:160], refresh_token=d["refresh_token"]))
    db.session.commit()
    _token.update(valor=d["access_token"], vence=time.time() + int(d.get("expires_in", 3600)) - 120)
    return email


def desconectar():
    c = cuenta()
    if c:
        try:
            requests.post("https://oauth2.googleapis.com/revoke", params={"token": c.refresh_token}, timeout=10)
        except Exception:
            pass
    DriveCuenta.query.delete()
    DriveCarpeta.query.delete()
    db.session.commit()
    _token.update(valor="", vence=0)


def token():
    if _token["valor"] and time.time() < _token["vence"]:
        return _token["valor"]
    c = cuenta()
    if not c or not configurado():
        raise DriveError("Google Drive no está conectado.")
    r = requests.post(TOKEN_URL, data={"client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                                       "refresh_token": c.refresh_token, "grant_type": "refresh_token"}, timeout=20)
    if r.status_code != 200:
        raise DriveError("Se perdió el permiso de Google Drive. Volvé a conectarlo desde el panel → Drive.")
    d = r.json()
    _token.update(valor=d["access_token"], vence=time.time() + int(d.get("expires_in", 3600)) - 120)
    return _token["valor"]


def _h(extra=None):
    h = {"Authorization": f"Bearer {token()}"}
    h.update(extra or {})
    return h


def _ok(r, que):
    if r.status_code >= 400:
        raise DriveError(f"Drive no pudo {que} ({r.status_code}).")
    return r


# ---------------------------------------------------------------- carpetas y archivos

def _crear_carpeta(nombre, padre):
    meta = {"name": nombre[:120], "mimeType": "application/vnd.google-apps.folder"}
    if padre:
        meta["parents"] = [padre]
    return _ok(requests.post(f"{API}/files", headers=_h(), json=meta, params={"fields": "id"}, timeout=20), "crear la carpeta").json()["id"]


def _existe(fid):
    r = requests.get(f"{API}/files/{fid}", headers=_h(), params={"fields": "id,trashed"}, timeout=15)
    return r.status_code == 200 and not r.json().get("trashed")


def carpeta(*partes):
    """Devuelve el id de la carpeta «Virgen del Valle - Web/partes...», creándola si hace falta."""
    c = cuenta()
    if not c.raiz_id or not _existe(c.raiz_id):
        c.raiz_id = _crear_carpeta(RAIZ, None)
        DriveCarpeta.query.delete()
        db.session.commit()
    padre, ruta = c.raiz_id, ""
    for p in [" ".join(str(x).replace("/", "-").split())[:100] or "Sin nombre" for x in partes]:
        ruta = f"{ruta}/{p}"
        fila = DriveCarpeta.query.filter_by(ruta=ruta).first()
        if fila:
            padre = fila.drive_id
            continue
        padre = _crear_carpeta(p, padre)
        db.session.add(DriveCarpeta(ruta=ruta[:400], drive_id=padre))
        db.session.commit()
    return padre


def subir(datos, nombre, mime, partes, _reintento=True):
    """Sube un archivo chico (fotos) y devuelve su id."""
    try:
        return _subir(datos, nombre, mime, carpeta(*partes))
    except DriveError:
        if not _reintento:
            raise
        DriveCarpeta.query.delete()          # alguien borró o movió una carpeta en Drive: se vuelven a crear
        db.session.commit()
        return subir(datos, nombre, mime, partes, _reintento=False)


def _subir(datos, nombre, mime, padre):
    limite = "vdv" + secrets.token_hex(8)
    meta = '{"name": %s, "parents": ["%s"]}' % (_json_str(nombre), padre)
    cuerpo = (f"--{limite}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
              f"--{limite}\r\nContent-Type: {mime}\r\n\r\n").encode() + datos + f"\r\n--{limite}--".encode()
    r = requests.post(UPLOAD, headers=_h({"Content-Type": f"multipart/related; boundary={limite}"}),
                      params={"uploadType": "multipart", "fields": "id"}, data=cuerpo, timeout=60)
    return _ok(r, "subir el archivo").json()["id"]


def _json_str(s):
    import json
    return json.dumps(s or "archivo", ensure_ascii=False)


def iniciar_subida(nombre, mime, tamano, partes):
    """Abre una subida reanudable (videos) y devuelve la URL de sesión de Google."""
    padre = carpeta(*partes)
    r = requests.post(UPLOAD, headers=_h({"X-Upload-Content-Type": mime, "X-Upload-Content-Length": str(tamano)}),
                      params={"uploadType": "resumable", "fields": "id,size,mimeType"}, json={"name": nombre[:150], "parents": [padre]}, timeout=30)
    _ok(r, "empezar la subida")
    return r.headers["Location"]


def mandar_trozo(url, desde, datos, total):
    """Manda un trozo. Devuelve (terminado, info_del_archivo | siguiente_byte)."""
    hasta = desde + len(datos) - 1
    r = requests.put(url, headers={"Content-Range": f"bytes {desde}-{hasta}/{total}"}, data=datos, timeout=120)
    if r.status_code in (200, 201):
        return True, r.json()
    if r.status_code == 308:
        rng = r.headers.get("Range", "")
        return False, (int(rng.split("-")[-1]) + 1) if rng else 0
    raise DriveError(f"Drive cortó la subida ({r.status_code}).")


def compartir(fid):
    """Cualquiera con el link puede ver (lo necesita el reproductor de Drive incrustado)."""
    _ok(requests.post(f"{API}/files/{fid}/permissions", headers=_h(), json={"role": "reader", "type": "anyone"}, timeout=20), "compartir el video")


def borrar(fid):
    try:
        requests.delete(f"{API}/files/{fid}", headers=_h(), timeout=20)
    except Exception:
        pass
    try:
        os.remove(os.path.join(CACHE, f"{fid}.bin"))
    except OSError:
        pass


def bajar(fid):
    """Contenido completo (fotos), con caché en disco: Google se consulta una sola vez por foto."""
    ruta = os.path.join(CACHE, f"{fid}.bin")
    try:
        with open(ruta, "rb") as f:
            return f.read()
    except OSError:
        pass
    r = _ok(requests.get(f"{API}/files/{fid}", headers=_h(), params={"alt": "media"}, timeout=60), "traer la foto")
    os.makedirs(CACHE, exist_ok=True)
    tmp = f"{ruta}.{secrets.token_hex(4)}"
    with open(tmp, "wb") as f:
        f.write(r.content)
    os.replace(tmp, ruta)
    return r.content


def trozo_video(fid, tamano, rango):
    """Para el reproductor del navegador: devuelve (status, headers, generador) de un pedazo de hasta 4 MB."""
    ini, fin = 0, tamano - 1
    if rango and rango.startswith("bytes="):
        a, _, b = rango[6:].split(",")[0].partition("-")
        if a.strip():
            ini = int(a)
            fin = int(b) if b.strip() else tamano - 1
        elif b.strip():
            ini = max(0, tamano - int(b))
    if ini >= tamano:
        return 416, {"Content-Range": f"bytes */{tamano}"}, iter(())
    fin = min(fin, ini + TROZO_MAX - 1, tamano - 1)
    r = requests.get(f"{API}/files/{fid}", headers=_h({"Range": f"bytes={ini}-{fin}"}), params={"alt": "media"}, stream=True, timeout=30)
    _ok(r, "traer el video")
    return 206, {"Content-Range": f"bytes {ini}-{fin}/{tamano}", "Content-Length": str(fin - ini + 1), "Accept-Ranges": "bytes"}, r.iter_content(256 * 1024)


def embed(fid):
    return f"https://drive.google.com/file/d/{fid}/preview"
