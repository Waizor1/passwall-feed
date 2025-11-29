import os
import sys
import time
import traceback
from typing import List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# HTML-дерево проекта на SourceForge
FILES_ROOT = "https://sourceforge.net/projects/openwrt-passwall-build/files/"

# Реальное файловое хранилище SourceForge (CDN)
DIRECT_BASE = "https://master.dl.sourceforge.net/project/openwrt-passwall-build/"

# Твой кейс: релиз 24.10 и архитектура aarch64_cortex-a53
RELEASE_PATH = "releases/packages-24.10"
ARCH = "aarch64_cortex-a53"

# Только эти директории выкачиваем
TARGET_DIRS = [
    "passwall2",
    "passwall_luci",
    "passwall_packages",
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEST_DIR = os.path.join(SCRIPT_DIR, "openwrt-passwall-24.10-aarch64_cortex-a53")

# Метаданные, которые нужно всегда обновлять
ALWAYS_UPDATE_NAMES = {
    "Packages",
    "Packages.gz",
    "Packages.sig",
    "Packages.manifest",
    "Packages.bom.cdx.json",
    "index.json",
}


def is_meta_file(name: str) -> bool:
    return name in ALWAYS_UPDATE_NAMES


def fetch_html(session: requests.Session, url: str) -> str:
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def list_files_in_dir(session: requests.Session, dir_name: str) -> List[str]:
    """
    Возвращает список файлов (rel_path) внутри каталога:
      releases/packages-24.10/aarch64_cortex-a53/<dir_name>/
    Тут мы НЕ доверяем href, а берём ровно текст ссылки (имя файла)
    из таблицы и строим путь сами.
    """
    dir_rel = f"{RELEASE_PATH}/{ARCH}/{dir_name}".rstrip("/")
    page_url = FILES_ROOT + dir_rel + "/"

    print(f"[SCAN] {page_url}")
    try:
        html = fetch_html(session, page_url)
    except Exception as e:
        print(f"  ! Не удалось загрузить список {page_url}: {e}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    files: List[str] = []

    for a in soup.find_all("a"):
        text = a.get_text(strip=True)
        if not text:
            continue

        # Отсекаем служебные элементы
        if text == "Parent folder":
            continue
        if text.startswith("Download Latest Version"):
            continue

        # Собственно файлы + метаданные
        if text in ALWAYS_UPDATE_NAMES or "." in text:
            # В таблице имена файлов идут как раз в таком виде:
            # luci-app-passwall2_25.11.18-r1_all.ipk
            # Packages.gz
            # index.json
            rel_path = f"{dir_rel}/{text}"
            files.append(rel_path)

    return sorted(set(files))


def download_file(session: requests.Session, rel_path: str) -> str:
    """
    Качает один файл по rel_path относительно DIRECT_BASE.
    Возвращает 'new', 'updated', 'skipped' или 'error'.
    """
    url = urljoin(DIRECT_BASE, rel_path)
    local_path = os.path.join(DEST_DIR, rel_path.replace("/", os.sep))
    local_dir = os.path.dirname(local_path)
    os.makedirs(local_dir, exist_ok=True)

    name = os.path.basename(local_path)
    exists = os.path.exists(local_path)

    # .ipk считаем "immutable": если файл уже есть и это не метаданные — не трогаем
    if exists and not is_meta_file(name):
        return "skipped"

    tmp_path = local_path + ".part"
    print(f"[GET] {rel_path}")
    # print(f"      {url}")

    try:
        with session.get(url, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    f.write(chunk)
    except Exception as e:
        print(f"  ! Ошибка при скачивании {url}: {e}")
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return "error"

    try:
        os.replace(tmp_path, local_path)
    except OSError:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise

    if exists and is_meta_file(name):
        return "updated"
    return "new"


def main() -> None:
    print(f"Зеркалим только 24.10 / {ARCH} (PassWall):")
    print(f"  → {DEST_DIR}")
    os.makedirs(DEST_DIR, exist_ok=True)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; passwall-24.10-mirror/1.1)",
        }
    )

    all_files: List[str] = []

    print("\n=== Шаг 1. Собираем список файлов по директориям ===")
    for d in TARGET_DIRS:
        files = list_files_in_dir(session, d)
        print(f"  {d}: найдено {len(files)} файлов")
        all_files.extend(files)
        time.sleep(0.5)

    all_files = sorted(set(all_files))
    print(f"\nИтого уникальных файлов: {len(all_files)}")

    if not all_files:
        print("Похоже, ничего не нашли — проверь структуру проекта или релиз/арх.")
        return

    print("\n=== Шаг 2. Скачиваем только нужное (с инкрементальной логикой) ===")
    new_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0

    for rel_path in all_files:
        status = download_file(session, rel_path)
        if status == "new":
            new_count += 1
        elif status == "updated":
            updated_count += 1
        elif status == "skipped":
            skipped_count += 1
        elif status == "error":
            error_count += 1

    print("\n=== РЕЗЮМЕ ===")
    print(f"Новых файлов:          {new_count}")
    print(f"Обновлённых файлов:   {updated_count}")
    print(f"Пропущено (уже были): {skipped_count}")
    print(f"Ошибок при скачивании:{error_count}")
    print("\nГотово. Можно гонять скрипт хоть каждый день — будет тянуть только дельту.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nОтмена пользователем.")
    except Exception:
        print("Фатальная ошибка:")
        traceback.print_exc()
        sys.exit(1)
