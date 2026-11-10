"""Transparent z/OS maintenance assertions; never equate an ID with installability.

Status applies to an explicit vendor/workbook phrase, not merely the presence
of an identifier. Avoid combining maintenance IDs from a different z/OS release.
"""
from __future__ import annotations
import re
from typing import Mapping

_ID = re.compile(r'\b(?:LU|RO|SO|UI|UK|UA|UQ|UJ|AQ|UO|UR|PH|PI|PM|PK|OA)[0-9]{5,7}\b',re.I)


def ptf_ids(value):
    if isinstance(value,(list,tuple,set)):
        value=' '.join(str(x) for x in value)
    return sorted(set(x.upper() for x in _ID.findall(str(value or ''))))


def maintenance_availability(text):
    """Conservative classification of *publication* availability, not install state.

    The text is retained separately; mixed assertions cannot be reduced safely
    to an unqualified Available/Required status.
    """
    t=re.sub(r'\s+',' ',str(text or '')).strip().lower()
    if not t or t in ('verify','nan','n/a','none','unknown'):
        return 'Unknown'
    unavailable=bool(re.search(r'\b(not available|unavailable|not yet available|pending release|not released|awaiting release)\b',t))
    superseded=bool(re.search(r'\b(superseded|replaced by|supersedes)\b',t))
    if unavailable and superseded:return 'Mixed: unavailable / superseded'
    if unavailable:return 'Not available'
    if superseded:return 'Superseded / replacement noted'
    if re.search(r'\b(not installed|not applied|not yet installed|not yet applied)\b',t):
        return 'Availability unknown — not installed is a separate status'
    if re.search(r'\b(available|published|released)\b',t):return 'Published / available (source statement)'
    if re.search(r'\b(required|requires|must apply|needs to be applied)\b',t):return 'Required (source statement)'
    return 'Not stated / verify'


def maintenance_source(record:Mapping):
    """Preserve deep link (including fragment) over matrix landing URL."""
    links=record.get('links') or []
    for l in links:
        if isinstance(l,dict) and 'PTF' in str(l.get('type','')).upper() and l.get('url'):
            return str(l['url'])
    return str(record.get('source_url') or '')


def scraped_ptf_status(record:Mapping):
    links=[l for l in record.get('links',[]) if isinstance(l,dict) and 'PTF' in str(l.get('type','')).upper()]
    if not links:return 'No PTF reference on source'
    if not ptf_ids(record.get('ptfs')):return 'Link present — IDs not verified'
    text=' '.join(str(l.get('text') or '') for l in links)
    return maintenance_availability(text)


def match_key(vendor,product,version):
    """Exact normalized name + release; handles embedded trailing version only."""
    v=re.sub(r'[^a-z0-9]+','',str(vendor or '').casefold())
    name=str(product or '').strip()
    vrm=str(version or '').strip().lstrip('vV')
    if not vrm:
        m=re.search(r'\s+[vV]?(\d+(?:\.\d+){0,3})\s*$',name)
        if m:name=name[:m.start()].strip();vrm=m.group(1)
    name=re.sub(r'[^a-z0-9]+','',name.casefold())
    vrm=re.sub(r'[^a-z0-9]+','',vrm.casefold())
    return v,name,vrm


def installation_status(text):
    """Separate proven installation wording from *instructions* to install.

    An ordinary vendor instruction such as 'PTFs need to be installed' is never
    evidence that the customer's mainframe has already applied the maintenance.
    """
    t=re.sub(r'\s+',' ',str(text or '')).casefold()
    if re.search(r'\b(?:not|never|haven.t|hasn.t|isn.t|wasn.t)\s+(?:been\s+)?(?:installed|applied)\b|\b(?:missing ptfs?|ptfs? missing|not yet installed|not yet applied)\b',t):
        return 'Not installed (source-reported)'
    if re.search(r'\b(?:needs? to|must|should|required to|to be|will be|can be|please)\s+(?:be\s+)?(?:installed|applied)\b',t):
        return 'Unknown'
    if re.search(r'\b(?:already|successfully|currently|has been|have been|was|were)\s+(?:installed|applied)\b|\b(?:installed and verified|ptfs? installed)\b',t):
        return 'Installed/applied (source-reported)'
    return 'Unknown'


def per_ptf_statements(text):
    """PTF-level status from nearby source text; never asserts actual machine state."""
    t=re.sub(r'\s+',' ',str(text or ''))
    results=[]
    ids=ptf_ids(t)
    for ident in ids:
        spans=[m for m in re.finditer(r'\b'+re.escape(ident)+r'\b',t,re.I)]
        statements=[]
        for match in spans:
            before=t[max(0,match.start()-65):match.start()]
            after=t[match.end():min(len(t),match.end()+90)]
            snippet=(before+' '+ident+' '+after).strip()
            availability=maintenance_availability(snippet)
            installed=installation_status(snippet)
            # When the same sentence references multiple PTFs, do not pretend
            # the source assigns an individual status to only one of them.
            statements.append({'ptf_id':ident,'availability':availability,'installation':installed,
                               'source_excerpt':snippet[:180]})
        results.extend(statements)
    return results
