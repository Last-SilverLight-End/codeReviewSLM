def add(a: int, b: int) -> int:
    return a + b


def multiply(a: int, b: int) -> int:
    return a * b


class Calculator:
    def __init__(self):
        self.history = []

    def calculate(self, op: str, a: int, b: int) -> int:
        if op == "add":
            result = add(a, b)
        elif op == "mul":
            result = multiply(a, b)
        else:
            raise ValueError(f"Unknown op: {op}")
        self.history.append((op, a, b, result))
        return result

    def get_history(self) -> list:
        return self.history
