# Pipeline : 50h de vidéos → Guide de Séduction Complet

Ce projet automatise entièrement la transformation de tes **50 heures de vidéos**
de formation en séduction en un **guide pratique Markdown** structuré, actionnable
et prêt à l'emploi — le tout via **Whisper** (transcription) et **Gemini 1.5 Pro**
(synthèse & rédaction).

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
GEMINI_API_KEY=AIza...          # Obligatoire – clé API Gemini
OPENAI_API_KEY=sk-...           # Optionnel – seulement si engine=whisper_api
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

### Pipeline complet (toutes les étapes)

```bash
python main.py --steps all --folder-id TON_FOLDER_ID_GDRIVE
```

> L'ID du dossier Google Drive se trouve dans l'URL :  
> `https://drive.google.com/drive/folders/**1aBcDeFgHiJ...**`

### Si tes vidéos sont déjà téléchargées localement

```bash
# Place tes vidéos dans un dossier, ex: mes_videos/
python main.py --steps transcribe merge generate --video-dir mes_videos/
```

### Étapes séparées

```bash
# Étape 1 : Télécharger
python main.py --steps download --folder-id FOLDER_ID

# Étape 2 : Transcrire (moteur local, plus lent mais gratuit)
python main.py --steps transcribe --engine whisper_local

# Étape 2 alternative : Transcrire via API OpenAI (plus rapide, ~$0.006/min)
python main.py --steps transcribe --engine whisper_api

# Étape 3 : Fusionner
python main.py --steps merge

# Étape 4 : Générer le guide
python main.py --steps generate
```

### Reprendre après une interruption

Chaque étape est **idempotente** : les vidéos déjà téléchargées et les
transcriptions déjà générées sont automatiquement ignorées (`[SKIP]`).
Tu peux relancer sans risque.

---

## Quelle stratégie choisir ? (Comparatif)

| Critère | Whisper Local | Whisper API | Gemini Native |
|---|---|---|---|
| **Coût** | Gratuit | ~$0.006/min | Inclus dans abonnement |
| **Vitesse** | Lent (CPU) / Rapide (GPU) | Très rapide | — |
| **Qualité** | Excellente (medium/large) | Excellente | Bonne |
| **50h de vidéo** | 5-15h CPU / 1-2h GPU | ~18 min + coût | Limité par contexte |
| **Confidentialité** | Totale (local) | OpenAI voit les données | Google voit les données |
| **Recommandation** | ✅ Si tu as un bon CPU/GPU | ✅ Si tu veux aller vite | ⚠️ Uniquement pour petites vidéos |

**Recommandation pour 50h de vidéos :**
1. Utilise **Whisper local** (modèle `medium`) sur ton CPU pendant la nuit — gratuit et privé.
2. Envoie le fichier `merged_transcript.txt` à **Gemini 1.5 Pro** pour générer le guide.

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
| `GEMINI_API_KEY` | Clé API Gemini (obligatoire) | — |
| `OPENAI_API_KEY` | Clé API OpenAI Whisper (optionnel) | — |
| `GDRIVE_CREDENTIALS_FILE` | Chemin credentials OAuth2 | `credentials.json` |
| `GDRIVE_TOKEN_FILE` | Cache token OAuth2 | `token.json` |
| `DOWNLOAD_DIR` | Dossier téléchargements | `downloads` |
| `TRANSCRIPTS_DIR` | Dossier transcriptions | `transcripts` |
| `MERGED_TRANSCRIPT` | Fichier fusionné | `merged_transcript.txt` |
| `OUTPUT_GUIDE` | Guide final | `guide_seduction_complet.md` |
