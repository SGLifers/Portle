import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from portle.__main__ import main


class EditorCliTests(unittest.TestCase):
    def setUp(self):
        self.config=patch('portle.__main__.load_dotenv');self.config.start();self.addCleanup(self.config.stop)
    def test_editor_starts_without_opening_player_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            # Bot-only configuration must not prevent the authoring tool opening.
            settings={'PORTLE_CLUE_SOURCE':'manual','PORTLE_DATABASE':str(root/'private.sqlite3'),
                      'PORTLE_TIMEZONE':'invalid/zone','DISCORD_GUILD_ID':'not-a-server'}
            with patch.dict(os.environ,settings,clear=True),patch('portle.__main__.ROOT',root),patch('sys.argv',['portle','editor','--port','8749']),patch('portle.editor.serve') as serve,patch('portle.store.GameStore',side_effect=AssertionError('Editor opened player DB')):
                self.assertEqual(main(),0)
            catalog,library,port=serve.call_args.args
            self.assertGreater(len(catalog.maps),0);self.assertEqual(library.root,root/'data/clues');self.assertEqual(port,8749)
            self.assertFalse(list(root.rglob('*.sqlite3')))
    def test_old_preview_command_is_removed(self):
        with patch('sys.argv',['portle','preview']),contextlib.redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as result:main()
        self.assertEqual(result.exception.code,2);self.assertIn('invalid choice',error.getvalue())
    def test_editor_requires_manual_clue_source(self):
        with patch.dict(os.environ,{'PORTLE_CLUE_SOURCE':'generated'},clear=True),patch('sys.argv',['portle','editor']),contextlib.redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as result:main()
        self.assertEqual(result.exception.code,2);self.assertIn('requires PORTLE_CLUE_SOURCE=manual',error.getvalue())
