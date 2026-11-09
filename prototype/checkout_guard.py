"""Pure checkout validation. No Selenium, network, card data or payment calls."""
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Item:
    product: str
    variant: str
    quantity: int


@dataclass(frozen=True)
class Snapshot:
    items: tuple
    address: str
    card: str
    matching_cards: int
    card_selected: bool
    currency: str
    total_satang: int
    coupon: str
    observed_at: datetime
    available: bool = True


class CheckoutBlocked(ValueError):
    pass


def validate(plan, snapshot, now, reserved_satang):
    """Return final payable amount only when every required fact is verified."""
    def require(condition, reason):
        if not condition:
            raise CheckoutBlocked(reason)

    require(now.utcoffset() is not None and snapshot.observed_at.utcoffset() is not None,
            'เวลา snapshot ต้องมี timezone')
    age = now - snapshot.observed_at
    require(timedelta(0) <= age <= timedelta(seconds=10), 'ข้อมูล checkout เก่าหรือเวลาไม่ถูกต้อง')
    require(snapshot.available, 'สินค้าหมด')
    expected = (Item(plan['product'], plan['variant'], int(plan['quantity'])),)
    require(snapshot.items == expected, 'สินค้า รุ่น จำนวน หรือรายการในรถเข็นไม่ตรง')
    require(snapshot.address == plan['address'], 'ที่อยู่ไม่ตรงกับแผน')
    require(snapshot.matching_cards == 1, 'ไม่พบบัตรหรือพบหลายใบ ไม่เลือกโดยเดา')
    require(snapshot.card_selected and snapshot.card == plan['card'], 'ยังไม่ได้เลือกบัตรที่กำหนด')
    require(snapshot.currency == 'THB', 'สกุลเงินต้องเป็น THB')
    total = snapshot.total_satang
    require(type(total) is int and total >= 0, 'ยอดเงินจริงไม่ถูกต้อง')
    require(type(reserved_satang) is int and reserved_satang >= 0, 'ยอดกันงบไม่ถูกต้อง')
    require(total <= plan['cap'], 'ยอดสุดท้ายเกินเพดานคำสั่งซื้อ')
    require(total + reserved_satang <= plan['budget'], 'ยอดสุดท้ายเกินงบรวมแคมเปญ')
    require(not plan['required_coupon'] or snapshot.coupon == plan['coupon'], 'คูปองบังคับใช้ไม่ตรง')
    return total


def simulated_snapshot(plan, now):
    """Fixture adapter; values are synthetic and are never read from Shopee."""
    from dataclasses import replace
    scenario = plan['scenario']
    discount = 0 if scenario == 'coupon_missing' else plan['discount']
    s = Snapshot(
        items=(Item(plan['product'], plan['variant'], int(plan['quantity'])),),
        address=plan['address'], card=plan['card'], matching_cards=1,
        card_selected=True, currency='THB',
        total_satang=plan['price'] * int(plan['quantity']) + plan['shipping'] - discount,
        coupon='' if scenario == 'coupon_missing' else plan['coupon'], observed_at=now,
        available=scenario != 'sold_out')
    if scenario == 'price_changed': return replace(s, total_satang=plan['cap'] + 100)
    if scenario == 'wrong_card': return replace(s, card_selected=False)
    if scenario == 'ambiguous_card': return replace(s, matching_cards=2)
    if scenario == 'wrong_variant': return replace(s, items=(Item(plan['product'], '__OTHER__', 1),))
    if scenario == 'extra_item': return replace(s, items=s.items + (Item('__OTHER__', 'x', 1),))
    if scenario == 'stale_quote': return replace(s, observed_at=now-timedelta(seconds=11))
    return s
