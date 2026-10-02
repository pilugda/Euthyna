#!/usr/bin/env python3
"""Euthyna - descarga y cuenta las iniciativas de la legislatura actual del Congreso.

Fuente: https://www.congreso.es/es/datos-abiertos (datos abiertos oficiales).
Solo usa la libreria estandar de Python 3.8+. Uso:  python3 actualizar_iniciativas.py

Que hace, paso a paso:
 1. Lee la pagina de iniciativas y encuentra los 4 enlaces JSON (el nombre lleva una
    marca de fecha que cambia, por eso no se puede fijar la URL).
 2. Guarda los archivos originales SIN tocar, con su huella SHA-256 (verificacion).
 3. Calcula recuentos y los guarda en resumen.json / resumen.csv, con la fecha de descarga.
 4. Anota en 'sin_clasificar' todo lo que no sabe clasificar, para revisarlo a mano.
"""
import csv, hashlib, json, re, sys, urllib.request
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

PAGINA = "https://www.congreso.es/es/opendata/iniciativas"
BASE = "https://www.congreso.es"
NOMBRES = ["IniciativasLegislativasAprobadas", "ProyectosDeLey",
           "ProposicionesDeLey", "PropuestasDeReforma"]
RAIZ = Path(__file__).resolve().parent
UA = {"User-Agent": "Euthyna/0.1 (proyecto ciudadano; datos abiertos)"}


def descargar(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def registros(datos):
    """El JSON puede ser una lista o un objeto que contiene la lista."""
    if isinstance(datos, list):
        return datos
    if isinstance(datos, dict):
        for v in datos.values():
            if isinstance(v, list):
                return v
    return []


def enlaces_json(html):
    out = {}
    for m in re.finditer(r'href="([^"]*?/opendata/iniciativas/(\w+?)__\d+\.json)"', html):
        href, nombre = m.group(1), m.group(2)
        if nombre in NOMBRES:
            out[nombre] = href if href.startswith("http") else BASE + href
    return out


def clasificar_aprobada(r):
    """Clasifica cada FILA del archivo de aprobadas. Ojo: una fila no es una norma."""
    t = (r.get("TITULO_LEY") or "").lower()
    if "corrección de errores" in t or "correccion de errores" in t:
        return "correccion_de_errores"
    if "resolución" in t or "resolucion" in t:
        if "derogaci" in t:
            return "resolucion_derogacion"
        if "convalidaci" in t:
            return "resolucion_convalidacion"
        return "sin_clasificar"
    return "norma"


def anio(fecha):
    m = re.search(r"(\d{4})", fecha or "")
    return m.group(1) if m else "?"


def resumen_aprobadas(regs):
    filas = Counter(); normas = set(); sin = []
    for r in regs:
        tipo, c = r.get("TIPO", "?"), clasificar_aprobada(r)
        filas[(tipo, c)] += 1
        if c == "norma":
            normas.add((tipo, r.get("NUMERO_LEY"), anio(r.get("FECHA_LEY"))))
        elif c == "sin_clasificar":
            sin.append(r.get("TITULO_LEY"))
    por_tipo = Counter(t for t, _, _ in normas)
    return {"filas_total": len(regs),
            "normas_distintas_por_tipo": dict(por_tipo),
            "filas_por_tipo_y_clase": {f"{t} | {c}": n for (t, c), n in filas.items()},
            "sin_clasificar": sin}


def resumen_tramitacion(regs):
    res = Counter(); sit = Counter(); aut = Counter(); rdl = 0
    for r in regs:
        x = (r.get("RESULTADOTRAMITACION") or "").strip()
        res[re.split(r"\s+\d", x)[0] if x else "En tramitación (sin resultado)"] += 1
        sit[(r.get("SITUACIONACTUAL") or "?").split(" - ")[0]] += 1
        aut[r.get("AUTOR") or "?"] += 1
        if re.search(r"procedente del Real Decreto-ley", r.get("OBJETO") or "", re.I):
            rdl += 1
    return {"total": len(regs), "por_resultado": dict(res), "por_situacion": dict(sit),
            "por_autor": dict(aut), "procedentes_de_real_decreto_ley": rdl}


def main():
    hoy = date.today().isoformat()
    carpeta = RAIZ / "datos" / "originales" / hoy
    carpeta.mkdir(parents=True, exist_ok=True)
    enl = enlaces_json(descargar(PAGINA).decode("utf-8", "replace"))
    faltan = [n for n in NOMBRES if n not in enl]
    if faltan:
        sys.exit(f"No encuentro estos enlaces en la pagina: {faltan}. No se escribe nada.")
    huellas, res = {}, {}
    for nombre, url in enl.items():
        crudo = descargar(url)
        (carpeta / f"{nombre}.json").write_bytes(crudo)
        huellas[nombre] = {"url": url, "sha256": hashlib.sha256(crudo).hexdigest(), "bytes": len(crudo)}
        regs = registros(json.loads(crudo.decode("utf-8-sig")))
        res[nombre] = resumen_aprobadas(regs) if nombre == NOMBRES[0] else resumen_tramitacion(regs)
    salida = {"legislatura": "XV (actual)", "fuente": PAGINA, "descargado_utc":
              datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "archivos": huellas, "resumen": res}
    (RAIZ / "datos").mkdir(exist_ok=True)
    (RAIZ / "datos" / "resumen.json").write_text(json.dumps(salida, ensure_ascii=False, indent=2), "utf-8")
    with open(RAIZ / "datos" / "resumen.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["archivo", "medida", "valor", "descargado"])
        for nombre, r in res.items():
            for k, v in r.items():
                if isinstance(v, dict):
                    for kk, vv in v.items():
                        w.writerow([nombre, f"{k}: {kk}", vv, hoy])
                elif not isinstance(v, list):
                    w.writerow([nombre, k, v, hoy])
    print("Listo. Resumen en datos/resumen.json y datos/resumen.csv")


if __name__ == "__main__":
    main()
