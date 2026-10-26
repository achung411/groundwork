"""Read-only property rent ledger from saved obligations and approved allocations."""
from app.services.payments import review_date


def build_ledger(connection, property_id, as_of):
    as_of = review_date(as_of)
    if not connection.in_transaction:
        connection.execute('BEGIN')
    obligations = [dict(row) for row in connection.execute(
        'SELECT * FROM rent_obligations WHERE property_id=? ORDER BY due_date,id', (property_id,))]
    payments = [dict(row) for row in connection.execute(
        'SELECT a.id,a.amount_cents,a.obligation_id,a.review_decision_id,t.posted_date,t.external_id,t.description,o.period,o.due_date '
        'FROM payment_allocations a JOIN transactions t ON t.id=a.transaction_id '
        'JOIN rent_obligations o ON o.id=a.obligation_id '
        'WHERE o.property_id=? AND t.property_id=? AND t.posted_date<=? ORDER BY t.posted_date,a.id',
        (property_id, property_id, as_of))]
    rows = []
    for obligation in obligations:
        if obligation['due_date'] <= as_of:
            rows.append({'event_date': obligation['due_date'], 'kind': 'Rent charge', 'order': 0, 'id': obligation['id'],
                         'period': obligation['period'], 'due_date': obligation['due_date'], 'received_date': None,
                         'charged_cents': obligation['amount_cents'], 'received_cents': 0,
                         'reference': 'Rent obligation #{}'.format(obligation['id'])})
    for payment in payments:
        rows.append({'event_date': payment['posted_date'], 'kind': 'Approved payment', 'order': 1, 'id': payment['id'],
                     'period': payment['period'], 'due_date': payment['due_date'], 'received_date': payment['posted_date'],
                     'charged_cents': 0, 'received_cents': payment['amount_cents'], 'reference': payment['external_id'],
                     'decision_id': payment['review_decision_id'], 'description': payment['description']})
    rows.sort(key=lambda row: (row['event_date'], row['order'], row['id']))
    balance = 0
    for row in rows:
        balance += row['charged_cents'] - row['received_cents']
        row['balance_cents'] = balance
    pending = [dict(row) for row in connection.execute(
        'SELECT t.* FROM transactions t WHERE property_id=? AND posted_date<=? '
        'AND NOT EXISTS (SELECT 1 FROM payment_allocations a WHERE a.transaction_id=t.id) ORDER BY posted_date,id', (property_id, as_of))]
    return {'as_of': as_of, 'rows': rows, 'balance_cents': balance,
            'charged_cents': sum(row['charged_cents'] for row in rows),
            'received_cents': sum(row['received_cents'] for row in rows),
            'pending': pending, 'pending_cents': sum(row['amount_cents'] for row in pending),
            'upcoming': [row for row in obligations if row['due_date'] > as_of]}
