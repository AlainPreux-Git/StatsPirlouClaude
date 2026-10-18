#!/usr/bin/env python3
"""Régénère la webapp « Pirlouette – statistiques » à partir du wiki pirlouette.fr.

Étapes : télécharge les 3 pages (bals, animations, soirées privées) -> extrait
(type, date, lieu) -> retrouve les coordonnées (cache geocache.json, puis
géocodage des nouvelles communes) -> injecte les données dans template.html
-> écrit site/index.html.
"""
import datetime
import json
import pathlib
import re
import sys
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).parent
PAGES = {"b": "BalsFolk", "a": "Animations", "p": "SoireesPrivees"}
URL = "https://pirlouette.fr/pmwiki/pmwiki.php?n=Pirlouette.{}"
# Nominatim exige un User-Agent identifiable : mettez ici un contact réel.
HEADERS = {"User-Agent": "pirlouette-stats/1.0 (+https://github.com/AlainPreux-Git/StatsPirlouClaude)"}
UNKNOWN = "lieu non precise"

MONTHS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet",
          "aout", "septembre", "octobre", "novembre", "decembre"]
TYPOS = {"ocotbre": "octobre"}  # fautes de frappe connues du wiki
WEEKDAYS = r"(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)"
FLAGS = {"b": "B", "gb": "GB", "uk": "GB"}

# Variantes d'écriture du wiki -> clé normalisée du cache (voir norm()).
ALIASES = {
    "": UNKNOWN, "belgique": UNKNOWN, "le biset": UNKNOWN,
    "tounai": "tournai", "lomprez": "lompret", "ascq": "villeneuve d ascq",
    "villeneuved ascq": "villeneuve d ascq", "marcq en ostrevent": "marquette en ostrevant",
    "roselaere": "roulers|B", "lenik": "lennik|B", "brugges": "bruges|B",
    "lieven": "lievin", "mont noir": "saint jans cappel", "cassel cornemuses": "cassel",
    "annay sous lens": "annay", "flines les mortagnes": "flines les mortagne",
    "hellemmes lille": "hellemmes", "lille grand palais": "lille",
    "abbaye de clairmarais": "clairmarais", "saint andre": "saint andre les lille",
    "premesque": "premesques", "boulogne": "boulogne sur mer",
    "talmont": "talmont sur gironde", "versols": "versols et lapeyre",
    "rombies": "rombies et marchipont",
}


def strip_acc(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))


def norm(s):
    """Clé de comparaison : minuscules, sans accents ni ponctuation, St->Saint, lez->les."""
    s = strip_acc(s.lower()).replace("œ", "oe")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join({"st": "saint", "ste": "sainte", "lez": "les"}.get(w, w) for w in s.split())


def split_place(raw):
    """'Tournai (B)' -> ('Tournai', 'B', None) ; 'Lillers (62)' -> ('Lillers', None, '62')."""
    flag = dept = None

    def paren(m):
        nonlocal flag, dept
        v = m.group(1).strip().lower()
        if v in FLAGS:
            flag = FLAGS[v]
        elif v.isdigit():
            dept = v
        return " "

    name = re.sub(r"\(([^)]*)\)", paren, raw)
    name = re.sub(r"\*+|<[^>]+>|Attach:\S*", "", name)
    name = re.sub(r"^(?:et[eé]|hiver|printemps|automne)\s+\d{4}\W*", "", name, flags=re.I)
    return re.sub(r"\s+", " ", name).strip(" -–:|\t"), flag, dept


# ---------------------------------------------------------------- analyse du wiki
RX = re.compile(
    r"(?:(?P<d>\d{1,2}|1er)(?:\s*(?:et|au|/)\s*\d{1,2})?\s+)?"
    r"(?P<m>%s)\b\.?(?:\s+(?P<y>\d{3,4})(?!\d))?" % "|".join(MONTHS + list(TYPOS)),
    re.I,
)


def find_date(line):
    """Renvoie (lieu brut, jour|None, mois, année|None) ou None."""
    t = strip_acc(line).lower()
    m = RX.search(t)
    if not m:
        return None
    src = line if len(t) == len(line) else t
    place = re.sub(WEEKDAYS + r"\b", "", src[: m.start()], flags=re.I).strip()
    segs = [s.strip() for s in re.split(r"\s+[-–]\s*|\s*[-–]\s+", place) if s.strip()]
    d = m.group("d")
    day = None if not d else 1 if d.lower() == "1er" else int(d)
    mon = MONTHS.index(TYPOS.get(m.group("m"), m.group("m"))) + 1
    y = m.group("y")
    year = int(y) if y and len(y) == 4 else None
    if year and year > 2100:  # « 3018 » -> 2018
        year = 2000 + year % 1000
    return (segs[0] if segs else ""), day, mon, year


