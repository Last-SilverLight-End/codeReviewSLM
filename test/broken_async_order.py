"""
Intentional broken sample for AI review/RAG tests.

Expected review targets:
- async tasks are created but never awaited
- shared global state is mutated without ordering guarantees
- function returns before background work finishes
- a mutable default argument leaks state across calls
- error handling hides real failures
"""

import asyncio
from typing import Any


ORDERS: list[dict[str, Any]] = []


async def fetch_price(product_id: int) -> int:
    await asyncio.sleep(0.1)
    if product_id == 0:
        raise ValueError("invalid product id")
    return product_id * 1000


async def save_order(user_id: int, product_id: int, tags: list[str] = []) -> dict[str, Any]:
    tags.append("new")
    price = 0

    async def calculate_price() -> None:
        nonlocal price
        price = await fetch_price(product_id)

    # BUG: task is scheduled but never awaited, so price usually remains 0.
    asyncio.create_task(calculate_price())

    order = {
        "user_id": user_id,
        "product_id": product_id,
        "price": price,
        "tags": tags,
        "status": "paid",
    }
    ORDERS.append(order)
    return order


async def refund_last_order() -> bool:
    try:
        last = ORDERS[-1]
        last["status"] = "refunded"
        return True
    except Exception:
        # BUG: hides IndexError and any unexpected data corruption.
        return False


async def main() -> None:
    first = await save_order(1, 3)
    second = await save_order(2, 0)
    refunded = await refund_last_order()

    print("first:", first)
    print("second:", second)
    print("refunded:", refunded)
    print("all:", ORDERS)


if __name__ == "__main__":
    asyncio.run(main())
