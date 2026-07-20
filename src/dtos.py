from datetime import date

from pydantic import BaseModel, RootModel, field_validator


class Lotto535PrizeRow(BaseModel):
    """One row of the prize table on the right side of the Lotto 5/35 page.

    Schema::

        Giải thưởng | Kết quả | Số lượng giải | Giá trị giải (đồng)
        Giải Độc Đắc | O O O O O + O | 0 | 6.948.692.500
        Giải Nhất   | O O O O O | 1 | 10.000.000
        ...

    The Kết quả column on Vietlott's listing shows a literal pattern of
    letter ``O``s (one per matching main ball) and ``+`` separators
    marking the bonus-ball position.
    """

    prize: str
    pattern: str
    pattern_count: int
    winner_count: int
    prize_value: int


class Lotto535Result(BaseModel):
    """Single Lotto 5/35 draw.

    Draws happen daily at 18:00. Each draw yields 5 distinct main
    numbers in the range 01–35 plus 1 bonus number in the same range.

    There are 7 prize tiers: Độc Đắc (5+bonus), Nhất (5), Nhì (4+bonus),
    Ba (4), Tư (3+bonus), Năm (3), Khuyến Khích (near-miss recovery).
    """

    date: date
    draw_id: str  # zero-padded, e.g. "00774"
    numbers: list[str]  # 5 distinct two-digit strings, sorted ascending
    bonus: str  # one two-digit string
    jackpot_value: int  # VND
    prizes: list[Lotto535PrizeRow]

    @field_validator('numbers')
    @classmethod
    def _validate_numbers(cls, v: list[str]) -> list[str]:
        if len(v) != 5:
            raise ValueError(f'Lotto 5/35 requires exactly 5 main numbers, got {len(v)}')
        ints = []
        for n in v:
            if len(n) != 2 or not n.isdigit():
                raise ValueError(f'expected a 2-digit string, got {n!r}')
            ints.append(int(n))
        if len(set(ints)) != 5:
            raise ValueError(f'main numbers must be distinct, got {v}')
        for n in ints:
            if not 1 <= n <= 35:
                raise ValueError(f'each number must be in 01-35, got {n}')
        if ints != sorted(ints):
            raise ValueError(f'main numbers must be sorted ascending, got {v}')
        return v

    @field_validator('bonus')
    @classmethod
    def _validate_bonus(cls, v: str) -> str:
        if len(v) != 2 or not v.isdigit():
            raise ValueError(f'expected a 2-digit bonus, got {v!r}')
        if not 1 <= int(v) <= 35:
            raise ValueError(f'bonus must be in 01-35, got {v}')
        return v


class Lotto535ResultList(RootModel):
    root: list[Lotto535Result]
