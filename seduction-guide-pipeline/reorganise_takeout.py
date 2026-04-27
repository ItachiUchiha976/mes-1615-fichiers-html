#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REORGANISATION GOOGLE TAKEOUT - WINDOWS 10
==========================================
SCRIPT 1 SUR 2 - A lancer AVANT windows_transcribe_api.py

Ce script nettoie la structure desordonnee de Google Takeout :
  1. DEPLACE (pas copie) les fichiers -> zero espace supplementaire
  2. Supprime les JSON inutiles
  3. Convertit les sous-titres VTT/SRT YouTube en texte pur (.txt)
  4. Corrige les noms de fichiers (supprime ".mp4" embedi dans les noms)
  5. Reorganise par module/dossier dans une structure propre

APRES ce script : lance windows_transcribe_api.py sur le dossier SORTIE

AUCUNE INSTALLATION REQUISE (bibliotheques standard Python uniquement)
USAGE : Double-clique sur ce fichier
"""

import re
import shutil
import sys
from pathlib import Path
from datetime import datetime


# ================================================================================
#  CONFIGURATION
# ================================================================================

KEEP_EXT = {
    ".mp4", ".avi", ".mov", ".mkv", ".webm", ".mpeg", ".m4v", ".flv", ".wmv",
    ".mp3", ".wav", ".aac", ".ogg", ".wma", ".m4a", ".opus", ".flac",
    ".pdf", ".docx", ".doc", ".pptx", ".ppt",
    ".txt", ".md", ".srt", ".vtt", ".sbv",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",
}
DELETE_EXT = {".json"}

SUBTITLE_KEYWORDS = [
    "sous-tit", "sous_tit", "subtitle", "subtitles",
    "transcription", "transcript", "caption", "captions",
    "-tit.", "_tit.", "sous-titres",
]

# Extensions media qui peuvent etre embarquees dans le stem d'un sous-titre
# Ex: "video.mp4-sous-tit.txt" -> le stem contient ".mp4"
MEDIA_EXT_IN_STEM = [
    ".mp4", ".avi", ".mov", ".mkv", ".webm", ".mpeg", ".m4v", ".flv", ".wmv",
    ".mp3", ".wav", ".aac", ".m4a", ".ogg", ".wma", ".opus", ".flac",
]

# ================================================================================


def demander_dossier(titre):
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        d = filedialog.askdirectory(title=titre)
        root.destroy()
        return Path(d) if d else None
    except Exception:
        return None


def natural_key(name):
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", name)]


def est_sous_titre(filename):
    name_lower = filename.lower()
    if any(kw in name_lower for kw in SUBTITLE_KEYWORDS):
        return True
    return Path(filename).suffix.lower() in {".srt", ".vtt", ".sbv"}


def nettoyer_vtt(content):
    """
    Convertit VTT/SRT YouTube en texte pur lisible.
    Gere :
      - Les horodatages mot par mot : Okay,<00:00:00.560><c> so</c>...
      - Les phrases repetees en double
      - Les entetes WEBVTT, Kind:, Language:
    """
    lines = content.splitlines()
    texte_pur = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.match(r"^(WEBVTT|NOTE|STYLE|Kind:|Language:)", line):
            continue
        if re.match(r"^\d+$", line):
            continue
        if re.match(r"\d{1,2}:\d{2}:\d{2}[,\.]\d{3}\s*-->", line):
            continue
        if re.match(r"\d{1,2}:\d{2}[,\.]\d{3}\s*-->", line):
            continue
        # Ignorer les lignes karaoke VTT (<00:00:xx> dans la ligne)
        if "<" in line and re.search(r"<\d{2}:\d{2}", line):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = re.sub(r"\{[^}]+\}", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            texte_pur.append(line)

    if not texte_pur:
        return ""

    # Dedupliquer les repetitions du VTT YouTube
    result = []
    prev = ""
    for line in texte_pur:
        n = line.lower().strip()
        p = prev.lower().strip()
        if n == p:
            continue
        if p.startswith(n) and len(n) > 10:
            continue
        result.append(line)
        prev = line

    return " ".join(result)


def nettoyer_nom(name):
    """
    Nettoie le nom d'un fichier de sous-titres :
    1. Supprime le mot-cle de sous-titres (ex: "-sous-tit", "-sous-titres")
    2. Supprime l'extension media embarquee dans le stem
       Ex: "1. Video.mp4-sous-tit.txt"
           -> stem = "1. Video.mp4"  (apres suppression du mot-cle)
           -> stem = "1. Video"      (apres suppression de ".mp4")
    3. Tronque a 120 chars
    4. Supprime les caracteres invalides Windows
    """
    stem = Path(name).stem
    ext  = Path(name).suffix

    # Etape 1 : supprimer le mot-cle sous-titres
    for kw in SUBTITLE_KEYWORDS:
        if kw in stem.lower():
            idx = stem.lower().find(kw)
            if idx > 3:
                stem = stem[:idx].rstrip(" -_.")
            break

    # Etape 2 : supprimer l'extension media eventuellement encore dans le stem
    # Ex: "1. Leveling Explained - The System.mp4" -> "1. Leveling Explained - The System"
    for media_ext in MEDIA_EXT_IN_STEM:
        if stem.lower().endswith(media_ext):
            stem = stem[:len(stem) - len(media_ext)].rstrip(" -_.")
            break

    # Etape 3 : tronquer
    if len(stem) > 120:
        stem = stem[:120].rstrip()

    # Etape 4 : caracteres invalides Windows
    stem = re.sub(r'[<>:"/\\|?*]', '_', stem)

    return stem + ext


def nettoyer_nom_simple(name):
    """Nettoyage simple pour les fichiers non-sous-titres (tronque + invalides)."""
    stem = Path(name).stem
    ext  = Path(name).suffix
    if len(stem) > 120:
        stem = stem[:120].rstrip()
    stem = re.sub(r'[<>:"/\\|?*]', '_', stem)
    return stem + ext


def trouver_module_parent(file_path, racine):
    """Retourne le nom du dossier parent direct du fichier."""
    try:
        parts = file_path.relative_to(racine).parts
        return parts[-2] if len(parts) >= 2 else "Racine"
    except ValueError:
        return file_path.parent.name


def main():
    print("\n" + "=" * 70)
    print("  SCRIPT 1/2 : REORGANISATION GOOGLE TAKEOUT")
    print("=" * 70)
    print("\nCe script va :")
    print("  1. Scanner la formation Google Takeout")
    print("  2. DEPLACER (pas copier) les fichiers -> zero espace supplementaire")
    print("  3. Supprimer tous les .json inutiles")
    print("  4. Nettoyer les sous-titres VTT en texte pur lisible")
    print("  5. Corriger les noms (supprimer '.mp4' embedi dans les noms txt)")
    print("\nLance ensuite : windows_transcribe_api.py sur le dossier SORTIE\n")

    print("ETAPE 1 : Dossier SOURCE (le desordre Google Takeout)")
    print("          Ex: D:\\Le Systeme de Todd Valentine\n")
    source = demander_dossier("SCRIPT 1 - Dossier SOURCE (Google Takeout)")
    if not source or not source.exists():
        print("Annule.")
        input("Entree pour fermer...")
        sys.exit(0)
    print(f"Source : {source}\n")

    print("ETAPE 2 : Dossier SORTIE (propre)")
    print("          Ex: D:\\Todd_Propre\n")
    sortie = demander_dossier("SCRIPT 1 - Dossier SORTIE (propre)")
    if not sortie:
        sortie = source.parent / (source.name + "_PROPRE")
        print(f"Sortie auto : {sortie}")
    sortie.mkdir(parents=True, exist_ok=True)
    print(f"Sortie : {sortie}\n")

    # Scan
    print("Scan en cours...\n")
    tous = [f for f in source.rglob("*") if f.is_file()]

    compteur = {}
    for f in tous:
        ext = f.suffix.lower() if f.suffix else "(aucune)"
        compteur[ext] = compteur.get(ext, 0) + 1

    print("=" * 70)
    print("  FICHIERS TROUVES")
    print("=" * 70)
    print(f"  {'Extension':<20} {'Nombre':>8}    {'Action'}")
    print(f"  {'-'*20} {'-'*8}    {'-'*30}")
    for ext, nb in sorted(compteur.items(), key=lambda x: -x[1]):
        if ext in DELETE_EXT:   action = "SUPPRIME"
        elif ext in KEEP_EXT:   action = "DEPLACE"
        else:                   action = "ignore"
        print(f"  {ext:<20} {nb:>8}    {action}")
    print("=" * 70 + "\n")

    sous_titres = [f for f in tous if f.suffix.lower() in KEEP_EXT and est_sous_titre(f.name)]
    videos = [f for f in tous if f.suffix.lower() in {".mp4",".avi",".mov",".mkv",".webm",".m4v"}]
    audios = [f for f in tous if f.suffix.lower() in {".mp3",".wav",".aac",".m4a",".ogg",".flac"}]

    print("=" * 70)
    print("  ANALYSE")
    print("=" * 70)
    print(f"  Videos          : {len(videos)}")
    print(f"  Audios          : {len(audios)}")
    print(f"  Sous-titres/TXT : {len(sous_titres)}")

    if sous_titres:
        print(f"\n  {len(sous_titres)} sous-titres detectes.")
        print(f"  -> Conserves comme reference, mais les videos seront quand meme")
        print(f"     transcrites en ENTIER via Whisper API (completude garantie).")
        print(f"\n  Exemples :")
        for st in sous_titres[:5]:
            print(f"    {st.name}")
        if len(sous_titres) > 5:
            print(f"    ... et {len(sous_titres)-5} autres")

    print("=" * 70 + "\n")

    reponse = input("Reorganiser maintenant ? (oui / non) : ").strip().lower()
    if reponse not in ("oui", "o", "yes", "y"):
        sys.exit(0)

    print("\nReorganisation (deplacement) en cours...\n")

    # Grouper par module
    modules = {}
    for f in tous:
        ext = f.suffix.lower()
        if ext in DELETE_EXT:
            try:
                f.unlink()
            except Exception:
                pass
            continue
        if ext not in KEEP_EXT:
            continue
        mod = trouver_module_parent(f, source)
        modules.setdefault(mod, []).append(f)

    ok = 0
    log_lignes = []

    for module in sorted(modules.keys(), key=natural_key):
        fichiers = sorted(modules[module], key=lambda f: natural_key(f.name))
        mod_dir = sortie / module
        mod_dir.mkdir(parents=True, exist_ok=True)
        print(f"  [{module}] -> {len(fichiers)} fichier(s)")

        for f in fichiers:
            # Choisir le bon nettoyage de nom
            if est_sous_titre(f.name) or f.suffix.lower() in {".srt", ".vtt", ".sbv"}:
                nouveau_nom = nettoyer_nom(f.name)
                # Forcer extension .txt pour les sous-titres
                nouveau_nom = str(Path(nouveau_nom).with_suffix(".txt"))
            else:
                nouveau_nom = nettoyer_nom_simple(f.name)

            dest = mod_dir / nouveau_nom
            # Gerer les collisions
            n = 1
            base = Path(dest)
            while dest.exists():
                dest = base.parent / f"{base.stem}_{n}{base.suffix}"
                n += 1

            try:
                if est_sous_titre(f.name) or f.suffix.lower() in {".srt", ".vtt", ".sbv"}:
                    # Lire et nettoyer le VTT
                    content = ""
                    for enc in ("utf-8", "latin-1", "cp1252"):
                        try:
                            content = f.read_text(encoding=enc)
                            break
                        except Exception:
                            pass
                    texte = nettoyer_vtt(content)
                    header = (
                        f"=== SOUS-TITRES (partiels, a titre de reference) : {f.name} ===\n"
                        f"=== MODULE : {module} ===\n"
                        f"=== ATTENTION : La video associee sera QUAND MEME transcrite ===\n"
                        f"=== via Whisper API pour garantir une transcription COMPLETE. ===\n\n"
                    )
                    dest.write_text(header + texte, encoding="utf-8")
                    try:
                        f.unlink()  # supprimer source
                    except Exception:
                        pass
                else:
                    shutil.move(str(f), str(dest))

                ok += 1
                log_lignes.append(f"OK  {f.name}  ->  {dest.name}")

            except Exception as e:
                log_lignes.append(f"ERR {f.name} -> {e}")
                print(f"    ERREUR : {f.name} -> {e}")

    # Log
    log_path = sortie / "reorganisation.log"
    with open(log_path, "w", encoding="utf-8") as lf:
        lf.write(f"Reorganisation {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
        lf.write(f"Source : {source}\nSortie : {sortie}\n\n")
        lf.write("\n".join(log_lignes))

    print(f"\n{'='*70}")
    print(f"  TERMINE !")
    print(f"  Fichiers deplaces/traites : {ok}")
    print(f"  Dossier propre            : {sortie}")
    print(f"  Log complet               : {log_path}")
    print(f"{'='*70}")
    print(f"\n  PROCHAINE ETAPE :")
    print(f"  Lance windows_transcribe_api.py")
    print(f"  Selectionne : {sortie}")
    if sous_titres:
        print(f"\n  Note : {len(sous_titres)} sous-titres conserves comme reference.")
        print(f"  Toutes les {len(videos)+len(audios)} videos/audios seront quand meme")
        print(f"  transcrites en entier via Whisper API.")

    input("\nAppuie sur Entree pour fermer...")


if __name__ == "__main__":
    main()
