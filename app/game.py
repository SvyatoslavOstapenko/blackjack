"""Правила блэкджека. Чистые функции: без БД, без HTTP, без глобального состояния.

Именно этот модуль покрывается юнит-тестами в ЛБ7 (требуется покрытие от 40 %).
"""

RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
SUITS = ("S", "H", "D", "C")  # пики, червы, бубны, трефы


def build_deck() -> list[tuple[str, str]]:
    """Полная колода: 52 карты, 4 масти по 13, без повторов."""
    raise NotImplementedError


def card_value(rank: str) -> int:
    """Номинал карты: 2–10 по значению, J/Q/K = 10, туз = 11."""
    raise NotImplementedError


def hand_score(cards: list[tuple[str, str]]) -> int:
    """Очки руки. Туз считается 11, а если перебор — 1 (A+K = 21, A+A = 12)."""
    raise NotImplementedError


def is_blackjack(cards: list[tuple[str, str]]) -> bool:
    """Блэкджек — это ровно две карты на 21, а не любое 21."""
    raise NotImplementedError


def is_bust(score: int) -> bool:
    """Перебор: больше 21."""
    raise NotImplementedError


def dealer_should_hit(score: int) -> bool:
    """Дилер добирает, пока меньше 17; на 17 и выше останавливается."""
    raise NotImplementedError


def settle(player_cards, dealer_cards, bet: int) -> int:
    """Сколько ВСЕГО фишек возвращается игроку: проигрыш — 0, ничья — bet,
    победа — 2*bet, блэкджек — bet + bet*3/2. Ставка уже списана в начале раздачи."""
    raise NotImplementedError
