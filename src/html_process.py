"""
this function process html into telegram defined markup language
"""
from typing import List
from xml.dom.minidom import parseString
from xml.dom import Node


def walk(node: Node, result: List[str]):
    if node.nodeType == Node.DOCUMENT_NODE:
        walk(node.documentElement, result)
    if node.nodeType == Node.ELEMENT_NODE:
        if node.tagName == 'p':
            if len(result) == 0 or len(result) > 0 and len(result[-1]) > 0 and result[-1][-1] != '\n':
                result.append('\n')
            walkChildren(node, result)
            result.append('\n')
        elif node.tagName in ['b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del']:
            # https://core.telegram.org/bots/update56kabdkb12ibuisabdubodbasbdaosd
            result.append(f'<{node.tagName}>')
            walkChildren(node, result)
            result.append(f'</{node.tagName}>')
        else:
            walkChildren(node, result)
    elif node.nodeType == Node.TEXT_NODE:
        result.append(node.data)


def walkChildren(node: Node, result: List[str]):
    for child in node.childNodes:
        walk(child, result)


def transform(s: str) -> str:
    node = parseString("<root>" + s + "</root>")
    result = []
    walk(node, result)
    return "".join(result).strip() + '\n'
