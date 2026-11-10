"""Consistent maintenance rendering: keep vendor evidence and workbook values distinct."""
from __future__ import annotations
import re
from typing import Mapping

PTF_ID = re.compile(r'\b(?:LU|RO|SO|UI|UK|UA|UQ|UJ|AQ|UO|UR)[0-9]{5,7}\b',re.I)

def ids(value):
    if isinstance(value,(list,tuple,set)):
        text=' '.join(map(str,value))
    else:
        text=str(value or '')
    return sorted(set(s.upper() for s in PTF_ID.findall(text)))

def link_present(record:Mapping):
    return bool(record.get('ptf_links_present')) or any('PTF' in str(link.get('type','')).upper() for link in (record.get('links') or []) if isinstance(link,dict))

def link_ids(record:Mapping):
    """Avoid mixing additional-information PTFs with a PTF requirement."""
    found=ids(record.get('ptfs'))
    for link in record.get('links') or []:
        if isinstance(link,dict) and 'PTF' in str(link.get('type','')).upper():
            found=sorted(set(found + ids(link.get('ptfs'))))
    return found

def display_ptfs(record:Mapping, baseline=''):
    """Never wipe an existing workbook maintenance assertion on a partial scrape."""
    found=link_ids(record)
    if found:
        return ', '.join(found), 'Live vendor evidence'
    if baseline and str(baseline).strip().casefold() not in ('', 'verify', 'none', 'nan'):
        return str(baseline), 'Existing workbook/CSV evidence (live IDs unavailable)'
    if link_present(record):
        return 'PTF link present — IDs not extracted; verify source', 'Partial vendor evidence'
    return str(baseline or 'Verify'), 'No extracted PTF ID'
