#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TRANSCRIPTION WHISPER - WINDOWS 10
====================================
Transcrit automatiquement toutes tes videos en fichiers .txt.
Lance le soir, retrouve les transcriptions le matin.

INSTALLATION (une seule fois) :
  1. pip install faster-whisper
  2. winget install ffmpeg   (dans cmd en administrateur)

USAGE :
  Double-clique sur ce fichier
  OU depuis cmd :
  python windows_transcribe.py C:\\Users\\Toi\\Videos\\Formations

RESULTAT :
  transcriptions\\                    -> un .txt par video
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

VIDEO_EXTENSIONS = {
    ".mp4", ".avi", ".mov", ".mkv", ".webm",
    ".mpeg", ".3gp", ".m4v", ".flv", ".wmv"
}

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


# -- Extraction audio via ffmpeg -------------------------------------------------

def extract_audio(video_path: Path, audio_path: Path):
    """Extrait la piste audio en MP3 mono 16 kHz (optimal pour Whisper)."""
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn",           # supprimer la video
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

_model_cache = None  # modele charge une seule fois en memoire

def get_whisper_model():
    global _model_cache
    if _model_cache is None:
        log.info(f"Chargement du modele Whisper '{WHISPER_MODEL}'...")
        log.info("(Premier lancement : telechargement ~1-3 Go, une seule fois)")
        from faster_whisper import WhisperModel
        _model_cache = WhisperModel(
            WHISPER_MODEL,
            device="cpu",
            compute_type="int8",  # quantise int8 = moins de RAM, meme qualite
        )
        log.info("Modele charge.")
    return _model_cache

def transcribe_audio(audio_path: Path) -> tuple:
    """Transcrit l'audio. Retourne (texte, langue_detectee)."""
    model = get_whisper_model()
    # Detection automatique de la langue (anglais, espagnol, etc.)
    segments, info = model.transcribe(str(audio_path), beam_size=5)
    text = " ".join(seg.text for seg in segments).strip()
    return text, info.language


# -- Suivi de progression --------------------------------------------------------

def format_duree(secondes: float) -> str:
    """Formate une duree en hh:mm:ss."""
    s = int(secondes)
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    if h > 0:
        return f"{h}h{m:02d}m{sec:02d}s"
    return f"{m}m{sec:02d}s"

def affiche_barre(i: int, total: int, durees_reelles: list,
                  debut_global: float, success: int, errors: int):
    """
    Affiche une ligne de progression apres chaque video :
      [####----] 34.2%  12/35 videos | OK:11 Err:1 | Ecoule: 1h23m | Reste estim.: 2h41m
    """
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
        f"{i}/{total} videos  |  "
        f"OK:{success} Err:{errors}  |  "
        f"Ecoule: {format_duree(elapsed)}  |  "
        f"Reste estim.: {eta_str}"
    )


# -- Traitement d'une video ------------------------------------------------------

