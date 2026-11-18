import pytest

from app.game import (
    build_deck,
    card_value,
    dealer_should_hit,
    hand_score,
    is_blackjack,
    settle,
)


@pytest.mark.parametrize(
    "rank,expected",
    [("2", 2), ("10", 10), ("J", 10), ("Q", 10), ("K", 10), ("A", 11)],
)
def test_card_values(rank, expected):
    assert card_value(rank) == expected


def test_invalid_rank():
    with pytest.raises(ValueError):
        card_value("1")


@pytest.mark.parametrize(
    "ranks,score",
    [("AA", 12), ("AA9", 21), ("AAA9", 12), ("AK", 21), ("KQ5", 25)],
)
def test_ace_scores(ranks, score):
    assert hand_score([(r, "S") for r in ranks]) == score


def test_deck_and_dealer_rule():
    deck = build_deck()
    assert len(deck) == len(set(deck)) == 52
    assert dealer_should_hit(16) and not dealer_should_hit(17)
    assert is_blackjack([("A", "S"), ("K", "D")])
    assert not is_blackjack([("7", "S"), ("7", "H"), ("7", "D")])


@pytest.mark.parametrize(
    "player,dealer,expected",
    [
        ("AK", "Q9", 250),
        ("AK", "AQ", 100),
        ("Q9", "AK", 0),
        ("KQ", "Q9", 200),
        ("KQ", "QK", 100),
        ("KQ5", "Q9", 0),
        ("Q9", "KQ5", 200),
    ],
)
def test_payouts(player, dealer, expected):
    assert (
        settle([(r, "S") for r in player], [(r, "H") for r in dealer], 100)
        == expected
    )


@pytest.mark.parametrize("bet", [0, -2, 3])
def test_bad_stakes(bet):
    with pytest.raises(ValueError):
        settle([("K", "S")], [("Q", "H")], bet)
