import xml.etree.ElementTree as ET
import shutil
import json
import sys
import os


HEADER_AND_UTIL_CODE = r"""use arrayref::array_ref;
use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;

pub fn string_to_char_array<const N: usize>(s: &str) -> Result<[char; N], &'static str> {
    if s.len() > N {
        return Err("String is too long");
    }

    let mut char_vec: Vec<char> = s.chars().collect();
    while char_vec.len() < N {
        char_vec.push(' '); // Fill the remaining spaces with a default character
    }

    // Attempt to convert Vec<char> into [char; N]
    let char_array: [char; N] = char_vec
        .try_into()
        .map_err(|_| "Failed to convert to array")?;
    Ok(char_array)
}

#[derive(Debug, PartialEq)]
pub struct Header {
    pub msg_size: u32,
    pub msg_type: u8,
    pub bitmask: u32,
}

impl Header {
    pub fn to_bytes(&self) -> [u8; 9] {
        let size_bytes = self.msg_size.to_be_bytes();
        let mask_bytes = self.bitmask.to_be_bytes();

        [
            size_bytes[0],
            size_bytes[1],
            size_bytes[2],
            size_bytes[3],
            self.msg_type,
            mask_bytes[0],
            mask_bytes[1],
            mask_bytes[2],
            mask_bytes[3],
        ]
    }

    pub fn from_bytes(buffer: &[u8; 9]) -> Self {
        let msg_size = u32::from_be_bytes([buffer[0], buffer[1], buffer[2], buffer[3]]);
        let msg_type = buffer[4];
        let bitmask = u32::from_be_bytes([buffer[5], buffer[6], buffer[7], buffer[8]]);

        Self {
            msg_size,
            msg_type,
            bitmask,
        }
    }
}

#[pyclass]
struct PyMessage {
    message: Message,
}

#[pymodule]
fn xparse(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<PyMessage>()?;
    Ok(())
}
"""


def get_test_value(rust_type: str, enum_schema) -> str:
    if rust_type[0] == "i":
        return "-123"
    elif rust_type[0] == "u":
        return "123"
    elif rust_type == "bool":
        return "true"
    elif rust_type.startswith("[char;"):
        return f"""string_to_char_array("John Doe").unwrap()"""
    elif rust_type.startswith("Option"):
        inner_type = rust_type[rust_type.index("<") + 1 : -1]
        return f"""Some({get_test_value(inner_type, enum_schema)})"""
    elif rust_type[0] == "f":
        return "3.14"
    elif rust_type.lower() in enum_schema:
        variant = list(enum_schema[rust_type.lower()].keys())[0].capitalize()
        return f"{rust_type}::{variant}"
    else:
        raise Exception(f"Unknown Rust type for get_test_value: {rust_type}")


def get_test_python_value(rust_type: str, enum_schema):
    if rust_type[0] == "i":
        return -123
    elif rust_type[0] == "u":
        return 123
    elif rust_type[0] == "f":
        return 3.14
    elif rust_type == "bool":
        return (True,)
    elif rust_type.startswith("[char;"):
        return f"""'John Doe'"""
    elif rust_type.lower() in enum_schema:
        return 1
    elif rust_type.startswith("Option"):
        inner_rust_type = rust_type[rust_type.index("<") + 1 : -1]
        return get_test_python_value(inner_rust_type, enum_schema)
    else:
        raise Exception(f"Unknown Rust type for get_test_python_value: {rust_type}")


def parse_xml_schema(xml_file: str):
    tree = ET.parse(xml_file)
    root = tree.getroot()

    # Parsing enumTypes
    enum_types = {}
    for enumType in root.findall("./enumTypes/enumType"):
        enum_name = enumType.get("name")
        enum_values = {
            ev.get("name"): ev.get("value") for ev in enumType.findall("enumValue")
        }
        enum_types[enum_name] = enum_values

    # Parsing messageFormats
    message_formats = []
    for message_format in root.findall("./messageFormats/messageFormat"):
        format_details = {
            "id": message_format.get("id"),
            "name": message_format.get("name"),
            "attributes": [],
        }

        for attribute in message_format.findall("attribute"):
            attr_details = {
                "name": attribute.get("name"),
                "type": attribute.get("type"),
                "length": attribute.get("length"),
                "required": attribute.get("required") == "true",
            }
            format_details["attributes"].append(attr_details)

        message_formats.append(format_details)

    return enum_types, message_formats


def get_rust_type(attribute) -> str:
    if attribute.get("length") is None:
        length = 1
    else:
        length = int(attribute.get("length"))

    base_type, optional = (
        attribute["type"],
        not attribute["required"],
    )
    inner_type = ""
    if base_type == "int":
        inner_type = f"i{length * 8}"
    elif base_type == "uint":
        inner_type = f"u{length * 8}"
    elif base_type == "float":
        inner_type = f"f{length * 8}"
    elif base_type == "bool":
        inner_type = "bool"
    elif base_type == "str":
        inner_type = f"[char; {length}]"
    else:  # assume Enum here
        inner_type = base_type.capitalize()
    if optional:
        return f"Option<{inner_type}>"
    else:
        return inner_type


