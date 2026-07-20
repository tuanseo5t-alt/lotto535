"""Render README.md from the latest draw in data/lotto535/lotto535.json.

Run after the fetcher has updated data files. The README lists the
most recent draw's main numbers, bonus, jackpot, and per-prize
breakdown. Re-running on unchanged data yields an idempotent README.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA_FILE = REPO / 'data' / 'lotto535' / 'lotto535.json'
README = REPO / 'README.md'

REPO_OWNER = 'tuanseo5t-alt'
REPO_NAME = 'lotto535'
BRANCH = 'main'
DATA_SUBDIR = 'data/lotto535'

JSON_URL = f'https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/refs/heads/{BRANCH}/{DATA_SUBDIR}/lotto535.json'
CSV_URL = f'https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/refs/heads/{BRANCH}/{DATA_SUBDIR}/lotto535.csv'


def _fmt_vnd(n: int) -> str:
    """16938370500 -> '16.938.370.500'."""
    return f'{n:,}'.replace(',', '.')


def _fmt_int_dotted(n: int) -> str:
    """1076 -> '1.076'."""
    return f'{n:,}'.replace(',', '.')


def _fmt_date(d: date | str) -> str:
    if isinstance(d, str):
        y, m, day = d.split('-')
        return f'{day}/{m}/{y}'
    return f'{d.day:02d}/{d.month:02d}/{d.year}'


def render_latest(draw: dict) -> str:
    numbers = ', '.join(draw['numbers'])
    bonus = draw['bonus']
    jackpot = draw['jackpot_value']
    draw_id = draw['draw_id']
    draw_date = _fmt_date(draw['date'])

    prize_rows = []
    for row in draw['prizes']:
        prize_rows.append(
            f"| {row['prize']} | `{row['pattern']}` | {_fmt_int_dotted(row['winner_count'])} | {_fmt_vnd(row['prize_value'])} |"
        )

    body = f"""# Xổ Số Điện Toán Lotto 5/35

Kết quả xổ số điện toán LOTTO 5/35 mới nhất.

## Kết quả mới nhất

| Kỳ QSMT | Ngày | 5 Số Chính | Bonus | Jackpot |
| :-----: | :--: | :--------: | :---: | :-----: |
| [#{draw_id}]({JSON_URL}) | {draw_date} | {numbers} | {bonus} | {_fmt_vnd(jackpot)} |

**Số người trúng mỗi giải:**

| Giải | Pattern | SL | Giá trị (VNĐ) |
| :--- | :------ | :-: | -----: |
{chr(10).join(prize_rows)}

## Data (Dữ liệu)

| CSV | JSON |
|-----|------|
| [lotto535.csv]({CSV_URL}) | [lotto535.json]({JSON_URL}) |

## Using

```sh
wget {CSV_URL}
```

```python
import pandas as pd
df = pd.read_csv('{CSV_URL}')
df.info()
```
"""
    return body


def main() -> None:
    if not DATA_FILE.exists():
        raise SystemExit(f'missing data file: {DATA_FILE}')
    with DATA_FILE.open('r', encoding='utf-8') as f:
        records = json.load(f)
    if not records:
        raise SystemExit('data file is empty')
    latest = max(records, key=lambda r: (r['date'], int(r['draw_id'])))
    rendered = render_latest(latest)
    if README.exists() and README.read_text(encoding='utf-8') == rendered:
        print('README unchanged.')
        return
    README.write_text(rendered, encoding='utf-8')
    print(f'Rendered README for draw #{latest["draw_id"]} on {latest["date"]}.')


if __name__ == '__main__':
    main()