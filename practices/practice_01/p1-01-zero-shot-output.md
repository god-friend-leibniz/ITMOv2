# P1-01 — zero-shot output

Запрос: `Ниже diff учебного PR. Посмотри PR и найди проблемы.`

```text
Findings
- app/api.py — доступ к payload["diff"] может привести к KeyError при отсутствии поля.
- app/api.py и app/review_service.py — вызов LLM не имеет локальной обработки ошибок.
- app/review_service.py — большой diff передаётся в prompt целиком.
- Также предложены Pydantic-модели, response_model, асинхронный endpoint,
  аутентификация, rate limiting, изменение доменной модели и дополнительные тесты.
```

Оценка и отклонённые предположения сохранены в `prompts.md`.