def generate_rust_code_for_schema(schema) -> str:
    code = HEADER_AND_UTIL_CODE

    def get_rust_num_bytes(rust_type: str) -> int:
        if rust_type[0] in ("i", "u", "f"):
            num_bits = int(rust_type[1:])
            return int(num_bits / 8)
        elif rust_type.startswith("[char"):
            # technically char is 4 bytes but we are presupposing ASCII so its only 1
            return int(rust_type[rust_type.index(";") + 1 : -1])
        elif rust_type == "bool":
            return 1
        elif rust_type.startswith("Option<"):
            return get_rust_num_bytes(rust_type[rust_type.index("<") + 1 : -1])
        else:  # assume enum
            return 1

    def get_serialization_code(
        att, rust_type: str, enum_schema, omit_self=False
    ) -> str:
        code = ""
        if rust_type.startswith("Option<"):
            inner_type = rust_type[rust_type.index("<") + 1 : -1]
            # [:-1] at end to exclude semicolon inside match arm
            if inner_type.lower() in enum_schema:
                extra = "&"
            else:
                extra = ""
            return f"""\t\tmatch {extra}self.{att} {{\n\t\t\tSome({att}) => {get_serialization_code(att, inner_type, enum_schema, omit_self=True)[:-1]},\n\t\t\t_ => {{}}\n\t\t}}"""
        else:
            if not omit_self:
                self_string = "self."
                tab_string = "\t\t"
            else:
                self_string = ""
                tab_string = ""

            if rust_type[0] in ("i", "u", "f"):
                return f"""{tab_string}buf.extend_from_slice(&{self_string}{att}.to_be_bytes());"""
            elif rust_type == "bool":
                return f"""{tab_string}buf.push(if {self_string}{att} {{ 1 }} else {{ 0 }});"""
            elif rust_type.startswith("[char;"):
                return f"""{tab_string}buf.append({self_string}{att}.iter().map(|&c| c as u8).collect::<Vec<u8>>().as_mut());"""
            else:  # assume Enum variant
                return f"""{tab_string}buf.push({self_string}{att}.to_u8());"""

    def get_bitmask_code(attribute_rust_types) -> str:
        code = "\t\tlet mut mask: u32 = 0;\n\n"
        cnt = 0
        for att_name, rust_type in attribute_rust_types:
            if rust_type.startswith("Option<"):
                code += f"""\t\tmatch self.{att_name} {{\n\t\t\tSome(_) => mask |= 1 << {cnt},\n\t\t\t_ => {{}}\n\t\t}}\n\n"""
                cnt += 1

        code += f"""\t\tmask\n\t}}"""
        return code

    def get_deserialization_code(attribute_rust_types) -> str:
        code = f"""\tfn deserialize(buffer: &[u8]) -> Result<Self, &'static str> {{\n"""
        code += f"""\t\tif buffer.len() < 9 {{\n\t\t\treturn Err("Buffer too short for header");\n\t\t}}\n\n"""

        code += f"""\t\tlet header = Header::from_bytes(array_ref![buffer, 0, 9]);\n"""
        code += f"""\t\tlet mut offset = 9;\n\n"""

        ok_code = f"""\t\tOk(Self {{\n"""

        opt_cnt = 0

        for i, pair in enumerate(attribute_rust_types):
            att_name, rust_type = pair
            ok_code += f"""\t\t\t{att_name},\n"""

            skip_offset = i == len(attribute_rust_types) - 1

            if rust_type.startswith("Option"):
                inner_rust_type = rust_type[rust_type.index("<") + 1 : -1]
                n = get_rust_num_bytes(inner_rust_type)

                code += f"""\t\tlet {att_name} = if header.bitmask & (1 << {opt_cnt}) != 0 {{\n"""
                opt_cnt += 1

                if inner_rust_type.startswith("[char;"):
                    code += f"""\t\t\tlet mut {att_name}_chars = [' '; {n}];\n"""
                    code += f"""\t\t\tfor i in 0..{n} {{\n"""
                    code += f"""\t\t\t\t{att_name}_chars[i] = buffer[offset + i] as char;\n"""
                    code += f"""\t\t\t}}\n"""

                    if not skip_offset:
                        code += f"""\t\t\toffset += {n};\n"""
                    code += f"""\t\t\tSome({att_name}_chars)\n"""

                elif inner_rust_type[0] in ("i", "u", "f"):
                    code += f"""\t\t\tlet {att_name}_value = {inner_rust_type}::from_be_bytes(buffer[offset..offset + {n}].try_into().map_err(|_| "Invalid buffer: {att_name}")?);\n"""

                    if not skip_offset:
                        code += f"""\t\t\toffset += {n};\n"""
                    code += f"""\t\t\tSome({att_name}_value)\n"""

                elif inner_rust_type[0] == "bool":
                    code += f"""\t\t\tlet {att_name}_value = buffer[offset] != 0;"""

                    if not skip_offset:
                        code += f"""\t\t\toffset += {n};\n"""
                    code += f"""\t\t\tSome({att_name}_value)\n"""

                else:  # assume Enum
                    code += f"""\t\t\tlet {att_name}_value = {inner_rust_type}::from_u8(buffer[offset]).map_err(|_| "Invalid buffer: {att_name}")?;\n"""
                    if not skip_offset:
                        code += f"""\t\t\toffset += 1;\n"""
                    code += f"""\t\t\tSome({att_name}_value)\n"""

                code += f"""\t\t}} else {{\n\t\t\tNone\n\t\t}};\n\n"""

            else:
                n = get_rust_num_bytes(rust_type)

                if rust_type.startswith("[char;"):
                    code += f"""\t\tlet mut {att_name} = [' '; {n}];\n"""
                    code += f"""\t\tfor i in 0..{n} {{\n"""
                    code += f"""\t\t\t{att_name}[i] = buffer[offset + i] as char;\n"""
                    code += f"""\t\t}}\n"""

                elif rust_type[0] in ("i", "u", "f"):
                    code += f"""\t\t let {att_name} = {rust_type}::from_be_bytes(buffer[offset..offset + {n}].try_into().map_err(|_| "Invalid buffer: {att_name}")?);\n"""

                elif rust_type == "bool":
                    code += f"""\t\tlet {att_name} = buffer[offset] != 0;\n"""

                else:  # assume Enum
                    code += f"""\t\tlet {att_name} = {rust_type}::from_u8(buffer[offset]).map_err(|_| "Invalid buffer: {att_name}")?;"""

                if not skip_offset:
                    code += f"""\t\toffset += {n};\n\n"""

        ok_code += f"""\t\t}})\n"""

        code += ok_code

        code += f"""\t}}"""
        return code

    enums_schema = schema[0]
    message_formats_schema = schema[1]

    # Generate code for Enum definitions and implementations
    for enum_name in enums_schema:
        code += f"""#[derive(PartialEq, Debug)]\n"""
        code += f"""pub enum {enum_name.capitalize()} {{\n"""

        for variant_name, variant_value in enums_schema[enum_name].items():
            code += f"""\t{variant_name.capitalize()} = {int(variant_value)},\n"""

        code += f"""}}\n\n"""

        code += f"""impl {enum_name.capitalize()} {{\n"""

        code += f"""\tpub fn from_u8(value: u8) -> Result<Self, &'static str> {{\n"""
        code += f"""\t\tmatch value {{\n"""
        for variant_name, variant_value in enums_schema[enum_name].items():
            code += f"""\t\t\t{int(variant_value)} => Ok({enum_name.capitalize()}::{variant_name.capitalize()}),\n"""
        code += (
            f"""\t\t\t_ => Err("Invalid value for enum {enum_name.capitalize()}"),\n"""
        )
        code += f"""\t\t}}\n"""
        code += f"""\t}}\n\n"""

        code += f"""\tpub fn to_u8(&self) -> u8 {{\n"""
        code += f"""\t\tmatch self {{\n"""
        for variant_name, variant_value in enums_schema[enum_name].items():
            code += f"""\t\t\t{enum_name.capitalize()}::{variant_name.capitalize()} => {int(variant_value)},\n"""
        code += f"""\t\t}}\n"""
        code += f"""\t}}\n\n"""

        code += f"""}}\n\n"""

    for message_format in message_formats_schema:
        code += f"""#[derive(PartialEq, Debug)]\npub struct {message_format['name'].capitalize()} {{\n"""
        attribute_rust_types = []
        for attribute in message_format["attributes"]:
            attribute_rust_types.append([attribute["name"], get_rust_type(attribute)])

        for attribute, rust_type in attribute_rust_types:
            code += f"    pub {attribute}: {rust_type},\n"
        code += "}\n\n"

        name = message_format["name"].capitalize()

        # begin impl
        code += f"""impl {name} {{\n"""

        # begin max_payload_size
        code += """    fn max_payload_size() -> usize {\n"""
        total_payload_size = 0
        for _, rt in attribute_rust_types:
            total_payload_size += get_rust_num_bytes(rt)
        code += f"\t\t{total_payload_size}"
        # end max_payload_size
        code += "\n    }\n\n"

        # begin serialize
        code += f"""\tfn serialize(&self) -> Vec<u8> {{\n"""
        code += f"""\t\tlet mut buf: Vec<u8> = Vec::with_capacity({name}::max_payload_size());\n\n"""

        for att, rust_type in attribute_rust_types:
            code += f"{get_serialization_code(att, rust_type, enums_schema)}\n\n"

        # end serialize
        code += """\n\t\tbuf\n\t}\n\n"""

        # get_bitmask
        code += f"""\tfn get_bitmask(&self) -> u32 {{\n"""
        code += f"""{get_bitmask_code(attribute_rust_types)}\n\n"""

        # deserialize
        code += f"""{get_deserialization_code(attribute_rust_types)}\n\n"""

        # get_example
        code += f"""\tpub fn get_example() -> Self {{\n"""
        code += f"""\t\tSelf {{\n"""
        for attrib in message_format["attributes"]:
            code += f"""\t\t\t{attrib['name']}: {get_test_value(get_rust_type(attrib), enums_schema)},\n"""
        code += f"""\t\t}}\n"""
        code += f"""\t}}\n"""

        # end struct impl
        code += "}\n\n"

    code += f"""#[derive(PartialEq, Debug)]\npub enum Message {{\n"""
    for message_format in message_formats_schema:
        name = message_format["name"].capitalize()
        code += f"    {name}({name}),\n"
    code += "}\n\n"

    # begin Message impl
    code += f"""impl Message {{\n"""

    # begin Message::serialize
    code += f"""\tpub fn serialize(&self) -> Vec<u8> {{\n"""
    code += f"""\t\tlet mut buffer = match self {{\n"""
    for message_format in message_formats_schema:
        code += f"""\t\t\tMessage::{message_format['name'].capitalize()}(p) => p.serialize(),\n"""
    code += f"""\t\t}};\n\n"""

    code += f"""\t\t// Create a buffer and prepend it to the buffer\n"""
    code += f"""\t\tlet header = Header {{\n"""
    code += f"""\t\t\tmsg_size: buffer.len() as u32 + 9, // +9 for header size\n"""
    code += f"""\t\t\tmsg_type: match self {{\n"""
    for i, message_format in enumerate(message_formats_schema):
        code += (
            f"""\t\t\t\tMessage::{message_format['name'].capitalize()}(_) => {i+1},\n"""
        )
    code += f"""\t\t\t}},\n"""
    code += f"""\t\t\tbitmask: self.get_bitmask(),\n"""
    code += f"""\t\t}};\n\n"""

    code += f"""\t\tlet mut header_bytes = header.to_bytes().to_vec();\n"""
    code += f"""\t\theader_bytes.append(&mut buffer);\n"""
    code += f"""\t\theader_bytes\n"""

    # end Message::serialize
    code += f"""\t}}\n\n"""

    # Message::get_bitmask
    code += f"""\tfn get_bitmask(&self) -> u32 {{\n"""
    code += f"""\t\tmatch self {{\n"""
    for message_format in message_formats_schema:
        code += f"""\t\t\tMessage::{message_format['name'].capitalize()}(p) => p.get_bitmask(),\n"""
    code += f"""\t\t}}\n"""
    code += f"""\t}}\n\n"""

    # begin Message::deserialize
    code += (
        f"""\tpub fn deserialize(buffer: &[u8]) -> Result<Self, &'static str> {{\n"""
    )
    code += f"""\t\tmatch buffer[4] {{\n"""
    for i, message_format in enumerate(message_formats_schema):
        name = message_format["name"]
        code += (
            f"""\t\t\t{i+1} => match {name.capitalize()}::deserialize(buffer) {{\n"""
        )
        code += f"""\t\t\t\tOk({name}) => Ok(Message::{name.capitalize()}({name})),\n"""
        code += f"""\t\t\t\tErr(e) => Err(e),\n"""
        code += f"""\t\t\t}},\n"""
    code += f"""\t\t\t_ => Err("Unknown message type id"),\n"""
    code += f"""\t\t}}\n"""
    # end Message::deserialize
    code += f"""\t}}\n\n"""

    # end Message impl
    code += f"""}}"""

    # begin PyMessage impl
    code += r"""#[pymethods]
impl PyMessage {
    fn to_bytes(&self) -> Vec<u8> {
        self.message.serialize()
    }

    #[staticmethod]
    fn from_bytes(buffer: Vec<u8>) -> PyResult<PyMessage> {
        match Message::deserialize(&buffer) {
            Ok(message) => Ok(PyMessage { message }),
            Err(e) => Err(PyValueError::new_err(e.to_string())),
        }
    }

    fn __repr__(&self) -> String {
        format!("{:?}", self.message)
    }

    fn __str__(&self) -> String {
        self.__repr__()
    }

    fn __eq__(&self, other: PyRef<PyMessage>) -> PyResult<bool> {
        Ok(self.message == other.message)
    }

"""
    # message format specific constructors
    for message_format in message_formats_schema:
        name = message_format["name"]
        code += f"""\t#[staticmethod]\n"""
        code += f"""\tfn {name}(\n"""

        # get attribute rust types again for constructor
        attribute_rust_types = []
        for attribute in message_format["attributes"]:
            attribute_rust_types.append([attribute["name"], get_rust_type(attribute)])

        # first pass - required attributes in args
        for att_name, rust_type in attribute_rust_types:
            if not "Option" in rust_type:
                if rust_type.lower() in enums_schema:
                    mapped_rust_type = "u8"
                elif "[char;" in rust_type:
                    mapped_rust_type = "String"
                else:
                    mapped_rust_type = rust_type

                code += f"""\t\t{att_name}: {mapped_rust_type},\n"""

        # second pass - optional attributes in args
        for att_name, rust_type in attribute_rust_types:
            if "Option" in rust_type:
                inner_rust_type = rust_type[rust_type.index("<") + 1 : -1]
                if inner_rust_type.lower() in enums_schema:
                    mapped_inner_rust_type = "u8"
                elif "[char;" in inner_rust_type:
                    mapped_inner_rust_type = "String"
                else:
                    mapped_inner_rust_type = inner_rust_type
                mapped_rust_type = f"Option<{mapped_inner_rust_type}>"
                code += f"""\t\t{att_name}: {mapped_rust_type},\n"""

        code += f"""\t) -> PyResult<PyMessage> {{\n"""

        # now iterate over attributes for the body, generating special code for handling strings and enums
        arg_listings = ""
        for att_name, rust_type in attribute_rust_types:
            if rust_type.startswith("Option"):
                inner_rust_type = rust_type[rust_type.index("<") + 1 : -1]
                if (
                    inner_rust_type[0] not in ("i", "u", "f")
                    and inner_rust_type != "bool"
                ):
                    # handle Opt<String> -> Opt<[char; _]>
                    if inner_rust_type.startswith("[char;"):
                        # map string to char array and wrap it on an opt
                        code += f"""\t\tlet {att_name}_array = {att_name}.map(|s| string_to_char_array(&s)).transpose().map_err(|_| PyValueError::new_err("Error converting {att_name} string to char array"))?;\n\n"""
                        arg_listings += f"""\t\t\t\t{att_name}: {att_name}_array,\n"""

                    # handle Opt<u8> -> Opt<Enum>
                    elif inner_rust_type.lower() in enums_schema:
                        code += f"""\t\tlet {att_name}_enum = match {att_name} {{\n"""
                        code += f"""\t\t\tSome(value) => match value {{\n"""
                        for k, v in enums_schema[inner_rust_type.lower()].items():
                            code += f"""\t\t\t\t{int(v)} => Some({inner_rust_type}::{k.capitalize()}),\n"""
                        code += f"""\t\t\t\t_ => return Err(PyValueError::new_err("Invalid enum value for {att_name}")),\n"""
                        code += f"""\t\t\t}},\n"""
                        code += f"""\t\t\tNone => None,\n"""
                        code += f"""\t\t}};\n\n"""
                        arg_listings += f"""\t\t\t\t{att_name}: {att_name}_enum,\n"""

                    # rage, rage against the dying of the light
                    else:
                        raise Exception(
                            f"Unknown Rust type inside Option: {inner_rust_type}"
                        )
                else:
                    # numbers are so easy, we could all take a page from their book
                    arg_listings += f"""\t\t\t\t{att_name},\n"""

            else:
                if rust_type[0] not in ("i", "u", "f") and rust_type != "bool":
                    # handle String -> [char; _];
                    if rust_type.startswith("[char;"):
                        code += f"""\t\tlet {att_name}_array = string_to_char_array(&{att_name}).map_err(|_| PyValueError::new_err("Error convering {att_name} string to char array"))?;\n\n"""
                        arg_listings += f"""\t\t\t\t{att_name}: {att_name}_array,\n"""

                    # handle u8 -> Enum
                    elif rust_type.lower() in enums_schema:
                        code += f"""\t\tlet {att_name}_enum = match {att_name} {{\n"""
                        for k, v in enums_schema[rust_type.lower()].items():
                            code += f"""\t\t\t{int(v)} => {rust_type}::{k.capitalize()},\n"""
                        code += f"""\t\t\t_ => return Err(PyValueError::new_err("Invalid enum value for {att_name}")),\n"""
                        code += f"""\t\t}};\n\n"""
                        arg_listings += f"""\t\t\t\t{att_name}: {att_name}_enum,\n"""

                    else:
                        raise Exception(f"Unknown Rust type: {rust_type}")
                else:
                    arg_listings += f"""\t\t\t\t{att_name},\n"""

        code += f"""\t\tOk(PyMessage {{\n"""
        code += (
            f"""\t\t\tmessage: Message::{name.capitalize()}({name.capitalize()} {{\n"""
        )
        code += arg_listings
        code += f"""\t\t\t}}),\n"""
        code += f"""\t\t}})\n"""
        code += f"""\t}}\n\n"""

    # end PyMessage impl
    code += f"""}}\n\n"""

    # begin tests
    code += r"""#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_header_serialization() {
        let header = Header {
            msg_size: 23,
            msg_type: 1,
            bitmask: 33, // Example bitmask (1 << 0 | 1 << 5)
        };

        let serialized = header.to_bytes();
        let deserialized = Header::from_bytes(&serialized);

        assert_eq!(header, deserialized);
    }

    #[test]
    fn test_header_fields() {
        let header = Header {
            msg_size: 100,
            msg_type: 2,
            bitmask: 18, // Example bitmask (1 << 1 | 1 << 4)
        };

        assert_eq!(header.msg_size, 100);
        assert_eq!(header.msg_type, 2);
        assert_eq!(header.bitmask, 18);
    }

"""
    for message_format in message_formats_schema:
        code += f"""\t#[test]\n"""
        name = message_format["name"]
        code += f"""\tfn test_{name}_serialize_deserialize() {{\n"""

        code += f"""\t\tlet message_original = Message::{name.capitalize()}({name.capitalize()}::get_example());\n\n"""

        code += f"""\t\tlet message_bytes = message_original.serialize();\n"""
        code += f"""\t\tlet message_result = Message::deserialize(&message_bytes).unwrap();\n\n"""
        code += f"""\t\t assert_eq!(message_original, message_result);\n"""

        code += f"""\t}}\n\n"""

    code += f"""}}\n"""

    return code


