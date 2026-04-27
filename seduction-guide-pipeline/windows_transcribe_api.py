#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TRANSCRIPTION VIA API OPENAI WHISPER - WINDOWS 10
===================================================
Transcrit toutes les videos et audios via le cloud OpenAI.
Beaucoup plus rapide que le traitement local : ~30 a 90 min pour 50h de contenu.

COUT : $0.006 par minute audio
  Exemple : 50h = 3000 min x $0.006 = ~18$

QUALITE : whisper-1 (equivalent large-v2, excellent)

INSTALLATION :
  pip install openai

USAGE :
  1. Entre ta cle API OpenAI ci-dessous (OPENAI_API_KEY)
  2. Double-clique sur ce fichier
  3. Le script calcule d'abord le cout total, tu confirmes, puis ca demarre
"""

import json
import logging
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from datetime import datetime


# ================================================================================
#  CONFIGURATION - METS TA CLE API ICI
# ================================================================================

OPENAI_API_KEY = "sk-METS_TA_CLE_ICI"

OUTPUT_DIR      = "transcriptions"
CHECKPOINT_FILE = "transcription_api_checkpoint.json"
LOG_FILE        = "transcription_api.log"

# Taille max par partie de sortie (3.5 Mo = safe pour claude.ai)
MAX_BYTES_PAR_PARTIE = int(3.5 * 1024 * 1024)

# Limite API OpenAI Whisper : 25 Mo par appel -> on decoupe par segments de 10 min
MAX_CHUNK_MB    = 24
CHUNK_DURATION_S = 600  # 10 minutes

VIDEO_EXTENSIONS = {
    ".mp4", ".avi", ".mov", ".mkv", ".webm",
    ".mpeg", ".3gp", ".m4v", ".flv", ".wmv"
}
AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".aac", ".ogg", ".wma", ".m4a", ".opus", ".flac"
}
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


# -- Selecteur de dossier --------------------------------------------------------

def demander_dossier() -> Path:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        print("\nUne fenetre de selection de dossier va s'ouvrir...")
        print("Choisis le dossier PRINCIPAL qui contient toutes tes formations.\n")
        dossier = filedialog.askdirectory(
            title="Choisis le dossier contenant tes formations"
        )
        root.destroy()
        return Path(dossier) if dossier else Path(".")
    except Exception as e:
        print(f"Fenetre impossible ({e}). Utilisation du dossier courant.")
        return Path(".")


# -- Tri naturel -----------------------------------------------------------------

def natural_key(name: str) -> list:
    return [int(c) if c.isdigit() else c.lower()
            for c in re.split(r"(\d+)", name)]

def sorted_naturally(paths):
    return sorted(paths, key=lambda p: natural_key(p.name))


# -- Checkpoint ------------------------------------------------------------------

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


# -- Duree des fichiers (pour estimation du cout) --------------------------------

def get_duration_seconds(media_path: Path) -> float:
    """Retourne la duree en secondes via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(media_path)
    ]
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                startupinfo=startupinfo, timeout=30)
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception:
        return 0.0


# -- Extraction audio ------------------------------------------------------------

