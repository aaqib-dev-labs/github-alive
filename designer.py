#!/usr/bin/env python3

import datetime
import math
import sys


ANCHOR_DATE = datetime.date(2012, 9, 9)


def base_commits(days_since_anchor: int, day_of_week: int) -> int:
    t = days_since_anchor / 7.0
    d = day_of_week

    w1 = math.sin(2 * math.pi * t / 26 + 0.0)
    w2 = math.sin(2 * math.pi * t / 13 + 1.5)
    w3 = math.sin(2 * math.pi * t / 52 + 0.8)
    w4 = math.sin(2 * math.pi * d / 7 + t * 0.4)
    w5 = math.sin(2 * math.pi * (t * 1.3 + d) / 9)

    combined = w1 * 0.35 + w2 * 0.25 + w3 * 0.15 + w4 * 0.15 + w5 * 0.10
    count = round(3 + (combined + 1) * 18.5)
    return max(1, min(40, count))


def commits_to_char(n: int) -> str:
    if n <= 5:
        return '·'
    elif n <= 15:
        return '░'
    elif n <= 25:
        return '▒'
    elif n <= 35:
        return '▓'
    else:
        return '█'



DISPLAY_WEEKS = 52
DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']


def get_week_start(today: datetime.date) -> datetime.date:
    dow = today.isoweekday() % 7
    return today - datetime.timedelta(days=dow)


def render_pattern(today: datetime.date) -> None:
    week_start = get_week_start(today)
    today_week = 0
    today_dow = today.isoweekday() % 7

    grid = []
    for day in range(7):
        row = []
        for week in range(DISPLAY_WEEKS):
            date = week_start + datetime.timedelta(weeks=week, days=day)
            days = (date - ANCHOR_DATE).days
            n = base_commits(days, day)
            ch = commits_to_char(n)
            row.append(ch)
        grid.append(row)

    print()
    print("  github-alive — pattern preview (next 52 weeks)")
    print(f"  Anchor: {ANCHOR_DATE}  |  Today: {today.isoformat()}")
    print()

    print("  Legend:  · 1–5   ░ 6–15   ▒ 16–25   ▓ 26–35   █ 36–40  commits")
    print()

    sep = '─' * (DISPLAY_WEEKS * 2 + 2)
    print(f"  {sep}")
    for day in range(7):
        row_str = ' '.join(grid[day])
        print(f"  {DAY_NAMES[day]}  {row_str}")
    print(f"  {sep}")

    arrow_pos = today_week * 2
    prefix = ' ' * (6 + arrow_pos)
    print(f"  {prefix}↑ today ({today.strftime('%a %b %d')})")
    print()

    total = sum(
        base_commits(
            (week_start + datetime.timedelta(weeks=w, days=d) - ANCHOR_DATE).days,
            d
        )
        for w in range(DISPLAY_WEEKS)
        for d in range(7)
    )
    avg = total / (DISPLAY_WEEKS * 7)
    print(f"  52-week window: {DISPLAY_WEEKS * 7} days  |  avg {avg:.1f} commits/day  |  est. {total} total")
    print()


def main():
    if '--help' in sys.argv or '-h' in sys.argv:
        print(__doc__)
        sys.exit(0)

    today = datetime.date.today()
    render_pattern(today)


if __name__ == '__main__':
    main()
