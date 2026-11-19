# StudyFlow: схема практики и ДЗ 5

- `studyflow-workflow.svg` — полный векторный плакат.
- `studyflow-workflow.png` — растровая версия плаката.
- `studyflow-workflow.mmd` — редактируемая Mermaid-схема того же процесса.
- `01-openspec.png`, `02-speckit-planning.png`, `03-worktree-integration.png` — три части для чтения в чате.
- `workflow-graph.json` — данные блоков и связей.

Показано фактически выполненное до подготовки итогового отчёта. Пунктирный перенос в `practice_05` — следующий шаг, а не выполненная операция.

Команды с `$` — навыки в чате агента; `openspec …` / `specify …` — CLI. `git …` — операции версионирования и синхронизации, не команды SDD-фреймворка. Human review и приёмка отражены в описаниях соответствующих этапов.

Обмен спецификациями на clarify не является merge кода. Оба worktree созданы от `32ffa22`; main specs OpenSpec и общий `StudyFlow/spec.md` имеют разные роли.

Ключевые коммиты: baseline `32ffa22`; документы logic `1d4e3ee` и UI `c4cf22b`; ядро `c8f4e78`; первый merge `03ce694`; UI `ae22a86`; интеграция `9c728b9`; финальная проверка UI `4bd71f6`; исправление T041 `7d43b94`.
