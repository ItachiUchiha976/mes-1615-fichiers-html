#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TRANSCRIPTION WHISPER - WINDOWS 10
====================================
Transcrit automatiquement toutes tes videos ET fichiers audio en fichiers .txt.
Lance le soir, retrouve les transcriptions le matin.

INSTALLATION (une seule fois) :
  1. pip install faster-whisper
  2. winget install ffmpeg   (dans cmd en administrateur)

USAGE :
  Double-clique sur ce fichier -> une fenetre s'ouvre pour choisir le dossier
  OU depuis cmd :
  python windows_transcribe.py C:\\Users\\Toi\\Videos\\Formations

FICHIERS TRAITES :
  Videos : .mp4 .avi .mov .mkv .webm .mpeg .3gp .m4v .flv .wmv
  Audios : .mp3 .wav .aac .ogg .wma .m4a .opus .flac
  Ignores (silencieusement) : .pdf et tous les autres types

RESULTAT :
  transcriptions\\                    -> un .txt par video/audio
  transcription_COMPLETE_PARTIE_1.txt -> fichiers decoupes en ~3.5 Mo
  transcription_COMPLETE_PARTIE_2.txt -> (si le contenu est long)
  transcription.log                   -> journal de progression
"""

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from datetime import datetime


# ================================================================================
#  CONFIGURATION  (modifie ici si besoin)
# ================================================================================

OUTPUT_DIR      = "transcriptions"
CHECKPOINT_FILE = "transcription_checkpoint.json"
LOG_FILE        = "transcription.log"

# Modele Whisper :
#   "large-v3"        -> meilleure qualite anglais/espagnol (recommande)
#   "medium"          -> plus rapide, bonne qualite
#   "small"           -> rapide, qualite correcte
#   "distil-large-v3" -> presque aussi bon que large-v3, 2x plus rapide
WHISPER_MODEL = "large-v3"

# Taille max par fichier de sortie (3.5 Mo = safe pour claude.ai)
MAX_BYTES_PAR_PARTIE = int(3.5 * 1024 * 1024)

# Fichiers VIDEO reconnus
VIDEO_EXTENSIONS = {
    ".mp4", ".avi", ".mov", ".mkv", ".webm",
    ".mpeg", ".3gp", ".m4v", ".flv", ".wmv"
}

# Fichiers AUDIO reconnus (transcrits directement sans extraction video)
AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".aac", ".ogg", ".wma", ".m4a", ".opus", ".flac"
}

# Tous les fichiers media a traiter (video + audio)
ALL_MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

# ================================================================================


def setup_logging():
    fmt = "%(asctime)s  %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

log = logging.getLogger(__name__)


# -- Selecteur de dossier graphique (Windows) ------------------------------------

def demander_dossier() -> Path:
    """
    Ouvre une fenetre graphique pour choisir le dossier principal.
    Si l'utilisateur annule ou si tkinter n'est pas disponible,
    utilise le dossier courant.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()  # cacher la fenetre principale
        root.attributes("-topmost", True)  # mettre la boite de dialogue au premier plan

        print("\nUne fenetre de selection de dossier va s'ouvrir...")
        print("Choisis le dossier PRINCIPAL qui contient toutes tes formations.\n")

        dossier = filedialog.askdirectory(
            title="Choisis le dossier contenant tes formations (videos et audios)"
        )
        root.destroy()

        if dossier:
            return Path(dossier)
        else:
            print("Aucun dossier selectionne. Utilisation du dossier courant.")
            return Path(".")

    except Exception as e:
        print(f"Impossible d'ouvrir la fenetre graphique ({e}).")
        print("Utilisation du dossier courant.")
        return Path(".")


# -- Tri naturel (Module 2 avant Module 10, 01_intro avant 02_cours) -------------

def natural_key(name: str) -> list:
    return [int(c) if c.isdigit() else c.lower()
            for c in re.split(r"(\d+)", name)]

def sorted_naturally(paths):
    return sorted(paths, key=lambda p: natural_key(p.name))


