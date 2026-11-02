import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


client = load('vision_client', ROOT / 'vision/scripts/detect.py')
command = load('vision_command', ROOT / 'vision_command.py')


class VisionTests(unittest.TestCase):
    def test_only_latest_user_command_activates(self):
        p = {'messages': [{'role': 'user', 'content': '/vision photo.png'},
                          {'role': 'user', 'content': 'hello'}]}
        self.assertIs(command.prepare_vision_command(p), p)

    def test_command_boundary(self):
        for text in ['/visionary', 'explain /vision', '/web /vision']:
            p = {'messages': [{'role': 'user', 'content': text}]}
            self.assertIs(command.prepare_vision_command(p), p)

    def test_multimodal_preserves_input_and_policy(self):
        p = {'model': 'configured-model', 'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': '/vision'},
            {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,TEST'}}]}]}
        result = command.prepare_vision_command(p)
        self.assertEqual(result['messages'][1], p['messages'][0])
        self.assertEqual(len(p['messages']), 1)
        self.assertEqual(result['model'], 'configured-model')
        self.assertIn('existing approvals', result['messages'][0]['content'])

    def test_bad_service_origins(self):
        for url in ['', 'file:///etc/passwd', 'http://u:p@host', 'http://host/path', 'http://host/?secret=x']:
            with self.assertRaises(ValueError):
                client.origin(url)

    def test_output_cannot_change_origin(self):
        for path in ['https://other/image.jpg', '//other/x', '/outputs/../secret', '/outputs/x?key=y']:
            with self.assertRaises(ValueError):
                client.output_url('http://vision:8015', path)

    def run_response(self, result):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / 'photo.png'
            image.write_bytes(b'IMAGE_BYTES_FOR_TRANSPORT_TEST')
            response = MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps(result).encode()
            opener = MagicMock()
            opener.open.return_value = response
            with patch.object(client, 'build_opener', return_value=opener):
                output = client.detect(image, 'http://vision:8015')
                request = opener.open.call_args.args[0]
                self.assertEqual(request.full_url, 'http://vision:8015/api/detect')
                self.assertIn(b'IMAGE_BYTES_FOR_TRANSPORT_TEST', request.data)
                self.assertIn(b'name="file"', request.data)
                return output

    def test_detection_response_links(self):
        output = self.run_response({'status': 'ok', 'count': 1,
            'annotated_url': '/outputs/a.jpg', 'detections': [
                {'label': 'book', 'score': 0.9, 'crop_url': '/outputs/b.jpg'}]})
        self.assertEqual(output['annotated_url'], 'http://vision:8015/outputs/a.jpg')
        self.assertEqual(output['detections'][0]['crop_url'], 'http://vision:8015/outputs/b.jpg')

    def test_zero_detections_is_valid(self):
        self.assertEqual(self.run_response({'status': 'ok', 'count': 0,
            'annotated_url': '/outputs/a.jpg', 'detections': []})['count'], 0)

    def test_invalid_result_fails(self):
        with self.assertRaises(ValueError):
            self.run_response({'status': 'ok', 'count': 1, 'detections': []})

    def test_empty_input_fails_before_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'empty.png'
            p.touch()
            with patch.object(client, 'build_opener') as opener:
                with self.assertRaises(ValueError):
                    client.detect(p, 'http://vision:8015')
                opener.assert_not_called()

    def test_redirect_is_refused(self):
        self.assertIsNone(client.NoRedirect().redirect_request(None, None, 307, '', {}, 'http://other'))


if __name__ == '__main__':
    unittest.main()
