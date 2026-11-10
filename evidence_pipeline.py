"""Reviewable vendor observations, freshness and safe matching.

Source checks and product-release assertions are not interchangeable.  This module
only selects the latest observation per natural evidence identity and classifies
whether the source supports a product-level or release-level claim.
"""
from __future__ import annotations
import json
import re
from urllib.parse import urlsplit, urlunsplit
from quality import match_key
from workbook_data import vendor_name

UNKNOWN_PTF = 'Unknown / Not verified'


def canonical_url(url):
    s=str(url or '').strip()
    u=urlsplit(s)
    if not u.scheme or not u.netloc:return s
    # Keep URL query and fragment: they may identify precise maintenance sections.
    return urlunsplit((u.scheme.lower(),u.netloc.lower(),u.path.rstrip('/') or '/',u.query,u.fragment))


def evidence_identity(o):
    return (vendor_name(o.get('vendor','')).casefold(),
            match_key('',o.get('product',''),o.get('vrm',''))[1:],
            str(o.get('zos_version','')).strip(),
            canonical_url(o.get('source_url','')),
            str(o.get('evidence_level','')).strip(),
            str(o.get('required_level','')).strip(),
            str(o.get('maintenance_ids',o.get('maintenance_id',''))).strip())


def latest_unique_observations(audit_rows):
    """Latest per URL first; repeated refreshes must not multiply assertions.

    Audit rows can be SQLite dicts with assertions_json or in-memory audits with
    assertions. The full audit history remains available separately.
    """
    newest={}
    for row in audit_rows:
        key=(vendor_name(row.get('vendor','')).casefold(),canonical_url(row.get('source_url',row.get('url',''))))
        date=str(row.get('checked_at',''))
        # Do not erase previously extracted evidence after a failed refresh.
        # The audit-history table separately exposes the latest failed check.
        if row.get('state') not in (None,'Read'):continue
        if key not in newest or date>str(newest[key].get('checked_at','')):newest[key]=row
    output=[];seen=set()
    for row in newest.values():
        try:
            assertions=row.get('assertions',None)
            if assertions is None:assertions=json.loads(row.get('assertions_json') or '[]')
            for observation in assertions:
                obs=dict(observation)
                obs['source_checked_at']=row.get('checked_at','')
                ident=evidence_identity(obs)
                if ident not in seen:
                    seen.add(ident);output.append(obs)
        except (ValueError,TypeError,AttributeError):continue
    return output


def observation_match(observation, inventory):
    """Explicit full release is required for an exact match; no fuzzy guessing."""
    v=vendor_name(observation.get('vendor',''))
    version=str(observation.get('vrm','')).strip()
    if not version or version.lower() in ('not stated','unknown','nan'):return None
    needle=match_key(v,observation.get('product',''),version)
    return next((r for r in inventory if match_key(vendor_name(r.get('vendor','')),r.get('product',''),r.get('vrm',''))==needle),None)


def classification(obs, match):
    level=str(obs.get('evidence_level',''))
    if not match:return 'Evidence only — no exact release match'
    if 'Explicit vendor table: product, release' in level and str(obs.get('compatibility','')) in ('Yes','No'):
        return 'Exact release claim — manual review required'
    return 'Matched product/release; statement not a certification'

# Conservative, operator-review-only aliases, never automatic compatibility updates.
REVIEW_NAME_ALIASES = {('precisely','mfxforzos'):'syncsortmfx'}

def review_candidates(observation, inventory):
    """Find possible existing inventory rows for human review, with exact VRM only."""
    version=str(observation.get('vrm','')).strip().lstrip('vV').casefold()
    if not re.fullmatch(r'\d+(?:\.\d+){0,3}',version):return []
    v=vendor_name(observation.get('vendor',''))
    name=match_key(v,observation.get('product',''),version)[1]
    alias=REVIEW_NAME_ALIASES.get((v.casefold(),name))
    if not alias:return []
    return [r for r in inventory if vendor_name(r.get('vendor','')).casefold()==v.casefold()
            and match_key(v,r.get('product',''),r.get('vrm',''))[1:]==(alias,re.sub(r'[^a-z0-9]+','',version))]
