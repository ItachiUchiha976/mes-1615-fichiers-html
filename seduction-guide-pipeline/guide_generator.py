"""
Module 4 – Génération du guide complet de séduction via Gemini.

Stratégie :
  1. Si le texte fusionné est court (< ~800 k tokens), on l'envoie en un seul appel
     à Gemini 1.5 Pro (fenêtre de 1 M de tokens).
  2. Si le texte est trop long, on utilise une stratégie de "map-reduce" :
       • Map   : résumer chaque bloc indépendamment (parallel/sequential)
       • Reduce: synthétiser tous les résumés en un guide structuré.

Le guide final est sauvegardé en Markdown.
"""

import os
import math
from pathlib import Path

import google.generativeai as genai  # type: ignore


# ─── Configuration ────────────────────────────────────────────────────────────

GEMINI_MODEL = "gemini-1.5-pro-latest"
# Fenêtre sûre : on laisse de la marge pour la réponse
MAX_INPUT_CHARS = 3_000_000   # ~750 k tokens (Gemini 1.5 Pro supporte ~1 M tokens)
CHUNK_CHARS = 500_000         # Taille de chaque bloc pour le map-reduce


GUIDE_PROMPT = """
Tu es un expert en psychologie sociale, communication et séduction.
Tu vas analyser la transcription complète de plusieurs formations sur la séduction
et produire un GUIDE PRATIQUE COMPLET, structuré, actionnable et nuancé.

Le guide doit couvrir au minimum les sections suivantes, avec des exemples concrets
tirés des formations et des scripts/dialogues illustratifs :

1. **Mindset & Confiance en soi**
   - Croyances limitantes à éliminer
   - Exercices pour développer la confiance
   - Le cadre mental du séducteur (abondance vs. rareté)

2. **Comprendre les femmes**
   - Psychologie de l'attraction féminine
   - Ce qu'elles disent vs. ce qu'elles veulent vraiment
   - Les signaux d'intérêt (verbaux & non-verbaux)

3. **L'approche**
   - Comment aborder une inconnue (rue, café, soirée, etc.)
   - Les premières secondes : ton, posture, regard
   - Openers universels et openers situationnels (avec exemples)
   - Gérer le rejet et rebondir

4. **La conversation & la connexion**
   - Comment maintenir une conversation intéressante
   - Taquinerie, humour, tension sexuelle
   - Poser des questions de qualité vs. l'interrogatoire
   - La technique du "push-pull"
   - Créer de l'intimité rapidement

5. **La séduction progressive**
   - Les étapes de l'attraction à l'intimité
   - Calibration (lire les signaux et adapter)
   - Escalade physique (kino) : guide étape par étape
   - Gérer les "tests" féminins (shit tests)

6. **Situations spécifiques**
   - Applications de rencontres (Tinder, Bumble…) : profil & messages
   - Les soirées et contextes sociaux
   - La femme en groupe
   - La femme en relation (comment ne pas "friendzonner")
   - La reprise de contact après une période de silence
   - Gérer la jalousie, la concurrence

7. **Erreurs classiques à éviter**
   - Les comportements qui tuent l'attraction
   - Le piège du "nice guy"
   - La dépendance émotionnelle

8. **Routines & Scripts pratiques**
   - Scripts d'approche prêts à l'emploi
   - Réponses aux objections courantes
   - Checklist avant un rendez-vous

9. **Développement personnel continu**
   - Habitudes quotidiennes du séducteur
   - Gestion des émotions et de l'ego
   - Comment s'améliorer en continu

Pour chaque section, fournis :
- Une explication claire du concept
- Des exemples pratiques et des anecdotes tirés des formations
- Des phrases / scripts réutilisables
- Des erreurs fréquentes et comment les éviter

IMPORTANT : Base-toi EXCLUSIVEMENT sur le contenu des transcriptions fournies.
Cite les insights les plus pertinents et les plus récurrents.
Écris en français, de manière directe et pratique.

--- TRANSCRIPTIONS ---
{transcript_content}
--- FIN DES TRANSCRIPTIONS ---
"""

