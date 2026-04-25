#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TRANSCRIPTION WHISPER – WINDOWS 10
===================================
Ce script transcrit automatiquement toutes tes vidéos en fichiers .txt.
Lance-le le soir, laisse tourner la nuit, retrouve tes transcriptions le matin.

INSTALLATION (à faire une seule fois, voir README_WINDOWS.txt) :
  pip install faster-whisper

USAGE :
  python windows_transcribe.py

  Par défaut, il cherche les vidéos dans le dossier courant.
  Pour spécifier un autre dossier :
  python windows_transcribe.py C:\\Users\\Toi\\Videos\\Formations

RÉSULTAT :
  Un dossier "transcriptions\\" est créé à côté du script.
  Il contient les mêmes sous-dossiers que tes vidéos, avec un .txt par vidéo.
  Un fichier "transcription_COMPLETE.txt" fusionne tout dans l'ordre.
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


# ════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION  (modifie ici si besoin)
# ════════════════════════════════════════════════════════════════════════════

# Dossier de sortie (sera créé automatiquement)
OUTPUT_DIR = "transcriptions"

# Fichier de reprise (si le PC s'éteint, le script reprend là où il était)
CHECKPOINT_FILE = "transcription_checkpoint.json"

# Fichier log (pour suivre la progression)
LOG_FILE = "transcription.log"

# Modèle Whisper :
#   "large-v3"        → meilleure qualité anglais/espagnol (recommandé)
#   "medium"          → plus rapide, bonne qualité
#   "small"           → rapide, qualité correcte
#   "distil-large-v3" → presque aussi bon que large-v3, 2x plus rapide
WHISPER_MODEL = "large-v3"

# Extensions vidéo reconnues
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".mpeg", ".3gp", ".m4v", ".flv", ".wmv"}

# ════════════════════════════════════════════════════════════════════════════


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


# ── Tri naturel (Module 2 avant Module 10, 01_intro avant 02_cours) ──────────

def natural_key(name: str) -> list:
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", name)]


def sorted_naturally(paths):
    return sorted(paths, key=lambda p: natural_key(p.name))


# ── Checkpoint (reprise après interruption) ──────────────────────────────────

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


# ── Extraction audio via ffmpeg ───────────────────────────────────────────────

