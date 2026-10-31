"""Real Chromium UI test with explicitly synthetic provider and corpus fixtures."""
import os
import threading
import time
import pytest
from .conftest import Script, fixture_corpus, clarify
from wireless_assistant.app import create_app
from wireless_assistant.common import canonical
from wireless_assistant.engine import Engine


@pytest.mark.skipif(os.environ.get('WA_BROWSER_TEST')!='1',reason='Opt-in Chromium test; see setup guide')
def test_browser_chat_sources_clarification_cancel_and_delete(settings,monkeypatch):
    from playwright.sync_api import sync_playwright,expect
    import uvicorn
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-test-only')
    monkeypatch.setenv('WA_FREE_TIER_CONFIRMED','1')
    script=Script()
    app=create_app(settings,lambda s:Engine(s,role_transport=script,embedding_transport=lambda q:[1.0]+[0.0]*767,require_ready=False))
    fixture_corpus(app.state.store)
    with app.state.store.transaction() as db:
        db.execute('UPDATE corpus_builds SET config_json=?',(canonical({'retrieval':'hybrid','embedding_model':'gemini-embedding-001','dimensions':768}),))
        db.execute('INSERT INTO passage_vectors VALUES (?,?,?,?)',('fixture-passage','gemini-embedding-001',768,canonical([1.0]+[0.0]*767)))
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=settings.port,log_level='error',access_log=False))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    deadline=time.monotonic()+5
    while not server.started and time.monotonic()<deadline:time.sleep(.02)
    assert server.started
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1365,'height':900})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto('http://127.0.0.1:'+str(settings.port))
            expect(page.locator('#send')).to_be_enabled()
            page.locator('#question').fill('Explain an NR resource block <script>alert(1)</script>')
            page.locator('#send').click()
            expect(page.locator('.message.assistant')).to_contain_text('twelve consecutive',timeout=15000)
            page.get_by_role('button',name='[1] View source').click()
            expect(page.locator('#source-dialog')).to_be_visible()
            expect(page.locator('#source-meta')).to_contain_text('18.10.0')
            page.locator('#close-source').click()
            page.get_by_role('button',name='unclear',exact=True).click()
            expect(page.get_by_role('button',name='Saved',exact=True)).to_be_visible()
            page.once('dialog',lambda dialog:dialog.accept('Browser verified chat'))
            page.locator('#rename-chat').click()
            expect(page.locator('#chat-title')).to_have_text('Browser verified chat')
            page.reload()
            page.get_by_role('button',name='Browser verified chat',exact=True).click()
            expect(page.locator('.message.assistant')).to_contain_text('twelve consecutive')
            script.actions=[('A',clarify)]
            page.locator('#question').fill('Explain that part')
            page.locator('#send').click()
            expect(page.locator('#run-label')).to_contain_text('Waiting for your reply',timeout=15000)
            expect(page.locator('#busy-indicator')).to_be_hidden()
            page.locator('#cancel-run').click()
            expect(page.locator('#run-status')).to_be_hidden()
            from pathlib import Path
            out=Path('artifacts');out.mkdir(exist_ok=True)
            page.screenshot(path=str(out/'browser-chat.png'),full_page=True)
            page.once('dialog',lambda dialog:dialog.accept())
            page.locator('#delete-chat').click()
            expect(page.locator('#welcome')).to_be_visible()
            expect(page.locator('#chat-list')).to_be_empty()
            assert errors==[]
            browser.close()
    finally:
        server.should_exit=True;thread.join(5)
        assert not thread.is_alive()
