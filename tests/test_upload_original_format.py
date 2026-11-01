import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import prehrajto_upload as upload


@pytest.mark.parametrize('suffix,mime', [('.mkv','video/x-matroska'), ('.mp4','video/mp4'),
                                       ('.avi','video/x-msvideo')])
def test_prepare_and_multipart_keep_original_container(monkeypatch, tmp_path, suffix, mime):
    path = tmp_path / ('source' + suffix)
    path.write_bytes(b'video')
    calls = []
    class Response:
        status_code, text = 200, '{}'
        def raise_for_status(self):pass
        def json(self):return {'params':json.dumps({'video_id':123}), 'response':'ok',
                               'project':'test','nonce':'test','signature':'test'}
    class Session:
        def get(self, *a, **kw):return Response()
        def post(self, url, **kwargs):
            calls.append((url,kwargs));return Response()
    cdn = []
    def post(url, **kwargs):
        file_entry = kwargs['files'][0][1]
        cdn.append((file_entry[0],file_entry[2]))
        return Response()
    monkeypatch.setattr(upload.requests, 'post', post)
    assert upload.upload_video(Session(),path,display_name='Example S01E02 - 2. epizoda CZ Dabing') == 123
    prep = calls[0][1]['data']
    assert prep['type'] == mime
    assert prep['name'].endswith(suffix)
    assert cdn == [(prep['name'],mime)]
    assert calls[-1][1]['data']['uploadedVideoListing-name'] == 'Example S01E02 - 2. epizoda CZ Dabing'


def test_login_does_not_log_response_bodies_or_cookie_values(monkeypatch, capsys):
    from unittest.mock import Mock
    session = Mock(headers={}, cookies={'PHPSESSID': 'private-cookie-value', 'Nette': 'private-csrf-value'})
    response = Mock(status_code=200, text='private-login-response', headers={
        'content-type': 'application/json', 'set-cookie': 'PHPSESSID=private-cookie-value; Path=/'})
    session.get.return_value = response
    session.post.return_value = response
    monkeypatch.setattr(upload.requests, 'Session', lambda: session)
    assert upload.login('test@example.invalid', 'private-password') is session
    output = capsys.readouterr().out
    for value in ['private-cookie-value', 'private-csrf-value', 'private-login-response', 'private-password']:
        assert value not in output
    assert '/profil check status=200' in output


def test_upload_does_not_log_nonce_or_signatures(monkeypatch, tmp_path, capsys):
    from unittest.mock import Mock
    path = tmp_path / 'source.mp4'
    path.write_bytes(b'video')
    prepared = {'params': json.dumps({'video_id': 123}), 'response': 'JSON', 'project': '1',
                'nonce': 'private-nonce', 'signature': 'private-prepare-signature'}
    prep = Mock(status_code=200)
    prep.json.return_value = prepared
    session = Mock()
    session.post.return_value = prep
    cdn = Mock(status_code=200, text='private-cdn-signature')
    post = Mock(return_value=cdn)
    monkeypatch.setattr(upload.requests, 'post', post)
    assert upload.upload_video(session, path) == 123
    output = capsys.readouterr().out
    for value in ['private-nonce', 'private-prepare-signature', 'private-cdn-signature']:
        assert value not in output
    fields = dict(post.call_args.kwargs['files'])
    assert fields['nonce'][1] == prepared['nonce']
    assert fields['signature'][1] == prepared['signature']
