#!/usr/bin/env python3
"""
Script autonome : Transcription robuste + Fusion intelligente hiérarchique

Ce script fait TOUT en une seule commande :
  1. Parcourt récursivement un dossier de vidéos (avec sous-dossiers)
  2. Transcrit chaque vidéo avec Whisper local (GRATUIT)
  3. Sauvegarde une transcription .txt par vidéo en miroir de l'arborescence
  4. Fusionne de façon hiérarchique et ordonnée (sous-dossiers les plus profonds
     d'abord, ordre naturel des noms de fichiers/dossiers respecté)
  5. Produit un seul fichier merged_transcript.txt final

Robustesse :
  - Reprise automatique après crash (checkpoint JSON)
  - Retry avec backoff exponentiel sur les erreurs transitoires
  - Log détaillé dans whisper_pipeline.log
  - Sauvegarde après chaque vidéo (aucun travail perdu)
  - Ignore les fichiers déjà traités

Usage :
  python transcribe_and_merge.py --video-dir /chemin/vers/tes/formations
  python transcribe_and_merge.py --video-dir /chemin/vers/tes/formations --model medium
  python transcribe_and_merge.py --only-merge   # si transcriptions déjà faites
"""

import argparse
import json
import logging
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path


# ─── Configuration ────────────────────────────────────────────────────────────

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".mpeg", ".3gp", ".m4v", ".flv"}
CHECKPOINT_FILE = "whisper_checkpoint.json"
LOG_FILE = "whisper_pipeline.log"


# ─── Logging ──────────────────────────────────────────────────────────────────

def setup_logging():
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


log = logging.getLogger(__name__)


# ─── Tri naturel ──────────────────────────────────────────────────────────────

def _natural_key(s: str) -> list:
    """
    Clé de tri naturel : "Module 2" < "Module 10", "01_intro" < "02_lesson".
    Trie les nombres comme des entiers, pas comme des chaînes.
    """
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", s)]


def sorted_natural(paths: list[Path]) -> list[Path]:
    return sorted(paths, key=lambda p: _natural_key(p.name))


# ─── Checkpoint ───────────────────────────────────────────────────────────────