def generate_rust_code_main_for_schema(schema, schema_name) -> str:
    code = f"""use std::io::Write;\n"""
    code += f"""use xparse::{{Message"""
    message_formats_schema = schema[1]

    for message_format in message_formats_schema:
        code += f""", {message_format['name'].capitalize()}"""
    code += f"""}};\n\n"""

    code += f"""fn main() {{\n"""
    for message_format in message_formats_schema:
        name = message_format["name"]
        code += f"""\tlet {name} = Message::{name.capitalize()}({name.capitalize()}::get_example());\n\n"""
        code += f"""\tlet mut file = std::fs::File::create("{schema_name}_{name}.xb").unwrap();\n"""
        code += f"""\tfile.write_all(&{name}.serialize()).unwrap();\n\n"""

    code += f"""}}"""
    return code


def generate_python_tests_for_schema(schema, schema_name) -> str:
    code = f"""from xparse import PyMessage\n\n\n"""
    message_formats_schema = schema[1]
    enums_schema = schema[0]
    for message_format in message_formats_schema:
        name = message_format["name"]
        code += f"""def test_{name}_deserialize_serialize():\n"""
        code += f"""\tmessage_bytes = open("{schema_name}_{name}.xb", "rb").read()\n"""
        code += f"""\tmessage = PyMessage.from_bytes(message_bytes)\n"""
        code += f"""\tmessage_bytes_out = message.to_bytes()\n\n"""
        code += f"""\tfor x, y in zip(message_bytes, message_bytes_out):\n"""
        code += f"""\t\tassert x == y\n\n\n"""

        attribute_rust_types = []
        for attribute in message_format["attributes"]:
            attribute_rust_types.append([attribute["name"], get_rust_type(attribute)])

        code += f"""def test_{name}_serialize_deserialize():\n"""
        code += f"""\t{name} = PyMessage.{name}(\n"""
        for att_name, rust_type in attribute_rust_types:
            code += f"""\t\t{att_name}={get_test_python_value(rust_type, enums_schema)},\n"""
        code += f"""\t)\n"""
        code += f"""\t{name}_bytes = {name}.to_bytes()\n"""
        code += f"""\t{name}_result = PyMessage.from_bytes({name}_bytes)\n\n"""
        code += f"""\tassert {name} == {name}_result\n\n\n"""

    return code