def parse_page(html, typ):
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find(id="wikitext") or soup.body
    out, prev_year, warn = [], None, []
    for part in re.split(r"<hr[^>]*>", str(root), flags=re.I):
        part = re.sub(r"<br\s*/?>|</?(?:p|div|li|tr|td|table|ul|h\d)[^>]*>", "\n", part, flags=re.I)
        text = BeautifulSoup(part, "html.parser").get_text("")
        best = None
        for line in text.splitlines():
            # « Nov 2012Lestrem - ... » : légende d'image collée au texte suivant
            for sub in re.sub(r"(?<=\d{4})(?=[A-Za-zÀ-ÿ])", "\n", line).split("\n"):
                r = find_date(sub)
                if r and (best is None or (best[1] is None and r[1] is not None)):
                    best = r
        if not best:
            continue
        place, day, mon, year = best
        if year is None:
            year = prev_year
            warn.append(f"année déduite ({year}) : {place!r} {day or ''}/{mon}")
        else:
            prev_year = year
        if not year or not 2000 <= year <= datetime.date.today().year + 2:
            warn.append(f"entrée ignorée (année invalide) : {place!r} {day}/{mon}/{year}")
            continue
        try:
            date = datetime.date(year, mon, day or 15)
        except ValueError:
            date = datetime.date(year, mon, 15)
        out.append((typ, date.isoformat(), place))
    return out, warn


def fetch(page):
    r = requests.get(URL.format(page), headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = "iso-8859-1"  # encodage déclaré par le wiki
    return r.text


# ---------------------------------------------------------------- géocodage
def geocode(name, flag, dept):
    """Renvoie (nom affiché, lat, lon) ou None. Jamais de résultat approximatif pour la France."""
    if not flag:
        r = requests.get("https://geo.api.gouv.fr/communes", headers=HEADERS, timeout=30, params={
            "nom": name, "fields": "nom,centre,codeDepartement", "boost": "population", "limit": 5})
        exact = [c for c in r.json() if norm(c["nom"]) == norm(name) and c.get("centre")]
        prefs = ([dept] if dept else []) + ["59", "62"]
        exact.sort(key=lambda c: prefs.index(c["codeDepartement"]) if c["codeDepartement"] in prefs else 99)
        if exact:
            lon, lat = exact[0]["centre"]["coordinates"]
            return exact[0]["nom"], round(lat, 3), round(lon, 3)
        return None
    time.sleep(1.1)  # politique d'usage de Nominatim : 1 requête/seconde
    r = requests.get("https://nominatim.openstreetmap.org/search", headers=HEADERS, timeout=30, params={
        "q": name, "format": "json", "limit": 1, "countrycodes": "be" if flag == "B" else "gb"})
    j = r.json()
    if j:
        return f"{name} ({flag})", round(float(j[0]["lat"]), 3), round(float(j[0]["lon"]), 3)
    return None


def resolve(raw, cache, unresolved):
    name, flag, dept = split_place(raw)
    k = norm(name)
    k = ALIASES.get(k, k)
    keys = [k] if "|" in k else ([f"{k}|{flag}"] if flag else [k, f"{k}|B", f"{k}|GB"])
    for key in keys:
        if key in cache:
            c = cache[key]
            return c["name"], c["lat"], c["lon"]
    res = None if "|" in k else geocode(name, flag, dept)
    if res:
        cache[keys[0]] = {"name": res[0], "lat": res[1], "lon": res[2]}
        print(f"  nouveau lieu géocodé : {res}")
        return res
    unresolved.add(raw)
    return name or "Lieu non précisé", None, None


# ---------------------------------------------------------------- génération
def build_data(events, cache):
    unresolved, groups = set(), {}
    for typ, date, raw in events:
        disp, lat, lon = resolve(raw, cache, unresolved)
        groups.setdefault((disp, lat, lon), set()).add(f"{typ}{date[2:4]}{date[5:7]}{date[8:10]}")
    D = [[n, la, lo, " ".join(sorted(c, key=lambda s: s[1:], reverse=True))]
         for (n, la, lo), c in sorted(groups.items(), key=lambda g: g[0][0])]
    return D, unresolved


def render(D):
    tpl = (ROOT / "template.html").read_text(encoding="utf-8")
    html = tpl.replace("__DATA__", json.dumps(D, ensure_ascii=False))
    html = html.replace("__UPDATED__", datetime.date.today().strftime("%d/%m/%Y"))
    out = ROOT / "site"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")


def main():
    cache_f, data_f = ROOT / "geocache.json", ROOT / "data.json"
    cache = json.loads(cache_f.read_text(encoding="utf-8"))
    events, warns = [], []
    for typ, page in PAGES.items():
        ev, w = parse_page(fetch(page), typ)
        print(f"{page}: {len(ev)} entrées")
        events += ev
        warns += w
    events = sorted(set(events))
    old = len(json.loads(data_f.read_text())) if data_f.exists() else 0
    if len(events) < 0.9 * old or len(events) < 100:
        sys.exit(f"ERREUR : {len(events)} entrées lues contre {old} avant ; le format du wiki a "
                 "probablement changé. Rien n'est publié.")
    D, unresolved = build_data(events, cache)
    render(D)
    cache_f.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    data_f.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
    for w in warns:
        print(f"::warning::{w}")
    for u in sorted(unresolved):
        print(f"::warning::lieu non localisé (ajoutez-le à geocache.json ou ALIASES) : {u!r}")
    print(f"OK : {len(events)} prestations, {len(D)} lieux, {len(unresolved)} non localisés.")


if __name__ == "__main__":
    main()
