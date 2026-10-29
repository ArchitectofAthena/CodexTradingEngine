"""Original Stage A contract, tested against the independent Stage B validator."""
import copy
import json
import unittest
from datetime import datetime, UTC
from pathlib import Path

from eve_q.evm_capability_registry import validate_registry

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT
NOW = datetime(2026,10,29,12,tzinfo=UTC)


def original():
    return json.loads((ORIGINAL/'registry/evm_capabilities_v0_1.json').read_text())


def pins():
    return {n['network_id']:n['chain_id'] for n in original()['networks']}


def mutate(raw, change):
    value=copy.deepcopy(raw)
    parts=change['path'].split('/')[1:]
    target=value
    for part in parts[:-1]:
        target=target[int(part)] if isinstance(target,list) else target[part]
    key=int(parts[-1]) if isinstance(target,list) else parts[-1]
    target[key]=copy.deepcopy(change['value'])
    return value


def source():
    contract=json.loads((ORIGINAL/'tests/fixtures/evm_negative_contract_v0_1.json').read_text())
    return copy.deepcopy(next(c for c in contract['cases'] if c['id']=='N16')['mutation']['value'][0])


class OriginalStageAContractTests(unittest.TestCase):
    def validate(self,raw):
        return validate_registry(raw,now=NOW,pinned_identities=pins())

    def test_original_fourteen_profile_baseline(self):
        self.assertEqual(self.validate(original()),())
        self.assertEqual(len(original()['networks']),14)

    def test_original_files_are_preserved_byte_for_byte(self):
        import hashlib
        expected={
            'registry/evm_capabilities_v0_1.json':'7a1595fcab02975449ba4bbe8df3165ac1ac659de69644022d56c5845b1508db',
            'schemas/evm_capability_registry_v0_1.schema.json':'92532dd20bf56707ed2d6a01a8bb1b75919663d9739f69c9838788d90e47d488',
            'tests/fixtures/evm_negative_contract_v0_1.json':'6b8fabb6a04f7a8dc75911b3fa63217a501a22507198d7228a5eb86331720fc3',
        }
        for name,digest in expected.items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest)
        self.assertEqual((ROOT/'eve_q/evm_capability_registry_v0_1.schema.json').read_bytes(),(ROOT/'schemas/evm_capability_registry_v0_1.schema.json').read_bytes())

    def test_N01_through_N22_original_meanings_and_codes(self):
        contract=json.loads((ORIGINAL/'tests/fixtures/evm_negative_contract_v0_1.json').read_text())
        cases=[c for c in contract['cases'] if c['test_kind']=='LOCAL_CONTRACT']
        self.assertEqual([c['id'] for c in cases],[f'N{i:02}' for i in range(1,23)])
        for case in cases:
            with self.subTest(case=case['id']):
                self.assertIn(case['reason_code'],self.validate(mutate(original(),case['mutation'])))

    def test_source_credentials_are_refused(self):
        raw=original();s=source();s['url']='https://user:pass@example.org/stats'
        raw['networks'][0]['source_reviews']=[s]
        self.assertIn('SOURCE_CREDENTIALS_PROHIBITED',self.validate(raw))

    def test_malformed_source_url_is_refusal(self):
        raw=original();s=source();s['url']='https://[malformed'
        raw['networks'][0]['source_reviews']=[s]
        self.assertIn('SOURCE_URL_INVALID',self.validate(raw))

    def test_naive_source_expiry_is_refusal(self):
        raw=original();s=source();s['review_expires_at']='2026-10-30T00:00:00'
        raw['networks'][0]['source_reviews']=[s]
        self.assertIn('SOURCE_REVIEW_INVALID_EXPIRY',self.validate(raw))

    def test_network_review_expiry_is_checked(self):
        raw=original();raw['networks'][0]['evidence'].update(review_sha256='a'*64,last_reviewed_at='2026-08-01T00:00:00Z',review_expires_at='2026-09-04T00:00:00Z')
        self.assertIn('EVIDENCE_REVIEW_EXPIRED',self.validate(raw))

    def test_pinned_dependency_missing_is_refusal(self):
        self.assertIn('PINNED_IDENTITIES_UNAVAILABLE',validate_registry(original(),now=NOW,pinned_identities=None))

    def test_source_commit_cannot_drift(self):
        raw=original();raw['networks'][0]['evidence']['source_commit']='f'*40
        self.assertIn('SOURCE_COMMIT_MISMATCH',self.validate(raw))

    def test_invalid_timestamp_format(self):
        raw=original();raw['as_of_utc']='not-a-timestamp'
        self.assertIn('SCHEMA_REJECT',self.validate(raw))
