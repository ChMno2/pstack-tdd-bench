def add(a: int, b: int) -> int:
    return a + b


def clamp(x: int, lo: int, hi: int) -> int:
    return max(lo, min(x, hi))


def is_even(n: int) -> bool:
    return n % 2 == 0
