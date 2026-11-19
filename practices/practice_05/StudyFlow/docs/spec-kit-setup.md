# GitHub Spec Kit для StudyFlow

Подготовлено 25 октября 2026 года. Установлен официальный `specify-cli` **1.2.3**
из тега `v1.2.3` репозитория `github/spec-kit`, commit
`5ea8b1cf0a38699340a38e00d02770308997d8c0`.

## Область подготовки

Добавлены `.specify/` и 10 skills `.agents/skills/speckit-*/SKILL.md`.
CLI установлен локально в игнорируемую `.tools/`; зависимости приложения,
`pyproject.toml` и `uv.lock` не менялись.

Существующие `AGENTS.md`, skills, `.codex/config.toml`, `.codex/hooks.json`,
исходники и материалы `../openspec/` сохранены. До установки выполнена пробная
генерация на временной копии конфигурации: конфликтующих изменений нет.
После установки проверены содержимое и права 102 существовавших файлов
в `practice_05` (без секретов, кешей и генерируемых runtime-каталогов).

`.specify/memory/constitution.md` пока содержит штатный **шаблон**, а не принятые
правила проекта. Спецификации фичи, планы, задачи и `.specify/feature.json`
не создавались; реализация не запускалась. Существующие документы OpenSpec
не импортировались в Spec Kit. Дополнительные extensions не устанавливались.

## Установка и диагностика

Все команды ниже выполняются **из каталога StudyFlow**.
Для восстановления локального CLI после клонирования:

```sh
UV_TOOL_DIR="$PWD/.tools/uv-tools" \
UV_TOOL_BIN_DIR="$PWD/.tools/bin" \
UV_CACHE_DIR="$PWD/.uv-cache" \
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@v1.2.3
```

Фактически выполненная инициализация (повторять для обычной работы не нужно):

```sh
.tools/bin/specify init --here --force --non-interactive \
  --integration codex --integration-options="--skills --events false" --script sh
```

`--force` применён после проверки конфликтов. `--events false` отключает только
обработчики событий Spec Kit и сохраняет существующие hooks StudyFlow.
Глобальный `CODEX_HOME` менять не требуется: эта интеграция использует repo skills.

Проверки установки:

```sh
.tools/bin/specify version
.tools/bin/specify check
.tools/bin/specify integration status --json
```

Получено: версия `1.2.3`, Codex CLI доступен, статус интеграции `ok`,
отсутствующих/изменённых управляемых файлов — `0`. Синтаксис всех шести Bash
скриптов проверен через `bash -n`. `get_repo_root` определяет именно StudyFlow,
хотя корневой Git-репозиторий находится выше, в ITMOv2.

По существующему `AGENTS.md` вручную выполнен неизменённый финальный обработчик
`python3 scripts/verify_before_finish.py`: **232 offline-теста, 66 browser-тестов
и сборка прошли**. Первая попытка в песочнице не смогла запустить Chrome;
повторная проверка вне песочницы завершилась успешно. Это ручной запуск проверки,
а не свидетельство автоматического вызова hook. Полный результат находится в
игнорируемом `data/verification/final-last.json`, история — в `final-runs.jsonl`.

## Два будущих чата: UI и логика

Открывайте оба чата с рабочим каталогом StudyFlow: Codex ищет skills от текущего
каталога вверх, поэтому чат в корне ITMOv2 не обнаружит вложенные skills StudyFlow.
Команды этой версии вызываются как `$speckit-specify`, `$speckit-clarify`,
`$speckit-plan` и т. д. Если skills не появились, перезапустите Codex.

Фича ДЗ: сортировка заданий по дедлайну и вкладка «Просроченные».
Спецификацию UI и спецификацию логики предстоит подготовить в отдельных чатах.
Каждый чат должен явно задавать свой `SPECIFY_FEATURE_DIRECTORY` под `specs/`
при работе со скриптами; не полагайтесь на общий изменяемый указатель
`.specify/feature.json`, особенно при одновременной работе. Эти каталоги пока
не созданы. Общие правила конституции следует согласовать один раз до планирования.

## Официальные инструкции

- [Установка](https://github.github.io/spec-kit/installation.html)
- [Существующий проект](https://github.github.io/spec-kit/guides/existing-projects.html)
- [Интеграция Codex](https://github.github.io/spec-kit/integrations/codex.html)
- [События интеграций](https://github.github.io/spec-kit/integrations/cli.html#runtime-events)
- [Релиз v1.2.3](https://github.com/github/spec-kit/releases/tag/v1.2.3)
- [Обнаружение skills в Codex](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)
