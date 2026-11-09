"""Offline simulation only. No browser, network or payment integrations."""
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from checkout_guard import CheckoutBlocked, validate, simulated_snapshot

BANGKOK = timezone(timedelta(hours=7))
SCENARIOS = ('success', 'sold_out', 'coupon_missing', 'price_changed', 'challenge', 'unknown', 'declined',
             'wrong_card', 'ambiguous_card', 'wrong_variant', 'extra_item', 'stale_quote', 'payment_page_only')

def money(value):
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n < 0 or n != n.quantize(Decimal('.01')):
            raise ValueError('จำนวนเงินต้องไม่ติดลบ และมีทศนิยมไม่เกิน 2 ตำแหน่ง')
        return int(n * 100)
    except InvalidOperation as exc:
        raise ValueError('จำนวนเงินไม่ถูกต้อง') from exc

class Engine:
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=10)
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT, state TEXT, reserved INTEGER DEFAULT 0, receipt TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS events (job TEXT, at TEXT, message TEXT)')
        self.db.commit()

    def log(self, job, message):
        self.db.execute('INSERT INTO events VALUES (?,?,?)', (job, datetime.now(BANGKOK).isoformat(), message))

    def add(self, p):
        p = dict(p)
        for name in ('campaign', 'product', 'variant', 'address', 'card'):
            if not str(p.get(name, '')).strip():
                raise ValueError('กรุณาระบุ ' + name)
        if p.get('scenario') not in SCENARIOS:
            raise ValueError('สถานการณ์จำลองไม่ถูกต้อง')
        if int(p['quantity']) < 1:
            raise ValueError('จำนวนต้องมากกว่า 0')
        start = datetime.fromisoformat(p['start'])
        if start.utcoffset() != timedelta(hours=7):
            raise ValueError('เวลาต้องระบุเขตเวลา +07:00')
        if not 1 <= int(p['window']) <= 86400:
            raise ValueError('ช่วงเวลาซื้อ 1–86400 วินาที')
        for key in ('price', 'shipping', 'discount', 'cap', 'budget'):
            p[key] = money(p[key])
        if p['discount'] > p['price'] * int(p['quantity']) or not p['cap'] or not p['budget']:
            raise ValueError('ส่วนลดหรือวงเงินไม่ถูกต้อง')
        if p.get('required_coupon') and not p.get('coupon', '').strip():
            raise ValueError('ต้องระบุโค้ดเมื่อบังคับใช้คูปอง')
        job = uuid.uuid4().hex[:12]
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            for row in self.db.execute('SELECT data FROM jobs'):
                existing = json.loads(row[0])
                if existing['campaign'] == p['campaign'] and existing['budget'] != p['budget']:
                    raise ValueError('งานในแคมเปญเดียวกันต้องใช้งบรวมเท่ากัน')
            self.db.execute('INSERT INTO jobs(id,data,state) VALUES (?,?,?)', (job, json.dumps(p, ensure_ascii=False), 'ARMED'))
            self.log(job, 'ตั้งเวลาจำลองแล้ว — ไม่มีการซื้อจริง')
        return job

    def rows(self):
        return [(r[0], json.loads(r[1]), r[2], r[3], r[4]) for r in self.db.execute('SELECT * FROM jobs ORDER BY rowid DESC')]

    def events(self, job):
        return self.db.execute('SELECT at,message FROM events WHERE job=? ORDER BY rowid', (job,)).fetchall()

    def _state(self, job, state, message, reserved=None):
        self.db.execute('UPDATE jobs SET state=? WHERE id=?', (state, job))
        if reserved is not None:
            self.db.execute('UPDATE jobs SET reserved=? WHERE id=?', (reserved, job))
        self.log(job, message)

    def tick(self, now=None):
        now = now or datetime.now(BANGKOK)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            for job, p, state, reserved, receipt in self.rows():
                start = datetime.fromisoformat(p['start'])
                end = start + timedelta(seconds=int(p['window']))
                if state == 'WAITING_USER' and now >= end:
                    self._state(job, 'UNKNOWN', 'หมดเวลายืนยัน: ต้องตรวจผลคำสั่งซื้อเดิมก่อน ป้องกันการส่งซ้ำ')
                if state != 'ARMED' or now < start:
                    continue
                if now >= end:
                    self._state(job, 'EXPIRED', 'เลยเวลาที่อนุญาตแล้ว ไม่ส่งคำสั่ง')
                    continue
                s = p['scenario']
                spent = sum(r[3] for r in self.rows() if r[1]['campaign'] == p['campaign'])
                try:
                    total = validate(p, simulated_snapshot(p, now), now, spent)
                except CheckoutBlocked as exc:
                    self._state(job, 'STOPPED', str(exc))
                    continue
                self.db.execute('UPDATE jobs SET reserved=?,receipt=? WHERE id=?', (total, 'SIM-' + job, job))
                self.log(job, f'ส่งคำสั่งจำลองครั้งเดียว ยอด {total / 100:.2f} บาท')
                state = {'challenge': 'WAITING_USER', 'unknown': 'UNKNOWN', 'declined': 'DECLINED',
                         'payment_page_only': 'UNKNOWN'}.get(s, 'PAID_SIMULATED')
                self._state(job, state, 'ผลจำลอง: ' + state, 0 if state == 'DECLINED' else total)

    def resolve(self, job, paid):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT state FROM jobs WHERE id=?', (job,)).fetchone()
            if not row or row[0] not in ('UNKNOWN', 'WAITING_USER'):
                raise ValueError('เลือกงานที่รอยืนยันหรือไม่ทราบผลเท่านั้น')
            self._state(job, 'PAID_SIMULATED' if paid else 'DECLINED', 'กำหนดผลจำลองของคำสั่งเดิม โดยไม่ส่งซ้ำ', None if paid else 0)

    def cancel(self, job):
        with self.db:
            row = self.db.execute('SELECT state FROM jobs WHERE id=?', (job,)).fetchone()
            if not row or row[0] != 'ARMED':
                raise ValueError('หยุดได้เฉพาะงานที่ยังไม่ส่งคำสั่ง')
            self._state(job, 'CANCELLED', 'ผู้ใช้หยุดงานก่อนส่งคำสั่ง')