def extract_audio(video_path: Path, audio_path: Path):
    """Extrait la piste audio en MP3 mono 16 kHz (optimal pour Whisper)."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",          # supprimer la vidéo
        "-ac", "1",     # mono
        "-ar", "16000", # 16 000 Hz
        "-b:a", "64k",  # bitrate léger
        str(audio_path),
    ]
    # Sur Windows, cacher la fenêtre ffmpeg
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    result = subprocess.run(
        cmd, capture_output=True, text=True, startupinfo=startupinfo
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg erreur : {result.stderr[-300:]}")


# ── Transcription faster-whisper ─────────────────────────────────────────────

_whisper_model_cache = None  # chargé une seule fois en mémoire

def get_whisper_model():
    global _whisper_model_cache
    if _whisper_model_cache is None:
        log.info(f"Chargement du modèle Whisper '{WHISPER_MODEL}'…")
        log.info("(Premier chargement : téléchargement ~1-3 Go selon le modèle)")
        from faster_whisper import WhisperModel
        _whisper_model_cache = WhisperModel(
            WHISPER_MODEL,
            device="cpu",
            compute_type="int8",  # quantisé int8 = moins de RAM, même qualité
        )
        log.info("Modèle chargé.")
    return _whisper_model_cache


def transcribe_audio(audio_path: Path) -> tuple[str, str]:
    """
    Transcrit le fichier audio.
    Retourne (texte, langue_détectée).
    """
    model = get_whisper_model()
    segments, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        # Pas de langue spécifiée = détection automatique (anglais, espagnol, etc.)
    )
    text = " ".join(seg.text for seg in segments).strip()
    return text, info.language


# ── Traitement d'une vidéo ────────────────────────────────────────────────────

def process_video(video_path: Path, output_txt: Path, checkpoint: dict) -> bool:
    """
    Transcrit une vidéo et sauvegarde le .txt.
    Retourne True si succès, False si erreur.
    """
    key = str(video_path)

    # Déjà fait ? → skip
    if checkpoint.get(key) == "ok" and output_txt.exists():
        log.info(f"  ✓ Déjà transcrit : {video_path.name}")
        return True

    log.info(f"  → Traitement : {video_path.name}")
    output_txt.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, 4):  # 3 tentatives
        try:
            with tempfile.TemporaryDirectory() as tmp:
                audio = Path(tmp) / "audio.mp3"
                extract_audio(video_path, audio)
                text, lang = transcribe_audio(audio)

            # En-tête informatif
            chemin_relatif = str(video_path)
            header = (
                f"=== VIDÉO : {video_path.name} ===\n"
                f"=== DOSSIER : {video_path.parent.name} ===\n"
                f"=== LANGUE DÉTECTÉE : {lang} ===\n\n"
            )
            output_txt.write_text(header + text + "\n", encoding="utf-8")

            checkpoint[key] = "ok"
            save_checkpoint(checkpoint)
            log.info(f"    ✓ Sauvegardé ({lang}) : {output_txt.name}")
            return True

        except Exception as e:
            if attempt < 3:
                wait = 5 * attempt
                log.warning(f"    Tentative {attempt}/3 échouée : {e}. Pause {wait}s…")
                time.sleep(wait)
            else:
                log.error(f"    ✗ ÉCHEC définitif pour {video_path.name} : {e}")
                checkpoint[key] = f"erreur: {e}"
                save_checkpoint(checkpoint)
                return False


# ── Fusion finale ─────────────────────────────────────────────────────────────

def fusionne_tout(output_dir: Path, fichier_final: Path):
    """
    Parcourt output_dir et fusionne tous les .txt dans l'ordre naturel.
    Génère un SOMMAIRE complet en tête de fichier pour guider Claude.
    """
    log.info("\nFusion de tous les .txt en un seul fichier…")

    # Collecter tous les .txt par dossier
    dossiers: dict[Path, list[Path]] = {}
    for txt in output_dir.rglob("*.txt"):
        dossiers.setdefault(txt.parent, []).append(txt)

    # Tri : dossiers du plus profond au plus superficiel, ordre naturel
    dossiers_tries = sorted(
        dossiers.keys(),
        key=lambda p: (-len(p.parts), natural_key(p.name))
    )

    # Construire la liste ordonnée (dossier, [txts]) pour éviter de calculer deux fois
    sections = []
    for dossier in dossiers_tries:
        txts = sorted_naturally(dossiers[dossier])
        try:
            rel = dossier.relative_to(output_dir)
            section_name = str(rel) if str(rel) != "." else "Racine"
        except ValueError:
            section_name = dossier.name
        sections.append((section_name, txts))

    total_videos = sum(len(txts) for _, txts in sections)

    with open(fichier_final, "w", encoding="utf-8") as f:

        # ── EN-TÊTE ────────────────────────────────────────────────────────
        f.write("═" * 70 + "\n")
        f.write("  TRANSCRIPTIONS COMPLÈTES – FORMATIONS SUR LA SÉDUCTION\n")
        f.write(f"  Généré le : {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
        f.write(f"  Nombre de vidéos : {total_videos}\n")
        f.write(f"  Nombre de sections : {len(sections)}\n")
        f.write("═" * 70 + "\n\n")

        # ── SOMMAIRE (index de l'arborescence) ────────────────────────────
        # Ce sommaire sert de "GPS" à Claude : il voit d'un coup d'œil
        # la structure complète avant de lire le premier mot de transcription.
        f.write("┌" + "─" * 68 + "┐\n")
        f.write("│  SOMMAIRE – ARBORESCENCE DES FORMATIONS" + " " * 28 + "│\n")
        f.write("│  (dans l'ordre exact de la fusion)" + " " * 33 + "│\n")
        f.write("└" + "─" * 68 + "┘\n\n")

        num_global = 1
        for section_name, txts in sections:
            # Indentation visuelle selon la profondeur du dossier
            depth = section_name.count("\\") + section_name.count("/")
            indent = "    " * depth
            f.write(f"{indent}📁 {section_name}\n")
            for txt in txts:
                f.write(f"{indent}    [{num_global:03d}] {txt.stem}\n")
                num_global += 1
            f.write("\n")

        f.write("\n" + "═" * 70 + "\n")
        f.write("  FIN DU SOMMAIRE – DÉBUT DES TRANSCRIPTIONS\n")
        f.write("═" * 70 + "\n\n")

        # ── TRANSCRIPTIONS ────────────────────────────────────────────────
        for section_name, txts in sections:
            f.write(f"\n{'─' * 60}\n")
            f.write(f"  SECTION : {section_name}\n")
            f.write(f"{'─' * 60}\n\n")

            for txt in txts:
                f.write(txt.read_text(encoding="utf-8"))
                f.write("\n\n")

    taille_mo = fichier_final.stat().st_size / (1024 * 1024)
    log.info(f"Fichier fusionné : {fichier_final}")
    log.info(f"Taille : {taille_mo:.1f} Mo ({total_videos} vidéos, {len(sections)} sections)")


# ── Programme principal ───────────────────────────────────────────────────────

def main():
    setup_logging()

    # Dossier vidéo = argument en ligne de commande OU dossier courant
    if len(sys.argv) > 1:
        video_root = Path(sys.argv[1])
    else:
        video_root = Path(".")

    video_root = video_root.resolve()
    output_dir = Path(OUTPUT_DIR).resolve()
    fichier_final = Path("transcription_COMPLETE.txt").resolve()

    log.info("═" * 70)
    log.info("  TRANSCRIPTION WHISPER – WINDOWS 10")
    log.info("═" * 70)
    log.info(f"  Dossier vidéos  : {video_root}")
    log.info(f"  Sorties .txt    : {output_dir}")
    log.info(f"  Fichier final   : {fichier_final}")
    log.info(f"  Modèle Whisper  : {WHISPER_MODEL}")
    log.info("═" * 70 + "\n")

    if not video_root.exists():
        log.error(f"Dossier introuvable : {video_root}")
        input("Appuie sur Entrée pour fermer…")
        sys.exit(1)

    # Vérifier ffmpeg
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        log.error("ffmpeg n'est pas installé ou pas dans le PATH.")
        log.error("Télécharge-le sur https://ffmpeg.org/download.html")
        log.error("et ajoute le dossier 'bin' dans les variables d'environnement PATH.")
        input("Appuie sur Entrée pour fermer…")
        sys.exit(1)

    # Collecter toutes les vidéos
    videos = [
        p for p in video_root.rglob("*")
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    ]
    videos = sorted_naturally(videos)

    if not videos:
        log.error(f"Aucune vidéo trouvée dans : {video_root}")
        input("Appuie sur Entrée pour fermer…")
        sys.exit(1)

    log.info(f"Vidéos trouvées : {len(videos)}")
    log.info("Début de la transcription…\n")

    checkpoint = load_checkpoint()
    success = 0
    errors = 0

    for i, video in enumerate(videos, 1):
        # Calculer le chemin de sortie en miroir de l'arborescence
        try:
            rel = video.relative_to(video_root)
        except ValueError:
            rel = Path(video.name)
        output_txt = output_dir / rel.parent / (video.stem + ".txt")

        log.info(f"[{i}/{len(videos)}] {rel}")
        ok = process_video(video, output_txt, checkpoint)
        if ok:
            success += 1
        else:
            errors += 1

    # Résumé
    log.info("\n" + "═" * 70)
    log.info(f"  TERMINÉ : {success} vidéo(s) transcrite(s), {errors} erreur(s)")
    log.info("═" * 70)

    # Fusion finale
    if success > 0:
        fusionne_tout(output_dir, fichier_final)
        log.info("\n✓ Tu peux maintenant donner ces fichiers à Claude pour créer le guide.")
        log.info(f"  Fichier fusionné complet : {fichier_final}")
        log.info(f"  Dossier transcriptions   : {output_dir}")

    if errors > 0:
        log.warning(f"\n⚠ {errors} vidéo(s) n'ont pas pu être transcrites.")
        log.warning("  Consulte transcription.log pour les détails.")
        log.warning("  Relance le script pour réessayer ces vidéos.")

    input("\nAppuie sur Entrée pour fermer…")


if __name__ == "__main__":
    main()
