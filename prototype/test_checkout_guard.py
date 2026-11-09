import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from checkout_guard import validate, simulated_snapshot, CheckoutBlocked
from engine import BANGKOK
import test_engine


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(BANGKOK)
        self.p = dict(product='item', variant='black', quantity=1, address='home', card='main',
                      scenario='success', price=120000, shipping=4000, discount=30000,
                      cap=100000, budget=150000, coupon='DEMO', required_coupon=True)
        self.s = simulated_snapshot(self.p, self.now)

    def test_valid_quote(self):
        self.assertEqual(validate(self.p,self.s,self.now,0),94000)

    def test_identity_and_money_rejections(self):
        cases = [dict(address='other'), dict(card='other'), dict(card_selected=False),
                 dict(matching_cards=0), dict(matching_cards=2), dict(currency='MYR'),
                 dict(total_satang=-1), dict(total_satang=94000.0), dict(total_satang=100001),
                 dict(coupon='OTHER'), dict(items=()), dict(available=False),
                 dict(observed_at=self.now+timedelta(seconds=1)),
                 dict(observed_at=self.now-timedelta(seconds=11))]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(CheckoutBlocked):
                validate(self.p,replace(self.s,**case),self.now,0)

    def test_final_total_is_authoritative(self):
        self.assertEqual(validate(self.p,replace(self.s,total_satang=99000),self.now,0),99000)

    def test_campaign_budget(self):
        with self.assertRaises(CheckoutBlocked): validate(self.p,self.s,self.now,60000)


class CheckoutIntegrationTests(unittest.TestCase):
    setUp = test_engine.Tests.setUp
    tearDown = test_engine.Tests.tearDown
    plan = test_engine.Tests.plan
    state = test_engine.Tests.state
    def test_bad_checkout_never_submits(self):
        for scenario in ('wrong_card','ambiguous_card','wrong_variant','extra_item','stale_quote'):
            with self.subTest(scenario=scenario):
                j=self.plan(scenario=scenario); self.e.tick(self.now)
                self.assertEqual(self.state(j)[2],'STOPPED')
                self.assertIsNone(self.state(j)[4])
                self.assertFalse(any('ส่งคำสั่งจำลองครั้งเดียว' in event[1] for event in self.e.events(j)))

    def test_payment_url_is_not_success(self):
        j=self.plan(scenario='payment_page_only'); self.e.tick(self.now)
        self.assertEqual(self.state(j)[2],'UNKNOWN')
        self.e.tick(self.now)
        self.assertEqual(sum('ส่งคำสั่งจำลองครั้งเดียว' in m for _,m in self.e.events(j)),1)

    def test_resolve_paid_without_new_submission(self):
        j=self.plan(scenario='unknown'); self.e.tick(self.now)
        self.e.resolve(j,True); self.e.tick(self.now)
        self.assertEqual(self.state(j)[2],'PAID_SIMULATED')
        self.assertEqual(sum('ส่งคำสั่งจำลองครั้งเดียว' in m for _,m in self.e.events(j)),1)

if __name__ == '__main__': unittest.main()
