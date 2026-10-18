"""Blackjack game rules."""

from secrets import SystemRandom

RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
SUITS = ("S", "H", "D", "C")


def build_deck() -> list[tuple[str, str]]:
    deck = [(rank, suit) for suit in SUITS for rank in RANKS]
    SystemRandom().shuffle(deck)
    return deck


def card_value(rank: str) -> int:
    if rank not in RANKS:
        raise ValueError("Invalid card rank")
    if rank == "A":
        return 11
    if rank in ("J", "Q", "K"):
        return 10
    return int(rank)


def hand_score(cards: list[tuple[str, str]]) -> int:
    total = sum(card_value(rank) for rank, _ in cards)
    aces = sum(rank == "A" for rank, _ in cards)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def is_blackjack(cards: list[tuple[str, str]]) -> bool:
    return len(cards) == 2 and hand_score(cards) == 21


def is_bust(score: int) -> bool:
    return score > 21


def dealer_should_hit(score: int) -> bool:
    return score < 17


def settle(player_cards, dealer_cards, bet: int) -> int:
    if bet <= 0 or bet % 2:
        raise ValueError("Bet must be positive and even")

    player_bj = is_blackjack(player_cards)
    dealer_bj = is_blackjack(dealer_cards)

    if player_bj and dealer_bj:
        return bet
    if player_bj:
        return bet * 5 // 2
    if dealer_bj:
        return 0

    player_score = hand_score(player_cards)
    dealer_score = hand_score(dealer_cards)

    if is_bust(player_score):
        return 0
    if is_bust(dealer_score):
        return bet * 2
    if player_score > dealer_score:
        return bet * 2
    if player_score == dealer_score:
        return bet
    return 0