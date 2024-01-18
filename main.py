import xml.etree.ElementTree as ET
import json

HEADER_AND_UTIL_CODE = r"""use arrayref::array_ref;

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

"""

def parse_xml_schema(xml_file: str):
    tree = ET.parse(xml_file)
    root = tree.getroot()

    message_formats = []

    for message_format in root.findall("messageFormat"):
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

    return message_formats


def generate_rust_code_for_schema(message_formats) -> str:
    code = HEADER_AND_UTIL_CODE

    def get_rust_type(attribute) -> str:
        base_type, length, optional = (
            attribute["type"],
            int(attribute["length"]),
            not attribute["required"],
        )
        inner_type = ""
        if base_type == "integer":
            inner_type = f"i{length * 8}"
        elif base_type == "boolean":
            inner_type = "bool"
        elif base_type == "string":
            inner_type = f"[char; {length}]"

        if optional:
            return f"Option<{inner_type}>"
        else:
            return inner_type

    def get_rust_num_bytes(rust_type: str) -> int:
        if rust_type[0] in ('i', 'u'):
            num_bits = int(rust_type[1:])
            return int(num_bits / 8)
        elif rust_type.startswith('[char'):
            # technically char is 4 bytes but we are presupposing ASCII so its only 1
            return int(rust_type[rust_type.index(';') + 1:-1])
        elif rust_type == 'bool':
            return 1
        elif rust_type.startswith('Option<'):
            return get_rust_num_bytes(rust_type[rust_type.index('<') + 1:-1])


    def get_serialization_code(att, rust_type: str, omit_self=False) -> str:
        code = ""
        if rust_type.startswith('Option<'):
            inner_type = rust_type[rust_type.index('<')+1:-1]
            # [:-1] at end to exclude semicolon inside match arm
            return f"""\t\tmatch self.{att} {{\n\t\t\tSome({att}) => {get_serialization_code(att, inner_type, omit_self=True)[:-1]},\n\t\t\t_ => {{}}\n\t\t}}"""
        else:
            if not omit_self:
                self_string = "self."
                tab_string = "\t\t"
            else:
                self_string = ""
                tab_string = ""

            if rust_type[0] in ('i', 'u'):
                return f"""{tab_string}buf.extend_from_slice(&{self_string}{att}.to_be_bytes());"""
            elif rust_type == 'bool':
                return f"""{tab_string}buf.push(if {self_string}{att} {{ 1 }} else {{ 0 }});"""
            elif rust_type.startswith('[char;'):
                return f"""{tab_string}buf.append({self_string}{att}.iter().map(|&c| c as u8).collect::<Vec<u8>>().as_mut());"""

        return code

    def get_bitmask_code(attribute_rust_types) -> str:
        code = "\t\tlet mut mask: u32 = 0;\n\n"
        cnt = 0
        for att_name, rust_type in attribute_rust_types:
            if rust_type.startswith('Option<'):
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

        for att_name, rust_type in attribute_rust_types:
            ok_code += f"""\t\t\t{att_name},\n"""
            if rust_type.startswith('Option'):
                inner_rust_type = rust_type[rust_type.index('<')+1:-1]
                n = get_rust_num_bytes(inner_rust_type)

                code += f"""\t\tlet {att_name} = if header.bitmask & (1 << {opt_cnt}) != 0 {{\n"""
                opt_cnt += 1

                if inner_rust_type.startswith('[char;'):
                    code += f"""\t\t\tlet mut {att_name}_chars = [' '; {n}];\n"""
                    code += f"""\t\t\tfor i in 0..{n} {{\n"""
                    code += f"""\t\t\t\t{att_name}_chars[i] = buffer[offset + i] as char;\n"""
                    code += f"""\t\t\t}}\n"""

                    code += f"""\t\t\toffset += {n};\n"""
                    code += f"""\t\t\tSome({att_name}_chars)\n"""
            
                elif inner_rust_type[0] in ('i', 'u'):
                    code += f"""\t\t\tlet {att_name}_value = {inner_rust_type}::from_be_bytes(buffer[offset..offset + {n}].try_into().map_err(|_| "Invalid buffer: {att_name}")?);\n"""
                
                    code += f"""\t\t\toffset += {n};\n"""
                    code += f"""\t\t\tSome({att_name}_value)\n"""

                elif inner_rust_type[0] == 'bool':
                    code += f"""\t\t\tlet {att_name}_value = buffer[offset] != 0;"""

                    code += f"""\t\t\toffset += {n};\n"""
                    code += f"""\t\t\tSome({att_name}_value)\n"""
                
                code += f"""\t\t}} else {{\n\t\t\tNone\n\t\t}};\n\n"""

            else:
                n = get_rust_num_bytes(rust_type)

                if rust_type.startswith('[char;'):
                    code += f"""\t\tlet mut {att_name} = [' '; {n}];\n"""
                    code += f"""\t\tfor i in 0..{n} {{\n"""
                    code += f"""\t\t\t{att_name}[i] = buffer[offset + i] as char;\n"""
                    code += f"""\t\t}}\n"""
                
                elif rust_type[0] in ('i', 'u'):
                    code += f"""\t\t let {att_name} = {rust_type}::from_be_bytes(buffer[offset..offset + {n}].try_into().map_err(|_| "Invalid buffer: {att_name}")?);\n"""

                elif rust_type == 'bool':
                    code += f"""\t\tlet {att_name} = buffer[offset] != 0;\n"""

                code += f"""\t\toffset += {n};\n\n"""

        ok_code += f"""\t\t}})\n"""
        
        code += ok_code

        code += f"""\t}}"""
        return code


    for message_format in schema:
        code += f"""#[derive(PartialEq, Debug)]\npub struct {message_format['name'].capitalize()} {{\n"""
        attribute_rust_types = []
        for attribute in message_format["attributes"]:
            attribute_rust_types.append([attribute['name'], get_rust_type(attribute)])

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
            code += f"{get_serialization_code(att, rust_type)}\n\n"
        
        # end serialize
        code += """\n\t\tbuf\n\t}\n\n"""

        # get_bitmask
        code += f"""\tfn get_bitmask(&self) -> u32 {{\n"""
        code += f"""{get_bitmask_code(attribute_rust_types)}\n\n"""
        
        code += f"""{get_deserialization_code(attribute_rust_types)}\n\n"""

        # end struct impl
        code += "}\n\n"

    code += f"""#[derive(PartialEq, Debug)]\npub enum Message {{\n"""
    for message_format in schema:
        name = message_format["name"].capitalize()
        code += f"    {name}({name}),\n"
    code += "}\n\n"

    # begin Message impl
    code += f"""impl Message {{\n"""

    # begin Message::serialize
    code += f"""\tpub fn serialize(&self) -> Vec<u8> {{\n"""
    code += f"""\t\tlet mut buffer = match self {{\n"""
    for message_format in schema:
        code += f"""\t\t\tMessage::{message_format['name'].capitalize()}(p) => p.serialize(),\n"""
    code += f"""\t\t}};\n\n"""

    code += f"""\t\t// Create a buffer and prepend it to the buffer\n"""
    code += f"""\t\tlet header = Header {{\n"""
    code += f"""\t\t\tmsg_size: buffer.len() as u32 + 9, // +9 for header size\n"""
    code += f"""\t\t\tmsg_type: match self {{\n"""
    for i, message_format in enumerate(schema):
        code += f"""\t\t\t\tMessage::{message_format['name'].capitalize()}(_) => {i+1},\n"""
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
    for message_format in schema:
        code += f"""\t\t\tMessage::{message_format['name'].capitalize()}(p) => p.get_bitmask(),\n"""
    code += f"""\t\t}}\n"""
    code += f"""\t}}\n\n"""

    # begin Message::deserialize
    code += f"""\tpub fn deserialize(buffer: &[u8]) -> Result<Self, &'static str> {{\n"""
    code += f"""\t\tmatch buffer[4] {{\n"""
    for i, message_format in enumerate(schema):
        name = message_format['name']
        code += f"""\t\t\t{i+1} => match {name.capitalize()}::deserialize(buffer) {{\n"""
        code += f"""\t\t\t\tOk({name}) => Ok(Message::{name.capitalize()}({name})),\n"""
        code += f"""\t\t\t\tErr(e) => Err(e),\n"""
        code += f"""\t\t\t}},\n"""
    code += f"""\t\t\t_ => Err("Unknown message type id"),\n"""
    code += f"""\t\t}}\n"""
    # end Message::deserialize
    code += f"""\t}}\n"""

    # end Message impl
    code += f"""}}"""
    return code


if __name__ == "__main__":
    schema = parse_xml_schema("example_schema.xml")

    print(json.dumps(schema, indent=4))

    rust_code = generate_rust_code_for_schema(schema)

    with open(f"src/lib.rs", "w") as f:
        f.write(rust_code)