def process_video(video_path: Path, output_txt: Path,
                  checkpoint: dict) -> tuple:
    """
    Transcrit une video et sauvegarde le .txt.
    Retourne (succes: bool, duree_traitement: float).
    duree = 0.0 si la video etait deja traitee (skip).
    """
    key = str(video_path)

    if checkpoint.get(key) == "ok" and output_txt.exists():
        log.info(f"  [SKIP] Deja transcrit : {video_path.name}")
        return True, 0.0

    log.info(f"  --> Traitement : {video_path.name}")
    output_txt.parent.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    for attempt in range(1, 4):  # 3 tentatives maximum
        try:
            with tempfile.TemporaryDirectory() as tmp:
                audio = Path(tmp) / "audio.mp3"
                extract_audio(video_path, audio)
                text, lang = transcribe_audio(audio)

            header = (
                f"=== VIDEO : {video_path.name} ===\n"
                f"=== DOSSIER : {video_path.parent.name} ===\n"
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
                log.error(f"    ECHEC definitif : {video_path.name} -> {e}")
                checkpoint[key] = f"erreur: {e}"
                save_checkpoint(checkpoint)
                return False, 0.0


# -- Fusion avec sommaire + decoupage automatique en parties de 3.5 Mo ----------

def fusionne_tout(output_dir: Path, base_name: str = "transcription_COMPLETE"):
    """
    Fusionne tous les .txt dans l'ordre naturel et les decoupe automatiquement
    en parties de 3.5 Mo max (taille sure pour claude.ai gratuit).

    La PARTIE 1 contient le SOMMAIRE complet de toute l'arborescence,
    suivi des premieres transcriptions.
    Les parties suivantes continuent la ou la precedente s'est arretee.

    Produit :
      transcription_COMPLETE_PARTIE_1.txt
      transcription_COMPLETE_PARTIE_2.txt  (si necessaire)
      ...
    """
    log.info("\nFusion et decoupage automatique des fichiers .txt...")

    # Collecter tous les .txt par dossier
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

    total_videos = sum(len(txts) for _, txts in sections)
    date_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    def ouvre_partie(num: int):
        """Ouvre un nouveau fichier partie et ecrit son en-tete."""
        nom_fichier = f"{base_name}_PARTIE_{num}.txt"
        f = open(nom_fichier, "w", encoding="utf-8")
        f.write("=" * 70 + "\n")
        f.write(f"  TRANSCRIPTIONS - FORMATIONS SUR LA SEDUCTION\n")
        f.write(f"  PARTIE {num}\n")
        f.write(f"  Genere le : {date_str}\n")
        f.write(f"  Total videos (toutes parties) : {total_videos}\n")
        f.write("=" * 70 + "\n\n")
        return f, nom_fichier

    # Ouvrir la partie 1
    partie_num = 1
    f, nom_courant = ouvre_partie(partie_num)
    octets_courants = 0
    fichiers_crees = [nom_courant]

    # ── Ecrire le SOMMAIRE dans la partie 1 ──────────────────────────────────
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

    # ── Ecrire les transcriptions section par section ─────────────────────────
    for nom_section, txts in sections:

        section_header = (
            "\n" + "-" * 60 + "\n"
            f"  SECTION : {nom_section}\n"
            + "-" * 60 + "\n\n"
        )
        header_bytes = len(section_header.encode("utf-8"))

        # Ouvrir une nouvelle partie si la section ne rentre plus
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

            # Ouvrir une nouvelle partie si ce fichier ne rentre plus
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

    # Recapitulatif
    log.info(f"\nFusion terminee : {partie_num} fichier(s) cree(s)")
    for nom_f in fichiers_crees:
        taille = Path(nom_f).stat().st_size / 1024 / 1024
        log.info(f"  {nom_f}  ({taille:.1f} Mo)")
    log.info(f"  Total : {total_videos} videos dans {len(sections)} sections")

    return fichiers_crees


# -- Programme principal ---------------------------------------------------------

def main():
    setup_logging()

    video_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    video_root = video_root.resolve()
    output_dir = Path(OUTPUT_DIR).resolve()

    log.info("=" * 70)
    log.info("  TRANSCRIPTION WHISPER - WINDOWS 10")
    log.info("=" * 70)
    log.info(f"  Dossier videos     : {video_root}")
    log.info(f"  Sorties .txt       : {output_dir}")
    log.info(f"  Fichiers fusionnes : transcription_COMPLETE_PARTIE_*.txt")
    log.info(f"  Modele Whisper     : {WHISPER_MODEL}")
    log.info(f"  Taille max/partie  : {MAX_BYTES_PAR_PARTIE / 1024 / 1024:.1f} Mo")
    log.info("=" * 70 + "\n")

    # Verifier que le dossier video existe
    if not video_root.exists():
        log.error(f"Dossier introuvable : {video_root}")
        input("Appuie sur Entree pour fermer...")
        sys.exit(1)

    # Verifier que ffmpeg est installe
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        log.error("ffmpeg n'est pas installe ou introuvable.")
        log.error("Installe-le : winget install ffmpeg  (cmd en administrateur)")
        log.error("Puis ferme et reouvre cette fenetre.")
        input("Appuie sur Entree pour fermer...")
        sys.exit(1)

    # Collecter toutes les videos (tous sous-dossiers inclus)
    videos = sorted_naturally([
        p for p in video_root.rglob("*")
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    ])

    if not videos:
        log.error(f"Aucune video trouvee dans : {video_root}")
        log.error(f"Extensions reconnues : {', '.join(sorted(VIDEO_EXTENSIONS))}")
        input("Appuie sur Entree pour fermer...")
        sys.exit(1)

    checkpoint = load_checkpoint()
    total = len(videos)
    deja_faites = sum(1 for v in videos if checkpoint.get(str(v)) == "ok")

    log.info(f"Videos trouvees   : {total}")
    log.info(f"Deja transcrites  : {deja_faites}  (seront ignorees [SKIP])")
    log.info(f"Restant a traiter : {total - deja_faites}")
    log.info("\nDebut de la transcription...")
    log.info("Barre : [####----] XX.X%  N/total | OK:x Err:y | Ecoule: ... | Reste estim.: ...\n")

    success = 0
    errors = 0
    durees_reelles = []
    debut_global = time.time()

    for i, video in enumerate(videos, 1):
        try:
            rel = video.relative_to(video_root)
        except ValueError:
            rel = Path(video.name)

        output_txt = output_dir / rel.parent / (video.stem + ".txt")
        log.info(f"\n[{i}/{total}] {rel}")

        ok, duree = process_video(video, output_txt, checkpoint)

        if ok:
            success += 1
            if duree > 2.0:  # ignorer les skips pour l'estimation
                durees_reelles.append(duree)
        else:
            errors += 1

        affiche_barre(i, total, durees_reelles, debut_global, success, errors)

    # Resume final
    temps_total = time.time() - debut_global
    log.info("\n" + "=" * 70)
    log.info("  TERMINE !")
    log.info(f"  Videos traitees avec succes : {success}/{total}")
    log.info(f"  Erreurs                     : {errors}")
    log.info(f"  Temps total                 : {format_duree(temps_total)}")
    if durees_reelles:
        log.info(f"  Temps moyen par video       : {format_duree(sum(durees_reelles)/len(durees_reelles))}")
    log.info("=" * 70)

    # Fusion et decoupage
    if success > 0:
        fichiers = fusionne_tout(output_dir)
        nb = len(fichiers)
        log.info(f"\nProchaine etape - uploade les {nb} fichier(s) sur claude.ai :")
        for f in fichiers:
            log.info(f"  {Path(f).resolve()}")
        if nb > 1:
            log.info(f"\nCOMMENT ENVOYER PLUSIEURS PARTIES A CLAUDE :")
            log.info("  1. Va sur claude.ai et demarre une nouvelle conversation.")
            log.info("  2. Ecris : 'Je vais te donner plusieurs fichiers de transcription.")
            log.info("     Lis-les tous avant de creer le guide. Voici la partie 1.'")
            log.info("     Puis attache PARTIE_1.txt.")
            log.info("  3. Pour chaque partie suivante : 'Voici la suite.' + fichier.")
            log.info("  4. Apres la derniere : 'C'est tout. Cree maintenant le guide")
            log.info("     complet de seduction en francais en 9 chapitres.'")
        else:
            log.info("\n  Attache le fichier dans claude.ai (bouton trombone).")
            log.info("  Demande : 'Cree un guide complet de seduction en francais")
            log.info("  en 9 chapitres a partir de ces transcriptions.'")

    if errors > 0:
        log.warning(f"\n{errors} video(s) ont echoue.")
        log.warning("Consulte transcription.log pour les details.")
        log.warning("Relance le script pour reessayer automatiquement.")

    input("\nAppuie sur Entree pour fermer...")


if __name__ == "__main__":
    main()
