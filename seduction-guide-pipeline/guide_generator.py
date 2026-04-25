"""
Module 4 – Génération du guide complet de séduction.

Deux moteurs disponibles :
  - "claude"  : Claude Sonnet via API Anthropic (recommandé – meilleure rédaction)
  - "gemini"  : Gemini 2.5 Pro via API Google (bonne option, fenêtre 1M tokens)

Les transcriptions peuvent être en anglais ou espagnol – le guide est TOUJOURS
produit en français.

Stratégie :
  1. Si le texte fusionné tient dans la fenêtre de contexte → envoi direct.
  2. Sinon → map-reduce : résumé bloc par bloc, puis synthèse finale.
"""

import os
from pathlib import Path


# ─── Prompts ──────────────────────────────────────────────────────────────────

GUIDE_PROMPT = """Tu es un expert en psychologie sociale, communication et séduction.
Tu vas analyser la transcription complète de plusieurs formations sur la séduction.
Les transcriptions peuvent être en anglais ou en espagnol — peu importe, tu comprends les deux.

IMPORTANT : Tu dois rédiger le guide EXCLUSIVEMENT EN FRANÇAIS, peu importe la langue des transcriptions.

Produis un GUIDE PRATIQUE COMPLET, structuré, actionnable et nuancé, couvrant :

# Guide Complet de la Séduction

## 1. Mindset & Confiance en soi
- Croyances limitantes à éliminer (avec exemples tirés des formations)
- Exercices concrets pour développer la confiance
- Le cadre mental du séducteur : abondance vs. rareté
- Comment penser, se comporter, se percevoir

## 2. Comprendre les femmes
- Psychologie de l'attraction féminine (ce qui crée réellement l'attirance)
- Ce qu'elles disent vs. ce qu'elles veulent vraiment
- Les signaux d'intérêt verbaux et non-verbaux (liste détaillée)
- Comment les femmes testent les hommes

## 3. L'approche
- Comment aborder une inconnue (rue, café, soirée, transport, gym, etc.)
- Les premières secondes : ton de voix, posture, regard, sourire
- Openers universels prêts à l'emploi (avec au moins 10 exemples)
- Openers situationnels (s'adapter au contexte)
- Gérer le rejet : que faire et que dire

## 4. La conversation & la connexion
- Comment maintenir une conversation vivante et intéressante
- Taquinerie, humour, tension sexuelle (avec exemples de phrases)
- Poser des questions de qualité vs. l'interrogatoire
- La technique du push-pull (explication + exemples)
- Créer de l'intimité rapidement
- Les sujets à éviter et les sujets qui créent une connexion

## 5. La séduction progressive
- Les étapes de l'attraction à l'intimité (schéma clair)
- Calibration : lire les signaux et adapter son comportement
- Escalade physique (kino) : guide étape par étape
- Comment proposer et obtenir un rendez-vous
- Gérer les "tests" féminins (shit tests) : réponses types

## 6. Situations spécifiques
- Applications de rencontres (Tinder, Bumble…) : optimiser son profil + messages types
- Les soirées et contextes sociaux (comment s'y comporter)
- La femme entourée de son groupe d'amis
- Éviter la "friend zone" : signes et comment l'éviter
- La reprise de contact après une période de silence (textos types)
- Gérer la jalousie et la concurrence masculine
- La relation à distance ou sporadique

## 7. Erreurs classiques à éviter
- Les comportements qui tuent l'attraction (liste exhaustive)
- Le piège du "nice guy" : pourquoi et comment en sortir
- La dépendance émotionnelle et comment la surmonter
- Les erreurs des débutants vs. les erreurs des intermédiaires

## 8. Routines & Scripts pratiques
- Au moins 15 scripts d'approche prêts à l'emploi
- Réponses aux objections courantes ("j'ai un copain", "je ne te connais pas", etc.)
- Checklist complète avant un rendez-vous
- Idées de dates originales et efficaces

## 9. Développement personnel continu
- Habitudes quotidiennes du séducteur (liste actionnable)
- Gestion des émotions, de l'ego et des échecs
- Comment s'améliorer en continu (ressources, pratique, feedback)
- Le mindset à long terme

---

Pour chaque section :
- Explique clairement le concept
- Donne des exemples pratiques tirés des formations
- Fournis des scripts / phrases réutilisables entre guillemets
- Indique les erreurs fréquentes et comment les éviter

IMPORTANT :
- Base-toi EXCLUSIVEMENT sur le contenu des transcriptions fournies
- Rédige TOUT en français, même si les transcriptions sont en anglais ou espagnol
- Sois direct, pratique, sans langue de bois
- Le guide doit être utilisable immédiatement par un homme ordinaire

--- TRANSCRIPTIONS ---
{transcript_content}
--- FIN DES TRANSCRIPTIONS ---
"""

SUMMARY_PROMPT = """Voici un extrait de transcription de formations sur la séduction.
Les transcriptions sont peut-être en anglais ou en espagnol.

Résume en français en points clés TOUS les conseils, techniques, anecdotes et concepts
importants présents dans cet extrait. Sois exhaustif et précis.
Conserve les exemples concrets et les phrases types (traduis-les en français).

--- EXTRAIT ---
{chunk}
--- FIN DE L'EXTRAIT ---
"""

