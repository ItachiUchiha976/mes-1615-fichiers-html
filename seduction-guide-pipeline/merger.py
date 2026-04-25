"""
Module 3 – Fusion des transcriptions en un seul fichier texte.

Concatène tous les fichiers .txt du dossier transcripts/
et sauvegarde le résultat dans merged_transcript.txt.
"""

from pathlib import Path


def run(transcripts_dir: Path, output_file: Path) -> Path:
    """
    Fusionne tous les fichiers .txt de transcripts_dir dans output_file.
    Retourne le chemin du fichier fusionné.
    """
    txt_files = sorted(transcripts_dir.glob("*.txt"))
    if not txt_files:
        raise FileNotFoundError(
            f"Aucun fichier .txt trouvé dans : {transcripts_dir}"
        )

    print(f"Fusion de {len(txt_files)} transcription(s)…")
    total_chars = 0

    with open(output_file, "w", encoding="utf-8") as out:
        out.write(
            "=== TRANSCRIPTIONS FUSIONNÉES – FORMATIONS SUR LA SÉDUCTION ===\n\n"
        )
        for txt_file in txt_files:
            content = txt_file.read_text(encoding="utf-8")
            out.write(content)
            out.write("\n\n")
            total_chars += len(content)

    size_mb = output_file.stat().st_size / (1024 * 1024)
    print(f"  → Fichier fusionné : {output_file}")
    print(f"  → Taille : {size_mb:.1f} Mo ({total_chars:,} caractères)")
    return output_file
