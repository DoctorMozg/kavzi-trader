NA = "n/a"


class Md:
    """Small Markdown helpers; every undefined number renders as n/a."""

    @staticmethod
    def table(headers: list[str], rows: list[list[str]]) -> str:
        lines = [
            "| " + " | ".join(headers) + " |",
            "|" + "|".join("---" for _ in headers) + "|",
            *("| " + " | ".join(row) + " |" for row in rows),
        ]
        return "\n".join(lines)

    @staticmethod
    def pct(numerator: int, denominator: int) -> str:
        if denominator == 0:
            return f"{NA} (0/0)"
        return f"{100 * numerator / denominator:.1f}% ({numerator}/{denominator})"

    @staticmethod
    def rate(value: float | None) -> str:
        return NA if value is None else f"{value:.3f}"

    @staticmethod
    def num(value: float | None, digits: int = 2) -> str:
        return NA if value is None else f"{value:.{digits}f}"

    @staticmethod
    def section(title: str, *blocks: str) -> str:
        return "\n\n".join([f"## {title}", *blocks])
