import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta
from engine import Engine, BANGKOK

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'test.db'
        self.e = Engine(self.path)
        self.now = datetime.now(BANGKOK)
    def tearDown(self):
        self.e.db.close()
        self.tmp.cleanup()
    def plan(self, **changes):
        p = dict(campaign='demo', product='item', variant='black', quantity=1,
                 address='home', card='main', price='1200', shipping='40', discount='300',
                 cap='1000', budget='1500', start=self.now.isoformat(), window=60,
                 required_coupon=True, coupon='DEMO', scenario='success')
        p.update(changes)
        return self.e.add(p)
    def state(self, job):
        return next(r for r in self.e.rows() if r[0] == job)
    def test_wait_until_due(self):
        j=self.plan(); self.e.tick(self.now-timedelta(seconds=1))
        self.assertEqual(self.state(j)[2], 'ARMED')
        self.e.tick(self.now); self.assertEqual(self.state(j)[2], 'PAID_SIMULATED')
    def test_reopen_no_duplicate(self):
        j=self.plan(); self.e.tick(self.now)
        self.e.db.close(); self.e=Engine(self.path); self.e.tick(self.now)
        sends=[e for e in self.e.events(j) if 'ส่งคำสั่งจำลองครั้งเดียว' in e[1]]
        self.assertEqual(len(sends),1)
    def test_budget_across_jobs(self):
        self.plan(); self.plan(); self.e.tick(self.now)
        self.assertEqual(sorted(r[2] for r in self.e.rows()), ['PAID_SIMULATED','STOPPED'])
    def test_unknown_keeps_budget(self):
        j=self.plan(scenario='unknown'); self.e.tick(self.now)
        self.assertEqual(self.state(j)[3],94000)
        self.e.tick(self.now+timedelta(seconds=90)); self.assertEqual(self.state(j)[2],'UNKNOWN')
    def test_challenge_timeout(self):
        j=self.plan(scenario='challenge'); self.e.tick(self.now)
        self.e.tick(self.now+timedelta(seconds=61))
        self.assertEqual(self.state(j)[2],'UNKNOWN')
        self.e.resolve(j,False); self.assertEqual(self.state(j)[3],0)
    def test_stop_conditions(self):
        for scenario in ('sold_out','coupon_missing','price_changed'):
            j=self.plan(scenario=scenario); self.e.tick(self.now)
            self.assertEqual(self.state(j)[2],'STOPPED')
    def test_optional_coupon_still_checks_cap(self):
        j=self.plan(scenario='coupon_missing', required_coupon=False)
        self.e.tick(self.now); self.assertEqual(self.state(j)[2],'STOPPED')
    def test_expired(self):
        j=self.plan(); self.e.tick(self.now+timedelta(seconds=60))
        self.assertEqual(self.state(j)[2],'EXPIRED')
    def test_cancel(self):
        j=self.plan(); self.e.cancel(j); self.e.tick(self.now)
        self.assertEqual(self.state(j)[2],'CANCELLED')
    def test_invalid_money(self):
        for value in ('NaN','-1','1.001','Infinity'):
            with self.assertRaises(ValueError): self.plan(price=value)
    def test_decline_releases(self):
        j=self.plan(scenario='declined'); self.e.tick(self.now)
        self.assertEqual(self.state(j)[3],0)
    def test_conflicting_campaign_budget(self):
        self.plan()
        with self.assertRaises(ValueError): self.plan(budget='2000')

if __name__ == '__main__': unittest.main()
