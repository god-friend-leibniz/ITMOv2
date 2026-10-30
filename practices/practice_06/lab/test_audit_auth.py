"""Regressions for quota isolation and order-specific receipt integrity."""

import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from service import Shop


class AuditAuthTest(unittest.TestCase):
    def setUp(self):
        self.shop = Shop()
        self.addCleanup(self.shop.close)
        self.alice = self.login('alice')
        self.bob = self.login('bob')
        self.staff = self.login('staff')

    def request(self, method, path, body=None, auth=None):
        return self.shop.dispatch(method, path, {} if body is None else body,
                                  {} if auth is None else auth)

    def login(self, username):
        status, result = self.request('POST', '/login',
                                      {'username': username, 'password': 'learn-' + username})
        self.assertEqual(status, 200)
        return {'X-Token': result['token']}

    def buy(self, product='lamp', auth=None):
        return self.request('POST', '/orders', {'product': product},
                            self.alice if auth is None else auth)

    def orders(self, auth):
        status, result = self.request('GET', '/orders', auth=auth)
        self.assertEqual(status, 200)
        return result

    def execute(self, path, auth):
        return self.request('POST', '/assistant/execute',
                            {'decision': {'tool': 'read_file', 'arguments': {'path': path}}}, auth)

    def file(self, user, path, auth):
        return self.request('GET', '/files?' + urlencode({'user': user, 'path': path}), auth=auth)

    def test_personal_quota_counts_seed_order_and_preserves_other_customer_capacity(self):
        with patch.object(self.shop, 'MAX_ORDERS_PER_CUSTOMER', 3, create=True):
            for _ in range(2):
                self.assertEqual(self.buy()[0], 201)
            before = self.orders(self.staff)
            self.assertEqual(len(self.orders(self.alice)), 3)
            self.assertEqual(self.buy()[0], 409)
            self.assertEqual(self.orders(self.staff), before)
            self.assertEqual(self.buy(auth=self.bob)[0], 201)
            self.assertEqual(len(self.orders(self.bob)), 2)

    def test_real_personal_quotas_fit_both_customers_inside_global_capacity(self):
        self.assertEqual(getattr(Shop, 'MAX_ORDERS_PER_CUSTOMER', None), 1000)
        customer_count = sum(account[2] == 'customer' for account in self.shop.accounts.values())
        self.assertEqual(customer_count, 2)
        self.assertLessEqual(customer_count * Shop.MAX_ORDERS_PER_CUSTOMER, Shop.MAX_ORDERS)

    def test_global_quota_still_rejects_without_partial_order(self):
        with patch.object(self.shop, 'MAX_ORDERS', 3):
            self.assertEqual(self.buy()[0], 201)
            before = self.orders(self.staff)
            self.assertEqual(self.buy(auth=self.bob)[0], 409)
            self.assertEqual(self.orders(self.staff), before)

    def test_account_session_quota_isolated_and_logout_releases_capacity(self):
        credentials = {'username': 'alice', 'password': 'learn-alice'}
        with patch.object(self.shop, 'MAX_SESSIONS_PER_ACCOUNT', 2, create=True):
            status, second = self.request('POST', '/login', credentials)
            self.assertEqual(status, 200)
            second_auth = {'X-Token': second['token']}
            self.assertEqual(self.request('POST', '/login', credentials)[0], 429)
            self.assertEqual(self.request('GET', '/orders', auth=self.alice)[0], 200)
            self.assertEqual(self.request('GET', '/orders', auth=second_auth)[0], 200)
            self.assertEqual(self.request('POST', '/login',
                                           {'username': 'bob', 'password': 'learn-bob'})[0], 200)
            self.assertEqual(self.request('POST', '/logout', auth=second_auth)[0], 200)
            self.assertEqual(self.request('GET', '/orders', auth=second_auth)[0], 401)
            self.assertEqual(self.request('POST', '/login', credentials)[0], 200)

    def test_new_order_context_and_both_readers_return_that_orders_receipt(self):
        status, order = self.buy('lamp')
        self.assertEqual(status, 201)
        logical_path = f'files/alice/orders/{order["id"]}/receipt.txt'
        relative_path = f'orders/{order["id"]}/receipt.txt'
        status, context = self.request('GET', f'/assistant/context?order_id={order["id"]}', auth=self.alice)
        self.assertEqual(status, 200)
        self.assertIn(logical_path, context['prompt'])
        status, receipt = self.execute(logical_path, self.alice)
        self.assertEqual(status, 200)
        self.assertIn('TEST_ALICE', receipt['content'])
        self.assertIn(order['product'], receipt['content'])
        self.assertIn(str(order['price']), receipt['content'])
        self.assertNotIn('chair', receipt['content'])
        self.assertEqual(self.file('alice', relative_path, self.alice), (200, receipt))
        self.assertEqual(self.file('alice', relative_path, self.staff), (200, receipt))

    def test_new_receipts_check_owner_order_and_exact_resource_name(self):
        status, order = self.buy('lamp')
        self.assertEqual(status, 201)
        relative_path = f'orders/{order["id"]}/receipt.txt'
        logical_path = 'files/alice/' + relative_path
        self.assertEqual(self.execute(logical_path, self.bob)[0], 404)
        self.assertEqual(self.file('alice', relative_path, self.bob)[0], 404)
        self.assertEqual(self.file('bob', relative_path, self.alice)[0], 404)
        self.assertEqual(self.file('bob', relative_path, self.bob)[0], 404)
        self.assertEqual(self.execute('files/bob/' + relative_path, self.alice)[0], 404)
        self.assertEqual(self.execute(logical_path, None)[0], 401)
        for path in ('orders/999999/receipt.txt', f'orders/0{order["id"]}/receipt.txt',
                     f'orders/{order["id"]}/../receipt.txt',
                     f'orders/{order["id"]}/receipt.txt/',
                     f'./orders/{order["id"]}/receipt.txt',
                     '../bob/receipt.txt', '/etc/passwd'):
            with self.subTest(path=path):
                self.assertEqual(self.file('alice', path, self.alice)[0], 404)
                self.assertEqual(self.execute('files/alice/' + path, self.alice)[0], 404)

    def test_initial_receipt_aliases_stay_bound_to_initial_orders(self):
        for username, order_id, product, price, auth in (
                ('alice', 1, 'chair', 5000, self.alice),
                ('bob', 2, 'lamp', 1500, self.bob)):
            with self.subTest(username=username):
                alias = f'files/{username}/receipt.txt'
                status, context = self.request('GET', f'/assistant/context?order_id={order_id}', auth=auth)
                self.assertEqual(status, 200)
                self.assertIn(alias, context['prompt'])
                status, receipt = self.execute(alias, auth)
                self.assertEqual(status, 200)
                self.assertIn('TEST_' + username.upper(), receipt['content'])
                self.assertIn(product, receipt['content'])
                self.assertIn(str(price), receipt['content'])
                self.assertEqual(self.file(username, 'receipt.txt', auth), (200, receipt))
        self.assertEqual(self.buy('lamp')[0], 201)
        self.assertIn('chair', self.execute('files/alice/receipt.txt', self.alice)[1]['content'])


if __name__ == '__main__':
    unittest.main()