def extract_audio(media_path: Path, audio_path: Path):
    """Convertit video ou audio en MP3 mono 16 kHz."""
    cmd = [
        "ffmpeg", "-y", "-i", str(media_path),
        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k",
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


def split_audio_chunks(audio_path: Path, out_dir: Path) -> list:
    """Coupe l'audio en segments de 10 minutes (limite API 25 Mo)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "chunk_%04d.mp3")
    cmd = [
        "ffmpeg", "-y", "-i", str(audio_path),
        "-f", "segment",
        "-segment_time", str(CHUNK_DURATION_S),
        "-c", "copy", pattern
    ]
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    subprocess.run(cmd, capture_output=True, startupinfo=startupinfo)
    return sorted(out_dir.glob("chunk_*.mp3"))


# -- Transcription API -----------------------------------------------------------

def transcribe_with_api(audio_path: Path) -> tuple:
    """
    Envoie l'audio a l'API OpenAI Whisper.
    Si le fichier depasse 24 Mo, le decoupe automatiquement en segments.
    Retourne (texte_complet, langue_detectee).
    """
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

    file_size_mb = audio_path.stat().st_size / (1024 * 1024)

    if file_size_mb <= MAX_CHUNK_MB:
        with open(audio_path, "rb") as f:
            resp = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json"
            )
        lang = getattr(resp, "language", "en")
        return resp.text.strip(), lang
    else:
        log.info(f"    Fichier {file_size_mb:.0f} Mo > 24 Mo -> decoupage en segments...")
        chunks_dir = audio_path.parent / (audio_path.stem + "_chunks")
        chunks = split_audio_chunks(audio_path, chunks_dir)
        texts = []
        lang = "en"
        for j, chunk in enumerate(chunks, 1):
            log.info(f"    Segment {j}/{len(chunks)} ({chunk.stem})...")
            with open(chunk, "rb") as f:
                resp = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    response_format="verbose_json"
                )
            texts.append(resp.text.strip())
            if j == 1:
                lang = getattr(resp, "language", "en")
        return " ".join(texts), lang


# -- Suivi de progression --------------------------------------------------------

def format_duree(secondes: float) -> str:
    s = int(secondes)
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    if h > 0:
        return f"{h}h{m:02d}m{sec:02d}s"
    return f"{m}m{sec:02d}s"

def affiche_barre(i, total, debut_global, success, errors, durees):
    pct = i / total * 100
    elapsed = time.time() - debut_global
    eta_str = format_duree((sum(durees)/len(durees)) * (total - i)) if durees else "calcul..."
    largeur = 28
    rempli = int(largeur * i / total)
    barre = "#" * rempli + "-" * (largeur - rempli)
    log.info(
        f"  [{barre}] {pct:5.1f}%  {i}/{total}  |  "
        f"OK:{success} Err:{errors}  |  "
        f"Ecoule: {format_duree(elapsed)}  |  Reste estim.: {eta_str}"
    )


# -- Traitement d'un fichier -----------------------------------------------------

def process_media(media_path: Path, output_txt: Path, checkpoint: dict) -> tuple:
    key = str(media_path)

    if checkpoint.get(key) == "ok" and output_txt.exists():
        log.info(f"  [SKIP] Deja transcrit : {media_path.name}")
        return True, 0.0

    type_f = "AUDIO" if media_path.suffix.lower() in AUDIO_EXTENSIONS else "VIDEO"
    log.info(f"  --> [{type_f}] {media_path.name}")
    output_txt.parent.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    for attempt in range(1, 4):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                audio = Path(tmp) / "audio.mp3"
                extract_audio(media_path, audio)
                text, lang = transcribe_with_api(audio)

            header = (
                f"=== FICHIER : {media_path.name} ===\n"
                f"=== TYPE : {type_f} ===\n"
                f"=== DOSSIER : {media_path.parent.name} ===\n"
                f"=== LANGUE DETECTEE : {lang} ===\n\n"
            )
            output_txt.write_text(header + text + "\n", encoding="utf-8")
            checkpoint[key] = "ok"
            save_checkpoint(checkpoint)
            duree = time.time() - t_start
            log.info(f"    OK ({lang}) en {format_duree(duree)}")
            return True, duree

        except Exception as e:
            if attempt < 3:
                wait = 15 * attempt
                log.warning(f"    Tentative {attempt}/3 echouee : {e}. Pause {wait}s...")
                time.sleep(wait)
            else:
                log.error(f"    ECHEC definitif : {media_path.name} -> {e}")
                checkpoint[key] = f"erreur: {e}"
                save_checkpoint(checkpoint)
                return False, 0.0


# -- Fusion finale ---------------------------------------------------------------

def fusionne_tout(output_dir: Path, base_name: str = "transcription_COMPLETE"):
    log.info("\nFusion et decoupage automatique des .txt...")

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

    total_fichiers = sum(len(t) for _, t in sections)
    date_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    def ouvre_partie(num: int):
        nom_f = f"{base_name}_PARTIE_{num}.txt"
        f = open(nom_f, "w", encoding="utf-8")
        f.write("=" * 70 + "\n")
        f.write("  TRANSCRIPTIONS - FORMATIONS SUR LA SEDUCTION\n")
        f.write(f"  PARTIE {num} | Genere le : {date_str}\n")
        f.write(f"  Total fichiers (toutes parties) : {total_fichiers}\n")
        f.write("=" * 70 + "\n\n")
        return f, nom_f

    partie_num = 1
    f, nom_courant = ouvre_partie(partie_num)
    octets = 0
    fichiers_crees = [nom_courant]

    # Sommaire GPS
    lignes = [
        "+" + "-" * 68 + "+\n",
        "|  SOMMAIRE - ARBORESCENCE COMPLETE DES FORMATIONS                |\n",
        "|  (dans l'ordre exact ou les transcriptions apparaissent)         |\n",
        "+" + "-" * 68 + "+\n\n"
    ]
    num = 1
    for nom_section, txts in sections:
        depth = nom_section.count("\\") + nom_section.count("/")
        indent = "    " * depth
        lignes.append(f"{indent}[DOSSIER] {nom_section}\n")
        for txt in txts:
            lignes.append(f"{indent}    [{num:03d}] {txt.stem}\n")
            num += 1
        lignes.append("\n")
    lignes += ["\n" + "=" * 70 + "\n",
               "  FIN DU SOMMAIRE - DEBUT DES TRANSCRIPTIONS\n",
               "=" * 70 + "\n\n"]

    bloc = "".join(lignes)
    f.write(bloc)
    octets += len(bloc.encode("utf-8"))

    for nom_section, txts in sections:
        header = ("\n" + "-" * 60 + "\n"
                  f"  SECTION : {nom_section}\n"
                  + "-" * 60 + "\n\n")
        hb = len(header.encode("utf-8"))
        if octets + hb > MAX_BYTES_PAR_PARTIE:
            f.close()
            log.info(f"  -> Partie {partie_num} terminee ({octets/1024/1024:.1f} Mo)")
            partie_num += 1
            f, nom_courant = ouvre_partie(partie_num)
            fichiers_crees.append(nom_courant)
            octets = 0
        f.write(header)
        octets += hb

        for txt in txts:
            contenu = txt.read_text(encoding="utf-8") + "\n\n"
            cb = len(contenu.encode("utf-8"))
            if octets > 0 and octets + cb > MAX_BYTES_PAR_PARTIE:
                f.close()
                log.info(f"  -> Partie {partie_num} terminee ({octets/1024/1024:.1f} Mo)")
                partie_num += 1
                f, nom_courant = ouvre_partie(partie_num)
                fichiers_crees.append(nom_courant)
                octets = 0
            f.write(contenu)
            octets += cb

    f.close()
    log.info(f"  -> Partie {partie_num} terminee ({octets/1024/1024:.1f} Mo)")
    log.info(f"\nFusion terminee : {partie_num} fichier(s)")
    for nf in fichiers_crees:
        taille = Path(nf).stat().st_size / 1024 / 1024
        log.info(f"  {nf}  ({taille:.1f} Mo)")
    return fichiers_crees


# -- Programme principal ---------------------------------------------------------

def main():
    setup_logging()

    # Verifier la cle API
    if OPENAI_API_KEY == "sk-METS_TA_CLE_ICI":
        print("\n" + "=" * 70)
        print("  ERREUR : Cle API OpenAI manquante !")
        print("=" * 70)
        print("\nOuvre ce fichier avec Notepad++ et remplace :")
        print("  sk-METS_TA_CLE_ICI")
        print("par ta vraie cle API (elle commence par sk-proj-... ou sk-...)")
        print("\nPour obtenir une cle : https://platform.openai.com/api-keys")
        input("\nAppuie sur Entree pour fermer...")
        sys.exit(1)

    # Verifier ffmpeg
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("ERREUR : ffmpeg n'est pas installe.")
        print("Lance : winget install ffmpeg  (dans cmd administrateur)")
        input("\nAppuie sur Entree pour fermer...")
        sys.exit(1)

    # Choisir le dossier
    if len(sys.argv) > 1:
        media_root = Path(sys.argv[1])
    else:
        media_root = demander_dossier()
    media_root = media_root.resolve()
    output_dir = Path(OUTPUT_DIR).resolve()

    log.info("=" * 70)
    log.info("  TRANSCRIPTION VIA API OPENAI WHISPER")
    log.info("=" * 70)
    log.info(f"  Dossier source     : {media_root}")
    log.info(f"  Sorties .txt       : {output_dir}")
    log.info(f"  Modele API         : whisper-1 (equivalent large-v2)")
    log.info(f"  Taille max/partie  : {MAX_BYTES_PAR_PARTIE/1024/1024:.1f} Mo")
    log.info("=" * 70 + "\n")

    # Collecter les fichiers
    medias = sorted_naturally([
        p for p in media_root.rglob("*")
        if p.is_file() and p.suffix.lower() in ALL_MEDIA_EXTENSIONS
    ])

    if not medias:
        log.error(f"Aucun fichier video/audio trouve dans : {media_root}")
        input("Appuie sur Entree pour fermer...")
        sys.exit(1)

    nb_videos = sum(1 for m in medias if m.suffix.lower() in VIDEO_EXTENSIONS)
    nb_audios  = sum(1 for m in medias if m.suffix.lower() in AUDIO_EXTENSIONS)
    log.info(f"Fichiers trouves : {len(medias)} ({nb_videos} videos, {nb_audios} audios)")

    # Calcul de la duree totale et du cout estime
    log.info("\nCalcul de la duree totale pour estimer le cout...")
    log.info("(Analyse de chaque fichier via ffprobe, 1-3 minutes...)\n")

    duree_totale_s = 0.0
    for i, m in enumerate(medias, 1):
        d = get_duration_seconds(m)
        duree_totale_s += d
        print(f"\r  Analyse {i}/{len(medias)} : {m.name[:50]:<50}", end="", flush=True)

    print()  # retour a la ligne

    duree_min = duree_totale_s / 60
    cout = duree_min * 0.006
    marge = cout + 3  # +3$ de marge de securite

    log.info("\n" + "=" * 70)
    log.info("  ESTIMATION DU COUT AVANT DE COMMENCER")
    log.info("=" * 70)
    log.info(f"  Duree totale des fichiers : {format_duree(duree_totale_s)}"
             f"  ({duree_min:.0f} minutes)")
    log.info(f"  Tarif API OpenAI Whisper  : $0.006 / minute")
    log.info(f"  COUT ESTIME               : ${cout:.2f}")
    log.info(f"  Recommandation credits    : au moins ${marge:.0f}"
             f" (cout + marge de securite)")
    log.info(f"  Duree du traitement       : ~30 a 90 minutes")
    log.info("=" * 70)
    log.info(f"\n  Verifie que ton compte OpenAI a au moins ${marge:.0f} de credits")
    log.info(f"  sur : https://platform.openai.com/usage")
    log.info("")

    reponse = input("Continuer la transcription ? (oui / non) : ").strip().lower()
    if reponse not in ("oui", "o", "yes", "y"):
        print("Annule. Recharge tes credits puis relance.")
        sys.exit(0)

    # Lancement
    checkpoint = load_checkpoint()
    total = len(medias)
    deja = sum(1 for m in medias if checkpoint.get(str(m)) == "ok")
    log.info(f"\nDeja transcrits   : {deja} (seront ignores [SKIP])")
    log.info(f"Restant a traiter : {total - deja}")
    log.info("Debut de la transcription via API OpenAI...\n")

    success, errors = 0, 0
    durees = []
    debut_global = time.time()

    for i, media in enumerate(medias, 1):
        try:
            rel = media.relative_to(media_root)
        except ValueError:
            rel = Path(media.name)

        output_txt = output_dir / rel.parent / (media.stem + ".txt")
        log.info(f"\n[{i}/{total}] {rel}")

        ok, duree = process_media(media, output_txt, checkpoint)
        if ok:
            success += 1
            if duree > 1.0:
                durees.append(duree)
        else:
            errors += 1

        affiche_barre(i, total, debut_global, success, errors, durees)

    temps_total = time.time() - debut_global
    log.info("\n" + "=" * 70)
    log.info("  TERMINE !")
    log.info(f"  Transcrits avec succes : {success}/{total}")
    log.info(f"  Erreurs                : {errors}")
    log.info(f"  Temps total            : {format_duree(temps_total)}")
    log.info(f"  Cout reel (estime)     : ${(duree_min * 0.006):.2f}")
    log.info("=" * 70)

    if success > 0:
        fichiers = fusionne_tout(output_dir)
        nb = len(fichiers)
        log.info(f"\nProchaine etape - uploade les {nb} fichier(s) sur claude.ai :")
        for fich in fichiers:
            log.info(f"  {Path(fich).resolve()}")
        if nb > 1:
            log.info("\n  Envoie-les un par un dans la meme conversation Claude.")
            log.info("  Commence par : 'Voici la partie 1, lis tout avant de creer le guide.'")

    if errors > 0:
        log.warning(f"\n{errors} fichier(s) ont echoue.")
        log.warning("Relance le script pour reessayer automatiquement.")

    input("\nAppuie sur Entree pour fermer...")


if __name__ == "__main__":
    main()