SUMMARY_PROMPT = """
Voici un extrait de transcription de formations sur la séduction.
Résume en points clés TOUS les conseils, techniques, anecdotes et concepts
importants présents dans cet extrait. Sois exhaustif et précis.
Conserve les exemples concrets et les phrases types.

--- EXTRAIT ---
{chunk}
--- FIN DE L'EXTRAIT ---
"""

REDUCE_PROMPT = """
Tu es un expert en séduction et psychologie sociale.
Ci-dessous se trouvent des résumés de différentes parties de formations sur la séduction.
Synthétise-les pour créer un GUIDE PRATIQUE COMPLET, structuré et actionnable.

Structure le guide avec les sections suivantes :
1. Mindset & Confiance en soi
2. Comprendre les femmes
3. L'approche
4. La conversation & la connexion
5. La séduction progressive
6. Situations spécifiques
7. Erreurs classiques à éviter
8. Routines & Scripts pratiques
9. Développement personnel continu

Pour chaque section : explications claires, exemples, scripts réutilisables,
erreurs à éviter. Écris en français, de manière directe et pratique.

--- RÉSUMÉS ---
{summaries}
--- FIN DES RÉSUMÉS ---
"""


# ─── Fonctions utilitaires ────────────────────────────────────────────────────

def _init_gemini():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "Variable d'environnement GEMINI_API_KEY manquante. "
            "Vérifie ton fichier .env."
        )
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(GEMINI_MODEL)


def _call_gemini(model, prompt: str) -> str:
    """Envoie un prompt à Gemini et retourne le texte de la réponse."""
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=0.4,
            max_output_tokens=8192,
        ),
    )
    return response.text


def _split_into_chunks(text: str, chunk_size: int) -> list[str]:
    """Découpe le texte en blocs de chunk_size caractères (sans couper les mots)."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # Reculer jusqu'à un espace pour ne pas couper un mot
        if end < len(text):
            last_space = text.rfind(" ", start, end)
            if last_space > start:
                end = last_space
        chunks.append(text[start:end].strip())
        start = end
    return chunks


# ─── Stratégie map-reduce ─────────────────────────────────────────────────────

def _map_reduce(model, transcript: str) -> str:
    """Résume chaque bloc puis synthétise en un guide final."""
    chunks = _split_into_chunks(transcript, CHUNK_CHARS)
    n = len(chunks)
    print(f"  Mode map-reduce : {n} bloc(s) à résumer.")

    summaries = []
    for i, chunk in enumerate(chunks, 1):
        print(f"  Résumé du bloc {i}/{n}…")
        prompt = SUMMARY_PROMPT.format(chunk=chunk)
        summary = _call_gemini(model, prompt)
        summaries.append(f"--- Résumé bloc {i}/{n} ---\n{summary}")

    all_summaries = "\n\n".join(summaries)
    print("  Génération du guide final à partir des résumés…")
    reduce_prompt = REDUCE_PROMPT.format(summaries=all_summaries)
    return _call_gemini(model, reduce_prompt)


# ─── Point d'entrée principal ─────────────────────────────────────────────────

def run(merged_transcript_path: Path, output_guide_path: Path) -> Path:
    """
    Génère le guide complet depuis le fichier de transcription fusionné.
    Retourne le chemin du guide Markdown.
    """
    transcript = merged_transcript_path.read_text(encoding="utf-8")
    model = _init_gemini()

    if len(transcript) <= MAX_INPUT_CHARS:
        print("  Envoi de la transcription complète à Gemini (fenêtre unique)…")
        prompt = GUIDE_PROMPT.format(transcript_content=transcript)
        guide_text = _call_gemini(model, prompt)
    else:
        print(
            f"  Transcription trop longue ({len(transcript):,} chars). "
            "Utilisation du mode map-reduce…"
        )
        guide_text = _map_reduce(model, transcript)

    output_guide_path.write_text(guide_text, encoding="utf-8")
    print(f"  Guide sauvegardé : {output_guide_path}")
    return output_guide_path
