from lxml import etree
from typing import Dict, List, Optional


class EnumType:
    def __init__(self, name: str, values: Dict[str, str]):
        self.name = name
        self.values = values


class Attribute:
    def __init__(
        self, name: str, attr_type: str, length: Optional[int], required: bool
    ):
        self.name = name
        self.type = attr_type
        self.length = length
        self.required = required


class MessageFormat:
    def __init__(
        self, name: str, attributes: List[Attribute], id: Optional[str] = None
    ):
        self.name = name
        self.attributes = attributes
        self.id = id


class XMLSchema:
    def __init__(
        self,
        enum_types: List[EnumType],
        data_types: List[MessageFormat],
        message_formats: List[MessageFormat],
    ):
        self.enum_types = enum_types
        self.data_types = data_types
        self.message_formats = message_formats

    def __repr__(self):
        s = "XMLSchema:\n"

        s += "\tenum types:\n"
        for enum_type in self.enum_types:
            s += f"\t\t{enum_type.name=}, {enum_type.values=}\n"

        s += "\n\tdata types:\n"
        for data_type in self.data_types:
            s += f"\t\t{data_type.name=}:\n"
            for attrib in data_type.attributes:
                s += f"\t\t\t{attrib.name=}, {attrib.type=}, {attrib.length=}, {attrib.required=}\n"

        s += "\n\tmessage formats:\n"
        for message_format in self.message_formats:
            s += f"\n\t\t{message_format.name=}, {message_format.id=}:\n"
            for attrib in message_format.attributes:
                s += f"\t\t\t{attrib.name=}, {attrib.type=}, {attrib.length=}, {attrib.required=}\n"

        return s

    @staticmethod
    def parse(xml_file: str) -> "XMLSchema":
        tree = etree.parse(xml_file)
        root = tree.getroot()

        enum_types = [
            EnumType(
                enumType.get("name"),
                {
                    ev.get("name"): ev.get("value")
                    for ev in enumType.findall("enumValue")
                },
            )
            for enumType in root.xpath(".//enumType")
        ]

        def parse_formats(parent):
            return [
                MessageFormat(
                    format_tag.get("name"),
                    [
                        Attribute(
                            attr.get("name"),
                            attr.get("type"),
                            int(attr.get("length")) if attr.get("length") else None,
                            attr.get("required") == "true",
                        )
                        for attr in format_tag.findall("attribute")
                    ],
                    format_tag.get("id"),
                )
                for format_tag in parent
            ]

        data_types = parse_formats(root.find("./dataTypes"))
        message_formats = parse_formats(root.find("./messageFormats"))

        return XMLSchema(enum_types, data_types, message_formats)


# Usage
xml_schema = XMLSchema.parse("example.xml")
print(xml_schema)
