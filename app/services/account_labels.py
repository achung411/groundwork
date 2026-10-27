"""Explicit, property-owned description phrases; retired labels retain historical ownership."""
import json

from app.db import connect


class AccountLabelError(ValueError):
    pass


def normalize(value):
    return value.strip().casefold()


def owners(connection, historical=False):
    result = {normalize(row['account_label']): row['id'] for row in connection.execute('SELECT id, account_label FROM properties')}
    for row in connection.execute('SELECT * FROM property_account_labels'):
        if historical or row['active']:
            result[row['normalized_label']] = row['property_id']
    return result


def settings(connection, property_id):
    record = connection.execute('SELECT * FROM properties WHERE id=?', (property_id,)).fetchone()
    if record is None:
        raise AccountLabelError('Property not found.')
    aliases = [row['label'] for row in connection.execute(
        'SELECT label FROM property_account_labels WHERE property_id=? AND active=1 ORDER BY normalized_label', (property_id,))
        if normalize(row['label']) != normalize(record['account_label'])]
    return {'preferred_label': record['account_label'], 'aliases': '\n'.join(aliases)}


def save_settings(property_id, preferred_label, aliases):
    labels = [preferred_label.strip()] + [line.strip() for line in aliases.splitlines() if line.strip()]
    if len(labels) > 30:
        raise AccountLabelError('Use at most 30 labels per property.')
    if any(not label or len(label) > 160 or any(ord(char) < 32 or ord(char) == 127 for char in label) for label in labels):
        raise AccountLabelError('Each account label must contain 1–160 characters without control characters.')
    requested = {normalize(label): label for label in reversed(labels)}
    with connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        before = settings(connection, property_id)
        reserved = owners(connection, historical=True)
        for key, label in requested.items():
            if key in reserved and reserved[key] != property_id:
                raise AccountLabelError('Account label “{}” is already reserved for another property. Choose a distinct label.'.format(label))
        # Claim the old label before changing the preferred one; never rewrite imported evidence.
        old = before['preferred_label']
        connection.execute('INSERT OR IGNORE INTO property_account_labels(normalized_label,label,property_id,active) VALUES (?,?,?,1)',
                           (normalize(old), old, property_id))
        connection.execute('UPDATE property_account_labels SET active=0 WHERE property_id=?', (property_id,))
        for key, label in requested.items():
            connection.execute('INSERT INTO property_account_labels(normalized_label,label,property_id,active) VALUES (?,?,?,1) '
                               'ON CONFLICT(normalized_label) DO UPDATE SET label=excluded.label,active=1', (key, label, property_id))
        connection.execute('UPDATE properties SET account_label=? WHERE id=?', (labels[0], property_id))
        after = settings(connection, property_id)
        if before != after:
            connection.execute("INSERT INTO review_decisions(record_type,record_id,decision,reviewer_label,notes) VALUES ('property',?,'matching_labels_changed','Demo owner',?)",
                               (property_id, json.dumps({'before': before, 'after': after})))
