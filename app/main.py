"""АС «БлэкДжек» — точка входа приложения."""

from fastapi import FastAPI

app = FastAPI(title="БлэкДжек")


@app.get("/health")
def health() -> dict[str, str]:
    """Проверка работоспособности. По ней пайплайн в ЛБ5 и ЛБ8 убеждается,
    что деплой прошёл успешно."""
    return {"status": "ok"}