def wipe_dir(dir_path: str):
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)
    os.makedirs(dir_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python3 {sys.argv[0]} <XML_PATH>")
        exit(1)
    schema_path = sys.argv[1]
    schema = parse_xml_schema(schema_path)

    schema_name = schema_path[schema_path.index("/") + 1 : -4]

    print(f"Generating code for {schema_path}...")
    # print(json.dumps(schema, indent=4))

    print(f"Wiping src/ directory...")
    wipe_dir("src")

    print(f"Generating Rust code [src/lib.rs]...")
    rust_code = generate_rust_code_for_schema(schema)
    with open(f"src/lib.rs", "w") as f:
        f.write(rust_code)

    rust_code_main = generate_rust_code_main_for_schema(schema, schema_name)
    print(f"Generating Rust code [src/main.rs]...")
    with open(f"src/main.rs", "w") as f:
        f.write(rust_code_main)

    print(f"Wiping tests/ directory...")
    wipe_dir("tests")

    print(f"Generating Python code [tests/test_xparse.py]...")
    python_tests_code = generate_python_tests_for_schema(schema, schema_name)
    with open(f"tests/test_xparse.py", "w") as f:
        f.write(python_tests_code)
import xml.etree.ElementTree as ET
import shutil
import json
import sys
import os


HEADER_AND_UTIL_CODE = r"""use arrayref::array_ref;
use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;

pub fn string_to_char_array<const N: usize>(s: &str) -> Result<[char; N], &'static str> {
    if s.len() > N {
        return Err("String is too long");
    }

    let mut char_vec: Vec<char> = s.chars().collect();
    while char_vec.len() < N {
        char_vec.push(' '); // Fill the remaining spaces with a default character
    }

    // Attempt to convert Vec<char> into [char; N]
    let char_array: [char; N] = char_vec
        .try_into()
        .map_err(|_| "Failed to convert to array")?;
    Ok(char_array)
}

#[derive(Debug, PartialEq)]
pub struct Header {
    pub msg_size: u32,
    pub msg_type: u8,
    pub bitmask: u32,
}

impl Header {
    pub fn to_bytes(&self) -> [u8; 9] {
        let size_bytes = self.msg_size.to_be_bytes();
        let mask_bytes = self.bitmask.to_be_bytes();

        [
            size_bytes[0],
            size_bytes[1],
            size_bytes[2],
            size_bytes[3],
            self.msg_type,
            mask_bytes[0],
            mask_bytes[1],
            mask_bytes[2],
            mask_bytes[3],
        ]
    }

    pub fn from_bytes(buffer: &[u8; 9]) -> Self {
        let msg_size = u32::from_be_bytes([buffer[0], buffer[1], buffer[2], buffer[3]]);
        let msg_type = buffer[4];
        let bitmask = u32::from_be_bytes([buffer[5], buffer[6], buffer[7], buffer[8]]);

        Self {
            msg_size,
            msg_type,
            bitmask,
        }
    }
}

#[pyclass]
struct PyMessage {
    message: Message,
}

#[pymodule]
fn xparse(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<PyMessage>()?;
    Ok(())
}
"""


def get_test_value(rust_type: str, enum_schema) -> str:
    if rust_type[0] == "i":
        return "-123"
    elif rust_type[0] == "u":
        return "123"
    elif rust_type == "bool":
        return "true"
    elif rust_type.startswith("[char;"):
        return f"""string_to_char_array("John Doe").unwrap()"""
    elif rust_type.startswith("Option"):
        inner_type = rust_type[rust_type.index("<") + 1 : -1]
        return f"""Some({get_test_value(inner_type, enum_schema)})"""
    elif rust_type[0] == "f":
        return "3.14"
    elif rust_type.lower() in enum_schema:
        variant = list(enum_schema[rust_type.lower()].keys())[0].capitalize()
        return f"{rust_type}::{variant}"
    else:
        raise Exception(f"Unknown Rust type for get_test_value: {rust_type}")


def get_test_python_value(rust_type: str, enum_schema):
    if rust_type[0] == "i":
        return -123
    elif rust_type[0] == "u":
        return 123
    elif rust_type[0] == "f":
        return 3.14
    elif rust_type == "bool":
        return True
    elif rust_type.startswith("[char;"):
        return f"""'John Doe'"""
    elif rust_type.lower() in enum_schema:
        return 1
    elif rust_type.startswith("Option"):
        inner_rust_type = rust_type[rust_type.index("<") + 1 : -1]
        return get_test_python_value(inner_rust_type, enum_schema)
    else:
        raise Exception(f"Unknown Rust type for get_test_python_value: {rust_type}")


def parse_xml_schema(xml_file: str):
    tree = ET.parse(xml_file)
    root = tree.getroot()

    # Parsing enumTypes
    enum_types = {}
    for enumType in root.findall("./enumTypes/enumType"):
        enum_name = enumType.get("name")
        enum_values = {
            ev.get("name"): ev.get("value") for ev in enumType.findall("enumValue")
        }
        enum_types[enum_name] = enum_values

    # Parsing messageFormats
    message_formats = []
    for message_format in root.findall("./messageFormats/messageFormat"):
        format_details = {
            "id": message_format.get("id"),
            "name": message_format.get("name"),
            "attributes": [],
        }

        for attribute in message_format.findall("attribute"):
            attr_details = {
                "name": attribute.get("name"),
                "type": attribute.get("type"),
                "length": attribute.get("length"),
                "required": attribute.get("required") == "true",
            }
            format_details["attributes"].append(attr_details)

        message_formats.append(format_details)

    return enum_types, message_formats


def get_rust_type(attribute) -> str:
    if attribute.get("length") is None:
        length = 1
    else:
        length = int(attribute.get("length"))

    base_type, optional = (
        attribute["type"],
        not attribute["required"],
    )
    inner_type = ""
    if base_type == "int":
        inner_type = f"i{length * 8}"
    elif base_type == "uint":
        inner_type = f"u{length * 8}"
    elif base_type == "float":
        inner_type = f"f{length * 8}"
    elif base_type == "bool":
        inner_type = "bool"
    elif base_type == "str":
        inner_type = f"[char; {length}]"
    else:  # assume Enum here
        inner_type = base_type.capitalize()
    if optional:
        return f"Option<{inner_type}>"
    else:
        return inner_type


def generate_rust_code_for_schema(schema) -> str:
    code = HEADER_AND_UTIL_CODE

    def get_rust_num_bytes(rust_type: str) -> int:
        if rust_type[0] in ("i", "u", "f"):
            num_bits = int(rust_type[1:])
            return int(num_bits / 8)
        elif rust_type.startswith("[char"):
            # technically char is 4 bytes but we are presupposing ASCII so its only 1
            return int(rust_type[rust_type.index(";") + 1 : -1])
        elif rust_type == "bool":
            return 1
        elif rust_type.startswith("Option<"):
            return get_rust_num_bytes(rust_type[rust_type.index("<") + 1 : -1])
        else:  # assume enum
            return 1

    def get_serialization_code(
        att, rust_type: str, enum_schema, omit_self=False
    ) -> str:
        code = ""
        if rust_type.startswith("Option<"):
            inner_type = rust_type[rust_type.index("<") + 1 : -1]
            # [:-1] at end to exclude semicolon inside match arm
            if inner_type.lower() in enum_schema:
                extra = "&"
            else:
                extra = ""
            return f"""\t\tmatch {extra}self.{att} {{\n\t\t\tSome({att}) => {get_serialization_code(att, inner_type, enum_schema, omit_self=True)[:-1]},\n\t\t\t_ => {{}}\n\t\t}}"""
        else:
            if not omit_self:
                self_string = "self."
                tab_string = "\t\t"
            else:
                self_string = ""
                tab_string = ""

            if rust_type[0] in ("i", "u", "f"):
                return f"""{tab_string}buf.extend_from_slice(&{self_string}{att}.to_be_bytes());"""
            elif rust_type == "bool":
                return f"""{tab_string}buf.push(if {self_string}{att} {{ 1 }} else {{ 0 }});"""
            elif rust_type.startswith("[char;"):
                return f"""{tab_string}buf.append({self_string}{att}.iter().map(|&c| c as u8).collect::<Vec<u8>>().as_mut());"""
            else:  # assume Enum variant
                return f"""{tab_string}buf.push({self_string}{att}.to_u8());"""

    def get_bitmask_code(attribute_rust_types) -> str:
        code = "\t\tlet mut mask: u32 = 0;\n\n"
        cnt = 0
        for att_name, rust_type in attribute_rust_types:
            if rust_type.startswith("Option<"):
                code += f"""\t\tmatch self.{att_name} {{\n\t\t\tSome(_) => mask |= 1 << {cnt},\n\t\t\t_ => {{}}\n\t\t}}\n\n"""
                cnt += 1

        code += f"""\t\tmask\n\t}}"""
        return code

    def get_deserialization_code(attribute_rust_types) -> str:
        code = f"""\tfn deserialize(buffer: &[u8]) -> Result<Self, &'static str> {{\n"""
        code += f"""\t\tif buffer.len() < 9 {{\n\t\t\treturn Err("Buffer too short for header");\n\t\t}}\n\n"""

        code += f"""\t\tlet header = Header::from_bytes(array_ref![buffer, 0, 9]);\n"""
        code += f"""\t\tlet mut offset = 9;\n\n"""

        ok_code = f"""\t\tOk(Self {{\n"""

        opt_cnt = 0

        for i, pair in enumerate(attribute_rust_types):
            att_name, rust_type = pair
            ok_code += f"""\t\t\t{att_name},\n"""

            skip_offset = i == len(attribute_rust_types) - 1

            if rust_type.startswith("Option"):
                inner_rust_type = rust_type[rust_type.index("<") + 1 : -1]
                n = get_rust_num_bytes(inner_rust_type)

                code += f"""\t\tlet {att_name} = if header.bitmask & (1 << {opt_cnt}) != 0 {{\n"""
                opt_cnt += 1

                if inner_rust_type.startswith("[char;"):
                    code += f"""\t\t\tlet mut {att_name}_chars = [' '; {n}];\n"""
                    code += f"""\t\t\tfor i in 0..{n} {{\n"""
                    code += f"""\t\t\t\t{att_name}_chars[i] = buffer[offset + i] as char;\n"""
                    code += f"""\t\t\t}}\n"""

                    if not skip_offset:
                        code += f"""\t\t\toffset += {n};\n"""
                    code += f"""\t\t\tSome({att_name}_chars)\n"""

                elif inner_rust_type[0] in ("i", "u", "f"):
                    code += f"""\t\t\tlet {att_name}_value = {inner_rust_type}::from_be_bytes(buffer[offset..offset + {n}].try_into().map_err(|_| "Invalid buffer: {att_name}")?);\n"""

                    if not skip_offset:
                        code += f"""\t\t\toffset += {n};\n"""
                    code += f"""\t\t\tSome({att_name}_value)\n"""

                elif inner_rust_type[0] == "bool":
                    code += f"""\t\t\tlet {att_name}_value = buffer[offset] != 0;"""

                    if not skip_offset:
                        code += f"""\t\t\toffset += {n};\n"""
                    code += f"""\t\t\tSome({att_name}_value)\n"""

                else:  # assume Enum
                    code += f"""\t\t\tlet {att_name}_value = {inner_rust_type}::from_u8(buffer[offset]).map_err(|_| "Invalid buffer: {att_name}")?;\n"""
                    if not skip_offset:
                        code += f"""\t\t\toffset += 1;\n"""
                    code += f"""\t\t\tSome({att_name}_value)\n"""

                code += f"""\t\t}} else {{\n\t\t\tNone\n\t\t}};\n\n"""

            else:
                n = get_rust_num_bytes(rust_type)

                if rust_type.startswith("[char;"):
                    code += f"""\t\tlet mut {att_name} = [' '; {n}];\n"""
                    code += f"""\t\tfor i in 0..{n} {{\n"""
                    code += f"""\t\t\t{att_name}[i] = buffer[offset + i] as char;\n"""
                    code += f"""\t\t}}\n"""

                elif rust_type[0] in ("i", "u", "f"):
                    code += f"""\t\t let {att_name} = {rust_type}::from_be_bytes(buffer[offset..offset + {n}].try_into().map_err(|_| "Invalid buffer: {att_name}")?);\n"""

                elif rust_type == "bool":
                    code += f"""\t\tlet {att_name} = buffer[offset] != 0;\n"""

                else:  # assume Enum
                    code += f"""\t\tlet {att_name} = {rust_type}::from_u8(buffer[offset]).map_err(|_| "Invalid buffer: {att_name}")?;"""

                if not skip_offset:
                    code += f"""\t\toffset += {n};\n\n"""

        ok_code += f"""\t\t}})\n"""

        code += ok_code

        code += f"""\t}}"""
        return code

    enums_schema = schema[0]
    message_formats_schema = schema[1]

    # Generate code for Enum definitions and implementations
    for enum_name in enums_schema:
        code += f"""#[derive(PartialEq, Debug)]\n"""
        code += f"""pub enum {enum_name.capitalize()} {{\n"""

        for variant_name, variant_value in enums_schema[enum_name].items():
            code += f"""\t{variant_name.capitalize()} = {int(variant_value)},\n"""

        code += f"""}}\n\n"""

        code += f"""impl {enum_name.capitalize()} {{\n"""

        code += f"""\tpub fn from_u8(value: u8) -> Result<Self, &'static str> {{\n"""
        code += f"""\t\tmatch value {{\n"""
        for variant_name, variant_value in enums_schema[enum_name].items():
            code += f"""\t\t\t{int(variant_value)} => Ok({enum_name.capitalize()}::{variant_name.capitalize()}),\n"""
        code += (
            f"""\t\t\t_ => Err("Invalid value for enum {enum_name.capitalize()}"),\n"""
        )
        code += f"""\t\t}}\n"""
        code += f"""\t}}\n\n"""

        code += f"""\tpub fn to_u8(&self) -> u8 {{\n"""
        code += f"""\t\tmatch self {{\n"""
        for variant_name, variant_value in enums_schema[enum_name].items():
            code += f"""\t\t\t{enum_name.capitalize()}::{variant_name.capitalize()} => {int(variant_value)},\n"""
        code += f"""\t\t}}\n"""
        code += f"""\t}}\n\n"""

        code += f"""}}\n\n"""

    for message_format in message_formats_schema:
        code += f"""#[derive(PartialEq, Debug)]\npub struct {message_format['name'].capitalize()} {{\n"""
        attribute_rust_types = []
        for attribute in message_format["attributes"]:
            attribute_rust_types.append([attribute["name"], get_rust_type(attribute)])

        for attribute, rust_type in attribute_rust_types:
            code += f"    pub {attribute}: {rust_type},\n"
        code += "}\n\n"

        name = message_format["name"].capitalize()

        # begin impl
        code += f"""impl {name} {{\n"""

        # begin max_payload_size
        code += """    fn max_payload_size() -> usize {\n"""
        total_payload_size = 0
        for _, rt in attribute_rust_types:
            total_payload_size += get_rust_num_bytes(rt)
        code += f"\t\t{total_payload_size}"
        # end max_payload_size
        code += "\n    }\n\n"

        # begin serialize
        code += f"""\tfn serialize(&self) -> Vec<u8> {{\n"""
        code += f"""\t\tlet mut buf: Vec<u8> = Vec::with_capacity({name}::max_payload_size());\n\n"""

        for att, rust_type in attribute_rust_types:
            code += f"{get_serialization_code(att, rust_type, enums_schema)}\n\n"

        # end serialize
        code += """\n\t\tbuf\n\t}\n\n"""

        # get_bitmask
        code += f"""\tfn get_bitmask(&self) -> u32 {{\n"""
        code += f"""{get_bitmask_code(attribute_rust_types)}\n\n"""

        # deserialize
        code += f"""{get_deserialization_code(attribute_rust_types)}\n\n"""

        # get_example
        code += f"""\tpub fn get_example() -> Self {{\n"""
        code += f"""\t\tSelf {{\n"""
        for attrib in message_format["attributes"]:
            code += f"""\t\t\t{attrib['name']}: {get_test_value(get_rust_type(attrib), enums_schema)},\n"""
        code += f"""\t\t}}\n"""
        code += f"""\t}}\n"""

        # end struct impl
        code += "}\n\n"

    code += f"""#[derive(PartialEq, Debug)]\npub enum Message {{\n"""
    for message_format in message_formats_schema:
        name = message_format["name"].capitalize()
        code += f"    {name}({name}),\n"
    code += "}\n\n"

    # begin Message impl
    code += f"""impl Message {{\n"""

    # begin Message::serialize
    code += f"""\tpub fn serialize(&self) -> Vec<u8> {{\n"""
    code += f"""\t\tlet mut buffer = match self {{\n"""
    for message_format in message_formats_schema:
        code += f"""\t\t\tMessage::{message_format['name'].capitalize()}(p) => p.serialize(),\n"""
    code += f"""\t\t}};\n\n"""

    code += f"""\t\t// Create a buffer and prepend it to the buffer\n"""
    code += f"""\t\tlet header = Header {{\n"""
    code += f"""\t\t\tmsg_size: buffer.len() as u32 + 9, // +9 for header size\n"""
    code += f"""\t\t\tmsg_type: match self {{\n"""
    for i, message_format in enumerate(message_formats_schema):
        code += (
            f"""\t\t\t\tMessage::{message_format['name'].capitalize()}(_) => {i+1},\n"""
        )
    code += f"""\t\t\t}},\n"""
    code += f"""\t\t\tbitmask: self.get_bitmask(),\n"""
    code += f"""\t\t}};\n\n"""

    code += f"""\t\tlet mut header_bytes = header.to_bytes().to_vec();\n"""
    code += f"""\t\theader_bytes.append(&mut buffer);\n"""
    code += f"""\t\theader_bytes\n"""

    # end Message::serialize
    code += f"""\t}}\n\n"""

    # Message::get_bitmask
    code += f"""\tfn get_bitmask(&self) -> u32 {{\n"""
    code += f"""\t\tmatch self {{\n"""
    for message_format in message_formats_schema:
        code += f"""\t\t\tMessage::{message_format['name'].capitalize()}(p) => p.get_bitmask(),\n"""
    code += f"""\t\t}}\n"""
    code += f"""\t}}\n\n"""

    # begin Message::deserialize
    code += (
        f"""\tpub fn deserialize(buffer: &[u8]) -> Result<Self, &'static str> {{\n"""
    )
    code += f"""\t\tmatch buffer[4] {{\n"""
    for i, message_format in enumerate(message_formats_schema):
        name = message_format["name"]
        code += (
            f"""\t\t\t{i+1} => match {name.capitalize()}::deserialize(buffer) {{\n"""
        )
        code += f"""\t\t\t\tOk({name}) => Ok(Message::{name.capitalize()}({name})),\n"""
        code += f"""\t\t\t\tErr(e) => Err(e),\n"""
        code += f"""\t\t\t}},\n"""
    code += f"""\t\t\t_ => Err("Unknown message type id"),\n"""
    code += f"""\t\t}}\n"""
    # end Message::deserialize
    code += f"""\t}}\n\n"""

    # end Message impl
    code += f"""}}"""

    # begin PyMessage impl
    code += r"""#[pymethods]
impl PyMessage {
    fn to_bytes(&self) -> Vec<u8> {
        self.message.serialize()
    }

    #[staticmethod]
    fn from_bytes(buffer: Vec<u8>) -> PyResult<PyMessage> {
        match Message::deserialize(&buffer) {
            Ok(message) => Ok(PyMessage { message }),
            Err(e) => Err(PyValueError::new_err(e.to_string())),
        }
    }

    fn __repr__(&self) -> String {
        format!("{:?}", self.message)
    }

    fn __str__(&self) -> String {
        self.__repr__()
    }

    fn __eq__(&self, other: PyRef<PyMessage>) -> PyResult<bool> {
        Ok(self.message == other.message)
    }

"""
    # message format specific constructors
    for message_format in message_formats_schema:
        name = message_format["name"]
        code += f"""\t#[staticmethod]\n"""
        code += f"""\tfn {name}(\n"""

        # get attribute rust types again for constructor
        attribute_rust_types = []
        for attribute in message_format["attributes"]:
            attribute_rust_types.append([attribute["name"], get_rust_type(attribute)])

        # first pass - required attributes in args
        for att_name, rust_type in attribute_rust_types:
            if not "Option" in rust_type:
                if rust_type.lower() in enums_schema:
                    mapped_rust_type = "u8"
                elif "[char;" in rust_type:
                    mapped_rust_type = "String"
                else:
                    mapped_rust_type = rust_type

                code += f"""\t\t{att_name}: {mapped_rust_type},\n"""

        # second pass - optional attributes in args
        for att_name, rust_type in attribute_rust_types:
            if "Option" in rust_type:
                inner_rust_type = rust_type[rust_type.index("<") + 1 : -1]
                if inner_rust_type.lower() in enums_schema:
                    mapped_inner_rust_type = "u8"
                elif "[char;" in inner_rust_type:
                    mapped_inner_rust_type = "String"
                else:
                    mapped_inner_rust_type = inner_rust_type
                mapped_rust_type = f"Option<{mapped_inner_rust_type}>"
                code += f"""\t\t{att_name}: {mapped_rust_type},\n"""

        code += f"""\t) -> PyResult<PyMessage> {{\n"""

        # now iterate over attributes for the body, generating special code for handling strings and enums
        arg_listings = ""
        for att_name, rust_type in attribute_rust_types:
            if rust_type.startswith("Option"):
                inner_rust_type = rust_type[rust_type.index("<") + 1 : -1]
                if (
                    inner_rust_type[0] not in ("i", "u", "f")
                    and inner_rust_type != "bool"
                ):
                    # handle Opt<String> -> Opt<[char; _]>
                    if inner_rust_type.startswith("[char;"):
                        # map string to char array and wrap it on an opt
                        code += f"""\t\tlet {att_name}_array = {att_name}.map(|s| string_to_char_array(&s)).transpose().map_err(|_| PyValueError::new_err("Error converting {att_name} string to char array"))?;\n\n"""
                        arg_listings += f"""\t\t\t\t{att_name}: {att_name}_array,\n"""

                    # handle Opt<u8> -> Opt<Enum>
                    elif inner_rust_type.lower() in enums_schema:
                        code += f"""\t\tlet {att_name}_enum = match {att_name} {{\n"""
                        code += f"""\t\t\tSome(value) => match value {{\n"""
                        for k, v in enums_schema[inner_rust_type.lower()].items():
                            code += f"""\t\t\t\t{int(v)} => Some({inner_rust_type}::{k.capitalize()}),\n"""
                        code += f"""\t\t\t\t_ => return Err(PyValueError::new_err("Invalid enum value for {att_name}")),\n"""
                        code += f"""\t\t\t}},\n"""
                        code += f"""\t\t\tNone => None,\n"""
                        code += f"""\t\t}};\n\n"""
                        arg_listings += f"""\t\t\t\t{att_name}: {att_name}_enum,\n"""

                    # rage, rage against the dying of the light
                    else:
                        raise Exception(
                            f"Unknown Rust type inside Option: {inner_rust_type}"
                        )
                else:
                    # numbers are so easy, we could all take a page from their book
                    arg_listings += f"""\t\t\t\t{att_name},\n"""

            else:
                if rust_type[0] not in ("i", "u", "f") and rust_type != "bool":
                    # handle String -> [char; _];
                    if rust_type.startswith("[char;"):
                        code += f"""\t\tlet {att_name}_array = string_to_char_array(&{att_name}).map_err(|_| PyValueError::new_err("Error convering {att_name} string to char array"))?;\n\n"""
                        arg_listings += f"""\t\t\t\t{att_name}: {att_name}_array,\n"""

                    # handle u8 -> Enum
                    elif rust_type.lower() in enums_schema:
                        code += f"""\t\tlet {att_name}_enum = match {att_name} {{\n"""
                        for k, v in enums_schema[rust_type.lower()].items():
                            code += f"""\t\t\t{int(v)} => {rust_type}::{k.capitalize()},\n"""
                        code += f"""\t\t\t_ => return Err(PyValueError::new_err("Invalid enum value for {att_name}")),\n"""
                        code += f"""\t\t}};\n\n"""
                        arg_listings += f"""\t\t\t\t{att_name}: {att_name}_enum,\n"""

                    else:
                        raise Exception(f"Unknown Rust type: {rust_type}")
                else:
                    arg_listings += f"""\t\t\t\t{att_name},\n"""

        code += f"""\t\tOk(PyMessage {{\n"""
        code += (
            f"""\t\t\tmessage: Message::{name.capitalize()}({name.capitalize()} {{\n"""
        )
        code += arg_listings
        code += f"""\t\t\t}}),\n"""
        code += f"""\t\t}})\n"""
        code += f"""\t}}\n\n"""

    # end PyMessage impl
    code += f"""}}\n\n"""

    # begin tests
    code += r"""#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_header_serialization() {
        let header = Header {
            msg_size: 23,
            msg_type: 1,
            bitmask: 33, // Example bitmask (1 << 0 | 1 << 5)
        };

        let serialized = header.to_bytes();
        let deserialized = Header::from_bytes(&serialized);

        assert_eq!(header, deserialized);
    }

    #[test]
    fn test_header_fields() {
        let header = Header {
            msg_size: 100,
            msg_type: 2,
            bitmask: 18, // Example bitmask (1 << 1 | 1 << 4)
        };

        assert_eq!(header.msg_size, 100);
        assert_eq!(header.msg_type, 2);
        assert_eq!(header.bitmask, 18);
    }

"""
    for message_format in message_formats_schema:
        code += f"""\t#[test]\n"""
        name = message_format["name"]
        code += f"""\tfn test_{name}_serialize_deserialize() {{\n"""

        code += f"""\t\tlet message_original = Message::{name.capitalize()}({name.capitalize()}::get_example());\n\n"""

        code += f"""\t\tlet message_bytes = message_original.serialize();\n"""
        code += f"""\t\tlet message_result = Message::deserialize(&message_bytes).unwrap();\n\n"""
        code += f"""\t\t assert_eq!(message_original, message_result);\n"""

        code += f"""\t}}\n\n"""

    code += f"""}}\n"""

    return code


def generate_rust_code_main_for_schema(schema, schema_name) -> str:
    code = f"""use std::io::Write;\n"""
    code += f"""use xparse::{{Message"""
    message_formats_schema = schema[1]

    for message_format in message_formats_schema:
        code += f""", {message_format['name'].capitalize()}"""
    code += f"""}};\n\n"""

    code += f"""fn main() {{\n"""
    for message_format in message_formats_schema:
        name = message_format["name"]
        code += f"""\tlet {name} = Message::{name.capitalize()}({name.capitalize()}::get_example());\n\n"""
        code += f"""\tlet mut file = std::fs::File::create("{schema_name}_{name}.xb").unwrap();\n"""
        code += f"""\tfile.write_all(&{name}.serialize()).unwrap();\n\n"""

    code += f"""}}"""
    return code


def generate_python_tests_for_schema(schema, schema_name) -> str:
    code = f"""from xparse import PyMessage\n\n\n"""
    message_formats_schema = schema[1]
    enums_schema = schema[0]
    for message_format in message_formats_schema:
        name = message_format["name"]
        code += f"""def test_{name}_deserialize_serialize():\n"""
        code += f"""\tmessage_bytes = open("{schema_name}_{name}.xb", "rb").read()\n"""
        code += f"""\tmessage = PyMessage.from_bytes(message_bytes)\n"""
        code += f"""\tmessage_bytes_out = message.to_bytes()\n\n"""
        code += f"""\tfor x, y in zip(message_bytes, message_bytes_out):\n"""
        code += f"""\t\tassert x == y\n\n\n"""

        attribute_rust_types = []
        for attribute in message_format["attributes"]:
            attribute_rust_types.append([attribute["name"], get_rust_type(attribute)])

        code += f"""def test_{name}_serialize_deserialize():\n"""
        code += f"""\t{name} = PyMessage.{name}(\n"""
        for att_name, rust_type in attribute_rust_types:
            code += f"""\t\t{att_name}={get_test_python_value(rust_type, enums_schema)},\n"""
        code += f"""\t)\n"""
        code += f"""\t{name}_bytes = {name}.to_bytes()\n"""
        code += f"""\t{name}_result = PyMessage.from_bytes({name}_bytes)\n\n"""
        code += f"""\tassert {name} == {name}_result\n\n\n"""

    return code


def wipe_dir(dir_path: str):
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)
    os.makedirs(dir_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python3 {sys.argv[0]} <XML_PATH>")
        exit(1)
    schema_path = sys.argv[1]
    schema = parse_xml_schema(schema_path)

    schema_name = schema_path[schema_path.index("/") + 1 : -4]

    print(f"Generating code for {schema_path}...")
    # print(json.dumps(schema, indent=4))

    print(f"Wiping src/ directory...")
    wipe_dir("src")

    print(f"Generating Rust code [src/lib.rs]...")
    rust_code = generate_rust_code_for_schema(schema)
    with open(f"src/lib.rs", "w") as f:
        f.write(rust_code)

    rust_code_main = generate_rust_code_main_for_schema(schema, schema_name)
    print(f"Generating Rust code [src/main.rs]...")
    with open(f"src/main.rs", "w") as f:
        f.write(rust_code_main)

    print(f"Wiping tests/ directory...")
    wipe_dir("tests")

    print(f"Generating Python code [tests/test_xparse.py]...")
    python_tests_code = generate_python_tests_for_schema(schema, schema_name)
    with open(f"tests/test_xparse.py", "w") as f:
        f.write(python_tests_code)
