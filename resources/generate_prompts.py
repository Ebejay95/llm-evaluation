#!/usr/bin/env python3
"""
generate_prompts.py

Durchsucht eine Musik-"Datenbank" (Ordnerstruktur) nach Künstlern, Alben (und optional Tracks)
und schreibt eine prompts.json im Format:
[
  {"text": "Artist, Album", "mode": "real"},
  {"text": "Artist, Album, Track", "mode": "real"},
  {"text": "Erfundener Artist, Erfundenes Album[, Track]", "mode": "madeup_all"},
  {"text": "Falscher Artist, Echtes Album[, Track]", "mode": "switch_author"},
  {"text": "Echter Artist, Falsches Album[, Track]", "mode": "switch_album"},
  {"text": "Echter Artist, Echtes Album, Falscher Titel", "mode": "switch_title"}
]

Standard-Pfade:
  database/                        (Eingabe)
  knowledge-base/prompts.json      (Ausgabe)

Beispiele:
  python generate_prompts.py
  python generate_prompts.py --include-tracks
  python generate_prompts.py --synthetic-per-mode 50
  python generate_prompts.py --madeup-all 0 --switch-author 500  # nur switch_author 500x
  python generate_prompts.py --no-synthetic  # nur 'real'
"""

from __future__ import annotations
import argparse
import json
import random
import re
from pathlib import Path
from typing import Dict, Iterable, List, Tuple, Set

# --- Helpers -----------------------------------------------------------------

VALID_TRACK_EXTS = {
    ".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".wma",
    ".txt", ".md", ".json"  # falls Tracklisten als Textdateien o.ä. abgelegt sind
}

def clean_name(name: str) -> str:
    """Normalisiere Ordner-/Dateinamen zu lesbaren Titeln."""
    base = name
    base = base.replace("_", " ")
    base = re.sub(r"\s+", " ", base).strip()
    base = re.sub(r"^[\s\-_.()]*\d{1,3}[\s\-_.)(]+", "", base).strip()
    base = re.sub(r"[\s\-_.]+$", "", base).strip()
    return base

def iter_artists_albums(db_root: Path) -> Iterable[Tuple[str, str, Path]]:
    """
    Liefert (artist, album, album_path).
    Erwartet grob: <db_root>/<Letter>/<Artist>/<Album>/...
    Funktioniert aber auch mit generischen Ebenen letter->artist->album.
    """
    if not db_root.exists():
        return
    for letter_dir in sorted([p for p in db_root.iterdir() if p.is_dir()]):
        for artist_dir in sorted([p for p in letter_dir.iterdir() if p.is_dir()]):
            artist = clean_name(artist_dir.name)
            for album_dir in sorted([p for p in artist_dir.iterdir() if p.is_dir()]):
                album = clean_name(album_dir.name)
                yield (artist, album, album_dir)

def find_tracks(album_dir: Path) -> List[str]:
    """Finde Trackdateien unterhalb eines Albums und liefere bereinigte Titelnamen."""
    tracks: List[str] = []
    try:
        entries = sorted(album_dir.iterdir())
    except PermissionError:
        return tracks
    for p in entries:
        if p.is_file() and p.suffix.lower() in VALID_TRACK_EXTS:
            title = clean_name(p.stem if p.suffix else p.name)
            if title:
                tracks.append(title)
    return tracks

# --- Synthetic text helpers ---------------------------------------------------

