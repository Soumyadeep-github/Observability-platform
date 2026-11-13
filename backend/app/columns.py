"""Column health is derived from explicitly scoped evidence, never table health."""


def project_columns(state):
    rows = []
    for asset in state['assets']:
        for column in asset['columns']:
            checks = [c for c in asset['checks'] if c['column'] == column['name']]
            alerts = [i for i in state['incidents'] if i['assetId'] == asset['id'] and i.get('column') == column['name'] and i['state'] != 'resolved']
            if not asset['monitorAvailable']:
                health, reason = 'unknown', 'Collector unavailable; column evidence cannot be verified'
            elif any(c['status'] == 'FAIL' for c in checks):
                health, reason = 'critical', 'A column quality assertion failed'
            elif any(c['status'] == 'ERROR' for c in checks):
                health, reason = 'warning', 'A column check could not execute'
            elif any(c['status'] == 'PASS' for c in checks):
                health, reason = 'healthy', 'Configured column assertions passed'
            else:
                health, reason = 'unknown', 'No evaluated column checks'
            rows.append({'id': asset['id'] + ':' + column['name'], 'assetId': asset['id'],
                         'dataset': asset['name'], 'namespace': asset['namespace'], 'owner': asset['owner'],
                         'source': asset['source'], **column, 'health': health, 'reason': reason,
                         'checks': checks, 'alerts': alerts})
    return rows