REDUCE_PROMPT = """Tu es un expert en séduction et psychologie sociale.
Ci-dessous se trouvent des résumés (en français) de différentes parties de formations sur la séduction.
Synthétise-les pour créer un GUIDE PRATIQUE COMPLET, structuré et actionnable.

Rédige TOUT en français. Le guide doit être immédiatement utilisable.

Structure le guide avec ces sections (toutes en détail) :
1. Mindset & Confiance en soi
2. Comprendre les femmes
3. L'approche (avec au moins 10 scripts/openers)
4. La conversation & la connexion
5. La séduction progressive
6. Situations spécifiques (Tinder, soirées, friend zone, etc.)
7. Erreurs classiques à éviter
8. Routines & Scripts pratiques (au moins 15 scripts)
9. Développement personnel continu

Pour chaque section : explications claires, exemples, scripts entre guillemets,
erreurs à éviter. Direct et pratique.

--- RÉSUMÉS ---
{summaries}
--- FIN DES RÉSUMÉS ---
"""


# ─── Moteur Claude (Anthropic) ────────────────────────────────────────────────

# Fenêtre sûre pour Claude Sonnet (200k tokens ≈ 800k chars)
CLAUDE_MAX_INPUT_CHARS = 700_000
CLAUDE_CHUNK_CHARS = 150_000


def _call_claude(prompt: str) -> str:
    """Envoie un prompt à Claude Sonnet via l'API Anthropic."""
    import anthropic  # type: ignore

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "Variable d'environnement ANTHROPIC_API_KEY manquante. "
            "Ajoute-la dans ton fichier .env."
        )
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=8096,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def _generate_with_claude(transcript: str) -> str:
    """Génère le guide via Claude avec map-reduce si nécessaire."""
    if len(transcript) <= CLAUDE_MAX_INPUT_CHARS:
        print("  Envoi de la transcription complète à Claude (fenêtre unique)…")
        return _call_claude(GUIDE_PROMPT.format(transcript_content=transcript))
    else:
        print(
            f"  Transcription trop longue ({len(transcript):,} chars). "
            "Mode map-reduce avec Claude…"
        )
        return _map_reduce(_call_claude, transcript, CLAUDE_CHUNK_CHARS)


# ─── Moteur Gemini ────────────────────────────────────────────────────────────

# Gemini 2.5 Pro supporte ~1M tokens ≈ 4M chars (on reste conservatif)
GEMINI_MODEL = "gemini-2.5-pro-latest"
GEMINI_MAX_INPUT_CHARS = 3_000_000
GEMINI_CHUNK_CHARS = 500_000


def _init_gemini():
    import google.generativeai as genai  # type: ignore

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "Variable d'environnement GEMINI_API_KEY manquante. "
            "Vérifie ton fichier .env."
        )
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)

    def _call(prompt: str) -> str:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.4,
                max_output_tokens=8192,
            ),
        )
        return response.text

    return _call


def _generate_with_gemini(transcript: str) -> str:
    """Génère le guide via Gemini avec map-reduce si nécessaire."""
    call_fn = _init_gemini()
    if len(transcript) <= GEMINI_MAX_INPUT_CHARS:
        print("  Envoi de la transcription complète à Gemini (fenêtre unique)…")
        return call_fn(GUIDE_PROMPT.format(transcript_content=transcript))
    else:
        print(
            f"  Transcription trop longue ({len(transcript):,} chars). "
            "Mode map-reduce avec Gemini…"
        )
        return _map_reduce(call_fn, transcript, GEMINI_CHUNK_CHARS)


# ─── Map-reduce générique ─────────────────────────────────────────────────────

def _split_into_chunks(text: str, chunk_size: int) -> list[str]:
    """Découpe le texte en blocs sans couper les mots."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            last_space = text.rfind(" ", start, end)
            if last_space > start:
                end = last_space
        chunks.append(text[start:end].strip())
        start = end
    return chunks


def _map_reduce(call_fn, transcript: str, chunk_size: int) -> str:
    """Résume chaque bloc, puis synthétise en un guide final."""
    chunks = _split_into_chunks(transcript, chunk_size)
    n = len(chunks)
    print(f"  Mode map-reduce : {n} bloc(s) à résumer.")

    summaries = []
    for i, chunk in enumerate(chunks, 1):
        print(f"  Résumé du bloc {i}/{n}…")
        summary = call_fn(SUMMARY_PROMPT.format(chunk=chunk))
        summaries.append(f"--- Résumé bloc {i}/{n} ---\n{summary}")

    all_summaries = "\n\n".join(summaries)
    print("  Génération du guide final à partir des résumés…")
    return call_fn(REDUCE_PROMPT.format(summaries=all_summaries))


# ─── Point d'entrée principal ─────────────────────────────────────────────────

def run(
    merged_transcript_path: Path,
    output_guide_path: Path,
    engine: str = "claude",
) -> Path:
    """
    Génère le guide complet depuis le fichier de transcription fusionné.

    engine : "claude" (recommandé) ou "gemini"
    """
    transcript = merged_transcript_path.read_text(encoding="utf-8")

    print(f"  Moteur de génération : {engine}")
    print(f"  Taille de la transcription : {len(transcript):,} caractères")

    if engine == "claude":
        guide_text = _generate_with_claude(transcript)
    elif engine == "gemini":
        guide_text = _generate_with_gemini(transcript)
    else:
        raise ValueError(f"Moteur inconnu : {engine}. Choisir 'claude' ou 'gemini'.")

    output_guide_path.write_text(guide_text, encoding="utf-8")
    print(f"  Guide sauvegardé : {output_guide_path}")
    return output_guide_path
