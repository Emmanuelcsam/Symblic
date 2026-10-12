"""Image assembly (symblic/os/image_builder.py): synthetic copies only, no compiler or image tool runs.

The builder's copies are replaced by writes of fixture bytes, the guest daemon binary is reported as
already built, and any subprocess (gcc, cpio, mkfs) fails the test. Covers the refusal of an image that
picked up a file that looks like a secret, and a clean assembly listing what the image really holds.
Run: DASH_TEST=1 python3 -m unittest discover -s tests/os -t .
"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from symblic.os.image_builder import BootableImageBuilder


class ImageSecretScanTests(unittest.TestCase):
    def assemble(self, root, injected_name):
        builder = BootableImageBuilder(root)
        exists = __import__('os').path.exists

        def copy_fixture(_source, destination):
            target = Path(destination)
            target.write_bytes(b'synthetic executable or source fixture\n')
            if target.name == 'guest_daemon':
                (target.parent / injected_name).write_text('synthetic fixture only\n')

        with patch('symblic.os.image_builder.shutil.which', return_value='/fixture/busybox'), \
                patch('symblic.os.image_builder.shutil.copy2', side_effect=copy_fixture), \
                patch('symblic.os.image_builder.os.path.exists', side_effect=lambda path:
                      True if str(path) == builder.daemon_path else exists(path)), \
                patch('symblic.os.image_builder.subprocess.run',
                      side_effect=AssertionError('No compiler or image tool may run')) as launch:
            try:
                return builder.assemble_rootfs()
            finally:
                launch.assert_not_called()
                self.assertFalse(Path(builder.image_path).exists())
                self.assertFalse(Path(builder.initrd_path).exists())
                self.assertFalse(Path(builder.manifest_path).exists())

    def test_detected_secret_names_raise_a_security_refusal(self):
        for name in ('.env', '.env.local', 'secrets.json', 'cloud-credentials.txt', 'fixture.pem', 'fixture.key'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as root:
                with self.assertRaisesRegex(PermissionError, 'Secret file detected in rootfs'):
                    self.assemble(root, name)

    def test_a_clean_synthetic_assembly_lists_what_the_image_holds(self):
        with tempfile.TemporaryDirectory() as root:
            result = self.assemble(root, 'notes.txt')
            self.assertTrue(result['secrets_clean'])
            self.assertEqual(Path(root, 'rootfs'), Path(result['rootfs_dir']))
            self.assertEqual(['bin/busybox', 'init', 'opt/symblicos/language.py', 'opt/symblicos/guest_daemon'],
                             result['components'])          # no terminal page unless one is passed in


if __name__ == '__main__':
    unittest.main()
