# Releases (versiones y tags)

## Semver

- **MAJOR**: rompe API/contrato con clientes, migraciones forzadas.
- **MINOR**: funcionalidad nueva sin romper entornos existentes.
- **PATCH**: correcciones, ajustes, dependencias, CI, docs.

## Archivo `VERSION`

Debe reflejar la **próxima** versión que vas a etiquetar. Tras publicar un tag, sube el número.

## Flujo de release

1. En local, valida el estado del repo:
   ```bash
   git checkout main
   git pull --ff-only
   ```

2. Verifica/actualiza `VERSION` y haz commit (Conventional Commits):
   ```bash
   git commit -am "chore(release): bump version to 0.1.0"
   ```

3. Crea y publica el tag **con prefijo `v`** (dispara el changelog y el release en GitHub Actions):
   ```bash
   git tag -a v0.1.0 -m "v0.1.0"
   git push origin main
   git push origin v0.1.0
   ```

4. Comprueba GitHub Actions:
   - **Update Changelog** actualiza `CHANGELOG.md` y hace push a `main`.
   - **GitHub Release** crea el Release con notas automáticas.

## Notas

El tag es lo que dispara deploy y changelog. Si el tag no sigue `v*`, no se ejecutan los workflows de release.