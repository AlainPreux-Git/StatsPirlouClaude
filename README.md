# Pirlouette – statistiques (mise à jour automatique)

Chaque jour, GitHub Actions relit les pages « Bals folk », « Animations » et
« Soirées privées » de pirlouette.fr, retrouve les coordonnées des nouvelles
communes et republie la page sur GitHub Pages.

## Mise en place (une seule fois)
1. Créez un dépôt GitHub (public, ou privé si votre offre autorise Pages) et déposez-y tout le contenu de ce dossier, sur la branche `main`.
2. Dans `build.py`, remplacez l'adresse de la ligne `HEADERS` par celle de votre dépôt (exigé par le service de géocodage).
3. Dépôt > Settings > Pages > Source : **GitHub Actions**.
4. Onglet Actions > « Mise à jour de la carte Pirlouette » > **Run workflow**. L'adresse de la page s'affiche à la fin.

## Fichiers
- `build.py` : lit le wiki, géocode, génère `site/index.html`.
- `template.html` : la webapp ; `__DATA__` et `__UPDATED__` sont remplacés à chaque génération.
- `geocache.json` : coordonnées déjà connues (corrigeables à la main). Les nouvelles communes y sont ajoutées automatiquement.
- `data.json` : dernières prestations lues (sert de garde-fou).

## Quand quelque chose ne va pas
- Un lieu non reconnu apparaît en **avertissement** dans le journal de l'Action : ajoutez-le dans `geocache.json` (clé en minuscules sans accents, ex. `"ma commune": {"name": "Ma Commune", "lat": 50.6, "lon": 3.1}`) ou ajoutez une variante d'écriture dans `ALIASES` de `build.py`. Entre-temps il est compté mais absent de la carte.
- Si le wiki change de forme et que moins de 90 % des entrées précédentes sont lues, le script **s'arrête sans rien publier** : la dernière version reste en ligne.
- Dates sans jour : placées au 15 du mois. Dates sans année : l'année de l'entrée précédente est reprise (avertissement).
- Les dates à venir (« On y sera ») ne sont pas lues : seules les 3 pages d'historique le sont.

## Tester en local
`pip install -r requirements.txt && python build.py` puis ouvrir `site/index.html`.
