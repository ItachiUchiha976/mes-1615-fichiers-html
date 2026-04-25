"""
Module 2 – Transcription audio/vidéo → texte.

Deux moteurs disponibles :
  - "whisper_local"  : openai-whisper tournant localement (CPU/GPU, gratuit)
  - "whisper_api"    : API OpenAI Whisper (cloud, payant, plus rapide)

Le module extrait d'abord l'audio de la vidéo (via ffmpeg),
puis transcrit chunk par chunk si le fichier est trop long pour l'API cloud
(limite OpenAI : 25 Mo par appel).
"""

import os
import subprocess
import tempfile
from pathlib import Path

from tqdm import tqdm


# ─── Extraction audio ─────────────────────────────────────────────────────────

def extract_audio(video_path: Path, audio_path: Path) -> Path:
    """Extrait la piste audio d'une vidéo en MP3 mono 16 kHz."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",                  # pas de vidéo
        "-ac", "1",             # mono
        "-ar", "16000",         # 16 kHz (optimal Whisper)
        "-b:a", "64k",          # bitrate léger
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg a échoué pour {video_path.name}:\n{result.stderr}"
        )
    return audio_path


def split_audio(audio_path: Path, chunk_duration_s: int = 600) -> list[Path]:
    """
    Coupe l'audio en segments de chunk_duration_s secondes.
    Nécessaire pour l'API OpenAI (limite 25 Mo ≈ 10 min à 64 kbps).
    Retourne la liste des chemins des segments.
    """
    out_dir = audio_path.parent / (audio_path.stem + "_chunks")
    out_dir.mkdir(exist_ok=True)

    pattern = str(out_dir / "chunk_%04d.mp3")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(audio_path),
        "-f", "segment",
        "-segment_time", str(chunk_duration_s),
        "-c", "copy",
        pattern,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg split a échoué:\n{result.stderr}")

    chunks = sorted(out_dir.glob("chunk_*.mp3"))
    return chunks


# ─── Moteurs de transcription ─────────────────────────────────────────────────

def _transcribe_whisper_local(audio_path: Path, language: str | None = None) -> str:
    """
    Transcrit avec faster-whisper large-v3 (4x plus rapide que Whisper standard,
    moins de RAM, même qualité). Détecte automatiquement anglais/espagnol.
    Fallback vers openai-whisper si faster-whisper n'est pas installé.
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore

        model = WhisperModel("large-v3", device="cpu", compute_type="int8")
        segments, info = model.transcribe(
            str(audio_path),
            language=language,  # None = détection auto
            beam_size=5,
        )
        detected = info.language
        print(f"    Langue détectée : {detected} (prob: {info.language_probability:.0%})")
        return " ".join(seg.text for seg in segments).strip()

    except ImportError:
        # Fallback : openai-whisper classique
        import whisper  # type: ignore

        model = whisper.load_model("medium")
        kwargs = {"fp16": False}
        if language:
            kwargs["language"] = language
        result = model.transcribe(str(audio_path), **kwargs)
        detected = result.get("language", "?")
        print(f"    Langue détectée : {detected}")
        return result["text"]


def _transcribe_whisper_api(audio_path: Path, language: str | None = None) -> str:
    """
    Transcrit via l'API OpenAI Whisper.
    Si language=None, Whisper détecte automatiquement (anglais, espagnol, etc.).
    Si le fichier dépasse 25 Mo, le découpe automatiquement.
    """
    from openai import OpenAI  # type: ignore

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    file_size_mb = audio_path.stat().st_size / (1024 * 1024)

    def _transcribe_chunk(f):
        kwargs = {"model": "whisper-1", "file": f}
        if language:
            kwargs["language"] = language
        return client.audio.transcriptions.create(**kwargs).text

    if file_size_mb <= 24:
        with open(audio_path, "rb") as f:
            return _transcribe_chunk(f)
    else:
        chunks = split_audio(audio_path, chunk_duration_s=600)
        texts = []
        for chunk in tqdm(chunks, desc=f"  Chunks {audio_path.name[:30]}", leave=False):
            with open(chunk, "rb") as f:
                texts.append(_transcribe_chunk(f))
        return " ".join(texts)


# ─── Point d'entrée principal ─────────────────────────────────────────────────

def transcribe_video(
    video_path: Path,
    transcripts_dir: Path,
    engine: str = "whisper_local",
    language: str | None = None,
    skip_existing: bool = True,
) -> Path:
    """
    Transcrit une vidéo et sauvegarde le résultat dans transcripts_dir/<nom>.txt.
    Retourne le chemin du fichier texte.
    """
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = transcripts_dir / (video_path.stem + ".txt")

    if skip_existing and transcript_path.exists():
        print(f"  [SKIP] Transcription existante : {transcript_path.name}")
        return transcript_path

    print(f"  Extraction audio : {video_path.name}")
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = Path(tmpdir) / (video_path.stem + ".mp3")
        extract_audio(video_path, audio_path)

        print(f"  Transcription ({engine}) : {video_path.name}")
        if engine == "whisper_local":
            text = _transcribe_whisper_local(audio_path, language)
        elif engine == "whisper_api":
            text = _transcribe_whisper_api(audio_path, language)
        else:
            raise ValueError(f"Moteur inconnu : {engine}. Choisir 'whisper_local' ou 'whisper_api'.")

    # Ajoute un en-tête pour faciliter la fusion
    header = f"=== TRANSCRIPTION : {video_path.name} ===\n\n"
    transcript_path.write_text(header + text.strip() + "\n", encoding="utf-8")
    print(f"  Sauvegardé : {transcript_path}")
    return transcript_path


def run(
    video_paths: list[Path],
    transcripts_dir: Path,
    engine: str = "whisper_local",
    language: str | None = None,
) -> list[Path]:
    """
    Transcrit toutes les vidéos et retourne la liste des fichiers .txt.
    """
    transcript_files = []
    for video in tqdm(video_paths, desc="Transcription des vidéos"):
        try:
            tp = transcribe_video(video, transcripts_dir, engine, language)
            transcript_files.append(tp)
        except Exception as e:
            print(f"  [ERREUR] {video.name} : {e}")
    return transcript_files