# -- Checkpoint (reprise automatique si le PC s'eteint) --------------------------

def load_checkpoint() -> dict:
    if Path(CHECKPOINT_FILE).exists():
        try:
            return json.loads(Path(CHECKPOINT_FILE).read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_checkpoint(data: dict):
    Path(CHECKPOINT_FILE).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# -- Extraction / conversion audio via ffmpeg ------------------------------------

def extract_audio(media_path: Path, audio_path: Path):
    """
    Convertit n'importe quel fichier video ou audio en MP3 mono 16 kHz.
    Fonctionne sur .mp4, .mkv, .avi mais aussi .mp3, .wav, .m4a, etc.
    """
    cmd = [
        "ffmpeg", "-y", "-i", str(media_path),
        "-vn",           # ignorer la piste video si presente
        "-ac", "1",      # mono
        "-ar", "16000",  # 16 000 Hz
        "-b:a", "64k",   # bitrate leger
        str(audio_path),
    ]
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    result = subprocess.run(cmd, capture_output=True, text=True,
                            startupinfo=startupinfo)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg erreur : {result.stderr[-300:]}")


# -- Transcription faster-whisper ------------------------------------------------

_model_cache = None

def get_whisper_model():
    global _model_cache
    if _model_cache is None:
        log.info(f"Chargement du modele Whisper '{WHISPER_MODEL}'...")
        log.info("(Premier lancement : telechargement ~1-3 Go, une seule fois)")
        from faster_whisper import WhisperModel
        _model_cache = WhisperModel(
            WHISPER_MODEL,
            device="cpu",
            compute_type="int8",
        )
        log.info("Modele charge.")
    return _model_cache

def transcribe_audio(audio_path: Path) -> tuple:
    """Transcrit l'audio. Retourne (texte, langue_detectee)."""
    model = get_whisper_model()
    segments, info = model.transcribe(str(audio_path), beam_size=5)
    text = " ".join(seg.text for seg in segments).strip()
    return text, info.language


# -- Suivi de progression --------------------------------------------------------

def format_duree(secondes: float) -> str:
    s = int(secondes)
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    if h > 0:
        return f"{h}h{m:02d}m{sec:02d}s"
    return f"{m}m{sec:02d}s"

def affiche_barre(i: int, total: int, durees_reelles: list,
                  debut_global: float, success: int, errors: int):
    pct = i / total * 100
    elapsed = time.time() - debut_global

    if durees_reelles:
        moy = sum(durees_reelles) / len(durees_reelles)
        eta_str = format_duree(moy * (total - i))
    else:
        eta_str = "calcul en cours..."

    largeur = 28
    rempli = int(largeur * i / total)
    barre = "#" * rempli + "-" * (largeur - rempli)

    log.info(
        f"  [{barre}] {pct:5.1f}%  "
        f"{i}/{total}  |  "
        f"OK:{success} Err:{errors}  |  "
        f"Ecoule: {format_duree(elapsed)}  |  "
        f"Reste estim.: {eta_str}"
    )


# -- Traitement d'un fichier media -----------------------------------------------

def process_media(media_path: Path, output_txt: Path,
                  checkpoint: dict) -> tuple:
    """
    Transcrit un fichier video ou audio et sauvegarde le .txt.
    Les PDF et autres types non-media sont ignores (ne doivent pas arriver ici).
    Retourne (succes: bool, duree_traitement: float).
    duree = 0.0 si deja traite (skip).
    """
    key = str(media_path)

    if checkpoint.get(key) == "ok" and output_txt.exists():
        log.info(f"  [SKIP] Deja transcrit : {media_path.name}")
        return True, 0.0

    type_fichier = "AUDIO" if media_path.suffix.lower() in AUDIO_EXTENSIONS else "VIDEO"
    log.info(f"  --> [{type_fichier}] {media_path.name}")
    output_txt.parent.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    for attempt in range(1, 4):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                audio = Path(tmp) / "audio.mp3"
                extract_audio(media_path, audio)
                text, lang = transcribe_audio(audio)

            header = (
                f"=== FICHIER : {media_path.name} ===\n"
                f"=== TYPE : {type_fichier} ===\n"
                f"=== DOSSIER : {media_path.parent.name} ===\n"
                f"=== LANGUE DETECTEE : {lang} ===\n\n"
            )
            output_txt.write_text(header + text + "\n", encoding="utf-8")
            checkpoint[key] = "ok"
            save_checkpoint(checkpoint)

            duree = time.time() - t_start
            log.info(f"    OK ({lang}) en {format_duree(duree)} : {output_txt.name}")
            return True, duree

        except Exception as e:
            if attempt < 3:
                wait = 5 * attempt
                log.warning(f"    Tentative {attempt}/3 echouee : {e}. Pause {wait}s...")
                time.sleep(wait)
            else:
                log.error(f"    ECHEC definitif : {media_path.name} -> {e}")
                checkpoint[key] = f"erreur: {e}"
                save_checkpoint(checkpoint)
                return False, 0.0


# -- Fusion avec sommaire + decoupage automatique en parties de 3.5 Mo ----------

def fusionne_tout(output_dir: Path, base_name: str = "transcription_COMPLETE"):
    """
    Fusionne tous les .txt dans l'ordre naturel et les decoupe automatiquement
    en parties de 3.5 Mo max (safe pour claude.ai gratuit).
    La PARTIE 1 contient le SOMMAIRE complet de toute l'arborescence.
    """
    log.info("\nFusion et decoupage automatique des fichiers .txt...")

    dossiers = {}
    for txt in output_dir.rglob("*.txt"):
        dossiers.setdefault(txt.parent, []).append(txt)

    dossiers_tries = sorted(
        dossiers.keys(),
        key=lambda p: (-len(p.parts), natural_key(p.name))
    )

    sections = []
    for dossier in dossiers_tries:
        txts = sorted_naturally(dossiers[dossier])
        try:
            rel = dossier.relative_to(output_dir)
            nom = str(rel) if str(rel) != "." else "Racine"
        except ValueError:
            nom = dossier.name
        sections.append((nom, txts))

    total_fichiers = sum(len(txts) for _, txts in sections)
    date_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    def ouvre_partie(num: int):
        nom_fichier = f"{base_name}_PARTIE_{num}.txt"
        f = open(nom_fichier, "w", encoding="utf-8")
        f.write("=" * 70 + "\n")
        f.write("  TRANSCRIPTIONS - FORMATIONS SUR LA SEDUCTION\n")
        f.write(f"  PARTIE {num}\n")
        f.write(f"  Genere le : {date_str}\n")
        f.write(f"  Total fichiers (toutes parties) : {total_fichiers}\n")
        f.write("=" * 70 + "\n\n")
        return f, nom_fichier

    partie_num = 1
    f, nom_courant = ouvre_partie(partie_num)
    octets_courants = 0
    fichiers_crees = [nom_courant]

    # Sommaire complet dans la partie 1
    lignes_sommaire = []
    lignes_sommaire.append("+" + "-" * 68 + "+\n")
    lignes_sommaire.append("|  SOMMAIRE - ARBORESCENCE COMPLETE DES FORMATIONS                |\n")
    lignes_sommaire.append("|  (dans l'ordre exact ou les transcriptions apparaissent)         |\n")
    lignes_sommaire.append("+" + "-" * 68 + "+\n\n")
    num = 1
    for nom_section, txts in sections:
        depth = nom_section.count("\\") + nom_section.count("/")
        indent = "    " * depth
        lignes_sommaire.append(f"{indent}[DOSSIER] {nom_section}\n")
        for txt in txts:
            lignes_sommaire.append(f"{indent}    [{num:03d}] {txt.stem}\n")
            num += 1
        lignes_sommaire.append("\n")
    lignes_sommaire.append("\n" + "=" * 70 + "\n")
    lignes_sommaire.append("  FIN DU SOMMAIRE - DEBUT DES TRANSCRIPTIONS\n")
    lignes_sommaire.append("=" * 70 + "\n\n")

    bloc_sommaire = "".join(lignes_sommaire)
    f.write(bloc_sommaire)
    octets_courants += len(bloc_sommaire.encode("utf-8"))

    for nom_section, txts in sections:
        section_header = (
            "\n" + "-" * 60 + "\n"
            f"  SECTION : {nom_section}\n"
            + "-" * 60 + "\n\n"
        )
        header_bytes = len(section_header.encode("utf-8"))

        if octets_courants + header_bytes > MAX_BYTES_PAR_PARTIE:
            f.close()
            log.info(f"  -> Partie {partie_num} terminee ({octets_courants / 1024 / 1024:.1f} Mo)")
            partie_num += 1
            f, nom_courant = ouvre_partie(partie_num)
            fichiers_crees.append(nom_courant)
            octets_courants = 0

        f.write(section_header)
        octets_courants += header_bytes

        for txt in txts:
            contenu = txt.read_text(encoding="utf-8") + "\n\n"
            contenu_bytes = len(contenu.encode("utf-8"))

            if octets_courants > 0 and octets_courants + contenu_bytes > MAX_BYTES_PAR_PARTIE:
                f.close()
                log.info(f"  -> Partie {partie_num} terminee ({octets_courants / 1024 / 1024:.1f} Mo)")
                partie_num += 1
                f, nom_courant = ouvre_partie(partie_num)
                fichiers_crees.append(nom_courant)
                octets_courants = 0

            f.write(contenu)
            octets_courants += contenu_bytes

    f.close()
    log.info(f"  -> Partie {partie_num} terminee ({octets_courants / 1024 / 1024:.1f} Mo)")

    log.info(f"\nFusion terminee : {partie_num} fichier(s) cree(s)")
    for nom_f in fichiers_crees:
        taille = Path(nom_f).stat().st_size / 1024 / 1024
        log.info(f"  {nom_f}  ({taille:.1f} Mo)")
    log.info(f"  Total : {total_fichiers} fichiers dans {len(sections)} sections")

    return fichiers_crees


# -- Programme principal ---------------------------------------------------------

def main():
    setup_logging()

    # Dossier source : argument en ligne de commande OU fenetre graphique
    if len(sys.argv) > 1:
        video_root = Path(sys.argv[1])
        log.info(f"Dossier specifie en argument : {video_root}")
    else:
        video_root = demander_dossier()

    video_root = video_root.resolve()
    output_dir = Path(OUTPUT_DIR).resolve()

    log.info("=" * 70)
    log.info("  TRANSCRIPTION WHISPER - WINDOWS 10")
    log.info("=" * 70)
    log.info(f"  Dossier source     : {video_root}")
    log.info(f"  Sorties .txt       : {output_dir}")
    log.info(f"  Fichiers fusionnes : transcription_COMPLETE_PARTIE_*.txt")
    log.info(f"  Modele Whisper     : {WHISPER_MODEL}")
    log.info(f"  Taille max/partie  : {MAX_BYTES_PAR_PARTIE / 1024 / 1024:.1f} Mo")
    log.info(f"  Videos traitees    : {', '.join(sorted(VIDEO_EXTENSIONS))}")
    log.info(f"  Audios traites     : {', '.join(sorted(AUDIO_EXTENSIONS))}")
    log.info(f"  Ignores            : .pdf et tous les autres types")
    log.info("=" * 70 + "\n")

    if not video_root.exists():
        log.error(f"Dossier introuvable : {video_root}")
        input("Appuie sur Entree pour fermer...")
        sys.exit(1)

    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        log.error("ffmpeg n'est pas installe ou introuvable.")
        log.error("Installe-le : winget install ffmpeg  (cmd en administrateur)")
        log.error("Puis ferme et reouvre cette fenetre.")
        input("Appuie sur Entree pour fermer...")
        sys.exit(1)

    # Collecter tous les fichiers media (video + audio), ignorer le reste (pdf, etc.)
    medias = sorted_naturally([
        p for p in video_root.rglob("*")
        if p.is_file() and p.suffix.lower() in ALL_MEDIA_EXTENSIONS
    ])

    if not medias:
        log.error(f"Aucun fichier video/audio trouve dans : {video_root}")
        log.error(f"Extensions reconnues : {', '.join(sorted(ALL_MEDIA_EXTENSIONS))}")
        input("Appuie sur Entree pour fermer...")
        sys.exit(1)

    # Compter par type pour info
    nb_videos = sum(1 for m in medias if m.suffix.lower() in VIDEO_EXTENSIONS)
    nb_audios = sum(1 for m in medias if m.suffix.lower() in AUDIO_EXTENSIONS)

    checkpoint = load_checkpoint()
    total = len(medias)
    deja_faites = sum(1 for m in medias if checkpoint.get(str(m)) == "ok")

    log.info(f"Fichiers trouves  : {total}  ({nb_videos} videos, {nb_audios} audios)")
    log.info(f"Deja transcrits   : {deja_faites}  (seront ignores [SKIP])")
    log.info(f"Restant a traiter : {total - deja_faites}")
    log.info("\nDebut de la transcription...")
    log.info("Barre : [####----] XX.X%  N/total | OK:x Err:y | Ecoule: ... | Reste estim.: ...\n")

    success = 0
    errors = 0
    durees_reelles = []
    debut_global = time.time()

    for i, media in enumerate(medias, 1):
        try:
            rel = media.relative_to(video_root)
        except ValueError:
            rel = Path(media.name)

        output_txt = output_dir / rel.parent / (media.stem + ".txt")
        log.info(f"\n[{i}/{total}] {rel}")

        ok, duree = process_media(media, output_txt, checkpoint)

        if ok:
            success += 1
            if duree > 2.0:
                durees_reelles.append(duree)
        else:
            errors += 1

        affiche_barre(i, total, durees_reelles, debut_global, success, errors)

    temps_total = time.time() - debut_global
    log.info("\n" + "=" * 70)
    log.info("  TERMINE !")
    log.info(f"  Fichiers transcrits avec succes : {success}/{total}")
    log.info(f"  Erreurs                         : {errors}")
    log.info(f"  Temps total                     : {format_duree(temps_total)}")
    if durees_reelles:
        log.info(f"  Temps moyen par fichier         : {format_duree(sum(durees_reelles)/len(durees_reelles))}")
    log.info("=" * 70)

    if success > 0:
        fichiers = fusionne_tout(output_dir)
        nb = len(fichiers)
        log.info(f"\nProchaine etape - uploade les {nb} fichier(s) sur claude.ai :")
        for fich in fichiers:
            log.info(f"  {Path(fich).resolve()}")
        if nb > 1:
            log.info("\nCOMMENT ENVOYER PLUSIEURS PARTIES A CLAUDE :")
            log.info("  1. Va sur claude.ai, demarre une nouvelle conversation.")
            log.info("  2. Ecris : 'Je vais te donner plusieurs fichiers de transcription.")
            log.info("     Lis-les tous avant de creer le guide. Voici la partie 1.'")
            log.info("     Attache PARTIE_1.txt et envoie.")
            log.info("  3. Pour chaque partie suivante : 'Voici la suite.' + fichier.")
            log.info("  4. Apres la derniere partie : 'C'est tout. Cree maintenant le")
            log.info("     guide complet de seduction en francais en 9 chapitres.'")
        else:
            log.info("\n  Attache le fichier dans claude.ai (bouton trombone).")
            log.info("  Demande : 'Cree un guide complet de seduction en francais")
            log.info("  en 9 chapitres a partir de ces transcriptions.'")

    if errors > 0:
        log.warning(f"\n{errors} fichier(s) ont echoue.")
        log.warning("Consulte transcription.log pour les details.")
        log.warning("Relance le script pour reessayer automatiquement.")

    input("\nAppuie sur Entree pour fermer...")


if __name__ == "__main__":
    main()
