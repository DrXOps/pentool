#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Скрипт сборки проекта в один текстовый файл.
Собирает все текстовые файлы (по расширениям и известным именам),
игнорируя служебные папки (__pycache__, .git, node_modules и т.п.).
Результат сохраняется в указанный файл с заголовками для каждого исходного файла.

После создания выводится статистика:
- размер файла на диске
- количество символов
- приблизительное число токенов (символы / 4)
- предупреждение, если токенов > 128k
"""

import os
import sys
import argparse
from pathlib import Path

# Папки, которые будут полностью исключены из обхода
EXCLUDE_DIRS = {
    '.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env',
    'dist', 'build', '.idea', '.vscode', '.pytest_cache', '.mypy_cache',
    '.tox', '.eggs', 'coverage', 'htmlcov', '.ruff_cache', '.ipynb_checkpoints'
}

# Расширения файлов, считающихся текстовыми (код, конфиги, документация)
INCLUDE_EXTS = {
    '.py', '.js', '.jsx', '.ts', '.tsx', '.html', '.htm', '.css', '.scss', '.sass',
    '.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
    '.txt', '.md', '.rst', '.log', '.sh', '.bash', '.bat', '.cmd', '.ps1',
    '.sql', '.php', '.rb', '.go', '.rs', '.c', '.cpp', '.h', '.hpp', '.java',
    '.kt', '.swift', '.pl', '.pm', '.lua', '.r', '.dart', '.lisp', '.clj',
    '.scala', '.groovy', '.gradle', '.makefile', '.cmake', '.dockerfile',
    '.gitignore', '.gitattributes', '.editorconfig', '.env',
    '.csv', '.tsv', '.svg', '.xml', '.xslt', '.wsdl'
}

# Имена файлов без расширения, которые тоже нужно включать
SPECIAL_NAMES = {
    'Dockerfile', 'Makefile', 'makefile', 'CMakeLists.txt', 'LICENSE',
    'README', 'README.md', 'CHANGELOG', 'CONTRIBUTING', 'AUTHORS'
}


def should_include_file(file_path: Path, include_exts, exclude_dirs, special_names):
    """
    Определяет, нужно ли включать файл в сборку.
    Проверяет:
      - не находится ли в исключённой папке;
      - соответствует ли расширение списку разрешённых;
      - или имя файла входит в специальные имена;
      - а также пытается прочитать начало файла как UTF‑8 (проверка на текст).
    """
    # Исключаем папки
    for part in file_path.parts:
        if part in exclude_dirs:
            return False

    # Проверка расширения или специального имени
    if file_path.suffix.lower() in include_exts:
        pass  # разрешено по расширению
    elif file_path.name in special_names:
        pass  # разрешено по имени
    else:
        return False  # не подходит

    # Попытка прочитать небольшой кусок как текст UTF‑8
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            f.read(1024)
        return True
    except (UnicodeDecodeError, PermissionError, OSError):
        return False


def collect_files(root_dir: str, include_exts=None, exclude_dirs=None, special_names=None):
    """Рекурсивно собирает все подходящие файлы из корневой директории."""
    if include_exts is None:
        include_exts = INCLUDE_EXTS
    if exclude_dirs is None:
        exclude_dirs = EXCLUDE_DIRS
    if special_names is None:
        special_names = SPECIAL_NAMES

    root = Path(root_dir).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"'{root_dir}' не является директорией.")

    files = []
    for item in root.rglob('*'):
        if item.is_file():
            if should_include_file(item, include_exts, exclude_dirs, special_names):
                files.append(item)
    return files


def generate_output(files, output_file: str, root_dir: str):
    """Записывает все файлы в выходной файл с разделителями."""
    with open(output_file, 'w', encoding='utf-8') as out:
        out.write("=" * 80 + "\n")
        out.write("СБОРКА ВСЕХ ФАЙЛОВ ПРОЕКТА\n")
        out.write(f"Корневая папка: {root_dir}\n")
        out.write(f"Всего файлов: {len(files)}\n")
        out.write("=" * 80 + "\n\n")

        for file_path in sorted(files):
            # Относительный путь от корня проекта для наглядности
            try:
                rel_path = file_path.relative_to(Path(root_dir).resolve())
            except ValueError:
                rel_path = file_path  # на случай, если путь не вложен

            out.write(f"ФАЙЛ: {rel_path}\n")
            out.write("-" * 80 + "\n")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                out.write(content)
            except Exception as e:
                out.write(f"ОШИБКА ЧТЕНИЯ: {e}\n")
            out.write("\n" + "=" * 80 + "\n\n")


def main():
    parser = argparse.ArgumentParser(
        description="Собрать все текстовые файлы проекта в один файл для передачи ИИ."
    )
    parser.add_argument(
        '--root', default='.',
        help='Корневая папка проекта (по умолчанию текущая)'
    )
    parser.add_argument(
        '--output', default='project_export.txt',
        help='Выходной файл (по умолчанию project_export.txt)'
    )
    parser.add_argument(
        '--extensions', nargs='+',
        help='Список расширений для включения (например .py .js) — переопределяет стандартный список'
    )
    parser.add_argument(
        '--exclude-dirs', nargs='+',
        help='Список дополнительных папок для исключения (добавляются к стандартным)'
    )
    parser.add_argument(
        '--no-default-excludes', action='store_true',
        help='Не использовать стандартный список исключённых папок'
    )
    parser.add_argument(
        '--max-size-mb', type=float, default=None,
        help='Пропускать файлы размером больше указанного МБ (по умолчанию без ограничения)'
    )
    parser.add_argument(
        '--no-stats', action='store_true',
        help='Не выводить статистику по итоговому файлу'
    )
    args = parser.parse_args()

    root_dir = args.root
    output_file = args.output

    # Формируем списки
    include_exts = set(args.extensions) if args.extensions else None  # None означает использовать стандартный
    exclude_dirs = set(args.exclude_dirs) if args.exclude_dirs else set()
    if not args.no_default_excludes:
        exclude_dirs.update(EXCLUDE_DIRS)

    files = collect_files(root_dir, include_exts, exclude_dirs, SPECIAL_NAMES)

    # Фильтр по размеру, если задан
    if args.max_size_mb is not None:
        max_bytes = args.max_size_mb * 1024 * 1024
        files = [f for f in files if f.stat().st_size <= max_bytes]
        print(f"После фильтра по размеру осталось {len(files)} файлов.")

    print(f"Найдено файлов для включения: {len(files)}")
    generate_output(files, output_file, root_dir)
    print(f"Результат записан в {output_file}")

    # --- ВЫВОД СТАТИСТИКИ ---
    if not args.no_stats:
        try:
            file_size = os.path.getsize(output_file)
            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read()
            char_count = len(content)
            approx_tokens = char_count // 4  # грубая оценка

            print("\n" + "=" * 50)
            print("СТАТИСТИКА ИТОГОВОГО ФАЙЛА")
            print(f"Размер на диске: {file_size} байт "
                  f"({file_size / 1024:.2f} КБ, {file_size / 1024 / 1024:.2f} МБ)")
            print(f"Количество символов: {char_count:,}")
            print(f"Оценка токенов (символы ÷ 4): {approx_tokens:,}")

            # Предупреждение о превышении типичного контекста
            if approx_tokens > 128_000:
                print("\n⚠️  ВНИМАНИЕ: оценка токенов превышает 128 000.")
                print("   Это может не поместиться в контекст многих современных моделей (GPT-4, Claude 3 и др.).")
                print("   Рекомендуется сократить проект или разбить на части.")
            elif approx_tokens > 16_000:
                print("\nℹ️  Оценка токенов > 16 000 — контекст может быть заполнен значительной частью.")
            else:
                print("\n✅ Оценка токенов в пределах типичного контекста (≤ 16 000).")
            print("=" * 50)
        except Exception as e:
            print(f"Не удалось подсчитать статистику: {e}")


if __name__ == '__main__':
    main()
