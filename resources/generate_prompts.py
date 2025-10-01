#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_prompts.py

Durchsucht eine Musik-"Datenbank" (Ordnerstruktur) nach Künstlern, Alben (und optional Tracks)
und schreibt eine prompts.json im Format:
[
  {"text": "Artist, Album", "mode": "real"},
  {"text": "Artist, Album, Track", "mode": "real"},
  {"text": "Neuer Artist, Neues Album", "mode": "madeup_all"},
  {"text": "Artist(vert), Album(orig), Track(orig)", "mode": "switch_author"},
  {"text": "Artist(orig), Album(vert), Track(orig)", "mode": "switch_album"},
  {"text": "Artist(orig), Album(orig), Track(vert)", "mode": "switch_title"},
  ...
]

Standard-Pfade sind passend zur Struktur:
  resources/database/                        (Eingabe)
  resources/knowledge-base/prompts.json      (Ausgabe)

Beispiel:
  python generate_prompts.py
  python generate_prompts.py --db resources/database --out resources/knowledge-base/prompts.json --include-tracks
  python generate_prompts.py --synthetic 0  # keine synthetischen Einträge

Tipps:
- Track-Dateinamen werden zu sauberen Titeln normalisiert (Numerierung/Endungen entfernt).
- Wenn keine Tracks gefunden werden, wird wenigstens "Künstler, Album" geschrieben.
- Zusätzlich können synthetische Prompts generiert werden, die in 'mode' dokumentieren, was verändert/erfunden wurde.
"""

from __future__ import annotations
import argparse
import json
import random
import re
from pathlib import Path
from typing import Dict, Iterable, List, Tuple, Set

# --- Helpers -----------------------------------------------------------------

# Wir brauchen KEINE Whitelist an Endungen mehr.
# Stattdessen ignorieren wir nur typische "Nicht-Track"-Endungen.
IGNORE_FILE_EXTS = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff",
    ".pdf", ".cue", ".log", ".nfo", ".sfv", ".md5", ".sha1",
    ".txt", ".rtf", ".doc", ".docx",
    ".m3u", ".m3u8", ".pls", ".url", ".ini", ".db", ".json", ".xml",
    ".zip", ".rar", ".7z"
}

# Ordnernamen, die i. d. R. keine Tracks sind
IGNORE_DIR_NAMES = {
    "scan", "scans", "art", "artwork", "cover", "covers", "booklet",
    "lyrics", "subtitles", "subs", "extras", "bonus",
    "poster", "posters", "images", "pics",
    "dvd", "bd", "bluray", "blu-ray", "video", "videos"
}

DISC_DIR_PATTERN = re.compile(r"^(cd|disc|disk|platte|scheibe)\s*[_\-\s\.]*\d{1,2}$", re.IGNORECASE)

def clean_name(name: str) -> str:
    """Normalisiere Ordner-/Dateinamen zu lesbaren Titeln."""
    base = name
    base = base.replace("_", " ")
    base = re.sub(r"\s+", " ", base).strip()
    # führende Tracknummern entfernen (01-, 1., 001 )
    base = re.sub(r"^[\s\-_.()]*\d{1,3}[\s\-_.)(]+", "", base).strip()
    # trailing Trennzeichen entfernen
    base = re.sub(r"[\s\-_.]+$", "", base).strip()
    return base

def iter_artists_albums(db_root: Path) -> Iterable[Tuple[str, str, Path]]:
    """Erwartet Struktur: <db_root>/<Letter>/<Artist>/<Album>"""
    if not db_root.exists():
        return
    for letter_dir in sorted([p for p in db_root.iterdir() if p.is_dir()]):
        for artist_dir in sorted([p for p in letter_dir.iterdir() if p.is_dir()]):
            artist = clean_name(artist_dir.name)
            if not artist:
                continue
            for album_dir in sorted([p for p in artist_dir.iterdir() if p.is_dir()]):
                album = clean_name(album_dir.name)
                if not album:
                    continue
                yield (artist, album, album_dir)

def _iter_tracks_recursive(album_dir: Path, max_depth: int) -> Iterable[str]:
    """
    Durchsucht album_dir bis max_depth Ebenen tief nach Tracks.
    Nimmt:
      - Dateien, außer sie haben typische Nicht-Track-Endungen (IGNORE_FILE_EXTS)
      - Unterordner als Track (falls der Ordnername nicht "Beifang" ist)
    """
    try:
        entries = sorted(album_dir.iterdir())
    except PermissionError:
        return

    for p in entries:
        name_lower = p.name.lower()
        if name_lower.startswith("."):
            continue

        if p.is_file():
            # Hinweis: Hier könnte man optional Dateiendungen filtern.
            title = clean_name(p.stem if p.suffix else p.name)
            if title:
                yield title

        elif p.is_dir():
            nice = clean_name(p.name)
            if not nice:
                continue

            # offensichtliche Nicht-Track-Container ignorieren
            if nice.lower() in IGNORE_DIR_NAMES:
                continue

            # "CD1", "Disc 2", ... dürfen wir betreten, zählen aber nicht als eigener Track
            if DISC_DIR_PATTERN.match(nice):
                if max_depth > 0:
                    yield from _iter_tracks_recursive(p, max_depth - 1)
                continue

            # Manche Sammlungen: jeder Track ist ein Ordner
            # -> Den Ordnernamen selbst als Tracktitel verwenden
            yield nice

            # Falls darin wiederum tatsächliche Dateien liegen (z. B. Lyrics.txt),
            # macht zusätzliche Tiefe oft nur Lärm. Deshalb nur
            # bei noch vorhandener Tiefe weiterlaufen.
            if max_depth > 0:
                yield from _iter_tracks_recursive(p, max_depth - 1)

def find_tracks(album_dir: Path, max_depth: int = 2) -> List[str]:
    """Finde Track-(Dateien/Ordner) unterhalb eines Albums und liefere bereinigte Titelnamen."""
    tracks_set: Set[str] = set()
    for t in _iter_tracks_recursive(album_dir, max_depth=max_depth):
        if t:
            tracks_set.add(t)
    return sorted(tracks_set, key=lambda s: s.casefold())

# --- Synthetic text helpers ---------------------------------------------------

_ADJECTIVES = [
    "Silent", "Electric", "Neon", "Golden", "Velvet", "Crystal", "Midnight",
    "Emerald", "Fading", "Endless", "Digital", "Wandering", "Aurora", "Paper",
    "Fever", "Hollow", "Broken", "Hidden", "Crimson", "Silver"
]
_NOUNS = [
    "Echoes", "Horizons", "Dreams", "Parade", "Skylines", "Waves", "Rooms",
    "Stories", "Patterns", "Fragments", "Gardens", "Signals", "Shadows",
    "Lights", "Halos", "Fables", "Letters", "Windows", "Scenes", "Motors"
]
_FIRSTNAMES = [
    "Luna", "Milo", "Aria", "Noah", "Ivy", "Eli", "Nora", "Levi", "Mira",
    "Ezra", "Zoe", "Kai", "Lena", "Theo", "Ava", "Rio", "Enzo", "Mina", "Juno", "Remy"
]
_SURNAMES = [
    "Hayes", "Monroe", "Valen", "Sato", "Russo", "Kline", "Archer", "Lopez",
    "Nguyen", "Khan", "Silva", "Rossi", "Bauer", "Weiss", "Fischer", "Moreau",
    "Jensen", "Kovac", "Ishida", "Novak"
]
_BANDS_SUFFIX = ["Trio", "Quartet", "Collective", "Project", "Club", "Ensemble", "Band", "Orchestra"]

def _random_artist_name() -> str:
    # Mischtyp: Solo oder Band
    if random.random() < 0.5:
        return f"{random.choice(_FIRSTNAMES)} {random.choice(_SURNAMES)}"
    else:
        return f"{random.choice(_ADJECTIVES)} {random.choice(_NOUNS)} {random.choice(_BANDS_SUFFIX)}"

def _random_album_title() -> str:
    if random.random() < 0.6:
        return f"{random.choice(_ADJECTIVES)} {random.choice(_NOUNS)}"
    else:
        return f"{random.choice(_NOUNS)} of {random.choice(_NOUNS)}"

def _random_track_title() -> str:
    patterns = [
        lambda: f"{random.choice(_ADJECTIVES)} {random.choice(_NOUNS)}",
        lambda: f"{random.choice(_NOUNS)} #{random.randint(2, 99)}",
        lambda: f"{random.choice(['Intro','Interlude','Prelude','Epilogue'])}",
        lambda: f"{random.choice(['Blue','Red','White','Black','Green'])} {random.choice(['Room','Line','Sky','Light','River'])}",
    ]
    return random.choice(patterns)()

# --- Main --------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generiert prompts.json aus Musik-Datenbank (+ optionale synthetische Prompts).")
    parser.add_argument("--db", dest="db_root", default="database", help="Pfad zur Datenbank-Wurzel (Default: database)")
    parser.add_argument("--out", dest="out_path", default="knowledge-base/prompts.json", help="Ziel-Datei (Default: knowledge-base/prompts.json)")
    parser.add_argument("--include-tracks", action="store_true", help="Zusätzlich pro Track einen Prompt erzeugen")
    parser.add_argument("--only-tracks", action="store_true", help="Nur Track-Prompts schreiben (keine reinen Album-Prompts)")
    parser.add_argument("--dry-run", action="store_true", help="Nur Ausgabe auf STDOUT, nicht schreiben")
    parser.add_argument("--synthetic", type=int, default=500, help="Anzahl zusätzlich zu generierender synthetischer Prompts (Default: 500; 0 zum Deaktivieren)")
    parser.add_argument("--max-depth", type=int, default=2, help="Rekursionstiefe für Track-Suche (Default: 2)")
    # NEU: finale Begrenzung mit fairer Verteilung über 'mode'
    parser.add_argument("--limit", type=int, default=200, help="Maximale Anzahl finaler Prompts, gleichmäßig über 'mode' verteilt (Default: 200; 0=keine Begrenzung)")
    args = parser.parse_args()

    random.seed(42)  # deterministischer Default

    db_root = Path(args.db_root).resolve()
    out_path = Path(args.out_path)

    prompts: List[Dict[str, str]] = []
    seen: Set[str] = set()

    # Sammler für spätere Permutations-Strategien
    artists: Set[str] = set()
    albums_by_artist: Dict[str, Set[str]] = {}
    tracks_by_key: Dict[Tuple[str, str], List[str]] = {}

    print("Root: " + str(db_root))
    # --- Real prompts einsammeln ---
    for artist, album, album_path in iter_artists_albums(db_root):
        artists.add(artist)
        albums_by_artist.setdefault(artist, set()).add(album)

        tracks = find_tracks(album_path, max_depth=args.max_depth)

        if tracks:
            tracks_by_key[(artist, album)] = tracks
            for t in tracks:
                txt = f"{artist}, {album}, {t}"
                if txt not in seen:
                    prompts.append({"text": txt, "mode": "real"})
                    seen.add(txt)
        else:
            # Nur wenn KEIN Track existiert, schreibe Artist/Album
            if not args.only_tracks:
                txt = f"{artist}, {album}"
                if txt not in seen:
                    prompts.append({"text": txt, "mode": "real"})
                    seen.add(txt)

    # flache Listen für Zufallsauswahl
    all_albums: List[Tuple[str, str]] = [(a, alb) for a, albs in albums_by_artist.items() for alb in albs]
    all_tracks: List[Tuple[str, str, str]] = []
    for (a, alb), ts in tracks_by_key.items():
        for t in ts:
            all_tracks.append((a, alb, t))

    # --- Synthetische Prompts generieren ---
    def add_prompt(text: str, mode: str) -> bool:
        if not text or text in seen:
            return False
        prompts.append({"text": text, "mode": mode})
        seen.add(text)
        return True

    def make_madeup() -> bool:
        artist = _random_artist_name()
        album = _random_album_title()
        if random.random() < 0.7:
            title = _random_track_title()
            return add_prompt(f"{artist}, {album}, {title}", "madeup_all")
        else:
            return add_prompt(f"{artist}, {album}", "madeup_all")

    def make_switch_author() -> bool:
        # Nutze existierendes (Album[, Track]) aber setze anderen Artist
        if not all_albums or len(artists) < 2:
            return False
        src_artist, src_album = random.choice(all_albums)
        candidates = list(artists - {src_artist})
        if not candidates:
            return False
        new_artist = random.choice(candidates)
        tracks = tracks_by_key.get((src_artist, src_album), [])
        if tracks and random.random() < 0.8:
            title = random.choice(tracks)
            return add_prompt(f"{new_artist}, {src_album}, {title}", "switch_author")
        else:
            return add_prompt(f"{new_artist}, {src_album}", "switch_author")

    def make_switch_album() -> bool:
        # Nutze existierenden Artist und (Track), aber anderes Album
        if not all_albums:
            return False
        src_artist, src_album = random.choice(all_albums)
        other = random.choice([pair for pair in all_albums if pair != (src_artist, src_album)])
        new_album = other[1]
        tracks = tracks_by_key.get((src_artist, src_album), [])
        if tracks and random.random() < 0.8:
            title = random.choice(tracks)
            return add_prompt(f"{src_artist}, {new_album}, {title}", "switch_album")
        else:
            return add_prompt(f"{src_artist}, {new_album}", "switch_album")

    def make_switch_title() -> bool:
        # Nutze existierenden Artist/Album mit *anderem* existierenden oder erfundenen Titel
        if not all_albums:
            return False
        src_artist, src_album = random.choice(all_albums)
        existing_tracks = tracks_by_key.get((src_artist, src_album), [])
        new_title = None
        if all_tracks and random.random() < 0.7:
            a2, al2, t2 = random.choice([t for t in all_tracks if not (t[0] == src_artist and t[1] == src_album)])
            new_title = t2
        else:
            tries = 0
            while tries < 5:
                cand = _random_track_title()
                if cand not in existing_tracks:
                    new_title = cand
                    break
                tries += 1
            if new_title is None:
                new_title = _random_track_title()
        return add_prompt(f"{src_artist}, {src_album}, {new_title}", "switch_title")

    synthetic_target = max(0, args.synthetic)
    made = 0
    attempts = 0
    makers = [make_madeup, make_switch_author, make_switch_album, make_switch_title]

    while made < synthetic_target and attempts < synthetic_target * 20:
        attempts += 1
        maker = random.choice(makers)
        if maker():
            made += 1

    # --- Downsampling (gleichmäßig über 'mode') -------------------------------
    if args.limit and args.limit > 0 and len(prompts) > args.limit:
        from collections import defaultdict
        grouped = defaultdict(list)
        for p in prompts:
            grouped[p["mode"]].append(p)

        rng = random.Random(42)
        modes = sorted(grouped.keys())
        for m in modes:
            rng.shuffle(grouped[m])

        selected: List[Dict[str, str]] = []
        indices = {m: 0 for m in modes}

        while len(selected) < args.limit and any(indices[m] < len(grouped[m]) for m in modes):
            for m in modes:
                if len(selected) >= args.limit:
                    break
                i = indices[m]
                if i < len(grouped[m]):
                    selected.append(grouped[m][i])
                    indices[m] += 1

        prompts = selected

    # --- Sortierung stabil nach Text, JSON schreiben --------------------------
    prompts.sort(key=lambda x: x["text"].casefold())
    output_json = json.dumps(prompts, ensure_ascii=False, indent=2)

    if args.dry_run:
        print(output_json)
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output_json, encoding="utf-8")
    print(f"Wrote {len(prompts)} prompts (incl. {made} synthetic) -> {out_path}")

if __name__ == "__main__":
    main()
