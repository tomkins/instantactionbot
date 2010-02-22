from pyxmpp import xmlextra


def clean_node(node):
    node.setNs(None)
    for i in xmlextra.xml_node_iter(node.children):
        clean_node(i)


def yes_or_no(value):
    if value is True:
        return 'yes'
    else:
        return 'no'
