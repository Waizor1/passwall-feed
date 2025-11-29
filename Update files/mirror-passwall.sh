#!/usr/bin/env bash
set -euo pipefail

# Корневая страница со всеми файлами проекта
BASE_URL="https://sourceforge.net/projects/openwrt-passwall-build/files/"

# Куда складывать локальную копию
DEST_DIR="./openwrt-passwall-build-mirror"

mkdir -p "$DEST_DIR"
cd "$DEST_DIR"

echo "=== Зеркалируем $BASE_URL в $PWD ==="

wget \
  --mirror \                # режим зеркала: рекурсивно + по датам
  --no-parent \             # не подниматься выше /files/
  --continue \              # докачивать обрывы
  --timestamping \          # не перекачивать, если файл не менялся
  --no-host-directories \   # не создавать подкаталог sourceforge.net
  --cut-dirs=4 \            # обрезать /projects/openwrt-passwall-build/files/
  --content-disposition \   # сохранять файлы по имени из заголовка (ipk, Packages.gz и т.п.)
  -e robots=off \           # игнорировать robots.txt (иначе SourceForge режет рекурсивный wget)
  "$BASE_URL"

echo "=== Готово. Локальное зеркало обновлено. ==="
