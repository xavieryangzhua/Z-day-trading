"""Read-only IB Gateway historical download; run with ../.venv/bin/python.

Caches completed weekly requests for restart; never requests or submits orders.
Output timestamps are UTC bar-open times. Current NY trading date is excluded.
"""
import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())
import argparse
import csv
import hashlib
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ib_insync import IB, Stock

NY = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent / 'data/external/ibkr'


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temp.replace(path)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=4002)
    parser.add_argument('--symbols', nargs='+', choices=['SPY','QQQ','NVDA','TSLA','AAPL','META'], default=['NVDA','TSLA','AAPL','META'])
    parser.add_argument('--end', default=datetime.now(NY).date().isoformat(),
                        help='Exclusive NY date; current day is never downloaded')
    args = parser.parse_args()
    end = datetime.fromisoformat(args.end).replace(tzinfo=NY)
    if end.date() > datetime.now(NY).date():
        raise ValueError('End date must exclude the current trading day')
    start = end.replace(year=end.year - 1)
    folder = ROOT / f'{start.date()}_{end.date()}'
    folder.mkdir(parents=True, exist_ok=True)
    ib = IB()
    errors = []
    def error(req_id, code, message, contract):
        if code not in (2104, 2106, 2158):
            errors.append({'code': code, 'message': message})
            print('IB_MESSAGE', code, message, flush=True)
    ib.errorEvent += error
    logging.getLogger('ib_insync').setLevel(logging.CRITICAL)
    sources = json.loads((folder/'sources.json').read_text()) if (folder/'sources.json').exists() else []
    try:
        await ib.connectAsync('127.0.0.1', args.port, clientId=194,
                              timeout=15, readonly=True)
        print('CONNECTED readonly; range', start.isoformat(), end.isoformat(), flush=True)
        for symbol in args.symbols:
            primary = 'ARCA' if symbol == 'SPY' else 'NASDAQ'
            contract = Stock(symbol, 'SMART', 'USD', primaryExchange=primary)
            await ib.qualifyContractsAsync(contract)
            if not contract.conId:
                raise RuntimeError(f'Unable to resolve {symbol}')
            all_rows = {}
            cursor = end
            chunks = 0
            conflicts = 0
            while cursor > start:
                cache = folder / 'chunks' / f'{symbol}_{cursor.date()}.json'
                if cache.exists():
                    payload = json.loads(cache.read_text())
                    if payload['conId'] != contract.conId:
                        raise ValueError('Cached contract mismatch')
                    rows = payload['bars']
                else:
                    rows = None
                    for attempt in range(3):
                        bars = await ib.reqHistoricalDataAsync(
                            contract, endDateTime=cursor.astimezone(timezone.utc),
                            durationStr='1 W', barSizeSetting='1 min',
                            whatToShow='TRADES', useRTH=True, formatDate=2,
                            timeout=90)
                        if bars:
                            rows = [{'timestamp': b.date.isoformat(), 'open': b.open,
                                     'high': b.high, 'low': b.low, 'close': b.close,
                                     'volume': b.volume, 'average': b.average,
                                     'bar_count': b.barCount} for b in bars]
                            break
                        await asyncio.sleep(16 * (attempt + 1))
                    if not rows:
                        raise RuntimeError(f'{symbol} {cursor.date()}: no bars; retry later')
                    save_json(cache, {'conId': contract.conId,
                                     'retrieved_at': datetime.now(timezone.utc).isoformat(),
                                     'end': cursor.isoformat(), 'bars': rows})
                    await asyncio.sleep(1)
                for row in rows:
                    stamp = datetime.fromisoformat(row['timestamp'])
                    if not start <= stamp < end:
                        continue
                    nums = [row[k] for k in ('open', 'high', 'low', 'close', 'volume')]
                    if (not all(math.isfinite(x) for x in nums) or min(nums[:4]) <= 0
                            or row['volume'] < 0
                            or row['low'] > min(row['open'], row['close'])
                            or row['high'] < max(row['open'], row['close'])):
                        raise ValueError(f'Invalid OHLCV: {symbol} {row}')
                    if row['timestamp'] in all_rows and all_rows[row['timestamp']] != row:
                        conflicts += 1
                    all_rows.setdefault(row['timestamp'], row)
                chunks += 1
                print(symbol, 'chunk', chunks, 'through', cursor.date(), 'rows', len(all_rows), flush=True)
                cursor -= timedelta(days=7)
            ordered = sorted(all_rows.values(), key=lambda row: row['timestamp'])
            if not ordered:
                raise RuntimeError(f'{symbol}: empty dataset')
            output = folder / f'{symbol}_1min.csv'
            temp = output.with_suffix('.tmp')
            with temp.open('w', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=list(ordered[0]))
                writer.writeheader()
                writer.writerows(ordered)
            temp.replace(output)
            days = {}
            gaps = []
            previous = None
            for row in ordered:
                stamp = datetime.fromisoformat(row['timestamp']).astimezone(NY)
                day = str(stamp.date())
                days[day] = days.get(day, 0) + 1
                if previous and previous.date() == stamp.date() and stamp - previous != timedelta(minutes=1):
                    gaps.append([previous.isoformat(), stamp.isoformat()])
                previous = stamp
            sources = [s for s in sources if s['symbol'] != symbol]
            sources.append({'symbol': symbol, 'conId': contract.conId,
                            'source': 'IBKR TWS API via local IB Gateway',
                            'exchange': 'SMART', 'primaryExchange': contract.primaryExchange,
                            'whatToShow': 'TRADES', 'useRTH': True, 'barSize': '1 min',
                            'requested_start_inclusive': start.isoformat(),
                            'requested_end_exclusive': end.isoformat(),
                            'timezone': 'UTC; timestamps mark bar open',
                            'file': output.name,
                            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                            'rows': len(ordered), 'days': len(days),
                            'first_bar': ordered[0]['timestamp'], 'last_bar': ordered[-1]['timestamp'],
                            'rows_by_day': days, 'within_session_gaps': gaps,
                            'overlapping_conflicts': conflicts,
                            'retrieved_at': datetime.now(timezone.utc).isoformat(),
                            'limitations': ['IBKR TRADES data; not independently reconciled',
                                            'No missing bars filled; early-close days retained',
                                            'Stock bars, not historical option quotes']})
            save_json(folder / 'sources.json', sources)
            print('SAVED', symbol, len(ordered), 'bars', len(days), 'days', 'gaps', len(gaps), flush=True)
        save_json(folder / 'download_status.json', {'status': 'complete', 'errors': errors})
        print('COMPLETE', folder, flush=True)
    finally:
        ib.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
