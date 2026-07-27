from buggy import calculate_ctr


def test_normal_ctr():
    assert calculate_ctr(10, 100) == 0.1


def test_zero_impressions():
    assert calculate_ctr(0, 0) == 0.0  # fails on buggy code (ZeroDivisionError)
