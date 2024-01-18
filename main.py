import xml.etree.ElementTree as ET
import json


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
    code = r"""use arrayref::array_ref;

fn string_to_char_array<const N: usize>(s: &str) -> Result<[char; N], &'static str> {
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
struct Header {
    msg_size: u32,
    msg_type: u8,
    bitmask: u32,
}

impl Header {
    fn to_bytes(&self) -> [u8; 9] {
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

    fn from_bytes(buffer: &[u8; 9]) -> Self {
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

    for message_format in schema:
        code += f"""#[derive(PartialEq, Debug)]
struct {message_format['name'].capitalize()} {{
"""
        for attribute in message_format["attributes"]:
            code += f"    {attribute['name']}: {get_rust_type(attribute)},\n"
        code += "}\n\n"

    code += f"""#[derive(PartialEq, Debug)]
enum Message {{
"""
    for message_format in schema:
        name = message_format["name"].capitalize()
        code += f"    {name}({name}),\n"
    code += "}\n\n"

    for message_format in schema:
        name = message_format["name"].capitalize()
        code += f"""impl {name} {{
"""
        code += """    fn max_payload_size() -> usize {
"""

        code += "    }\n\n"

        code += "}\n"

    return code


if __name__ == "__main__":
    schema = parse_xml_schema("example_schema.xml")

    print(json.dumps(schema, indent=4))

    rust_code = generate_rust_code_for_schema(schema)

    with open(f"src/foo.rs", "w") as f:
        f.write(rust_code)
