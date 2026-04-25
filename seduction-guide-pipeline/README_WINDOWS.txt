══════════════════════════════════════════════════════════════════
  GUIDE D'INSTALLATION ET D'UTILISATION – WINDOWS 10
  Script de transcription Whisper pour formations vidéo
══════════════════════════════════════════════════════════════════

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ÉTAPE 1 – Installer Python (si pas déjà fait)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Va sur https://www.python.org/downloads/
2. Télécharge Python 3.11 ou 3.12 (bouton jaune "Download Python")
3. Lance l'installeur
   ⚠ IMPORTANT : coche "Add Python to PATH" en bas avant de cliquer Install


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ÉTAPE 2 – Installer ffmpeg
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ffmpeg est l'outil qui extrait l'audio des vidéos.

Option A (recommandée) – Via winget (Windows 10/11) :
  1. Ouvre le menu Démarrer, cherche "Invite de commandes", clique droit → "Exécuter en tant qu'administrateur"
  2. Tape :
     winget install ffmpeg
  3. Ferme et réouvre l'invite de commandes

Option B – Manuellement :
  1. Va sur https://github.com/BtbN/FFmpeg-Builds/releases
  2. Télécharge "ffmpeg-master-latest-win64-gpl.zip"
  3. Décompresse dans C:\ffmpeg\
  4. Ajoute C:\ffmpeg\bin dans les variables d'environnement PATH :
     - Démarrer → "variables d'environnement" → Modifier les variables système
     - Variable "Path" → Modifier → Nouveau → C:\ffmpeg\bin


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ÉTAPE 3 – Installer les bibliothèques Python
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ouvre l'invite de commandes (Démarrer → "cmd") et tape :

  pip install faster-whisper

C'est tout. Cette commande télécharge faster-whisper et toutes ses dépendances.
(~500 Mo de téléchargement, inclut le moteur CTranslate2)

Le modèle Whisper lui-même (large-v3, ~1.5 Go) sera téléchargé
automatiquement lors du premier lancement du script.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ÉTAPE 4 – Lancer le script
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Place le fichier windows_transcribe.py dans n'importe quel dossier.

Méthode A – Double-clic (le plus simple) :
  1. Place windows_transcribe.py dans le même dossier que tes vidéos
     (ou dans un dossier parent contenant tous les sous-dossiers de formations)
  2. Double-clique sur windows_transcribe.py
  → Le script transcrit toutes les vidéos du dossier et des sous-dossiers

Méthode B – Ligne de commande (si tes vidéos sont ailleurs) :
  1. Ouvre l'invite de commandes (cmd)
  2. Tape :
     python C:\chemin\vers\windows_transcribe.py C:\chemin\vers\tes\videos

Exemple concret :
  python windows_transcribe.py "C:\Users\Toi\Google Drive\Formations Séduction"


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CE QUE TU OBTIENS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Après le script, dans le même dossier que windows_transcribe.py :

  transcriptions\                    ← dossier miroir de tes vidéos
    Formation 1\
      Module 01\
        01 - Introduction.txt
        02 - Les bases.txt
      Module 02\
        ...
    Formation 2\
      ...

  transcription_COMPLETE.txt         ← TOUT en un seul fichier (pour Claude)
  transcription.log                  ← journal de progression
  transcription_checkpoint.json      ← fichier de reprise (ne pas supprimer)


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DURÉE ESTIMÉE (sur CPU, sans GPU)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Modèle large-v3 (recommandé, défaut) :
    - Environ 4 à 8 heures pour 50h de vidéo sur un PC normal
    - Lance le soir, retrouve les résultats le matin

  Modèle medium (plus rapide) :
    - Environ 2 à 4 heures pour 50h de vidéo
    - Qualité légèrement inférieure mais suffisante
    - Pour changer : ouvre windows_transcribe.py avec Notepad,
      ligne "WHISPER_MODEL = "large-v3"" → remplace par "medium"

  Si le script est interrompu (PC éteint, etc.) :
    → Relance simplement le script, il reprend là où il s'était arrêté.
    → Ne supprime pas transcription_checkpoint.json !


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROBLÈMES COURANTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"pip n'est pas reconnu"
  → Python n'a pas été ajouté au PATH lors de l'installation.
  → Désinstalle Python et réinstalle en cochant "Add Python to PATH".

"ffmpeg n'est pas installé"
  → Suis l'Étape 2 ci-dessus.

"ModuleNotFoundError: No module named 'faster_whisper'"
  → Lance : pip install faster-whisper

Le script se ferme immédiatement sans rien faire
  → Lance-le depuis cmd pour voir le message d'erreur :
     cd dossier\du\script
     python windows_transcribe.py

La qualité de transcription est mauvaise sur certaines vidéos
  → Normal pour les vidéos avec beaucoup de bruit de fond.
  → Le fichier .txt sera quand même utilisable.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ÉTAPE SUIVANTE : DONNER LES FICHIERS À CLAUDE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Voir README_DONNER_A_CLAUDE.txt pour les instructions.

══════════════════════════════════════════════════════════════════
