# Feuillet

Numérisation de documents et filigranes PDF/Word, **entièrement hors ligne**, pour **Windows 10 et Windows 11** (64 bits).

Logiciel libre sous licence **GNU AGPL-3.0** (voir `LICENSE`).

Feuillet — Copyright (C) 2026 les contributeurs de Feuillet. Ce programme est un logiciel libre :
vous pouvez le redistribuer et/ou le modifier selon les termes de la GNU Affero General Public
License, version 3, publiée par la Free Software Foundation. Il est distribué SANS AUCUNE GARANTIE.
`SPDX-License-Identifier: AGPL-3.0-only`

## Télécharger

Les versions prêtes à l'emploi se trouvent dans l'onglet **Releases** du dépôt GitHub :
- `Feuillet-x.y.z-setup.exe` : installateur Windows 10/11 64 bits ;
- `Feuillet-x.y.z-portable-win64.zip` : version portable, sans installation ;
- `SHA256SUMS.txt` : empreintes pour vérifier l'intégrité des fichiers téléchargés.

L'exécutable n'est pas signé numériquement : au premier lancement, Windows SmartScreen peut afficher
« Windows a protégé votre ordinateur ». Cliquez sur « Informations complémentaires », puis « Exécuter quand même ».

## Fonctionnalités

