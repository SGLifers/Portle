"""Exercise real process locks, including Windows spawn workers."""
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from pathlib import Path
import tempfile
import time
import unittest

from portle.clues import ClueLibrary


def increment_index(root):
    library=ClueLibrary(root)
    for _ in range(10):
        with library._edit() as data:
            value=data.get('lock_test_count',0)
            time.sleep(.01)
            data['lock_test_count']=value+1


class LibraryLockTests(unittest.TestCase):
    def test_independent_processes_do_not_lose_index_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('spawn')) as pool:
                list(pool.map(increment_index,[directory]*4))
            self.assertEqual(ClueLibrary(directory)._read()['lock_test_count'],40)

    def test_failed_edit_releases_lock_without_publishing_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            library=ClueLibrary(directory)
            with self.assertRaises(RuntimeError):
                with library._edit() as data:
                    data['lock_test_count']=99
                    raise RuntimeError('Aborted edit')
            self.assertFalse((Path(directory)/'index.json').exists())
            with ProcessPoolExecutor(max_workers=1,mp_context=multiprocessing.get_context('spawn')) as pool:
                pool.submit(increment_index,directory).result(timeout=20)
            self.assertEqual(library._read()['lock_test_count'],10)
