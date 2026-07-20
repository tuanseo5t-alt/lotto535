__author__ = 'Khiem Doan'
__github__ = 'https://github.com/khiemdoan'
__email__ = 'doankhiem.crazy@gmail.com'

from datetime import date, datetime
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from cloudscraper import CloudScraper

from dtos import Lotto535PrizeRow, Lotto535Result, Lotto535ResultList

URL = 'https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong/535'

DATA_DIR = Path('data/lotto535')

# Zero-padded draw_id width used by Vietlott for Lotto 5/35 (e.g. "00774").
DRAW_ID_WIDTH = 5

# Required number of main balls (the game name says it).
NUMBERS_COUNT = 5

# Header text in the prize table on the right side; skip any row whose
# first cell matches this string. The first table row uses the same
# label "Giải Độc Đắc" but only has 2 cells (it carries the rolling
# jackpot amount, not a prize row), so we filter by cell count too.
TABLE_HEADER = 'Giải thưởng'
JACKPOT_HEADER = 'Giải Độc Đắc'


def _parse_draw_id(text: str) -> str | None:
    """Parse '#00774' → '00774'."""
    t = text.strip().lstrip('#')
    if not t.isdigit():
        return None
    return t.zfill(DRAW_ID_WIDTH)


def _parse_date(text: str) -> date | None:
    """Parse '20/07/2026' → date(2026, 7, 20). Returns None on failure."""
    try:
        return datetime.strptime(text.strip(), '%d/%m/%Y').date()
    except ValueError:
        return None


def _parse_vnd(text: str) -> int | None:
    """Parse '6.948.692.500' → 6948692500. Returns None on failure.

    Vietnamese formatting uses ``.`` as thousands separator.
    """
    digits = text.strip().replace('.', '').replace(',', '').replace(' ', '')
    if not digits.isdigit():
        return None
    return int(digits)


def _strip_vnd_label(text: str) -> str:
    """Strip the trailing 'VND' label from ``"6.948.692.500 VNĐ"``."""
    return text.replace('VNĐ', '').replace('VND', '').strip()


def _numbers_from_box(box: BeautifulSoup) -> tuple[list[str], str | None]:
    """Extract the 5 main numbers and the bonus from the result block.

    The DOM is::

        <div class="day_so_ket_qua border-bottom">
          <div class="day_so_ket_qua_v2">
            <center>
              <span class="bong_tron small">03</span>
              <span class="bong_tron small">12</span>
              <span class="bong_tron small">17</span>
              <span class="bong_tron small">27</span>
              <span class="bong_tron small">35</span>
              <i>|</i>                              ← visual separator
              <span class="bong_tron small active">07</span>   ← bonus
            </center>
          </div>
        </div>

    The bonus is distinguished by the ``active`` class (which Vietlott
    applies to the bonus ball only). We collect ALL ``bong_tron`` spans
    in document order and split: first NUMBERS_COUNT are main balls,
    the rest (if exactly one) is the bonus. This avoids depending on
    the ``<i>|</i>`` separator being present.
    """
    inner = box.find('div', class_='day_so_ket_qua_v2')
    if inner is None:
        return [], None
    spans = inner.find_all('span', class_='bong_tron')
    out: list[str] = []
    for span in spans:
        t = span.get_text(strip=True)
        if len(t) != 2 or not t.isdigit():
            continue
        out.append(t)
    if len(out) != NUMBERS_COUNT + 1:
        return [], None
    return out[:NUMBERS_COUNT], out[NUMBERS_COUNT]


def _jackpot_and_prizes(right: BeautifulSoup) -> tuple[int | None, list[Lotto535PrizeRow]]:
    """Parse the right-side prize table.

    Layout::

        row 0: ['Giải Độc Đắc', '6.948.692.500 VND']            ← jackpot header (2 cells)
        row 1: ['Giải thưởng', 'Kết quả', 'Số lượng giải', ...]  ← column header
        row 2: ['Giải Độc Đắc', 'O O O O O + O', '0', '6.948.692.500']
        row 3: ['Giải Nhất',   'O O O O O',     '1', '10.000.000']
        ... (5 more prize rows)
        row 8: ['Giải Khuyến Khích', 'OO + O O + O O', '22.028', '10.000']

    The first row's second cell carries the rolling jackpot amount. The
    column-header row is skipped by name. Each prize row stores its
    text pattern (with ``+`` markers), the count of O's, the number of
    winners, and the prize value.
    """
    tbl = right.find('table') if right is not None else None
    if tbl is None:
        return None, []

    rows = tbl.find_all('tr')
    jackpot_value: int | None = None

    # First row: jackpot header (2 cells, second contains '... VND').
    if len(rows) >= 1:
        first_cells = rows[0].find_all(['th', 'td'])
        if len(first_cells) == 2 and first_cells[0].get_text(strip=True) == JACKPOT_HEADER:
            v = _parse_vnd(_strip_vnd_label(first_cells[1].get_text(' ', strip=True)))
            if v is not None and v > 0:
                jackpot_value = v

    prizes: list[Lotto535PrizeRow] = []
    for tr in rows[1:]:
        cells = [c.get_text(' ', strip=True) for c in tr.find_all(['th', 'td'])]
        if len(cells) != 4:
            continue
        prize, pattern, count, value = cells
        if prize == TABLE_HEADER:
            continue
        # Count the number of letter-O tokens (main balls the player must match).
        # Tokens like "+", "|" are separators; we ignore them.
        pattern_count = sum(1 for tok in pattern.split() if tok == 'O')
        winner_count_v = _parse_vnd(count)
        prize_value_v = _parse_vnd(value)
        if winner_count_v is None or prize_value_v is None:
            continue
        prizes.append(Lotto535PrizeRow(
            prize=prize,
            pattern=pattern,
            pattern_count=pattern_count,
            winner_count=winner_count_v,
            prize_value=prize_value_v,
        ))
    return jackpot_value, prizes


