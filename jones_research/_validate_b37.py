import json, collections
d = json.load(open('jonesbatch_37_results.json'))
print('records:', len(d))
print('conf:', dict(collections.Counter(r['confidence'] for r in d)))
print('null_industry:', sum(1 for r in d if r['industry'] is None))
print('with_affils:', sum(1 for r in d if r['affiliations']))
print('searches_ok:', all(set(r['searches_run']) == {'fec_pac','tx_lobbyist','bio_full_read'} for r in d))
cats = {'aipac_direct','pro_israel','liberal_zionist','jewish_civic','palestine_solidarity','pro_palestine_advocacy','oil_gas','gun_rights','gun_control','military_defense','civic','business','political'}
bad = [(r['name'], a['category']) for r in d for a in r['affiliations'] if a['category'] not in cats]
print('bad_categories:', bad)
print('affils_missing_src:', [(r['name']) for r in d for a in r['affiliations'] if not a.get('source_url') or not a.get('snippet')])
