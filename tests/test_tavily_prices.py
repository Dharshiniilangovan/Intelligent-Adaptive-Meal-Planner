from src.grocery.tavily_client import extract_price


def test_offer_price():

    text = """
    Offer
    $1.62
    $1.70
    Save $0.08
    Till 31st Oct 2026
    Churo Black Pepper (Crushed)
    """

    assert extract_price(text) == 1.62


def test_normal_price():

    text = """
    FairPrice Fresh Milk
    $3.25
    2L
    """

    assert extract_price(text) == 3.25


def test_savings_not_selected():

    text = """
    Product
    Save $0.80
    $4.20
    """

    assert extract_price(text) == 4.20


def test_old_and_offer_price():

    text = """
    Product
    $5.50
    $6.20
    Save $0.70
    """

    assert extract_price(text) == 5.50


def test_unit_price_ignored():

    text = """
    Product
    $4.50
    $0.45/100g
    """

    assert extract_price(text) == 4.50


def test_delivery_price_ignored():

    text = """
    Free delivery above $79
    Product
    $3.80
    """

    assert extract_price(text) == 3.80