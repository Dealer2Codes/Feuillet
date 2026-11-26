# Construction automatique sur GitHub

Ces deux fichiers doivent être placés dans le dossier `.github\workflows\` du projet
pour que GitHub les exécute :

```powershell
New-Item -ItemType Directory -Force .github\workflows
Move-Item installer\github-actions\*.yml .github\workflows\
```

- `tests.yml` : lance les tests sous Windows à chaque envoi sur `main`.
- `release.yml` : quand une étiquette `v…` est envoyée, construit l'exécutable,
  l'installateur et la version portable, puis crée un brouillon de Release.
