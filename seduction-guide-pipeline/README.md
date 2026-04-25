# Pipeline : 50h de vidéos → Guide de Séduction Complet

Ce projet automatise entièrement la transformation de tes **50 heures de vidéos**
de formation en séduction en un **guide pratique Markdown** structuré, actionnable
et prêt à l'emploi — le tout via **Whisper** (transcription) et **Claude / Gemini**
(synthèse & rédaction en français).

---

## Architecture du pipeline

```
Google Drive (vidéos)
       │
       ▼  [Étape 1 – optionnelle]
  downloads/         ← vidéos téléchargées localement
       │
       ▼  [Étape 2]
  transcripts/       ← un fichier .txt par vidéo (Whisper)
       │
       ▼  [Étape 3]
  merged_transcript.txt  ← tout en un seul fichier
       │
       ▼  [Étape 4]
  guide_seduction_complet.md  ← le guide final ✅
```

---

## Prérequis système

- **Python 3.10+**
- **ffmpeg** installé et dans le PATH
  - macOS : `brew install ffmpeg`
  - Ubuntu/Debian : `sudo apt install ffmpeg`
  - Windows : [ffmpeg.org/download.html](https://ffmpeg.org/download.html)
- (Optionnel pour Whisper local) **CUDA** si tu as un GPU Nvidia

---

## Installation

```bash
# Cloner le projet
cd seduction-guide-pipeline

# Créer un environnement virtuel
python -m venv .venv
source .venv/bin/activate   # Windows : .venv\Scripts\activate

# Installer les dépendances
pip install -r requirements.txt
```

---

## Configuration

### 1. Copier le fichier d'environnement

```bash
cp .env.example .env
```

### 2. Remplir `.env`

```
# Pour la génération du guide (choisir un des deux) :
ANTHROPIC_API_KEY=sk-ant-...    # Recommandé – Claude Sonnet (meilleure qualité)
GEMINI_API_KEY=AIza...          # Alternative – Gemini 2.5 Pro

OPENAI_API_KEY=sk-...           # Optionnel – seulement si --engine whisper_api
GDRIVE_CREDENTIALS_FILE=credentials.json
GDRIVE_TOKEN_FILE=token.json
```

### 3. Configurer l'accès Google Drive (si tu veux l'étape download)

1. Va sur [console.cloud.google.com](https://console.cloud.google.com)
2. Crée un projet → Active l'**API Google Drive**
3. Crée des identifiants **OAuth 2.0** → type **Application de bureau**
4. Télécharge le fichier `credentials.json` et place-le à la racine du projet

---

## Utilisation

### Workflow recommandé (le plus simple)

**Étape 1 — Transcription + fusion avec le script autonome (sur ton PC)**

```bash
# Pointe vers le dossier racine de tes formations (avec tous les sous-dossiers)
python transcribe_and_merge.py --video-dir /chemin/vers/mes_formations --model medium
```

Ce script fait tout en une fois : transcription Whisper (avec checkpoint anti-crash),
fusion hiérarchique intelligente (respecte l'ordre des modules/chapitres),
et produit `merged_transcript.txt`.

Options utiles :

```bash
# Si la transcription a planté et tu veux reprendre là où tu t'es arrêté :
python transcribe_and_merge.py --video-dir /chemin/vers/mes_formations  # repart du checkpoint

# Si les .txt sont déjà générés et tu veux seulement refaire la fusion :
python transcribe_and_merge.py --only-merge --transcripts-dir transcripts/

# Modèle plus rapide (moins bon) si ton PC est lent :
python transcribe_and_merge.py --video-dir /chemin/vers/mes_formations --model small
```

**Étape 2 — Donner le fichier à Claude pour générer le guide**

Voir la section [Comment donner les fichiers à Claude](#comment-donner-les-fichiers-à-claude) ci-dessous.

---

### Pipeline complet automatisé (avec Google Drive + clé API)

```bash
# Depuis Google Drive, avec Claude pour le guide (recommandé)
python main.py --steps all --folder-id TON_FOLDER_ID_GDRIVE --guide-engine claude
```

> L'ID du dossier Google Drive se trouve dans l'URL :  
> `https://drive.google.com/drive/folders/**1aBcDeFgHiJ...**`

> **Note multilingue :** Whisper détecte automatiquement l'anglais et l'espagnol.
> Le guide est toujours généré **en français**, quelle que soit la langue des vidéos.

### Reprendre après une interruption

`transcribe_and_merge.py` sauvegarde un **checkpoint** (`whisper_checkpoint.json`) après
chaque vidéo. Si le script est interrompu (coupure, crash, redémarrage), relance simplement
la même commande : les vidéos déjà transcrites sont ignorées (`[SKIP]`).

---

## Comment donner les fichiers à Claude

Voici les **3 méthodes** pour me transmettre tes transcriptions, de la plus simple à la plus avancée.

### Méthode A — Claude.ai (interface web) — GRATUITE, la plus simple

1. Lance `transcribe_and_merge.py` sur ton PC → tu obtiens `merged_transcript.txt`
2. Va sur **[claude.ai](https://claude.ai)**
3. Clique sur le trombone 📎 pour joindre un fichier
4. Uploade `merged_transcript.txt` (jusqu'à ~30 Mo acceptés)
5. Écris : *"Crée-moi un guide complet de la séduction en français à partir de ces transcriptions,
   structuré en 9 chapitres : mindset, comprendre les femmes, l'approche, la conversation,
   la séduction progressive, situations spécifiques, erreurs à éviter, scripts pratiques,
   développement personnel."*

> ⚠️ Si le fichier dépasse ~30 Mo, coupe-le en 2-3 parties et envoie-les dans la même conversation.

### Méthode B — Claude Projects (abonnement Pro) — MEILLEURE OPTION

Si tu as **Claude Pro** (~$20/mois) :
1. Crée un **Project** sur claude.ai
2. Uploade `merged_transcript.txt` dans les documents du projet
3. Claude a accès permanent au fichier dans toutes les conversations du projet
4. Demande le guide — tu peux itérer, demander des corrections, des ajouts, etc.

### Méthode C — Via ce pipeline Python (clé API Anthropic)

```bash
python main.py --steps generate --guide-engine claude
# Nécessite ANTHROPIC_API_KEY dans .env (~$1.60 pour 50h)
```

### Méthode D — Gemini avec ton abonnement existant

1. Va sur **[gemini.google.com](https://gemini.google.com)**
2. Uploade `merged_transcript.txt`
3. Demande le guide en français

> Gemini 2.0/2.5 Pro supporte de très grands fichiers — idéal pour ta transcription de 50h.

---

## Quelle stratégie choisir ? (Comparatif complet)

### Étape transcription

| Critère | Whisper Local | Whisper API (OpenAI) |
|---|---|---|
| **Coût** | Gratuit | ~$0.006/min ≈ **$18 pour 50h** |
| **50h de vidéo** | 5-15h CPU / 1-2h GPU | ~18 minutes |
| **Qualité** | Excellente (modèle medium) | Excellente |
| **Langues** | Détection auto (EN, ES, etc.) | Détection auto (EN, ES, etc.) |
| **Confidentialité** | Totale (local) | OpenAI voit les données |
| **Recommandation** | ✅ Lance la nuit | ✅ Si tu veux aller vite |

### Étape génération du guide

| Critère | Claude Sonnet (recommandé) | Gemini 2.5 Pro |
|---|---|---|
| **Coût estimé** (50h) | ~$1.60 | ~$0.70 |
| **Qualité rédaction** | ⭐⭐⭐⭐⭐ Excellente | ⭐⭐⭐⭐ Très bonne |
| **Fenêtre contexte** | 200k tokens | 1M tokens |
| **Mode map-reduce** | Automatique si besoin | Automatique si besoin |
| **Recommandation** | ✅ **Meilleur guide** | ✅ Si tu as déjà Gemini Pro |

### Coût total estimé pour 50h de vidéos

| Scénario | Coût |
|---|---|
| Whisper local (nuit) + Claude guide | **~$1.60** |
| Whisper local (nuit) + Gemini guide | **~$0.70** |
| Whisper API (rapide) + Claude guide | **~$19.60** |

**Recommandation finale :**
1. Lance **Whisper local** (`--engine whisper_local`) pendant la nuit — gratuit.
2. Génère le guide avec **Claude** (`--guide-engine claude`) — ~$1.60, meilleure qualité.
3. Le guide sera rédigé **en français**, même si les vidéos sont en anglais ou espagnol.

---

## Structure du guide généré

Le guide final `guide_seduction_complet.md` couvre :

1. **Mindset & Confiance en soi**
2. **Comprendre les femmes** (psychologie de l'attraction)
3. **L'approche** (openers, premières secondes, gestion du rejet)
4. **La conversation & la connexion** (humour, tension, push-pull)
5. **La séduction progressive** (étapes, kino, shit tests)
6. **Situations spécifiques** (Tinder, soirées, femme en groupe…)
7. **Erreurs classiques à éviter**
8. **Routines & Scripts pratiques** (phrases prêtes à l'emploi)
9. **Développement personnel continu**

---

## Dépannage

### `ffmpeg: command not found`
Installe ffmpeg (voir Prérequis système).

### `GEMINI_API_KEY manquante`
Vérifie que ton `.env` est correctement rempli et que tu es dans le bon dossier.

### Transcription très lente
- Passe au modèle `small` dans `transcriber.py` (ligne `whisper.load_model("medium")`)
- Ou utilise `--engine whisper_api` avec une clé OpenAI

### Gemini retourne une erreur de quota
- Gemini 1.5 Pro avec abonnement supporte de très grands contextes, mais si le fichier
  fusionné dépasse 3M de caractères, le mode **map-reduce** s'active automatiquement.

---

## Variables d'environnement (référence complète)

| Variable | Description | Défaut |
|---|---|---|
| `ANTHROPIC_API_KEY` | Clé API Claude/Anthropic (recommandé) | — |
| `GEMINI_API_KEY` | Clé API Gemini (alternative) | — |
| `OPENAI_API_KEY` | Clé API OpenAI Whisper (optionnel) | — |
| `GDRIVE_CREDENTIALS_FILE` | Chemin credentials OAuth2 | `credentials.json` |
| `GDRIVE_TOKEN_FILE` | Cache token OAuth2 | `token.json` |
| `DOWNLOAD_DIR` | Dossier téléchargements | `downloads` |
| `TRANSCRIPTS_DIR` | Dossier transcriptions | `transcripts` |
| `MERGED_TRANSCRIPT` | Fichier fusionné | `merged_transcript.txt` |
| `OUTPUT_GUIDE` | Guide final | `guide_seduction_complet.md` |
