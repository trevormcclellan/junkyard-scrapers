import copy
import os
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from junkyard.common import InventoryError
from junkyard import worker


class Collection:
    """Mongo-shaped test double with explicit query semantics."""
    def __init__(self, documents=()):
        self.docs = copy.deepcopy(list(documents))
        self.writes = []

    def find(self, query):
        return [copy.deepcopy(doc) for doc in self.docs if all(doc.get(k) == v for k, v in query.items())]

    def find_one(self, query):
        return next(iter(self.find(query)), None)

    def insert_one(self, doc):
        self.writes.append(('insert', copy.deepcopy(doc)))
        self.docs.append(copy.deepcopy(doc))

    def delete_one(self, query):
        self.writes.append(('delete', query))
        doc = self.find_one(query)
        if doc:
            self.docs.remove(doc)

    def update_one(self, query, update):
        self.writes.append(('update', query, update))
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                doc.update(update['$set'])
                return


def car(stock='123', location='Dayton', **fields):
    return {'stock_num': stock, 'location': location, 'year': 2001, 'model': 'E-CLASS', **fields}


class WorkerTests(unittest.TestCase):
    def test_watch_rules_preserve_main_and_utah_behavior(self):
        cars = [car(), car('456', year=2010, model='C-CLASS')]
        self.assertEqual([c['interest_level'] for c in worker.watch_results('picknpull', cars)], [1, 0])
        self.assertEqual(len(worker.watch_results('utpap', cars)), 1)
        self.assertTrue(worker.interested('lkq', car(model='E320')))
        self.assertFalse(worker.interested('utpap', car(model='E320')))
        self.assertNotIn('interest_level', cars[0])

    def test_failure_preserves_inventory_and_other_location_runs(self):
        collection = Collection([car('old')])
        failure = Mock(side_effect=InventoryError('layout changed'))
        success = Mock(return_value=[car('new', 'Cincinnati')])
        notify = Mock()
        with patch.object(worker, 'searches', return_value=[({'location': 'Dayton'}, failure), ({'location': 'Cincinnati'}, success)]), self.assertLogs(worker.LOG, level='ERROR'):
            self.assertFalse(worker.run_checks('lkq', collection, notify))
        self.assertEqual({c['stock_num'] for c in collection.docs}, {'old', 'new'})
        success.assert_called_once()
        notify.assert_called_once()

    def test_partial_generator_failure_causes_no_writes(self):
        def broken():
            yield car('new')
            raise InventoryError('second page failed')
        collection = Collection([car('old')])
        with patch.object(worker, 'searches', return_value=[({}, broken)]), self.assertLogs(worker.LOG, level='ERROR'):
            self.assertFalse(worker.run_checks('lkq', collection, Mock()))
        self.assertEqual(collection.writes, [])

    def test_scope_validated_before_interest_filtering(self):
        collection = Collection([car('old', 'Orem')])
        fetch = Mock(return_value=[car(location='Ogden', year=2010)])
        with patch.object(worker, 'searches', return_value=[({'location': 'Orem'}, fetch)]), self.assertLogs(worker.LOG, level='ERROR'):
            self.assertFalse(worker.run_checks('utpap', collection, Mock()))
        self.assertEqual(collection.writes, [])

    def test_successful_empty_snapshot_only_removes_its_scope(self):
        collection = Collection([car('same'), car('same', 'Cincinnati')])
        worker.sync_snapshot(collection, {'location': 'Dayton'}, [], Mock(), 'lkq')
        self.assertEqual(collection.docs, [car('same', 'Cincinnati')])

    def test_duplicate_or_wrong_location_rejected_before_writes(self):
        for snapshot in ([car(), car()], [car(location='Cincinnati')]):
            collection = Collection([car('old')])
            with self.assertRaises(InventoryError):
                worker.sync_snapshot(collection, {'location': 'Dayton'}, snapshot, Mock(), 'lkq')
            self.assertEqual(collection.writes, [])

    def test_existing_car_updated_without_arrival_notification(self):
        collection, notify = Collection([car(row='4', series='Preserved')]), Mock()
        worker.sync_snapshot(collection, {}, [car(row='5')], notify, 'lkq')
        notify.assert_not_called()
        self.assertEqual(collection.docs[0]['row'], '5')
        self.assertEqual(collection.docs[0]['series'], 'Preserved')

    def test_notification_failure_does_not_insert_or_delete(self):
        collection = Collection([car('old')])
        with self.assertRaises(InventoryError):
            worker.sync_snapshot(collection, {}, [car('new')], Mock(side_effect=InventoryError('webhook failed')), 'lkq')
        self.assertEqual(collection.writes, [])

    def test_jacks_legacy_identity_does_not_renotify(self):
        old = car(location="Jack's")
        old.pop('location')
        collection, notify = Collection([old]), Mock()
        worker.sync_snapshot(collection, {}, [car(location="Jack's")], notify, 'jacks')
        self.assertEqual(len(collection.docs), 1)
        notify.assert_not_called()

    def test_existing_missing_image_notifies_with_new_image(self):
        collection, notify = Collection([car(image=None)]), Mock()
        worker.sync_snapshot(collection, {}, [car(image='https://example.test/car.jpg')], notify, 'pullapart')
        notify.assert_called_once()
        self.assertEqual(collection.docs[0]['image'], 'https://example.test/car.jpg')

    def test_scheduler_runs_later_yards_after_failure(self):
        with patch.object(worker, 'configured_yards', return_value=['jacks', 'lkq']), patch.object(worker.subprocess, 'run', side_effect=[subprocess.TimeoutExpired('test', 1), Mock(returncode=0)]) as run, patch.object(worker, 'write_health') as health, self.assertLogs(worker.LOG, level='ERROR'):
            self.assertFalse(worker.run_cycle())
        self.assertEqual(run.call_count, 2)
        health.assert_called_once_with('jacks', False)

    def test_configured_yards_validation(self):
        with patch.dict(os.environ, {'SCRAPER_YARDS': 'lkq,utpap,lkq'}):
            self.assertEqual(worker.configured_yards(), ['lkq', 'utpap'])
        with patch.dict(os.environ, {'SCRAPER_YARDS': 'bogus'}), self.assertRaises(ValueError):
            worker.configured_yards()

    def test_health_requires_success_and_freshness(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'status'
            with patch.object(worker, 'configured_yards', return_value=['lkq']), patch.object(worker, 'health_file', return_value=path):
                self.assertFalse(worker.healthcheck())
                path.write_text('healthy')
                self.assertTrue(worker.healthcheck())
                os.utime(path, (1, 1))
                self.assertFalse(worker.healthcheck())
                path.write_text('unhealthy')
                self.assertFalse(worker.healthcheck())
