# Composants tiers

Feuillet est distribué sous GNU AGPL-3.0. Il utilise les composants suivants, dont les licences sont compatibles avec ce choix.

| Composant | Rôle | Licence |
| --- | --- | --- |
| PyMuPDF / MuPDF (Artifex) | Lecture, écriture et rendu PDF, filigranes | AGPL-3.0 (ou licence commerciale Artifex) |
| OpenCV (opencv-python-headless) | Traitement d'image | Apache 2.0 |
| NumPy | Calcul numérique | BSD-3-Clause |
| Pillow | Lecture et écriture d'images | MIT-CMU (HPND) |
| python-docx | Lecture et écriture DOCX | MIT |
| lxml | XML | BSD-3-Clause |
| Qt 6 / PySide6-Essentials | Interface graphique | LGPL-3.0 |
| pywin32 | Accès COM (WIA) | PSF |
| pdf2docx | PDF vers Word | MIT |
| python-pptx / XlsxWriter | PDF vers PowerPoint | MIT / BSD-2-Clause |
| openpyxl / et-xmlfile | PDF vers Excel | MIT |
| Markdown | Markdown vers PDF | BSD-3-Clause |
| fonttools / fire / termcolor | Dépendances de pdf2docx | MIT / Apache 2.0 / MIT |
| Tesseract OCR et données de langue | Reconnaissance de texte | Apache 2.0 |

Les textes complets des licences sont fournis par chaque paquet installé (dossiers `*.dist-info`) et doivent accompagner l'exécutable distribué.

## Logiciels externes facultatifs (non livrés)

| Logiciel | Rôle | Remarque |
| --- | --- | --- |
| Microsoft Office | Conversions Word/Excel/PowerPoint | Utilisé s'il est installé (automatisation COM) |
| LibreOffice | Conversions bureautiques de secours | Appelé en ligne de commande s'il est installé (MPL 2.0) |

## Composant exclu de la distribution

| Composant | Rôle | Licence | Statut |
| --- | --- | --- | --- |
| pytwain | Accès TWAIN | GPL v2 seule | Incompatible avec l'AGPL v3 : optionnel (`pip install -e ".[twain]"`), jamais livré avec l'exécutable. Sans lui, l'application utilise WIA. |
| pillow-heif | Lecture HEIC (photos iPhone) | binaires GPL v2 | Non retenu pour la même raison. |