class Lotto535:
    def __init__(self) -> None:
        self._http = CloudScraper()
        self._data: dict[tuple[date, str], Lotto535Result] = {}
        self._raw_data: pd.DataFrame = pd.DataFrame()

    def load(self) -> None:
        path = DATA_DIR / 'lotto535.json'
        if not path.exists():
            return
        with path.open('r', encoding='utf-8') as f:
            data = Lotto535ResultList.model_validate_json(f.read())
        for d in data.root:
            self._data[(d.date, d.draw_id)] = d
        self.generate_dataframe()

    def fetch(self) -> list[Lotto535Result]:
        """Fetch the most recent Lotto 5/35 draw from Vietlott's listing.

        Returns the list of newly fetched results (those whose
        ``(date, draw_id)`` was not already in the cache). The page
        exposes only the latest draw; there is no historical API, so
        this is meant for incremental polling.
        """
        resp = self._http.get(URL)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, 'lxml')

        title = soup.select_one('div.chitietketqua_title')
        if title is None:
            return []
        b_tags = title.find_all('b')
        if len(b_tags) < 2:
            return []

        # Live DOM order: b[0] = '#00774', b[1] = '20/07/2026'.
        draw_id = _parse_draw_id(b_tags[0].get_text(strip=True))
        parsed_date = _parse_date(b_tags[1].get_text(strip=True))
        if draw_id is None or parsed_date is None:
            return []

        box = soup.select_one('div.day_so_ket_qua.border-bottom')
        if box is None:
            return []
        numbers, bonus = _numbers_from_box(box)
        if len(numbers) != NUMBERS_COUNT or bonus is None:
            # Page layout changed or got truncated; refuse to persist a
            # malformed record rather than guess.
            return []

        right = soup.select_one('#divRightContent')
        jackpot_value, prize_rows = _jackpot_and_prizes(right)
        if jackpot_value is None:
            return []

        try:
            result = Lotto535Result(
                date=parsed_date,
                draw_id=draw_id,
                numbers=numbers,
                bonus=bonus,
                jackpot_value=jackpot_value,
                prizes=prize_rows,
            )
        except ValueError:
            return []

        key = (result.date, result.draw_id)
        if key in self._data:
            return []
        self._data[key] = result
        self.generate_dataframe()
        return [result]

    def generate_dataframe(self) -> None:
        records = [d.model_dump() for d in self._data.values()]
        self._raw_data = pd.DataFrame(records)
        if not self._raw_data.empty:
            self._raw_data['date'] = pd.to_datetime(self._raw_data['date'])
            self._raw_data['draw_id'] = self._raw_data['draw_id'].astype('string')

    def dump(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        records = sorted(
            (d.model_dump() for d in self._data.values()),
            key=lambda r: (r['date'], int(r['draw_id'])),
        )
        result_list = Lotto535ResultList.model_validate([Lotto535Result(**r) for r in records])

        df = pd.DataFrame(records)
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])

        with open(DATA_DIR / 'lotto535.json', 'w', encoding='utf-8') as f:
            f.write(result_list.model_dump_json(indent=2))

        df.to_csv(DATA_DIR / 'lotto535.csv', index=False)
        df.to_parquet(DATA_DIR / 'lotto535.parquet', index=False)

    def get_raw_data(self) -> pd.DataFrame:
        return self._raw_data

    def get_last_draw_id(self) -> str | None:
        if not self._data:
            return None
        return max(d.draw_id for d in self._data.values())


if __name__ == '__main__':
    game = Lotto535()
    game.load()
    new = game.fetch()
    if new:
        for r in new:
            nums = ' '.join(r.numbers)
            print(f'  {r.date} #{r.draw_id}  numbers={nums} bonus={r.bonus}  jackpot={r.jackpot_value:,} VND')
            for row in r.prizes:
                print(f'    {row.prize}: pattern={row.pattern!r} (Os={row.pattern_count})  winners={row.winner_count}  value={row.prize_value:,}')
    else:
        print('No new draws found.')
    game.dump()
    print(f'Total draws stored: {len(game._data)}')
    print(f'Last draw id: {game.get_last_draw_id()}')