def load_checkpoint() -> dict:
    if Path(CHECKPOINT_FILE).exists():
        try:
            return json.loads(Path(CHECKPOINT_FILE).read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_checkpoint(checkpoint: dict):
    Path(CHECKPOINT_FILE).write_text(
        json.dumps(checkpoint, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ─── Extraction audio ─────────────────────────────────────────────────────────

def extract_audio(video_path: Path, audio_path: Path):
    """Extrait l'audio en MP3 mono 16 kHz via ffmpeg."""
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg échoué pour {video_path.name}:\n{result.stderr[-500:]}")


# ─── Transcription Whisper ────────────────────────────────────────────────────

def transcribe_audio(audio_path: Path, model_name: str = "large-v3") -> str:
    """
    Transcrit l'audio avec faster-whisper (4x plus rapide, moins de RAM).
    Détecte automatiquement la langue (anglais, espagnol, etc.).
    Fallback vers openai-whisper si faster-whisper n'est pas installé.
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore

        log.info(f"    faster-whisper '{model_name}' (int8, CPU)…")
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(audio_path), beam_size=5)
        lang = info.language
        prob = info.language_probability
        log.info(f"    Langue détectée : {lang} ({prob:.0%})")
        return " ".join(seg.text for seg in segments).strip()

    except ImportError:
        import whisper  # type: ignore

        log.info(f"    openai-whisper '{model_name}' (fallback)…")
        model = whisper.load_model(model_name)
        result = model.transcribe(str(audio_path), fp16=False)
        lang = result.get("language", "?")
        log.info(f"    Langue détectée : {lang}")
        return result["text"]


def transcribe_with_retry(
    audio_path: Path,
    model_name: str,
    max_retries: int = 3,
) -> str:
    """Transcrit avec retry exponentiel (2s, 4s, 8s)."""
    for attempt in range(1, max_retries + 1):
        try:
            return transcribe_audio(audio_path, model_name)
        except Exception as e:
            if attempt == max_retries:
                raise
            wait = 2 ** attempt
            log.warning(f"    Tentative {attempt}/{max_retries} échouée : {e}. Pause {wait}s…")
            time.sleep(wait)


# ─── Transcription d'une vidéo ────────────────────────────────────────────────

def transcribe_video(
    video_path: Path,
    output_txt: Path,
    model_name: str,
    checkpoint: dict,
) -> bool:
    """
    Transcrit une vidéo et sauvegarde le .txt.
    Retourne True si traité (ou déjà fait), False si erreur non bloquante.
    """
    key = str(video_path)

    if checkpoint.get(key) == "done" and output_txt.exists():
        log.info(f"  [SKIP] Déjà transcrit : {video_path.name}")
        return True

    log.info(f"  Traitement : {video_path}")

    output_txt.parent.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / "audio.mp3"
            log.info(f"    Extraction audio…")
            extract_audio(video_path, audio_path)
            text = transcribe_with_retry(audio_path, model_name)

        header = f"=== {video_path.name} ===\n\n"
        output_txt.write_text(header + text.strip() + "\n", encoding="utf-8")
        checkpoint[key] = "done"
        save_checkpoint(checkpoint)
        log.info(f"    Sauvegardé : {output_txt}")
        return True

    except Exception as e:
        log.error(f"    ERREUR sur {video_path.name} : {e}")
        checkpoint[key] = f"error: {e}"
        save_checkpoint(checkpoint)
        return False


# ─── Parcours et transcription de l'arborescence ─────────────────────────────

def find_and_transcribe(
    video_root: Path,
    transcripts_root: Path,
    model_name: str,
    checkpoint: dict,
) -> dict[Path, list[Path]]:
    """
    Parcourt récursivement video_root, transcrit chaque vidéo,
    et retourne un dict {dossier: [fichiers_txt]} trié naturellement.
    """
    # Collecte tous les dossiers contenant des vidéos
    dir_to_videos: dict[Path, list[Path]] = {}
    for video_path in video_root.rglob("*"):
        if video_path.suffix.lower() in VIDEO_EXTENSIONS and video_path.is_file():
            dir_to_videos.setdefault(video_path.parent, []).append(video_path)

    # Tri naturel des dossiers et des fichiers dans chaque dossier
    total_videos = sum(len(v) for v in dir_to_videos.values())
    log.info(f"Vidéos trouvées : {total_videos} dans {len(dir_to_videos)} dossier(s)")

    done = 0
    errors = 0
    dir_to_txts: dict[Path, list[Path]] = {}

    for folder in sorted_natural(list(dir_to_videos.keys())):
        videos = sorted_natural(dir_to_videos[folder])
        relative_folder = folder.relative_to(video_root)
        txt_folder = transcripts_root / relative_folder
        txts_in_folder = []

        for video in videos:
            output_txt = txt_folder / (video.stem + ".txt")
            ok = transcribe_video(video, output_txt, model_name, checkpoint)
            if ok and output_txt.exists():
                txts_in_folder.append(output_txt)
                done += 1
            else:
                errors += 1

        if txts_in_folder:
            dir_to_txts[folder] = txts_in_folder

    log.info(f"Transcriptions terminées : {done} OK, {errors} erreur(s)")
    return dir_to_txts


# ─── Fusion hiérarchique intelligente ────────────────────────────────────────

def get_all_txt_files(transcripts_root: Path) -> dict[Path, list[Path]]:
    """
    Relit les .txt déjà générés depuis transcripts_root (pour --only-merge).
    """
    dir_to_txts: dict[Path, list[Path]] = {}
    for txt in transcripts_root.rglob("*.txt"):
        if txt.name.startswith("_merged"):
            continue
        dir_to_txts.setdefault(txt.parent, []).append(txt)
    for folder in dir_to_txts:
        dir_to_txts[folder] = sorted_natural(dir_to_txts[folder])
    return dir_to_txts


def build_folder_tree(transcripts_root: Path, dir_to_txts: dict[Path, list[Path]]) -> Path:
    """
    Fusionne les transcriptions de façon hiérarchique :
      - Crée un _merged.txt dans chaque dossier contenant ses vidéos (ordre naturel)
      - Puis fusionne les _merged.txt depuis les sous-dossiers vers les dossiers parents
      - Remonte jusqu'à la racine pour produire le fichier final

    Retourne le chemin du fichier fusionné final.
    """
    # Tous les dossiers triés du plus profond au plus superficiel
    all_dirs = set(dir_to_txts.keys())
    # Ajouter aussi les dossiers intermédiaires (qui n'ont peut-être pas de vidéos directes)
    for d in list(all_dirs):
        p = d
        while p != transcripts_root and p != p.parent:
            all_dirs.add(p)
            p = p.parent

    # Trier du plus profond au plus superficiel (longueur de chemin décroissante)
    sorted_dirs = sorted(all_dirs, key=lambda p: len(p.parts), reverse=True)

    merged_files: dict[Path, Path] = {}  # dossier → son _merged.txt

    for folder in sorted_dirs:
        parts_to_merge = []

        # 1. D'abord les .txt de vidéos directement dans ce dossier (ordre naturel)
        if folder in dir_to_txts:
            parts_to_merge.extend(dir_to_txts[folder])

        # 2. Ensuite les _merged.txt des sous-dossiers directs (ordre naturel)
        try:
            subdirs = sorted_natural([
                d for d in folder.iterdir()
                if d.is_dir() and d in merged_files
            ])
        except Exception:
            subdirs = []
        for subdir in subdirs:
            parts_to_merge.append(merged_files[subdir])

        if not parts_to_merge:
            continue

        # Créer le _merged.txt pour ce dossier
        merged_path = folder / "_merged.txt"
        rel = folder.relative_to(transcripts_root)
        section_title = str(rel) if str(rel) != "." else "ROOT"

        with open(merged_path, "w", encoding="utf-8") as out:
            out.write(f"\n{'='*70}\n")
            out.write(f"  SECTION : {section_title}\n")
            out.write(f"{'='*70}\n\n")
            for part in parts_to_merge:
                content = part.read_text(encoding="utf-8")
                out.write(content)
                out.write("\n\n")

        merged_files[folder] = merged_path
        log.info(f"  Fusionné : {merged_path} ({len(parts_to_merge)} source(s))")

    # Le _merged.txt de la racine = fichier final
    root_merged = merged_files.get(transcripts_root)
    if root_merged is None:
        # Si la racine n'est pas dans merged_files, prendre le seul dossier de premier niveau
        first_level = [p for p in merged_files if p.parent == transcripts_root]
        if first_level:
            root_merged = merged_files[sorted_natural(first_level)[0]]
        else:
            # Dernier recours : fusionner tout à plat
            root_merged = transcripts_root / "_merged.txt"
            all_txts = sorted_natural([
                p for p in transcripts_root.rglob("*.txt")
                if not p.name.startswith("_merged")
            ])
            with open(root_merged, "w", encoding="utf-8") as out:
                for t in all_txts:
                    out.write(t.read_text(encoding="utf-8") + "\n\n")

    return root_merged


def produce_final_merged(merged_root: Path, output_file: Path):
    """Copie le fichier fusionné final vers output_file."""
    content = merged_root.read_text(encoding="utf-8")
    header = (
        "=== TRANSCRIPTIONS COMPLÈTES – FORMATIONS SUR LA SÉDUCTION ===\n"
        "=== Généré automatiquement – prêt pour Claude / Gemini       ===\n\n"
    )
    output_file.write_text(header + content, encoding="utf-8")
    size_mb = output_file.stat().st_size / (1024 * 1024)
    log.info(f"\nFichier final : {output_file}")
    log.info(f"Taille        : {size_mb:.1f} Mo ({len(content):,} caractères)")


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Transcription Whisper + Fusion hiérarchique intelligente"
    )
    parser.add_argument(
        "--video-dir",
        default=".",
        help="Dossier racine contenant les vidéos (avec sous-dossiers). Défaut : répertoire courant.",
    )
    parser.add_argument(
        "--transcripts-dir",
        default="transcripts",
        help="Dossier de sortie des transcriptions .txt. Défaut : transcripts/",
    )
    parser.add_argument(
        "--output",
        default="merged_transcript.txt",
        help="Fichier texte fusionné final. Défaut : merged_transcript.txt",
    )
    parser.add_argument(
        "--model",
        choices=["tiny", "base", "small", "medium", "large", "large-v2", "large-v3", "distil-large-v3"],
        default="large-v3",
        help=(
            "Modèle faster-whisper à utiliser. Défaut : large-v3.\n"
            "  tiny/base         : très rapide, qualité réduite\n"
            "  small             : bon compromis vitesse/qualité\n"
            "  medium            : qualité correcte, RAM modérée\n"
            "  large-v3          : recommandé – meilleure qualité EN/ES (défaut)\n"
            "  distil-large-v3   : 2x plus rapide que large-v3, qualité proche"
        ),
    )
    parser.add_argument(
        "--only-merge",
        action="store_true",
        help="Sauter la transcription et ne faire que la fusion (si .txt déjà générés).",
    )
    parser.add_argument(
        "--only-transcribe",
        action="store_true",
        help="Faire uniquement la transcription, sans fusion.",
    )
    return parser.parse_args()


def main():
    setup_logging()
    args = parse_args()

    video_root = Path(args.video_dir).resolve()
    transcripts_root = Path(args.transcripts_dir).resolve()
    output_file = Path(args.output).resolve()

    log.info("=" * 70)
    log.info("  PIPELINE WHISPER – TRANSCRIPTION & FUSION HIÉRARCHIQUE")
    log.info("=" * 70)
    log.info(f"  Dossier vidéos      : {video_root}")
    log.info(f"  Dossier transcripts : {transcripts_root}")
    log.info(f"  Fichier final       : {output_file}")
    log.info(f"  Modèle Whisper      : {args.model}")
    log.info("=" * 70)

    checkpoint = load_checkpoint()

    # ── Étape 1 : Transcription ────────────────────────────────────────────────
    if not args.only_merge:
        if not video_root.exists():
            log.error(f"Dossier vidéo introuvable : {video_root}")
            sys.exit(1)
        dir_to_txts = find_and_transcribe(video_root, transcripts_root, args.model, checkpoint)
    else:
        log.info("Mode --only-merge : lecture des .txt existants…")
        dir_to_txts = get_all_txt_files(transcripts_root)

    if args.only_transcribe:
        log.info("Mode --only-transcribe : fusion ignorée.")
        return

    # ── Étape 2 : Fusion hiérarchique ─────────────────────────────────────────
    if not dir_to_txts:
        # Relire depuis le dossier transcripts si vide (ex: reprise après crash)
        dir_to_txts = get_all_txt_files(transcripts_root)

    if not dir_to_txts:
        log.error("Aucun fichier .txt trouvé. Vérifie le dossier transcripts.")
        sys.exit(1)

    log.info(f"\nFusion hiérarchique ({len(dir_to_txts)} dossier(s))…")
    merged_root = build_folder_tree(transcripts_root, dir_to_txts)
    produce_final_merged(merged_root, output_file)

    log.info("\n" + "=" * 70)
    log.info("  TERMINÉ !")
    log.info(f"  Fichier final prêt : {output_file}")
    log.info("=" * 70)
    log.info("\nProchaine étape : donne ce fichier à Claude pour générer le guide.")
    log.info("  python main.py --steps generate --guide-engine claude")


if __name__ == "__main__":
    main()
