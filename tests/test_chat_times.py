"""Orari della chat in UTC esplicito: il browser li converte nell'ora italiana (collaudo 10/11: un'ora indietro)."""
from test_agents_feature import env
from test_delivery_pod import setup_portals


def test_chat_times_are_marked_utc_for_driver_and_office(env):
    client, db, owner, route, delivery, account = setup_portals(env)
    sent = client.post('/api/driver/chat/direct', json={'message': 'In ritardo di 10 minuti'})
    assert sent.status_code == 200, sent.text
    mine = client.get('/api/driver/chat/direct').json()
    items = mine.get('messages', mine) if isinstance(mine, dict) else mine
    assert items and all(m['created_at'].endswith('Z') for m in items)
    threads = client.get('/api/driver/admin/chat-threads').json()
    assert any(t['last_message_at'] and t['last_message_at'].endswith('Z') for t in threads)
