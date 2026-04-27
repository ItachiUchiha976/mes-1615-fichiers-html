#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REORGANISATION GOOGLE TAKEOUT - WINDOWS 10
==========================================
Google Takeout cree une structure profonde et complexe.
Ce script :
  1. Scanne toute l'arborescence extraite
  2. Affiche ce qu'il trouve (videos, sous-titres, pdfs, etc.)
  3. Detecte les fichiers de sous-titres / transcriptions deja existants
  4. Reorganise tout dans une structure propre et plate
  5. Supprime les fichiers JSON (metadonnees inutiles)
  6. Nettoie les sous-titres SRT/VTT en texte pur lisible

USAGE :
  Double-clique sur ce fichier
  -> Selectionne le dossier a reorganiser (ex: D:\Le Systeme de Todd Valentine)
  -> Indique un dossier de sortie propre (ex: D:\Todd_Valentine_PROPRE)
  -> C'est tout

AUCUNE INSTALLATION REQUISE (bibliotheques standard Python uniquement)
"""

import re
import shutil
import sys
import os
from pathlib import Path
from datetime import datetime


# ================================================================================
#  CONFIGURATION
# ================================================================================

# Extensions a CONSERVER (tout le reste est ignore)
KEEP_EXT = {
    # Media
    ".mp4", ".avi", ".mov", ".mkv", ".webm", ".mpeg", ".m4v", ".flv", ".wmv",
    ".mp3", ".wav", ".aac", ".ogg", ".wma", ".m4a", ".opus", ".flac",
    # Documents
    ".pdf", ".docx", ".doc", ".pptx", ".ppt",
    # Texte (inclut les sous-titres)
    ".txt", ".md", ".srt", ".vtt", ".sbv",
    # Images
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",
}

# Extensions a SUPPRIMER sans hesiter
DELETE_EXT = {".json"}

# Mots-cles dans les noms de fichiers qui indiquent des sous-titres
SUBTITLE_KEYWORDS = [
    "sous-tit", "sous_tit", "subtitle", "subtitles",
    "transcription", "transcript", "caption", "captions",
    "-tit.", "_tit.", "sous-titres",
]

# ================================================================================


def demander_dossier(titre: str) -> Path:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        dossier = filedialog.askdirectory(title=titre)
        root.destroy()
        return Path(dossier) if dossier else None
    except Exception:
        return None


def natural_key(name: str) -> list:
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", name)]


def est_sous_titre(filename: str) -> bool:
    """Detecte si un fichier est un sous-titre/transcription."""
    name_lower = filename.lower()
    if any(kw in name_lower for kw in SUBTITLE_KEYWORDS):
        return True
    ext = Path(filename).suffix.lower()
    if ext in {".srt", ".vtt", ".sbv"}:
        return True
    return False


def nettoyer_sous_titre(content: str) -> str:
    """
    Convertit SRT/VTT YouTube en texte pur lisible.

    Le format VTT YouTube a deux problemes :
      1. Lignes avec horodatages mot par mot : Okay,<00:00:00.560><c> so</c>...
      2. Phrases repetees en double (la phrase complete + la ligne karaoke)

    Strategie : ne garder QUE les lignes sans balise '<' (les lignes propres),
    ignorer les lignes karaoke, puis dedupliquer.
    """
    lines = content.splitlines()
    texte_pur = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Ignorer entetes VTT
        if re.match(r"^(WEBVTT|NOTE|STYLE|Kind:|Language:)", line):
            continue
        # Ignorer les numeros de sequence SRT
        if re.match(r"^\d+$", line):
            continue
        # Ignorer toutes les lignes d'horodatage (SRT et VTT)
        if re.match(r"\d{1,2}:\d{2}:\d{2}[,\.]\d{3}\s*-->", line):
            continue
        if re.match(r"\d{1,2}:\d{2}[,\.]\d{3}\s*-->", line):
            continue
        # CLES : ignorer les lignes qui contiennent des balises temporelles VTT
        # ex: Okay,<00:00:00.560><c> so</c><00:00:00.719><c> that's</c>...
        # Ces lignes sont les doublons "karaoke" -> on les saute completement
        if "<" in line and re.search(r"<\d{2}:\d{2}", line):
            continue
        # Supprimer les eventuelles balises HTML residuelles (<i>, <b>, etc.)
        line = re.sub(r"<[^>]+>", "", line)
        # Supprimer les tags de positionnement {align:start}
        line = re.sub(r"\{[^}]+\}", "", line)
        # Nettoyer les espaces multiples
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            texte_pur.append(line)

    # Dedupliquer : supprimer TOUTES les repetitions (pas seulement consecutives)
    # Le VTT YouTube repete la meme phrase plusieurs fois de suite
    # On garde la derniere occurrence de chaque "bloc" de phrases identiques
    if not texte_pur:
        return ""

    # Algorithme : garder une ligne uniquement si elle n'est pas la meme
    # que la precedente ET qu'elle apporte du nouveau contenu
    result = []
    prev = ""
    for line in texte_pur:
        # Normaliser pour la comparaison (minuscules, espaces)
        normalized = line.lower().strip()
        prev_normalized = prev.lower().strip()

        # Ignorer si identique a la precedente
        if normalized == prev_normalized:
            continue

        # Ignorer si la ligne precedente CONTIENT deja cette ligne
        # (cas frequents dans VTT : "Okay" puis "Okay, so that's a lot")
        if prev_normalized.startswith(normalized) and len(normalized) > 10:
            continue

        # Mettre a jour avec la version la plus complete
        result.append(line)
        prev = line

    return " ".join(result)


def trouver_module_parent(file_path: Path, racine_takeout: Path) -> str:
    """
    Dans la structure Google Takeout profonde, trouve le nom du module
    (le dossier significatif le plus proche du fichier).

    Structure typique :
    racine/takeout-xxx-001/Takeout/Drive/Formation/Module/fichier.mp4
                                                   ^^^^^^ <- on veut ca
    """
    try:
        rel = file_path.relative_to(racine_takeout)
        parts = rel.parts

        # Le dossier parent immediat du fichier
        if len(parts) >= 2:
            return parts[-2]  # dossier parent direct
        return "Racine"
    except ValueError:
        return file_path.parent.name


def nettoyer_nom_fichier(name: str) -> str:
    """
    Nettoie le nom du fichier :
    - Supprime les suffixes de sous-titres pour les .txt
    - Tronque les noms trop longs
    """
    stem = Path(name).stem
    ext = Path(name).suffix

    # Nettoyer les suffixes de sous-titres (garder le nom propre de la video)
    for kw in SUBTITLE_KEYWORDS:
        if kw in stem.lower():
            # Trouver la position et couper
            idx = stem.lower().find(kw)
            if idx > 3:  # garder au moins les premiers caracteres
                stem = stem[:idx].rstrip(" -_.").rstrip()
            break

    # Nettoyer les noms tres longs (Windows limite a 260 chars de chemin total)
    if len(stem) > 120:
        stem = stem[:120].rstrip()

    # Supprimer les caracteres invalides Windows
    stem = re.sub(r'[<>:"/\\|?*]', '_', stem)

    return stem + ext


def main():
    print("\n" + "=" * 70)
    print("  REORGANISATION GOOGLE TAKEOUT")
    print("=" * 70)
    print("\nCe script va :")
    print("  1. Scanner ta formation extraite depuis Google Takeout")
    print("  2. Detecter les sous-titres/transcriptions deja existants")
    print("  3. Reorganiser tout proprement dans un nouveau dossier")
    print("  4. Supprimer les JSON inutiles")
    print("  5. Convertir les sous-titres en texte pur lisible\n")

    # Choisir le dossier source (le desordre Google Takeout)
    print("ETAPE 1 : Selectionne le dossier SOURCE (le desordre Google Takeout)")
    print("         Ex: D:\\Le Systeme de Todd Valentine\n")
    source = demander_dossier("Dossier SOURCE (Google Takeout desordonne)")
    if not source or not source.exists():
        print("Annule ou dossier introuvable.")
        input("Appuie sur Entree pour fermer...")
        sys.exit(0)

    print(f"Source : {source}\n")

    # Choisir le dossier de sortie
    print("ETAPE 2 : Selectionne le dossier SORTIE (propre et organise)")
    print("         Ex: D:\\Todd_Valentine_PROPRE\n")
    sortie = demander_dossier("Dossier SORTIE (propre)")
    if not sortie:
        # Proposer un nom automatique
        sortie = source.parent / (source.name + "_PROPRE")
        print(f"Sortie automatique : {sortie}")

    sortie.mkdir(parents=True, exist_ok=True)
    print(f"Sortie : {sortie}\n")

    # ── Scanner tous les fichiers ─────────────────────────────────────────────

    print("Scan en cours...\n")

    tous_fichiers = [f for f in source.rglob("*") if f.is_file()]

    # Compter par extension
    compteur_ext = {}
    for f in tous_fichiers:
        ext = f.suffix.lower() if f.suffix else "(aucune)"
        compteur_ext[ext] = compteur_ext.get(ext, 0) + 1

    compteur_ext_trie = sorted(compteur_ext.items(), key=lambda x: -x[1])

    print("=" * 70)
    print("  FICHIERS TROUVES")
    print("=" * 70)
    print(f"  {'Extension':<20} {'Nombre':>8}    {'Action'}")
    print(f"  {'-'*20} {'-'*8}    {'-'*30}")

    total = 0
    for ext, nb in compteur_ext_trie:
        if ext in DELETE_EXT:
            action = "SUPPRIME"
        elif ext in KEEP_EXT:
            action = "CONSERVE"
        else:
            action = "ignore"
        print(f"  {ext:<20} {nb:>8}    {action}")
        total += nb
    print(f"  {'-'*20} {'-'*8}")
    print(f"  {'TOTAL':<20} {total:>8}")
    print("=" * 70 + "\n")

    # Detecter les sous-titres
    sous_titres = [f for f in tous_fichiers
                   if f.suffix.lower() in KEEP_EXT and est_sous_titre(f.name)]

    videos = [f for f in tous_fichiers
              if f.suffix.lower() in {".mp4", ".avi", ".mov", ".mkv", ".webm",
                                       ".mpeg", ".m4v", ".flv", ".wmv"}]

    audios = [f for f in tous_fichiers
              if f.suffix.lower() in {".mp3", ".wav", ".aac", ".m4a", ".ogg",
                                       ".wma", ".opus", ".flac"}]

    print("=" * 70)
    print("  ANALYSE DES CONTENUS")
    print("=" * 70)
    print(f"  Videos trouvees          : {len(videos)}")
    print(f"  Audios trouves           : {len(audios)}")
    print(f"  Sous-titres/transcripts  : {len(sous_titres)}")

    if sous_titres:
        print(f"\n  BONNE NOUVELLE : {len(sous_titres)} fichier(s) de sous-titres detecte(s) !")
        print(f"  Ces fichiers contiennent deja les transcriptions des videos.")
        print(f"  -> Beaucoup moins de videos a transcrire via l'API Whisper !")
        print(f"\n  Exemples de sous-titres trouves :")
        for st in sous_titres[:5]:
            print(f"    - {st.name}")
        if len(sous_titres) > 5:
            print(f"    ... et {len(sous_titres) - 5} autres")

    print("=" * 70 + "\n")

    reponse = input("Reorganiser maintenant ? (oui / non) : ").strip().lower()
    if reponse not in ("oui", "o", "yes", "y"):
        print("Annule.")
        input("Appuie sur Entree pour fermer...")
        sys.exit(0)

    # ── Reorganisation ────────────────────────────────────────────────────────

    print("\nReorganisation en cours...\n")

    modules: dict[str, list[Path]] = {}
    for f in tous_fichiers:
        ext = f.suffix.lower()
        if ext in DELETE_EXT:
            continue
        if ext not in KEEP_EXT:
            continue
        module = trouver_module_parent(f, source)
        modules.setdefault(module, []).append(f)

    ok = 0
    skips = 0
    log_lignes = []

    modules_tries = sorted(modules.keys(), key=lambda s: natural_key(s))

    for module in modules_tries:
        fichiers = sorted(modules[module], key=lambda f: natural_key(f.name))
        module_dir = sortie / module
        module_dir.mkdir(parents=True, exist_ok=True)

        print(f"  [{module}] -> {len(fichiers)} fichier(s)")

        for f in fichiers:
            # Nettoyer le nom
            nouveau_nom = nettoyer_nom_fichier(f.name)
            dest = module_dir / nouveau_nom

            # Eviter les collisions de noms
            if dest.exists():
                stem = dest.stem
                suffixe = dest.suffix
                compteur = 1
                while dest.exists():
                    dest = module_dir / f"{stem}_{compteur}{suffixe}"
                    compteur += 1
                skips += 1

            try:
                # Pour les sous-titres TXT/SRT/VTT : nettoyer et sauvegarder
                if est_sous_titre(f.name) or f.suffix.lower() in {".srt", ".vtt", ".sbv"}:
                    for enc in ("utf-8", "latin-1", "cp1252"):
                        try:
                            content = f.read_text(encoding=enc)
                            break
                        except Exception:
                            content = ""
                    texte = nettoyer_sous_titre(content)
                    # Changer l'extension en .txt si ce n'est pas deja le cas
                    if dest.suffix.lower() != ".txt":
                        dest = dest.with_suffix(".txt")
                    # Ajouter un en-tete informatif
                    header = (
                        f"=== TRANSCRIPTION/SOUS-TITRES : {f.name} ===\n"
                        f"=== MODULE : {module} ===\n\n"
                    )
                    dest.write_text(header + texte, encoding="utf-8")
                else:
                    shutil.copy2(str(f), str(dest))

                ok += 1
                log_lignes.append(f"OK  {f}  ->  {dest}")

            except Exception as e:
                log_lignes.append(f"ERR {f}  ->  {e}")
                print(f"    ERREUR : {f.name} -> {e}")

    # ── Log et rapport final ──────────────────────────────────────────────────

    log_path = sortie / "reorganisation.log"
    with open(log_path, "w", encoding="utf-8") as lf:
        lf.write(f"Reorganisation du {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
        lf.write(f"Source  : {source}\n")
        lf.write(f"Sortie  : {sortie}\n\n")
        lf.write("\n".join(log_lignes))

    print(f"\n{'='*70}")
    print(f"  TERMINE !")
    print(f"  Fichiers copies/traites : {ok}")
    print(f"  Dossier propre          : {sortie}")
    print(f"  Log complet             : {log_path}")
    print(f"{'='*70}")

    if sous_titres:
        print(f"\n  IMPORTANT : {len(sous_titres)} sous-titres/transcriptions trouves !")
        print(f"  -> Beaucoup de videos ont deja leur transcription en texte.")
        print(f"  -> Lance windows_transcribe_api.py sur le dossier propre.")
        print(f"     Le script detectera les .txt existants et evitera de")
        print(f"     retranscrire les videos qui ont deja leurs sous-titres.")
    else:
        print(f"\n  Lance ensuite windows_transcribe_api.py sur :")
        print(f"  {sortie}")

    input("\nAppuie sur Entree pour fermer...")


if __name__ == "__main__":
    main()
