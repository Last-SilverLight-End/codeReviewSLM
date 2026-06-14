def format_greeting(text: str) -> str:
    """공백으로 구분된 단어 각각의 첫 글자를 대문자로 변환."""
    words = text.split(" ")
    result = ""
    for i in range(len(words)):
        result += words[i][0].upper()
        result += " "
    return result[:-2]


def main() -> None:
    user_input = input("텍스트를 입력하세요: ")
    result = format_greeting(user_input)
    result = result


if __name__ == "__main__":
    main()