_ADJECTIVES = [
    "Silent","Electric","Neon","Golden","Velvet","Crystal","Midnight","Emerald","Fading",
    "Endless","Digital","Wandering","Aurora","Paper","Fever","Hollow","Broken","Hidden",
    "Crimson","Silver"
]
_NOUNS = [
    "Echoes","Horizons","Dreams","Parade","Skylines","Waves","Rooms","Stories","Patterns",
    "Fragments","Gardens","Signals","Shadows","Lights","Halos","Fables","Letters","Windows",
    "Scenes","Motors"
]
_FIRSTNAMES = [
    "Luna","Milo","Aria","Noah","Ivy","Eli","Nora","Levi","Mira","Ezra","Zoe","Kai","Lena",
    "Theo","Ava","Rio","Enzo","Mina","Juno","Remy"
]
_SURNAMES = [
    "Hayes","Monroe","Valen","Sato","Russo","Kline","Archer","Lopez","Nguyen","Khan","Silva",
    "Rossi","Bauer","Weiss","Fischer","Moreau","Jensen","Kovac","Ishida","Novak"
]
_BANDS_SUFFIX = ["Trio","Quartet","Collective","Project","Club","Ensemble","Band","Orchestra"]

def _random_artist_name() -> str:
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
    parser = argparse.ArgumentParser(description="Generiert prompts.json aus Musik-Datenbank (+ synthetische Prompts je Modus).")
    parser.add_argument("--db", dest="db_root", default="database", help="Pfad zur Datenbank-Wurzel (Default:database)")
    parser.add_argument("--out", dest="out_path", default="knowledge-base/prompts.json", help="Ziel-Datei (Default: knowledge-base/prompts.json)")
    parser.add_argument("--include-tracks", action="store_true", help="Zusätzlich pro Track einen Prompt erzeugen")
    parser.add_argument("--only-tracks", action="store_true", help="Nur Track-Prompts schreiben (keine reinen Album-Prompts)")
    parser.add_argument("--dry-run", action="store_true", help="Nur Ausgabe auf STDOUT, nicht schreiben")

    # Steuerung der synthetischen Mengen
    parser.add_argument("--synthetic-per-mode", type=int, default=200, help="Standardanzahl je Modus (Default: 200)")
    parser.add_argument("--madeup-all", type=int, default=None, help="Anzahl für madeup_all (überschreibt --synthetic-per-mode)")
    parser.add_argument("--switch-author", type=int, default=None, help="Anzahl für switch_author (überschreibt --synthetic-per-mode)")
    parser.add_argument("--switch-album", type=int, default=None, help="Anzahl für switch_album (überschreibt --synthetic-per-mode)")
    parser.add_argument("--switch-title", type=int, default=None, help="Anzahl für switch_title (überschreibt --synthetic-per-mode)")
    parser.add_argument("--no-synthetic", action="store_true", help="Keine synthetischen Prompts erzeugen")

    args = parser.parse_args()

    random.seed(42)  # deterministischer Default für reproduzierbare Sets

    db_root = Path(args.db_root).resolve()
    out_path = Path(args.out_path)

    prompts: List[Dict[str, str]] = []
    seen: Set[str] = set()

    # Sammler für Permutations-Strategien (nur aus DB!)
    artists: Set[str] = set()
    albums_by_artist: Dict[str, Set[str]] = {}
    tracks_by_key: Dict[Tuple[str, str], List[str]] = {}

    # --- Real prompts einsammeln ---
    for artist, album, album_path in iter_artists_albums(db_root):
        artists.add(artist)
        albums_by_artist.setdefault(artist, set()).add(album)

        tracks = find_tracks(album_path) if args.include-tracks or args.only_tracks else []
        if args.include_tracks or args.only_tracks:
            if tracks:
                tracks_by_key[(artist, album)] = tracks
            wrote_any = False
            for t in tracks:
                txt = f"{artist}, {album}, {t}"
                if txt not in seen:
                    prompts.append({"text": txt, "mode": "real"})
                    seen.add(txt)
                    wrote_any = True
            if not args.only_tracks and not wrote_any:
                txt = f"{artist}, {album}"
                if txt not in seen:
                    prompts.append({"text": txt, "mode": "real"})
                    seen.add(txt)
        else:
            txt = f"{artist}, {album}"
            if txt not in seen:
                prompts.append({"text": txt, "mode": "real"})
                seen.add(txt)

    # flache Listen für Zufallsauswahl (nur DB-basiert!)
    all_albums: List[Tuple[str, str]] = [(a, alb) for a, albs in albums_by_artist.items() for alb in albs]
    all_tracks: List[Tuple[str, str, str]] = []
    for (a, alb), ts in tracks_by_key.items():
        for t in ts:
            all_tracks.append((a, alb, t))

    # --- Synthetische Prompts -------------------------------------------------
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
        # wähle echtes Album (und ggf. echten Track), setze anderen echten Artist aus DB
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
        # wähle echten Artist, kombiniere mit *anderem echten* Album aus DB
        if not all_albums:
            return False
        src_artist, src_album = random.choice(all_albums)
        candidates = [pair for pair in all_albums if pair != (src_artist, src_album)]
        if not candidates:
            return False
        new_album = random.choice(candidates)[1]
        tracks = tracks_by_key.get((src_artist, src_album), [])
        if tracks and random.random() < 0.8:
            title = random.choice(tracks)
            return add_prompt(f"{src_artist}, {new_album}, {title}", "switch_album")
        else:
            return add_prompt(f"{src_artist}, {new_album}", "switch_album")

    def make_switch_title() -> bool:
        # wähle echtes (Artist, Album) und kombiniere mit *anderem echten* Titel aus DB (oder generiere einen)
        if not all_albums:
            return False
        src_artist, src_album = random.choice(all_albums)
        existing_tracks = set(tracks_by_key.get((src_artist, src_album), []))
        new_title = None
        # bevorzuge andere echte Titel aus DB
        other_db_titles = [t for (a2, al2, t) in all_tracks if not (a2 == src_artist and al2 == src_album)]
        if other_db_titles:
            # nimm einen, der nicht identisch ist
            new_title = random.choice(other_db_titles)
        else:
            # fallback: generiere, vermeide vorhandene Titel falls möglich
            tries = 0
            while tries < 7:
                cand = _random_track_title()
                if cand not in existing_tracks:
                    new_title = cand
                    break
                tries += 1
            if new_title is None:
                new_title = _random_track_title()
        return add_prompt(f"{src_artist}, {src_album}, {new_title}", "switch_title")

    # Zielmengen festlegen
    if args.no_synthetic:
        targets = {"madeup_all": 0, "switch_author": 0, "switch_album": 0, "switch_title": 0}
    else:
        per = max(0, args.synthetic_per_mode)
        targets = {
            "madeup_all": per if args.madeup_all is None else max(0, args.madeup_all),
            "switch_author": per if args.switch_author is None else max(0, args.switch_author),
            "switch_album": per if args.switch_album is None else max(0, args.switch_album),
            "switch_title": per if args.switch_title is None else max(0, args.switch_title),
        }

    makers = {
        "madeup_all": make_madeup,
        "switch_author": make_switch_author,
        "switch_album": make_switch_album,
        "switch_title": make_switch_title,
    }

    # Erzeuge je Modus exakt die Zielmenge (sofern DB genug hergibt)
    for mode, target in targets.items():
        made = 0
        attempts = 0
        # großzügiges Limit, falls viele Duplikate rausfallen
        max_attempts = target * 30 if target > 0 else 0
        while made < target and attempts < max_attempts:
            attempts += 1
            if makers[mode]():
                made += 1
        # Hinweis in Konsole, falls Ziel nicht erreicht
        if target > 0 and made < target:
            print(f"[WARN] {mode}: nur {made}/{target} generiert (evtl. zu wenig DB-Kombinationen).")

    # --- Sortierung & Ausgabe -------------------------------------------------
    prompts.sort(key=lambda x: x["text"].lower())
    output_json = json.dumps(prompts, ensure_ascii=False, indent=2)

    if args.dry_run:
        print(output_json)
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output_json, encoding="utf-8")
    print(f"Wrote {len(prompts)} prompts "
          f"(madeup_all={targets['madeup_all']}, switch_author={targets['switch_author']}, "
          f"switch_album={targets['switch_album']}, switch_title={targets['switch_title']}) -> {out_path}")

if __name__ == "__main__":
    main()
