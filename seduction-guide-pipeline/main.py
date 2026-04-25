#!/usr/bin/env python3
"""
Pipeline principal – De Google Drive au Guide de Séduction Complet.

Usage :
  python main.py --help

Étapes :
  1. (optionnel) Télécharger les vidéos depuis Google Drive
  2. Transcrire les vidéos en texte (Whisper local ou API)
  3. Fusionner toutes les transcriptions en un seul fichier
  4. Générer le guide complet via Gemini 1.5 Pro
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def parse_args():
    parser = argparse.ArgumentParser(
        description="Pipeline : Vidéos → Transcription → Guide de Séduction (Gemini)"
    )

    # ── Étapes à exécuter ──────────────────────────────────────────────────────
    parser.add_argument(
        "--steps",
        nargs="+",
        choices=["download", "transcribe", "merge", "generate", "all"],
        default=["all"],
        help=(
            "Étapes à exécuter : download, transcribe, merge, generate, all. "
            "Défaut : all."
        ),
    )

    # ── Google Drive ───────────────────────────────────────────────────────────
    parser.add_argument(
        "--folder-id",
        default=None,
        help=(
            "ID du dossier Google Drive contenant les vidéos. "
            "Visible dans l'URL : drive.google.com/drive/folders/<FOLDER_ID>. "
            "Si absent, cherche dans tout le Drive."
        ),
    )
    parser.add_argument(
        "--credentials",
        default=None,
        help="Chemin vers credentials.json OAuth2 Google (défaut : $GDRIVE_CREDENTIALS_FILE).",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Chemin vers token.json de cache OAuth2 (défaut : $GDRIVE_TOKEN_FILE).",
    )

    # ── Transcription ──────────────────────────────────────────────────────────
    parser.add_argument(
        "--engine",
        choices=["whisper_local", "whisper_api"],
        default="whisper_local",
        help="Moteur de transcription : whisper_local (défaut) ou whisper_api (OpenAI, payant).",
    )
    parser.add_argument(
        "--language",
        default="fr",
        help="Code langue pour Whisper (ex: fr, en). Défaut : fr.",
    )
    parser.add_argument(
        "--video-dir",
        default=None,
        help=(
            "Dossier contenant des vidéos déjà téléchargées. "
            "Utilisé si tu sautes l'étape download."
        ),
    )

    # ── Répertoires ────────────────────────────────────────────────────────────
    parser.add_argument(
        "--download-dir",
        default=None,
        help="Dossier de téléchargement des vidéos (défaut : $DOWNLOAD_DIR ou 'downloads').",
    )
    parser.add_argument(
        "--transcripts-dir",
        default=None,
        help="Dossier des transcriptions (défaut : $TRANSCRIPTS_DIR ou 'transcripts').",
    )
    parser.add_argument(
        "--merged-file",
        default=None,
        help="Fichier texte fusionné (défaut : $MERGED_TRANSCRIPT ou 'merged_transcript.txt').",
    )
    parser.add_argument(
        "--output-guide",
        default=None,
        help="Fichier guide final Markdown (défaut : $OUTPUT_GUIDE ou 'guide_seduction_complet.md').",
    )

    return parser.parse_args()


def resolve_paths(args) -> dict:
    """Résout les chemins depuis les arguments ou les variables d'environnement."""
    return {
        "credentials": args.credentials or os.environ.get("GDRIVE_CREDENTIALS_FILE", "credentials.json"),
        "token": args.token or os.environ.get("GDRIVE_TOKEN_FILE", "token.json"),
        "download_dir": Path(args.download_dir or os.environ.get("DOWNLOAD_DIR", "downloads")),
        "transcripts_dir": Path(args.transcripts_dir or os.environ.get("TRANSCRIPTS_DIR", "transcripts")),
        "merged_file": Path(args.merged_file or os.environ.get("MERGED_TRANSCRIPT", "merged_transcript.txt")),
        "output_guide": Path(args.output_guide or os.environ.get("OUTPUT_GUIDE", "guide_seduction_complet.md")),
    }


def should_run(step: str, steps: list[str]) -> bool:
    return "all" in steps or step in steps


def main():
    load_dotenv()
    args = parse_args()
    paths = resolve_paths(args)
    steps = args.steps

    print("\n" + "=" * 60)
    print("  PIPELINE : VIDÉOS → GUIDE DE SÉDUCTION")
    print("=" * 60)
    print(f"  Étapes : {', '.join(steps)}")
    print(f"  Moteur  : {args.engine}")
    print(f"  Langue  : {args.language}")
    print("=" * 60 + "\n")

    video_paths = []

    # ── ÉTAPE 1 : Téléchargement Google Drive ──────────────────────────────────
    if should_run("download", steps):
        print("▶ Étape 1 : Téléchargement Google Drive")
        import gdrive_downloader

        video_paths = gdrive_downloader.run(
            credentials_file=paths["credentials"],
            token_file=paths["token"],
            download_dir=str(paths["download_dir"]),
            folder_id=args.folder_id,
        )
        print(f"  {len(video_paths)} vidéo(s) téléchargée(s).\n")
    else:
        # Si on saute le téléchargement, on lit depuis --video-dir ou --download-dir
        src_dir = Path(args.video_dir) if args.video_dir else paths["download_dir"]
        if src_dir.exists():
            extensions = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".mpeg", ".3gp"}
            video_paths = [p for p in src_dir.iterdir() if p.suffix.lower() in extensions]
            print(f"  Vidéos locales trouvées dans {src_dir} : {len(video_paths)}\n")
        else:
            print(f"  Avertissement : dossier vidéo introuvable ({src_dir}).")

    # ── ÉTAPE 2 : Transcription ────────────────────────────────────────────────
    if should_run("transcribe", steps):
        if not video_paths:
            print("  Aucune vidéo à transcrire. Vérifiez --video-dir ou exécutez l'étape download.")
            if "all" in steps:
                sys.exit(1)
        else:
            print(f"▶ Étape 2 : Transcription ({len(video_paths)} vidéo(s), moteur : {args.engine})")
            import transcriber

            transcript_files = transcriber.run(
                video_paths=video_paths,
                transcripts_dir=paths["transcripts_dir"],
                engine=args.engine,
                language=args.language,
            )
            print(f"  {len(transcript_files)} transcription(s) terminée(s).\n")

    # ── ÉTAPE 3 : Fusion ───────────────────────────────────────────────────────
    if should_run("merge", steps):
        print("▶ Étape 3 : Fusion des transcriptions")
        import merger

        merger.run(
            transcripts_dir=paths["transcripts_dir"],
            output_file=paths["merged_file"],
        )
        print()

    # ── ÉTAPE 4 : Génération du guide ──────────────────────────────────────────
    if should_run("generate", steps):
        if not paths["merged_file"].exists():
            print(f"  Erreur : fichier fusionné introuvable ({paths['merged_file']}).")
            print("  Lance d'abord les étapes transcribe + merge.")
            sys.exit(1)

        print("▶ Étape 4 : Génération du guide (Gemini 1.5 Pro)")
        import guide_generator

        guide_generator.run(
            merged_transcript_path=paths["merged_file"],
            output_guide_path=paths["output_guide"],
        )
        print()

    print("=" * 60)
    print(f"  TERMINÉ ! Guide disponible : {paths['output_guide']}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
