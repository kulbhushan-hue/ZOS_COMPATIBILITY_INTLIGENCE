"""Read-only vendor extraction: Broadcom matrix + linked PTF / additional-information sections.

No authentication bypass, unrestricted URL fetching, JavaScript execution or recursive crawling.
The crawler processes links shown in compatibility table cells, including local anchors.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag

from bs4 import BeautifulSoup, Tag, NavigableString
from vendor_details import _allowed_url, _download, _plain_text

BROADCOM_URL = "https://ftpdocs.broadcom.com/WebInterface/phpdocs/0/MSPSaccount/COMPAT/zos_compat.HTML"
OS = ("3.2", "3.1", "2.5")
PTF = re.compile(r"\b(?:LU|SO|RO|UI|UK|UA|UQ|UJ|AQ|UO|UR)[0-9]{5,7}\b", re.I)
APAR = re.compile(r"\b(?:OA|PH|PI|PM|PK|PQ|IZ)[0-9]{5,7}\b", re.I)
FIXCAT = re.compile(r"(?:CA|IBM)\.TargetSystem-[\w./-]+", re.I)
FMID = re.compile(r"\b[A-Z][A-Z0-9]{6}\b")
USERMOD = re.compile(r"\bUSERMOD\s*[:=#-]?\s*([A-Z0-9-]{4,20})", re.I)
SYSMOD = re.compile(r"\bSYSMOD\s*[:=#-]?\s*([A-Z0-9-]{4,20})", re.I)
STATUS = {"YES":"Yes", "NO":"No", "IN PROGRESS":"In Progress", "N/A":"N/A", "NOT APPLICABLE":"N/A"}
MAX_LINKS = 220
MAX_DETAIL_CHARS = 4500


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def product_split(label: str) -> tuple[str, str]:
    label = re.sub(r"\s*\((?:End Of (?:Life|Service)|EOL|EOS)\)\s*", "", label, flags=re.I).strip()
    m = re.match(r"^(.*)\s+([vV]?\d+(?:\.\d+){0,3})$", label)
    return (m.group(1).strip(), m.group(2).lstrip("vV")) if m else (label, "")


def _version_header(t: str) -> str | None:
    s = clean(t).upper().replace(" ", "")
    m = re.search(r"V([235])R([125])", s)
    if m:
        found = f"{m.group(1)}.{m.group(2)}"
        return found if found in OS else None
    m = re.search(r"(?:Z/OS)([235])\.([125])", s)
    if m:
        found = f"{m.group(1)}.{m.group(2)}"
        return found if found in OS else None
    return None


def _anchor_context(soup: BeautifulSoup, href: str, page_url: str) -> tuple[str, str, str]:
    """Read the *whole* referenced detail, up to the next detail anchor.

    Broadcom's PTF anchors sometimes precede several nested HTML elements and
    FMID/PTF tables. Looking only at the anchor's parent row/cell (or stopping
    at any element with an id) misses these PTFs. Walk in document order, but
    stop at the next named detail anchor so PTFs cannot bleed between products.
    """
    full = urljoin(page_url, href)
    base, fragment = urldefrag(full)
    if not _allowed_url(base):
        return full, "", "Blocked external or non-HTTPS detail link"
    if base.rstrip('/').lower() != page_url.rstrip('/').lower():
        return full, "", "Separate approved vendor page; fetch during crawl"
    if not fragment:
        return full, "", "No fragment/detail identifier"
    # HTML anchor identifiers can be case-sensitive, so try exact first.
    target = soup.find(id=fragment) or soup.find(attrs={"name":fragment})
    if target is None:
        target = soup.find(lambda tag: isinstance(tag, Tag) and
                           (str(tag.get('id','')).casefold()==fragment.casefold() or
                            str(tag.get('name','')).casefold()==fragment.casefold()))
    if target is None:
        return full, "", "Anchor target not found in document"

    # Use text nodes (not parent.get_text) to retain the sequence beyond
    # parent/table boundaries. This handles anchors in empty spans or headers.
    collected=[]
    size=0
    for node in target.next_elements:
        if isinstance(node, Tag):
            if node.name in ('script', 'style', 'noscript'):
                continue
            # Stop at another section anchor. Do not stop at ordinary element
            # IDs used for styling, tables or navigation.
            identifier = node.get('name') or node.get('id') or ''
            if identifier and node is not target and (
                str(identifier).upper().startswith('IN0') or
                (node.name == 'a' and node.get('name'))
            ):
                break
        elif isinstance(node, NavigableString):
            if node.find_parent(['script','style','noscript']):
                continue
            value=clean(str(node))
            if value:
                collected.append(value)
                size+=len(value)+1
                if size >= MAX_DETAIL_CHARS:
                    break
    result=clean(' '.join(collected))[:MAX_DETAIL_CHARS]
    return full, result, ('Bounded anchor section' if result else 'Empty anchor section')

def _details(text: str, link_type: str, url: str, source: str) -> dict:
    return {"type":link_type, "url":url, "text":text[:MAX_DETAIL_CHARS],
            "ptfs":sorted(set(PTF.findall(text))), "apars":sorted(set(APAR.findall(text))),
            "fixcats":sorted(set(FIXCAT.findall(text))),
            "usermods":sorted(set(USERMOD.findall(text))), "sysmods":sorted(set(SYSMOD.findall(text))),
            "fmids":sorted(set(FMID.findall(text)))[:50], "extraction_status":source}


def parse_broadcom_html(html: bytes | str, page_url: str = BROADCOM_URL) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    matrix = None
    headers: dict[int,str] = {}
    for table in soup.find_all("table"):
        rows=table.find_all("tr")
        for r in rows[:5]:
            cells=r.find_all(["th","td"],recursive=False)
            h={i:_version_header(c.get_text(" ",strip=True)) for i,c in enumerate(cells)}
            h={i:v for i,v in h.items() if v}
            if len(h)>=2:
                matrix=table;headers=h;break
        if matrix: break
    if matrix is None: raise ValueError("Could not locate a Broadcom z/OS release compatibility table")
    extracted=[]
    for tr in matrix.find_all("tr"):
        cells=tr.find_all(["td","th"],recursive=False)
        if not cells or len(cells)<=max(headers): continue
        first=clean(cells[0].get_text(" ",strip=True))
        if not first or first.lower().startswith("product"):continue
        name,vrm=product_split(first)
        if not name:continue
        for column,os_version in headers.items():
            cell=cells[column]
            # Text may include PTF and Additional Information but status is the first token.
            cell_txt=clean(cell.get_text(" ",strip=True))
            m=re.match(r"^(IN PROGRESS|NOT APPLICABLE|YES|NO|N/A)\b",cell_txt,re.I)
            status=STATUS.get(m.group(1).upper(),"Unverified") if m else "Unverified"
            links=[]
            for a in cell.find_all("a",href=True):
                kind=clean(a.get_text(" ",strip=True))
                if not re.search(r"PTF|Additional Information|Prerequisite|APAR|USERMOD|SYSMOD",kind,re.I):continue
                full,text,method=_anchor_context(soup,a["href"],page_url)
                links.append(_details(text,kind,full,method))
            ptfs=sorted({p for link in links if re.search(r"PTF",link["type"],re.I) for p in link["ptfs"]})
            extracted.append({"vendor":"Broadcom","product":name,"vrm":vrm,"display_name":first,
                "zos_version":os_version,"status":status,"ptf_links_present":any("PTF" in x["type"].upper() for x in links),
                "ptfs":ptfs,"links":links,"source_url":page_url,
                "source_kind":"vendor_live","evidence_status":"Partial" if any(not x["text"] for x in links) else "Extracted"})
    if len(extracted)<3:raise ValueError("Matrix parser found too few rows; verify source layout")
    return extracted


def _fetch_link(link: dict, page_url: str) -> dict:
    # External vendor detail links are fetched only within approved vendor hosts.
    if link["extraction_status"]!="Separate approved vendor page; fetch during crawl":return link
    base,_=urldefrag(link["url"])
    if not _allowed_url(base):return link
    payload,ctype,status=_download(base)
    if status!="Fetched":return {**link,"extraction_status":status}
    text,parsed=_plain_text(payload,ctype,base)
    return _details(text,link["type"],link["url"],parsed)


def crawl_broadcom(page_url: str = BROADCOM_URL, follow_external: bool=True) -> tuple[list[dict],dict]:
    if not _allowed_url(page_url):raise ValueError("Vendor URL not allowlisted")
    payload,ctype,status=_download(page_url)
    if status!="Fetched":raise RuntimeError(status)
    if not ("html" in ctype or payload.lstrip().startswith(b"<")):
        raise RuntimeError("Vendor source did not return HTML")
    records=parse_broadcom_html(payload,page_url)
    fetched={}
    link_attempts=0
    if follow_external:
        for record in records:
            for link in record["links"]:
                base,_=urldefrag(link["url"])
                if link["extraction_status"]!="Separate approved vendor page; fetch during crawl":continue
                if base not in fetched and link_attempts<MAX_LINKS:
                    fetched[base]=_fetch_link(link,page_url);link_attempts+=1
                if base in fetched:
                    r=fetched[base]
                    record_link={**r,"type":link["type"],"url":link["url"]}
                    record["links"][record["links"].index(link)]=record_link
    for record in records:
        record["ptfs"]=sorted({p for link in record["links"] if "PTF" in link["type"].upper() for p in link["ptfs"]})
        record["evidence_status"]="Partial" if any(not l["text"] for l in record["links"]) else "Extracted"
    metrics={"source_url":page_url,"html_bytes":len(payload),"records":len(records),"products":len({(r['product'],r['vrm']) for r in records}),"links":sum(len(r['links']) for r in records),"external_pages_fetched":link_attempts,"timestamp":datetime.now(timezone.utc).isoformat(),"sha256":hashlib.sha256(payload).hexdigest()}
    return records,metrics