### Module Scanner
- Import de plusieurs images (JPG, PNG, BMP, TIFF multipage, WebP, GIF), par bouton ou glisser-déposer.
- Galerie avec aperçu, réordonnancement par glisser-déposer, suppression, rotation 90/180/270°.
- Détection automatique des bords du document, cadre ajustable à la main (4 coins).
- Correction de perspective **sans étirement** : les proportions réelles sont recalculées à partir de la perspective (méthode de Zhang et He).
- Redressement automatique du texte, orientation automatique (Tesseract OSD, facultatif).
- Suppression des ombres, contraste (CLAHE), luminosité, débruitage, netteté, balance des blancs.
- Modes : Original, Document couleur, Niveaux de gris, Noir et blanc, Automatique.
- Comparaison avant/après.
- Protection des informations importantes :
  - le mode Automatique ne binarise jamais ;
  - en Noir et blanc, signatures et tampons colorés restent en couleur ;
  - les grandes zones sombres (photo d'identité, logo) ne sont pas « blanchies » par la suppression des ombres ;
  - si les bords ne sont pas détectés avec certitude, l'image entière est conservée.
- Mode carte d'identité : format ID-1 (85,60 × 53,98 mm) à taille réelle, recto/verso sur une ou deux pages.
- PDF multipage (une page par image), formats A4, Lettre US ou taille de l'image ; 150/200/300 DPI ; qualité JPEG réglable ; noir et blanc en PNG 1 bit (léger).
- OCR facultatif (français + anglais) : couche de texte invisible, PDF interrogeable.
- Numérisation depuis un scanner : WIA (par défaut) et TWAIN (facultatif, voir plus bas), résolution, mode couleur, chargeur de documents, messages d'erreur explicites.

### Module Filigrane
- PDF : filigrane texte ou image (PNG transparent conseillé), police, taille, couleur, opacité, angle, 8 positions dont personnalisée, répétition sur toute la page, sélection de pages (toutes, uniquement, toutes sauf), pages pivotées gérées.
- Word (DOCX) : filigrane **natif** inséré dans l'en-tête, comme le fait Word (Création > Filigrane). Le document reste modifiable et Word le reconnaît comme un filigrane. Sélection par section.
- Aperçu en temps réel, nouveau fichier à chaque export (nom et dossier au choix, dossier Téléchargements proposé par défaut), original intact, fichier produit relu pour vérification.

> Un filigrane est un marquage visuel : ce n'est ni un chiffrement ni une protection contre la copie ou la suppression.

### Module Conversion (équivalent hors ligne d'iLovePDF)
- **Vers PDF** : Word, Excel, PowerPoint (Microsoft Office s'il est installé, sinon LibreOffice), images, texte, Markdown, HTML.
- **Depuis PDF** : Word (modifiable, pdf2docx), Excel (tableaux détectés), PowerPoint, images JPG/PNG/WebP, texte.
- **Images** : JPG, PNG, WebP, BMP, TIFF, GIF, ICO, AVIF dans tous les sens ; transparence et animations gérées.
- **Bureautique** : DOC ↔ DOCX ↔ ODT ↔ RTF, XLS ↔ XLSX ↔ ODS ↔ CSV, PPT ↔ PPTX ↔ ODP.
- **Organiser** : fusionner, diviser, extraire, supprimer, réorganiser, pivoter des pages.
- **Optimiser et sécuriser** : compresser, protéger par mot de passe (AES-256), déverrouiller, numéroter les pages, OCR d'un PDF scanné, réparer.
- Traitement par lots, glisser-déposer, nouveaux fichiers sans jamais écraser (« nom (2).pdf »), originaux intacts.
- Sans Microsoft Office ni LibreOffice, les outils bureautiques sont grisés avec une explication ; les autres fonctionnent.
- Fichiers créés par défaut dans le dossier Téléchargements ; message de succès en fin de traitement (fichiers créés, dossier, gain de compression) avec ouverture directe du résultat.

### Sécurité
- Macros Office désactivées lors des conversions ; documents protégés refusés sans bloquer Office.
- Contenu des fichiers contrôlé : fichier vide, document dont le contenu ne correspond pas à l'extension, image « bombe de décompression », page PDF démesurée.
- PDF → Excel : aucune formule n'est créée à partir du texte extrait.
- Protection PDF : mot de passe d'ouverture de 6 à 40 caractères, mot de passe propriétaire aléatoire (les interdictions d'impression et de copie sont réellement appliquées).
- Position GPS retirée des photos converties ; noms de fichiers assainis ; programmes externes jamais cherchés dans le dossier courant.

## Prise en charge de Windows

Uniquement Windows 10 (build 10240 et plus) et Windows 11, 64 bits. Le contrôle est fait :
1. par l'installateur (`installer/feuillet.iss` : `MinVersion` et `InitializeSetup`, message bilingue) ;
2. par l'application à chaque lancement (`feuillet/core/platform_check.py`).

## Développement

Python 3.11 à 3.13 (3.12 recommandé). Une version plus récente est refusée à l'installation.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.lock   # versions exactes testées
python -m pip install -e . --no-deps         # le projet lui-même
pytest
python -m feuillet
```

- `requirements.lock` fige les versions de toutes les dépendances : chaque poste obtient exactement le même environnement.
- `pip install -e ".[dev]"` reste possible : il prend les dernières versions compatibles avec les bornes de `pyproject.toml`.
- TWAIN (facultatif, développement uniquement) : `pip install -e ".[twain]"`. pytwain est sous GPL v2 seule et ne doit pas être livré avec Feuillet (AGPL v3) ; sans lui, l'application utilise WIA.

Sous Linux ou macOS (développement uniquement) : `FEUILLET_ALLOW_UNSUPPORTED_OS=1 python -m feuillet`.

### Tesseract (OCR)
- Développement : installez Tesseract 5 (build UB Mannheim sous Windows) avec les langues `fra`, `eng` et `osd`.
- Distribution : copiez `tesseract.exe`, ses DLL et le dossier `tessdata` (fra, eng, osd) dans `vendor/tesseract/` avant la construction. Ils sont livrés avec l'application.
- La variable `FEUILLET_TESSERACT` permet d'indiquer un autre emplacement.
- Sans Tesseract, l'option OCR est grisée avec une explication ; le reste fonctionne.

## Construire l'installateur

Prérequis : Python 3.12 64 bits, Inno Setup 6.3+ (`ISCC.exe` dans le PATH).

```powershell
powershell -ExecutionPolicy Bypass -File installer\build.ps1
```

Résultat : `dist\installer\Feuillet-0.1.0-setup.exe`.

## Publier une version sur GitHub

La construction est automatique (GitHub Actions, sur un Windows de GitHub) :
1. Mettez à jour `version` dans `pyproject.toml` (et `__version__` dans `src/feuillet/__init__.py`).
2. Envoyez une étiquette de version : `git tag v0.1.0` puis `git push origin v0.1.0`.
3. Le workflow « Release » lance les tests, construit l'exécutable et l'installateur, et crée un
   brouillon de Release avec les fichiers. Relisez-le dans l'onglet Releases, puis cliquez sur « Publish ».

Chaque envoi sur `main` lance aussi les tests sous Windows (workflow « Tests »).

## Architecture

```
src/feuillet/
  core/          erreurs typées, traductions FR/EN, contrôle Windows 10/11, écriture sûre des fichiers
  scanner/       traitement d'image (OpenCV), assemblage PDF, OCR (Tesseract), modèles
    sources/     scanners physiques : WIA, TWAIN, interface commune
  convert/       conversions : catalogue d'outils, images, PDF, bureautique (Office/LibreOffice)
  watermark/     filigranes PDF (PyMuPDF) et Word (python-docx + lxml), sélection de pages, polices
  ui/            interface PySide6 (Qt 6) : onglets Scanner et Filigrane
  locales/       fr.json, en.json
tests/           tests unitaires et d'intégration (images de test générées)
installer/       PyInstaller, Inno Setup, script de construction
```

Chaque moteur tiers est isolé dans son module : l'interface ne dépend que des fonctions du cœur.

## À valider sur le matériel cible

Ces points ne peuvent pas être testés hors d'un poste Windows réel :
- acquisition WIA et TWAIN sur les scanners utilisés (chargeur, recto-verso, pilotes 32/64 bits) ;
- rendu du filigrane Word dans Microsoft Word (testé sous LibreOffice) ;
- installateur et exécutable sur Windows 10 et 11.
