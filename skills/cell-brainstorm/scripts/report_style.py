"""Narrow structural/style guards for the memo. Not an academic writing judge."""
from __future__ import annotations
import re
from typing import Any

FORBIDDEN = ('创新亮点','推荐指数','顶刊潜力','保底发文','全球首创','颠覆性突破','填补国际空白',
             '值得押注','创新等级','判断置信度','最终赢家','五星推荐')

def check_sections(sections: dict[str,Any], allowed_ids: set[str], nearest_ids: set[str]) -> None:
    if set(sections) != {'basis','question','plan','limitations'}:
        raise ValueError('Memo requires basis, question, plan and limitations.')
    for name, section in sections.items():
        body = section['text']
        if not body.strip():
            raise ValueError('Empty memo paragraph: ' + name)
        if '\n' in body or re.search(r'(^|\s)(#{1,6}|[|]|```)', body):
            raise ValueError('Memo fields must contain single paragraphs, not tables or headings.')
        bad = [term for term in FORBIDDEN if term in body]
        if bad:
            raise ValueError('Rewrite promotional/audit phrasing in memo: ' + ', '.join(bad))
        if not set(section['source_ids']).issubset(allowed_ids):
            raise ValueError('Memo introduced a source not in the candidate audit.')
    if nearest_ids and not (set(sections['basis']['source_ids']) & nearest_ids):
        raise ValueError('Research basis must cite an audited closest-work source.')
