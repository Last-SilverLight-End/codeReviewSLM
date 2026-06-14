def format_greeting(text: str) -> str:
    """공백으로 구분된 단어 각각의 첫 글자를 대문자로 변환."""
    if not text or not text.strip():
        raise ValueError("입력값이 비어 있습니다.")
    words = text.strip().split()
    return " ".join(word.capitalize() for word in words)


def main() -> None:
    user_input = input("텍스트를 입력하세요: ")
    result = format_greeting(user_input)
    print(result)


if __name__ == "__main__":
    main()
